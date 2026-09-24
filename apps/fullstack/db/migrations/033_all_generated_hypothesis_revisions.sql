-- Cada revisao gerada e um resultado auditavel e pode ser aberta pelo seu ID.
-- Revisoes posteriores nao devem ocultar a hipotese que o operador ja viu.

CREATE OR REPLACE VIEW gold.v_hypothesis AS
WITH eligible_run AS (
  SELECT r.*
    FROM detect.run r
   WHERE r.status = 'completed'
     AND r.sim_now <= sim.now()
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
  FROM gold.hypothesis h
  JOIN eligible_run r ON r.run_id = h.run_id
  LEFT JOIN latest_feedback f ON f.hypothesis_id = h.hypothesis_id
 WHERE h.evaluation_status = 'generated'
   AND h.effect_start <= r.sim_now
   AND r.sim_now <= sim.now();
