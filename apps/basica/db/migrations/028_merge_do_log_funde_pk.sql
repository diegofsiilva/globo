-- 028_merge_do_log_funde_pk.sql
--
-- Corrige bronze.merge_do_log: para op='u' o CDC manda em `after` só o que
-- mudou (ex.: {"value": ...}), com as colunas de identidade (bts/source/
-- entity/metric/ts/hour_ts...) vivendo em `pk`, nunca em `after`. A funcao
-- original montava a linha só com `c.after`, então update violava a NOT NULL
-- dessas colunas -- e como o gerador de carga (`payloads.js`) so emite 'u',
-- praticamente todo update de teste ia parar na changes-dlq em vez da bronze
-- corrente. Fix: funde `c.pk` antes de `c.after` (pk nunca colide com as
-- chaves de `after`, que só carrega os campos não-chave).
CREATE OR REPLACE FUNCTION bronze.merge_do_log(
  p_tabela   text,
  p_from_lsn bigint,
  p_to_lsn   bigint
) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE
  cols      text[] := bronze.colunas_de(p_tabela);
  pk        text[] := bronze.pk_de(p_tabela);
  sem_pk    text[];
  atualiza  text;
  casa_pk   text;
  aplicadas bigint := 0;
  removidas bigint := 0;
BEGIN
  IF cols IS NULL OR pk IS NULL THEN
    RAISE EXCEPTION 'bronze.% nao existe ou nao tem chave primaria', p_tabela;
  END IF;

  SELECT array_agg(c) INTO sem_pk FROM unnest(cols) c WHERE NOT (c = ANY(pk));

  SELECT string_agg(format('%I = EXCLUDED.%I', c, c), ', ')
    INTO atualiza
    FROM unnest(
      COALESCE(sem_pk, '{}'::text[])
      || ARRAY['_extra', '_lsn', '_op', '_captured_at']
    ) c;

  EXECUTE format($fmt$
    INSERT INTO bronze.%I
    SELECT (jsonb_populate_record(
              NULL::bronze.%I,
              c.pk || c.after || jsonb_build_object(
                '_lsn', c.lsn, '_op', c.op, '_captured_at', c.captured_at,
                '_extra', (c.pk || c.after) - %L::text[]
              )
           )).*
      FROM (
        SELECT DISTINCT ON (l.pk) l.pk, l.after, l.lsn, l.op, l.captured_at
          FROM bronze.change_log l
         WHERE l.source_table = %L AND l.lsn BETWEEN %s AND %s
           AND l.op IN ('i','u','r') AND l.after IS NOT NULL
         ORDER BY l.pk, l.lsn DESC
      ) c
    ON CONFLICT (%s) DO UPDATE SET %s
     WHERE bronze.%I._lsn < EXCLUDED._lsn
  $fmt$,
    p_tabela, p_tabela, cols, p_tabela, p_from_lsn, p_to_lsn,
    (SELECT string_agg(quote_ident(c), ', ') FROM unnest(pk) c),
    atualiza, p_tabela
  );
  GET DIAGNOSTICS aplicadas = ROW_COUNT;

  SELECT string_agg(
           format('t.%I = (d.pk ->> %L)::%s', u.c, u.c,
                  format_type(a.atttypid, a.atttypmod)), ' AND ')
    INTO casa_pk
    FROM unnest(pk) AS u(c)
    JOIN pg_class cl ON cl.relname = p_tabela
    JOIN pg_namespace n ON n.oid = cl.relnamespace AND n.nspname = 'bronze'
    JOIN pg_attribute a ON a.attrelid = cl.oid AND a.attname = u.c;

  EXECUTE format($fmt$
    DELETE FROM bronze.%I t
     USING (
       SELECT DISTINCT ON (l.pk) l.pk, l.lsn
         FROM bronze.change_log l
        WHERE l.source_table = %L AND l.lsn BETWEEN %s AND %s AND l.op = 'd'
        ORDER BY l.pk, l.lsn DESC
     ) d
     WHERE %s AND t._lsn < d.lsn
  $fmt$, p_tabela, p_tabela, p_from_lsn, p_to_lsn, casa_pk);
  GET DIAGNOSTICS removidas = ROW_COUNT;

  RETURN aplicadas + removidas;
END
$$;
