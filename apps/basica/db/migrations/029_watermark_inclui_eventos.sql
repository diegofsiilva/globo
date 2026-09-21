-- 029_watermark_inclui_eventos.sql
--
-- O watermark bronze->silver era dirigido apenas por bronze.change_log. Com o
-- simulador desligado, eventos novos em bronze.event recebiam LSN, mas nenhum
-- change posterior criava uma faixa: a fila drenava e o dashboard permanecia
-- sem os eventos. A fronteira deve considerar os dois produtores da sequencia.

CREATE OR REPLACE FUNCTION etl.proxima_faixa_lsn(
  p_from_lsn bigint,
  p_batch_size int
) RETURNS bigint
LANGUAGE sql STABLE AS $$
  SELECT max(lsn)
  FROM (
    SELECT lsn
    FROM (
      SELECT lsn
        FROM bronze.change_log
       WHERE lsn > p_from_lsn
      UNION ALL
      SELECT _lsn AS lsn
        FROM bronze.event
       WHERE _lsn > p_from_lsn
    ) pendentes
    ORDER BY lsn
    LIMIT p_batch_size
  ) faixa;
$$;

COMMENT ON FUNCTION etl.proxima_faixa_lsn(bigint, int) IS
  'Proxima faixa global de LSN de changes ou eventos; NULL quando ambos os '
  'fluxos estao sem backlog';
