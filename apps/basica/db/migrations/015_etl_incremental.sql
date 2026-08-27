-- 015_etl_incremental.sql
--
-- Watermarks e as duas funcoes de orquestracao do ETL incremental
-- (bronze->silver e silver->gold), conforme o guia "Watermarks e workers de
-- transicao de camada" (publicacao interna, 20/08/2026).
--
-- Ate aqui, `gold.rebuild_tudo()` (010_merge_e_etl.sql) faz RECOMPUTE
-- COMPLETO a cada chamada: os `build_*` variam sobre a tabela de origem
-- inteira, e so o `ON CONFLICT ... WHERE _lsn < EXCLUDED._lsn` evita reescrita
-- desnecessaria. Isso e correto e e o que sustenta o teste de rebuild do §9 do
-- plano, mas nao escala: rodar a cada 1-5 min sobre 18 M linhas de
-- signal_point custaria uma varredura completa por ciclo.
--
-- Esta migration NAO edita 010 (migration aplicada e imutavel -- ver
-- tools/migrate.py). Em vez disso substitui a ASSINATURA das funcoes
-- `build_*` que precisam de filtro incremental, acrescentando parametros de
-- faixa com DEFAULT que reproduzem o comportamento antigo (faixa aberta) --
-- por isso `gold.rebuild_tudo()` continua chamando `silver.build_signal_point()`
-- sem argumento nenhum e nada quebra: a resolucao de chamada em PL/pgSQL e
-- por nome, feita em tempo de execucao, entao trocar a funcao depois que
-- `rebuild_tudo` foi criada nao exige recriar `rebuild_tudo`.
--
-- Duas exclusoes deliberadas do escopo "windowed": `gold.build_live_event_window`
-- e `gold.build_incident_window` continuam de tabela inteira. As origens
-- (`bronze.live_event`, `bronze.incidents`, `bronze.incident_label`) sao
-- pequenas -- centenas a poucos milhares de linhas -- contra os quase 5 M de
-- `signal_bucket`. Recomputar as duas por inteiro a cada ciclo do worker
-- silver->gold custa menos do que o esforco de as tornar incrementais tambem
-- compraria. Se um dia isso deixar de ser verdade (por exemplo, `incidents`
-- crescer muito), revisitar aqui.

-- --------------------------------------------------------------------------- #
-- Schema de controle
-- --------------------------------------------------------------------------- #

CREATE SCHEMA IF NOT EXISTS etl;

COMMENT ON SCHEMA etl IS
  'Controle da transformacao incremental: watermarks e log de execucoes dos '
  'dois workers (bronze->silver, silver->gold). Nao e camada de dado -- nenhuma '
  'tela le daqui';

-- gen_random_uuid(): builtin do PostgreSQL 13+ (pgcrypto nao e mais
-- necessario), mas a extensao continua sendo o jeito documentado de garantir a
-- funcao em qualquer versao suportada.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- --------------------------------------------------------------------------- #
-- Watermark bronze -> silver: marcador SEQUENCIAL (lsn)
-- --------------------------------------------------------------------------- #

CREATE TABLE etl.watermark_bronze_silver (
  id             smallint    PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  lsn_processado bigint      NOT NULL DEFAULT 0,
  atualizado_em  timestamptz NOT NULL DEFAULT now(),
  execucao_id    uuid
);

COMMENT ON TABLE etl.watermark_bronze_silver IS
  'Uma linha so (CHECK id=1): nao existe watermark "por fonte" nessa transicao '
  '-- e sempre a bronze corrente inteira, por construcao do change_log unico';
COMMENT ON COLUMN etl.watermark_bronze_silver.lsn_processado IS
  'Maior lsn do bronze.change_log ja levado para a silver. Marcador de '
  'retomada: se o worker cair, ele sabe exatamente de onde continuar';
COMMENT ON COLUMN etl.watermark_bronze_silver.atualizado_em IS
  'Sinal operacional direto: se parar de mudar, o worker parou de rodar';

INSERT INTO etl.watermark_bronze_silver (id, lsn_processado)
VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;

-- --------------------------------------------------------------------------- #
-- Watermark silver -> gold: marcador TEMPORAL (available_at) com margem
-- --------------------------------------------------------------------------- #

CREATE TABLE etl.watermark_silver_gold (
  id                       smallint    PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  available_at_processado timestamptz NOT NULL,
  margem_seguranca        interval    NOT NULL DEFAULT interval '2 hours',
  atualizado_em            timestamptz NOT NULL DEFAULT now(),
  execucao_id              uuid
);

COMMENT ON COLUMN etl.watermark_silver_gold.available_at_processado IS
  'Ate onde a gold esta "fechada" fora da margem de reabertura. NAO e "processei '
  'tudo ate aqui": e "processei tudo ate aqui e vou reabrir de novo a faixa da '
  'margem no proximo ciclo", de proposito -- e o que absorve dado fora de ordem';
COMMENT ON COLUMN etl.watermark_silver_gold.margem_seguranca IS
  'Fica como coluna, nao como constante no worker, para poder recalibrar sem '
  'deploy assim que o atraso real do pipeline for medido rodando o injetor de '
  'falhas de verdade';

-- Divergencia deliberada da publicacao "Watermarks do Argus", que semeava
-- 1970-01-01 (epoch): aqui NAO ha dado possivel antes do limite inferior das
-- particoes de silver/gold (`date '2026-07-01'`, ver 006_silver.sql e
-- 007_gold.sql). Semear em epoch faria o primeiro drenar() do worker
-- percorrer ~56 anos em janelas de minutos ate encontrar a primeira linha real
-- -- correto, so que muito lento. Semear no inicio real dos dados elimina essa
-- varredura vazia sem mudar nenhuma garantia de correcao.
INSERT INTO etl.watermark_silver_gold (id, available_at_processado)
VALUES (1, timestamptz '2026-07-01 00:00:00+00')
ON CONFLICT (id) DO NOTHING;

-- --------------------------------------------------------------------------- #
-- Log de execucoes -- observabilidade dos dois workers
-- --------------------------------------------------------------------------- #

CREATE TABLE etl.execucoes (
  execucao_id        uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  worker             text        NOT NULL
                      CHECK (worker IN ('bronze_silver', 'silver_gold')),
  iniciado_em        timestamptz NOT NULL DEFAULT now(),
  finalizado_em       timestamptz,
  status             text        NOT NULL DEFAULT 'em_execucao'
                      CHECK (status IN ('em_execucao', 'sem_pendencia', 'sucesso', 'falha')),
  linhas_processadas  integer,
  watermark_anterior  text,
  watermark_novo      text,
  erro               text
);

COMMENT ON TABLE etl.execucoes IS
  'Uma linha por chamada de etl.executar_bronze_silver/etl.executar_silver_gold '
  '-- responde "quando foi a ultima vez que isso rodou, e o que processou" sem '
  'grep de log do CloudWatch';
COMMENT ON COLUMN etl.execucoes.watermark_anterior IS
  'Texto de proposito: o mesmo log serve pros dois workers, guardando um lsn '
  'num caso e um timestamp no outro. Nao precisa de tipagem forte -- e para '
  'leitura humana, nao para logica programatica em cima';
COMMENT ON COLUMN etl.execucoes.status IS
  '''sem_pendencia'' registrado so em memoria (nunca grava linha -- ver '
  'etl.executar_*): backlog vazio nao e evento que mereca uma linha por ciclo, '
  'senao a tabela cresceria por ociosidade em vez de por trabalho';

CREATE INDEX etl_execucoes_worker_status
    ON etl.execucoes (worker, status, iniciado_em DESC);

-- --------------------------------------------------------------------------- #
-- silver.build_* -- versoes com faixa de lsn (DROP + CREATE: muda a aridade)
-- --------------------------------------------------------------------------- #

DROP FUNCTION silver.build_signal_point();

CREATE FUNCTION silver.build_signal_point(
  p_from_lsn bigint DEFAULT 0,
  p_to_lsn   bigint DEFAULT 9223372036854775807
) RETURNS bigint
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
   WHERE b._lsn > p_from_lsn AND b._lsn <= p_to_lsn
  ON CONFLICT (ts, source, entity, metric) DO UPDATE
     SET value = EXCLUDED.value, tags = EXCLUDED.tags,
         available_at = EXCLUDED.available_at, _lsn = EXCLUDED._lsn
   WHERE silver.signal_point._lsn < EXCLUDED._lsn;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

COMMENT ON FUNCTION silver.build_signal_point(bigint, bigint) IS
  'Faixa aberta (0, bigint max) por DEFAULT reproduz o comportamento de '
  'rebuild completo -- gold.rebuild_tudo() continua chamando sem argumento. '
  'O worker incremental (etl.executar_bronze_silver) passa a faixa real';

DROP FUNCTION silver.build_signal_bucket();

CREATE FUNCTION silver.build_signal_bucket(
  p_from_lsn bigint DEFAULT 0,
  p_to_lsn   bigint DEFAULT 9223372036854775807
) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  INSERT INTO silver.signal_bucket
    (bucket_ts, source, entity, metric, value, available_at, _lsn)
  SELECT silver.ts_from_ms(b.bts), b.source, b.entity, b.metric, b.value,
         silver.ts_from_ms(b.bts) + silver.latency_of(b.source),
         b._lsn
    FROM bronze.signal_bucket b
   WHERE b._lsn > p_from_lsn AND b._lsn <= p_to_lsn
  ON CONFLICT (bucket_ts, source, entity, metric) DO UPDATE
     SET value = EXCLUDED.value, available_at = EXCLUDED.available_at,
         _lsn = EXCLUDED._lsn
   WHERE silver.signal_bucket._lsn < EXCLUDED._lsn;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

DROP FUNCTION silver.build_session_event();

CREATE FUNCTION silver.build_session_event(
  p_from_lsn bigint DEFAULT 0,
  p_to_lsn   bigint DEFAULT 9223372036854775807
) RETURNS bigint
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
         e.payload ->> 'uf',
         e.payload ->> 'isp',
         e.payload,
         e.ts,
         e._lsn
    FROM bronze.event e
   WHERE e._lsn > p_from_lsn AND e._lsn <= p_to_lsn
  ON CONFLICT (ts, event_id) DO UPDATE
     SET payload = EXCLUDED.payload, uf = EXCLUDED.uf, isp = EXCLUDED.isp,
         _lsn = EXCLUDED._lsn
   WHERE silver.session_event._lsn < EXCLUDED._lsn;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

-- --------------------------------------------------------------------------- #
-- gold.build_feature_bucket -- versao com janela de available_at
-- --------------------------------------------------------------------------- #

DROP FUNCTION gold.build_feature_bucket();

CREATE FUNCTION gold.build_feature_bucket(
  p_from timestamptz DEFAULT '-infinity',
  p_to   timestamptz DEFAULT 'infinity'
) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  INSERT INTO gold.feature_bucket (
    bucket_ts, source, entity, metric, value, hora_brt, dow, tem_jogo, available_at)
  SELECT s.bucket_ts, s.source, s.entity, s.metric, s.value,
         extract(hour FROM s.bucket_ts AT TIME ZONE 'America/Sao_Paulo')::smallint,
         extract(dow  FROM s.bucket_ts AT TIME ZONE 'America/Sao_Paulo')::smallint,
         EXISTS (
           SELECT 1 FROM gold.live_event_window w
            WHERE s.bucket_ts >= w.ts_start AND s.bucket_ts < w.ts_end
         ),
         s.available_at
    FROM silver.signal_bucket s
   WHERE s.available_at >= p_from AND s.available_at < p_to
  ON CONFLICT (bucket_ts, source, entity, metric) DO UPDATE
     SET value = EXCLUDED.value, tem_jogo = EXCLUDED.tem_jogo,
         available_at = EXCLUDED.available_at;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

COMMENT ON FUNCTION gold.build_feature_bucket(timestamptz, timestamptz) IS
  'Unica build_* de gold que vale a pena janelar: silver.signal_bucket e a '
  'origem grande (~4,9 M linhas). live_event_window e incident_window '
  'continuam de tabela inteira -- ver cabecalho desta migration';

-- 006_silver.sql indexou available_at em signal_point e session_event, mas nao
-- em signal_bucket -- lacuna que nao doia enquanto o unico leitor era o
-- rebuild completo (varria a tabela inteira de qualquer jeito). O worker
-- incremental faz uma consulta por available_at A CADA CICLO; sem indice, cada
-- uma seria sequential scan nas ~4,9 M linhas.
CREATE INDEX signal_bucket_disponivel ON silver.signal_bucket (available_at);

-- --------------------------------------------------------------------------- #
-- Orquestracao: uma chamada = um ciclo = uma transacao = um commit atomico
-- de dado + watermark + log de execucao
-- --------------------------------------------------------------------------- #

-- Proxima fronteira de lsn a processar, limitada por p_batch_size ENTRADAS DO
-- LOG (nao linhas de silver). O teto existe para dar um limite de tempo/memoria
-- por chamada -- sem ele, o primeiro ciclo depois de o worker ficar parado
-- tentaria processar todo o backlog de uma vez.
CREATE FUNCTION etl.proxima_faixa_lsn(p_from_lsn bigint, p_batch_size int)
RETURNS bigint
LANGUAGE sql STABLE AS $$
  SELECT max(lsn) FROM (
    SELECT lsn FROM bronze.change_log
     WHERE lsn > p_from_lsn
     ORDER BY lsn
     LIMIT p_batch_size
  ) faixa;
$$;

COMMENT ON FUNCTION etl.proxima_faixa_lsn(bigint, int) IS
  'NULL quando nao ha backlog -- e o sinal que etl.executar_bronze_silver usa '
  'para devolver "sem_pendencia" sem tocar em silver nem no watermark';

CREATE FUNCTION etl.executar_bronze_silver(p_batch_size int DEFAULT 5000)
RETURNS TABLE (status text, linhas bigint, de_lsn bigint, ate_lsn bigint, erro text)
LANGUAGE plpgsql AS $$
DECLARE
  v_from bigint;
  v_to   bigint;
  v_n    bigint;
  v_erro text;
BEGIN
  -- SELECT ... FOR UPDATE: uma segunda chamada concorrente (ex.: retry do
  -- scheduler sobrepondo uma execucao anterior que ainda nao terminou) espera
  -- aqui ate a primeira comitar, em vez de processar a mesma faixa em paralelo.
  -- O ON CONFLICT dos build_* ja protege contra duplicidade de DADO; o lock
  -- evita gastar processamento em duplicidade -- defesa em profundidade.
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
         + silver.build_session_event(v_from, v_to);
  EXCEPTION WHEN OTHERS THEN
    -- Nao propaga: se o RAISE subisse ate o chamador, o INSERT abaixo seria
    -- desfeito junto (a mesma instrucao top-level que falhou reverte tudo que
    -- fez, inclusive o que um handler de excecao escreveu). Devolvendo status
    -- em vez de erro de SQL, a chamada inteira continua sendo uma transacao
    -- que COMMITA -- com o watermark intacto e a falha registrada de verdade.
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

  -- Watermark avanca NO MESMO commit que o dado e o log: se a transacao falhar
  -- antes daqui, nada avanca, e o proximo ciclo repete o lote inteiro do zero.
  UPDATE etl.watermark_bronze_silver
     SET lsn_processado = v_to, atualizado_em = now()
   WHERE id = 1;

  RETURN QUERY SELECT 'sucesso'::text, v_n, v_from, v_to, NULL::text;
END
$$;

COMMENT ON FUNCTION etl.executar_bronze_silver(int) IS
  'Um ciclo do worker bronze->silver. Chamar em loop ate ''sem_pendencia'' '
  'drena o backlog inteiro; chamar uma vez por tick processa so o proximo lote';

CREATE FUNCTION etl.executar_silver_gold(p_janela_max_segundos int DEFAULT 14400)
RETURNS TABLE (status text, linhas bigint, de_ts timestamptz, ate_ts timestamptz, erro text)
LANGUAGE plpgsql AS $$
DECLARE
  v_processado timestamptz;
  v_margem     interval;
  v_from       timestamptz;
  v_to         timestamptz;
  v_n          bigint;
  v_erro       text;
BEGIN
  SELECT available_at_processado, margem_seguranca
    INTO v_processado, v_margem
    FROM etl.watermark_silver_gold WHERE id = 1 FOR UPDATE;

  -- Guarda de configuracao, nao de dado: se p_janela_max_segundos nao for
  -- MAIOR que a margem, o watermark NUNCA avanca -- pior, ele REGRIDE a cada
  -- chamada (ver a conta abaixo), porque a margem e subtraida nas DUAS pontas
  -- do ciclo. Falha alto e imediato aqui, em vez de deixar o worker girar para
  -- tras silenciosamente ate alguem notar que a gold parou de crescer.
  --
  --   progresso por chamada = (v_to - margem) - v_processado
  --                         = LEAST(sim.now(), v_processado + janela) - margem - v_processado
  --   no regime com backlog (sim.now() bem a frente): = janela - margem
  --
  -- janela == margem faria progresso zero (trava, nao regride); exigir ESTRITAMENTE
  -- maior garante progresso positivo de verdade, nao so "nao regride".
  IF p_janela_max_segundos <= extract(epoch FROM v_margem) THEN
    RAISE EXCEPTION
      'etl.executar_silver_gold: p_janela_max_segundos (% s) precisa ser MAIOR '
      'que margem_seguranca (%, = % s), senao o watermark nao avanca',
      p_janela_max_segundos, v_margem, extract(epoch FROM v_margem);
  END IF;

  -- Reabre a margem de proposito (watermark temporal != sequencial: ver
  -- comentario da tabela) -- por isso v_from usa v_processado - margem. Mas o
  -- TETO de quanto avancar (p_janela_max_segundos) e medido a partir de
  -- v_processado, NAO de v_from: ancorar no v_from (ja reduzido pela margem)
  -- faria cada chamada subtrair a margem DUAS vezes por ciclo (uma no inicio
  -- da janela, outra no novo watermark), que e exatamente a regressao que a
  -- guarda acima impede de passar despercebida.
  v_from := v_processado - v_margem;
  v_to   := LEAST(sim.now(), v_processado + make_interval(secs => p_janela_max_segundos));

  IF v_to <= v_from THEN
    RETURN QUERY SELECT 'sem_pendencia'::text, 0::bigint, v_from, v_from, NULL::text;
    RETURN;
  END IF;

  BEGIN
    -- live_event_window e incident_window: tabela inteira (ver cabecalho).
    -- feature_bucket: janelado. A ordem importa -- feature_bucket le
    -- live_event_window para resolver tem_jogo, igual em gold.rebuild_tudo().
    v_n := gold.build_live_event_window()
         + gold.build_incident_window()
         + gold.build_feature_bucket(v_from, v_to);
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
  VALUES ('silver_gold', 'sucesso', now(), v_n,
          v_processado::text, (v_to - v_margem)::text);

  -- Nunca avanca para v_to puro -- sempre v_to - margem, deixando a faixa
  -- final como "zona sempre reaberta" para o proximo ciclo.
  UPDATE etl.watermark_silver_gold
     SET available_at_processado = v_to - v_margem, atualizado_em = now()
   WHERE id = 1;

  RETURN QUERY SELECT 'sucesso'::text, v_n, v_from, v_to, NULL::text;
END
$$;

COMMENT ON FUNCTION etl.executar_silver_gold(int) IS
  'Um ciclo do worker silver->gold. p_janela_max_segundos PRECISA ser maior '
  'que margem_seguranca (a funcao falha alto se nao for -- ver o corpo). Com '
  'sim.speed > 0, esta funcao raramente devolve ''sem_pendencia'' de verdade: '
  'sim.now() anda sozinho, entao o chamador NAO deve reavaliar sim.now() a '
  'cada iteracao de um loop de dreno -- congelar um alvo antes do loop (ver '
  '_drenar_silver_gold em argus_processing) e o que evita girar para sempre';
