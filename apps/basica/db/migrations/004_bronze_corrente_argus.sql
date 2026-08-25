-- 004_bronze_corrente_argus.sql
--
-- ARQUIVO GERADO por tools/gen_ddl.py -- nao edite a mao.
-- Fonte: data/parquet/_schema.json e _keys.json, ambos extraidos do DDL de
-- argus_dump.sql por tools/etl_dump.py. Para regerar:
--
--     make gen-ddl
--
-- As 33 tabelas do Argus, copiadas com fidelidade da origem. Cada
-- uma ganha quatro colunas de controle:
--
--   _extra jsonb    escape de schema: coluna nova da Globo cai aqui, sem DDL
--   _lsn bigint     posicao no bronze.change_log que produziu esta versao
--   _op char(1)     i | u | d | r (r = linha vinda do snapshot inicial)
--   _captured_at    quando a origem observou a mudanca
--
-- A chave primaria e a identidade natural declarada no dump: e ela que torna o
-- MERGE do worker idempotente sem coluna de controle extra.
--
-- Seis tabelas sao particionadas por RANGE na coluna de tempo, em faixas
-- diarias mais uma DEFAULT. Repare que a coluna de tempo tem nome diferente em
-- cada uma: nao existe um `ts` universal neste dataset, cada tabela herdou o
-- nome da sua fonte.
--
--   ca_point             por ts_ms
--   device_hourly        por hour_ts
--   operation_metrics    por start_ts
--   prom_point           por epoch_ms
--   signal_bucket        por bts
--   signal_point         por ts


CREATE TABLE bronze.signal_point (
  ts            bigint,
  source        text,
  entity        text,
  metric        text,
  value         double precision,
  tags          text,
  _extra        jsonb       NOT NULL DEFAULT '{}',
  _lsn          bigint      NOT NULL,
  _op           char(1)     NOT NULL,
  _captured_at  timestamptz NOT NULL,
  PRIMARY KEY (ts, source, entity, metric)
) PARTITION BY RANGE (ts);
-- 45 particoes diarias cobrindo 20260702..20260815, mais a DEFAULT.
CREATE TABLE bronze.signal_point_p20260702 PARTITION OF bronze.signal_point FOR VALUES FROM (1782950400000) TO (1783036800000);
CREATE TABLE bronze.signal_point_p20260703 PARTITION OF bronze.signal_point FOR VALUES FROM (1783036800000) TO (1783123200000);
CREATE TABLE bronze.signal_point_p20260704 PARTITION OF bronze.signal_point FOR VALUES FROM (1783123200000) TO (1783209600000);
CREATE TABLE bronze.signal_point_p20260705 PARTITION OF bronze.signal_point FOR VALUES FROM (1783209600000) TO (1783296000000);
CREATE TABLE bronze.signal_point_p20260706 PARTITION OF bronze.signal_point FOR VALUES FROM (1783296000000) TO (1783382400000);
CREATE TABLE bronze.signal_point_p20260707 PARTITION OF bronze.signal_point FOR VALUES FROM (1783382400000) TO (1783468800000);
CREATE TABLE bronze.signal_point_p20260708 PARTITION OF bronze.signal_point FOR VALUES FROM (1783468800000) TO (1783555200000);
CREATE TABLE bronze.signal_point_p20260709 PARTITION OF bronze.signal_point FOR VALUES FROM (1783555200000) TO (1783641600000);
CREATE TABLE bronze.signal_point_p20260710 PARTITION OF bronze.signal_point FOR VALUES FROM (1783641600000) TO (1783728000000);
CREATE TABLE bronze.signal_point_p20260711 PARTITION OF bronze.signal_point FOR VALUES FROM (1783728000000) TO (1783814400000);
CREATE TABLE bronze.signal_point_p20260712 PARTITION OF bronze.signal_point FOR VALUES FROM (1783814400000) TO (1783900800000);
CREATE TABLE bronze.signal_point_p20260713 PARTITION OF bronze.signal_point FOR VALUES FROM (1783900800000) TO (1783987200000);
CREATE TABLE bronze.signal_point_p20260714 PARTITION OF bronze.signal_point FOR VALUES FROM (1783987200000) TO (1784073600000);
CREATE TABLE bronze.signal_point_p20260715 PARTITION OF bronze.signal_point FOR VALUES FROM (1784073600000) TO (1784160000000);
CREATE TABLE bronze.signal_point_p20260716 PARTITION OF bronze.signal_point FOR VALUES FROM (1784160000000) TO (1784246400000);
CREATE TABLE bronze.signal_point_p20260717 PARTITION OF bronze.signal_point FOR VALUES FROM (1784246400000) TO (1784332800000);
CREATE TABLE bronze.signal_point_p20260718 PARTITION OF bronze.signal_point FOR VALUES FROM (1784332800000) TO (1784419200000);
CREATE TABLE bronze.signal_point_p20260719 PARTITION OF bronze.signal_point FOR VALUES FROM (1784419200000) TO (1784505600000);
CREATE TABLE bronze.signal_point_p20260720 PARTITION OF bronze.signal_point FOR VALUES FROM (1784505600000) TO (1784592000000);
CREATE TABLE bronze.signal_point_p20260721 PARTITION OF bronze.signal_point FOR VALUES FROM (1784592000000) TO (1784678400000);
CREATE TABLE bronze.signal_point_p20260722 PARTITION OF bronze.signal_point FOR VALUES FROM (1784678400000) TO (1784764800000);
CREATE TABLE bronze.signal_point_p20260723 PARTITION OF bronze.signal_point FOR VALUES FROM (1784764800000) TO (1784851200000);
CREATE TABLE bronze.signal_point_p20260724 PARTITION OF bronze.signal_point FOR VALUES FROM (1784851200000) TO (1784937600000);
CREATE TABLE bronze.signal_point_p20260725 PARTITION OF bronze.signal_point FOR VALUES FROM (1784937600000) TO (1785024000000);
CREATE TABLE bronze.signal_point_p20260726 PARTITION OF bronze.signal_point FOR VALUES FROM (1785024000000) TO (1785110400000);
CREATE TABLE bronze.signal_point_p20260727 PARTITION OF bronze.signal_point FOR VALUES FROM (1785110400000) TO (1785196800000);
CREATE TABLE bronze.signal_point_p20260728 PARTITION OF bronze.signal_point FOR VALUES FROM (1785196800000) TO (1785283200000);
CREATE TABLE bronze.signal_point_p20260729 PARTITION OF bronze.signal_point FOR VALUES FROM (1785283200000) TO (1785369600000);
CREATE TABLE bronze.signal_point_p20260730 PARTITION OF bronze.signal_point FOR VALUES FROM (1785369600000) TO (1785456000000);
CREATE TABLE bronze.signal_point_p20260731 PARTITION OF bronze.signal_point FOR VALUES FROM (1785456000000) TO (1785542400000);
CREATE TABLE bronze.signal_point_p20260801 PARTITION OF bronze.signal_point FOR VALUES FROM (1785542400000) TO (1785628800000);
CREATE TABLE bronze.signal_point_p20260802 PARTITION OF bronze.signal_point FOR VALUES FROM (1785628800000) TO (1785715200000);
CREATE TABLE bronze.signal_point_p20260803 PARTITION OF bronze.signal_point FOR VALUES FROM (1785715200000) TO (1785801600000);
CREATE TABLE bronze.signal_point_p20260804 PARTITION OF bronze.signal_point FOR VALUES FROM (1785801600000) TO (1785888000000);
CREATE TABLE bronze.signal_point_p20260805 PARTITION OF bronze.signal_point FOR VALUES FROM (1785888000000) TO (1785974400000);
CREATE TABLE bronze.signal_point_p20260806 PARTITION OF bronze.signal_point FOR VALUES FROM (1785974400000) TO (1786060800000);
CREATE TABLE bronze.signal_point_p20260807 PARTITION OF bronze.signal_point FOR VALUES FROM (1786060800000) TO (1786147200000);
CREATE TABLE bronze.signal_point_p20260808 PARTITION OF bronze.signal_point FOR VALUES FROM (1786147200000) TO (1786233600000);
CREATE TABLE bronze.signal_point_p20260809 PARTITION OF bronze.signal_point FOR VALUES FROM (1786233600000) TO (1786320000000);
CREATE TABLE bronze.signal_point_p20260810 PARTITION OF bronze.signal_point FOR VALUES FROM (1786320000000) TO (1786406400000);
CREATE TABLE bronze.signal_point_p20260811 PARTITION OF bronze.signal_point FOR VALUES FROM (1786406400000) TO (1786492800000);
CREATE TABLE bronze.signal_point_p20260812 PARTITION OF bronze.signal_point FOR VALUES FROM (1786492800000) TO (1786579200000);
CREATE TABLE bronze.signal_point_p20260813 PARTITION OF bronze.signal_point FOR VALUES FROM (1786579200000) TO (1786665600000);
CREATE TABLE bronze.signal_point_p20260814 PARTITION OF bronze.signal_point FOR VALUES FROM (1786665600000) TO (1786752000000);
CREATE TABLE bronze.signal_point_p20260815 PARTITION OF bronze.signal_point FOR VALUES FROM (1786752000000) TO (1786838400000);
CREATE TABLE bronze.signal_point_default PARTITION OF bronze.signal_point DEFAULT;
COMMENT ON TABLE bronze.signal_point IS 'camada canonica ponto a ponto, ja normalizada pela origem';
COMMENT ON COLUMN bronze.signal_point._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';
COMMENT ON COLUMN bronze.signal_point.tags IS 'JSON na maioria das fontes, mas a string literal ''live'' em youbora_player_live e NULL em varias. A silver converte tolerando falha de parse';

CREATE TABLE bronze.signal_bucket (
  bts           bigint,
  source        text,
  entity        text,
  metric        text,
  value         double precision,
  _extra        jsonb       NOT NULL DEFAULT '{}',
  _lsn          bigint      NOT NULL,
  _op           char(1)     NOT NULL,
  _captured_at  timestamptz NOT NULL,
  PRIMARY KEY (bts, source, entity, metric)
) PARTITION BY RANGE (bts);
-- 47 particoes diarias cobrindo 20260630..20260815, mais a DEFAULT.
CREATE TABLE bronze.signal_bucket_p20260630 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1782777600000) TO (1782864000000);
CREATE TABLE bronze.signal_bucket_p20260701 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1782864000000) TO (1782950400000);
CREATE TABLE bronze.signal_bucket_p20260702 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1782950400000) TO (1783036800000);
CREATE TABLE bronze.signal_bucket_p20260703 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783036800000) TO (1783123200000);
CREATE TABLE bronze.signal_bucket_p20260704 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783123200000) TO (1783209600000);
CREATE TABLE bronze.signal_bucket_p20260705 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783209600000) TO (1783296000000);
CREATE TABLE bronze.signal_bucket_p20260706 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783296000000) TO (1783382400000);
CREATE TABLE bronze.signal_bucket_p20260707 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783382400000) TO (1783468800000);
CREATE TABLE bronze.signal_bucket_p20260708 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783468800000) TO (1783555200000);
CREATE TABLE bronze.signal_bucket_p20260709 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783555200000) TO (1783641600000);
CREATE TABLE bronze.signal_bucket_p20260710 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783641600000) TO (1783728000000);
CREATE TABLE bronze.signal_bucket_p20260711 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783728000000) TO (1783814400000);
CREATE TABLE bronze.signal_bucket_p20260712 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783814400000) TO (1783900800000);
CREATE TABLE bronze.signal_bucket_p20260713 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783900800000) TO (1783987200000);
CREATE TABLE bronze.signal_bucket_p20260714 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1783987200000) TO (1784073600000);
CREATE TABLE bronze.signal_bucket_p20260715 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1784073600000) TO (1784160000000);
CREATE TABLE bronze.signal_bucket_p20260716 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1784160000000) TO (1784246400000);
CREATE TABLE bronze.signal_bucket_p20260717 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1784246400000) TO (1784332800000);
CREATE TABLE bronze.signal_bucket_p20260718 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1784332800000) TO (1784419200000);
CREATE TABLE bronze.signal_bucket_p20260719 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1784419200000) TO (1784505600000);
CREATE TABLE bronze.signal_bucket_p20260720 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1784505600000) TO (1784592000000);
CREATE TABLE bronze.signal_bucket_p20260721 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1784592000000) TO (1784678400000);
CREATE TABLE bronze.signal_bucket_p20260722 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1784678400000) TO (1784764800000);
CREATE TABLE bronze.signal_bucket_p20260723 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1784764800000) TO (1784851200000);
CREATE TABLE bronze.signal_bucket_p20260724 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1784851200000) TO (1784937600000);
CREATE TABLE bronze.signal_bucket_p20260725 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1784937600000) TO (1785024000000);
CREATE TABLE bronze.signal_bucket_p20260726 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785024000000) TO (1785110400000);
CREATE TABLE bronze.signal_bucket_p20260727 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785110400000) TO (1785196800000);
CREATE TABLE bronze.signal_bucket_p20260728 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785196800000) TO (1785283200000);
CREATE TABLE bronze.signal_bucket_p20260729 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785283200000) TO (1785369600000);
CREATE TABLE bronze.signal_bucket_p20260730 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785369600000) TO (1785456000000);
CREATE TABLE bronze.signal_bucket_p20260731 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785456000000) TO (1785542400000);
CREATE TABLE bronze.signal_bucket_p20260801 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785542400000) TO (1785628800000);
CREATE TABLE bronze.signal_bucket_p20260802 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785628800000) TO (1785715200000);
CREATE TABLE bronze.signal_bucket_p20260803 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785715200000) TO (1785801600000);
CREATE TABLE bronze.signal_bucket_p20260804 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785801600000) TO (1785888000000);
CREATE TABLE bronze.signal_bucket_p20260805 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785888000000) TO (1785974400000);
CREATE TABLE bronze.signal_bucket_p20260806 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1785974400000) TO (1786060800000);
CREATE TABLE bronze.signal_bucket_p20260807 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1786060800000) TO (1786147200000);
CREATE TABLE bronze.signal_bucket_p20260808 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1786147200000) TO (1786233600000);
CREATE TABLE bronze.signal_bucket_p20260809 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1786233600000) TO (1786320000000);
CREATE TABLE bronze.signal_bucket_p20260810 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1786320000000) TO (1786406400000);
CREATE TABLE bronze.signal_bucket_p20260811 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1786406400000) TO (1786492800000);
CREATE TABLE bronze.signal_bucket_p20260812 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1786492800000) TO (1786579200000);
CREATE TABLE bronze.signal_bucket_p20260813 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1786579200000) TO (1786665600000);
CREATE TABLE bronze.signal_bucket_p20260814 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1786665600000) TO (1786752000000);
CREATE TABLE bronze.signal_bucket_p20260815 PARTITION OF bronze.signal_bucket FOR VALUES FROM (1786752000000) TO (1786838400000);
CREATE TABLE bronze.signal_bucket_default PARTITION OF bronze.signal_bucket DEFAULT;
COMMENT ON TABLE bronze.signal_bucket IS 'camada canonica em bucket de 15 min';
COMMENT ON COLUMN bronze.signal_bucket._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.signal_meta (
  source            text,
  last_ingested_ts  bigint,
  last_run_at       text,
  rows_total        bigint,
  rows_last_run     bigint,
  _extra            jsonb       NOT NULL DEFAULT '{}',
  _lsn              bigint      NOT NULL,
  _op               char(1)     NOT NULL,
  _captured_at      timestamptz NOT NULL,
  PRIMARY KEY (source)
);
COMMENT ON COLUMN bronze.signal_meta._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';
COMMENT ON COLUMN bronze.signal_meta.last_run_at IS 'texto ISO-8601, nao epoch_ms';

CREATE TABLE bronze.cdn_entity_tier (
  source          text,
  entity          text,
  mean_req_per_s  double precision,
  tier            integer,
  updated_at      text,
  _extra          jsonb       NOT NULL DEFAULT '{}',
  _lsn            bigint      NOT NULL,
  _op             char(1)     NOT NULL,
  _captured_at    timestamptz NOT NULL,
  PRIMARY KEY (source, entity)
);
COMMENT ON COLUMN bronze.cdn_entity_tier._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';
COMMENT ON COLUMN bronze.cdn_entity_tier.updated_at IS 'texto ISO-8601, nao epoch_ms';

CREATE TABLE bronze.service_overview (
  timestamp             bigint,
  app_name              text,
  response_time_avg_ms  double precision,
  throughput_rpm        double precision,
  error_rate_pct        double precision,
  apdex_score           double precision,
  _extra                jsonb       NOT NULL DEFAULT '{}',
  _lsn                  bigint      NOT NULL,
  _op                   char(1)     NOT NULL,
  _captured_at          timestamptz NOT NULL,
  PRIMARY KEY (timestamp, app_name)
);
COMMENT ON COLUMN bronze.service_overview._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.operation_metrics (
  start_ts        bigint,
  end_ts          bigint,
  operation_name  text,
  request_count   double precision,
  error_count     double precision,
  p50_ms          double precision,
  p90_ms          double precision,
  p99_ms          double precision,
  _extra          jsonb       NOT NULL DEFAULT '{}',
  _lsn            bigint      NOT NULL,
  _op             char(1)     NOT NULL,
  _captured_at    timestamptz NOT NULL,
  PRIMARY KEY (start_ts, operation_name)
) PARTITION BY RANGE (start_ts);
-- 45 particoes diarias cobrindo 20260702..20260815, mais a DEFAULT.
CREATE TABLE bronze.operation_metrics_p20260702 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1782950400000) TO (1783036800000);
CREATE TABLE bronze.operation_metrics_p20260703 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783036800000) TO (1783123200000);
CREATE TABLE bronze.operation_metrics_p20260704 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783123200000) TO (1783209600000);
CREATE TABLE bronze.operation_metrics_p20260705 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783209600000) TO (1783296000000);
CREATE TABLE bronze.operation_metrics_p20260706 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783296000000) TO (1783382400000);
CREATE TABLE bronze.operation_metrics_p20260707 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783382400000) TO (1783468800000);
CREATE TABLE bronze.operation_metrics_p20260708 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783468800000) TO (1783555200000);
CREATE TABLE bronze.operation_metrics_p20260709 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783555200000) TO (1783641600000);
CREATE TABLE bronze.operation_metrics_p20260710 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783641600000) TO (1783728000000);
CREATE TABLE bronze.operation_metrics_p20260711 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783728000000) TO (1783814400000);
CREATE TABLE bronze.operation_metrics_p20260712 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783814400000) TO (1783900800000);
CREATE TABLE bronze.operation_metrics_p20260713 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783900800000) TO (1783987200000);
CREATE TABLE bronze.operation_metrics_p20260714 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1783987200000) TO (1784073600000);
CREATE TABLE bronze.operation_metrics_p20260715 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1784073600000) TO (1784160000000);
CREATE TABLE bronze.operation_metrics_p20260716 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1784160000000) TO (1784246400000);
CREATE TABLE bronze.operation_metrics_p20260717 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1784246400000) TO (1784332800000);
CREATE TABLE bronze.operation_metrics_p20260718 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1784332800000) TO (1784419200000);
CREATE TABLE bronze.operation_metrics_p20260719 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1784419200000) TO (1784505600000);
CREATE TABLE bronze.operation_metrics_p20260720 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1784505600000) TO (1784592000000);
CREATE TABLE bronze.operation_metrics_p20260721 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1784592000000) TO (1784678400000);
CREATE TABLE bronze.operation_metrics_p20260722 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1784678400000) TO (1784764800000);
CREATE TABLE bronze.operation_metrics_p20260723 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1784764800000) TO (1784851200000);
CREATE TABLE bronze.operation_metrics_p20260724 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1784851200000) TO (1784937600000);
CREATE TABLE bronze.operation_metrics_p20260725 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1784937600000) TO (1785024000000);
CREATE TABLE bronze.operation_metrics_p20260726 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785024000000) TO (1785110400000);
CREATE TABLE bronze.operation_metrics_p20260727 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785110400000) TO (1785196800000);
CREATE TABLE bronze.operation_metrics_p20260728 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785196800000) TO (1785283200000);
CREATE TABLE bronze.operation_metrics_p20260729 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785283200000) TO (1785369600000);
CREATE TABLE bronze.operation_metrics_p20260730 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785369600000) TO (1785456000000);
CREATE TABLE bronze.operation_metrics_p20260731 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785456000000) TO (1785542400000);
CREATE TABLE bronze.operation_metrics_p20260801 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785542400000) TO (1785628800000);
CREATE TABLE bronze.operation_metrics_p20260802 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785628800000) TO (1785715200000);
CREATE TABLE bronze.operation_metrics_p20260803 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785715200000) TO (1785801600000);
CREATE TABLE bronze.operation_metrics_p20260804 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785801600000) TO (1785888000000);
CREATE TABLE bronze.operation_metrics_p20260805 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785888000000) TO (1785974400000);
CREATE TABLE bronze.operation_metrics_p20260806 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1785974400000) TO (1786060800000);
CREATE TABLE bronze.operation_metrics_p20260807 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1786060800000) TO (1786147200000);
CREATE TABLE bronze.operation_metrics_p20260808 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1786147200000) TO (1786233600000);
CREATE TABLE bronze.operation_metrics_p20260809 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1786233600000) TO (1786320000000);
CREATE TABLE bronze.operation_metrics_p20260810 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1786320000000) TO (1786406400000);
CREATE TABLE bronze.operation_metrics_p20260811 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1786406400000) TO (1786492800000);
CREATE TABLE bronze.operation_metrics_p20260812 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1786492800000) TO (1786579200000);
CREATE TABLE bronze.operation_metrics_p20260813 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1786579200000) TO (1786665600000);
CREATE TABLE bronze.operation_metrics_p20260814 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1786665600000) TO (1786752000000);
CREATE TABLE bronze.operation_metrics_p20260815 PARTITION OF bronze.operation_metrics FOR VALUES FROM (1786752000000) TO (1786838400000);
CREATE TABLE bronze.operation_metrics_default PARTITION OF bronze.operation_metrics DEFAULT;
COMMENT ON COLUMN bronze.operation_metrics._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.field_metrics (
  start_ts       bigint,
  end_ts         bigint,
  coordinate     text,
  observed_exec  double precision,
  request_count  double precision,
  error_count    double precision,
  _extra         jsonb       NOT NULL DEFAULT '{}',
  _lsn           bigint      NOT NULL,
  _op            char(1)     NOT NULL,
  _captured_at   timestamptz NOT NULL,
  PRIMARY KEY (start_ts, coordinate)
);
COMMENT ON COLUMN bronze.field_metrics._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.prom_query (
  query_id        integer,
  expr_hash       text,
  expr            text,
  panel_id        integer,
  panel_title     text,
  section         text,
  ref_id          text,
  legend_format   text,
  interval_s      integer,
  enabled         smallint,
  datasource_uid  text,
  _extra          jsonb       NOT NULL DEFAULT '{}',
  _lsn            bigint      NOT NULL,
  _op             char(1)     NOT NULL,
  _captured_at    timestamptz NOT NULL,
  PRIMARY KEY (query_id)
);
COMMENT ON COLUMN bronze.prom_query._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.prom_series (
  series_id               integer,
  query_id                integer,
  labels_hash             text,
  labels_json             text,
  service_label           text,
  service_instance_label  text,
  pod_label               text,
  code_label              text,
  first_seen_ms           bigint,
  last_seen_ms            bigint,
  _extra                  jsonb       NOT NULL DEFAULT '{}',
  _lsn                    bigint      NOT NULL,
  _op                     char(1)     NOT NULL,
  _captured_at            timestamptz NOT NULL,
  PRIMARY KEY (series_id)
);
COMMENT ON COLUMN bronze.prom_series._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.prom_point (
  epoch_ms      bigint,
  series_id     integer,
  value_num     double precision,
  _extra        jsonb       NOT NULL DEFAULT '{}',
  _lsn          bigint      NOT NULL,
  _op           char(1)     NOT NULL,
  _captured_at  timestamptz NOT NULL,
  PRIMARY KEY (epoch_ms, series_id)
) PARTITION BY RANGE (epoch_ms);
-- 45 particoes diarias cobrindo 20260702..20260815, mais a DEFAULT.
CREATE TABLE bronze.prom_point_p20260702 PARTITION OF bronze.prom_point FOR VALUES FROM (1782950400000) TO (1783036800000);
CREATE TABLE bronze.prom_point_p20260703 PARTITION OF bronze.prom_point FOR VALUES FROM (1783036800000) TO (1783123200000);
CREATE TABLE bronze.prom_point_p20260704 PARTITION OF bronze.prom_point FOR VALUES FROM (1783123200000) TO (1783209600000);
CREATE TABLE bronze.prom_point_p20260705 PARTITION OF bronze.prom_point FOR VALUES FROM (1783209600000) TO (1783296000000);
CREATE TABLE bronze.prom_point_p20260706 PARTITION OF bronze.prom_point FOR VALUES FROM (1783296000000) TO (1783382400000);
CREATE TABLE bronze.prom_point_p20260707 PARTITION OF bronze.prom_point FOR VALUES FROM (1783382400000) TO (1783468800000);
CREATE TABLE bronze.prom_point_p20260708 PARTITION OF bronze.prom_point FOR VALUES FROM (1783468800000) TO (1783555200000);
CREATE TABLE bronze.prom_point_p20260709 PARTITION OF bronze.prom_point FOR VALUES FROM (1783555200000) TO (1783641600000);
CREATE TABLE bronze.prom_point_p20260710 PARTITION OF bronze.prom_point FOR VALUES FROM (1783641600000) TO (1783728000000);
CREATE TABLE bronze.prom_point_p20260711 PARTITION OF bronze.prom_point FOR VALUES FROM (1783728000000) TO (1783814400000);
CREATE TABLE bronze.prom_point_p20260712 PARTITION OF bronze.prom_point FOR VALUES FROM (1783814400000) TO (1783900800000);
CREATE TABLE bronze.prom_point_p20260713 PARTITION OF bronze.prom_point FOR VALUES FROM (1783900800000) TO (1783987200000);
CREATE TABLE bronze.prom_point_p20260714 PARTITION OF bronze.prom_point FOR VALUES FROM (1783987200000) TO (1784073600000);
CREATE TABLE bronze.prom_point_p20260715 PARTITION OF bronze.prom_point FOR VALUES FROM (1784073600000) TO (1784160000000);
CREATE TABLE bronze.prom_point_p20260716 PARTITION OF bronze.prom_point FOR VALUES FROM (1784160000000) TO (1784246400000);
CREATE TABLE bronze.prom_point_p20260717 PARTITION OF bronze.prom_point FOR VALUES FROM (1784246400000) TO (1784332800000);
CREATE TABLE bronze.prom_point_p20260718 PARTITION OF bronze.prom_point FOR VALUES FROM (1784332800000) TO (1784419200000);
CREATE TABLE bronze.prom_point_p20260719 PARTITION OF bronze.prom_point FOR VALUES FROM (1784419200000) TO (1784505600000);
CREATE TABLE bronze.prom_point_p20260720 PARTITION OF bronze.prom_point FOR VALUES FROM (1784505600000) TO (1784592000000);
CREATE TABLE bronze.prom_point_p20260721 PARTITION OF bronze.prom_point FOR VALUES FROM (1784592000000) TO (1784678400000);
CREATE TABLE bronze.prom_point_p20260722 PARTITION OF bronze.prom_point FOR VALUES FROM (1784678400000) TO (1784764800000);
CREATE TABLE bronze.prom_point_p20260723 PARTITION OF bronze.prom_point FOR VALUES FROM (1784764800000) TO (1784851200000);
CREATE TABLE bronze.prom_point_p20260724 PARTITION OF bronze.prom_point FOR VALUES FROM (1784851200000) TO (1784937600000);
CREATE TABLE bronze.prom_point_p20260725 PARTITION OF bronze.prom_point FOR VALUES FROM (1784937600000) TO (1785024000000);
CREATE TABLE bronze.prom_point_p20260726 PARTITION OF bronze.prom_point FOR VALUES FROM (1785024000000) TO (1785110400000);
CREATE TABLE bronze.prom_point_p20260727 PARTITION OF bronze.prom_point FOR VALUES FROM (1785110400000) TO (1785196800000);
CREATE TABLE bronze.prom_point_p20260728 PARTITION OF bronze.prom_point FOR VALUES FROM (1785196800000) TO (1785283200000);
CREATE TABLE bronze.prom_point_p20260729 PARTITION OF bronze.prom_point FOR VALUES FROM (1785283200000) TO (1785369600000);
CREATE TABLE bronze.prom_point_p20260730 PARTITION OF bronze.prom_point FOR VALUES FROM (1785369600000) TO (1785456000000);
CREATE TABLE bronze.prom_point_p20260731 PARTITION OF bronze.prom_point FOR VALUES FROM (1785456000000) TO (1785542400000);
CREATE TABLE bronze.prom_point_p20260801 PARTITION OF bronze.prom_point FOR VALUES FROM (1785542400000) TO (1785628800000);
CREATE TABLE bronze.prom_point_p20260802 PARTITION OF bronze.prom_point FOR VALUES FROM (1785628800000) TO (1785715200000);
CREATE TABLE bronze.prom_point_p20260803 PARTITION OF bronze.prom_point FOR VALUES FROM (1785715200000) TO (1785801600000);
CREATE TABLE bronze.prom_point_p20260804 PARTITION OF bronze.prom_point FOR VALUES FROM (1785801600000) TO (1785888000000);
CREATE TABLE bronze.prom_point_p20260805 PARTITION OF bronze.prom_point FOR VALUES FROM (1785888000000) TO (1785974400000);
CREATE TABLE bronze.prom_point_p20260806 PARTITION OF bronze.prom_point FOR VALUES FROM (1785974400000) TO (1786060800000);
CREATE TABLE bronze.prom_point_p20260807 PARTITION OF bronze.prom_point FOR VALUES FROM (1786060800000) TO (1786147200000);
CREATE TABLE bronze.prom_point_p20260808 PARTITION OF bronze.prom_point FOR VALUES FROM (1786147200000) TO (1786233600000);
CREATE TABLE bronze.prom_point_p20260809 PARTITION OF bronze.prom_point FOR VALUES FROM (1786233600000) TO (1786320000000);
CREATE TABLE bronze.prom_point_p20260810 PARTITION OF bronze.prom_point FOR VALUES FROM (1786320000000) TO (1786406400000);
CREATE TABLE bronze.prom_point_p20260811 PARTITION OF bronze.prom_point FOR VALUES FROM (1786406400000) TO (1786492800000);
CREATE TABLE bronze.prom_point_p20260812 PARTITION OF bronze.prom_point FOR VALUES FROM (1786492800000) TO (1786579200000);
CREATE TABLE bronze.prom_point_p20260813 PARTITION OF bronze.prom_point FOR VALUES FROM (1786579200000) TO (1786665600000);
CREATE TABLE bronze.prom_point_p20260814 PARTITION OF bronze.prom_point FOR VALUES FROM (1786665600000) TO (1786752000000);
CREATE TABLE bronze.prom_point_p20260815 PARTITION OF bronze.prom_point FOR VALUES FROM (1786752000000) TO (1786838400000);
CREATE TABLE bronze.prom_point_default PARTITION OF bronze.prom_point DEFAULT;
COMMENT ON TABLE bronze.prom_point IS 'tabela-fato do Prometheus: 41,2 M linhas, cadencia de 1 min';
COMMENT ON COLUMN bronze.prom_point._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.rpaas_bucket (
  bucket_ts_ms     bigint,
  region           text,
  vhost            text,
  requests_total   integer,
  requests_2xx     integer,
  requests_3xx     integer,
  requests_4xx     integer,
  requests_5xx     integer,
  p50_ms           double precision,
  p90_ms           double precision,
  p95_ms           double precision,
  p99_ms           double precision,
  latency_samples  text,
  last_updated_at  bigint,
  _extra           jsonb       NOT NULL DEFAULT '{}',
  _lsn             bigint      NOT NULL,
  _op              char(1)     NOT NULL,
  _captured_at     timestamptz NOT NULL,
  PRIMARY KEY (bucket_ts_ms, region, vhost)
);
COMMENT ON COLUMN bronze.rpaas_bucket._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';
COMMENT ON COLUMN bronze.rpaas_bucket.p50_ms IS '100% nula nas 52.560 linhas do dump';
COMMENT ON COLUMN bronze.rpaas_bucket.p90_ms IS '100% nula nas 52.560 linhas do dump';
COMMENT ON COLUMN bronze.rpaas_bucket.p95_ms IS '100% nula nas 52.560 linhas do dump';
COMMENT ON COLUMN bronze.rpaas_bucket.p99_ms IS '100% nula nas 52.560 linhas do dump';
COMMENT ON COLUMN bronze.rpaas_bucket.latency_samples IS '100% nula nas 52.560 linhas do dump: sem ela nao da para separar ''borda lenta'' de ''borda falhando''';

CREATE TABLE bronze.ca_point (
  ts_ms           bigint,
  app             text,
  backend_target  text,
  blocked         smallint,
  rps             double precision,
  _extra          jsonb       NOT NULL DEFAULT '{}',
  _lsn            bigint      NOT NULL,
  _op             char(1)     NOT NULL,
  _captured_at    timestamptz NOT NULL,
  PRIMARY KEY (ts_ms, app, blocked)
) PARTITION BY RANGE (ts_ms);
-- 45 particoes diarias cobrindo 20260702..20260815, mais a DEFAULT.
CREATE TABLE bronze.ca_point_p20260702 PARTITION OF bronze.ca_point FOR VALUES FROM (1782950400000) TO (1783036800000);
CREATE TABLE bronze.ca_point_p20260703 PARTITION OF bronze.ca_point FOR VALUES FROM (1783036800000) TO (1783123200000);
CREATE TABLE bronze.ca_point_p20260704 PARTITION OF bronze.ca_point FOR VALUES FROM (1783123200000) TO (1783209600000);
CREATE TABLE bronze.ca_point_p20260705 PARTITION OF bronze.ca_point FOR VALUES FROM (1783209600000) TO (1783296000000);
CREATE TABLE bronze.ca_point_p20260706 PARTITION OF bronze.ca_point FOR VALUES FROM (1783296000000) TO (1783382400000);
CREATE TABLE bronze.ca_point_p20260707 PARTITION OF bronze.ca_point FOR VALUES FROM (1783382400000) TO (1783468800000);
CREATE TABLE bronze.ca_point_p20260708 PARTITION OF bronze.ca_point FOR VALUES FROM (1783468800000) TO (1783555200000);
CREATE TABLE bronze.ca_point_p20260709 PARTITION OF bronze.ca_point FOR VALUES FROM (1783555200000) TO (1783641600000);
CREATE TABLE bronze.ca_point_p20260710 PARTITION OF bronze.ca_point FOR VALUES FROM (1783641600000) TO (1783728000000);
CREATE TABLE bronze.ca_point_p20260711 PARTITION OF bronze.ca_point FOR VALUES FROM (1783728000000) TO (1783814400000);
CREATE TABLE bronze.ca_point_p20260712 PARTITION OF bronze.ca_point FOR VALUES FROM (1783814400000) TO (1783900800000);
CREATE TABLE bronze.ca_point_p20260713 PARTITION OF bronze.ca_point FOR VALUES FROM (1783900800000) TO (1783987200000);
CREATE TABLE bronze.ca_point_p20260714 PARTITION OF bronze.ca_point FOR VALUES FROM (1783987200000) TO (1784073600000);
CREATE TABLE bronze.ca_point_p20260715 PARTITION OF bronze.ca_point FOR VALUES FROM (1784073600000) TO (1784160000000);
CREATE TABLE bronze.ca_point_p20260716 PARTITION OF bronze.ca_point FOR VALUES FROM (1784160000000) TO (1784246400000);
CREATE TABLE bronze.ca_point_p20260717 PARTITION OF bronze.ca_point FOR VALUES FROM (1784246400000) TO (1784332800000);
CREATE TABLE bronze.ca_point_p20260718 PARTITION OF bronze.ca_point FOR VALUES FROM (1784332800000) TO (1784419200000);
CREATE TABLE bronze.ca_point_p20260719 PARTITION OF bronze.ca_point FOR VALUES FROM (1784419200000) TO (1784505600000);
CREATE TABLE bronze.ca_point_p20260720 PARTITION OF bronze.ca_point FOR VALUES FROM (1784505600000) TO (1784592000000);
CREATE TABLE bronze.ca_point_p20260721 PARTITION OF bronze.ca_point FOR VALUES FROM (1784592000000) TO (1784678400000);
CREATE TABLE bronze.ca_point_p20260722 PARTITION OF bronze.ca_point FOR VALUES FROM (1784678400000) TO (1784764800000);
CREATE TABLE bronze.ca_point_p20260723 PARTITION OF bronze.ca_point FOR VALUES FROM (1784764800000) TO (1784851200000);
CREATE TABLE bronze.ca_point_p20260724 PARTITION OF bronze.ca_point FOR VALUES FROM (1784851200000) TO (1784937600000);
CREATE TABLE bronze.ca_point_p20260725 PARTITION OF bronze.ca_point FOR VALUES FROM (1784937600000) TO (1785024000000);
CREATE TABLE bronze.ca_point_p20260726 PARTITION OF bronze.ca_point FOR VALUES FROM (1785024000000) TO (1785110400000);
CREATE TABLE bronze.ca_point_p20260727 PARTITION OF bronze.ca_point FOR VALUES FROM (1785110400000) TO (1785196800000);
CREATE TABLE bronze.ca_point_p20260728 PARTITION OF bronze.ca_point FOR VALUES FROM (1785196800000) TO (1785283200000);
CREATE TABLE bronze.ca_point_p20260729 PARTITION OF bronze.ca_point FOR VALUES FROM (1785283200000) TO (1785369600000);
CREATE TABLE bronze.ca_point_p20260730 PARTITION OF bronze.ca_point FOR VALUES FROM (1785369600000) TO (1785456000000);
CREATE TABLE bronze.ca_point_p20260731 PARTITION OF bronze.ca_point FOR VALUES FROM (1785456000000) TO (1785542400000);
CREATE TABLE bronze.ca_point_p20260801 PARTITION OF bronze.ca_point FOR VALUES FROM (1785542400000) TO (1785628800000);
CREATE TABLE bronze.ca_point_p20260802 PARTITION OF bronze.ca_point FOR VALUES FROM (1785628800000) TO (1785715200000);
CREATE TABLE bronze.ca_point_p20260803 PARTITION OF bronze.ca_point FOR VALUES FROM (1785715200000) TO (1785801600000);
CREATE TABLE bronze.ca_point_p20260804 PARTITION OF bronze.ca_point FOR VALUES FROM (1785801600000) TO (1785888000000);
CREATE TABLE bronze.ca_point_p20260805 PARTITION OF bronze.ca_point FOR VALUES FROM (1785888000000) TO (1785974400000);
CREATE TABLE bronze.ca_point_p20260806 PARTITION OF bronze.ca_point FOR VALUES FROM (1785974400000) TO (1786060800000);
CREATE TABLE bronze.ca_point_p20260807 PARTITION OF bronze.ca_point FOR VALUES FROM (1786060800000) TO (1786147200000);
CREATE TABLE bronze.ca_point_p20260808 PARTITION OF bronze.ca_point FOR VALUES FROM (1786147200000) TO (1786233600000);
CREATE TABLE bronze.ca_point_p20260809 PARTITION OF bronze.ca_point FOR VALUES FROM (1786233600000) TO (1786320000000);
CREATE TABLE bronze.ca_point_p20260810 PARTITION OF bronze.ca_point FOR VALUES FROM (1786320000000) TO (1786406400000);
CREATE TABLE bronze.ca_point_p20260811 PARTITION OF bronze.ca_point FOR VALUES FROM (1786406400000) TO (1786492800000);
CREATE TABLE bronze.ca_point_p20260812 PARTITION OF bronze.ca_point FOR VALUES FROM (1786492800000) TO (1786579200000);
CREATE TABLE bronze.ca_point_p20260813 PARTITION OF bronze.ca_point FOR VALUES FROM (1786579200000) TO (1786665600000);
CREATE TABLE bronze.ca_point_p20260814 PARTITION OF bronze.ca_point FOR VALUES FROM (1786665600000) TO (1786752000000);
CREATE TABLE bronze.ca_point_p20260815 PARTITION OF bronze.ca_point FOR VALUES FROM (1786752000000) TO (1786838400000);
CREATE TABLE bronze.ca_point_default PARTITION OF bronze.ca_point DEFAULT;
COMMENT ON COLUMN bronze.ca_point._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.tsuru_event (
  start_time_ms  bigint,
  uniqueid       text,
  target_type    text,
  target_value   text,
  kind           text,
  owner_type     text,
  owner          text,
  end_time_ms    bigint,
  duration_ms    bigint,
  error          text,
  raw_json       text,
  _extra         jsonb       NOT NULL DEFAULT '{}',
  _lsn           bigint      NOT NULL,
  _op            char(1)     NOT NULL,
  _captured_at   timestamptz NOT NULL,
  PRIMARY KEY (start_time_ms, uniqueid)
);
COMMENT ON COLUMN bronze.tsuru_event._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.player_hourly (
  hour_ts       bigint,
  player        text,
  sessions      bigint,
  errors        bigint,
  _extra        jsonb       NOT NULL DEFAULT '{}',
  _lsn          bigint      NOT NULL,
  _op           char(1)     NOT NULL,
  _captured_at  timestamptz NOT NULL,
  PRIMARY KEY (hour_ts, player)
);
COMMENT ON COLUMN bronze.player_hourly._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.device_hourly (
  hour_ts       bigint,
  device        text,
  sessions      bigint,
  errors        bigint,
  _extra        jsonb       NOT NULL DEFAULT '{}',
  _lsn          bigint      NOT NULL,
  _op           char(1)     NOT NULL,
  _captured_at  timestamptz NOT NULL,
  PRIMARY KEY (hour_ts, device)
) PARTITION BY RANGE (hour_ts);
-- 45 particoes diarias cobrindo 20260702..20260815, mais a DEFAULT.
CREATE TABLE bronze.device_hourly_p20260702 PARTITION OF bronze.device_hourly FOR VALUES FROM (1782950400000) TO (1783036800000);
CREATE TABLE bronze.device_hourly_p20260703 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783036800000) TO (1783123200000);
CREATE TABLE bronze.device_hourly_p20260704 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783123200000) TO (1783209600000);
CREATE TABLE bronze.device_hourly_p20260705 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783209600000) TO (1783296000000);
CREATE TABLE bronze.device_hourly_p20260706 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783296000000) TO (1783382400000);
CREATE TABLE bronze.device_hourly_p20260707 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783382400000) TO (1783468800000);
CREATE TABLE bronze.device_hourly_p20260708 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783468800000) TO (1783555200000);
CREATE TABLE bronze.device_hourly_p20260709 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783555200000) TO (1783641600000);
CREATE TABLE bronze.device_hourly_p20260710 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783641600000) TO (1783728000000);
CREATE TABLE bronze.device_hourly_p20260711 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783728000000) TO (1783814400000);
CREATE TABLE bronze.device_hourly_p20260712 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783814400000) TO (1783900800000);
CREATE TABLE bronze.device_hourly_p20260713 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783900800000) TO (1783987200000);
CREATE TABLE bronze.device_hourly_p20260714 PARTITION OF bronze.device_hourly FOR VALUES FROM (1783987200000) TO (1784073600000);
CREATE TABLE bronze.device_hourly_p20260715 PARTITION OF bronze.device_hourly FOR VALUES FROM (1784073600000) TO (1784160000000);
CREATE TABLE bronze.device_hourly_p20260716 PARTITION OF bronze.device_hourly FOR VALUES FROM (1784160000000) TO (1784246400000);
CREATE TABLE bronze.device_hourly_p20260717 PARTITION OF bronze.device_hourly FOR VALUES FROM (1784246400000) TO (1784332800000);
CREATE TABLE bronze.device_hourly_p20260718 PARTITION OF bronze.device_hourly FOR VALUES FROM (1784332800000) TO (1784419200000);
CREATE TABLE bronze.device_hourly_p20260719 PARTITION OF bronze.device_hourly FOR VALUES FROM (1784419200000) TO (1784505600000);
CREATE TABLE bronze.device_hourly_p20260720 PARTITION OF bronze.device_hourly FOR VALUES FROM (1784505600000) TO (1784592000000);
CREATE TABLE bronze.device_hourly_p20260721 PARTITION OF bronze.device_hourly FOR VALUES FROM (1784592000000) TO (1784678400000);
CREATE TABLE bronze.device_hourly_p20260722 PARTITION OF bronze.device_hourly FOR VALUES FROM (1784678400000) TO (1784764800000);
CREATE TABLE bronze.device_hourly_p20260723 PARTITION OF bronze.device_hourly FOR VALUES FROM (1784764800000) TO (1784851200000);
CREATE TABLE bronze.device_hourly_p20260724 PARTITION OF bronze.device_hourly FOR VALUES FROM (1784851200000) TO (1784937600000);
CREATE TABLE bronze.device_hourly_p20260725 PARTITION OF bronze.device_hourly FOR VALUES FROM (1784937600000) TO (1785024000000);
CREATE TABLE bronze.device_hourly_p20260726 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785024000000) TO (1785110400000);
CREATE TABLE bronze.device_hourly_p20260727 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785110400000) TO (1785196800000);
CREATE TABLE bronze.device_hourly_p20260728 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785196800000) TO (1785283200000);
CREATE TABLE bronze.device_hourly_p20260729 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785283200000) TO (1785369600000);
CREATE TABLE bronze.device_hourly_p20260730 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785369600000) TO (1785456000000);
CREATE TABLE bronze.device_hourly_p20260731 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785456000000) TO (1785542400000);
CREATE TABLE bronze.device_hourly_p20260801 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785542400000) TO (1785628800000);
CREATE TABLE bronze.device_hourly_p20260802 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785628800000) TO (1785715200000);
CREATE TABLE bronze.device_hourly_p20260803 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785715200000) TO (1785801600000);
CREATE TABLE bronze.device_hourly_p20260804 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785801600000) TO (1785888000000);
CREATE TABLE bronze.device_hourly_p20260805 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785888000000) TO (1785974400000);
CREATE TABLE bronze.device_hourly_p20260806 PARTITION OF bronze.device_hourly FOR VALUES FROM (1785974400000) TO (1786060800000);
CREATE TABLE bronze.device_hourly_p20260807 PARTITION OF bronze.device_hourly FOR VALUES FROM (1786060800000) TO (1786147200000);
CREATE TABLE bronze.device_hourly_p20260808 PARTITION OF bronze.device_hourly FOR VALUES FROM (1786147200000) TO (1786233600000);
CREATE TABLE bronze.device_hourly_p20260809 PARTITION OF bronze.device_hourly FOR VALUES FROM (1786233600000) TO (1786320000000);
CREATE TABLE bronze.device_hourly_p20260810 PARTITION OF bronze.device_hourly FOR VALUES FROM (1786320000000) TO (1786406400000);
CREATE TABLE bronze.device_hourly_p20260811 PARTITION OF bronze.device_hourly FOR VALUES FROM (1786406400000) TO (1786492800000);
CREATE TABLE bronze.device_hourly_p20260812 PARTITION OF bronze.device_hourly FOR VALUES FROM (1786492800000) TO (1786579200000);
CREATE TABLE bronze.device_hourly_p20260813 PARTITION OF bronze.device_hourly FOR VALUES FROM (1786579200000) TO (1786665600000);
CREATE TABLE bronze.device_hourly_p20260814 PARTITION OF bronze.device_hourly FOR VALUES FROM (1786665600000) TO (1786752000000);
CREATE TABLE bronze.device_hourly_p20260815 PARTITION OF bronze.device_hourly FOR VALUES FROM (1786752000000) TO (1786838400000);
CREATE TABLE bronze.device_hourly_default PARTITION OF bronze.device_hourly DEFAULT;
COMMENT ON COLUMN bronze.device_hourly._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.geo_hourly (
  hour_ts         bigint,
  state_province  text,
  isp             text,
  sessions        bigint,
  errors          bigint,
  _extra          jsonb       NOT NULL DEFAULT '{}',
  _lsn            bigint      NOT NULL,
  _op             char(1)     NOT NULL,
  _captured_at    timestamptz NOT NULL,
  PRIMARY KEY (hour_ts, state_province, isp)
);
COMMENT ON COLUMN bronze.geo_hourly._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';
COMMENT ON COLUMN bronze.geo_hourly.isp IS 'exclusivo com state_province na pratica: a linha traz UF ou ISP, nunca os dois';

CREATE TABLE bronze.live_qoe_hourly (
  hour_ts             bigint,
  sinal               text,
  sessions            bigint,
  errors              bigint,
  startup_errors      bigint,
  latency_ms_avg      double precision,
  latency_ms_p50      double precision,
  latency_ms_p95      double precision,
  bufferratio_avg     double precision,
  jointime_s_avg      double precision,
  dropped_frames_avg  double precision,
  stalls_avg          double precision,
  bitrate_mbps_avg    double precision,
  bitrate_mbps_p50    double precision,
  _extra              jsonb       NOT NULL DEFAULT '{}',
  _lsn                bigint      NOT NULL,
  _op                 char(1)     NOT NULL,
  _captured_at        timestamptz NOT NULL,
  PRIMARY KEY (hour_ts, sinal)
);
COMMENT ON COLUMN bronze.live_qoe_hourly._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.player_live_hourly (
  hour_ts             bigint,
  player              text,
  sessions            bigint,
  errors              bigint,
  startup_errors      bigint,
  jointime_s_avg      double precision,
  bufferratio_avg     double precision,
  latency_ms_avg      double precision,
  dropped_frames_avg  double precision,
  stalls_avg          double precision,
  _extra              jsonb       NOT NULL DEFAULT '{}',
  _lsn                bigint      NOT NULL,
  _op                 char(1)     NOT NULL,
  _captured_at        timestamptz NOT NULL,
  PRIMARY KEY (hour_ts, player)
);
COMMENT ON COLUMN bronze.player_live_hourly._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.live_active_15min (
  bucket_ts           bigint,
  sinal               text,
  active_sessions     bigint,
  active_with_error   bigint,
  joins_in_bucket     bigint,
  latency_ms_p50      double precision,
  latency_ms_p95      double precision,
  bufferratio_avg     double precision,
  jointime_s_avg      double precision,
  dropped_frames_avg  double precision,
  _extra              jsonb       NOT NULL DEFAULT '{}',
  _lsn                bigint      NOT NULL,
  _op                 char(1)     NOT NULL,
  _captured_at        timestamptz NOT NULL,
  PRIMARY KEY (bucket_ts, sinal)
);
COMMENT ON COLUMN bronze.live_active_15min._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.live_error_attr_hourly (
  hour_ts       bigint,
  sinal         text,
  cdn           text,
  tier          text,
  http_code     text,
  error_name    text,
  errors        bigint,
  _extra        jsonb       NOT NULL DEFAULT '{}',
  _lsn          bigint      NOT NULL,
  _op           char(1)     NOT NULL,
  _captured_at  timestamptz NOT NULL,
  PRIMARY KEY (hour_ts, sinal, cdn, tier, http_code, error_name)
);
COMMENT ON COLUMN bronze.live_error_attr_hourly._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.error_cat_hourly (
  hour_ts       bigint,
  kind          text,
  category      text,
  errors        bigint,
  top_names     text,
  _extra        jsonb       NOT NULL DEFAULT '{}',
  _lsn          bigint      NOT NULL,
  _op           char(1)     NOT NULL,
  _captured_at  timestamptz NOT NULL,
  PRIMARY KEY (hour_ts, kind, category)
);
COMMENT ON COLUMN bronze.error_cat_hourly._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.live_event (
  tid            integer,
  start_ts       bigint,
  end_ts         bigint,
  event_key      text,
  event_date     text,
  slug           text,
  channel        text,
  competition    text,
  program        text,
  sport          text,
  team_home      text,
  team_away      text,
  guia_slot_id   bigint,
  url_program    text,
  first_seen_ts  bigint,
  updated_at     bigint,
  _extra         jsonb       NOT NULL DEFAULT '{}',
  _lsn           bigint      NOT NULL,
  _op            char(1)     NOT NULL,
  _captured_at   timestamptz NOT NULL,
  PRIMARY KEY (tid, start_ts)
);
COMMENT ON TABLE bronze.live_event IS 'calendario de transmissoes ao vivo; ver gold.live_event_window';
COMMENT ON COLUMN bronze.live_event._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';
COMMENT ON COLUMN bronze.live_event.tid IS 'tid 994 e 995 sao feeds SIMULTANEOS com jogos diferentes, nao o mesmo canal em horarios diferentes. Agrupar por start_ts funde dois jogos';
COMMENT ON COLUMN bronze.live_event.slug IS 'chega sempre como ''globo'' (a familia) enquanto a QoE vem por praca (globo-rj, globo-sp): o casamento e LIKE ''globo%'' como agregado nacional, nunca praca especifica';

CREATE TABLE bronze.incidents (
  opened_at                                         bigint,
  sys_id                                            text,
  number                                            text,
  resolved_at                                       bigint,
  closed_at                                         bigint,
  priority                                          text,
  priority_value                                    text,
  state                                             text,
  assignment_group                                  text,
  business_service                                  text,
  cmdb_ci                                           text,
  short_description                                 text,
  u_this_incident_caused_external_impacts           text,
  u_this_incident_was_caused_by_a_change_or_deploy  text,
  parent_incident                                   text,
  child_incidents                                   text,
  state_value                                       text,
  category                                          text,
  subcategory                                       text,
  cause                                             text,
  caused_by                                         text,
  u_what_s_the_root_cause                           text,
  impact_component                                  text,
  impact_component_value                            text,
  close_code                                        text,
  close_code_value                                  text,
  close_notes                                       text,
  scr_vendor                                        text,
  scr_vendor_point_of_contact                       text,
  scr_vendor_ticket                                 text,
  _extra                                            jsonb       NOT NULL DEFAULT '{}',
  _lsn                                              bigint      NOT NULL,
  _op                                               char(1)     NOT NULL,
  _captured_at                                      timestamptz NOT NULL,
  PRIMARY KEY (opened_at, sys_id)
);
COMMENT ON COLUMN bronze.incidents._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.incidents_platform (
  opened_at                                         bigint,
  sys_id                                            text,
  number                                            text,
  resolved_at                                       bigint,
  closed_at                                         bigint,
  priority                                          text,
  priority_value                                    text,
  state                                             text,
  assignment_group                                  text,
  business_service                                  text,
  cmdb_ci                                           text,
  short_description                                 text,
  u_this_incident_caused_external_impacts           text,
  u_this_incident_was_caused_by_a_change_or_deploy  text,
  parent_incident                                   text,
  child_incidents                                   text,
  state_value                                       text,
  category                                          text,
  subcategory                                       text,
  cause                                             text,
  caused_by                                         text,
  u_what_s_the_root_cause                           text,
  impact_component                                  text,
  impact_component_value                            text,
  close_code                                        text,
  close_code_value                                  text,
  close_notes                                       text,
  scr_vendor                                        text,
  scr_vendor_point_of_contact                       text,
  scr_vendor_ticket                                 text,
  _extra                                            jsonb       NOT NULL DEFAULT '{}',
  _lsn                                              bigint      NOT NULL,
  _op                                               char(1)     NOT NULL,
  _captured_at                                      timestamptz NOT NULL,
  PRIMARY KEY (opened_at, sys_id)
);
COMMENT ON COLUMN bronze.incidents_platform._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.incident_label (
  id             text,
  tier           smallint,
  kind           text,
  ts_start       bigint,
  ts_end         bigint,
  severity       text,
  region         text,
  services       text,
  description    text,
  narrative_md   text,
  metrics_cited  text,
  source_doc     text,
  notes          text,
  provenance     text,
  verdict        text,
  _extra         jsonb       NOT NULL DEFAULT '{}',
  _lsn           bigint      NOT NULL,
  _op            char(1)     NOT NULL,
  _captured_at   timestamptz NOT NULL,
  PRIMARY KEY (id)
);
COMMENT ON TABLE bronze.incident_label IS 'ground truth rotulado a mao; ver a coluna provenance';
COMMENT ON COLUMN bronze.incident_label._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';
COMMENT ON COLUMN bronze.incident_label.provenance IS '7 dos 20 rotulos sao ''detector-derived'', criados olhando a saida do proprio Argus. Avaliar detector contra eles mede concordancia com o baseline, nao acuracia';

CREATE TABLE bronze.investigation_feedback (
  id                 text,
  target_kind        text,
  target_id          text,
  investigated_at    text,
  target_attempt     smallint,
  vote               text,
  corrected_verdict  text,
  corrected_causes   text,
  critique           text,
  author             text,
  author_source      text,
  created_at         bigint,
  updated_at         bigint,
  processed_at       bigint,
  effects            text,
  resolution         text,
  _extra             jsonb       NOT NULL DEFAULT '{}',
  _lsn               bigint      NOT NULL,
  _op                char(1)     NOT NULL,
  _captured_at       timestamptz NOT NULL,
  PRIMARY KEY (id)
);
COMMENT ON TABLE bronze.investigation_feedback IS 'vazia no dump (0 linhas), schema preservado';
COMMENT ON COLUMN bronze.investigation_feedback._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';
COMMENT ON COLUMN bronze.investigation_feedback.investigated_at IS 'texto ISO-8601, nao epoch_ms';

CREATE TABLE bronze.dashboard_artifact (
  name          text,
  payload       text,
  bytes         bigint,
  updated_at    bigint,
  _extra        jsonb       NOT NULL DEFAULT '{}',
  _lsn          bigint      NOT NULL,
  _op           char(1)     NOT NULL,
  _captured_at  timestamptz NOT NULL,
  PRIMARY KEY (name)
);
COMMENT ON TABLE bronze.dashboard_artifact IS 'saida do Argus que ja existe em producao na Globo';
COMMENT ON COLUMN bronze.dashboard_artifact._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.collector_run (
  run_id         bigint,
  source         text,
  started_at     bigint,
  finished_at    bigint,
  range_start    bigint,
  range_end      bigint,
  rows_upserted  bigint,
  bytes_scanned  bigint,
  cost_usd       double precision,
  duration_s     double precision,
  notes          text,
  _extra         jsonb       NOT NULL DEFAULT '{}',
  _lsn           bigint      NOT NULL,
  _op            char(1)     NOT NULL,
  _captured_at   timestamptz NOT NULL,
  PRIMARY KEY (run_id)
);
COMMENT ON COLUMN bronze.collector_run._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.apollo_run (
  run_id         bigint,
  started_at     text,
  finished_at    text,
  kind           text,
  range_start    text,
  range_end      text,
  pages          bigint,
  rows_inserted  bigint,
  rows_updated   bigint,
  duration_s     double precision,
  notes          text,
  _extra         jsonb       NOT NULL DEFAULT '{}',
  _lsn           bigint      NOT NULL,
  _op            char(1)     NOT NULL,
  _captured_at   timestamptz NOT NULL,
  PRIMARY KEY (run_id)
);
COMMENT ON COLUMN bronze.apollo_run._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.nr_run (
  run_id         bigint,
  started_at     text,
  finished_at    text,
  kind           text,
  account_id     bigint,
  nrql           text,
  rows_seen      bigint,
  rows_inserted  bigint,
  duration_s     double precision,
  notes          text,
  _extra         jsonb       NOT NULL DEFAULT '{}',
  _lsn           bigint      NOT NULL,
  _op            char(1)     NOT NULL,
  _captured_at   timestamptz NOT NULL,
  PRIMARY KEY (run_id)
);
COMMENT ON COLUMN bronze.nr_run._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.prom_run (
  run_id           bigint,
  started_at       text,
  finished_at      text,
  range_start_ms   bigint,
  range_end_ms     bigint,
  step_s           bigint,
  queries_total    bigint,
  queries_ok       bigint,
  queries_err      bigint,
  series_touched   bigint,
  points_inserted  bigint,
  duration_s       double precision,
  notes            text,
  _extra           jsonb       NOT NULL DEFAULT '{}',
  _lsn             bigint      NOT NULL,
  _op              char(1)     NOT NULL,
  _captured_at     timestamptz NOT NULL,
  PRIMARY KEY (run_id)
);
COMMENT ON COLUMN bronze.prom_run._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.rpaas_run (
  run_id        bigint,
  started_at    text,
  finished_at   text,
  range_start   text,
  range_end     text,
  regions       text,
  entries_read  bigint,
  buckets_upd   bigint,
  duration_s    double precision,
  notes         text,
  _extra        jsonb       NOT NULL DEFAULT '{}',
  _lsn          bigint      NOT NULL,
  _op           char(1)     NOT NULL,
  _captured_at  timestamptz NOT NULL,
  PRIMARY KEY (run_id)
);
COMMENT ON COLUMN bronze.rpaas_run._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';

CREATE TABLE bronze.ca_run (
  run_id           bigint,
  started_at       text,
  finished_at      text,
  range_start_ms   bigint,
  range_end_ms     bigint,
  points_inserted  bigint,
  duration_s       double precision,
  notes            text,
  _extra           jsonb       NOT NULL DEFAULT '{}',
  _lsn             bigint      NOT NULL,
  _op              char(1)     NOT NULL,
  _captured_at     timestamptz NOT NULL,
  PRIMARY KEY (run_id)
);
COMMENT ON COLUMN bronze.ca_run._extra IS 'coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar';
