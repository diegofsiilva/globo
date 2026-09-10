-- Confere que os watermarks do ETL incremental (015_etl_incremental.sql)
-- nunca regrediram entre execucoes de sucesso.
--
-- Bug historico (plano-argus-v3.md, secao 12): se p_janela_max_segundos <=
-- margem_seguranca, watermark_silver_gold regredia a cada chamada (a margem e
-- subtraida nas duas pontas do ciclo). `etl.executar_silver_gold` hoje levanta
-- excecao nessa condicao -- o que garante o invariante DENTRO de uma chamada,
-- nao que ninguem reintroduza a condicao. Esta consulta confere o HISTORICO de
-- execucoes de verdade, incluindo as que rodaram durante os cenarios de
-- resiliencia desta Sprint. Zero linhas em cada bloco = sem regressao.

-- bronze -> silver: watermark e um lsn (bigint). Comparar como texto quebraria
-- entre "9" e "10" -- por isso o cast explicito, mesmo a coluna sendo `text`
-- de proposito (etl.execucoes serve aos dois workers, ver comentario da
-- migration).
WITH ordenado AS (
  SELECT execucao_id, iniciado_em,
         watermark_anterior::bigint AS anterior,
         watermark_novo::bigint     AS novo
    FROM etl.execucoes
   WHERE worker = 'bronze_silver'
     AND status = 'sucesso'
     AND watermark_anterior IS NOT NULL
     AND watermark_novo IS NOT NULL
)
SELECT 'bronze_silver' AS worker, execucao_id, iniciado_em, anterior, novo
  FROM ordenado
 WHERE novo < anterior
 ORDER BY iniciado_em;

-- silver -> gold: watermark e um timestamp (ISO 8601 ja ordena certo como
-- texto, mas o cast deixa a intencao explicita e pega formato inesperado).
WITH ordenado AS (
  SELECT execucao_id, iniciado_em,
         watermark_anterior::timestamptz AS anterior,
         watermark_novo::timestamptz     AS novo
    FROM etl.execucoes
   WHERE worker = 'silver_gold'
     AND status = 'sucesso'
     AND watermark_anterior IS NOT NULL
     AND watermark_novo IS NOT NULL
)
SELECT 'silver_gold' AS worker, execucao_id, iniciado_em, anterior, novo
  FROM ordenado
 WHERE novo < anterior
 ORDER BY iniciado_em;
