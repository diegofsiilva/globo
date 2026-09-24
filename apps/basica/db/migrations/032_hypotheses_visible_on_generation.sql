-- Hipoteses geradas em runs concluidos ficam disponiveis para revisao humana.
-- O historico de publicacao permanece auditavel, mas nao filtra a leitura.
-- O relogio virtual continua impedindo a exposicao de resultados futuros.

CREATE OR REPLACE VIEW gold.v_hypothesis_run AS
SELECT r.run_id, r.checkpoint_id, r.manifest_hash, r.sim_run_id, r.stream_key,
       r.sim_now, r.started_at, r.finished_at, r.input_lsn, r.input_digest,
       s.input_rows, s.anomalies, s.candidates_prefiltered,
       s.candidates_evaluated, s.candidates_truncated, s.generated,
       s.insufficient_evidence, s.discarded, s.duration_ms, s.truncated,
       s.family_counts
  FROM detect.run r
  LEFT JOIN gold.hypothesis_run_stats s ON s.run_id = r.run_id
 WHERE r.status = 'completed'
   AND r.sim_now <= sim.now();

CREATE OR REPLACE VIEW gold.v_hypothesis AS
WITH eligible_run AS (
  SELECT r.*
    FROM detect.run r
   WHERE r.status = 'completed'
     AND r.sim_now <= sim.now()
), latest_revision AS (
  SELECT DISTINCT ON (h.lineage_key) h.*
    FROM gold.hypothesis h
    JOIN eligible_run r ON r.run_id = h.run_id
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
