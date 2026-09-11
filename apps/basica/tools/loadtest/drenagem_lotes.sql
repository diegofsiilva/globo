-- Evidencia de persistencia e frescor dos lotes do RNF01 revisado.
-- Uso: psql "$DATABASE_URL" -v test_id="<K6_TEST_ID>" -f drenagem_lotes.sql

SELECT
  count(*) AS eventos_persistidos,
  count(DISTINCT payload ->> 'batch_id') AS lotes_persistidos,
  min(_captured_at) AS primeiro_evento_persistido_em,
  max(_captured_at) AS ultimo_evento_persistido_em,
  round(avg(extract(epoch FROM (
    _captured_at - (payload ->> 'load_test_sent_at')::timestamptz
  )))::numeric, 3) AS frescor_medio_s,
  round(percentile_cont(0.50) WITHIN GROUP (
    ORDER BY extract(epoch FROM (
      _captured_at - (payload ->> 'load_test_sent_at')::timestamptz
    ))
  )::numeric, 3) AS frescor_p50_s,
  round(percentile_cont(0.95) WITHIN GROUP (
    ORDER BY extract(epoch FROM (
      _captured_at - (payload ->> 'load_test_sent_at')::timestamptz
    ))
  )::numeric, 3) AS frescor_p95_s,
  round(percentile_cont(0.99) WITHIN GROUP (
    ORDER BY extract(epoch FROM (
      _captured_at - (payload ->> 'load_test_sent_at')::timestamptz
    ))
  )::numeric, 3) AS frescor_p99_s,
  round(max(extract(epoch FROM (
    _captured_at - (payload ->> 'load_test_sent_at')::timestamptz
  )))::numeric, 3) AS frescor_max_s
FROM bronze.event
WHERE payload ->> 'load_test_id' = :'test_id';

SELECT
  payload ->> 'batch_id' AS lote,
  count(*) AS eventos_persistidos,
  min(_captured_at) AS primeiro_evento_persistido_em,
  max(_captured_at) AS ultimo_evento_persistido_em
FROM bronze.event
WHERE payload ->> 'load_test_id' = :'test_id'
GROUP BY payload ->> 'batch_id'
ORDER BY lote;
