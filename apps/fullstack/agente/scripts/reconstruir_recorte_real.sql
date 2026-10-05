-- Reconstroi fatos de silver.analysis_fact_version a partir de bronze.signal_bucket
-- e registra um checkpoint para o piloto de hipoteses com IA.
--
-- USO (PostgreSQL local do projeto, nunca publicado):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--     -v entidade='br1|playback.video.globo.com' \
--     -v janela_inicio='2026-08-18 00:00+00' \
--     -v janela_fim='2026-08-31 00:00+00' \
--     -v presente='2026-08-21 08:00+00' \
--     -f scripts/reconstruir_recorte_real.sql
--
-- POR QUE EXISTE: a funcao oficial silver.build_analysis_fact_version le
-- bronze.change_log, e o banco local carregado a partir do dump nao tem
-- change_log para signal_bucket. Esta reconstrucao copia exatamente a expressao
-- que a funcao oficial usa para o ramo signal_bucket, com a versao LSN real da
-- bronze (_lsn), e nao cria nada alem de facts + um checkpoint marcado como
-- reconstruido em row_counts. Nao e um replay do CDC.
--
-- Idempotente: fatos repetidos sao ignorados (ON CONFLICT). Cada execucao
-- cria um checkpoint novo; o recorte usado no relatorio e o checkpoint_id que
-- a execucao imprime.

BEGIN;

INSERT INTO silver.analysis_fact_version
  (fact_key, version_lsn, kind, event_start, event_end, available_at,
   source, entity, metric, dimension_type, dimension_value, value,
   sample_size, attributes, is_deleted)
SELECT silver.analysis_fact_key('signal_bucket', b.bts::text, b.source, b.entity, b.metric),
       b._lsn, 'metric', silver.ts_from_ms(b.bts), NULL,
       silver.ts_from_ms(b.bts) + silver.latency_of(b.source),
       b.source, b.entity, b.metric, NULL, NULL, b.value, NULL,
       '{}'::jsonb, false
  FROM bronze.signal_bucket b
 WHERE b.entity = :'entidade'
   AND b.bts BETWEEN extract(epoch from (:'janela_inicio')::timestamptz) * 1000
                 AND extract(epoch from (:'janela_fim')::timestamptz) * 1000
ON CONFLICT DO NOTHING;

WITH n AS (
  SELECT count(*) AS c, max(_lsn) AS m
    FROM bronze.signal_bucket b
   WHERE b.entity = :'entidade'
     AND b.bts BETWEEN extract(epoch from (:'janela_inicio')::timestamptz) * 1000
                   AND extract(epoch from (:'janela_fim')::timestamptz) * 1000
),
e AS (
  INSERT INTO etl.execucoes (worker, status, finalizado_em, linhas_processadas)
  SELECT 'silver_gold', 'sucesso', now(), c FROM n
  RETURNING execucao_id
)
INSERT INTO etl.gold_checkpoint (etl_execution_id, sim_run_id, ready_through, source_lsn, row_counts)
SELECT e.execucao_id, NULL, (:'presente')::timestamptz, n.m,
       jsonb_build_object('origem', 'reconstruido_de_bronze_signal_bucket',
                          'entidade', :'entidade',
                          'fatos', n.c,
                          'recorte_escolhido_por', 'inspecao_manual_da_serie_bruta')
  FROM e, n
RETURNING checkpoint_id, ready_through, source_lsn;

COMMIT;
