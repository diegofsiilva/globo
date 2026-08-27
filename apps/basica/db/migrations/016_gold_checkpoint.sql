-- 016_gold_checkpoint.sql
--
-- Publica uma versao identificavel da Gold ao fim de cada ciclo silver->gold.
-- A linha nasce na MESMA transacao que atualiza as tabelas Gold, registra a
-- execucao do ETL e avanca o watermark. Por MVCC, um leitor ve o estado anterior
-- sem o checkpoint novo ou o estado novo com o checkpoint; nunca ve metade de
-- cada versao.

CREATE TABLE etl.gold_checkpoint (
  checkpoint_id   bigserial   PRIMARY KEY,
  etl_execution_id uuid       NOT NULL UNIQUE
                                REFERENCES etl.execucoes (execucao_id),
  sim_run_id      bigint      REFERENCES sim.run (run_id),
  ready_through   timestamptz NOT NULL,
  source_lsn      bigint      NOT NULL CHECK (source_lsn >= 0),
  created_at      timestamptz NOT NULL DEFAULT now(),
  row_counts      jsonb       NOT NULL DEFAULT '{}'::jsonb
                              CHECK (jsonb_typeof(row_counts) = 'object')
);

COMMENT ON TABLE etl.gold_checkpoint IS
  'Log append-only das versoes publicadas da Gold. Uma linha so existe quando '
  'o ciclo silver->gold, seu registro em etl.execucoes e o watermark foram '
  'confirmados na mesma transacao';
COMMENT ON COLUMN etl.gold_checkpoint.ready_through IS
  'Limite superior de available_at processado neste ciclo. Nao e o watermark '
  'reaberto: a margem continua sendo responsabilidade de '
  'etl.watermark_silver_gold';
COMMENT ON COLUMN etl.gold_checkpoint.source_lsn IS
  'Watermark bronze->silver observado antes do build da Gold. E conservador: '
  'mudancas concorrentes posteriores pertencem a outro checkpoint';
COMMENT ON COLUMN etl.gold_checkpoint.created_at IS
  'Tempo real de commit da infraestrutura, separado do tempo virtual em '
  'ready_through';
COMMENT ON COLUMN etl.gold_checkpoint.row_counts IS
  'Contagens por produto do build e total da execucao, para auditoria barata';

CREATE INDEX gold_checkpoint_ready_through
  ON etl.gold_checkpoint (ready_through DESC, checkpoint_id DESC);

-- Imutabilidade e uma garantia do banco, nao apenas uma convencao do worker.
-- TRUNCATE administrativo continua possivel (e usado pela suite de testes), mas
-- uma linha individual publicada nao pode ser reescrita nem removida.
CREATE FUNCTION etl.impedir_mutacao_gold_checkpoint() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION
    'etl.gold_checkpoint e append-only: checkpoint % nao pode sofrer %',
    OLD.checkpoint_id, TG_OP;
END
$$;

CREATE TRIGGER gold_checkpoint_append_only
BEFORE UPDATE OR DELETE ON etl.gold_checkpoint
FOR EACH ROW EXECUTE FUNCTION etl.impedir_mutacao_gold_checkpoint();

-- Mantem a assinatura publica da migration 015. O Python continua recebendo
-- status, linhas, de_ts, ate_ts e erro; a publicacao do checkpoint e um efeito
-- transacional interno do ciclo e nao exige mudanca em argus_processing.etl.
CREATE OR REPLACE FUNCTION etl.executar_silver_gold(
  p_janela_max_segundos int DEFAULT 14400
)
RETURNS TABLE (
  status text,
  linhas bigint,
  de_ts timestamptz,
  ate_ts timestamptz,
  erro text
)
LANGUAGE plpgsql AS $$
DECLARE
  v_processado       timestamptz;
  v_margem           interval;
  v_from             timestamptz;
  v_to               timestamptz;
  v_live_n           bigint;
  v_incident_n       bigint;
  v_feature_n        bigint;
  v_n                bigint;
  v_erro             text;
  v_execucao_id      uuid;
  v_sim_run_id       bigint;
  v_source_lsn       bigint;
BEGIN
  SELECT available_at_processado, margem_seguranca
    INTO v_processado, v_margem
    FROM etl.watermark_silver_gold
   WHERE id = 1
     FOR UPDATE;

  IF p_janela_max_segundos <= extract(epoch FROM v_margem) THEN
    RAISE EXCEPTION
      'etl.executar_silver_gold: p_janela_max_segundos (% s) precisa ser MAIOR '
      'que margem_seguranca (%, = % s), senao o watermark nao avanca',
      p_janela_max_segundos, v_margem, extract(epoch FROM v_margem);
  END IF;

  v_from := v_processado - v_margem;
  v_to   := LEAST(
    sim.now(),
    v_processado + make_interval(secs => p_janela_max_segundos)
  );

  IF v_to <= v_from THEN
    RETURN QUERY
      SELECT 'sem_pendencia'::text, 0::bigint, v_from, v_from, NULL::text;
    RETURN;
  END IF;

  -- Capturado antes do build: se bronze->silver avancar concorrentemente, este
  -- checkpoint declara somente o LSN que ja era conhecido ao iniciar o ciclo.
  SELECT lsn_processado
    INTO v_source_lsn
    FROM etl.watermark_bronze_silver
   WHERE id = 1;

  BEGIN
    -- A ordem e parte do contrato: feature_bucket usa live_event_window para
    -- calcular tem_jogo. As contagens separadas alimentam row_counts.
    v_live_n     := gold.build_live_event_window();
    v_incident_n := gold.build_incident_window();
    v_feature_n  := gold.build_feature_bucket(v_from, v_to);
    v_n          := v_live_n + v_incident_n + v_feature_n;
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
  VALUES (
    'silver_gold',
    'sucesso',
    now(),
    v_n,
    v_processado::text,
    (v_to - v_margem)::text
  )
  RETURNING execucao_id INTO v_execucao_id;

  UPDATE etl.watermark_silver_gold
     SET available_at_processado = v_to - v_margem,
         atualizado_em = now(),
         execucao_id = v_execucao_id
   WHERE id = 1;

  SELECT sr.run_id
    INTO v_sim_run_id
    FROM sim.run AS sr
   WHERE sr.status IN ('running', 'paused')
   ORDER BY sr.run_id DESC
   LIMIT 1;

  INSERT INTO etl.gold_checkpoint (
    etl_execution_id,
    sim_run_id,
    ready_through,
    source_lsn,
    row_counts
  )
  VALUES (
    v_execucao_id,
    v_sim_run_id,
    v_to,
    v_source_lsn,
    jsonb_build_object(
      'live_event_window', v_live_n,
      'incident_window', v_incident_n,
      'feature_bucket', v_feature_n,
      'total', v_n
    )
  );

  RETURN QUERY SELECT 'sucesso'::text, v_n, v_from, v_to, NULL::text;
END
$$;

COMMENT ON FUNCTION etl.executar_silver_gold(int) IS
  'Um ciclo atomico do worker silver->gold. Em sucesso atualiza Gold, registra '
  'etl.execucoes, avanca o watermark e publica etl.gold_checkpoint na mesma '
  'transacao. p_janela_max_segundos precisa ser maior que a margem de seguranca';
