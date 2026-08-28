-- 024_deploy_event_available_at.sql
--
-- Corrige o `available_at` de gold.deploy_event.
--
-- A 023 gravou `e._captured_at` -- o relogio REAL de quando o loader escreveu
-- a linha (~21/08/2026). A view gold.v_deploy_event corta por
-- `available_at <= sim.now()`, e o relogio simulado esta em 05/08/2026, entao
-- TODA linha era descartada: /api/v1/changes e as faixas de deploy da tela
-- Timeline respondiam 200 com lista vazia, em qualquer janela pedida.
--
-- A convencao das demais etapas (010_merge_e_etl.sql) e derivar o
-- `available_at` do tempo do proprio evento mais a latencia modelada da fonte,
-- e nao do instante de captura do pipeline:
--
--   available_at = silver.ts_from_ms(b.ts) + silver.latency_of(b.source)
--
-- Esta migration alinha deploy_event a essa convencao. `silver.latency_of`
-- faz COALESCE para interval '0' em fonte desconhecida, entao 'tsuru' e
-- seguro mesmo sem linha em silver.source_latency.
--
-- O `_captured_at` continua sendo o dado certo para um pipeline que observa
-- eventos ao vivo; ele so nao serve para carga historica em massa, onde o
-- instante de captura nao tem relacao com a linha do tempo simulada.

CREATE OR REPLACE FUNCTION gold.build_deploy_event() RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  INSERT INTO gold.deploy_event (
    event_id, kind, target_type, target_value, owner,
    started_at, ended_at, duration_ms, error, available_at)
  SELECT e.uniqueid, e.kind, e.target_type, e.target_value, e.owner,
         silver.ts_from_ms(e.start_time_ms),
         silver.ts_from_ms(e.end_time_ms),
         e.duration_ms, e.error,
         silver.ts_from_ms(e.start_time_ms) + silver.latency_of('tsuru')
    FROM bronze.tsuru_event e
   WHERE e.start_time_ms IS NOT NULL AND e.uniqueid IS NOT NULL
  ON CONFLICT (event_id) DO UPDATE
     SET ended_at = EXCLUDED.ended_at, duration_ms = EXCLUDED.duration_ms,
         error = EXCLUDED.error, available_at = EXCLUDED.available_at;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

COMMENT ON COLUMN gold.deploy_event.available_at IS
  'tempo do evento (start_time_ms) + latencia modelada da fonte, igual as '
  'demais etapas de gold -- e o corte que impede a view mostrar um deploy '
  'antes do momento em que ele seria sabido na linha do tempo simulada';

-- Reprocessa: o ON CONFLICT acima reescreve o available_at das linhas que a
-- 023 ja tinha inserido com o valor errado.
SELECT gold.build_deploy_event();
