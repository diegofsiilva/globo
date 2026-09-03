-- 027_dados_operacionais_e_revisao.sql
--
-- Fontes que nasceram depois do dump original e o estado de revisao usado
-- pelo radar. As seis tabelas de fonte ficam na bronze para preservar o
-- contrato CDC: o worker grava primeiro o change_log e depois faz o MERGE na
-- corrente. Elas nao entram automaticamente na silver.signal_point -- em
-- especial cdn_vod_shadow e uma referencia de calibracao offline.
--
-- finding_review e finding_status_log sao diferentes: nao sao uma fonte bruta,
-- mas o dossie editavel da tela /casos. Por isso ficam na gold e se relacionam
-- com o identificador numerico que detect.anomaly ja expoe desde a migration
-- 019.

-- --------------------------------------------------------------------------- #
-- Ajustes em tabelas existentes
-- --------------------------------------------------------------------------- #

-- O agregado por dispositivo e a granularidade que permite separar erros de
-- usuarios reais de erros produzidos por bot/crawler. A contagem segue o tipo
-- de `errors`; NULL significa que a fonte ainda nao informou a parcela.
ALTER TABLE bronze.device_hourly
  ADD COLUMN errors_bot bigint;

COMMENT ON COLUMN bronze.device_hourly.errors_bot IS
  'Quantidade de erros atribuida a trafego automatizado (bot/crawler); NULL '
  'quando a fonte nao informa a parcela';

-- O SDE e a identidade estavel do evento esportivo. Nao ha FK para a tabela de
-- reconciliacao: EPG e Jarvis podem chegar fora de ordem no CDC.
ALTER TABLE bronze.live_event
  ADD COLUMN sde_id text;

CREATE INDEX ix_live_event_sde
  ON bronze.live_event (sde_id)
  WHERE sde_id IS NOT NULL;

COMMENT ON COLUMN bronze.live_event.sde_id IS
  'Identificador do SDE no supergraph do Jarvis; usado para reconciliar o '
  'evento de EPG com nomes de time e competicao';

-- --------------------------------------------------------------------------- #
-- Novas fontes de dados (bronze)
-- --------------------------------------------------------------------------- #

CREATE TABLE bronze.app_error (
  error_id       text        NOT NULL,
  occurred_at    bigint      NOT NULL,
  source         text,
  session_id     text,
  device_id      text,
  app_target     text,
  app_version    text,
  model_id       text,
  version_id     text,
  error_name     text,
  error_message  text,
  error_stack    text,
  error_count    bigint,
  _extra         jsonb       NOT NULL DEFAULT '{}',
  _lsn           bigint      NOT NULL,
  _op            char(1)     NOT NULL,
  _captured_at   timestamptz NOT NULL,
  PRIMARY KEY (error_id)
);

COMMENT ON TABLE bronze.app_error IS
  'Erros pre-player do app Globoplay em smart TV e app, recebidos do New Relic';
COMMENT ON COLUMN bronze.app_error.occurred_at IS
  'Instante do erro em epoch de milissegundos UTC';
COMMENT ON COLUMN bronze.app_error.error_count IS
  'Quantidade agregada pelo New Relic quando o registro nao representa um '
  'erro individual';
COMMENT ON COLUMN bronze.app_error._extra IS
  'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE INDEX app_error_dispositivo_tempo
  ON bronze.app_error (device_id, occurred_at DESC)
  WHERE device_id IS NOT NULL;
CREATE INDEX app_error_versao_tempo
  ON bronze.app_error (version_id, occurred_at DESC)
  WHERE version_id IS NOT NULL;

CREATE TABLE bronze.app_error_model (
  model_id          text        NOT NULL,
  model_name        text,
  manufacturer      text,
  device_os         text,
  device_os_version text,
  _extra            jsonb       NOT NULL DEFAULT '{}',
  _lsn              bigint      NOT NULL,
  _op               char(1)     NOT NULL,
  _captured_at      timestamptz NOT NULL,
  PRIMARY KEY (model_id)
);

COMMENT ON TABLE bronze.app_error_model IS
  'Catalogo de modelos de dispositivo usados para contextualizar app_error';
COMMENT ON COLUMN bronze.app_error_model._extra IS
  'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.app_error_version (
  version_id      text        NOT NULL,
  app_target      text,
  app_version     text,
  release_channel text,
  released_at     bigint,
  _extra          jsonb       NOT NULL DEFAULT '{}',
  _lsn            bigint      NOT NULL,
  _op             char(1)     NOT NULL,
  _captured_at    timestamptz NOT NULL,
  PRIMARY KEY (version_id)
);

COMMENT ON TABLE bronze.app_error_version IS
  'Catalogo de versoes do app usadas para contextualizar app_error';
COMMENT ON COLUMN bronze.app_error_version.released_at IS
  'Instante de publicacao em epoch de milissegundos UTC, quando disponivel';
COMMENT ON COLUMN bronze.app_error_version._extra IS
  'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.cdn_vod_shadow (
  bucket_ts     bigint      NOT NULL,
  cdn           text        NOT NULL,
  pop           text        NOT NULL,
  status_2xx    bigint,
  status_4xx    bigint,
  status_5xx    bigint,
  requests_total bigint,
  _extra        jsonb       NOT NULL DEFAULT '{}',
  _lsn          bigint      NOT NULL,
  _op           char(1)     NOT NULL,
  _captured_at  timestamptz NOT NULL,
  PRIMARY KEY (bucket_ts, cdn, pop),
  CHECK (status_2xx IS NULL OR status_2xx >= 0),
  CHECK (status_4xx IS NULL OR status_4xx >= 0),
  CHECK (status_5xx IS NULL OR status_5xx >= 0),
  CHECK (requests_total IS NULL OR requests_total >= 0)
);

COMMENT ON TABLE bronze.cdn_vod_shadow IS
  'Metricas cruas 2xx/4xx/5xx da borda VOD; tabela sombra fora do signal_point '
  'para calibracao offline de piso e ratio';
COMMENT ON COLUMN bronze.cdn_vod_shadow.bucket_ts IS
  'Inicio do bucket em epoch de milissegundos UTC';
COMMENT ON COLUMN bronze.cdn_vod_shadow._extra IS
  'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE INDEX cdn_vod_shadow_cdn_tempo
  ON bronze.cdn_vod_shadow (cdn, bucket_ts DESC);
CREATE INDEX cdn_vod_shadow_pop_tempo
  ON bronze.cdn_vod_shadow (pop, bucket_ts DESC);

CREATE TABLE bronze.isp_pop_daily (
  day            date        NOT NULL,
  asn            bigint      NOT NULL,
  isp            text,
  pop            text        NOT NULL,
  sessions       bigint,
  errors         bigint,
  requests       bigint,
  bytes          bigint,
  _extra         jsonb       NOT NULL DEFAULT '{}',
  _lsn           bigint      NOT NULL,
  _op            char(1)     NOT NULL,
  _captured_at   timestamptz NOT NULL,
  PRIMARY KEY (day, asn, pop),
  CHECK (sessions IS NULL OR sessions >= 0),
  CHECK (errors IS NULL OR errors >= 0),
  CHECK (requests IS NULL OR requests >= 0),
  CHECK (bytes IS NULL OR bytes >= 0)
);

COMMENT ON TABLE bronze.isp_pop_daily IS
  'Cruzamento diario de ISP e PoP; ASN e a chave estavel, nao o nome do ISP';
COMMENT ON COLUMN bronze.isp_pop_daily.asn IS
  'Autonomous System Number usado como identidade do provedor';
COMMENT ON COLUMN bronze.isp_pop_daily.isp IS
  'Nome recebido da fonte, apenas descritivo: pode variar entre capturas';
COMMENT ON COLUMN bronze.isp_pop_daily._extra IS
  'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE INDEX isp_pop_daily_asn_tempo
  ON bronze.isp_pop_daily (asn, pop, day DESC);
CREATE INDEX isp_pop_daily_pop_tempo
  ON bronze.isp_pop_daily (pop, day DESC);

CREATE TABLE bronze.live_event_sde (
  sde_id            text        NOT NULL,
  epg_event_key     text,
  epg_event_name    text,
  epg_competition   text,
  epg_team_home     text,
  epg_team_away     text,
  jarvis_event_name text,
  jarvis_competition text,
  jarvis_team_home  text,
  jarvis_team_away  text,
  event_start       bigint,
  event_end         bigint,
  match_status      text,
  reconciled_at     timestamptz,
  _extra            jsonb       NOT NULL DEFAULT '{}',
  _lsn              bigint      NOT NULL,
  _op               char(1)     NOT NULL,
  _captured_at      timestamptz NOT NULL,
  PRIMARY KEY (sde_id)
);

COMMENT ON TABLE bronze.live_event_sde IS
  'Reconcilia EPG com o supergraph Jarvis por sde_id para auditar evento '
  'esportivo, times e competicao';
COMMENT ON COLUMN bronze.live_event_sde.sde_id IS
  'Identidade do evento no SDE/supergraph; corresponde a live_event.sde_id';
COMMENT ON COLUMN bronze.live_event_sde.match_status IS
  'Resultado verbatim da reconciliacao; a origem pode adicionar estados sem '
  'exigir migration';
COMMENT ON COLUMN bronze.live_event_sde._extra IS
  'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE INDEX live_event_sde_epg_event
  ON bronze.live_event_sde (epg_event_key)
  WHERE epg_event_key IS NOT NULL;

-- --------------------------------------------------------------------------- #
-- Dossie de revisao do radar (gold)
-- --------------------------------------------------------------------------- #

CREATE TABLE gold.finding_review (
  finding_id     bigint      NOT NULL
    REFERENCES detect.anomaly (anomaly_id),
  status         text        NOT NULL DEFAULT 'new'
    CHECK (status IN ('new', 'resolved', 'regressed', 'chronic')),
  root_cause     text,
  ticket         text,
  incident       text,
  affected_users bigint
    CHECK (affected_users IS NULL OR affected_users >= 0),
  notes          text,
  reviewed_by    text,
  created_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at     timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (finding_id)
);

COMMENT ON TABLE gold.finding_review IS
  'Triagem e dossie editavel de um achado do radar, mantido pela pagina /casos';
COMMENT ON COLUMN gold.finding_review.status IS
  'Estado operacional do caso: new, resolved, regressed ou chronic';
COMMENT ON COLUMN gold.finding_review.root_cause IS
  'Causa raiz registrada na revisao humana, nao uma inferencia automatica';
COMMENT ON COLUMN gold.finding_review.affected_users IS
  'Quantidade estimada de usuarios afetados na janela do achado';

CREATE INDEX finding_review_status
  ON gold.finding_review (status, updated_at DESC);

CREATE TABLE gold.finding_status_log (
  status_log_id bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  finding_id    bigint      NOT NULL
    REFERENCES gold.finding_review (finding_id) ON DELETE CASCADE,
  from_status   text
    CHECK (from_status IS NULL OR from_status IN ('new', 'resolved', 'regressed', 'chronic')),
  to_status     text        NOT NULL
    CHECK (to_status IN ('new', 'resolved', 'regressed', 'chronic')),
  changed_at    timestamptz NOT NULL DEFAULT clock_timestamp(),
  changed_by    text,
  reason        text,
  CHECK (from_status IS NULL OR from_status <> to_status)
);

COMMENT ON TABLE gold.finding_status_log IS
  'Historico append-only das viradas de estado de um achado, uma linha por '
  'transicao'; new, resolved, regressed e chronic';
COMMENT ON COLUMN gold.finding_status_log.from_status IS
  'Estado anterior; NULL identifica a criacao do caso';
COMMENT ON COLUMN gold.finding_status_log.to_status IS
  'Novo estado aplicado pela revisao';

CREATE INDEX finding_status_log_finding_tempo
  ON gold.finding_status_log (finding_id, changed_at DESC, status_log_id DESC);
