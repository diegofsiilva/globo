"""Avalia o modelo real contra os casos sinteticos com trajetoria-ouro.

Laco de avaliacao offline: nao toca banco, AWS nem o motor. Cada caso sintetico
tem um roteiro fixo que descreve a investigacao esperada. O script roda o caso
duas vezes -- uma com o roteiro, para fixar o desfecho esperado, e outra com o
modelo configurado em OLLAMA_* -- e mede onde o modelo diverge do roteiro.

E barato de repetir, entao serve para comparar modelos e versoes de prompt sem
precisar do checkpoint reconstruido do PostgreSQL. As divergencias saem no
codigo de saida: o processo termina em 1 se algum caso nao chegou ao desfecho
esperado. Coincidencia de desfecho nao valida a causa nem as evidencias.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "apps/fullstack/agente/src"))

from argus_agente.agente import investigar  # noqa: E402
from argus_agente.agentectl import construir_modelo  # noqa: E402
from argus_agente.casos import carregar_caso  # noqa: E402
from argus_agente.contrato import RegistroDoCaso  # noqa: E402
from argus_agente.modelo import ModeloDeRoteiro, ModeloIndisponivel  # noqa: E402

PASTA = ROOT / "apps/fullstack/agente/fixtures"
ROTEIROS = PASTA / "roteiros"


def _investigar_caso(caminho: Path, fabrica) -> RegistroDoCaso:
    """Investiga um caso, convertendo falha do modelo em registro de erro.

    Args:
        caminho (Path): Arquivo do caso sintetico.
        fabrica: Funcao que recebe o case_id e devolve o modelo a usar.

    Returns:
        RegistroDoCaso: Resultado da investigacao, util ou nao.
    """
    caso, leitor = carregar_caso(caminho)
    try:
        return investigar(caso, leitor, fabrica(caso.case_id))
    except (ModeloIndisponivel, OSError, ValueError) as erro:
        # Modelo fora do ar e um resultado do ensaio, nao um defeito do script.
        from argus_agente.contrato import DESFECHO_ERRO

        return RegistroDoCaso(
            case_id=caso.case_id,
            desfecho=DESFECHO_ERRO,
            motivo=f"{type(erro).__name__}: {erro}"[:200],
        )


def _modelo_de_roteiro(case_id: str) -> ModeloDeRoteiro:
    """Cria o duble de roteiro, a trajetoria-ouro, para um caso.

    Args:
        case_id (str): Identificador do caso, que nomeia o arquivo de roteiro.

    Returns:
        ModeloDeRoteiro: Duble que reproduz os passos esperados sem rede.
    """
    passos = json.loads((ROTEIROS / f"{case_id}.json").read_text(encoding="utf-8"))
    return ModeloDeRoteiro(passos, nome=case_id)


def _chamadas_invalidas(registro: RegistroDoCaso) -> int:
    """Conta as chamadas de ferramenta recusadas pelo leitor.

    E a falha central da run real: argumento que a ferramenta nao aceita gasta
    uma chamada do teto sem trazer fato. O passo invalido de formato (JSON
    malformado) e contado a parte, em `consumo.passos_invalidos`.

    Args:
        registro (RegistroDoCaso): Registro da investigacao.

    Returns:
        int: Numero de consultas com erro de ferramenta.
    """
    return sum(1 for consulta in registro.consultas if consulta.get("erro"))


def _erros_de_ferramenta(registro: RegistroDoCaso) -> list[dict]:
    """Lista cada chamada recusada com a ferramenta, os argumentos e o erro.

    E o diagnostico que diz QUAL argumento o modelo insiste em mandar errado,
    para que a correcao do prompt mire no erro real e nao em suposicao.

    Args:
        registro (RegistroDoCaso): Registro da investigacao.

    Returns:
        list[dict]: Uma entrada por consulta com erro.
    """
    return [
        {
            "ferramenta": consulta.get("ferramenta"),
            "argumentos": consulta.get("argumentos"),
            "erro": consulta.get("erro"),
        }
        for consulta in registro.consultas
        if consulta.get("erro")
    ]


def _linha(case_id: str, esperado: RegistroDoCaso, obtido: RegistroDoCaso) -> dict:
    """Resume a comparacao de um caso entre o roteiro e o modelo.

    Args:
        case_id (str): Caso avaliado.
        esperado (RegistroDoCaso): Resultado do roteiro, a trajetoria-ouro.
        obtido (RegistroDoCaso): Resultado do modelo configurado.

    Returns:
        dict: Campos comparaveis, com a coincidencia de desfecho.
    """
    consumo = obtido.metricas.get("consumo", {})
    return {
        "case_id": case_id,
        "desfecho_esperado": esperado.desfecho,
        "desfecho_obtido": obtido.desfecho,
        "desfecho_correto": obtido.desfecho == esperado.desfecho,
        "chamadas": consumo.get("chamadas", 0),
        "chamadas_invalidas": _chamadas_invalidas(obtido),
        "passos_invalidos": consumo.get("passos_invalidos", 0),
        "fatos_vistos": obtido.metricas.get("fatos_vistos", 0),
        "segundos": consumo.get("segundos", 0),
        "motivo": obtido.motivo,
        "erros_de_ferramenta": _erros_de_ferramenta(obtido),
        "respostas_ilegiveis": obtido.metricas.get("respostas_ilegiveis", []),
    }


def _imprimir(linhas: list[dict], identidade: dict) -> None:
    """Imprime a tabela de avaliacao em Markdown no stdout.

    Args:
        linhas (list[dict]): Resumo por caso.
        identidade (dict): Identidade do modelo avaliado.
    """
    print(f"\nModelo avaliado: {identidade}\n")
    print(
        "| Caso | Esperado | Obtido | Desfecho correto | Chamadas | Invalidas | Fatos |"
    )
    print("|---|---|---|---|---|---|---|")
    for linha in linhas:
        print(
            f"| {linha['case_id']} | {linha['desfecho_esperado']} "
            f"| {linha['desfecho_obtido']} "
            f"| {'sim' if linha['desfecho_correto'] else 'NAO'} "
            f"| {linha['chamadas']} | {linha['chamadas_invalidas']} "
            f"| {linha['fatos_vistos']} |"
        )
    acertos = sum(1 for linha in linhas if linha["desfecho_correto"])
    invalidas = sum(linha["chamadas_invalidas"] for linha in linhas)
    print(
        f"\n{acertos}/{len(linhas)} casos no desfecho esperado; "
        f"{invalidas} chamada(s) invalida(s) no total."
    )


def main(argv: list[str] | None = None) -> int:
    """Roda a avaliacao e grava o resumo estruturado.

    Args:
        argv (list[str] | None): Argumentos, ou `None` para usar `sys.argv`.

    Returns:
        int: 0 se todos os casos chegaram ao desfecho esperado, 1 caso contrario.
    """
    parser = argparse.ArgumentParser(prog="avaliar_modelo", description=__doc__)
    parser.add_argument(
        "--modelo",
        default="ollama",
        choices=("ollama", "roteiro"),
        help="modelo avaliado; `roteiro` e um ensaio seco que deve acertar tudo",
    )
    parser.add_argument(
        "--modelo-id",
        default="",
        help="sobrescreve OLLAMA_MODEL so nesta execucao, para comparar modelos",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=ROOT / "apps/fullstack/agente/saidas/eval",
        help="diretorio base do resumo (gitignored); cada modelo ganha um subdir",
    )
    args = parser.parse_args(argv)

    caminhos = sorted(PASTA.glob("caso-*.json"))
    if not caminhos:
        print(f"nenhum caso em {PASTA}", file=sys.stderr)
        return 2

    if args.modelo == "roteiro":
        fabrica = _modelo_de_roteiro
        rotulo = "roteiro"
    else:
        # --modelo-id vence o .env so nesta execucao, para comparar candidatos sem
        # editar o .env a cada rodada.
        if args.modelo_id:
            os.environ["OLLAMA_MODEL"] = args.modelo_id
        rotulo = os.getenv("OLLAMA_MODEL", "ollama")
        fabrica = lambda case_id: construir_modelo("ollama", case_id=case_id)  # noqa: E731

    # Um subdir por modelo preserva o baseline ao testar um candidato novo.
    saida = args.saida / rotulo.replace(":", "-").replace("/", "-")
    casos_dir = saida / "casos"
    casos_dir.mkdir(parents=True, exist_ok=True)

    linhas: list[dict] = []
    identidade: dict = {}
    for caminho in caminhos:
        esperado = _investigar_caso(caminho, _modelo_de_roteiro)
        obtido = _investigar_caso(caminho, fabrica)
        identidade = obtido.modelo or identidade
        linhas.append(_linha(caminho.stem, esperado, obtido))
        # A trajetoria completa (passos brutos, consultas e hipotese) e o que
        # explica por que o caso divergiu; o resumo so conta quanto.
        (casos_dir / f"{caminho.stem}.json").write_text(
            json.dumps(obtido.para_json(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    _imprimir(linhas, identidade)

    (saida / "resultado.json").write_text(
        json.dumps(
            {
                "tipo": "eval_offline_modelo_vs_roteiro",
                "modelo": identidade,
                "nota": (
                    "roteiro = trajetoria-ouro; compara-se somente o desfecho "
                    "nos mesmos casos sinteticos, sem validar causa ou evidencias"
                ),
                "casos": linhas,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nresumo em {saida / 'resultado.json'}")

    return 0 if all(linha["desfecho_correto"] for linha in linhas) else 1


if __name__ == "__main__":
    raise SystemExit(main())
