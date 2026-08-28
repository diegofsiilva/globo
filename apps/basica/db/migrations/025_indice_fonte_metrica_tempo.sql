-- Indice que as agregacoes da serie realmente usam.
--
-- O PROBLEMA
--
-- Explorar, Comparar e Recorte filtram gold.feature_bucket por
-- (source, metric, janela de bucket_ts). Os indices existentes nao cobrem
-- esse predicado:
--
--   PK (bucket_ts, source, entity, metric)
--     -- a particao poda pelo tempo, mas depois varre TODAS as entidades
--        da fonte na janela.
--   feature_bucket_serie (source, entity, metric, bucket_ts)
--     -- so ajuda quando a entidade ja e conhecida.
--   feature_bucket_source_recente (source, bucket_ts DESC)
--     -- acha o ultimo bucket da fonte, nao agrega uma metrica na janela.
--
-- youbora_device tem ~2.900 aparelhos. Um heatmap de `sessions` nas ultimas
-- 24 h varreria dezenas de milhares de linhas por indice errado, e a tela
-- Recorte dispara duas dessas de uma vez.
--
-- A CORRECAO
--
-- (source, metric, bucket_ts) deixa o planner entrar pela fonte e pela
-- metrica e so depois recortar o tempo. Particao por bucket_ts continua
-- podando os dias fora da janela.

CREATE INDEX feature_bucket_fonte_metrica_tempo
  ON gold.feature_bucket (source, metric, bucket_ts);
