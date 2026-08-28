-- 022_hypothesis_views.sql

CREATE VIEW gold.v_hypothesis_run AS
WITH publication AS (
  SELECT DISTINCT ON (manifest_hash) manifest_hash, action
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
  JOIN publication p ON p.manifest_hash = r.manifest_hash AND p.action = 'published'
  LEFT JOIN gold.hypothesis_run_stats s ON s.run_id = r.run_id
 WHERE r.status = 'completed'
   AND r.sim_now <= sim.now();

CREATE VIEW gold.v_hypothesis AS
WITH publication AS (
  SELECT DISTINCT ON (manifest_hash) manifest_hash, action
    FROM gold.manifest_publication_event
   ORDER BY manifest_hash, publication_event_id DESC
), eligible_run AS (
  SELECT r.*
    FROM detect.run r
    JOIN publication p ON p.manifest_hash = r.manifest_hash AND p.action = 'published'
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

CREATE VIEW gold.v_hypothesis_detail AS
SELECT h.*,
       jsonb_build_object(
         'run_id', r.run_id, 'checkpoint_id', r.checkpoint_id,
         'sim_now', r.sim_now, 'input_lsn', r.input_lsn,
         'input_digest', r.input_digest, 'manifest_hash', r.manifest_hash
       ) AS run,
       m.payload AS manifest,
       COALESCE((
         SELECT jsonb_agg(jsonb_build_object(
           'feature', f.feature, 'applicability', f.applicability,
           'value', f.value, 'weight', f.weight,
           'contribution', f.contribution, 'explanation', f.explanation
         ) ORDER BY f.feature)
           FROM gold.hypothesis_feature f
          WHERE f.hypothesis_id = h.hypothesis_id
       ), '[]'::jsonb) AS features,
       COALESCE((
         SELECT jsonb_agg(jsonb_build_object(
           'feedback_id', fb.feedback_id, 'verdict', fb.verdict,
           'note', fb.note, 'reviewer_ref', fb.reviewer_ref,
           'reviewer_verified', fb.reviewer_verified,
           'submitted_at', fb.submitted_at
         ) ORDER BY fb.submitted_at, fb.feedback_id)
           FROM gold.hypothesis_feedback fb
          WHERE fb.hypothesis_id = h.hypothesis_id
       ), '[]'::jsonb) AS feedback,
       COALESCE((
         SELECT jsonb_agg(jsonb_build_object(
           'finding_kind', hf.finding_kind, 'finding_id', hf.finding_id,
           'role', hf.role, 'bucket_ts', a.bucket_ts, 'source', a.source,
           'entity', a.entity, 'metric', a.metric, 'observed', a.observed,
           'expected', a.expected, 'direction', a.direction,
           'strength', a.strength, 'baseline', a.baseline_snapshot
         ) ORDER BY hf.finding_kind, hf.finding_id, hf.role)
           FROM gold.hypothesis_finding hf
           LEFT JOIN detect.anomaly a
             ON hf.finding_kind = 'anomaly' AND a.anomaly_id = hf.finding_id
          WHERE hf.hypothesis_id = h.hypothesis_id
       ), '[]'::jsonb) AS findings,
       COALESCE((
         SELECT jsonb_agg(jsonb_build_object(
           'source', q.source, 'status', q.status,
           'freshness', q.freshness, 'completeness', q.completeness,
           'validity', q.validity, 'consistency', q.consistency,
           'quality_score', q.quality_score, 'details', q.details
         ) ORDER BY q.source)
           FROM gold.source_quality q
          WHERE q.run_id = h.run_id
       ), '[]'::jsonb) AS source_quality,
       COALESCE((
         SELECT jsonb_agg(jsonb_build_object(
           'role', e.role, 'explanation', e.explanation,
           'attributes', e.attributes
         ) ORDER BY e.evidence_id)
           FROM gold.hypothesis_evidence e
          WHERE e.hypothesis_id = h.hypothesis_id
            AND e.polarity = 'missing'
       ), '[]'::jsonb) AS missing_evidence
  FROM gold.v_hypothesis h
  JOIN detect.run r ON r.run_id = h.run_id
  JOIN detect.manifest m ON m.manifest_hash = r.manifest_hash;

CREATE VIEW gold.v_hypothesis_evidence AS
SELECT e.evidence_id, e.hypothesis_id, e.role, e.polarity, e.source,
       e.entity, e.metric, e.event_at, e.available_at, e.observed,
       e.expected, e.strength, e.quality, e.explanation, e.attributes
  FROM gold.hypothesis_evidence e
  JOIN gold.v_hypothesis h ON h.hypothesis_id = e.hypothesis_id
 WHERE e.available_at IS NULL OR e.available_at <= h.sim_now;

CREATE FUNCTION gold.submit_hypothesis_feedback(
  p_hypothesis_id bigint,
  p_verdict text,
  p_note text,
  p_reviewer_ref text,
  p_idempotency_key uuid,
  p_request_id text DEFAULT NULL
) RETURNS TABLE (feedback_id bigint, created boolean)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, gold
AS $$
DECLARE
  v_id bigint;
  v_existing gold.hypothesis_feedback%ROWTYPE;
BEGIN
  IF p_verdict NOT IN ('confirmed', 'partially_confirmed', 'rejected') THEN
    RAISE EXCEPTION 'verdict invalido' USING ERRCODE = '22023';
  END IF;
  IF p_note IS NOT NULL AND length(p_note) > 2000 THEN
    RAISE EXCEPTION 'note excede 2000 caracteres' USING ERRCODE = '22023';
  END IF;
  IF p_reviewer_ref IS NOT NULL AND length(p_reviewer_ref) > 128 THEN
    RAISE EXCEPTION 'reviewer_ref excede 128 caracteres' USING ERRCODE = '22023';
  END IF;
  IF p_idempotency_key IS NULL THEN
    RAISE EXCEPTION 'idempotency_key obrigatoria' USING ERRCODE = '22023';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM gold.v_hypothesis h WHERE h.hypothesis_id = p_hypothesis_id
  ) THEN
    RAISE EXCEPTION 'hipotese publicada inexistente' USING ERRCODE = 'P0002';
  END IF;

  SELECT f.* INTO v_existing
    FROM gold.hypothesis_feedback f
   WHERE f.idempotency_key = p_idempotency_key;
  IF FOUND THEN
    IF v_existing.hypothesis_id IS DISTINCT FROM p_hypothesis_id
       OR v_existing.verdict IS DISTINCT FROM p_verdict
       OR v_existing.note IS DISTINCT FROM NULLIF(btrim(p_note), '')
       OR v_existing.reviewer_ref IS DISTINCT FROM NULLIF(btrim(p_reviewer_ref), '') THEN
      RAISE EXCEPTION 'idempotency_key reutilizada com payload diferente'
        USING ERRCODE = 'P0003';
    END IF;
    RETURN QUERY SELECT v_existing.feedback_id, false;
    RETURN;
  END IF;

  INSERT INTO gold.hypothesis_feedback (
    hypothesis_id, verdict, note, reviewer_ref, reviewer_verified,
    idempotency_key, request_id
  ) VALUES (
    p_hypothesis_id, p_verdict, NULLIF(btrim(p_note), ''),
    NULLIF(btrim(p_reviewer_ref), ''), false, p_idempotency_key, p_request_id
  ) RETURNING gold.hypothesis_feedback.feedback_id INTO v_id;
  RETURN QUERY SELECT v_id, true;
END
$$;

REVOKE ALL ON FUNCTION gold.submit_hypothesis_feedback(
  bigint, text, text, text, uuid, text
) FROM PUBLIC;

GRANT SELECT ON gold.v_hypothesis_run, gold.v_hypothesis,
  gold.v_hypothesis_detail, gold.v_hypothesis_evidence TO argus_reader;
GRANT EXECUTE ON FUNCTION gold.submit_hypothesis_feedback(
  bigint, text, text, text, uuid, text
) TO argus_reader;
