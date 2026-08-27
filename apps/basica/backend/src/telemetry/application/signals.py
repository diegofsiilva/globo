"""Sinais em desvio ativo, para a tela Agora (rotas-frontend.md §4.4.2).

Usa `infrastructure.signals.SignalsRepository.desvios` para responder "quais
grupos estao FORA do baseline AGORA, ha quantos buckets seguidos, e desde
quando" -- o que a tela Agora chama de "degradação ativa". Independente do
motor de hipoteses (em desenvolvimento por outro integrante em
`feat/hipotese`): sem `detect.anomaly` populado (nenhum detector roda ainda)
nem `gold.circadian_state` (nenhum job o preenche), o baseline e recalculado
a cada chamada, direto de `gold.v_feature_bucket`.

`severity` (`critical`/`warning`/`stable`) e `trend` (serie bruta de valores,
para sparkline) foram desenhados contra o mock real de
`agora/_mocks/scenario.ts` (`SignalDeviation`/`OpenDegradation`), nao
inventados -- ver double-check em `rotas-frontend.md` §1.1.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime
from typing import Any

# So vira sinal o que ainda esta desviado no ULTIMO bucket da janela --
# "ativo agora", nao "desviou em algum momento".
LIMIAR_SINAL = 2.0

# Faixas de severidade sobre |z|. LIMIAR_SINAL e o piso de entrada (abaixo
# disso nem vira sinal), entao "stable" aqui significa "desviado, mas na
# faixa mais fraca que ainda conta como sinal" -- nao "sem desvio".
LIMIAR_WARNING = 2.5
LIMIAR_CRITICAL = 4.0


def _severidade(z: float) -> str:
    magnitude = abs(z)
    if magnitude >= LIMIAR_CRITICAL:
        return "critical"
    if magnitude >= LIMIAR_WARNING:
        return "warning"
    return "stable"


def _signal_id(source: str, entity: str, metric: str) -> str:
    # Sem ancora de tempo no hash: um sinal e identidade do GRUPO, nao de um
    # pico especifico -- o mesmo sinal, consultado de novo minutos depois,
    # deve manter o mesmo id.
    chave = f"{source}|{entity}|{metric}"
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()[:16]


class GenerateSignals:
    """Monta a lista de sinais ativos a partir dos desvios do repository."""

    def __init__(self, repository) -> None:
        """Inicializa o caso de uso.

        Args:
            repository: `SignalsRepository` (ou equivalente de teste) --
                reusa `desvios` e `contagem_sessoes`.
        """
        self.repository = repository

    def execute(self, desde: datetime, ate: datetime) -> dict[str, Any]:
        """Gera a lista de sinais ativos na janela.

        Args:
            desde (datetime): Inicio da janela analisada.
            ate (datetime): Fim da janela analisada.

        Returns:
            dict[str, Any]: `{"items": [...]}`, do desvio mais forte para o
                mais fraco.
        """
        linhas = self.repository.desvios(desde, ate)

        grupos: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for linha in linhas:
            grupos[(linha["source"], linha["entity"], linha["metric"])].append(linha)

        sinais = []
        for (source, entity, metric), buckets in grupos.items():
            buckets.sort(key=lambda b: b["bucket_ts"])
            ultimo = buckets[-1]
            if ultimo["z"] is None or abs(ultimo["z"]) < LIMIAR_SINAL:
                continue

            consecutivos = 0
            for bucket in reversed(buckets):
                if bucket["z"] is not None and abs(bucket["z"]) >= LIMIAR_SINAL:
                    consecutivos += 1
                else:
                    break
            detectado_em = buckets[len(buckets) - consecutivos]["bucket_ts"]

            anterior = buckets[-2]["z"] if len(buckets) >= 2 else None
            if anterior is None:
                direcao = "estavel"
            elif abs(ultimo["z"]) > abs(anterior) + 0.1:
                direcao = "subindo"
            elif abs(ultimo["z"]) < abs(anterior) - 0.1:
                direcao = "descendo"
            else:
                direcao = "estavel"

            multiplicador = (
                round(ultimo["value"] / ultimo["media"], 2)
                if ultimo["media"] not in (None, 0)
                else None
            )

            # threshold_z (2.0) e em desvios-padrao, nao na unidade nativa da
            # metrica -- o front nao pode mostrar "z >= 2.0" pro operador sem
            # contexto. threshold_value e o mesmo limiar convertido de volta
            # pra unidade da metrica, do lado em que o desvio esta acontecendo
            # (sinal de z decide se o limiar fica acima ou abaixo do baseline).
            lado = 1 if ultimo["z"] >= 0 else -1
            threshold_value = (
                round(ultimo["media"] + lado * LIMIAR_SINAL * ultimo["desvio"], 2)
                if ultimo["media"] is not None and ultimo["desvio"] is not None
                else None
            )

            sinais.append(
                {
                    "id": _signal_id(source, entity, metric),
                    "source": source,
                    "entity": entity,
                    "metric": metric,
                    "title": f"{metric} de {entity} ({source}) fora do baseline horario",
                    "current_value": ultimo["value"],
                    "baseline": ultimo["media"],
                    "stddev": ultimo["desvio"],
                    "multiplier": multiplicador,
                    "z": round(ultimo["z"], 2),
                    "threshold_z": LIMIAR_SINAL,
                    "threshold_value": threshold_value,
                    "severity": _severidade(ultimo["z"]),
                    "consecutive_buckets_over_threshold": consecutivos,
                    "detected_at": detectado_em.isoformat(),
                    "time_since_detection_seconds": round((ate - detectado_em).total_seconds()),
                    "sessions_impacted": self.repository.contagem_sessoes(detectado_em, ate),
                    "direction": direcao,
                    # Serie bruta (nao so os buckets acima do limiar) para uma
                    # sparkline com contexto de antes/durante o desvio.
                    "trend": [b["value"] for b in buckets],
                }
            )

        sinais.sort(key=lambda s: abs(s["z"]), reverse=True)
        return {"items": sinais}
