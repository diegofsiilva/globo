-- 014_catalogo_de_fontes.sql
--
-- Evita agregar os 4,9 M buckets toda vez que o dashboard lista as fontes.
--
-- A consulta anterior fazia dois count(DISTINCT ...) e um max(bucket_ts) sobre
-- gold.v_feature_bucket. Medida no RDS do Learner Lab: 47,4 s, acima do timeout
-- de 30 s do API Gateway/Lambda. O catalogo abaixo tem uma linha por serie e
-- continua derivavel da gold; first_available_at preserva o corte de sim.now().

CREATE TABLE gold.source_series (
  source             text        NOT NULL,
  entity             text        NOT NULL,
  metric             text        NOT NULL,
  first_available_at timestamptz NOT NULL,
  PRIMARY KEY (source, entity, metric)
);

COMMENT ON TABLE gold.source_series IS
  'Catalogo derivado de feature_bucket, uma linha por serie. A API usa este '
  'catalogo para listar fontes sem varrer milhoes de buckets';

CREATE INDEX source_series_disponivel
  ON gold.source_series (first_available_at, source);

-- Uma sondagem por fonte encontra o bucket mais recente. available_at entra no
-- INCLUDE para o filtro da view ser resolvido sem visitar o heap na maioria dos
-- casos; (source, bucket_ts DESC) mantem a busca em ordem de recencia.
CREATE INDEX feature_bucket_source_recente
  ON gold.feature_bucket (source, bucket_ts DESC)
  INCLUDE (available_at);

CREATE FUNCTION gold.refresh_source_series() RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE
  n bigint;
BEGIN
  TRUNCATE gold.source_series;

  INSERT INTO gold.source_series (source, entity, metric, first_available_at)
  SELECT source, entity, metric, min(available_at)
    FROM gold.feature_bucket
   GROUP BY source, entity, metric;

  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

COMMENT ON FUNCTION gold.refresh_source_series() IS
  'Reconstroi o catalogo de series a partir de gold.feature_bucket';

CREATE VIEW gold.v_source_series AS
  SELECT source, entity, metric, first_available_at
    FROM gold.source_series
   WHERE first_available_at <= sim.now();

GRANT SELECT ON gold.v_source_series TO argus_reader;

-- O rebuild passa a manter o catalogo junto das outras derivacoes. A ordem
-- importa: source_series depende de feature_bucket ja reconstruida.
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
END
$$;

-- Popula o catalogo ao aplicar a migration num banco que ja recebeu a carga.
SELECT gold.refresh_source_series();
