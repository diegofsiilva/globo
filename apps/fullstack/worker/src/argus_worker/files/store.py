"""Fila PostgreSQL com lease, fencing e conclusão na transação dos eventos."""

import hashlib
import json
import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..repository import EventRepository

PUBLIC = """id, filename, status, total, inserted, duplicates, rejected, errors,
            attempts, created_at, updated_at"""


def public_job(row):
    """Serializa apenas metadados operacionais, sem token ou conteúdo do arquivo."""
    return {
        k: (str(v) if k == "id" else v.isoformat() if k.endswith("_at") else v)
        for k, v in row.items()
    }


class FileStore:
    """Coordena arquivos sem criar dependência de S3/SQS na API de leitura."""

    def __init__(self, db):
        """Recebe o pool compartilhado do serviço de ingestão."""
        self.db = db

    def enqueue(self, owner, filename, fmt, content, mapping, delimiter):
        """Deduplica conteúdo+mapeamento e limita a fila de cada credencial."""
        spec = json.dumps([fmt, mapping, delimiter], sort_keys=True).encode()
        fingerprint = hashlib.sha256(content + spec).hexdigest()
        with self.db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (owner,))
            cur.execute(
                f"SELECT {PUBLIC}, content IS NULL AS expired FROM ingest.file_job "
                "WHERE owner_hash=%s AND fingerprint=%s",
                (owner, fingerprint),
            )
            previous = cur.fetchone()
            if previous:
                expired = previous.pop("expired")
                if previous["status"] != "falhou" or not expired:
                    return public_job(previous)
            cur.execute(
                "UPDATE ingest.file_job SET content=NULL "
                "WHERE owner_hash=%s AND status='falhou' "
                "AND updated_at < clock_timestamp()-interval '7 days'",
                (owner,),
            )
            cur.execute(
                "SELECT count(*) AS n, coalesce(sum(octet_length(content)),0) AS b "
                "FROM ingest.file_job WHERE owner_hash=%s AND content IS NOT NULL",
                (owner,),
            )
            limits = cur.fetchone()
            if limits["n"] >= 10 or limits["b"] + len(content) > 100 * 1024**2:
                raise ValueError("Fila cheia: até 10 arquivos e 100 MiB por credencial.")
            if previous:
                cur.execute(
                    "UPDATE ingest.file_job SET content=%s, status='na_fila', "
                    "attempts=0, errors='[]', updated_at=clock_timestamp() "
                    f"WHERE id=%s RETURNING {PUBLIC}",
                    (content, previous["id"]),
                )
                return public_job(cur.fetchone())
            cur.execute(
                f"INSERT INTO ingest.file_job "
                "(id,owner_hash,fingerprint,filename,format,content,mapping,delimiter) "
                f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {PUBLIC}",
                (
                    uuid.uuid4(),
                    owner,
                    fingerprint,
                    filename,
                    fmt,
                    content,
                    Jsonb(mapping),
                    delimiter,
                ),
            )
            return public_job(cur.fetchone())

    def get(self, owner, job_id):
        """Busca resultado apenas para a credencial que criou o arquivo."""
        row = self.db.fetch_one(
            f"SELECT {PUBLIC} FROM ingest.file_job WHERE owner_hash=%s AND id=%s",
            (owner, job_id),
        )
        return public_job(row) if row else None

    def retry(self, owner, job_id):
        """Reenfileira falha transitória, preservando identidade e conteúdo."""
        with self.db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"UPDATE ingest.file_job SET status='na_fila', attempts=0, "
                "lease=NULL, errors='[]', updated_at=clock_timestamp() "
                "WHERE owner_hash=%s AND id=%s AND status='falhou' "
                f"AND content IS NOT NULL RETURNING {PUBLIC}",
                (owner, job_id),
            )
            row = cur.fetchone()
            return public_job(row) if row else None

    def claim(self):
        """Retoma leases expirados; um token novo bloqueia o trabalhador antigo."""
        with self.db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "UPDATE ingest.file_job SET status='falhou', lease=NULL, "
                "errors=%s, updated_at=clock_timestamp() "
                "WHERE status='processando' AND attempts>=3 "
                "AND updated_at < clock_timestamp()-interval '5 minutes'",
                (
                    Jsonb(
                        [
                            {
                                "campo": "arquivo",
                                "mensagem": "Três tentativas interrompidas.",
                            }
                        ]
                    ),
                ),
            )
            cur.execute(
                "SELECT id FROM ingest.file_job WHERE status='na_fila' OR "
                "(status='processando' AND attempts<3 AND updated_at < "
                "clock_timestamp()-interval '5 minutes') "
                "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
            )
            if not (row := cur.fetchone()):
                return None
            cur.execute(
                "UPDATE ingest.file_job SET status='processando', lease=%s, "
                "attempts=attempts+1, updated_at=clock_timestamp() "
                "WHERE id=%s RETURNING *",
                (uuid.uuid4(), row["id"]),
            )
            return cur.fetchone()

    def finish(self, job, rows, total, rejected, errors):
        """Commita dados e contadores juntos; rollback não publica falso sucesso."""
        with self.db.connection() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT lease FROM ingest.file_job WHERE id=%s FOR UPDATE", (job["id"],)
            )
            if cur.fetchone()[0] != job["lease"]:
                return False
            repository = EventRepository(self.db)
            inserted = sum(
                repository.put_many(rows[i : i + 500], connection=conn)
                for i in range(0, len(rows), 500)
            )
            status = (
                "rejeitado"
                if not rows
                else ("concluido_com_rejeicoes" if rejected else "concluido")
            )
            cur.execute(
                "UPDATE ingest.file_job SET status=%s, total=%s, inserted=%s, "
                "duplicates=%s, rejected=%s, errors=%s, content=NULL, "
                "lease=NULL, updated_at=clock_timestamp() WHERE id=%s",
                (
                    status,
                    total,
                    inserted,
                    len(rows) - inserted,
                    rejected,
                    Jsonb(errors),
                    job["id"],
                ),
            )
            return True

    def fail(self, job, permanent):
        """Registra falha sanitizada somente enquanto o lease ainda é nosso."""
        with self.db.connection() as conn, conn.cursor() as cur:
            status = "rejeitado" if permanent else "falhou"
            message = (
                (
                    "Arquivo inválido ou excede os limites; confira formato, "
                    "cabeçalho e registros."
                )
                if permanent
                else ("Falha temporária no processamento. Tente novamente.")
            )
            cur.execute(
                "UPDATE ingest.file_job SET status=%s, errors=%s, lease=NULL, "
                "content=CASE WHEN %s THEN NULL ELSE content END, "
                "updated_at=clock_timestamp() WHERE id=%s AND lease=%s",
                (
                    status,
                    Jsonb([{"campo": "arquivo", "mensagem": message}]),
                    permanent,
                    job["id"],
                    job["lease"],
                ),
            )
