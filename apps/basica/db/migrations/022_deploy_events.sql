-- 022_deploy_events.sql
--
-- Eventos de deploy/mudanca de plataforma (Tsuru), para responder "o que
-- mudou entre janelas" na tela Comparar (rotas-frontend.md §4.4.4).
--
-- `bronze.tsuru_event` (004_bronze_corrente_argus.sql) e a UNICA fonte deste
-- dataset com eventos discretos de mudanca -- nao ha tabela equivalente para
-- autoscale nem para regra de WAF. `bronze.ca_point` (CloudArmor) e serie de
-- METRICA (ex.: requisicoes bloqueadas), nao log de mudanca de regra. Este
-- gap fica registrado em rotas-frontend.md, nao inventado aqui.
--
-- `kind` vem verbatim da origem (Tsuru classifica deploy, healer, scale etc
-- nesse campo) -- sem whitelist nem traducao, porque nao ha documentacao do
-- dataset que enumere os valores possiveis (skill `dataset-argus`: nao
-- presumir schema de coluna livre sem conferir o dado real).

CREATE TABLE gold.deploy_event (
  event_id     text        PRIMARY KEY,
  kind         text,
  target_type  text,
  target_value text,
  owner        text,
  started_at   timestamptz NOT NULL,
  ended_at     timestamptz,
  duration_ms  bigint,
  error        text,
  available_at timestamptz NOT NULL
);

COMMENT ON TABLE gold.deploy_event IS
  'Eventos de mudanca de plataforma (deploy e afins), de bronze.tsuru_event. '
  'Nao cobre autoscale nem WAF -- o dataset nao tem log de mudanca discreto '
  'para essas duas fontes, so serie de metrica';
COMMENT ON COLUMN gold.deploy_event.kind IS
  'verbatim da origem (Tsuru), sem whitelist -- valores reais nao conferidos';
COMMENT ON COLUMN gold.deploy_event.available_at IS
  'usa bronze.tsuru_event._captured_at: quando o pipeline observou o evento, '
  'nao quando o deploy realmente aconteceu (start_time_ms). E o corte que '
  'impede a view mostrar um deploy antes do momento em que ele seria sabido';

CREATE INDEX deploy_event_janela ON gold.deploy_event (started_at);
CREATE INDEX deploy_event_disponivel ON gold.deploy_event (available_at);

CREATE FUNCTION gold.build_deploy_event() RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
  INSERT INTO gold.deploy_event (
    event_id, kind, target_type, target_value, owner,
    started_at, ended_at, duration_ms, error, available_at)
  SELECT e.uniqueid, e.kind, e.target_type, e.target_value, e.owner,
         silver.ts_from_ms(e.start_time_ms),
         silver.ts_from_ms(e.end_time_ms),
         e.duration_ms, e.error, e._captured_at
    FROM bronze.tsuru_event e
   WHERE e.start_time_ms IS NOT NULL AND e.uniqueid IS NOT NULL
  ON CONFLICT (event_id) DO UPDATE
     SET ended_at = EXCLUDED.ended_at, duration_ms = EXCLUDED.duration_ms,
         error = EXCLUDED.error, available_at = EXCLUDED.available_at;
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

COMMENT ON FUNCTION gold.build_deploy_event() IS
  'Recompute completo, igual as demais etapas de gold.rebuild_tudo() antes da '
  'versao incremental (015_etl_incremental.sql) -- nao ha variante '
  'incremental para deploy_event ainda';

-- O rebuild passa a trazer tambem os eventos de mudanca. Ordem nao importa
-- aqui: build_deploy_event() nao depende de nenhuma outra etapa.
CREATE OR REPLACE FUNCTION gold.rebuild_tudo()
RETURNS TABLE (etapa text, linhas bigint)
LANGUAGE plpgsql AS $$
BEGIN
  etapa := 'silver.signal_point';    linhas := silver.build_signal_point();    RETURN NEXT;
  etapa := 'silver.signal_bucket';   linhas := silver.build_signal_bucket();   RETURN NEXT;
  etapa := 'silver.session_event';   linhas := silver.build_session_event();   RETURN NEXT;
  etapa := 'gold.live_event_window'; linhas := gold.build_live_event_window(); RETURN NEXT;
  etapa := 'gold.incident_window';   linhas := gold.build_incident_window();   RETURN NEXT;
  etapa := 'gold.feature_bucket';    linhas := gold.build_feature_bucket();    RETURN NEXT;
  etapa := 'gold.source_series';     linhas := gold.refresh_source_series();   RETURN NEXT;
  etapa := 'gold.deploy_event';      linhas := gold.build_deploy_event();      RETURN NEXT;
END
$$;

-- Popula ao aplicar a migration num banco que ja recebeu a carga.
SELECT gold.build_deploy_event();

-- --------------------------------------------------------------------------- #
-- View e GRANT (mesmo padrao de 009_views_v.sql)
-- --------------------------------------------------------------------------- #

CREATE VIEW gold.v_deploy_event AS
  SELECT event_id, kind, target_type, target_value, owner,
         started_at, ended_at, duration_ms, error
    FROM gold.deploy_event
   WHERE available_at <= sim.now();

GRANT SELECT ON gold.v_deploy_event TO argus_reader;
