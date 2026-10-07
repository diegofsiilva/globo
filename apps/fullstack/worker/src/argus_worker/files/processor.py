"""Consumidor da fila durável com recuperação de jobs interrompidos."""

import csv
import logging

from argus_common import Database, Heartbeat, ShutdownSignal

from .parser import parse_file
from .store import FileStore

log = logging.getLogger(__name__)


def process_one(store):
    """Executa um job; commit dos eventos e do resultado é atômico."""
    job = store.claim()
    if job is None:
        return False
    try:
        rows, total, rejected, errors = parse_file(
            bytes(job["content"]),
            job["format"],
            job["mapping"],
            job["delimiter"],
            job["available_at"],
        )
        store.finish(job, rows, total, rejected, errors)
    except (ValueError, TypeError, UnicodeError, OverflowError, csv.Error):
        store.fail(job, permanent=True)
    except Exception:
        log.exception("falha ao processar job de arquivo %s", job["id"])
        store.fail(job, permanent=False)
    return True


def main():
    """Processa jobs até SIGTERM, sem depender de fila ou credencial AWS."""
    db = Database.from_env(application_name="argus-file-worker")
    shutdown = ShutdownSignal()
    heartbeat = Heartbeat("/tmp/argus-heartbeat")
    try:
        while shutdown.running:
            heartbeat.touch()
            if not process_one(FileStore(db)):
                shutdown.sleep(1)
    finally:
        db.close()
