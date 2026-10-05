"""CLI do piloto: investigar um caso, rodar um lote ou checar o modelo.

A execucao e local e experimental. Nada aqui escreve no banco, publica em API
ou alimenta o frontend -- o resultado sai em arquivo, para leitura humana.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from argus_agente.agente import investigar
from argus_agente.casos import carregar_caso, descrever_caso
from argus_agente.limites import Orcamento
from argus_agente.lote import executar_lote
from argus_agente.modelo import (
    AberturaSSH,
    ClienteOllama,
    ModeloDeRoteiro,
    ModeloIndisponivel,
)
from argus_agente.registro import escrever_caso, resumo_markdown

log = logging.getLogger("argus_agente")


def construir_modelo(fonte: str, roteiro: Path | None = None, case_id: str = "") -> Any:
    """Cria o modelo a partir da origem pedida na linha de comando.

    Args:
        fonte (str): `ollama` ou `roteiro`.
        roteiro (Path | None): Arquivo JSON com os passos do dublê, ou um
            diretorio com um arquivo `<case_id>.json` por caso.
        case_id (str): Caso a investigar, usado para escolher o roteiro.

    Returns:
        Any: Objeto com `passo` e `identidade`.

    Raises:
        ValueError: Se faltar configuracao obrigatoria.
    """
    if fonte == "roteiro":
        if roteiro is None:
            raise ValueError("--roteiro e obrigatorio com --modelo roteiro")
        arquivo = roteiro / f"{case_id}.json" if roteiro.is_dir() else roteiro
        if not arquivo.exists():
            raise ValueError(f"sem roteiro para o caso {case_id} em {roteiro}")
        passos = json.loads(arquivo.read_text(encoding="utf-8"))
        return ModeloDeRoteiro(passos, nome=arquivo.stem)
    url = os.getenv("OLLAMA_URL", "")
    modelo = os.getenv("OLLAMA_MODEL", "")
    if not url or not modelo:
        raise ValueError("defina OLLAMA_URL e OLLAMA_MODEL no .env antes de rodar")
    tempo = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
    abertura = None
    if os.getenv("OLLAMA_SSH_HOST"):
        abertura = AberturaSSH(
            host=os.environ["OLLAMA_SSH_HOST"],
            port=int(os.getenv("OLLAMA_SSH_PORT", "22")),
            username=os.environ["OLLAMA_SSH_USER"],
            password=os.environ["OLLAMA_SSH_PASSWORD"],
            remote_host=os.getenv("OLLAMA_REMOTE_HOST", "127.0.0.1"),
            remote_port=int(os.getenv("OLLAMA_REMOTE_PORT", "11434")),
        )
    extras: dict[str, Any] = {"opener": abertura} if abertura else {}
    return ClienteOllama(url, modelo, timeout_seconds=tempo, **extras)


def _orcamento(args: argparse.Namespace) -> Orcamento:
    """Monta o orcamento com os ajustes passados na linha de comando."""
    padrao = Orcamento()
    return Orcamento(
        max_chamadas=args.max_chamadas or padrao.max_chamadas,
        max_linhas_por_resposta=args.max_linhas or padrao.max_linhas_por_resposta,
        max_segundos=args.max_segundos or padrao.max_segundos,
    )


def _investigar(args: argparse.Namespace) -> int:
    """Investiga um caso e grava o registro."""
    caso, ferramentas = carregar_caso(args.caso)
    log.info("caso carregado: %s", descrever_caso(caso))
    registro = investigar(
        caso,
        ferramentas,
        construir_modelo(args.modelo, args.roteiro),
        orcamento=_orcamento(args),
    )
    arquivo = escrever_caso(registro, args.saida)
    print(resumo_markdown([registro]))
    print(f"registro completo em {arquivo}")
    return 0 if registro.desfecho in ("hipotese", "evidencia_insuficiente") else 1


def _lote(args: argparse.Namespace) -> int:
    """Roda um lote de casos e grava o relatorio."""
    caminhos = sorted(args.casos.glob("*.json")) if args.casos.is_dir() else [args.casos]
    if not caminhos:
        print(f"nenhum caso em {args.casos}", file=sys.stderr)
        return 2
    registros = executar_lote(
        caminhos,
        lambda case_id: construir_modelo(args.modelo, args.roteiro, case_id),
        destino=args.saida,
        orcamento=_orcamento(args),
    )
    print(f"{len(registros)} caso(s) em {args.saida / 'relatorio.md'}")
    uteis = sum(
        1
        for registro in registros
        if registro.desfecho in ("hipotese", "evidencia_insuficiente")
    )
    return 0 if uteis == len(registros) else 1


def _checar_modelo(args: argparse.Namespace) -> int:
    """Faz uma chamada curta so para confirmar que o modelo responde."""
    modelo = construir_modelo(args.modelo, args.roteiro)
    mensagens = [
        {"role": "system", "content": "Responda no formato exigido."},
        {
            "role": "user",
            "content": 'Responda {"action":"desistir","rationale":"teste de conexao",'
            '"gaps":[{"missing":"nada","reason":"sem_dado"}]}',
        },
    ]
    resposta = modelo.passo(mensagens)
    print(json.dumps({"identidade": modelo.identidade, "resposta": resposta}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da CLI.

    Args:
        argv (list[str] | None): Argumentos, ou `None` para usar `sys.argv`.

    Returns:
        int: Codigo de saida do processo.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="agentectl", description=__doc__)
    parser.add_argument("--modelo", default="ollama", choices=("ollama", "roteiro"))
    parser.add_argument(
        "--roteiro", type=Path, help="passos do dublê, com --modelo roteiro"
    )
    parser.add_argument("--max-chamadas", type=int, default=0)
    parser.add_argument("--max-linhas", type=int, default=0)
    parser.add_argument("--max-segundos", type=float, default=0.0)
    sub = parser.add_subparsers(dest="comando", required=True)

    um = sub.add_parser("investigar", help="investiga um caso")
    um.add_argument("caso", type=Path)
    um.add_argument("--saida", type=Path, default=Path("saidas"))
    um.set_defaults(funcao=_investigar)

    varios = sub.add_parser("lote", help="investiga um diretorio de casos")
    varios.add_argument("casos", type=Path)
    varios.add_argument("--saida", type=Path, default=Path("saidas/lote"))
    varios.set_defaults(funcao=_lote)

    ping = sub.add_parser("checar-modelo", help="confirma que o modelo responde")
    ping.set_defaults(funcao=_checar_modelo)

    args = parser.parse_args(argv)
    try:
        return int(args.funcao(args))
    except (ValueError, OSError, ModeloIndisponivel) as erro:
        # Modelo fora do ar e um resultado do piloto, nao um defeito da CLI:
        # sai com mensagem curta, para que o lote possa ser repetido depois.
        print(f"erro: {erro}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
