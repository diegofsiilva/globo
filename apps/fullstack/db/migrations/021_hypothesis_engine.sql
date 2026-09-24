-- 021_hypothesis_engine.sql

CREATE TABLE gold.finding_group (
  group_id     bigserial   PRIMARY KEY,
  run_id       bigint      NOT NULL REFERENCES detect.run (run_id) ON DELETE CASCADE,
  group_key    text        NOT NULL CHECK (length(group_key) = 64),
  window_start timestamptz NOT NULL,
  window_end   timestamptz NOT NULL,
  scope        jsonb       NOT NULL DEFAULT '{}'::jsonb
                            CHECK (jsonb_typeof(scope) = 'object'),
  UNIQUE (run_id, group_key),
  CHECK (window_end >= window_start)
);

CREATE TABLE gold.finding_group_member (
  group_id     bigint NOT NULL REFERENCES gold.finding_group (group_id) ON DELETE CASCADE,
  finding_kind text   NOT NULL CHECK (finding_kind IN ('anomaly', 'source_quality')),
  finding_id   bigint NOT NULL,
  PRIMARY KEY (group_id, finding_kind, finding_id)
);

CREATE TABLE gold.hypothesis (
  hypothesis_id          bigserial PRIMARY KEY,
  run_id                 bigint      NOT NULL REFERENCES detect.run (run_id) ON DELETE CASCADE,
  group_id               bigint      REFERENCES gold.finding_group (group_id) ON DELETE SET NULL,
  family                 text        NOT NULL,
  kind                   text        NOT NULL CHECK (kind IN ('operational', 'context', 'data_quality')),
  title                  text        NOT NULL,
  summary                text        NOT NULL,
  scope                  jsonb       NOT NULL DEFAULT '{}'::jsonb
                                      CHECK (jsonb_typeof(scope) = 'object'),
  effect_start           timestamptz NOT NULL,
  effect_end             timestamptz NOT NULL,
  score                  double precision NOT NULL CHECK (score BETWEEN 0 AND 100),
  coverage               double precision NOT NULL CHECK (coverage BETWEEN 0 AND 1),
  confidence             text        NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
  evaluation_status      text        NOT NULL CHECK (
    evaluation_status IN ('generated', 'insufficient_evidence', 'discarded')
  ),
  contradiction_strength double precision NOT NULL DEFAULT 0
                                      CHECK (contradiction_strength BETWEEN 0 AND 1),
  dedup_key              text        NOT NULL CHECK (length(dedup_key) = 64),
  lineage_key            text        NOT NULL CHECK (length(lineage_key) = 64),
  revision               integer     NOT NULL CHECK (revision > 0),
  supersedes_hypothesis_id bigint    REFERENCES gold.hypothesis (hypothesis_id),
  created_at             timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (run_id, dedup_key),
  UNIQUE (lineage_key, revision),
  CHECK (effect_end >= effect_start)
);

CREATE INDEX hypothesis_listagem
  ON gold.hypothesis
     (evaluation_status, confidence, score DESC, effect_start DESC, hypothesis_id DESC);
CREATE INDEX hypothesis_latest
  ON gold.hypothesis (lineage_key, revision DESC);

CREATE TABLE gold.hypothesis_finding (
  hypothesis_id bigint NOT NULL REFERENCES gold.hypothesis (hypothesis_id) ON DELETE CASCADE,
  finding_kind  text   NOT NULL CHECK (finding_kind IN ('anomaly', 'source_quality')),
  finding_id    bigint NOT NULL,
  role          text   NOT NULL CHECK (role IN ('subject', 'supporting', 'required')),
  PRIMARY KEY (hypothesis_id, finding_kind, finding_id, role)
);

CREATE TABLE gold.hypothesis_evidence (
  evidence_id   bigserial PRIMARY KEY,
  hypothesis_id bigint      NOT NULL REFERENCES gold.hypothesis (hypothesis_id) ON DELETE CASCADE,
  fact_key      text,
  version_lsn   bigint,
  role          text        NOT NULL CHECK (role IN ('required', 'supporting', 'optional', 'subject')),
  polarity      text        NOT NULL CHECK (polarity IN ('favorable', 'contrary', 'missing')),
  source        text,
  entity        text,
  metric        text,
  event_at      timestamptz,
  available_at  timestamptz,
  observed      double precision,
  expected      double precision,
  strength      double precision CHECK (strength IS NULL OR strength BETWEEN 0 AND 1),
  quality       double precision CHECK (quality IS NULL OR quality BETWEEN 0 AND 1),
  explanation   text        NOT NULL,
  attributes    jsonb       NOT NULL DEFAULT '{}'::jsonb
                              CHECK (jsonb_typeof(attributes) = 'object'),
  FOREIGN KEY (fact_key, version_lsn)
    REFERENCES silver.analysis_fact_version (fact_key, version_lsn),
  CHECK ((fact_key IS NULL) = (version_lsn IS NULL))
);

CREATE INDEX hypothesis_evidence_detail
  ON gold.hypothesis_evidence (hypothesis_id, polarity, evidence_id);

CREATE TABLE gold.hypothesis_feature (
  hypothesis_id bigint NOT NULL REFERENCES gold.hypothesis (hypothesis_id) ON DELETE CASCADE,
  feature       text   NOT NULL CHECK (feature IN ('A', 'T', 'C', 'E', 'I', 'Q', 'X')),
  applicability text   NOT NULL CHECK (applicability IN ('available', 'unavailable', 'not_applicable')),
  value         double precision CHECK (value IS NULL OR value BETWEEN 0 AND 1),
  weight        double precision NOT NULL CHECK (weight BETWEEN 0 AND 1),
  contribution  double precision,
  explanation   text NOT NULL,
  PRIMARY KEY (hypothesis_id, feature)
);

CREATE TABLE gold.hypothesis_feedback (
  feedback_id       bigserial   PRIMARY KEY,
  hypothesis_id     bigint      NOT NULL REFERENCES gold.hypothesis (hypothesis_id),
  verdict           text        NOT NULL CHECK (
    verdict IN ('confirmed', 'partially_confirmed', 'rejected')
  ),
  note              text        CHECK (note IS NULL OR length(note) <= 2000),
  reviewer_ref      text        CHECK (reviewer_ref IS NULL OR length(reviewer_ref) <= 128),
  reviewer_verified boolean     NOT NULL DEFAULT false CHECK (NOT reviewer_verified),
  idempotency_key   uuid        NOT NULL UNIQUE,
  request_id        text,
  submitted_at      timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX hypothesis_feedback_history
  ON gold.hypothesis_feedback (hypothesis_id, submitted_at DESC, feedback_id DESC);

CREATE TABLE gold.hypothesis_run_stats (
  run_id                 bigint PRIMARY KEY REFERENCES detect.run (run_id) ON DELETE CASCADE,
  input_rows             integer NOT NULL DEFAULT 0 CHECK (input_rows >= 0),
  anomalies              integer NOT NULL DEFAULT 0 CHECK (anomalies >= 0),
  candidates_prefiltered integer NOT NULL DEFAULT 0 CHECK (candidates_prefiltered >= 0),
  candidates_evaluated   integer NOT NULL DEFAULT 0 CHECK (candidates_evaluated >= 0),
  candidates_truncated   integer NOT NULL DEFAULT 0 CHECK (candidates_truncated >= 0),
  generated              integer NOT NULL DEFAULT 0 CHECK (generated >= 0),
  insufficient_evidence  integer NOT NULL DEFAULT 0 CHECK (insufficient_evidence >= 0),
  discarded              integer NOT NULL DEFAULT 0 CHECK (discarded >= 0),
  duration_ms            integer CHECK (duration_ms IS NULL OR duration_ms >= 0),
  truncated              boolean NOT NULL DEFAULT false,
  family_counts          jsonb NOT NULL DEFAULT '{}'::jsonb
                              CHECK (jsonb_typeof(family_counts) = 'object')
);

CREATE TABLE gold.manifest_publication_event (
  publication_event_id bigserial PRIMARY KEY,
  manifest_hash        text        NOT NULL REFERENCES detect.manifest (manifest_hash),
  action               text        NOT NULL CHECK (action IN ('published', 'withdrawn')),
  gate_metrics         jsonb       NOT NULL DEFAULT '{}'::jsonb
                                    CHECK (jsonb_typeof(gate_metrics) = 'object'),
  created_at           timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX manifest_publication_latest
  ON gold.manifest_publication_event (manifest_hash, publication_event_id DESC);

