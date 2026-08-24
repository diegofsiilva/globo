-- 010_merge_e_etl.sql
--
-- A regra do MERGE e as transformacoes bronze -> silver -> gold, em SQL.
--
-- ACRESCIMO ao conjunto de nove migrations do plano, com dois motivos:
--
--   1. §9 do plano exige que o rebuild seja TESTADO ("TRUNCATE em silver e gold
--      seguido de replay reconstroi tudo") e que o fim a fim chegue a gold.v_*.
--      Nenhum dos dois roda se o replay nao existir em lugar nenhum -- e o
--      processing worker e no-op por decisao 7.
--   2. Mover 18 M de linhas de signal_point para dentro do Python so para
--      devolve-las ao mesmo banco seria pagar rede e serializacao por um
--      trabalho que o proprio PostgreSQL faz num INSERT ... SELECT.
--
-- Assim a decisao 7 continua valendo: o container de processamento nao ganha
-- logica nenhuma. Ele passa a ter o que chamar quando ganhar.

-- --------------------------------------------------------------------------- #
-- MERGE: change_log -> bronze corrente
-- --------------------------------------------------------------------------- #

-- Colunas reais de uma tabela da bronze, exceto as de controle (`_`).
CREATE FUNCTION bronze.colunas_de(p_tabela text) RETURNS text[]
LANGUAGE sql STABLE AS $$
  SELECT array_agg(a.attname::text ORDER BY a.attnum)
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname = 'bronze' AND c.relname = p_tabela
     AND a.attnum > 0 AND NOT a.attisdropped
     AND a.attname NOT LIKE '\_%';
$$;

-- Colunas da chave primaria, na ordem em que foram declaradas.
CREATE FUNCTION bronze.pk_de(p_tabela text) RETURNS text[]
LANGUAGE sql STABLE AS $$
  SELECT array_agg(a.attname::text ORDER BY k.ord)
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_index i ON i.indrelid = c.oid AND i.indisprimary
    CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
   WHERE n.nspname = 'bronze' AND c.relname = p_tabela;
$$;

-- Aplica na bronze corrente a faixa [p_from_lsn, p_to_lsn] do log.
--
-- A REGRA, que e a razao de esta funcao existir: uma linha so e sobrescrita se
-- o `_lsn` que chega for MAIOR que o corrente. Evento fora de ordem e
-- descartado, nunca aplicado por cima. E isso que torna o consumo idempotente e
-- tolerante a reentrega do SQS -- a mesma mensagem entregue duas vezes produz o
-- mesmo estado, e uma mensagem atrasada nao desfaz uma atualizacao mais nova.
--
-- Mora em SQL, e nao no worker, para que a regra exista uma vez so: o worker, o
-- replay e o loader passam todos por aqui e nao tem como divergir.
CREATE FUNCTION bronze.merge_do_log(
  p_tabela   text,
  p_from_lsn bigint,
  p_to_lsn   bigint
) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE
  cols      text[] := bronze.colunas_de(p_tabela);
  pk        text[] := bronze.pk_de(p_tabela);
  sem_pk    text[];
  atualiza  text;
  casa_pk   text;
  aplicadas bigint := 0;
  removidas bigint := 0;
BEGIN
  IF cols IS NULL OR pk IS NULL THEN
    RAISE EXCEPTION 'bronze.% nao existe ou nao tem chave primaria', p_tabela;
  END IF;

  -- No ON CONFLICT nao se reescreve a propria chave.
  SELECT array_agg(c) INTO sem_pk FROM unnest(cols) c WHERE NOT (c = ANY(pk));

  SELECT string_agg(format('%I = EXCLUDED.%I', c, c), ', ')
    INTO atualiza
    FROM unnest(
      COALESCE(sem_pk, '{}'::text[])
      || ARRAY['_extra', '_lsn', '_op', '_captured_at']
    ) c;

  -- i / u / r. O DISTINCT ON e obrigatorio: o ON CONFLICT do PostgreSQL recusa
  -- a instrucao INTEIRA ("cannot affect row a second time") se o mesmo pk
  -- aparecer duas vezes no lote -- e duas mudancas da mesma linha dentro de uma
  -- janela de replay sao o caso NORMAL, nao a excecao. Fica a de maior lsn.
  --
  -- `_extra` recebe o que sobrou de `after` depois de tirar as colunas reais:
  -- e o escape de schema em acao. Coluna nova que a Globo acrescentar cai ali
  -- sem DDL e sem perda, e jsonb_populate_record ignora a chave desconhecida
  -- em vez de estourar.
  EXECUTE format($fmt$
    INSERT INTO bronze.%I
    SELECT (jsonb_populate_record(
              NULL::bronze.%I,
              c.after || jsonb_build_object(
                '_lsn', c.lsn, '_op', c.op, '_captured_at', c.captured_at,
                '_extra', c.after - %L::text[]
              )
           )).*
      FROM (
        SELECT DISTINCT ON (l.pk) l.pk, l.after, l.lsn, l.op, l.captured_at
          FROM bronze.change_log l
         WHERE l.source_table = %L AND l.lsn BETWEEN %s AND %s
           AND l.op IN ('i','u','r') AND l.after IS NOT NULL
         ORDER BY l.pk, l.lsn DESC
      ) c
    ON CONFLICT (%s) DO UPDATE SET %s
     WHERE bronze.%I._lsn < EXCLUDED._lsn
  $fmt$,
    p_tabela, p_tabela, cols, p_tabela, p_from_lsn, p_to_lsn,
    (SELECT string_agg(quote_ident(c), ', ') FROM unnest(pk) c),
    atualiza, p_tabela
  );
  GET DIAGNOSTICS aplicadas = ROW_COUNT;

  -- Delete so vale se for mais novo que a versao corrente, pela mesma regra.
  -- O pk vem do log em jsonb e precisa voltar ao tipo real da coluna, senao a
  -- comparacao seria texto contra bigint e nunca casaria.
  SELECT string_agg(
           format('t.%I = (d.pk ->> %L)::%s', u.c, u.c,
                  format_type(a.atttypid, a.atttypmod)), ' AND ')
    INTO casa_pk
    FROM unnest(pk) AS u(c)
    JOIN pg_class cl ON cl.relname = p_tabela
    JOIN pg_namespace n ON n.oid = cl.relnamespace AND n.nspname = 'bronze'
    JOIN pg_attribute a ON a.attrelid = cl.oid AND a.attname = u.c;

  EXECUTE format($fmt$
    DELETE FROM bronze.%I t
     USING (
       SELECT DISTINCT ON (l.pk) l.pk, l.lsn
         FROM bronze.change_log l
        WHERE l.source_table = %L AND l.lsn BETWEEN %s AND %s AND l.op = 'd'
        ORDER BY l.pk, l.lsn DESC
     ) d
     WHERE %s AND t._lsn < d.lsn
  $fmt$, p_tabela, p_tabela, p_from_lsn, p_to_lsn, casa_pk);
  GET DIAGNOSTICS removidas = ROW_COUNT;

  RETURN aplicadas + removidas;
END
$$;

-- Percorre todas as tabelas tocadas na faixa. E o que o merge worker chama
-- depois de anexar o lote ao log, e o que o replay chama sobre o log inteiro.
CREATE FUNCTION bronze.merge_todas(
  p_from_lsn bigint DEFAULT 0,
  p_to_lsn   bigint DEFAULT 9223372036854775807
) RETURNS TABLE (source_table text, linhas bigint)
LANGUAGE plpgsql AS $$
DECLARE
  t text;
BEGIN
  FOR t IN
    SELECT DISTINCT l.source_table
      FROM bronze.change_log l
     WHERE l.lsn BETWEEN p_from_lsn AND p_to_lsn
     ORDER BY 1
  LOOP
    source_table := t;
    linhas := bronze.merge_do_log(t, p_from_lsn, p_to_lsn);
    RETURN NEXT;
  END LOOP;
END
$$;

-- --------------------------------------------------------------------------- #
-- ETL: bronze -> silver
-- --------------------------------------------------------------------------- #

CREATE FUNCTION silver.build_signal_point() RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  INSERT INTO silver.signal_point
    (ts, source, entity, metric, value, tags, available_at, _lsn)
  SELECT silver.ts_from_ms(b.ts),
         b.source, b.entity, b.metric, b.value,
         silver.jsonb_or_null(b.tags),
         silver.ts_from_ms(b.ts) + silver.latency_of(b.source),
         b._lsn
    FROM bronze.signal_point b
  ON CONFLICT (ts, source, entity, metric) DO UPDATE
     SET value = EXCLUDED.value, tags = EXCLUDED.tags,
         available_at = EXCLUDED.available_at, _lsn = EXCLUDED._lsn
   WHERE silver.signal_point._lsn < EXCLUDED._lsn;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

CREATE FUNCTION silver.build_signal_bucket() RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  INSERT INTO silver.signal_bucket
    (bucket_ts, source, entity, metric, value, available_at, _lsn)
  SELECT silver.ts_from_ms(b.bts), b.source, b.entity, b.metric, b.value,
         silver.ts_from_ms(b.bts) + silver.latency_of(b.source),
         b._lsn
    FROM bronze.signal_bucket b
  ON CONFLICT (bucket_ts, source, entity, metric) DO UPDATE
     SET value = EXCLUDED.value, available_at = EXCLUDED.available_at,
         _lsn = EXCLUDED._lsn
   WHERE silver.signal_bucket._lsn < EXCLUDED._lsn;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

CREATE FUNCTION silver.build_session_event() RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  INSERT INTO silver.session_event (
    ts, event_id, event_name, session_id, device_id, user_id,
    app_bucket, app_env, app_target, app_version,
    device_manufacturer, device_model, device_os, route_path, duration,
    uf, isp, payload, available_at, _lsn)
  SELECT e.ts, e.event_id, e.event_name, e.session_id, e.device_id, e.user_id,
         e.app_bucket, e.app_env, e.app_target, e.app_version,
         e.device_manufacturer, e.device_model, e.device_os,
         e.route_path, e.duration,
         -- Hoje sempre NULL: nenhum dos seis tipos de evento traz UF ou ISP, e
         -- o `request` carrega apenas x-country-code: BR. Ler do payload desde
         -- ja e o que faz o dado aparecer sem migration e sem mudanca aqui no
         -- dia em que o outro fluxo do Argus passar a mandar.
         e.payload ->> 'uf',
         e.payload ->> 'isp',
         e.payload,
         -- Grain de sessao chega do proprio aparelho, sem batch no meio: nao ha
         -- latencia estrutural a descontar, ao contrario das fontes NPAW.
         e.ts,
         e._lsn
    FROM bronze.event e
  ON CONFLICT (ts, event_id) DO UPDATE
     SET payload = EXCLUDED.payload, uf = EXCLUDED.uf, isp = EXCLUDED.isp,
         _lsn = EXCLUDED._lsn
   WHERE silver.session_event._lsn < EXCLUDED._lsn;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

-- --------------------------------------------------------------------------- #
-- ETL: bronze/silver -> gold
-- --------------------------------------------------------------------------- #

CREATE FUNCTION gold.build_live_event_window() RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  INSERT INTO gold.live_event_window (
    event_key, tid, ts_start, ts_end, slug, channel, competition,
    sport, team_home, team_away, event_date, first_seen)
  SELECT e.event_key, e.tid,
         silver.ts_from_ms(e.start_ts), silver.ts_from_ms(e.end_ts),
         e.slug, e.channel, e.competition, e.sport, e.team_home, e.team_away,
         -- event_date da origem e o dia de PROGRAMACAO, que nao coincide com a
         -- data UTC quando a transmissao atravessa a meia-noite.
         COALESCE(
           silver.ts_from_iso(e.event_date)::date,
           (silver.ts_from_ms(e.start_ts) AT TIME ZONE 'America/Sao_Paulo')::date
         ),
         silver.ts_from_ms(e.first_seen_ts)
    FROM bronze.live_event e
   WHERE e.start_ts IS NOT NULL AND e.end_ts IS NOT NULL
  ON CONFLICT (tid, ts_start) DO UPDATE
     SET ts_end = EXCLUDED.ts_end, event_key = EXCLUDED.event_key,
         competition = EXCLUDED.competition, team_home = EXCLUDED.team_home,
         team_away = EXCLUDED.team_away;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

CREATE FUNCTION gold.build_incident_window() RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  -- Tickets do ServiceNow.
  INSERT INTO gold.incident_window
    (ts_start, ts_end, origem, ref_id, verdict, severity, provenance)
  SELECT silver.ts_from_ms(i.opened_at),
         silver.ts_from_ms(COALESCE(i.resolved_at, i.closed_at, i.opened_at)),
         'incidents', i.number,
         CASE WHEN i.u_this_incident_caused_external_impacts ILIKE 'true'
              THEN 'external' ELSE 'internal' END,
         i.priority, 'servicenow'
    FROM bronze.incidents i
   WHERE i.opened_at IS NOT NULL AND i.number IS NOT NULL
  ON CONFLICT (origem, ref_id) DO UPDATE
     SET ts_end = EXCLUDED.ts_end, verdict = EXCLUDED.verdict,
         severity = EXCLUDED.severity;

  -- Ground truth rotulado a mao. `provenance` vem da origem sem traducao: e ela
  -- que diz quais dos vinte rotulos sao `detector-derived` e portanto medem
  -- concordancia com o baseline, nao acuracia.
  INSERT INTO gold.incident_window
    (ts_start, ts_end, origem, ref_id, verdict, severity, provenance)
  SELECT silver.ts_from_ms(l.ts_start), silver.ts_from_ms(l.ts_end),
         'incident_label', l.id, l.verdict, l.severity, l.provenance
    FROM bronze.incident_label l
   WHERE l.ts_start IS NOT NULL AND l.ts_end IS NOT NULL
  ON CONFLICT (origem, ref_id) DO UPDATE
     SET ts_end = EXCLUDED.ts_end, verdict = EXCLUDED.verdict,
         severity = EXCLUDED.severity, provenance = EXCLUDED.provenance;

  SELECT count(*) INTO n FROM gold.incident_window;
  RETURN n;
END
$$;

CREATE FUNCTION gold.build_feature_bucket() RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  INSERT INTO gold.feature_bucket (
    bucket_ts, source, entity, metric, value, hora_brt, dow, tem_jogo, available_at)
  SELECT s.bucket_ts, s.source, s.entity, s.metric, s.value,
         -- BRT e nao UTC: o ciclo circadiano de audiencia segue o horario de
         -- quem esta assistindo, nao o do servidor.
         extract(hour FROM s.bucket_ts AT TIME ZONE 'America/Sao_Paulo')::smallint,
         extract(dow  FROM s.bucket_ts AT TIME ZONE 'America/Sao_Paulo')::smallint,
         -- EXISTS, jamais JOIN. A Globo transmite partidas diferentes em pracas
         -- diferentes no mesmo horario, entao ha feeds SIMULTANEOS: um JOIN
         -- duplicaria o bucket uma vez por feed e inflaria toda metrica
         -- agregada em cima dele.
         EXISTS (
           SELECT 1 FROM gold.live_event_window w
            WHERE s.bucket_ts >= w.ts_start AND s.bucket_ts < w.ts_end
         ),
         s.available_at
    FROM silver.signal_bucket s
  ON CONFLICT (bucket_ts, source, entity, metric) DO UPDATE
     SET value = EXCLUDED.value, tem_jogo = EXCLUDED.tem_jogo,
         available_at = EXCLUDED.available_at;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

-- --------------------------------------------------------------------------- #
-- Orquestracao
-- --------------------------------------------------------------------------- #

-- A ordem importa: feature_bucket le live_event_window para resolver `tem_jogo`.
CREATE FUNCTION gold.rebuild_tudo() RETURNS TABLE (etapa text, linhas bigint)
LANGUAGE plpgsql AS $$
BEGIN
  etapa := 'silver.signal_point';    linhas := silver.build_signal_point();    RETURN NEXT;
  etapa := 'silver.signal_bucket';   linhas := silver.build_signal_bucket();   RETURN NEXT;
  etapa := 'silver.session_event';   linhas := silver.build_session_event();   RETURN NEXT;
  etapa := 'gold.live_event_window'; linhas := gold.build_live_event_window(); RETURN NEXT;
  etapa := 'gold.incident_window';   linhas := gold.build_incident_window();   RETURN NEXT;
  etapa := 'gold.feature_bucket';    linhas := gold.build_feature_bucket();    RETURN NEXT;
END
$$;

COMMENT ON FUNCTION gold.rebuild_tudo() IS
  'Reconstroi silver e gold a partir da bronze. Seguro rodar de novo: toda '
  'etapa e ON CONFLICT DO UPDATE. Depois de TRUNCATE em silver/gold, isto mais '
  'bronze.merge_todas() sobre o log devolve as contagens identicas -- e a '
  'propriedade que sustenta a decisao 4 do plano';
