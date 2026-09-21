-- 018_analysis_inputs.sql
--
-- Entrada canonica e versionada do motor de analise. Diferente das tabelas
-- correntes da Bronze/Silver/Gold, esta tabela nunca sobrescreve uma versao:
-- (fact_key, version_lsn) permite reconstruir exatamente o que um checkpoint
-- podia conhecer.

CREATE TABLE silver.analysis_fact_version (
  fact_key        text        NOT NULL CHECK (length(fact_key) = 64),
  version_lsn     bigint      NOT NULL CHECK (version_lsn >= 0),
  kind            text        NOT NULL CHECK (kind IN ('metric', 'context')),
  event_start     timestamptz NOT NULL,
  event_end       timestamptz,
  available_at    timestamptz NOT NULL,
  source          text        NOT NULL,
  entity          text        NOT NULL,
  metric          text        NOT NULL,
  dimension_type  text,
  dimension_value text,
  value           double precision,
  sample_size     bigint,
  attributes      jsonb       NOT NULL DEFAULT '{}'::jsonb
                                CHECK (jsonb_typeof(attributes) = 'object'),
  is_deleted      boolean     NOT NULL DEFAULT false,
  PRIMARY KEY (fact_key, version_lsn),
  CHECK (event_end IS NULL OR event_end >= event_start),
  CHECK (sample_size IS NULL OR sample_size >= 0)
);

COMMENT ON TABLE silver.analysis_fact_version IS
  'Fatos imutaveis usados por detector, canario e correlacao. A versao mais '
  'recente com version_lsn <= checkpoint.source_lsn representa o estado que o '
  'checkpoint podia conhecer';

CREATE INDEX analysis_fact_as_of
  ON silver.analysis_fact_version (version_lsn, available_at);
CREATE INDEX analysis_fact_series
  ON silver.analysis_fact_version
     (source, entity, metric, event_start, version_lsn DESC);
CREATE INDEX analysis_fact_dimension
  ON silver.analysis_fact_version
     (dimension_type, dimension_value, event_start, version_lsn DESC)
  WHERE dimension_type IS NOT NULL;

CREATE FUNCTION silver.prevent_analysis_fact_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION
    'silver.analysis_fact_version e append-only: fato % versao % nao pode sofrer %',
    OLD.fact_key, OLD.version_lsn, TG_OP;
END
$$;

CREATE TRIGGER analysis_fact_version_append_only
BEFORE UPDATE OR DELETE ON silver.analysis_fact_version
FOR EACH ROW EXECUTE FUNCTION silver.prevent_analysis_fact_mutation();

CREATE FUNCTION silver.analysis_fact_key(VARIADIC parts text[]) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT encode(digest(array_to_string(parts, E'\x1f', '*'), 'sha256'), 'hex')
$$;

-- Materializa cada mudanca diretamente do change_log append-only. Ler a Bronze
-- corrente perderia duas alteracoes da mesma PK que chegassem antes do ciclo do
-- ETL. `before` e usado no delete para preservar a identidade do fato; quando
-- ele nao existe, a PK ainda basta para as familias cuja linha e expandida.
CREATE FUNCTION silver.build_analysis_fact_version(
  p_from_lsn bigint DEFAULT 0,
  p_to_lsn   bigint DEFAULT 9223372036854775807
) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  WITH facts AS (
    -- Serie canonica de 15 minutos.
    SELECT silver.analysis_fact_key(
             'signal_bucket', b.bts::text, b.source, b.entity, b.metric) AS fact_key,
           l.lsn AS version_lsn, 'metric'::text AS kind,
           silver.ts_from_ms(b.bts) AS event_start, NULL::timestamptz AS event_end,
           silver.ts_from_ms(b.bts) + silver.latency_of(b.source) AS available_at,
           b.source, b.entity, b.metric,
           NULL::text AS dimension_type, NULL::text AS dimension_value,
           b.value, NULL::bigint AS sample_size, '{}'::jsonb AS attributes,
           l.op = 'd' AS is_deleted
      FROM bronze.change_log l
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.signal_bucket, COALESCE(l.after, l.before, l.pk)
      ) b
     WHERE l.source_table = 'signal_bucket'
       AND l.lsn > p_from_lsn AND l.lsn <= p_to_lsn

    UNION ALL

    -- RPaaS: percentis de latencia nao entram porque sao nulos no dataset.
    SELECT silver.analysis_fact_key(
             'rpaas_bucket', r.bucket_ts_ms::text, r.region, r.vhost, m.metric),
           l.lsn, 'metric', silver.ts_from_ms(r.bucket_ts_ms), NULL,
           silver.ts_from_ms(r.bucket_ts_ms) + silver.latency_of('rpaas'),
           'rpaas', r.vhost, m.metric, 'region', r.region,
           m.value, r.requests_total::bigint,
           jsonb_build_object('region', r.region), l.op = 'd'
      FROM bronze.change_log l
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.rpaas_bucket, COALESCE(l.after, l.before, l.pk)
      ) r
      CROSS JOIN LATERAL (
        VALUES
          ('requests_total'::text, r.requests_total::double precision),
          ('4xx_rate_pct', CASE WHEN r.requests_total > 0
             THEN 100.0 * r.requests_4xx / r.requests_total END),
          ('5xx_rate_pct', CASE WHEN r.requests_total > 0
             THEN 100.0 * r.requests_5xx / r.requests_total END)
      ) AS m(metric, value)
     WHERE l.source_table = 'rpaas_bucket'
       AND l.lsn > p_from_lsn AND l.lsn <= p_to_lsn

    UNION ALL

    SELECT silver.analysis_fact_key(
             'tsuru_event', t.start_time_ms::text, t.uniqueid),
           l.lsn, 'context', silver.ts_from_ms(t.start_time_ms),
           -- Um evento sem fim registrado chega com o sentinela de data
           -- minima (-62135596800000 ms = ano 1). Converter direto produz
           -- event_end < event_start e derruba o CHECK da tabela inteira:
           -- 2 linhas em 1903 abortavam a migration toda.
           CASE
             WHEN t.end_time_ms IS NULL OR t.end_time_ms < t.start_time_ms
             THEN NULL
             ELSE silver.ts_from_ms(t.end_time_ms)
           END,
           silver.ts_from_ms(t.start_time_ms) + silver.latency_of('tsuru'),
           'tsuru', COALESCE(NULLIF(t.target_value, ''), t.uniqueid),
           COALESCE(t.kind, 'deleted'),
           t.target_type, t.target_value, 1.0, NULL,
           jsonb_strip_nulls(jsonb_build_object(
             'uniqueid', t.uniqueid, 'target_type', t.target_type,
             'target_value', t.target_value, 'owner_type', t.owner_type,
             'owner', t.owner, 'error', NULLIF(t.error, '')
           )), l.op = 'd'
      FROM bronze.change_log l
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.tsuru_event, COALESCE(l.after, l.before, l.pk)
      ) t
     WHERE l.source_table = 'tsuru_event'
       AND l.lsn > p_from_lsn AND l.lsn <= p_to_lsn

    UNION ALL

    SELECT silver.analysis_fact_key(
             'player_hourly', p.hour_ts::text, p.player, m.metric),
           l.lsn, 'metric', silver.ts_from_ms(p.hour_ts), NULL,
           silver.ts_from_ms(p.hour_ts) + silver.latency_of('npaw'),
           'npaw_player', p.player, m.metric, 'player', p.player,
           m.value, p.sessions,
           jsonb_build_object('errors', p.errors, 'sessions', p.sessions),
           l.op = 'd'
      FROM bronze.change_log l
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.player_hourly, COALESCE(l.after, l.before, l.pk)
      ) p
      CROSS JOIN LATERAL (
        VALUES
          ('sessions'::text, p.sessions::double precision),
          ('error_rate_pct', CASE WHEN p.sessions > 0
             THEN 100.0 * p.errors / p.sessions END)
      ) AS m(metric, value)
     WHERE l.source_table = 'player_hourly'
       AND l.lsn > p_from_lsn AND l.lsn <= p_to_lsn

    UNION ALL

    SELECT silver.analysis_fact_key(
             'device_hourly', d.hour_ts::text, d.device, m.metric),
           l.lsn, 'metric', silver.ts_from_ms(d.hour_ts), NULL,
           silver.ts_from_ms(d.hour_ts) + silver.latency_of('npaw'),
           'npaw_device', d.device, m.metric, 'device', d.device,
           m.value, d.sessions,
           jsonb_build_object('errors', d.errors, 'sessions', d.sessions),
           l.op = 'd'
      FROM bronze.change_log l
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.device_hourly, COALESCE(l.after, l.before, l.pk)
      ) d
      CROSS JOIN LATERAL (
        VALUES
          ('sessions'::text, d.sessions::double precision),
          ('error_rate_pct', CASE WHEN d.sessions > 0
             THEN 100.0 * d.errors / d.sessions END)
      ) AS m(metric, value)
     WHERE l.source_table = 'device_hourly'
       AND l.lsn > p_from_lsn AND l.lsn <= p_to_lsn

    UNION ALL

    SELECT silver.analysis_fact_key(
             'geo_hourly', g.hour_ts::text,
             COALESCE(g.state_province, ''), COALESCE(g.isp, ''), m.metric),
           l.lsn, 'metric', silver.ts_from_ms(g.hour_ts), NULL,
           silver.ts_from_ms(g.hour_ts) + silver.latency_of('npaw'),
           'npaw_geo', COALESCE(g.state_province, g.isp), m.metric,
           CASE WHEN g.state_province IS NOT NULL THEN 'uf' ELSE 'isp' END,
           COALESCE(g.state_province, g.isp), m.value, g.sessions,
           jsonb_build_object('errors', g.errors, 'sessions', g.sessions),
           l.op = 'd'
      FROM bronze.change_log l
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.geo_hourly, COALESCE(l.after, l.before, l.pk)
      ) g
      CROSS JOIN LATERAL (
        VALUES
          ('sessions'::text, g.sessions::double precision),
          ('error_rate_pct', CASE WHEN g.sessions > 0
             THEN 100.0 * g.errors / g.sessions END)
      ) AS m(metric, value)
     WHERE l.source_table = 'geo_hourly'
       AND l.lsn > p_from_lsn AND l.lsn <= p_to_lsn
       AND ((g.state_province IS NOT NULL) <> (g.isp IS NOT NULL))

    UNION ALL

    SELECT silver.analysis_fact_key(
             'live_qoe_hourly', q.hour_ts::text, q.sinal, m.metric),
           l.lsn, 'metric', silver.ts_from_ms(q.hour_ts), NULL,
           silver.ts_from_ms(q.hour_ts) + silver.latency_of('npaw'),
           'npaw_live_qoe', q.sinal, m.metric, 'channel', q.sinal,
           m.value, q.sessions,
           jsonb_build_object('sessions', q.sessions, 'errors', q.errors),
           l.op = 'd'
      FROM bronze.change_log l
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.live_qoe_hourly, COALESCE(l.after, l.before, l.pk)
      ) q
      CROSS JOIN LATERAL (
        VALUES
          ('sessions'::text, q.sessions::double precision),
          ('error_rate_pct', CASE WHEN q.sessions > 0
             THEN 100.0 * q.errors / q.sessions END),
          ('startup_error_rate_pct', CASE WHEN q.sessions > 0
             THEN 100.0 * q.startup_errors / q.sessions END),
          ('latency_ms_avg', q.latency_ms_avg),
          ('bufferratio_avg', q.bufferratio_avg),
          ('jointime_s_avg', q.jointime_s_avg),
          ('dropped_frames_avg', q.dropped_frames_avg),
          ('stalls_avg', q.stalls_avg)
      ) AS m(metric, value)
     WHERE l.source_table = 'live_qoe_hourly'
       AND l.lsn > p_from_lsn AND l.lsn <= p_to_lsn
       AND q.sinal NOT IN ('?', '(desconhecido)')

    UNION ALL

    SELECT silver.analysis_fact_key(
             'player_live_hourly', p.hour_ts::text, p.player, m.metric),
           l.lsn, 'metric', silver.ts_from_ms(p.hour_ts), NULL,
           silver.ts_from_ms(p.hour_ts) + silver.latency_of('npaw'),
           'npaw_player_live', p.player, m.metric, 'player', p.player,
           m.value, p.sessions, jsonb_build_object('sessions', p.sessions),
           l.op = 'd'
      FROM bronze.change_log l
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.player_live_hourly, COALESCE(l.after, l.before, l.pk)
      ) p
      CROSS JOIN LATERAL (
        VALUES
          ('sessions'::text, p.sessions::double precision),
          ('error_rate_pct', CASE WHEN p.sessions > 0
             THEN 100.0 * p.errors / p.sessions END),
          ('startup_error_rate_pct', CASE WHEN p.sessions > 0
             THEN 100.0 * p.startup_errors / p.sessions END),
          ('jointime_s_avg', p.jointime_s_avg),
          ('bufferratio_avg', p.bufferratio_avg),
          ('latency_ms_avg', p.latency_ms_avg),
          ('dropped_frames_avg', p.dropped_frames_avg),
          ('stalls_avg', p.stalls_avg)
      ) AS m(metric, value)
     WHERE l.source_table = 'player_live_hourly'
       AND l.lsn > p_from_lsn AND l.lsn <= p_to_lsn

    UNION ALL

    SELECT silver.analysis_fact_key(
             'live_active_15min', a.bucket_ts::text, a.sinal, m.metric),
           l.lsn, 'metric', silver.ts_from_ms(a.bucket_ts), NULL,
           silver.ts_from_ms(a.bucket_ts) + silver.latency_of('npaw'),
           'npaw_live_active', a.sinal, m.metric, 'channel', a.sinal,
           m.value, a.active_sessions,
           jsonb_build_object('active_sessions', a.active_sessions), l.op = 'd'
      FROM bronze.change_log l
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.live_active_15min, COALESCE(l.after, l.before, l.pk)
      ) a
      CROSS JOIN LATERAL (
        VALUES
          ('active_sessions'::text, a.active_sessions::double precision),
          ('active_error_rate_pct', CASE WHEN a.active_sessions > 0
             THEN 100.0 * a.active_with_error / a.active_sessions END),
          ('joins_in_bucket', a.joins_in_bucket::double precision),
          ('latency_ms_p95', a.latency_ms_p95),
          ('bufferratio_avg', a.bufferratio_avg),
          ('jointime_s_avg', a.jointime_s_avg),
          ('dropped_frames_avg', a.dropped_frames_avg)
      ) AS m(metric, value)
     WHERE l.source_table = 'live_active_15min'
       AND l.lsn > p_from_lsn AND l.lsn <= p_to_lsn
       AND a.sinal NOT IN ('?', '(desconhecido)')

    UNION ALL

    SELECT silver.analysis_fact_key(
             'live_error_attr_hourly', e.hour_ts::text, e.sinal, e.cdn,
             e.tier, e.http_code, e.error_name),
           l.lsn, 'metric', silver.ts_from_ms(e.hour_ts), NULL,
           silver.ts_from_ms(e.hour_ts) + silver.latency_of('npaw'),
           'npaw_error_attr', e.sinal, 'errors', 'channel', e.sinal,
           e.errors::double precision, NULL,
           jsonb_strip_nulls(jsonb_build_object(
             'cdn', e.cdn, 'tier', e.tier, 'http_code', e.http_code,
             'error_name', e.error_name
           )), l.op = 'd'
      FROM bronze.change_log l
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.live_error_attr_hourly, COALESCE(l.after, l.before, l.pk)
      ) e
     WHERE l.source_table = 'live_error_attr_hourly'
       AND l.lsn > p_from_lsn AND l.lsn <= p_to_lsn
       AND e.sinal NOT IN ('?', '(desconhecido)')

    UNION ALL

    SELECT silver.analysis_fact_key(
             'error_cat_hourly', e.hour_ts::text, e.kind, e.category),
           l.lsn, 'metric', silver.ts_from_ms(e.hour_ts), NULL,
           silver.ts_from_ms(e.hour_ts) + silver.latency_of('npaw'),
           'npaw_error_category', e.kind, 'errors', 'category', e.category,
           e.errors::double precision, NULL,
           jsonb_build_object('top_names', e.top_names), l.op = 'd'
      FROM bronze.change_log l
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.error_cat_hourly, COALESCE(l.after, l.before, l.pk)
      ) e
     WHERE l.source_table = 'error_cat_hourly'
       AND l.lsn > p_from_lsn AND l.lsn <= p_to_lsn
       AND e.category NOT IN ('?', '(desconhecido)')

    UNION ALL

    SELECT silver.analysis_fact_key(
             'live_event', e.tid::text, e.start_ts::text),
           c.lsn, 'context', silver.ts_from_ms(e.start_ts),
           CASE
             WHEN e.end_ts IS NULL OR e.end_ts < e.start_ts
             THEN NULL
             ELSE silver.ts_from_ms(e.end_ts)
           END,
           COALESCE(silver.ts_from_ms(e.first_seen_ts), silver.ts_from_ms(e.start_ts)),
           'editorial', COALESCE(e.channel, e.slug, e.event_key, e.tid::text),
           'live_event',
           'channel', COALESCE(e.channel, e.slug), 1.0, NULL,
           jsonb_strip_nulls(jsonb_build_object(
             'event_key', e.event_key, 'tid', e.tid, 'slug', e.slug,
             'channel', e.channel, 'competition', e.competition,
             'sport', e.sport, 'team_home', e.team_home, 'team_away', e.team_away
           )), c.op = 'd'
      FROM bronze.change_log c
      CROSS JOIN LATERAL jsonb_populate_record(
        NULL::bronze.live_event, COALESCE(c.after, c.before, c.pk)
      ) e
     WHERE c.source_table = 'live_event'
       AND c.lsn > p_from_lsn AND c.lsn <= p_to_lsn
  )
  INSERT INTO silver.analysis_fact_version (
    fact_key, version_lsn, kind, event_start, event_end, available_at,
    source, entity, metric, dimension_type, dimension_value, value,
    sample_size, attributes, is_deleted
  )
  SELECT fact_key, version_lsn, kind, event_start, event_end, available_at,
         source, entity, metric, dimension_type, dimension_value, value,
         sample_size, attributes, is_deleted
    FROM facts
   WHERE event_start IS NOT NULL
     AND available_at IS NOT NULL
     AND source IS NOT NULL
     AND entity IS NOT NULL
     AND metric IS NOT NULL
  ON CONFLICT (fact_key, version_lsn) DO NOTHING;

  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

COMMENT ON FUNCTION silver.build_analysis_fact_version(bigint, bigint) IS
  'Registra fatos de analise imutaveis para a faixa aberta/fechada de LSN';

-- Integra a materializacao versionada ao mesmo commit do Bronze -> Silver.
CREATE OR REPLACE FUNCTION etl.executar_bronze_silver(p_batch_size int DEFAULT 5000)
RETURNS TABLE (status text, linhas bigint, de_lsn bigint, ate_lsn bigint, erro text)
LANGUAGE plpgsql AS $$
DECLARE
  v_from bigint;
  v_to   bigint;
  v_n    bigint;
  v_erro text;
BEGIN
  SELECT lsn_processado INTO v_from
    FROM etl.watermark_bronze_silver WHERE id = 1 FOR UPDATE;
  v_to := etl.proxima_faixa_lsn(v_from, p_batch_size);
  IF v_to IS NULL THEN
    RETURN QUERY SELECT 'sem_pendencia'::text, 0::bigint, v_from, v_from, NULL::text;
    RETURN;
  END IF;

  BEGIN
    v_n := silver.build_signal_point(v_from, v_to)
         + silver.build_signal_bucket(v_from, v_to)
         + silver.build_session_event(v_from, v_to)
         + silver.build_analysis_fact_version(v_from, v_to);
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_erro = MESSAGE_TEXT;
    INSERT INTO etl.execucoes
      (worker, status, finalizado_em, watermark_anterior, erro)
    VALUES ('bronze_silver', 'falha', now(), v_from::text, v_erro);
    RETURN QUERY SELECT 'falha'::text, 0::bigint, v_from, v_to, v_erro;
    RETURN;
  END;

  INSERT INTO etl.execucoes
    (worker, status, finalizado_em, linhas_processadas,
     watermark_anterior, watermark_novo)
  VALUES ('bronze_silver', 'sucesso', now(), v_n, v_from::text, v_to::text);
  UPDATE etl.watermark_bronze_silver
     SET lsn_processado = v_to, atualizado_em = now()
   WHERE id = 1;
  RETURN QUERY SELECT 'sucesso'::text, v_n, v_from, v_to, NULL::text;
END
$$;

-- Gold passa a guardar o LSN que produziu cada bucket. A coluna e preenchida
-- na aplicacao da migration para os dados existentes e deixa de ser opcional.
ALTER TABLE gold.feature_bucket ADD COLUMN _lsn bigint;
UPDATE gold.feature_bucket g
   SET _lsn = s._lsn
  FROM silver.signal_bucket s
 WHERE s.bucket_ts = g.bucket_ts
   AND s.source = g.source
   AND s.entity = g.entity
   AND s.metric = g.metric;
UPDATE gold.feature_bucket SET _lsn = 0 WHERE _lsn IS NULL;
ALTER TABLE gold.feature_bucket
  ALTER COLUMN _lsn SET DEFAULT 0,
  ALTER COLUMN _lsn SET NOT NULL,
  ADD CONSTRAINT feature_bucket_lsn_valido CHECK (_lsn >= 0);

CREATE FUNCTION gold.build_feature_bucket(
  p_from timestamptz,
  p_to timestamptz,
  p_max_lsn bigint
) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  INSERT INTO gold.feature_bucket (
    bucket_ts, source, entity, metric, value, hora_brt, dow,
    tem_jogo, available_at, _lsn)
  SELECT s.bucket_ts, s.source, s.entity, s.metric, s.value,
         extract(hour FROM s.bucket_ts AT TIME ZONE 'America/Sao_Paulo')::smallint,
         extract(dow FROM s.bucket_ts AT TIME ZONE 'America/Sao_Paulo')::smallint,
         EXISTS (
           SELECT 1 FROM gold.live_event_window w
            WHERE s.bucket_ts >= w.ts_start AND s.bucket_ts < w.ts_end
         ),
         s.available_at, s._lsn
    FROM silver.signal_bucket s
   WHERE s.available_at >= p_from AND s.available_at < p_to
     AND s._lsn <= p_max_lsn
  ON CONFLICT (bucket_ts, source, entity, metric) DO UPDATE
     SET value = EXCLUDED.value, tem_jogo = EXCLUDED.tem_jogo,
         available_at = EXCLUDED.available_at, _lsn = EXCLUDED._lsn
   WHERE gold.feature_bucket._lsn <= EXCLUDED._lsn;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

-- Substitui a versao da 016: source_lsn e agora uma barreira de leitura, nao
-- apenas metadado conservador. source_series e atualizado no mesmo commit.
CREATE OR REPLACE FUNCTION etl.executar_silver_gold(
  p_janela_max_segundos int DEFAULT 14400
)
RETURNS TABLE (
  status text, linhas bigint, de_ts timestamptz, ate_ts timestamptz, erro text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_processado timestamptz;
  v_margem interval;
  v_from timestamptz;
  v_to timestamptz;
  v_live_n bigint;
  v_incident_n bigint;
  v_feature_n bigint;
  v_source_series_n bigint;
  v_n bigint;
  v_erro text;
  v_execucao_id uuid;
  v_sim_run_id bigint;
  v_source_lsn bigint;
BEGIN
  SELECT available_at_processado, margem_seguranca
    INTO v_processado, v_margem
    FROM etl.watermark_silver_gold WHERE id = 1 FOR UPDATE;
  IF p_janela_max_segundos <= extract(epoch FROM v_margem) THEN
    RAISE EXCEPTION
      'etl.executar_silver_gold: janela (%) precisa ser maior que margem (%)',
      p_janela_max_segundos, v_margem;
  END IF;
  v_from := v_processado - v_margem;
  v_to := LEAST(sim.now(), v_processado + make_interval(secs => p_janela_max_segundos));
  IF v_to <= v_from THEN
    RETURN QUERY SELECT 'sem_pendencia'::text, 0::bigint, v_from, v_from, NULL::text;
    RETURN;
  END IF;

  SELECT lsn_processado INTO v_source_lsn
    FROM etl.watermark_bronze_silver WHERE id = 1;
  BEGIN
    v_live_n := gold.build_live_event_window();
    v_incident_n := gold.build_incident_window();
    v_feature_n := gold.build_feature_bucket(v_from, v_to, v_source_lsn);
    v_source_series_n := gold.refresh_source_series();
    v_n := v_live_n + v_incident_n + v_feature_n + v_source_series_n;
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS v_erro = MESSAGE_TEXT;
    INSERT INTO etl.execucoes
      (worker, status, finalizado_em, watermark_anterior, erro)
    VALUES ('silver_gold', 'falha', now(), v_processado::text, v_erro);
    RETURN QUERY SELECT 'falha'::text, 0::bigint, v_from, v_to, v_erro;
    RETURN;
  END;

  INSERT INTO etl.execucoes
    (worker, status, finalizado_em, linhas_processadas,
     watermark_anterior, watermark_novo)
  VALUES ('silver_gold', 'sucesso', now(), v_n, v_processado::text,
          (v_to - v_margem)::text)
  RETURNING execucao_id INTO v_execucao_id;
  UPDATE etl.watermark_silver_gold
     SET available_at_processado = v_to - v_margem,
         atualizado_em = now(), execucao_id = v_execucao_id
   WHERE id = 1;
  SELECT sr.run_id INTO v_sim_run_id
    FROM sim.run sr WHERE sr.status IN ('running', 'paused')
   ORDER BY sr.run_id DESC LIMIT 1;
  INSERT INTO etl.gold_checkpoint (
    etl_execution_id, sim_run_id, ready_through, source_lsn, row_counts
  ) VALUES (
    v_execucao_id, v_sim_run_id, v_to, v_source_lsn,
    jsonb_build_object(
      'live_event_window', v_live_n, 'incident_window', v_incident_n,
      'feature_bucket', v_feature_n, 'source_series', v_source_series_n,
      'total', v_n
    )
  );
  RETURN QUERY SELECT 'sucesso'::text, v_n, v_from, v_to, NULL::text;
END
$$;

-- Bootstrap do estado corrente. Em bancos vazios e um no-op; no ambiente ja
-- carregado registra uma unica versao por fato existente.
SELECT silver.build_analysis_fact_version();
