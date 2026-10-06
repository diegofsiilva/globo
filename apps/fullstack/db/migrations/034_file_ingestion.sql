-- Fila durável de arquivos; acesso exclusivo do serviço de ingestão.
CREATE SCHEMA IF NOT EXISTS ingest;
CREATE TABLE ingest.file_job (
    id uuid PRIMARY KEY,
    owner_hash text NOT NULL,
    fingerprint text NOT NULL,
    filename text NOT NULL,
    format text NOT NULL CHECK (format IN ('csv', 'parquet')),
    mapping jsonb NOT NULL,
    delimiter text,
    content bytea,
    status text NOT NULL DEFAULT 'na_fila'
        CHECK (status IN ('na_fila', 'processando', 'concluido',
                         'concluido_com_rejeicoes', 'rejeitado', 'falhou')),
    lease uuid,
    attempts integer NOT NULL DEFAULT 0,
    total integer NOT NULL DEFAULT 0,
    inserted integer NOT NULL DEFAULT 0,
    duplicates integer NOT NULL DEFAULT 0,
    rejected integer NOT NULL DEFAULT 0,
    errors jsonb NOT NULL DEFAULT '[]'::jsonb,
    available_at timestamptz NOT NULL DEFAULT sim.now(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (owner_hash, fingerprint)
);
CREATE INDEX file_job_queue ON ingest.file_job (status, updated_at);
-- Não conceder acesso a argus_reader nem expor o arquivo nas APIs de leitura.
