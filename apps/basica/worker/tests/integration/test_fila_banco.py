"""TI-03 -- integracao entre a fila de mensagens e o banco de dados.

Componentes atravessados:

    SQS `argus-events` (dublado em memoria com `moto`)
        -> `EventConsumer` (`argus_worker.consumer`)
            -> `EventRepository` (`argus_worker.repository`)
                -> PostgreSQL (`bronze.event`)
        -> SQS `argus-events-dlq`, para o que o consumidor recusar

O SQS e dublado e o PostgreSQL e real, de proposito: a parte dificil deste
caminho mora no SQL (o `ON CONFLICT` que sustenta a idempotencia), enquanto o
comportamento da fila que importa aqui -- entregar, reentregar e aceitar a
mensagem de volta na DLQ -- o `moto` reproduz fielmente. E a mesma regra que o
resto da suite segue, registrada em `worker/tests/conftest.py`.

O que se verifica e a COMUNICACAO entre os tres: que uma mensagem postada na
fila vira linha no banco, que uma mensagem ruim no MESMO lote nao impede isso e
termina na DLQ com motivo legivel, e que a reentrega -- garantia at-least-once
do SQS, ou seja, a fila pode entregar a mesma mensagem mais de uma vez -- nao
duplica a linha ja gravada.

Requisitos exercitados: RF01 (ingestao por uma API unica), RF04 (rejeicao
rastreavel do invalido), RNF04 (um evento invalido nao impede os validos
seguintes) e RNF05 (nao perder silenciosamente o que ja foi aceito).

Pre-condicao: PostgreSQL de teste no ar (`make -C apps/basica db-local`). Sem
ele a suite e PULADA, nao quebrada.
"""

from __future__ import annotations

import json

# Sem envelope minimo: falta `timestamp`, `session_id` e `device_id`. E o
# formato que o RF04 manda recusar de forma rastreavel.
EVENTO_INVALIDO = {"event_name": "request"}

LIMITE_DE_CICLOS = 10


def _postar(aws, corpo) -> None:
    """Posta uma mensagem na fila de eventos."""
    aws.sqs.send_message(
        QueueUrl=aws.filas["argus-events"],
        MessageBody=corpo if isinstance(corpo, str) else json.dumps(corpo),
    )


def _drenar(consumer) -> int:
    """Roda o consumidor ate a fila parar de entregar.

    Um `run_once` esvazia um lote, nao a fila inteira. O laco tem teto para o
    teste falhar por assercao em vez de travar caso o consumidor deixe de
    apagar o que processou.

    Returns:
        int: Total de mensagens processadas.
    """
    total = 0
    for _ in range(LIMITE_DE_CICLOS):
        processadas = consumer.run_once()
        if processadas == 0:
            return total
        total += processadas
    raise AssertionError("a fila nao drenou dentro do limite de ciclos")


def _mensagens_na_dlq(aws) -> list[dict]:
    return aws.sqs.receive_message(
        QueueUrl=aws.filas["argus-events-dlq"],
        MaxNumberOfMessages=10,
        MessageAttributeNames=["All"],
    ).get("Messages", [])


def _restam_na_fila(aws) -> int:
    atributos = aws.sqs.get_queue_attributes(
        QueueUrl=aws.filas["argus-events"],
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
        ],
    )["Attributes"]
    return int(atributos["ApproximateNumberOfMessages"]) + int(
        atributos["ApproximateNumberOfMessagesNotVisible"]
    )


def test_ti03_lote_misto_grava_o_valido_no_banco_e_isola_o_invalido_na_dlq(
    aws, event_consumer, db, sample_events
):
    """TI-03.1 -- o invalido nao contamina o valido, e nenhum dos dois some.

    Entrada: duas mensagens na fila `argus-events`, postadas na ordem
    invalida -> valida. A invalida vem primeiro porque e a ordem que mais
    machuca: se o consumidor abortasse o lote no erro, o evento valido
    seguinte nunca chegaria ao banco.

    Resultado esperado: `bronze.event` com exatamente a linha do evento
    valido; a DLQ com exatamente uma mensagem, carregando o motivo da recusa;
    a fila principal drenada a zero, sem mensagem presa.
    """
    valido = sample_events["error"]
    _postar(aws, EVENTO_INVALIDO)
    _postar(aws, valido)

    _drenar(event_consumer)

    # 1. O valido chegou ao banco, com o conteudo que veio pela fila.
    linhas = db.fetch_all("SELECT event_name, session_id, device_id FROM bronze.event")
    assert len(linhas) == 1
    assert linhas[0]["event_name"] == valido["event_name"]
    assert linhas[0]["session_id"] == valido["session_id"]
    assert linhas[0]["device_id"] == valido["device_id"]

    # 2. O invalido saiu de circulacao pela DLQ, e nao em silencio (RF04).
    quarentena = _mensagens_na_dlq(aws)
    assert len(quarentena) == 1
    motivo = quarentena[0]["MessageAttributes"]["FailureReason"]["StringValue"]
    assert motivo, "a mensagem recusada foi para a DLQ sem motivo registrado"

    # 3. Nada ficou preso na fila de entrada (RNF04).
    assert _restam_na_fila(aws) == 0


def test_ti03_reentrega_da_mesma_mensagem_nao_duplica_a_linha(
    aws, event_consumer, db, sample_events
):
    """TI-03.2 -- at-least-once da fila + escrita idempotente no banco.

    Entrada: o mesmo evento valido postado duas vezes, em ciclos separados --
    e o que o SQS faz quando o `delete` da mensagem nao chega a tempo.

    Resultado esperado: uma unica linha em `bronze.event`, com o mesmo
    `event_id`. A idempotencia nao e do consumidor nem do banco isolados: ela
    so existe na combinacao dos dois.
    """
    valido = sample_events["error"]

    _postar(aws, valido)
    _drenar(event_consumer)
    antes = db.fetch_one("SELECT count(*) AS n FROM bronze.event")["n"]

    _postar(aws, valido)
    _drenar(event_consumer)
    depois = db.fetch_one("SELECT count(*) AS n FROM bronze.event")["n"]

    assert antes == 1
    assert depois == 1, "a reentrega duplicou a linha no banco"
    assert _mensagens_na_dlq(aws) == []
