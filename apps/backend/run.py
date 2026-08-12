"""Ponto unico de entrada da aplicacao de telemetria."""

import os
import subprocess
import sys
from importlib.util import find_spec
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = BACKEND_ROOT / "src"
RUNTIME_REQUIREMENTS = (
    "Flask>=3.1,<4",
    "boto3>=1.35,<2",
)

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def load_local_environment(path: Path) -> None:
    """Carrega variáveis de um arquivo .env simples para os.environ sem dependências externas.

    Args:
        path (Path): Caminho para o arquivo .env a ser lido.
    """
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


def ensure_runtime_dependencies() -> None:
    """Garante que as dependências necessárias estejam instaladas em um ambiente Python limpo.

    Raises:
        RuntimeError: Se a instalação automática via pip falhar.
    """
    required_modules = ("flask", "boto3")
    missing = [module for module in required_modules if find_spec(module) is None]
    if not missing:
        return

    print(
        f"Preparando o backend pela primeira vez (dependencias ausentes: {', '.join(missing)})...",
        flush=True,
    )
    try:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                *RUNTIME_REQUIREMENTS,
            ]
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            "Nao foi possivel instalar as dependencias automaticamente. "
            "Verifique sua conexao e execute o arquivo novamente."
        ) from error


ensure_runtime_dependencies()

from telemetry import create_app  # noqa: E402


def build_app(config: dict[str, Any] | None = None):
    """Cria a aplicação Flask e prepara a persistência configurada.

    Args:
        config (dict[str, Any] | None): Dicionário opcional com configurações da aplicação.

    Returns:
        Flask: Instância da aplicação WSGI/Flask configurada.
    """
    return create_app(config)


def main() -> None:
    """Inicia todos os componentes necessários para o servidor backend local."""
    app = build_app()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes"}
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
