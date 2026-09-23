-- Visualizacao controlada de uma hipotese para inspecao no lab.
-- `preview` nao atesta os criterios de promocao do manifesto. A ultima acao
-- continua append-only: `withdrawn` oculta a visualizacao sem apagar a trilha.

ALTER TABLE gold.manifest_publication_event
  DROP CONSTRAINT manifest_publication_event_action_check;

ALTER TABLE gold.manifest_publication_event
  ADD CONSTRAINT manifest_publication_event_action_check CHECK (
    action IN ('published', 'withdrawn', 'preview')
    AND (
      action <> 'preview'
      OR (
        COALESCE(jsonb_typeof(gate_metrics->'hypothesis_id') = 'number', false)
        AND COALESCE(gate_metrics->>'hypothesis_id' ~ '^[0-9]+$', false)
      )
    )
  );

CREATE OR REPLACE VIEW gold.v_hypothesis_run AS
WITH publication AS (
  SELECT DISTINCT ON (manifest_hash) manifest_hash, action, gate_metrics
    FROM gold.manifest_publication_event
   ORDER BY manifest_hash, publication_event_id DESC
)
SELECT r.run_id, r.checkpoint_id, r.manifest_hash, r.sim_run_id, r.stream_key,
       r.sim_now, r.started_at, r.finished_at, r.input_lsn, r.input_digest,
       s.input_rows, s.anomalies, s.candidates_prefiltered,
       s.candidates_evaluated, s.candidates_truncated, s.generated,
       s.insufficient_evidence, s.discarded, s.duration_ms, s.truncated,
       s.family_counts
  FROM detect.run r
  JOIN publication p ON p.manifest_hash = r.manifest_hash
  LEFT JOIN gold.hypothesis_run_stats s ON s.run_id = r.run_id
 WHERE r.status = 'completed'
   AND r.sim_now <= sim.now()
   AND (
     p.action = 'published'
     OR (p.action = 'preview' AND EXISTS (
       SELECT 1 FROM gold.hypothesis h
        WHERE h.run_id = r.run_id
          AND h.hypothesis_id = (p.gate_metrics->>'hypothesis_id')::bigint
          AND h.evaluation_status = 'generated'
     ))
   );

CREATE OR REPLACE VIEW gold.v_hypothesis AS
WITH publication AS (
  SELECT DISTINCT ON (manifest_hash) manifest_hash, action, gate_metrics
    FROM gold.manifest_publication_event
   ORDER BY manifest_hash, publication_event_id DESC
), eligible_run AS (
  SELECT r.*, p.action, p.gate_metrics
    FROM detect.run r
    JOIN publication p ON p.manifest_hash = r.manifest_hash
   WHERE r.status = 'completed'
     AND r.sim_now <= sim.now()
     AND p.action IN ('published', 'preview')
), latest_revision AS (
  SELECT DISTINCT ON (h.lineage_key) h.*
    FROM gold.hypothesis h
    JOIN eligible_run r ON r.run_id = h.run_id
   WHERE r.action = 'published'
      OR h.hypothesis_id = (r.gate_metrics->>'hypothesis_id')::bigint
   ORDER BY h.lineage_key, h.revision DESC
), latest_feedback AS (
  SELECT DISTINCT ON (hypothesis_id)
         hypothesis_id, verdict AS review_status, submitted_at
    FROM gold.hypothesis_feedback
   ORDER BY hypothesis_id, submitted_at DESC, feedback_id DESC
)
SELECT h.hypothesis_id, h.run_id, h.family, h.kind, h.title, h.summary,
       h.scope, h.effect_start, h.effect_end, h.score, h.coverage,
       h.confidence, h.evaluation_status,
       COALESCE(f.review_status, 'unreviewed') AS review_status,
       h.contradiction_strength, h.dedup_key, h.lineage_key, h.revision,
       h.supersedes_hypothesis_id, r.sim_now, r.manifest_hash, h.created_at
  FROM latest_revision h
  JOIN eligible_run r ON r.run_id = h.run_id
  LEFT JOIN latest_feedback f ON f.hypothesis_id = h.hypothesis_id
 WHERE h.evaluation_status = 'generated'
   AND h.effect_start <= r.sim_now
   AND r.sim_now <= sim.now();
