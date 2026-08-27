"""Simulador: avanca o relogio virtual e reemite o dump como se fosse agora.

O laco, a cada tick de parede:

  1. Le `sim.now()` -- o relogio virtual, que anda sozinho a `speed` vezes o
     tempo de parede.
  2. Le da bronze as linhas cuja coluna de tempo caiu na janela que acabou de
     passar.
  3. Aplica as falhas de `sim.fault` que alcancam cada linha.
  4. Emite tudo em POST /v1/changes, com `captured_at` no tempo VIRTUAL.

Nao ha `sleep` proporcional ao tempo virtual, nem contador de ticks: a posicao
do relogio e derivada do relogio de parede por `sim.now()`. Se um tick demorar
mais que o previsto, o proximo simplesmente le uma janela maior -- o tempo
virtual nao acumula atraso, que e o que manteria `available_at` coerente com o
que as telas mostram.

Uso:
    python -m argus_simulator
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import sys

from argus_common import Database, Heartbeat, Metrics, ShutdownSignal, configure_logging

from .clock import TABELAS, Clock, Janela
from .emitter import Emitter
from .faults import sortear

log = logging.getLogger(__name__)


def _env(name: str, default: str) -> str:
    """Le uma variavel de ambiente com padrao.

    Args:
        name (str): Nome da variavel.
        default (str): Valor padrao.

    Returns:
        str: Valor lido.
    """
    raw = os.getenv(name)
    return raw if raw and raw.strip() else default


def _ts(raw: str) -> dt.datetime:
    """Converte texto ISO-8601 em datetime com fuso.

    Args:
        raw (str): Texto ISO-8601, com ou sem o sufixo Z.

    Returns:
        datetime: Instante em UTC.
    """
    momento = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return momento if momento.tzinfo else momento.replace(tzinfo=dt.UTC)


def main() -> int:
    """Ponto de entrada.

    Returns:
        int: 0 em sucesso, 1 em falha.
    """
    service_name = _env("SERVICE_NAME", "argus-simulator")
    log_ = configure_logging(_env("LOG_LEVEL", "INFO").upper(), service_name)

    url = os.getenv("CHANGES_URL")
    if not url:
        print("erro: CHANGES_URL nao definida.", file=sys.stderr)
        return 1

    seed = int(_env("SIM_SEED", "20260821"))
    speed = float(_env("SIM_SPEED", "60"))
    t0 = _ts(_env("SIM_T0", "2026-07-12T00:00:00Z"))
    t1 = _ts(_env("SIM_T1", "2026-08-05T23:59:59Z"))
    tick = float(_env("SIM_TICK_SECONDS", "5"))

    metrics = Metrics(_env("METRICS_NAMESPACE", "Argus/Ingestion"), service_name)
    heartbeat = Heartbeat(_env("HEARTBEAT_PATH", "/tmp/argus-heartbeat"))
    shutdown = ShutdownSignal()

    db = None
    emitter = None
    run_id = None
    clock = None
    try:
        db = Database.from_env(min_size=1, max_size=3, application_name=service_name)
        clock = Clock(db)
        emitter = Emitter(url)

        # As chaves primarias vem do catalogo, e nao de uma lista escrita a mao:
        # sao a mesma verdade que o MERGE usa do outro lado.
        pks = {
            tabela: [
                linha["coluna"]
                for linha in db.fetch_all(
                    "SELECT unnest(bronze.pk_de(%s)) AS coluna", (tabela,)
                )
                if not linha["coluna"].startswith("_")
            ]
            for tabela in TABELAS
        }

        run_id = clock.abrir_run(seed, t0, t1, speed)
        falhas = sortear(seed, t0, t1, clock.fontes())
        clock.registrar_falhas(run_id, falhas)
        clock.reset(t0, speed)

        janela = Janela(db)
        anterior = t0

        log_.info(
            "simulador iniciado",
            extra={
                "run_id": run_id,
                "seed": seed,
                "speed": speed,
                "t0": t0.isoformat(),
                "t1": t1.isoformat(),
                "falhas": len(falhas),
                "tabelas": sorted(TABELAS),
            },
        )

        while shutdown.running:
            heartbeat.touch()
            agora = clock.now()

            if agora >= t1:
                log_.info(
                    "fim da janela simulada",
                    extra={"run_id": run_id, "sim_now": agora.isoformat()},
                )
                # Congela exatamente em t1. O tick pode acordar alguns segundos
                # depois; deixar esse excesso no relogio vazaria para a API.
                clock.fechar_run(run_id, "done", t1)
                break

            emitidos = 0
            for tabela, _coluna in TABELAS.items():
                linhas = janela.ler(tabela, anterior, agora)
                if not linhas:
                    continue

                atingidas = _aplicar_falhas(linhas, tabela, falhas, agora)
                if atingidas:
                    metrics.count("RowsFaulted", atingidas)

                emitidos += emitter.emitir(tabela, linhas, pks[tabela], agora, run_id)

            metrics.count("ChangesEmitted", emitidos)
            metrics.duration_ms(
                "SimWindowSeconds", (agora - anterior).total_seconds() * 1000
            )
            metrics.flush()

            log_.info(
                "tick",
                extra={
                    "sim_now": agora.isoformat(),
                    "janela_s": round((agora - anterior).total_seconds()),
                    "emitidos": emitidos,
                },
            )

            anterior = agora
            shutdown.sleep(tick)

        if shutdown.running is False and run_id is not None:
            clock.fechar_run(run_id, "paused")
        log_.info("simulador encerrado", extra={"run_id": run_id})

    except Exception:
        log_.exception("simulador abortou")
        if clock is not None and run_id is not None:
            try:
                clock.fechar_run(run_id, "paused")
            except Exception:
                log_.warning("nao consegui marcar a execucao como pausada")
        return 1
    finally:
        if emitter is not None:
            emitter.close()
        if db is not None:
            db.close()
    return 0


def _aplicar_falhas(linhas: list[dict], tabela: str, falhas, agora: dt.datetime) -> int:
    """Distorce, no lugar, as linhas alcancadas por alguma falha.

    A distorcao acontece AQUI e nao no banco de proposito: a bronze guarda o
    dump como a Globo entregou, e o que sai distorcido e a observacao que o
    simulador emite. Assim a mesma carga inicial serve para quantos cenarios se
    queira, e reiniciar com outra seed nao exige recarregar 68,7 M de linhas.

    Args:
        linhas (list[dict]): Linhas lidas da bronze. Modificadas no lugar.
        tabela (str): Tabela de origem.
        falhas (list[Falha]): Falhas da execucao.
        agora (datetime): Instante virtual do tick.

    Returns:
        int: Quantas linhas foram distorcidas.
    """
    if not falhas:
        return 0

    # `signal_bucket` e `signal_point` tem source/entity/metric; `ca_point` e
    # `rpaas_bucket` nao. Para essas, a fonte e o proprio nome da tabela, o que
    # deixa uma falha de `source_outage` continuar fazendo sentido.
    padrao = {"ca_point": "cloudarmor", "rpaas_bucket": "rpaas"}.get(tabela, tabela)

    atingidas = 0
    for linha in linhas:
        source = linha.get("source") or padrao
        entity = linha.get("entity") or linha.get("app") or linha.get("vhost") or ""
        metric = linha.get("metric") or ""

        for falha in falhas:
            if not falha.alcanca(agora, source, entity, metric):
                continue
            # A coluna de valor tambem muda de nome por tabela.
            for campo in ("value", "rps", "requests_5xx", "requests_total"):
                if campo in linha and isinstance(linha[campo], (int, float)):
                    linha[campo] = falha.aplicar(float(linha[campo]))
            atingidas += 1
            break  # uma falha por linha: composta nao seria mais realista

    return atingidas


if __name__ == "__main__":
    sys.exit(main())
