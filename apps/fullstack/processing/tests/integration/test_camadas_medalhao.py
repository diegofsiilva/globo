"""TI-04 -- integracao entre os modulos internos da ETL e o banco de dados.

Componentes atravessados:

    `bronze.change_log`  (mudanca bruta, como o worker de ingestao a deixa)
        -> `bronze.merge_todas()`      (funcao SQL de consolidacao)
            -> `etl.executar_bronze_silver`  (modulo `argus_processing.etl`)
                -> `silver.signal_bucket`    (dado normalizado)
                    -> `etl.executar_silver_gold`
                        -> `gold.feature_bucket`  (dado pronto para consulta)

Junto do dado caminham os dois marcadores de progresso -- os `watermark`, a
linha do banco que diz ate onde cada etapa ja processou. Sao eles que tornam a
ETL incremental: cada execucao le so o que entrou depois do marcador e o avanca
ao terminar.

O que se verifica e a COMUNICACAO entre esses modulos e o banco: que um mesmo
valor sobrevive as tres camadas sem se perder nem se deformar, que cada etapa so
avanca seu marcador na medida do que realmente processou, e que rodar de novo
sem dado novo nao reprocessa -- o que, num pipeline incremental, e a diferenca
entre um numero certo e um numero contado duas vezes.

Requisitos exercitados: RF05 (converter para um esquema comum) e RF06
(armazenar para consulta e analise posteriores).

Pre-condicao: PostgreSQL de teste no ar (`make -C apps/fullstack db-local`). Sem
ele a suite e PULADA, nao quebrada.
"""

from __future__ import annotations

from argus_processing import etl

# 2026-07-05 em milissegundos -- dentro da janela que o watermark silver->gold
# comeca aberta (semeado em 2026-07-01) e atras do relogio virtual do teste
# (2026-07-12). Fora dessa faixa a linha existiria e mesmo assim nao seria
# processada, e o teste falharia por motivo que nao e o que ele investiga.
BTS = 1783220400000

# Valor de assinatura: um numero improvavel de aparecer por acaso, para que
# encontra-lo na camada gold prove que veio DESTA linha e nao de outra.
VALOR = 412.5

BUCKET = {
    "bts": BTS,
    "source": "prometheus",
    "entity": "cdn-ti04",
    "metric": "p95_ms",
    "value": VALOR,
}


def test_ti04_o_valor_atravessa_bronze_silver_e_gold_sem_se_deformar(db, inserir_change):
    """TI-04.1 -- uma mudanca bruta vira dado consultavel, camada a camada.

    Entrada: uma linha em `bronze.change_log` descrevendo a insercao de um
    bucket de sinal com valor 412,5.

    Resultado esperado: apos as duas etapas da ETL, o mesmo valor esta em
    `silver.signal_bucket` e em `gold.feature_bucket`, com `source`, `entity` e
    `metric` preservados. Cada assercao intermediaria localiza em qual
    travessia o dado se perderia, caso se perdesse.
    """
    with db.connection() as conn:
        lsn = inserir_change(conn, "signal_bucket", BUCKET)
        conn.execute("SELECT bronze.merge_todas()")

    # 1. Bronze: a mudanca bruta foi consolidada na tabela de destino.
    bruto = db.fetch_one(
        "SELECT value FROM bronze.signal_bucket WHERE entity = %s", ("cdn-ti04",)
    )
    assert bruto is not None, "o merge nao consolidou a mudanca na bronze"
    assert bruto["value"] == VALOR

    # 2. Bronze -> silver: o modulo da ETL le o backlog e normaliza.
    resultado_silver = etl.executar_bronze_silver(db, batch_size=100)
    assert resultado_silver["status"] == "sucesso"
    assert resultado_silver["ate_lsn"] == lsn

    normalizado = db.fetch_one(
        "SELECT source, entity, metric, value FROM silver.signal_bucket"
        " WHERE entity = %s",
        ("cdn-ti04",),
    )
    assert normalizado == {
        "source": "prometheus",
        "entity": "cdn-ti04",
        "metric": "p95_ms",
        "value": VALOR,
    }

    # 3. Silver -> gold: a janela e materializada para consulta.
    resultado_gold = etl.executar_silver_gold(db, janela_max_segundos=999_999_999)
    assert resultado_gold["status"] == "sucesso"
    assert resultado_gold["linhas"] >= 1

    consultavel = db.fetch_one(
        "SELECT source, entity, metric, value FROM gold.feature_bucket WHERE entity = %s",
        ("cdn-ti04",),
    )
    assert consultavel == {
        "source": "prometheus",
        "entity": "cdn-ti04",
        "metric": "p95_ms",
        "value": VALOR,
    }


def test_ti04_cada_etapa_avanca_seu_marcador_na_medida_do_que_processou(
    db, inserir_change
):
    """TI-04.2 -- o progresso registrado no banco bate com o trabalho feito.

    Entrada: a mesma linha do caso anterior.

    Resultado esperado: o marcador bronze->silver passa a valer exatamente o
    `lsn` da ultima mudanca lida -- nem menos (reprocessaria) nem mais (pularia
    dado). O marcador silver->gold para uma margem de seguranca atras do fim da
    janela, deixando essa faixa reaberta para o ciclo seguinte, porque dado
    atrasado ainda pode chegar nela.
    """
    antes = db.fetch_one(
        "SELECT lsn_processado FROM etl.watermark_bronze_silver WHERE id = 1"
    )["lsn_processado"]

    with db.connection() as conn:
        lsn = inserir_change(conn, "signal_bucket", BUCKET)
        conn.execute("SELECT bronze.merge_todas()")

    etl.executar_bronze_silver(db, batch_size=100)

    depois = db.fetch_one(
        "SELECT lsn_processado FROM etl.watermark_bronze_silver WHERE id = 1"
    )["lsn_processado"]
    assert antes < depois == lsn

    resultado_gold = etl.executar_silver_gold(db, janela_max_segundos=999_999_999)
    marcador = db.fetch_one(
        "SELECT available_at_processado, margem_seguranca"
        "  FROM etl.watermark_silver_gold WHERE id = 1"
    )
    assert marcador["available_at_processado"] == (
        resultado_gold["ate_ts"] - marcador["margem_seguranca"]
    )


def test_ti04_rodar_de_novo_sem_dado_novo_nao_reprocessa(db, inserir_change):
    """TI-04.3 -- o caso negativo: o pipeline em repouso.

    Entrada: a linha ja processada por uma execucao completa, e nenhuma
    mudanca nova depois dela.

    Resultado esperado: a segunda execucao de bronze->silver responde
    `sem_pendencia` e a camada gold continua com uma unica linha da entidade.
    Sem isso, um ciclo ocioso somaria o mesmo evento outra vez e o dashboard
    mostraria o dobro do que aconteceu.
    """
    with db.connection() as conn:
        inserir_change(conn, "signal_bucket", BUCKET)
        conn.execute("SELECT bronze.merge_todas()")

    etl.executar_bronze_silver(db, batch_size=100)
    etl.executar_silver_gold(db, janela_max_segundos=999_999_999)

    segunda = etl.executar_bronze_silver(db, batch_size=100)
    assert segunda["status"] == "sem_pendencia"
    assert segunda["linhas"] == 0

    total = db.fetch_one(
        "SELECT count(*) AS n FROM gold.feature_bucket WHERE entity = %s", ("cdn-ti04",)
    )["n"]
    assert total == 1
