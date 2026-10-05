"""Compara o roteiro do agente com o motor atual sobre as mesmas fixtures.

Execucao local de avaliacao: o motor usa suas funcoes reais, com baseline vazio.
Sem historico de slots anteriores, este ensaio nao reproduz um run publicado.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/fullstack/agente/src"))

from argus_processing.catalog import Catalog  # noqa: E402
from argus_processing.detector import detect  # noqa: E402
from argus_processing.domain import Fact  # noqa: E402
from argus_processing.quality import evaluate_quality  # noqa: E402
from argus_processing.rules import build_candidates, evaluate_candidates  # noqa: E402

from argus_agente.casos import carregar_caso  # noqa: E402
from argus_agente.lote import executar_lote  # noqa: E402
from argus_agente.modelo import ModeloDeRoteiro  # noqa: E402


def _instante(valor: str | None):
    """Converte o horario do caso para o tipo do motor."""
    from datetime import datetime

    return datetime.fromisoformat(valor.replace("Z", "+00:00")) if valor else None


def _fato(linha: dict) -> Fact:
    """Converte um fato ja selecionado pelo leitor ao tipo do motor."""
    return Fact(
        **{
            chave: _instante(linha[chave])
            if chave in {"event_start", "event_end", "available_at"}
            else linha[chave]
            for chave in Fact.__dataclass_fields__
        }
    )


def main() -> None:
    """Executa ambos os caminhos e grava um resumo estruturado."""
    pasta = ROOT / "apps/fullstack/agente/fixtures"
    caminhos = sorted(pasta.glob("caso-*.json"))
    roteiros = pasta / "roteiros"
    destino = ROOT / "artefatos/comparacao-hipoteses"
    destino.mkdir(parents=True, exist_ok=True)
    registros = executar_lote(
        caminhos,
        lambda case_id: ModeloDeRoteiro(
            json.loads((roteiros / f"{case_id}.json").read_text(encoding="utf-8")),
            nome=case_id,
        ),
        destino=destino / "agente-roteiro",
    )
    relatorio = destino / "agente-roteiro/relatorio.md"
    relatorio.write_text(
        relatorio.read_text(encoding="utf-8").rstrip() + "\n", encoding="utf-8"
    )
    catalogo = Catalog("comparacao-local")
    saidas = []
    for caminho, registro in zip(caminhos, registros, strict=True):
        caso, leitor = carregar_caso(caminho)
        fatos = tuple(_fato(linha) for linha in leitor.facts)
        inicio = min(fato.event_start for fato in fatos)
        qualidade = evaluate_quality(
            fatos, catalogo, window_start=inicio, window_end=caso.recorte.sim_now
        )
        anomalias, baselines = detect(fatos, {}, catalogo)
        candidatos = build_candidates(anomalias, fatos, qualidade, catalogo)
        hipoteses, prefiltrados, avaliados, truncados = evaluate_candidates(
            candidatos, anomalias, qualidade, catalogo
        )
        saidas.append(
            {
                "case_id": caso.case_id,
                "recorte": caso.recorte.para_json(),
                "fatos_visiveis": len(fatos),
                "agente": {
                    "modo": "roteiro_fixo_sem_modelo",
                    "desfecho": registro.desfecho,
                    "hipotese": registro.hipotese,
                    "lacunas": registro.lacunas,
                    "consultas": len(registro.consultas),
                    "arquivo": f"agente-roteiro/casos/{caso.case_id}.json",
                },
                "motor": {
                    "modo": "funcoes_reais_sem_baseline_historico",
                    "anomalias": len(anomalias),
                    "candidatos_prefiltrados": prefiltrados,
                    "candidatos_avaliados": avaliados,
                    "candidatos_truncados": truncados,
                    "hipoteses": [
                        {
                            "family": item.family,
                            "title": item.title,
                            "summary": item.summary,
                            "evaluation_status": item.evaluation_status,
                            "score": item.score,
                            "coverage": item.coverage,
                        }
                        for item in hipoteses
                    ],
                    "fontes_com_qualidade": len(qualidade),
                    "slots_de_baseline_apos_caso": len(baselines),
                },
            }
        )
    (destino / "resultados.json").write_text(
        json.dumps(
            {
                "tipo": "ensaio_sintetico",
                "limites": [
                    "agente usa roteiro fixo, nao Ollama",
                    "motor usa baseline inicial vazio; nao equivale a run publicado",
                    "mesmos fatos e corte causal; digest do motor publicado indisponivel",
                ],
                "casos": saidas,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for saida in saidas:
        print(
            saida["case_id"],
            "agente:",
            saida["agente"]["desfecho"],
            "motor:",
            saida["motor"]["anomalias"],
            "anomalias,",
            len(saida["motor"]["hipoteses"]),
            "hipoteses",
        )


if __name__ == "__main__":
    main()
