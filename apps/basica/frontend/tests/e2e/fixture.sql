\set ON_ERROR_STOP on

BEGIN;

TRUNCATE silver.session_event, silver.signal_bucket,
         gold.feature_bucket, gold.source_series, gold.incident_window,
         gold.live_event_window, gold.deploy_event, detect.manifest
  RESTART IDENTITY CASCADE;

SELECT sim.set_clock('2026-07-14T12:00:00Z'::timestamptz, 0);

-- Baseline circadiano e sinal atual usado pela tela Agora.
INSERT INTO gold.feature_bucket
  (bucket_ts, source, entity, metric, value, hora_brt, dow, tem_jogo, available_at)
VALUES
  ('2026-07-07T11:00:00Z', 'prometheus', 'playback-api', 'error_rate_pct', 4, 8, 1, false, '2026-07-07T11:00:00Z'),
  ('2026-07-08T11:00:00Z', 'prometheus', 'playback-api', 'error_rate_pct', 5, 8, 2, false, '2026-07-08T11:00:00Z'),
  ('2026-07-09T11:00:00Z', 'prometheus', 'playback-api', 'error_rate_pct', 3, 8, 3, false, '2026-07-09T11:00:00Z'),
  ('2026-07-14T11:15:00Z', 'prometheus', 'playback-api', 'error_rate_pct', 8, 8, 1, false, '2026-07-14T11:15:00Z'),
  ('2026-07-14T11:30:00Z', 'prometheus', 'playback-api', 'error_rate_pct', 11, 8, 1, false, '2026-07-14T11:30:00Z'),
  ('2026-07-14T11:45:00Z', 'prometheus', 'playback-api', 'error_rate_pct', 15, 8, 1, false, '2026-07-14T11:45:00Z');

-- Séries reais para Explorar, Comparar, Recorte e as quatro raias métricas.
INSERT INTO gold.feature_bucket
  (bucket_ts, source, entity, metric, value, hora_brt, dow, tem_jogo, available_at)
VALUES
  ('2026-07-14T09:00:00Z', 'youbora_device', 'LG webOS 3.x', 'sessions', 800, 6, 1, true, '2026-07-14T09:00:00Z'),
  ('2026-07-14T09:00:00Z', 'youbora_device', 'LG webOS 3.x', 'error_rate_pct', 8.5, 6, 1, true, '2026-07-14T09:00:00Z'),
  ('2026-07-14T10:00:00Z', 'youbora_device', 'LG webOS 3.x', 'sessions', 920, 7, 1, true, '2026-07-14T10:00:00Z'),
  ('2026-07-14T10:00:00Z', 'youbora_device', 'LG webOS 3.x', 'error_rate_pct', 9.2, 7, 1, true, '2026-07-14T10:00:00Z'),
  ('2026-07-14T11:00:00Z', 'youbora_device', 'Samsung Tizen', 'sessions', 1200, 8, 1, true, '2026-07-14T11:00:00Z'),
  ('2026-07-14T11:00:00Z', 'youbora_device', 'Samsung Tizen', 'error_rate_pct', 2.1, 8, 1, true, '2026-07-14T11:00:00Z'),
  ('2026-07-14T11:30:00Z', 'npaw', 'globoplay-tv', 'bufferratio', 0.031, 8, 1, true, '2026-07-14T11:30:00Z'),
  ('2026-07-14T11:35:00Z', 'newrelic', 'playback-backend', 'request_count', 180, 8, 1, true, '2026-07-14T11:35:00Z'),
  ('2026-07-14T11:40:00Z', 'apollo', 'identity', 'request_count', 140, 8, 1, true, '2026-07-14T11:40:00Z'),
  ('2026-07-14T11:30:00Z', 'prometheus', 'playback-api', 'request_count', 200, 8, 1, true, '2026-07-14T11:30:00Z'),
  ('2026-07-14T11:35:00Z', 'prometheus', 'playback-api', 'request_count', 260, 8, 1, true, '2026-07-14T11:35:00Z'),
  ('2026-07-07T11:30:00Z', 'prometheus', 'playback-api', 'request_count', 100, 8, 1, true, '2026-07-07T11:30:00Z'),
  ('2026-07-07T11:35:00Z', 'prometheus', 'playback-api', 'request_count', 110, 8, 1, true, '2026-07-07T11:35:00Z'),
  ('2026-07-13T11:30:00Z', 'prometheus', 'playback-api', 'request_count', 150, 8, 0, true, '2026-07-13T11:30:00Z'),
  ('2026-07-13T11:35:00Z', 'prometheus', 'playback-api', 'request_count', 155, 8, 0, true, '2026-07-13T11:35:00Z');

INSERT INTO gold.deploy_event
  (event_id, kind, target_type, target_value, owner, started_at, ended_at, duration_ms, available_at)
VALUES
  ('deploy-e2e', 'deploy', 'app', 'globoplay-tv', 'time-player',
   '2026-07-14T11:38:00Z', '2026-07-14T11:38:45Z', 45000, '2026-07-14T11:38:00Z');

INSERT INTO gold.incident_window
  (ts_start, ts_end, origem, ref_id, verdict, severity, provenance)
VALUES
  ('2026-07-14T11:35:00Z', '2026-07-14T11:55:00Z', 'incidents',
   'INC-E2E-001', 'external', '1', 'servicenow');

INSERT INTO gold.live_event_window
  (event_key, tid, ts_start, ts_end, competition, team_home, team_away, event_date)
VALUES
  ('fla-flu-e2e', 994, '2026-07-13T20:00:00Z', '2026-07-13T22:00:00Z',
   'Brasileirão', 'Flamengo', 'Fluminense', '2026-07-13');

INSERT INTO silver.session_event
  (ts, event_id, event_name, session_id, device_id, app_target, app_version,
   device_manufacturer, device_model, device_os, route_path, payload, available_at, _lsn)
VALUES
  ('2026-07-14T11:20:00Z', 'evt-session', 'session', 'session-e2e', 'device-legacy',
   'tv', '7.4.1', 'LG', 'LG webOS 3.x', 'webOS', '/', '{}'::jsonb,
   '2026-07-14T11:20:00Z', 1),
  ('2026-07-14T11:25:00Z', 'evt-video', 'video_view', 'session-e2e', 'device-legacy',
   'tv', '7.4.1', 'LG', 'LG webOS 3.x', 'webOS', '/watch', '{}'::jsonb,
   '2026-07-14T11:25:00Z', 2),
  ('2026-07-14T11:30:00Z', 'evt-error', 'error', 'session-e2e', 'device-legacy',
   'tv', '7.4.1', 'LG', 'LG webOS 3.x', 'webOS', '/watch',
   '{"error_code":"PLAYER-500"}'::jsonb, '2026-07-14T11:30:00Z', 3);

DO $$
DECLARE
  v_execution_id uuid;
  v_checkpoint_id bigint;
  v_run_id bigint;
  v_hypothesis_id bigint;
  v_manifest constant text := repeat('a', 64);
BEGIN
  INSERT INTO detect.manifest (manifest_hash, payload, code_version)
  VALUES (v_manifest, '{"fixture":"frontend-e2e"}'::jsonb, 'e2e');

  INSERT INTO etl.execucoes (worker, status, finalizado_em, linhas_processadas)
  VALUES ('silver_gold', 'sucesso', clock_timestamp(), 1)
  RETURNING execucao_id INTO v_execution_id;

  INSERT INTO etl.gold_checkpoint (etl_execution_id, ready_through, source_lsn)
  VALUES (v_execution_id, sim.now(), 10)
  RETURNING checkpoint_id INTO v_checkpoint_id;

  INSERT INTO detect.run
    (detector, params, checkpoint_id, manifest_hash, sim_now, status, claimed_by,
     lease_expires_at, heartbeat_at, fencing_token, attempt, input_lsn,
     input_digest, input_rows, stream_key, started_at, finished_at)
  VALUES
    ('e2e', '{}'::jsonb, v_checkpoint_id, v_manifest, sim.now(), 'completed', 'e2e',
     clock_timestamp() + interval '1 minute', clock_timestamp(),
     nextval('detect.fencing_token_seq'), 1, 10, repeat('b', 64), 1, 'live',
     clock_timestamp(), clock_timestamp())
  RETURNING run_id INTO v_run_id;

  INSERT INTO gold.hypothesis_run_stats
    (run_id, input_rows, anomalies, candidates_prefiltered, candidates_evaluated,
     generated, duration_ms)
  VALUES (v_run_id, 1, 1, 1, 1, 1, 25);

  INSERT INTO gold.source_quality_run (run_id, window_start, window_end)
  VALUES (v_run_id, sim.now() - interval '30 minutes', sim.now());

  INSERT INTO gold.source_quality
    (source, run_id, expected_cadence, last_observation_at, freshness,
     completeness, validity, consistency, quality_score, status,
     expected_buckets, observed_buckets)
  VALUES
    ('prometheus', v_run_id, interval '15 minutes', sim.now(), 1, 1, 1, 1, 1,
     'healthy', 2, 2);

  INSERT INTO gold.hypothesis
    (run_id, family, kind, title, summary, scope, effect_start, effect_end,
     score, coverage, confidence, evaluation_status, dedup_key, lineage_key, revision)
  VALUES
    (v_run_id, 'backend_internal', 'operational', 'Falha interna de playback',
     'Aumento de erros corroborado por telemetria real',
     '{"service":"playback"}'::jsonb, sim.now() - interval '30 minutes', sim.now(),
     82, 0.9, 'high', 'generated', repeat('c', 64), repeat('d', 64), 1)
  RETURNING hypothesis_id INTO v_hypothesis_id;

  INSERT INTO gold.hypothesis_feature
    (hypothesis_id, feature, applicability, value, weight, contribution, explanation)
  VALUES
    (v_hypothesis_id, 'A', 'available', 0.9, 0.35, 0.315, 'desvio confirmado'),
    (v_hypothesis_id, 'C', 'available', 0.8, 0.30, 0.240, 'fontes corroboram'),
    (v_hypothesis_id, 'Q', 'available', 1.0, 0.20, 0.200, 'fonte saudável');

  INSERT INTO gold.hypothesis_evidence
    (hypothesis_id, role, polarity, source, entity, metric, event_at,
     available_at, observed, expected, strength, quality, explanation)
  VALUES
    (v_hypothesis_id, 'subject', 'favorable', 'prometheus', 'playback-api',
     'error_rate_pct', sim.now() - interval '15 minutes', sim.now() - interval '15 minutes',
     15, 4, 0.9, 1, 'taxa de erro acima do baseline');

  INSERT INTO gold.manifest_publication_event (manifest_hash, action, gate_metrics)
  VALUES (v_manifest, 'published', '{"fixture":true}'::jsonb);
END $$;

COMMIT;
