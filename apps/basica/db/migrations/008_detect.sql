-- 008_detect.sql
--
-- Saida do detector. Tabelas criadas agora, SEM logica que as popule (decisao 7
-- do plano: processamento e deteccao seguem embrionarios).
--
-- O `run_id` entra desde ja porque e o que permite rodar dois detectores sobre
-- a mesma janela e comparar -- e retrofitar identificador de execucao depois,
-- quando ja houver saida gravada sem ele, e caro.

CREATE TABLE detect.run (
  run_id      bigserial PRIMARY KEY,
  sim_run_id  bigint REFERENCES sim.run ON DELETE SET NULL,
  detector    text  NOT NULL,
  params      jsonb NOT NULL DEFAULT '{}',
  started_at  timestamptz,
  finished_at timestamptz
);

COMMENT ON COLUMN detect.run.params IS
  'hiperparametros da execucao. Comparar dois runs sem saber com que parametros '
  'rodaram nao responde nada';

CREATE TABLE detect.anomaly (
  run_id    bigint      NOT NULL REFERENCES detect.run ON DELETE CASCADE,
  bucket_ts timestamptz NOT NULL,
  source    text        NOT NULL,
  entity    text        NOT NULL,
  metric    text        NOT NULL,
  z         double precision,
  score     double precision,
  n_sources smallint,
  PRIMARY KEY (run_id, bucket_ts, source, entity, metric)
);

COMMENT ON COLUMN detect.anomaly.n_sources IS
  'quantas fontes independentes concordam com o desvio neste bucket: e o fator '
  'que separa incidente de ruido de uma fonte so';

CREATE INDEX anomaly_janela ON detect.anomaly (run_id, bucket_ts);
