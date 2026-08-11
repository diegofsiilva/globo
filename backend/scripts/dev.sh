#!/usr/bin/env sh
set -eu

backend_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
venv_path="$backend_root/.venv"

if [ ! -x "$venv_path/bin/python" ]; then
  python -m venv "$venv_path"
fi

"$venv_path/bin/python" -m pip install -e "$backend_root[dev]"
cd "$backend_root"
exec "$venv_path/bin/python" -m flask --app telemetry:create_app run --debug --host 0.0.0.0 --port 5000
