-- 001_schemas_e_extensoes.sql
--
-- Os cinco schemas e o papel de leitura.
--
-- A separacao em schemas nao e organizacao de gaveta: e o que permite dar
-- permissao por camada. A barreira contra vazamento de futuro (§4.8 do plano)
-- depende disso -- a Lambda de leitura recebe SELECT nas views `v_*` e em nada
-- mais, entao esquecer o filtro de `available_at` na aplicacao nao expoe dado
-- que o relogio virtual ainda nao alcancou.

CREATE SCHEMA IF NOT EXISTS sim;
CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;
CREATE SCHEMA IF NOT EXISTS detect;

COMMENT ON SCHEMA sim IS
  'Relogio virtual e injecao de falhas: define "o presente" para todo o resto';
COMMENT ON SCHEMA bronze IS
  'Log append-only de change events + estado corrente das 33 tabelas do Argus';
COMMENT ON SCHEMA silver IS
  'Canonicalizacao de tipo e tempo, e o carimbo de available_at';
COMMENT ON SCHEMA gold IS
  'Features e janelas: a unica camada que as telas consultam';
COMMENT ON SCHEMA detect IS
  'Saida do detector, particionada por run_id para permitir comparacao';

-- --------------------------------------------------------------------------- #
-- Papel de leitura
-- --------------------------------------------------------------------------- #

-- NOLOGIN de proposito: `argus_reader` e um pacote de permissao, nao uma
-- credencial. O usuario que a Lambda realmente usa e criado fora da migration
-- (`python tools/migrate.py criar-leitor`), porque criar usuario com senha aqui
-- colocaria segredo em arquivo versionado.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'argus_reader') THEN
    CREATE ROLE argus_reader NOLOGIN;
  END IF;
END
$$;

COMMENT ON ROLE argus_reader IS
  'SELECT apenas nas views v_*. Nunca receba GRANT em tabela base: e este papel '
  'que impede a API de enxergar o futuro do relogio virtual';
