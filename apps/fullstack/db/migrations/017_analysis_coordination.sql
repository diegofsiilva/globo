-- 017_analysis_coordination.sql
--
-- Coordena a analise de checkpoints Gold entre replicas do servico processing.
-- O advisory lock protege apenas a escolha do trabalho; lease e fencing
-- persistentes impedem que uma tentativa antiga publique resultados depois de
-- perder a posse.

CREATE SEQUENCE detect.fencing_token_seq
  AS bigint
  INCREMENT BY 1
  MINVALUE 1
  NO MAXVALUE
  START WITH 1
  CACHE 1
  NO CYCLE;

COMMENT ON SEQUENCE detect.fencing_token_seq IS
  'Token monotonicamente crescente de posse da analise. Lacunas por rollback '
  'sao esperadas; valores nunca devem ser reiniciados nem reutilizados';

ALTER TABLE detect.run
  ADD COLUMN checkpoint_id    bigint
    REFERENCES etl.gold_checkpoint (checkpoint_id),
  ADD COLUMN manifest_hash    text,
  ADD COLUMN sim_now          timestamptz,
  ADD COLUMN status           text,
  ADD COLUMN claimed_by       text,
  ADD COLUMN lease_expires_at timestamptz,
  ADD COLUMN heartbeat_at     timestamptz,
  ADD COLUMN fencing_token    bigint,
  ADD COLUMN attempt          integer,
  ADD COLUMN retry_of         bigint
    REFERENCES detect.run (run_id) ON DELETE SET NULL,
  ADD COLUMN input_lsn        bigint,
  ADD COLUMN input_digest     text,
  ADD COLUMN error_message    text;

-- Compatibilidade com eventuais runs embrionarios criados antes da
-- coordenacao. Eles continuam legiveis, mas nao recebem checkpoint nem token.
UPDATE detect.run
   SET status = CASE
     WHEN finished_at IS NOT NULL THEN 'completed'
     WHEN started_at IS NOT NULL THEN 'running'
     ELSE 'claimed'
   END;

ALTER TABLE detect.run
  ALTER COLUMN status SET DEFAULT 'claimed',
  ALTER COLUMN status SET NOT NULL,
  ADD CONSTRAINT detect_run_status_valido CHECK (
    status IN ('claimed', 'running', 'committing', 'completed', 'failed', 'abandoned')
  ),
  ADD CONSTRAINT detect_run_manifest_valido CHECK (
    manifest_hash IS NULL OR btrim(manifest_hash) <> ''
  ),
  ADD CONSTRAINT detect_run_owner_valido CHECK (
    claimed_by IS NULL OR btrim(claimed_by) <> ''
  ),
  ADD CONSTRAINT detect_run_attempt_valido CHECK (attempt IS NULL OR attempt > 0),
  ADD CONSTRAINT detect_run_input_lsn_valido CHECK (input_lsn IS NULL OR input_lsn >= 0),
  ADD CONSTRAINT detect_run_fencing_valido CHECK (
    fencing_token IS NULL OR fencing_token > 0
  ),
  ADD CONSTRAINT detect_run_coordenado_completo CHECK (
    checkpoint_id IS NULL OR (
      manifest_hash IS NOT NULL
      AND sim_now IS NOT NULL
      AND claimed_by IS NOT NULL
      AND lease_expires_at IS NOT NULL
      AND heartbeat_at IS NOT NULL
      AND fencing_token IS NOT NULL
      AND attempt IS NOT NULL
      AND input_lsn IS NOT NULL
    )
  ),
  ADD CONSTRAINT detect_run_fencing_unico UNIQUE (fencing_token),
  ADD CONSTRAINT detect_run_attempt_unico
    UNIQUE (checkpoint_id, manifest_hash, attempt),
  ADD CONSTRAINT detect_run_claim_fk_key
    UNIQUE (checkpoint_id, manifest_hash, run_id, fencing_token);

CREATE INDEX detect_run_trabalho
  ON detect.run (checkpoint_id, manifest_hash, status);

CREATE INDEX detect_run_lease_ativo
  ON detect.run (lease_expires_at)
  WHERE status IN ('claimed', 'running', 'committing');

CREATE TABLE detect.work_claim (
  checkpoint_id    bigint      NOT NULL,
  manifest_hash    text        NOT NULL CHECK (btrim(manifest_hash) <> ''),
  run_id           bigint      NOT NULL UNIQUE,
  claimed_by       text        NOT NULL CHECK (btrim(claimed_by) <> ''),
  lease_expires_at timestamptz NOT NULL,
  heartbeat_at     timestamptz NOT NULL,
  fencing_token    bigint      NOT NULL UNIQUE CHECK (fencing_token > 0),
  created_at       timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at       timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (checkpoint_id, manifest_hash),
  CONSTRAINT work_claim_lease_valido CHECK (lease_expires_at > heartbeat_at),
  CONSTRAINT work_claim_run_consistente FOREIGN KEY (
    checkpoint_id, manifest_hash, run_id, fencing_token
  ) REFERENCES detect.run (
    checkpoint_id, manifest_hash, run_id, fencing_token
  )
);

COMMENT ON TABLE detect.work_claim IS
  'Ponteiro mutavel para a tentativa que possui checkpoint + manifesto. O '
  'historico imutavel de tentativas permanece em detect.run';
COMMENT ON COLUMN detect.work_claim.lease_expires_at IS
  'Tempo real do banco; nao usa sim.now porque lease mede saude operacional';
COMMENT ON COLUMN detect.work_claim.fencing_token IS
  'Deve coincidir com o run atual. Takeover troca run, owner e token juntos';

CREATE INDEX work_claim_lease_expirado
  ON detect.work_claim (lease_expires_at);

COMMENT ON COLUMN detect.run.sim_now IS
  'Presente virtual congelado ao reivindicar o checkpoint';
COMMENT ON COLUMN detect.run.status IS
  'claimed, running, committing, completed, failed ou abandoned';
COMMENT ON COLUMN detect.run.fencing_token IS
  'Prova monotonicamente crescente de posse; unico em todo o historico';
COMMENT ON COLUMN detect.run.retry_of IS
  'Tentativa anterior do mesmo checkpoint e manifesto, quando houver';
