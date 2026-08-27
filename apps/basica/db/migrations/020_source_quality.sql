-- 020_source_quality.sql

CREATE TABLE gold.source_quality_run (
  run_id       bigint      PRIMARY KEY REFERENCES detect.run (run_id) ON DELETE CASCADE,
  window_start timestamptz NOT NULL,
  window_end   timestamptz NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (window_end >= window_start)
);

CREATE TABLE gold.source_quality (
  source              text        NOT NULL,
  run_id               bigint      NOT NULL
    REFERENCES gold.source_quality_run (run_id) ON DELETE CASCADE,
  expected_cadence     interval    NOT NULL CHECK (expected_cadence > interval '0'),
  last_observation_at  timestamptz,
  freshness            double precision,
  completeness         double precision,
  validity             double precision,
  consistency          double precision,
  quality_score        double precision,
  status               text        NOT NULL CHECK (
    status IN ('healthy', 'delayed', 'incomplete', 'silent', 'invalid', 'unknown')
  ),
  expected_buckets     integer     NOT NULL DEFAULT 0 CHECK (expected_buckets >= 0),
  observed_buckets     integer     NOT NULL DEFAULT 0 CHECK (observed_buckets >= 0),
  details              jsonb       NOT NULL DEFAULT '{}'::jsonb
                                  CHECK (jsonb_typeof(details) = 'object'),
  PRIMARY KEY (run_id, source),
  CHECK (freshness IS NULL OR freshness BETWEEN 0 AND 1),
  CHECK (completeness IS NULL OR completeness BETWEEN 0 AND 1),
  CHECK (validity IS NULL OR validity BETWEEN 0 AND 1),
  CHECK (consistency IS NULL OR consistency BETWEEN 0 AND 1),
  CHECK (quality_score IS NULL OR quality_score BETWEEN 0 AND 1)
);

CREATE INDEX source_quality_source_run
  ON gold.source_quality (source, run_id DESC);

