"""Gravacao dos resultados -- o rastro que o Dia 5 exige do lote.

Cada caso vira um JSON completo, com tudo o que seria preciso para reexecutar e
conferir. O Markdown nao acrescenta informacao: e a porta de entrada da revisao
humana, que precisa decidir rapidamente quais casos merecem leitura inteira.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from argus_agente.contrato import RegistroDoCaso

ROTULOS = {
    "hipotese": "hipotese",
    "evidencia_insuficiente": "evidencia insuficiente",
    "teto_atingido": "teto atingido",
    "resposta_invalida": "resposta invalida",
    "erro_de_execucao": "erro de execucao",
}


def escrever_caso(registro: RegistroDoCaso, destino: Path) -> Path:
    """Grava o registro completo de um caso.

    Args:
        registro (RegistroDoCaso): Resultado da investigacao.
        destino (Path): Diretorio de saida, criado se nao existir.

    Returns:
        Path: Arquivo escrito.
    """
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"{registro.case_id}.json"
    arquivo.write_text(
        json.dumps(registro.para_json(), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return arquivo


def resumo_markdown(registros: Iterable[RegistroDoCaso]) -> str:
    """Monta o relatorio de um lote.

    Args:
        registros (Iterable[RegistroDoCaso]): Casos ja investigados.

    Returns:
        str: Markdown com a tabela do lote e o detalhe de cada caso.
    """
    registros = list(registros)
    linhas = [
        "# Lote do piloto de hipoteses com IA",
        "",
        "Resultados experimentais. Uma hipotese aqui e explicacao candidata, nao",
        "causa confirmada; a leitura e humana.",
        "",
        f"Casos: {len(registros)}. "
        + ", ".join(
            f"{ROTULOS[desfecho]}: {total}"
            for desfecho, total in sorted(_contagem(registros).items())
        ),
        "",
        "| Caso | Desfecho | Chamadas | Fatos citados | Contestada | Observacao |",
        "|---|---|---|---|---|---|",
    ]
    for registro in registros:
        consumo = registro.metricas.get("consumo", {})
        citados = _fatos_citados(registro)
        linhas.append(
            "| {caso} | {desfecho} | {chamadas} | {citados} "
            "| {contestada} | {obs} |".format(
                caso=registro.case_id,
                desfecho=ROTULOS.get(registro.desfecho, registro.desfecho),
                chamadas=consumo.get("chamadas", 0),
                citados=citados,
                contestada="sim" if registro.contestada else "nao",
                obs=(registro.motivo or "").replace("|", "/")[:60] or "-",
            )
        )
    linhas.append("")
    for registro in registros:
        linhas.extend(_detalhe(registro))
    return "\n".join(linhas) + "\n"


def escrever_lote(registros: Iterable[RegistroDoCaso], destino: Path) -> Path:
    """Grava os casos e o relatorio do lote em um diretorio.

    Args:
        registros (Iterable[RegistroDoCaso]): Casos investigados.
        destino (Path): Diretorio do lote.

    Returns:
        Path: Arquivo `relatorio.md` do lote.
    """
    registros = list(registros)
    for registro in registros:
        escrever_caso(registro, destino / "casos")
    relatorio = destino / "relatorio.md"
    relatorio.write_text(resumo_markdown(registros), encoding="utf-8")
    return relatorio


def _contagem(registros: list[RegistroDoCaso]) -> dict[str, int]:
    """Conta quantos casos terminaram em cada desfecho."""
    contagem: dict[str, int] = {}
    for registro in registros:
        contagem[registro.desfecho] = contagem.get(registro.desfecho, 0) + 1
    return contagem


def _fatos_citados(registro: RegistroDoCaso) -> int:
    """Conta os fatos distintos citados pela hipotese."""
    if not registro.hipotese:
        return 0
    citados = {
        fact_id
        for campo in ("evidence_for", "evidence_against")
        for evidencia in registro.hipotese.get(campo, [])
        for fact_id in evidencia["fact_ids"]
    }
    return len(citados)


def _detalhe(registro: RegistroDoCaso) -> list[str]:
    """Monta a secao de um caso no relatorio."""
    linhas = [
        f"## {registro.case_id}",
        "",
        f"- Desfecho: **{ROTULOS.get(registro.desfecho, registro.desfecho)}**",
        f"- Recorte: `{registro.recorte.get('digest', '-')}` "
        f"em `{registro.recorte.get('sim_now', '-')}`",
        f"- Modelo: `{registro.modelo.get('model', '-')}`, "
        f"prompt `{registro.prompt_version}`",
    ]
    if registro.motivo:
        linhas.append(f"- Motivo: {registro.motivo}")
    if registro.hipotese:
        linhas += [
            "",
            f"**Causa candidata.** {registro.hipotese['statement']}",
            "",
            f"Evidencias a favor: {len(registro.hipotese['evidence_for'])}. "
            f"Contrarias: {len(registro.hipotese['evidence_against'])}. "
            f"Lacunas: {len(registro.hipotese['gaps'])}.",
        ]
    for aviso in registro.validacao.get("avisos", []):
        linhas.append(f"- Aviso do validador: {aviso}")
    if registro.lacunas and not registro.hipotese:
        linhas.append("")
        linhas.append("Lacunas declaradas:")
        linhas += [
            f"- {lacuna['missing']} ({lacuna['reason']})" for lacuna in registro.lacunas
        ]
    linhas.append("")
    linhas.append("Consultas:")
    if not registro.consultas:
        linhas.append("- nenhuma")
    for consulta in registro.consultas:
        detalhe = consulta.get("erro") or (
            consulta.get("vazia_porque") or f"{consulta['linhas']} linhas"
        )
        linhas.append(
            f"- `{consulta['ferramenta']}` {consulta['argumentos']} -> {detalhe}"
        )
    linhas.append("")
    return linhas
