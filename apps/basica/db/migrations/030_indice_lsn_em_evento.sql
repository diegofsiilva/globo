-- 030_indice_lsn_em_evento.sql
--
-- `bronze.event` particiona por `ts`, mas a ETL incremental le por `_lsn`. Sem
-- indice nessa coluna, cada ciclo do worker bronze->silver varre TODAS as
-- particoes da tabela -- duas vezes:
--
--   1. `etl.proxima_faixa_lsn`  ... SELECT _lsn FROM bronze.event WHERE _lsn > x
--   2. `silver.build_session_event` ... WHERE e._lsn > p_from AND e._lsn <= p_to
--
-- Nao ha poda de particao possivel (particiona por `ts`, filtra por `_lsn`) nem
-- indice a usar, entao o plano e Seq Scan em cada particao, com custo
-- proporcional ao TAMANHO DA TABELA -- e nao ao tamanho do lote. Medido no
-- banco local com 300.000 linhas: 48,7 ms sem o indice contra 12,6 ms com ele,
-- trocando `Seq Scan` por `Index Only Scan` com `Heap Fetches: 0`. A diferenca
-- cresce com a tabela, porque so um dos dois lados cresce junto.
--
-- Compare com `bronze.change_log`, que ja nasceu certa: PRIMARY KEY (lsn) e
-- PARTITION BY RANGE (lsn). A mesma consulta la e poda de particao mais indice.
--
-- A 029 foi quem trouxe `bronze.event` para o caminho quente -- corrigindo um
-- problema real: sem ela, evento novo recebia LSN e nenhuma faixa era criada
-- com o simulador desligado. O indice e o que faltou junto.
--
-- APLICACAO EM BANCO GRANDE: `CREATE INDEX` numa tabela particionada pega
-- ACCESS EXCLUSIVE no pai e o PostgreSQL NAO aceita CONCURRENTLY aqui (nem
-- caberia: o runner aplica cada migration dentro de uma transacao). Se o lock
-- for inaceitavel na janela de manutencao, a receita e criar o indice do pai
-- com `ON ONLY` (fica invalido), depois um `CREATE INDEX CONCURRENTLY` por
-- particao, e por fim `ALTER INDEX event_lsn ATTACH PARTITION ...` em cada uma
-- -- o que valida o indice do pai. Esta migration faz a forma simples, que e a
-- correta para o banco local e para uma base recem-criada.

CREATE INDEX event_lsn ON bronze.event (_lsn);

COMMENT ON INDEX bronze.event_lsn IS
  'Caminho de leitura da ETL incremental: etl.proxima_faixa_lsn e '
  'silver.build_session_event filtram por _lsn, coluna que nao participa da '
  'chave de particionamento (ts). Sem ele, cada ciclo varre a tabela inteira';
