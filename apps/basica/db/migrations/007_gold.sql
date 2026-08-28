-- 007_gold.sql
--
-- Features e janelas. E a UNICA camada que as telas consultam (§3, corolario
-- 1): isso desacopla o desempenho do dashboard do tamanho de prom_point, e e o
-- que faz a classe da instancia RDS deixar de ser um bloqueio de projeto.

CREATE TABLE gold.feature_bucket (
  bucket_ts    timestamptz NOT NULL,
  source       text        NOT NULL,
  entity       text        NOT NULL,
  metric       text        NOT NULL,
  value        double precision,
  hora_brt     smallint    NOT NULL CHECK (hora_brt BETWEEN 0 AND 23),
  dow          smallint    NOT NULL CHECK (dow BETWEEN 0 AND 6),
  tem_jogo     boolean     NOT NULL DEFAULT false,
  available_at timestamptz NOT NULL,
  PRIMARY KEY (bucket_ts, source, entity, metric)
) PARTITION BY RANGE (bucket_ts);

COMMENT ON TABLE gold.feature_bucket IS
  'Bucket de 15 min alinhado ao signal_bucket da origem';
COMMENT ON COLUMN gold.feature_bucket.hora_brt IS
  'hora em America/Sao_Paulo, nao em UTC: o ciclo circadiano de audiencia segue '
  'o horario de quem assiste';
COMMENT ON COLUMN gold.feature_bucket.tem_jogo IS
  'feature exogena. Popular com EXISTS contra gold.live_event_window, NUNCA com '
  'JOIN -- ha feeds simultaneos e o join duplica o bucket';

DO $$
DECLARE
  dia date := date '2026-07-01';
BEGIN
  WHILE dia < date '2026-09-01' LOOP
    EXECUTE format(
      'CREATE TABLE gold.feature_bucket_p%s PARTITION OF gold.feature_bucket '
      'FOR VALUES FROM (%L) TO (%L)',
      to_char(dia, 'YYYYMMDD'), dia, dia + 1
    );
    dia := dia + 1;
  END LOOP;
END
$$;

CREATE TABLE gold.feature_bucket_default PARTITION OF gold.feature_bucket DEFAULT;

CREATE INDEX feature_bucket_serie ON gold.feature_bucket (source, entity, metric, bucket_ts);
CREATE INDEX feature_bucket_disponivel ON gold.feature_bucket (available_at);

-- --------------------------------------------------------------------------- #
-- Baseline circadiano
-- --------------------------------------------------------------------------- #

CREATE TABLE gold.circadian_state (
  series_key text     NOT NULL,
  hora_brt   smallint NOT NULL CHECK (hora_brt BETWEEN 0 AND 23),
  mean       double precision,
  var        double precision,
  n          integer  NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (series_key, hora_brt)
);

COMMENT ON TABLE gold.circadian_state IS
  'Estado EWMA do baseline, ESTRITAMENTE causal: cada atualizacao so pode ver '
  'buckets cujo available_at ja passou. E o que separa avaliacao de ficcao';

-- --------------------------------------------------------------------------- #
-- Calendario de transmissoes
-- --------------------------------------------------------------------------- #

CREATE TABLE gold.live_event_window (
  event_key   text        NOT NULL,
  tid         integer     NOT NULL,
  ts_start    timestamptz NOT NULL,
  ts_end      timestamptz NOT NULL,
  slug        text,
  channel     text,
  competition text,
  sport       text,
  team_home   text,
  team_away   text,
  event_date  date        NOT NULL,
  first_seen  timestamptz,
  PRIMARY KEY (tid, ts_start)
);

COMMENT ON TABLE gold.live_event_window IS
  'Duas armadilhas no ETL. Primeira: tid 994 e 995 nao sao o mesmo canal em '
  'horarios diferentes -- sao feeds SIMULTANEOS com jogos diferentes, porque a '
  'Globo transmite partidas distintas em pracas distintas no mesmo horario. '
  'Agrupar por ts_start funde dois jogos num so; o correto e agrupar por '
  'event_key. Segunda: slug chega sempre como `globo` (a familia) enquanto a '
  'QoE vem por praca (globo-rj, globo-sp), entao o casamento e LIKE ''globo%'' '
  'tratado como agregado nacional, nunca como praca especifica';
COMMENT ON COLUMN gold.live_event_window.event_key IS
  'identidade do confronto, estavel entre feeds. E por aqui que se agrupa';
COMMENT ON COLUMN gold.live_event_window.event_date IS
  'dia de PROGRAMACAO em BRT, que nao coincide com a data UTC de ts_start numa '
  'transmissao que atravessa a meia-noite';

CREATE INDEX live_event_window_janela ON gold.live_event_window (ts_start, ts_end);
CREATE INDEX live_event_window_chave  ON gold.live_event_window (event_key);

-- --------------------------------------------------------------------------- #
-- Janelas de incidente e casamento com a deteccao
-- --------------------------------------------------------------------------- #

CREATE TABLE gold.incident_window (
  window_id  bigserial PRIMARY KEY,
  ts_start   timestamptz NOT NULL,
  ts_end     timestamptz NOT NULL,
  origem     text        NOT NULL
             CHECK (origem IN ('incidents', 'incident_label', 'detector')),
  ref_id     text,
  verdict    text,
  severity   text,
  provenance text,
  CHECK (ts_end >= ts_start),
  -- A PK e sintetica (bigserial) porque `detector` produz janela sem
  -- identificador da origem. Mas `incidents` e `incident_label` tem: sem esta
  -- unicidade, rodar o ETL duas vezes duplicaria os 501 tickets e os 20
  -- rotulos, e toda metrica de deteccao contra eles passaria a mentir por um
  -- fator de duas vezes.
  UNIQUE (origem, ref_id)
);

COMMENT ON COLUMN gold.incident_window.provenance IS
  'Sete dos vinte rotulos de incident_label sao `detector-derived`: foram '
  'criados olhando a saida do proprio Argus. Avaliar um detector novo contra '
  'eles mede CONCORDANCIA COM O BASELINE, nao acuracia -- um modelo que '
  'encontrasse incidentes reais que o Argus perdeu seria penalizado. A coluna '
  'existe para que a filtragem seja obrigatoria e visivel no schema, e nao uma '
  'lembranca de quem escreve a query';

CREATE INDEX incident_window_janela ON gold.incident_window (ts_start, ts_end);

CREATE TABLE gold.detection_match (
  window_id    bigint  NOT NULL REFERENCES gold.incident_window ON DELETE CASCADE,
  run_id       bigint  NOT NULL,
  detection_id bigint  NOT NULL,
  lead_time_s  integer,
  matched      boolean NOT NULL,
  PRIMARY KEY (window_id, run_id, detection_id)
);

COMMENT ON COLUMN gold.detection_match.lead_time_s IS
  'negativo = o detector viu antes de o ticket ser aberto, que e exatamente o '
  'caso que o projeto quer maximizar';
