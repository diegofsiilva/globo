#!/usr/bin/env bash
# Empacota somente o roteador; boto3 faz parte do runtime Python da Lambda.
set -euo pipefail

EDGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT="${1:-$EDGE_ROOT/dist/argus-edge.zip}"
mkdir -p "$(dirname "$OUTPUT")"
if [[ "${OSTYPE:-}" == msys* || "${OSTYPE:-}" == cygwin* ]]; then
  PYTHON=(py -3)
else
  PYTHON=(python3)
fi
"${PYTHON[@]}" - "$EDGE_ROOT/handler.py" "$OUTPUT" <<'PY'
import sys
import zipfile

origem, destino = sys.argv[1:]
with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as pacote:
    item = zipfile.ZipInfo("handler.py", date_time=(2000, 1, 1, 0, 0, 0))
    item.compress_type = zipfile.ZIP_DEFLATED
    with open(origem, "rb") as codigo:
        pacote.writestr(item, codigo.read())
PY
echo "pacote: $OUTPUT"
