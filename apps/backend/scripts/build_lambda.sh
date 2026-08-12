#!/usr/bin/env bash
# Monta o zip de deploy da API de leitura.
#
#   ./scripts/build_lambda.sh [saida.zip]
#
# O boto3 nao entra no pacote: o runtime da Lambda ja o traz. Incluir uma copia
# so aumentaria o zip e ainda correria o risco de divergir da versao que a AWS
# usa por baixo. Sobram Flask e apig-wsgi, ambos Python puro -- por isso o
# pacote funciona igual em ARM64 e x86, sem precisar de wheel por plataforma.
set -euo pipefail

BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="${1:-$BACKEND_ROOT/dist/telemetry-read-api.zip}"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "[1/3] instalando dependencias de runtime"
python3 -m pip install \
  --quiet --disable-pip-version-check \
  --target "$BUILD_DIR" \
  "Flask>=3.1,<4" "apig-wsgi>=2.18,<3"

echo "[2/3] copiando a aplicacao"
# O pacote vai para a raiz do zip, que a Lambda ja coloca no sys.path. O
# sys.path.insert do handler aponta para um ./src que nao existe aqui, e o
# Python ignora caminho inexistente -- e o mesmo arquivo serve para rodar
# local (onde ./src existe) e na Lambda.
cp -R "$BACKEND_ROOT/src/telemetry" "$BUILD_DIR/telemetry"
cp "$BACKEND_ROOT/lambda_handler.py" "$BUILD_DIR/"

find "$BUILD_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "*.dist-info" -prune -exec rm -rf {} + 2>/dev/null || true

echo "[3/3] compactando"
mkdir -p "$(dirname "$OUTPUT")"
rm -f "$OUTPUT"
(cd "$BUILD_DIR" && zip -qr "$OUTPUT" . -x '*.pyc')

echo
echo "pacote: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
