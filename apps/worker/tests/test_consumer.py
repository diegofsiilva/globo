"""Testes de integracao do loop de consumo, com SQS e DynamoDB reais via moto."""

from __future__ import annotations

import json

import pytest

from argus_worker.consumer import _extract_events


def _enviar(aws, payload) -> None:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    aws.sqs.send_message(QueueUrl=aws.config.queue_url, MessageBody=body)


def _itens(aws) -> list[dict]:
    return aws.dynamodb.scan(TableName=aws.config.table_name)["Items"]


def _profundidade(aws, url: str) -> int:
    attrs = aws.sqs.get_queue_attributes(
        QueueUrl=url,
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
        ],
    )["Attributes"]
    return int(attrs["ApproximateNumberOfMessages"]) + int(
        attrs["ApproximateNumberOfMessagesNotVisible"]
    )


# --------------------------------------------------------------------------- #
# Caminho feliz
# --------------------------------------------------------------------------- #


def test_ingere_os_seis_eventos_reais(aws, consumer, sample_events):
    for raw in sample_events.values():
        _enviar(aws, raw)

    escritos = consumer.run_once()

    assert escritos == 6
    assert len(_itens(aws)) == 6
    assert _profundidade(aws, aws.config.queue_url) == 0
    assert _profundidade(aws, aws.config.dlq_url) == 0


def test_uma_mensagem_com_varios_eventos(aws, consumer, sample_events):
    _enviar(aws, list(sample_events.values()))

    assert consumer.run_once() == 6
    assert len(_itens(aws)) == 6


def test_envelope_com_chave_events(aws, consumer, sample_events):
    _enviar(aws, {"events": list(sample_events.values())})

    assert consumer.run_once() == 6
    assert len(_itens(aws)) == 6


def test_item_gravado_tem_as_chaves_de_indice(aws, consumer, sample_events):
    _enviar(aws, sample_events["error"])
    consumer.run_once()

    item = _itens(aws)[0]
    assert item["pk"]["S"].startswith("SESSION#")
    assert item["gsi1pk"]["S"].startswith("EVT#error#2026-07-13#")
    assert item["gsi2pk"]["S"].startswith("DEV#")
    assert "expires_at" in item
    assert "ingested_at" in item


def test_duration_float_vira_number_no_dynamo(aws, consumer, sample_events):
    """DynamoDB nao tem float; se a conversao falhar, o put quebra."""
    _enviar(aws, sample_events["session"])
    consumer.run_once()

    item = _itens(aws)[0]
    assert item["duration"]["N"] == "6.486"


def test_query_por_sessao_devolve_a_linha_do_tempo(aws, consumer, sample_events):
    sessao = sample_events["error"]["session_id"]
    for i in range(3):
        _enviar(aws, dict(sample_events["error"], duration=float(i)))
    consumer.run_once()

    resposta = aws.dynamodb.query(
        TableName=aws.config.table_name,
        KeyConditionExpression="pk = :pk",
        ExpressionAttributeValues={":pk": {"S": f"SESSION#{sessao}"}},
    )
    assert resposta["Count"] == 3
    sks = [i["sk"]["S"] for i in resposta["Items"]]
    assert sks == sorted(sks)


def test_query_na_gsi1_por_tipo_e_dia(aws, consumer, sample_events):
    _enviar(aws, sample_events["error"])
    consumer.run_once()

    item = _itens(aws)[0]
    resposta = aws.dynamodb.query(
        TableName=aws.config.table_name,
        IndexName="gsi1",
        KeyConditionExpression="gsi1pk = :pk",
        ExpressionAttributeValues={":pk": {"S": item["gsi1pk"]["S"]}},
    )
    assert resposta["Count"] == 1


# --------------------------------------------------------------------------- #
# Idempotencia
# --------------------------------------------------------------------------- #


def test_evento_repetido_no_mesmo_lote_nao_derruba_a_escrita(
    aws, consumer, sample_events
):
    """Regressao: BatchWriteItem rejeita o lote INTEIRO se ha chave repetida.

    Como a chave deriva do hash do conteudo, reentrega do SQS colide de
    proposito -- entao duplicata no mesmo lote e rotina, e sem deduplicacao
    antes do batch ela levaria os outros itens junto.
    """
    _enviar(
        aws, [sample_events["error"], sample_events["error"], sample_events["vitals"]]
    )

    escritos = consumer.run_once()

    assert escritos == 2, "duplicata deveria colapsar, nao derrubar o lote"
    assert len(_itens(aws)) == 2
    assert _profundidade(aws, aws.config.dlq_url) == 0


def test_evento_repetido_em_mensagens_distintas_nao_duplica(aws, consumer, sample_events):
    """SQS e at-least-once; a chave por hash do conteudo absorve a reentrega."""
    _enviar(aws, sample_events["error"])
    _enviar(aws, sample_events["error"])

    # Drena: o receive pode devolver 1 ou 2 mensagens por chamada.
    while _profundidade(aws, aws.config.queue_url):
        consumer.run_once()

    assert len(_itens(aws)) == 1


def test_reprocessar_o_mesmo_evento_depois_tambem_nao_duplica(
    aws, consumer, sample_events
):
    _enviar(aws, sample_events["error"])
    consumer.run_once()
    _enviar(aws, sample_events["error"])
    consumer.run_once()

    assert len(_itens(aws)) == 1


# --------------------------------------------------------------------------- #
# Payload ruim -> DLQ
# --------------------------------------------------------------------------- #


def test_json_quebrado_vai_para_a_dlq_e_sai_da_fila(aws, consumer):
    _enviar(aws, "{isso nao e json")

    consumer.run_once()

    assert _profundidade(aws, aws.config.queue_url) == 0
    assert _profundidade(aws, aws.config.dlq_url) == 1
    assert _itens(aws) == []


def test_dlq_carrega_o_motivo_da_falha(aws, consumer):
    _enviar(aws, "{isso nao e json")
    consumer.run_once()

    msg = aws.sqs.receive_message(
        QueueUrl=aws.config.dlq_url, MessageAttributeNames=["All"]
    )["Messages"][0]
    assert "JSON invalido" in msg["MessageAttributes"]["FailureReason"]["StringValue"]
    assert msg["MessageAttributes"]["SourceMessageId"]["StringValue"]
    assert msg["Body"] == "{isso nao e json"  # payload original preservado


def test_evento_sem_envelope_minimo_vai_para_a_dlq(aws, consumer):
    _enviar(aws, {"event_name": "vitals", "session_id": "s1"})  # sem timestamp/device

    consumer.run_once()

    assert _profundidade(aws, aws.config.dlq_url) == 1
    assert _itens(aws) == []


def test_corpo_vazio_vai_para_a_dlq(aws, consumer):
    _enviar(aws, "   ")
    consumer.run_once()
    assert _profundidade(aws, aws.config.dlq_url) == 1


def test_evento_ruim_no_meio_do_lote_nao_derruba_os_bons(aws, consumer, sample_events):
    """Um evento invalido nao pode custar os outros da mesma mensagem."""
    _enviar(aws, [sample_events["error"], {"nada": "aqui"}, sample_events["vitals"]])

    consumer.run_once()

    assert len(_itens(aws)) == 2
    assert _profundidade(aws, aws.config.dlq_url) == 1
    assert _profundidade(aws, aws.config.queue_url) == 0


def test_item_gigante_vai_para_a_dlq_em_vez_de_travar(aws, consumer, sample_events):
    """Item acima de 400 KB nunca passa; retry so repetiria a falha para sempre."""
    gordo = dict(sample_events["error"], error_stack="x" * 400_000)
    _enviar(aws, gordo)

    consumer.run_once()

    assert _itens(aws) == []
    assert _profundidade(aws, aws.config.dlq_url) == 1
    assert _profundidade(aws, aws.config.queue_url) == 0


def test_tipo_desconhecido_e_gravado_e_nao_vai_para_a_dlq(aws, consumer):
    _enviar(
        aws,
        {
            "timestamp": "2026-07-13T23:04:44Z",
            "event_name": "ad_impression",
            "session_id": "s1",
            "device_id": "d1",
        },
    )

    assert consumer.run_once() == 1
    assert _profundidade(aws, aws.config.dlq_url) == 0
    assert _itens(aws)[0]["gsi1pk"]["S"].startswith("EVT#ad_impression#")


# --------------------------------------------------------------------------- #
# Falha de escrita -> mensagem fica na fila
# --------------------------------------------------------------------------- #


def test_falha_de_escrita_segura_o_delete(aws, consumer, sample_events, monkeypatch):
    """Sem escrita confirmada, a mensagem tem que voltar para o redrive."""
    monkeypatch.setattr(
        consumer._repo, "put_many", lambda items: {f"{i['pk']}|{i['sk']}" for i in items}
    )
    _enviar(aws, sample_events["error"])

    consumer.run_once()

    assert _profundidade(aws, aws.config.queue_url) == 1
    assert _profundidade(aws, aws.config.dlq_url) == 0


def test_falha_ao_enviar_para_a_dlq_segura_o_delete(aws, consumer, monkeypatch):
    """Se nem a DLQ aceita, nao podemos apagar: seria perda silenciosa."""
    from botocore.exceptions import ClientError

    def explode(**_kwargs):
        raise ClientError({"Error": {"Code": "InternalError"}}, "SendMessage")

    # Enfileira ANTES de quebrar o send_message, senao o proprio setup falha.
    _enviar(aws, "{json quebrado")
    monkeypatch.setattr(consumer._sqs, "send_message", explode)

    consumer.run_once()

    assert _profundidade(aws, aws.config.queue_url) == 1


def test_escrita_parcial_so_segura_a_mensagem_afetada(
    aws, consumer, sample_events, monkeypatch
):
    ruim = dict(sample_events["error"], duration=99.0)
    _enviar(aws, sample_events["vitals"])
    _enviar(aws, ruim)

    from argus_worker.keys import build_item
    from argus_worker.models import parse_event

    evento, _ = parse_event(ruim)
    item = build_item(
        evento,
        ingested_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        retention_days=90,
        gsi1_shards=aws.config.gsi1_shards,
        max_clock_skew_days=365,
    )
    chave_ruim = f"{item['pk']}|{item['sk']}"

    original = consumer._repo.put_many
    monkeypatch.setattr(
        consumer._repo,
        "put_many",
        lambda items: {chave_ruim} if original(items) is not None else set(),
    )

    consumer.run_once()

    # a mensagem boa saiu, a ruim ficou
    assert _profundidade(aws, aws.config.queue_url) == 1


# --------------------------------------------------------------------------- #
# Operacao
# --------------------------------------------------------------------------- #


def test_fila_vazia_nao_escreve_nada(aws, consumer):
    assert consumer.run_once() == 0
    assert _itens(aws) == []


def test_heartbeat_e_atualizado_mesmo_com_fila_vazia(aws, consumer):
    """O healthcheck nao pode confundir fila vazia com worker travado."""
    from pathlib import Path

    consumer.run_once()

    assert Path(aws.config.heartbeat_path).exists()


def test_sigterm_encerra_o_loop(aws, consumer, sample_events):
    import signal

    _enviar(aws, sample_events["error"])
    consumer._request_stop(signal.SIGTERM, None)
    consumer.run()  # tem que retornar sozinho

    assert consumer._running is False


# --------------------------------------------------------------------------- #
# Parsing do corpo
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "body,esperado",
    [
        ('{"a":1}', 1),
        ('[{"a":1},{"a":2}]', 2),
        ('{"events":[{"a":1},{"a":2},{"a":3}]}', 3),
    ],
)
def test_extract_events_aceita_as_tres_formas(body, esperado):
    assert len(_extract_events(body)) == esperado


@pytest.mark.parametrize("body", ["", "   ", "nao json", "[]", "123", '"texto"'])
def test_extract_events_rejeita_corpo_invalido(body):
    with pytest.raises(ValueError):
        _extract_events(body)
