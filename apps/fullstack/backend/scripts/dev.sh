#!/usr/bin/env sh
set -eu

backend_root="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
venv_path="$backend_root/.venv"

if [ ! -x "$venv_path/bin/python" ]; then
  python -m venv "$venv_path"
fi

"$venv_path/bin/python" -m pip install -e "$backend_root[dev]"
cd "$backend_root"
FLASK_DEBUG=1 exec "$venv_path/bin/python" run.py
