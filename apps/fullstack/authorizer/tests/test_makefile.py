"""Testes do fluxo operacional de rotacao dos tokens."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

FULLSTACK = Path(__file__).resolve().parents[2]


def _comando_falso(diretorio: Path, nome: str, conteudo: str) -> None:
    caminho = diretorio / nome
    caminho.write_text(conteudo, encoding="utf-8")
    caminho.chmod(0o755)


def test_auth_rotate_nao_imprime_tokens_quando_publicacao_falha(tmp_path):
    """Uma falha intermediaria precisa vencer os `echo` finais da receita."""
    binarios = tmp_path / "bin"
    binarios.mkdir()

    _comando_falso(
        binarios,
        "terraform",
        """#!/bin/sh
case "$3" in
  auth_tokens_secret) echo "argus/auth-tokens" ;;
  ingest_token_secret) echo "argus/ingest-token" ;;
  read_api_id) echo "read-api" ;;
  ingest_api_id) echo "ingest-api" ;;
  *) exit 2 ;;
esac
""",
    )
    _comando_falso(
        binarios,
        "aws",
        """#!/bin/sh
if [ "$1" = "secretsmanager" ] && [ "$2" = "describe-secret" ]; then
  exit 0
fi
if [ "$1" = "secretsmanager" ] && [ "$2" = "put-secret-value" ]; then
  echo "falha simulada no put-secret-value" >&2
  exit 42
fi
exit 2
""",
    )

    ambiente = os.environ.copy()
    ambiente.update(
        {
            "AWS_PROFILE": "g4",
            "AWS_REGION": "us-east-1",
            "PATH": f"{binarios}{os.pathsep}{ambiente['PATH']}",
        }
    )

    resultado = subprocess.run(
        ["make", "auth-rotate"],
        cwd=FULLSTACK,
        env=ambiente,
        input="rotacionar\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode != 0
    assert "falha simulada no put-secret-value" in resultado.stderr
    assert "Token de LEITURA" not in resultado.stdout
    assert "Token de INGESTAO" not in resultado.stdout
