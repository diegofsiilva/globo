"""Testes dos dois consumidores contra um PostgreSQL de verdade.

O que estes testes protegem, em ordem de importancia:

  1. A regra do `_lsn` maior -- evento fora de ordem nao sobrescreve.
  2. O `_extra` -- coluna nova da origem nao e perdida nem quebra a ingestao.
  3. A idempotencia -- reentrega do SQS nao duplica nem corrompe.
  4. A quarentena -- payload ruim vai para a DLQ e sai da fila, em vez de
     queimar as cinco tentativas do redrive para chegar no mesmo lugar.
"""

from __future__ import annotations

import json

import pytest

CHANGE_BASE = {
    "source_table": "signal_bucket",
    "op": "r",
    "pk": {
        "bts": 1784904300000,
        "source": "prometheus",
        "entity": "pop-fortaleza",
        "metric": "p95_ms",
    },
    "after": {
        "bts": 1784904300000,
        "source": "prometheus",
        "entity": "pop-fortaleza",
        "metric": "p95_ms",
        "value": 368.0,
    },
    "captured_at": "2026-07-24T12:05:00Z",
}


def _send(aws, fila: str, corpo) -> None:
    aws.sqs.send_message(
        QueueUrl=aws.filas[fila],
        MessageBody=corpo if isinstance(corpo, str) else json.dumps(corpo),
    )


def _dlq(aws, fila: str) -> list[dict]:
    return aws.sqs.receive_message(
        QueueUrl=aws.filas[fila], MaxNumberOfMessages=10, MessageAttributeNames=["All"]
    ).get("Messages", [])


def _restam(aws, fila: str) -> int:
    attrs = aws.sqs.get_queue_attributes(
        QueueUrl=aws.filas[fila],
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
        ],
    )["Attributes"]
    return int(attrs["ApproximateNumberOfMessages"]) + int(
        attrs["ApproximateNumberOfMessagesNotVisible"]
    )


# --------------------------------------------------------------------------- #
# Merge worker: o caminho feliz
# --------------------------------------------------------------------------- #


def test_change_event_chega_no_log_e_na_bronze(aws, merge_consumer, db):
    _send(aws, "argus-changes", CHANGE_BASE)
    merge_consumer.run_once()

    assert db.fetch_one("SELECT count(*) AS n FROM bronze.change_log")["n"] == 1
    linha = db.fetch_one("SELECT value, _op FROM bronze.signal_bucket")
    assert linha["value"] == 368.0
    assert linha["_op"] == "r"


def test_uma_mensagem_com_varios_changes(aws, merge_consumer, db):
    outro = {
        **CHANGE_BASE,
        "pk": {**CHANGE_BASE["pk"], "metric": "p99_ms"},
        "after": {**CHANGE_BASE["after"], "metric": "p99_ms", "value": 512.0},
    }
    _send(aws, "argus-changes", [CHANGE_BASE, outro])
    merge_consumer.run_once()
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.signal_bucket")["n"] == 2


def test_envelope_com_chave_changes(aws, merge_consumer, db):
    _send(aws, "argus-changes", {"changes": [CHANGE_BASE]})
    merge_consumer.run_once()
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.signal_bucket")["n"] == 1


def test_update_sobrescreve_a_versao_anterior(aws, merge_consumer, db):
    _send(aws, "argus-changes", CHANGE_BASE)
    merge_consumer.run_once()

    atualizado = {
        **CHANGE_BASE,
        "op": "u",
        "before": CHANGE_BASE["after"],
        "after": {**CHANGE_BASE["after"], "value": 412.0},
        "captured_at": "2026-07-24T12:20:00Z",
    }
    _send(aws, "argus-changes", atualizado)
    merge_consumer.run_once()

    assert db.fetch_one("SELECT count(*) AS n FROM bronze.signal_bucket")["n"] == 1
    assert db.fetch_one("SELECT value FROM bronze.signal_bucket")["value"] == 412.0


def test_delete_remove_a_linha(aws, merge_consumer, db):
    _send(aws, "argus-changes", CHANGE_BASE)
    merge_consumer.run_once()

    _send(
        aws,
        "argus-changes",
        {**CHANGE_BASE, "op": "d", "before": CHANGE_BASE["after"], "after": None},
    )
    merge_consumer.run_once()

    assert db.fetch_one("SELECT count(*) AS n FROM bronze.signal_bucket")["n"] == 0
    # Mas o log guarda as duas: e o que permite o replay reconstruir a historia.
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.change_log")["n"] == 2


# --------------------------------------------------------------------------- #
# As tres propriedades que sustentam a arquitetura
# --------------------------------------------------------------------------- #


def test_coluna_desconhecida_cai_no_extra_sem_quebrar(aws, merge_consumer, db):
    """A decisao 4 do plano em um teste.

    A Globo pode acrescentar coluna a qualquer momento. Ela tem que ser
    preservada, sem DDL e sem derrubar a ingestao.
    """
    _send(
        aws,
        "argus-changes",
        {
            **CHANGE_BASE,
            "after": {**CHANGE_BASE["after"], "confidence": 0.93, "pod": "prom-7f9"},
        },
    )
    merge_consumer.run_once()

    linha = db.fetch_one("SELECT value, _extra FROM bronze.signal_bucket")
    assert linha["value"] == 368.0
    assert linha["_extra"] == {"confidence": 0.93, "pod": "prom-7f9"}


def test_evento_fora_de_ordem_nao_sobrescreve(aws, merge_consumer, db):
    """A regra do `_lsn` maior.

    Duas mudancas da mesma linha no MESMO lote: o ON CONFLICT do PostgreSQL
    recusaria a instrucao inteira sem o DISTINCT ON, e sem a regra do lsn a
    versao que sobrasse seria arbitraria. Tem que sobrar a mais nova.
    """
    antiga = {**CHANGE_BASE, "op": "u", "after": {**CHANGE_BASE["after"], "value": 100.0}}
    nova = {**CHANGE_BASE, "op": "u", "after": {**CHANGE_BASE["after"], "value": 999.0}}
    _send(aws, "argus-changes", [antiga, nova])
    merge_consumer.run_once()

    assert db.fetch_one("SELECT value FROM bronze.signal_bucket")["value"] == 999.0


def test_reentrega_do_sqs_nao_duplica_nem_corrompe(aws, merge_consumer, db):
    """At-least-once do SQS + escrita idempotente = efeito de exactly-once."""
    _send(aws, "argus-changes", CHANGE_BASE)
    merge_consumer.run_once()
    _send(aws, "argus-changes", CHANGE_BASE)
    merge_consumer.run_once()

    assert db.fetch_one("SELECT count(*) AS n FROM bronze.signal_bucket")["n"] == 1
    assert db.fetch_one("SELECT value FROM bronze.signal_bucket")["value"] == 368.0


# --------------------------------------------------------------------------- #
# Merge worker: quarentena
# --------------------------------------------------------------------------- #


def test_tabela_desconhecida_vai_para_a_dlq(aws, merge_consumer, db):
    """Tabela nova exige migration; coluna nova nao. O erro tem que dizer qual e."""
    _send(aws, "argus-changes", {**CHANGE_BASE, "source_table": "tabela_inventada"})
    merge_consumer.run_once()

    mensagens = _dlq(aws, "argus-changes-dlq")
    assert len(mensagens) == 1
    motivo = mensagens[0]["MessageAttributes"]["FailureReason"]["StringValue"]
    assert "tabela_inventada" in motivo
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.change_log")["n"] == 0


def test_op_invalida_vai_para_a_dlq(aws, merge_consumer):
    _send(aws, "argus-changes", {**CHANGE_BASE, "op": "x"})
    merge_consumer.run_once()
    assert len(_dlq(aws, "argus-changes-dlq")) == 1


def test_update_sem_after_vai_para_a_dlq(aws, merge_consumer):
    """Sem `after`, o MERGE ignoraria a linha em silencio e a mudanca sumiria."""
    _send(aws, "argus-changes", {**CHANGE_BASE, "op": "u", "after": None})
    merge_consumer.run_once()
    mensagens = _dlq(aws, "argus-changes-dlq")
    assert len(mensagens) == 1
    assert "after" in mensagens[0]["MessageAttributes"]["FailureReason"]["StringValue"]


def test_pk_vazia_vai_para_a_dlq(aws, merge_consumer):
    _send(aws, "argus-changes", {**CHANGE_BASE, "pk": {}})
    merge_consumer.run_once()
    assert len(_dlq(aws, "argus-changes-dlq")) == 1


def test_json_quebrado_vai_para_a_dlq_e_sai_da_fila(aws, merge_consumer):
    _send(aws, "argus-changes", "{isso nao e json")
    merge_consumer.run_once()
    assert len(_dlq(aws, "argus-changes-dlq")) == 1
    assert _restam(aws, "argus-changes") == 0


def test_change_ruim_no_meio_do_lote_nao_derruba_os_bons(aws, merge_consumer, db):
    ruim = {**CHANGE_BASE, "source_table": "nao_existe"}
    _send(aws, "argus-changes", [CHANGE_BASE, ruim])
    merge_consumer.run_once()

    assert db.fetch_one("SELECT count(*) AS n FROM bronze.signal_bucket")["n"] == 1
    assert len(_dlq(aws, "argus-changes-dlq")) == 1


# --------------------------------------------------------------------------- #
# Merge worker: metricas do pipeline
# --------------------------------------------------------------------------- #


def test_lag_sim_mede_tempo_virtual(aws, merge_consumer, db):
    """O relogio esta em 12:00 e a mudanca foi observada as 12:05.

    O `captured_at` esta a frente do relogio virtual, entao o lag e NEGATIVO --
    o pipeline esta adiantado, nao atrasado. O que importa e que a medida sai em
    tempo virtual, e nao de parede.
    """
    _send(aws, "argus-changes", CHANGE_BASE)
    merge_consumer.run_once()
    assert merge_consumer._repo.lag_sim_seconds() == pytest.approx(-300, abs=5)


def test_lag_e_nulo_quando_o_log_esta_vazio(merge_consumer):
    """Nao ha atraso a medir num pipeline que nunca recebeu nada."""
    assert merge_consumer._repo.lag_sim_seconds() is None


def test_lag_continua_sendo_emitido_com_fila_vazia(aws, merge_consumer, monkeypatch):
    """Repouso da fila nao pode virar ausencia de metrica no CloudWatch."""
    chamadas = {"lag": 0, "fontes": 0}

    def lag():
        chamadas["lag"] += 1
        return 0.0

    def fontes():
        chamadas["fontes"] += 1
        return 0

    monkeypatch.setattr(merge_consumer._repo, "lag_sim_seconds", lag)
    monkeypatch.setattr(merge_consumer._repo, "sources_silent", fontes)

    merge_consumer.run_once()
    merge_consumer.run_once()

    assert chamadas == {"lag": 1, "fontes": 1}


# --------------------------------------------------------------------------- #
# Event worker
# --------------------------------------------------------------------------- #


def test_ingere_os_seis_eventos_reais(aws, event_consumer, db, sample_events):
    for evento in sample_events.values():
        _send(aws, "argus-events", evento)
    for _ in sample_events:
        event_consumer.run_once()

    total = db.fetch_one("SELECT count(*) AS n FROM bronze.event")["n"]
    assert total == len(sample_events)


def test_evento_repetido_nao_duplica(aws, event_consumer, db, sample_events):
    _send(aws, "argus-events", sample_events["error"])
    event_consumer.run_once()
    _send(aws, "argus-events", sample_events["error"])
    event_consumer.run_once()

    assert db.fetch_one("SELECT count(*) AS n FROM bronze.event")["n"] == 1


def test_evento_repetido_no_mesmo_lote_nao_derruba_a_escrita(
    aws, event_consumer, db, sample_events
):
    _send(aws, "argus-events", [sample_events["error"], sample_events["error"]])
    event_consumer.run_once()
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.event")["n"] == 1


def test_tipo_desconhecido_e_gravado_e_nao_vai_para_a_dlq(aws, event_consumer, db):
    """RF03: o parque de TVs atualiza devagar; schema estrito perderia dado em massa."""
    _send(
        aws,
        "argus-events",
        {
            "timestamp": "2026-07-24T12:00:00Z",
            "event_name": "tipo_que_ainda_nao_existe",
            "session_id": "s-1",
            "device_id": "d-1",
            "campo_novo": "valor",
        },
    )
    event_consumer.run_once()

    linha = db.fetch_one("SELECT event_name, payload FROM bronze.event")
    assert linha["event_name"] == "tipo_que_ainda_nao_existe"
    assert linha["payload"]["campo_novo"] == "valor"
    assert _dlq(aws, "argus-events-dlq") == []


def test_evento_sem_envelope_minimo_vai_para_a_dlq(aws, event_consumer, db):
    _send(aws, "argus-events", {"event_name": "request"})  # sem timestamp/session/device
    event_consumer.run_once()
    assert len(_dlq(aws, "argus-events-dlq")) == 1
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.event")["n"] == 0


def test_corpo_vazio_vai_para_a_dlq(aws, event_consumer):
    _send(aws, "argus-events", "")
    event_consumer.run_once()
    assert len(_dlq(aws, "argus-events-dlq")) == 1


# --------------------------------------------------------------------------- #
# Ciclo de vida
# --------------------------------------------------------------------------- #


def test_fila_vazia_nao_escreve_nada(aws, merge_consumer, db):
    assert merge_consumer.run_once() == 0
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.change_log")["n"] == 0


def test_heartbeat_e_atualizado_mesmo_com_fila_vazia(aws, merge_consumer):
    """Fila vazia nao pode ser confundida com processo travado.

    Sem isto, um worker saudavel num domingo de madrugada seria morto em laco
    pelo healthcheck da task definition.
    """
    from pathlib import Path

    merge_consumer.run_once()
    assert Path(aws.config_merge.heartbeat_path).exists()


def test_falha_de_escrita_segura_o_delete(aws, merge_consumer, monkeypatch):
    """Sem gravar, a mensagem NAO sai da fila -- e o SQS reentrega."""
    import psycopg

    def explode(*_args, **_kwargs):
        raise psycopg.OperationalError("banco caiu no meio do lote")

    _send(aws, "argus-changes", CHANGE_BASE)
    monkeypatch.setattr(merge_consumer._repo, "append_and_merge", explode)

    with pytest.raises(psycopg.OperationalError):
        merge_consumer.run_once()

    assert _restam(aws, "argus-changes") == 1


def test_registro_recusado_pelo_banco_nao_paralisa_a_fila(aws, merge_consumer, db):
    """Um change event malformado NAO pode travar toda a ingestao de mudancas.

    Regressao de producao: um unico registro sem uma coluna NOT NULL abortava a
    transacao do lote inteiro. Como append e MERGE estao na mesma transacao, nada
    era apagado da fila, o SQS reentregava, e a mesma falha se repetia -- de tres
    em tres minutos, para sempre. O ciclo passou a demorar mais que o healthcheck
    e o ECS matou o worker em laco. Um registro ruim derrubou o pipeline.

    O certo e o veneno ir para a DLQ e os vizinhos passarem.
    """
    veneno = {
        **CHANGE_BASE,
        # `bts` e da chave primaria e e NOT NULL. Sem ele, o
        # `jsonb_populate_record` do MERGE produz NULL e o banco recusa.
        "pk": {**CHANGE_BASE["pk"], "bts": 9_999_999_999_999},
        "after": {k: v for k, v in CHANGE_BASE["after"].items() if k != "bts"},
    }
    _send(aws, "argus-changes", veneno)
    _send(aws, "argus-changes", CHANGE_BASE)

    merge_consumer.run_once()

    # O bom entrou.
    assert db.fetch_one("SELECT count(*) AS n FROM bronze.signal_bucket")["n"] == 1
    # O ruim saiu da fila principal e foi para a DLQ, com o motivo anexado.
    assert _restam(aws, "argus-changes") == 0
    assert _restam(aws, "argus-changes-dlq") == 1


def test_banco_fora_do_ar_nao_manda_nada_para_a_dlq(aws, merge_consumer, monkeypatch):
    """Indisponibilidade e o oposto de registro ruim: o dado tem de ser mantido.

    A quarentena existe para dado que NUNCA vai passar. Aplicar a mesma regra a
    uma queda de banco jogaria fora dado perfeitamente valido.
    """
    import psycopg

    def explode(*_args, **_kwargs):
        raise psycopg.OperationalError("banco caiu")

    _send(aws, "argus-changes", CHANGE_BASE)
    monkeypatch.setattr(merge_consumer._repo, "append_and_merge", explode)

    with pytest.raises(psycopg.OperationalError):
        merge_consumer.run_once()

    assert _restam(aws, "argus-changes") == 1
    assert _restam(aws, "argus-changes-dlq") == 0


def test_sigterm_encerra_o_loop(aws, merge_consumer):
    import os
    import signal
    import threading

    def manda_sigterm():
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Timer(0.2, manda_sigterm).start()
    merge_consumer.run()  # tem que retornar sozinho


# --------------------------------------------------------------------------- #
# Parsing do corpo
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("body", "chave", "esperado"),
    [
        ('{"a": 1}', "changes", 1),
        ('[{"a": 1}, {"b": 2}]', "changes", 2),
        ('{"changes": [{"a": 1}, {"b": 2}]}', "changes", 2),
        ('{"events": [{"a": 1}]}', "events", 1),
    ],
)
def test_extract_aceita_as_tres_formas(body, chave, esperado):
    from argus_worker.consumer import _extract

    assert len(_extract(body, chave)) == esperado


@pytest.mark.parametrize("body", ["", "   ", "{quebrado", "[]", "null", "42"])
def test_extract_rejeita_corpo_invalido(body):
    from argus_worker.consumer import _extract

    with pytest.raises(ValueError):
        _extract(body, "changes")
