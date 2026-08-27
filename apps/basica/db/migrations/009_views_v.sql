-- 009_views_v.sql
--
-- O recorte do presente, e a barreira contra vazamento de futuro.
--
-- Uma view por tabela consultavel, cada uma cortada em `sim.now()`. E o UNICO
-- caminho de leitura da API: a Lambda nao recebe SELECT nas tabelas base.
--
-- A escolha e deliberada. Aplicacao esquece o filtro -- numa rota nova, num
-- JOIN de debug, numa consulta ad-hoc de quem esta investigando. GRANT nao
-- esquece. Colocar a barreira no banco e o que torna "o detector nao pode ver o
-- futuro" uma propriedade do sistema, e nao uma promessa da revisao de codigo.

-- --------------------------------------------------------------------------- #
-- Relogio
-- --------------------------------------------------------------------------- #

-- A tela e marcada "ao vivo", entao ela precisa saber que horas sao no mundo
-- virtual -- senao "agora" no dashboard e o relogio do navegador, que nao tem
-- relacao nenhuma com o que o banco esta mostrando.
CREATE VIEW sim.v_clock AS
  SELECT sim.now() AS sim_now,
         c.speed,
         c.updated_at
    FROM sim.clock c
   WHERE c.id = 1;

-- --------------------------------------------------------------------------- #
-- Silver
-- --------------------------------------------------------------------------- #

CREATE VIEW silver.v_signal_point AS
  SELECT ts, source, entity, metric, value, tags
    FROM silver.signal_point
   WHERE available_at <= sim.now();

CREATE VIEW silver.v_signal_bucket AS
  SELECT bucket_ts, source, entity, metric, value
    FROM silver.signal_bucket
   WHERE available_at <= sim.now();

CREATE VIEW silver.v_session_event AS
  SELECT ts, event_id, event_name, session_id, device_id, user_id,
         app_bucket, app_env, app_target, app_version,
         device_manufacturer, device_model, device_os,
         route_path, duration, uf, isp, payload
    FROM silver.session_event
   WHERE available_at <= sim.now();

-- --------------------------------------------------------------------------- #
-- Gold
-- --------------------------------------------------------------------------- #

CREATE VIEW gold.v_feature_bucket AS
  SELECT bucket_ts, source, entity, metric, value, hora_brt, dow, tem_jogo
    FROM gold.feature_bucket
   WHERE available_at <= sim.now();

-- O baseline e estado, nao serie: o corte e por quando ele foi atualizado.
CREATE VIEW gold.v_circadian_state AS
  SELECT series_key, hora_brt, mean, var, n, updated_at
    FROM gold.circadian_state
   WHERE updated_at <= sim.now();

-- Uma transmissao entra na tela quando comeca, nao quando o calendario e
-- publicado -- mas `first_seen` existe para quem quiser ser rigoroso e so
-- mostrar o que ja tinha sido anunciado.
CREATE VIEW gold.v_live_event_window AS
  SELECT event_key, tid, ts_start, ts_end, slug, channel, competition,
         sport, team_home, team_away, event_date, first_seen
    FROM gold.live_event_window
   WHERE ts_start <= sim.now();

CREATE VIEW gold.v_incident_window AS
  SELECT window_id, ts_start, ts_end, origem, ref_id, verdict, severity, provenance
    FROM gold.incident_window
   WHERE ts_start <= sim.now();

-- `provenance` vem junto de proposito: quem consome esta view PRECISA decidir
-- explicitamente se filtra os rotulos `detector-derived` (ver o COMMENT em
-- gold.incident_window). Esconder a coluna aqui seria facilitar a medicao
-- errada.
CREATE VIEW gold.v_detection_match AS
  SELECT m.window_id, m.run_id, m.detection_id, m.lead_time_s, m.matched,
         w.ts_start, w.ts_end, w.origem, w.provenance
    FROM gold.detection_match m
    JOIN gold.incident_window w USING (window_id)
   WHERE w.ts_start <= sim.now();

-- --------------------------------------------------------------------------- #
-- Detect
-- --------------------------------------------------------------------------- #

CREATE VIEW detect.v_anomaly AS
  SELECT run_id, bucket_ts, source, entity, metric, z, score, n_sources
    FROM detect.anomaly
   WHERE bucket_ts <= sim.now();

CREATE VIEW detect.v_run AS
  SELECT run_id, sim_run_id, detector, params, started_at, finished_at
    FROM detect.run;

-- --------------------------------------------------------------------------- #
-- A barreira
-- --------------------------------------------------------------------------- #

-- USAGE no schema permite RESOLVER nomes, nao ler tabela. Sem o GRANT SELECT
-- explicito abaixo, `argus_reader` enxerga que gold.feature_bucket existe e
-- recebe "permission denied" ao tentar le-la -- que e exatamente o
-- comportamento desejado.
GRANT USAGE ON SCHEMA sim, silver, gold, detect TO argus_reader;

-- `sim.clock` e a UNICA tabela base que o leitor enxerga, e a excecao tem
-- motivo tecnico, nao de conveniencia.
--
-- Uma view roda com a permissao do DONO dela, e e por isso que o leitor
-- consegue ler gold.v_feature_bucket sem ter acesso a gold.feature_bucket. Mas
-- FUNCAO dentro da view roda com a permissao de quem CHAMA -- entao `sim.now()`
-- no WHERE tenta ler sim.clock como argus_reader e leva "permission denied",
-- derrubando toda view v_*.
--
-- Dois caminhos resolviam: SECURITY DEFINER em sim.now(), ou este GRANT. O
-- GRANT ganhou por ser o menos magico -- SECURITY DEFINER cria uma funcao que
-- roda com privilegio elevado e vira superficie de escalonamento se o
-- search_path escapar. E o que se expoe aqui e uma linha dizendo que horas sao
-- no mundo virtual, que a propria sim.v_clock ja publica.
GRANT SELECT ON sim.clock TO argus_reader;

GRANT SELECT ON
  sim.v_clock,
  silver.v_signal_point,
  silver.v_signal_bucket,
  silver.v_session_event,
  gold.v_feature_bucket,
  gold.v_circadian_state,
  gold.v_live_event_window,
  gold.v_incident_window,
  gold.v_detection_match,
  detect.v_anomaly,
  detect.v_run
TO argus_reader;

-- Nao ha GRANT no schema bronze, em nenhuma forma. As telas nunca consultam
-- bronze (§3, corolario 1), e a ausencia aqui e o que garante isso.
--
-- Tambem nao ha ALTER DEFAULT PRIVILEGES: tabela nova nasce inacessivel ao
-- leitor, e passa a ser legivel quando alguem escrever a view e o GRANT numa
-- migration. Conceder por antecipacao anularia a barreira no primeiro CREATE
-- TABLE distraido.
