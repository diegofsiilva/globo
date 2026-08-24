-- 006_silver.sql
--
-- Canonicalizacao de tipo e tempo, e o carimbo de `available_at`.
--
-- SEM re-normalizacao (decisao 6 do plano). `signal_point` e `signal_bucket`
-- chegam prontos da origem: a Globo ja roda o build_signal_db.py em producao e
-- reimplementa-lo aqui seria refazer, pior, trabalho que ja esta feito. A
-- silver faz quatro coisas, e so essas quatro:
--
--   1. bigint epoch_ms -> timestamptz. Todo timestamp do dataset e milissegundo
--      UTC. Nao e segundo, nao e ISO, nao e horario de Brasilia.
--   2. As excecoes em texto ISO-8601 -> timestamptz (signal_meta.last_run_at,
--      cdn_entity_tier.updated_at, investigation_feedback.investigated_at e as
--      colunas das tabelas *_run legadas).
--   3. tags text -> jsonb, TOLERANDO falha de parse.
--   4. Carimba available_at -- e o que faz o replay ser honesto.

-- --------------------------------------------------------------------------- #
-- Conversores tolerantes
-- --------------------------------------------------------------------------- #

CREATE FUNCTION silver.ts_from_ms(ms bigint) RETURNS timestamptz
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT to_timestamp(ms / 1000.0);
$$;

COMMENT ON FUNCTION silver.ts_from_ms(bigint) IS
  'epoch em MILISSEGUNDOS. Dividir por 1000 e a conversao inteira -- tratar o '
  'numero como segundos joga o dado para o ano 58000 sem dar erro';

-- Devolve NULL em vez de estourar. `tags` e JSON na maioria das fontes, mas
-- youbora_player_live manda a string literal `live`, e varias mandam NULL.
-- Derrubar o ETL inteiro por causa de uma fonte mal comportada seria trocar um
-- campo perdido por uma camada perdida.
CREATE FUNCTION silver.jsonb_or_null(raw text) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
BEGIN
  IF raw IS NULL OR btrim(raw) = '' THEN
    RETURN NULL;
  END IF;
  RETURN raw::jsonb;
EXCEPTION WHEN others THEN
  RETURN NULL;
END
$$;

CREATE FUNCTION silver.ts_from_iso(raw text) RETURNS timestamptz
LANGUAGE plpgsql IMMUTABLE PARALLEL SAFE AS $$
BEGIN
  IF raw IS NULL OR btrim(raw) = '' THEN
    RETURN NULL;
  END IF;
  RETURN raw::timestamptz;
EXCEPTION WHEN others THEN
  RETURN NULL;
END
$$;

-- --------------------------------------------------------------------------- #
-- Latencia por fonte
-- --------------------------------------------------------------------------- #

CREATE TABLE silver.source_latency (
  source    text     PRIMARY KEY,
  latency   interval NOT NULL,
  rationale text
);

COMMENT ON TABLE silver.source_latency IS
  'Quanto tempo depois do evento a fonte realmente disponibiliza o dado. '
  'Somado ao ts, vira available_at';

INSERT INTO silver.source_latency (source, latency, rationale) VALUES
  ('youbora',             interval '28 hours',
   'latencia estrutural do batch BigQuery da NPAW'),
  ('youbora_player_live', interval '28 hours',
   'latencia estrutural do batch BigQuery da NPAW'),
  ('npaw',                interval '28 hours',
   'latencia estrutural do batch BigQuery da NPAW'),
  ('newrelic',            interval '1 hour',
   'granularidade mista: 5 min na janela recente, 1 h no historico. Assume o '
   'pior caso, porque prometer o melhor faria o detector "acertar" com dado '
   'que ele nao teria'),
  ('prometheus',          interval '1 minute',
   'quase real-time: e a fonte que sustenta a tela marcada ao vivo'),
  ('rpaas',               interval '15 minutes',
   'bucket de 15 min fechado na origem'),
  ('cloudarmor',          interval '5 minutes', NULL),
  ('apollo',              interval '5 minutes', NULL),
  ('tsuru',               interval '1 minute',  NULL);

-- Fonte que nao esta na tabela tem latencia zero. Existe como funcao para que a
-- regra de fallback fique num lugar so, e nao repetida em cada JOIN do ETL.
CREATE FUNCTION silver.latency_of(p_source text) RETURNS interval
LANGUAGE sql STABLE PARALLEL SAFE AS $$
  SELECT COALESCE(
    (SELECT latency FROM silver.source_latency WHERE source = p_source),
    interval '0'
  );
$$;

-- --------------------------------------------------------------------------- #
-- Serie canonica
-- --------------------------------------------------------------------------- #

CREATE TABLE silver.signal_point (
  ts           timestamptz NOT NULL,
  source       text        NOT NULL,
  entity       text        NOT NULL,
  metric       text        NOT NULL,
  value        double precision,
  tags         jsonb,
  available_at timestamptz NOT NULL,
  _lsn         bigint      NOT NULL,
  PRIMARY KEY (ts, source, entity, metric)
) PARTITION BY RANGE (ts);

COMMENT ON COLUMN silver.signal_point.available_at IS
  'ts + silver.latency_of(source). E o que impede vazamento de futuro: uma '
  'metrica NPAW das 21 h so fica visivel a 01 h do dia seguinte, exatamente '
  'como em producao. Sem isso, qualquer detector "acerta" usando dado que nao '
  'teria em tempo real, e a avaliacao vira ficcao';

CREATE TABLE silver.signal_bucket (
  bucket_ts    timestamptz NOT NULL,
  source       text        NOT NULL,
  entity       text        NOT NULL,
  metric       text        NOT NULL,
  value        double precision,
  available_at timestamptz NOT NULL,
  _lsn         bigint      NOT NULL,
  PRIMARY KEY (bucket_ts, source, entity, metric)
) PARTITION BY RANGE (bucket_ts);

DO $$
DECLARE
  tabela text;
  dia    date;
BEGIN
  FOREACH tabela IN ARRAY ARRAY['signal_point', 'signal_bucket'] LOOP
    dia := date '2026-07-01';
    WHILE dia < date '2026-09-01' LOOP
      EXECUTE format(
        'CREATE TABLE silver.%I PARTITION OF silver.%I FOR VALUES FROM (%L) TO (%L)',
        tabela || '_p' || to_char(dia, 'YYYYMMDD'), tabela, dia, dia + 1
      );
      dia := dia + 1;
    END LOOP;
    EXECUTE format(
      'CREATE TABLE silver.%I PARTITION OF silver.%I DEFAULT', tabela || '_default', tabela
    );
  END LOOP;
END
$$;

-- O detector varre por serie ao longo do tempo, nao por instante. Sem este
-- indice cada leitura de uma serie vira varredura de particao inteira.
CREATE INDEX signal_point_serie ON silver.signal_point (source, entity, metric, ts);
CREATE INDEX signal_point_disponivel ON silver.signal_point (available_at);

-- --------------------------------------------------------------------------- #
-- Grain de sessao
-- --------------------------------------------------------------------------- #

CREATE TABLE silver.session_event (
  ts           timestamptz NOT NULL,
  event_id     text        NOT NULL,
  event_name   text        NOT NULL,
  session_id   text        NOT NULL,
  device_id    text,
  user_id      text,
  app_bucket   text,
  app_env      text,
  app_target   text,
  app_version  text,
  device_manufacturer text,
  device_model text,
  device_os    text,
  route_path   text,
  duration     double precision,
  -- Nulos hoje: nenhum dos seis tipos de evento traz UF ou ISP, e o `request`
  -- carrega apenas x-country-code: BR. As colunas existem tipadas para que o
  -- enriquecimento entre sem migration quando o outro fluxo do Argus for
  -- especificado -- as telas Explorar e Recorte filtram por elas.
  uf           text,
  isp          text,
  payload      jsonb       NOT NULL DEFAULT '{}',
  available_at timestamptz NOT NULL,
  _lsn         bigint      NOT NULL,
  PRIMARY KEY (ts, event_id)
) PARTITION BY RANGE (ts);

DO $$
DECLARE
  mes date := date '2026-05-01';
BEGIN
  WHILE mes < date '2027-01-01' LOOP
    EXECUTE format(
      'CREATE TABLE silver.session_event_p%s PARTITION OF silver.session_event '
      'FOR VALUES FROM (%L) TO (%L)',
      to_char(mes, 'YYYYMM'), mes, mes + interval '1 month'
    );
    mes := mes + interval '1 month';
  END LOOP;
END
$$;

CREATE TABLE silver.session_event_default PARTITION OF silver.session_event DEFAULT;

CREATE INDEX session_event_nome ON silver.session_event (event_name, ts DESC);
CREATE INDEX session_event_disponivel ON silver.session_event (available_at);
