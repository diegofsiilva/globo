-- A tela Agora compara o ultimo ponto de cada serie com a mesma hora BRT dos
-- sete dias anteriores. O indice de serie existente termina em bucket_ts e,
-- por isso, ainda le as outras 23 horas antes de filtrar `hora_brt`.
--
-- Colocar a hora antes do tempo torna cada baseline uma faixa pequena. Os
-- campos em INCLUDE permitem resolver valor e a barreira de `available_at`
-- pelo proprio indice na maioria das paginas.

CREATE INDEX feature_bucket_baseline_horario
  ON gold.feature_bucket (source, entity, metric, hora_brt, bucket_ts)
  INCLUDE (value, available_at)
  WHERE value IS NOT NULL;
