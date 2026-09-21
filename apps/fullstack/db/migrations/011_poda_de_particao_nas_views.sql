-- Poda de particao nas views que filtram por disponibilidade.
--
-- O PROBLEMA
--
-- `gold.v_feature_bucket` filtrava so `available_at <= sim.now()`. Numa consulta
-- de serie -- `WHERE bucket_ts >= sim.now() - '24h' ORDER BY bucket_ts LIMIT 10`
-- -- o planner monta um Merge Append sobre as 63 particoes e precisa da primeira
-- linha de cada uma. Nas particoes de `bucket_ts` FUTURO toda linha reprova no
-- filtro de disponibilidade, entao o index scan varre a particao inteira para
-- concluir que nao ha nada.
--
-- Medido no RDS com 4,9 M linhas em gold.feature_bucket:
--
--   Limit (actual rows=10)
--     Buffers: shared hit=4911351 read=14885
--     Execution Time: 59548 ms
--
-- Quase cinco milhoes de buffers para devolver dez linhas. A Lambda tem 30 s de
-- timeout, entao a rota /api/v1/series devolvia 503.
--
-- A CORRECAO
--
-- Acrescentar `<coluna de tempo> <= sim.now()` a clausula. Isso e uma restricao
-- na COLUNA DE PARTICIONAMENTO, entao o planner poda as particoes futuras antes
-- de tocar nelas.
--
-- E provavelmente equivalente ao filtro que ja existia: `available_at` e o
-- instante em que o dado FICA DISPONIVEL, que nunca antecede o instante em que
-- ele aconteceu. Logo `available_at >= ts`, e uma linha com `ts > sim.now()`
-- tem `available_at >= ts > sim.now()` -- ja estava fora. A clausula nova nao
-- remove nenhuma linha, so ensina o planner a nao procurar onde nao ha.
--
-- POR QUE O CHECK VEM JUNTO
--
-- Essa equivalencia depende de um invariante que ate agora era so uma convencao
-- de quem escreveu o ETL. Se um dia alguem gravasse `available_at` anterior ao
-- tempo do dado, a view passaria a ESCONDER linhas em silencio -- o pior tipo de
-- defeito, porque a consulta continua respondendo, so que a menos.
--
-- Entao o invariante deixa de ser convencao e vira `CHECK`. Verificado contra os
-- dados ja carregados: zero violacoes em 18,2 M linhas de signal_point, 4,9 M de
-- feature_bucket e 4,9 M de signal_bucket.

-- --------------------------------------------------------------------------- #
-- O invariante, agora explicito
-- --------------------------------------------------------------------------- #

ALTER TABLE silver.signal_point
  ADD CONSTRAINT signal_point_disponivel_depois
  CHECK (available_at >= ts);

ALTER TABLE silver.signal_bucket
  ADD CONSTRAINT signal_bucket_disponivel_depois
  CHECK (available_at >= bucket_ts);

ALTER TABLE silver.session_event
  ADD CONSTRAINT session_event_disponivel_depois
  CHECK (available_at >= ts);

ALTER TABLE gold.feature_bucket
  ADD CONSTRAINT feature_bucket_disponivel_depois
  CHECK (available_at >= bucket_ts);

-- --------------------------------------------------------------------------- #
-- As views, agora podaveis
-- --------------------------------------------------------------------------- #

-- CREATE OR REPLACE mantem os GRANTs de 009: `argus_reader` continua com SELECT
-- sem precisar reconceder. Trocar por DROP + CREATE derrubaria a permissao e a
-- API perderia acesso sem ninguem mudar nada de permissao.

CREATE OR REPLACE VIEW silver.v_signal_point AS
  SELECT ts, source, entity, metric, value, tags
    FROM silver.signal_point
   WHERE available_at <= sim.now()
     AND ts <= sim.now();

CREATE OR REPLACE VIEW silver.v_signal_bucket AS
  SELECT bucket_ts, source, entity, metric, value
    FROM silver.signal_bucket
   WHERE available_at <= sim.now()
     AND bucket_ts <= sim.now();

CREATE OR REPLACE VIEW silver.v_session_event AS
  SELECT ts, event_id, event_name, session_id, device_id, user_id,
         app_bucket, app_env, app_target, app_version,
         device_manufacturer, device_model, device_os,
         route_path, duration, uf, isp, payload
    FROM silver.session_event
   WHERE available_at <= sim.now()
     AND ts <= sim.now();

CREATE OR REPLACE VIEW gold.v_feature_bucket AS
  SELECT bucket_ts, source, entity, metric, value, hora_brt, dow, tem_jogo
    FROM gold.feature_bucket
   WHERE available_at <= sim.now()
     AND bucket_ts <= sim.now();
