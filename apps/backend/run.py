"""Ponto unico de entrada da aplicacao de telemetria."""

import os
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = BACKEND_ROOT / "src"

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def load_local_environment(path: Path) -> None:
    """Carrega um .env simples sem exigir uma dependencia externa."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        os.environ.setdefault(key, value.strip().strip("'\""))


load_local_environment(BACKEND_ROOT / ".env")

from telemetry import create_app  # noqa: E402


def build_app(config: dict[str, Any] | None = None):
    """Cria a aplicacao e prepara a persistencia configurada."""
    return create_app(config)


def main() -> None:
    """Inicia todos os componentes necessarios para o backend local."""
    app = build_app()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes"}
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
