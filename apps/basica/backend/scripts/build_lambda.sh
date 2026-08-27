#!/usr/bin/env bash
# Monta o zip de deploy da API de leitura.
#
#   ./scripts/build_lambda.sh [saida.zip]
#
# Duas mudancas em relacao a v2:
#
#   boto3 SAIU. A API nao fala mais com servico nenhum da AWS -- ela le do
#   PostgreSQL, e a autorizacao vem de GRANT, nao de IAM. Sao ~15 MB a menos.
#
#   psycopg[binary] ENTROU, e ele NAO e Python puro. O wheel traz a libpq
#   compilada, entao precisa ser o wheel da plataforma da Lambda, e nao o da
#   maquina que faz o build. Numa maquina Apple Silicon, um `pip install`
#   comum baixaria o wheel de macOS e o pacote subiria quebrado -- com o erro
#   aparecendo so na primeira invocacao, como "No module named psycopg_binary".
#   Por isso os --platform/--only-binary abaixo.
set -euo pipefail

BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="${1:-$BACKEND_ROOT/dist/telemetry-read-api.zip}"

# Precisa casar com `architectures` da aws_lambda_function em infra/api_read.tf.
LAMBDA_PLATFORM="${LAMBDA_PLATFORM:-manylinux2014_aarch64}"
LAMBDA_PYTHON="${LAMBDA_PYTHON:-3.12}"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "[1/3] instalando dependencias de runtime ($LAMBDA_PLATFORM, py$LAMBDA_PYTHON)"
python3 -m pip install \
  --quiet --disable-pip-version-check \
  --target "$BUILD_DIR" \
  --platform "$LAMBDA_PLATFORM" \
  --python-version "$LAMBDA_PYTHON" \
  --implementation cp \
  --only-binary=:all: \
  "Flask>=3.1,<4" "apig-wsgi>=2.18,<3" "psycopg[binary,pool]>=3.2,<4"

echo "[2/3] copiando a aplicacao"
# O pacote vai para a raiz do zip, que a Lambda ja coloca no sys.path. O
# sys.path.insert do handler aponta para um ./src que nao existe aqui, e o
# Python ignora caminho inexistente -- e o mesmo arquivo serve para rodar
# local (onde ./src existe) e na Lambda.
cp -R "$BACKEND_ROOT/src/telemetry" "$BUILD_DIR/telemetry"
cp "$BACKEND_ROOT/lambda_handler.py" "$BUILD_DIR/"

find "$BUILD_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "*.dist-info" -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "tests" -prune -exec rm -rf {} + 2>/dev/null || true

# Confere que o wheel binario do psycopg realmente entrou. Sem esta checagem, o
# erro so apareceria na primeira invocacao em producao.
if [ ! -d "$BUILD_DIR/psycopg_binary" ]; then
  echo "erro: psycopg_binary nao foi instalado para $LAMBDA_PLATFORM." >&2
  echo "      A Lambda subiria e falharia na primeira consulta." >&2
  exit 1
fi

echo "[3/3] compactando"
mkdir -p "$(dirname "$OUTPUT")"
rm -f "$OUTPUT"
(cd "$BUILD_DIR" && zip -qr "$OUTPUT" . -x '*.pyc')

echo
echo "pacote: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
