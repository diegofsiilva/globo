#!/usr/bin/env bash
# Monta o zip de deploy do Lambda authorizer.
#
#   ./scripts/build_lambda.sh [saida.zip]
#
# Bem mais simples que o da API de leitura: nao ha dependencia para instalar.
# `boto3` vem no runtime da Lambda e e a unica biblioteca externa que o handler
# usa, entao o pacote e o proprio arquivo. Sem wheel binario, o zip e igual em
# qualquer maquina -- e o `source_code_hash` do Terraform so muda quando o
# codigo muda de verdade, e nao a cada build.
set -euo pipefail

AUTHORIZER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="${1:-$AUTHORIZER_ROOT/dist/argus-authorizer.zip}"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

cp "$AUTHORIZER_ROOT/handler.py" "$BUILD_DIR/"

mkdir -p "$(dirname "$OUTPUT")"
rm -f "$OUTPUT"
# O zip precisa ser REPRODUTIVEL, e nao apenas correto.
#
# `source_code_hash` no Terraform e o sha256 do arquivo. Um zip que carrega a
# data de modificacao real muda de bytes a cada build, e entao todo
# `terraform plan` proporia atualizar a Lambda -- mesmo sem uma linha de codigo
# diferente. O ruido esconde a mudanca de verdade no meio do plano.
#
# `touch` fixa o mtime numa data constante e `-X` descarta os atributos extras
# do sistema de arquivos (dono, grupo, timestamps de alta resolucao).
find "$BUILD_DIR" -exec touch -t 200001010000 {} +
(cd "$BUILD_DIR" && zip -qrX "$OUTPUT" . -x '*.pyc')

echo "pacote: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
