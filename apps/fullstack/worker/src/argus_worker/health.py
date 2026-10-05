"""Sonda Docker dos modos HTTP e consumidores da imagem compartilhada."""

import os
import time
from pathlib import Path
from urllib.request import urlopen


def main():
    """Inspeciona PID 1 para escolher HTTP ou heartbeat sem credenciais."""
    command = Path("/proc/1/cmdline").read_bytes()
    if b"argus_worker.files.api" in command:
        with urlopen(
            f"http://127.0.0.1:{os.getenv('PORT', '5002')}/ingestion/live", timeout=3
        ) as response:
            return 0 if response.status == 200 else 1
    path = Path(os.getenv("HEARTBEAT_PATH", "/tmp/argus-heartbeat"))
    limit = 300 if b"file-worker" in command else 120
    return 0 if path.exists() and time.time() - path.stat().st_mtime < limit else 1


if __name__ == "__main__":
    raise SystemExit(main())
