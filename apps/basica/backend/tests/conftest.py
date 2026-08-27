"""Fixtures dos testes da API de leitura.

Os testes rodam contra um PostgreSQL DE VERDADE, e nao contra um duble. Duas
razoes:

  1. A parte dificil deste adaptador e o SQL -- o keyset de paginacao, o
     `date_bin` da serie temporal, o `GROUP BY` do breakdown. Um duble que
     respondesse "ok" a tudo isso testaria apenas o duble, que foi exatamente o
     defeito encontrado no backend anterior.

  2. A barreira contra vazamento de futuro e do BANCO (o GRANT em `argus_reader`
     mais o `WHERE available_at <= sim.now()` da view). So da para verificar
     isso contra um banco que tem GRANT e tem view.

O dado entra pelas MESMAS fixtures que o worker usa -- uma fonte de verdade so
para os dois lados do pipeline.

Suba o banco com `make db-local`. Sem ele, os testes sao PULADOS.
"""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from telemetry import create_app

SALT = "test-salt"

# Instante virtual fixo. As fixtures sao todas de 2026-07-13, e uma consulta sem
# periodo fecha a janela em `sim.now()` -- com o relogio andando, estes testes
# passariam por proximidade da data e falhariam semanas depois sem nenhuma
# mudanca de codigo. `speed = 0` congela o relogio virtual de vez.
REFERENCE_NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)

# As mesmas fixtures que o worker usa.
FIXTURES_DIR = Path(__file__).resolve().parents[2] / "worker" / "tests" / "fixtures"
TOOLS = Path(__file__).resolve().parents[2] / "tools"


@pytest.fixture(scope="session")
def sample_events() -> dict[str, dict]:
    """Os seis eventos reais exportados do BI."""
    eventos = {}
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        eventos[path.stem] = json.loads(path.read_text(encoding="utf-8"))
    assert eventos, f"nenhuma fixture em {FIXTURES_DIR}"
    return eventos


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL do PostgreSQL de teste, ou pula a suite."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL nao definida (rode `make db-local`)")

    import psycopg

    try:
        with psycopg.connect(url, connect_timeout=2):
            pass
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL de teste indisponivel (rode `make db-local`)")
    return url


@pytest.fixture(scope="session")
def _migrated(database_url) -> str:
    """Aplica as migrations uma vez por sessao de teste."""
    resultado = subprocess.run(
        [sys.executable, str(TOOLS / "migrate.py"), "aplicar"],
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        pytest.fail(f"migrations falharam:\n{resultado.stdout}\n{resultado.stderr}")
    return database_url


@pytest.fixture
def pool(_migrated):
    """Pool de conexao com o banco limpo e o relogio virtual congelado."""
    from telemetry.infrastructure.postgres import build_pool

    p = build_pool(_migrated, min_size=1, max_size=2)
    with p.connection() as conn:
        conn.execute(
            """
            TRUNCATE silver.session_event, silver.signal_bucket,
                     gold.feature_bucket, gold.source_series, gold.incident_window,
                     gold.live_event_window, gold.deploy_event
              RESTART IDENTITY CASCADE
            """
        )
        # speed = 0 congela o relogio: sem isso, `sim.now()` andaria durante o
        # proprio teste e uma linha carimbada "disponivel daqui a um segundo"
        # apareceria no meio da execucao.
        conn.execute("SELECT sim.set_clock(%s, 0)", (REFERENCE_NOW,))
    yield p
    p.close()


def _inserir_eventos(pool, eventos: dict[str, dict]) -> None:
    """Grava os seis eventos em silver.session_event.

    Escreve na SILVER e nao na bronze porque o que se testa aqui e a LEITURA. O
    caminho bronze -> silver ja tem cobertura propria nos testes do worker;
    repeti-lo aqui so acoplaria a suite da API ao ETL.

    Args:
        pool: Pool de conexao.
        eventos (dict[str, dict]): Eventos crus das fixtures.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker" / "src"))
    from argus_worker.keys import build_row
    from argus_worker.models import parse_event
    from psycopg.types.json import Jsonb

    linhas = []
    for cru in eventos.values():
        evento, _ = parse_event(cru)
        # Monta a linha com o MESMO codigo que o worker usa: e o que impede a
        # API e o worker de divergirem em silencio sobre o que e envelope e o
        # que e payload.
        linha = build_row(evento, ingested_at=REFERENCE_NOW, max_clock_skew_days=36500)
        linhas.append(linha)

    with pool.connection() as conn, conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO silver.session_event (
              ts, event_id, event_name, session_id, device_id, user_id,
              app_bucket, app_env, app_target, app_version,
              device_manufacturer, device_model, device_os, route_path,
              duration, uf, isp, payload, available_at, _lsn)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, 1)
            ON CONFLICT (ts, event_id) DO NOTHING
            """,
            [
                (
                    linha["ts"], linha["event_id"], linha["event_name"],
                    linha["session_id"], linha["device_id"], linha.get("user_id"),
                    linha.get("app_bucket"), linha.get("app_env"),
                    linha.get("app_target"), linha.get("app_version"),
                    linha.get("device_manufacturer"), linha.get("device_model"),
                    linha.get("device_os"), linha.get("route_path"),
                    linha.get("duration"), None, None,
                    Jsonb(linha["payload"]),
                    # available_at no passado: o grain de sessao chega do
                    # proprio aparelho, sem batch no meio.
                    linha["ts"],
                )
                for linha in linhas
            ],
        )


@pytest.fixture
def inserir(pool):
    """Insere um evento avulso, para os testes que precisam de um caso extra.

    Substitui o `table.put_item(build_item(...))` da v2. Passa pelo MESMO
    `build_row` do worker, e nao por um INSERT montado a mao -- o ponto e que o
    teste exercite o formato que a ingestao realmente produz.
    """

    def _inserir(evento: dict) -> None:
        _inserir_eventos(pool, {"avulso": evento})

    return _inserir


@pytest.fixture
def seeded(pool, sample_events):
    """Banco com os seis eventos reais carregados."""
    _inserir_eventos(pool, sample_events)
    return pool


@pytest.fixture
def repository(pool):
    """Repositorio de eventos apontando para o banco de teste."""
    from telemetry.infrastructure.postgres import PostgresEventRepository

    return PostgresEventRepository(pool, user_id_hash_salt=SALT, max_items_scanned=1000)


@pytest.fixture
def gold_repository(pool):
    """Repositorio da camada gold apontando para o banco de teste."""
    from telemetry.infrastructure.gold import GoldRepository

    return GoldRepository(pool)


@pytest.fixture
def signals_repository(pool):
    """Repositorio de `/api/v1/signals` apontando para o banco de teste.

    `baseline_hours=168` (padrao) olharia 7 dias para tras a partir de
    `REFERENCE_NOW` -- mais do que as fixtures de teste cobrem. Os testes
    usam uma janela de baseline curta para caber nas poucas horas que as
    fixtures inserem.
    """
    from telemetry.infrastructure.signals import SignalsRepository

    return SignalsRepository(pool, baseline_hours=6)


@pytest.fixture
def app(repository, gold_repository, signals_repository):
    """Aplicacao Flask com os tres repositorios injetados."""
    from telemetry.config import TestConfig

    aplicacao = create_app(
        TestConfig, repository=repository, gold=gold_repository, signals=signals_repository
    )
    aplicacao.config["USER_ID_HASH_SALT"] = SALT
    return aplicacao


@pytest.fixture
def client(app):
    """Cliente de teste do Flask."""
    return app.test_client()
