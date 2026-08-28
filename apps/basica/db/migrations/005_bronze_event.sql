-- 005_bronze_event.sql
--
-- O segundo fluxo de ingestao: grain de sessao.
--
-- Envelope comum tipado -- e por ele que as telas Explorar e Recorte filtram --
-- e campos especificos do tipo em `payload`. O envelope sai do schema real dos
-- exports do BI e dos modelos Pydantic do worker (models.py), que ja resolvem
-- tipo de evento desconhecido caindo em GenericEvent.
--
-- O modelo e permissivo por motivo operacional, nao por desleixo: o parque de
-- TVs atualiza devagar e de forma desigual, e schema estrito transformaria
-- qualquer mudanca no app em perda de dado em massa (RF03).

CREATE TABLE bronze.event (
  event_id            text        NOT NULL,
  ts                  timestamptz NOT NULL,
  event_name          text        NOT NULL,
  session_id          text        NOT NULL,
  device_id           text,
  user_id             text,
  app_bucket          text,
  app_env             text,
  app_target          text,
  app_version         text,
  device_manufacturer text,
  device_model        text,
  device_model_year   integer,
  device_os           text,
  device_os_version   text,
  route_path          text,
  route_params        jsonb,
  duration            double precision,
  payload             jsonb       NOT NULL DEFAULT '{}',
  _lsn                bigint      NOT NULL,
  _captured_at        timestamptz NOT NULL,
  PRIMARY KEY (ts, event_id)
) PARTITION BY RANGE (ts);

COMMENT ON TABLE bronze.event IS
  'Grain de sessao, o segundo fluxo. Envelope tipado + payload jsonb';
COMMENT ON COLUMN bronze.event.event_name IS
  'request | screen_view | session | video_view | vitals | error -- e o que '
  'mais o app mandar: tipo desconhecido e gravado, nao descartado';
COMMENT ON COLUMN bronze.event.payload IS
  'campos especificos do tipo (request_*, media_*, error_*, capabilities_*). '
  'E aqui que UF e ISP entram quando o fluxo do Argus for especificado, sem '
  'migration';

-- Particoes mensais cobrindo a janela do dump com folga de cada lado. Mensal e
-- nao diaria porque este fluxo e de volume muito menor que a telemetria: uma
-- particao por dia so multiplicaria o custo de planejamento sem podar nada.
DO $$
DECLARE
  mes date := date '2026-05-01';
BEGIN
  WHILE mes < date '2027-01-01' LOOP
    EXECUTE format(
      'CREATE TABLE bronze.event_p%s PARTITION OF bronze.event '
      'FOR VALUES FROM (%L) TO (%L)',
      to_char(mes, 'YYYYMM'), mes, mes + interval '1 month'
    );
    mes := mes + interval '1 month';
  END LOOP;
END
$$;

CREATE TABLE bronze.event_default PARTITION OF bronze.event DEFAULT;

-- Os tres filtros que as telas Explorar e Recorte aplicam de fato.
CREATE INDEX event_name_ts   ON bronze.event (event_name, ts DESC);
CREATE INDEX event_session   ON bronze.event (session_id, ts);
CREATE INDEX event_device    ON bronze.event (device_model, ts DESC)
  WHERE device_model IS NOT NULL;
