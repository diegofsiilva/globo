-- 003_bronze_change_log.sql
--
-- O log append-only. E a unica tabela do sistema que nao pode ser reconstruida:
-- silver e gold saem dela por replay, a bronze corrente sai dela por MERGE.
--
-- Generico de proposito. As 33 tabelas do Argus tem schemas diferentes e a
-- Globo pode acrescentar coluna a qualquer momento; `before` e `after` em jsonb
-- absorvem qualquer forma sem DDL. E a decisao 4 do plano: a bronze e otimizada
-- para MUDAR, nao para performance, porque o ETL ainda esta em aprimoramento e
-- o custo de errar precisa ser baixo.

CREATE TABLE bronze.change_log (
  lsn          bigserial   NOT NULL,
  source_table text        NOT NULL,
  op           char(1)     NOT NULL CHECK (op IN ('i', 'u', 'd', 'r')),
  pk           jsonb       NOT NULL,
  before       jsonb,
  after        jsonb,
  captured_at  timestamptz NOT NULL,
  received_at  timestamptz NOT NULL DEFAULT now(),
  run_id       bigint,
  PRIMARY KEY (lsn)
) PARTITION BY RANGE (lsn);

COMMENT ON TABLE bronze.change_log IS
  'Append-only. Enquanto ele estiver integro, TRUNCATE em silver e gold seguido '
  'de replay reconstroi tudo -- e o que torna a iteracao do ETL barata';
COMMENT ON COLUMN bronze.change_log.op IS
  'i = insert, u = update, d = delete, r = read (linha do snapshot inicial)';
COMMENT ON COLUMN bronze.change_log.captured_at IS
  'quando a ORIGEM observou a mudanca';
COMMENT ON COLUMN bronze.change_log.received_at IS
  'quando ela chegou aqui. A diferenca para captured_at e o lag do pipeline';

-- Particoes de 10 M. A carga inicial sozinha ja escreve 68,7 M linhas, entao as
-- sete primeiras nascem ocupadas; as outras tres sao folga para o replay.
DO $$
DECLARE
  i int;
BEGIN
  FOR i IN 0..9 LOOP
    EXECUTE format(
      'CREATE TABLE bronze.change_log_p%s PARTITION OF bronze.change_log '
      'FOR VALUES FROM (%s) TO (%s)',
      lpad(i::text, 2, '0'), i::bigint * 10000000, (i + 1)::bigint * 10000000
    );
  END LOOP;
END
$$;

-- Sem a DEFAULT o log para de aceitar escrita no momento em que passa da ultima
-- faixa -- num log append-only isso seria perda de dado por conta de aritmetica.
CREATE TABLE bronze.change_log_default PARTITION OF bronze.change_log DEFAULT;

-- Unico indice alem da PK: o replay le por tabela, em ordem de lsn.
--
-- Nao ha indice em `after`. O log e escrito e relido em ordem, nunca consultado
-- ad-hoc; um GIN em jsonb aqui custaria escrita (e a escrita e o caminho quente
-- da ingestao) sem comprar nenhuma leitura que a gente realmente faca.
CREATE INDEX change_log_source_lsn ON bronze.change_log (source_table, lsn);
