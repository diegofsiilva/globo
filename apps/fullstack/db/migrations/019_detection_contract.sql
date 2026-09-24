-- 019_detection_contract.sql
-- Manifesto, cursor sequencial, fotografia de entrada e estado causal.

CREATE TABLE detect.manifest (
  manifest_hash text        PRIMARY KEY
    CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
  payload       jsonb       NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  code_version  text        NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE detect.run
  ADD COLUMN stream_key text,
  ADD COLUMN previous_checkpoint_id bigint
    REFERENCES etl.gold_checkpoint (checkpoint_id),
  ADD COLUMN input_rows integer,
  ADD COLUMN input_bytes bigint;

UPDATE detect.run
   SET stream_key = COALESCE('sim:' || sim_run_id::text, 'live')
 WHERE stream_key IS NULL;

ALTER TABLE detect.run
  ALTER COLUMN stream_key SET DEFAULT 'live',
  ALTER COLUMN stream_key SET NOT NULL,
  ADD CONSTRAINT detect_run_manifest_fk
    FOREIGN KEY (manifest_hash) REFERENCES detect.manifest (manifest_hash)
    NOT VALID,
  ADD CONSTRAINT detect_run_input_rows_valido
    CHECK (input_rows IS NULL OR input_rows >= 0),
  ADD CONSTRAINT detect_run_input_bytes_valido
    CHECK (input_bytes IS NULL OR input_bytes >= 0);

-- Runs embrionarios anteriores a 019 podem ter manifesto que nao existe na
-- tabela nova, por isso a FK nasce NOT VALID. Todo run novo e validado.

CREATE TABLE detect.analysis_cursor (
  manifest_hash                text        NOT NULL
    REFERENCES detect.manifest (manifest_hash),
  stream_key                   text        NOT NULL,
  sim_run_id                   bigint      REFERENCES sim.run (run_id),
  last_completed_checkpoint_id bigint      REFERENCES etl.gold_checkpoint (checkpoint_id),
  last_ready_through           timestamptz,
  last_source_lsn              bigint      NOT NULL DEFAULT 0 CHECK (last_source_lsn >= 0),
  active_run_id                bigint      REFERENCES detect.run (run_id) ON DELETE SET NULL,
  updated_at                   timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (manifest_hash, stream_key)
);

COMMENT ON TABLE detect.analysis_cursor IS
  'Serializa checkpoints do mesmo manifesto e replay. O cursor so avanca no '
  'mesmo commit protegido que publica os resultados e o baseline';

CREATE TABLE detect.run_input_fact (
  run_id       bigint NOT NULL REFERENCES detect.run (run_id) ON DELETE CASCADE,
  fact_key     text   NOT NULL,
  version_lsn  bigint NOT NULL,
  role         text   NOT NULL CHECK (role IN ('subject', 'context', 'quality')),
  PRIMARY KEY (run_id, fact_key, version_lsn, role),
  FOREIGN KEY (fact_key, version_lsn)
    REFERENCES silver.analysis_fact_version (fact_key, version_lsn)
);

CREATE INDEX run_input_fact_lookup
  ON detect.run_input_fact (run_id, role, fact_key);

CREATE TABLE detect.baseline_state (
  manifest_hash text        NOT NULL REFERENCES detect.manifest (manifest_hash),
  stream_key    text        NOT NULL,
  source        text        NOT NULL,
  entity        text        NOT NULL,
  metric        text        NOT NULL,
  hour_brt      smallint    NOT NULL CHECK (hour_brt BETWEEN 0 AND 23),
  mean          double precision,
  variance      double precision,
  n             integer     NOT NULL DEFAULT 0 CHECK (n >= 0),
  last_event_at timestamptz,
  updated_run_id bigint     REFERENCES detect.run (run_id),
  PRIMARY KEY (manifest_hash, stream_key, source, entity, metric, hour_brt),
  CHECK (variance IS NULL OR variance >= 0)
);

ALTER TABLE detect.anomaly
  ADD COLUMN anomaly_id bigint GENERATED ALWAYS AS IDENTITY,
  ADD COLUMN fact_key text,
  ADD COLUMN version_lsn bigint,
  ADD COLUMN observed double precision,
  ADD COLUMN expected double precision,
  ADD COLUMN direction text,
  ADD COLUMN deviation double precision,
  ADD COLUMN strength double precision,
  ADD COLUMN available_at timestamptz,
  ADD COLUMN sample_size bigint,
  ADD COLUMN baseline_snapshot jsonb;

ALTER TABLE detect.anomaly
  ADD CONSTRAINT detect_anomaly_id_unico UNIQUE (anomaly_id),
  ADD CONSTRAINT detect_anomaly_fact_fk
    FOREIGN KEY (fact_key, version_lsn)
    REFERENCES silver.analysis_fact_version (fact_key, version_lsn),
  ADD CONSTRAINT detect_anomaly_fact_par_valido
    CHECK ((fact_key IS NULL) = (version_lsn IS NULL)),
  ADD CONSTRAINT detect_anomaly_direction_valida
    CHECK (direction IS NULL OR direction IN ('up', 'down', 'two_sided')),
  ADD CONSTRAINT detect_anomaly_strength_valida
    CHECK (strength IS NULL OR strength BETWEEN 0 AND 1),
  ADD CONSTRAINT detect_anomaly_sample_valida
    CHECK (sample_size IS NULL OR sample_size >= 0),
  ADD CONSTRAINT detect_anomaly_baseline_valido
    CHECK (baseline_snapshot IS NULL OR jsonb_typeof(baseline_snapshot) = 'object');

CREATE INDEX anomaly_series_window
  ON detect.anomaly (source, entity, metric, bucket_ts);
CREATE INDEX anomaly_run_strength
  ON detect.anomaly (run_id, strength DESC NULLS LAST, bucket_ts);
