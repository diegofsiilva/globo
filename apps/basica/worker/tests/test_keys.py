"""Testes da identidade do evento e da montagem da linha de bronze.event."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from argus_worker.keys import CAMPOS_ENVELOPE, build_event_id, build_row, clock_skew
from argus_worker.models import parse_event

INGESTED_AT = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)


def _linha(raw: dict, **overrides):
    event, _ = parse_event(raw)
    return build_row(event, **{"ingested_at": INGESTED_AT, **overrides})


# --------------------------------------------------------------------------- #
# Identidade
# --------------------------------------------------------------------------- #


def test_event_id_e_deterministico(sample_events):
    a, _ = parse_event(sample_events["error"])
    b, _ = parse_event(sample_events["error"])
    assert build_event_id(a) == build_event_id(b)


def test_event_id_muda_com_o_conteudo(sample_events):
    a, _ = parse_event(sample_events["error"])
    b, _ = parse_event(dict(sample_events["error"], error_message="outra coisa"))
    assert build_event_id(a) != build_event_id(b)


def test_event_id_do_cliente_tem_prioridade(sample_events):
    raw = dict(sample_events["error"], event_id="id-fornecido-pelo-cliente")
    event, _ = parse_event(raw)
    assert build_event_id(event) == "id-fornecido-pelo-cliente"


def test_ordem_das_chaves_no_json_nao_muda_o_id(sample_events):
    """JSON nao promete ordem de chave, entao o id nao pode depender dela.

    Sem `sort_keys` na serializacao canonica, o mesmo evento reenviado com as
    chaves embaralhadas viraria uma duplicata em vez de colidir.
    """
    original = sample_events["request"]
    embaralhado = dict(reversed(list(original.items())))
    a, _ = parse_event(original)
    b, _ = parse_event(embaralhado)
    assert build_event_id(a) == build_event_id(b)


# --------------------------------------------------------------------------- #
# Relogio
# --------------------------------------------------------------------------- #


def test_clock_skew_grosseiro_e_sinalizado():
    futuro = datetime.now(UTC) + timedelta(days=400)
    assert clock_skew(futuro, max_days=365) is True


def test_replay_historico_normal_nao_e_sinalizado(sample_events):
    linha = _linha(sample_events["session"], max_clock_skew_days=36500)
    assert "clock_skew" not in linha["payload"]


def test_evento_com_relogio_errado_e_marcado_mas_nao_perdido(sample_events):
    raw = dict(
        sample_events["error"],
        timestamp=(datetime.now(UTC) + timedelta(days=400)).isoformat(),
    )
    linha = _linha(raw, max_clock_skew_days=365)
    # Marcado...
    assert linha["payload"]["clock_skew"] is True
    # ...mas presente. Descartar perderia justamente o aparelho com problema.
    assert linha["event_id"]
    assert linha["session_id"]


# --------------------------------------------------------------------------- #
# Envelope x payload
# --------------------------------------------------------------------------- #


def test_envelope_vira_coluna_e_o_resto_vira_payload(sample_events):
    linha = _linha(sample_events["request"])
    assert linha["event_name"] == "request"
    assert linha["session_id"]
    # Os campos especificos do tipo nao viram coluna.
    assert not (set(linha["payload"]) & CAMPOS_ENVELOPE)


def test_campos_especificos_do_tipo_sobrevivem_no_payload(sample_events):
    linha = _linha(sample_events["request"])
    assert any(k.startswith("request_") for k in linha["payload"]), linha["payload"]


def test_timestamp_vira_a_coluna_ts(sample_events):
    linha = _linha(sample_events["video_view"])
    assert linha["ts"].tzinfo is not None
    assert "timestamp" not in linha


def test_route_params_em_texto_vira_dicionario(sample_events):
    raw = dict(sample_events["screen_view"], route_params='{"id": "42"}')
    assert _linha(raw)["route_params"] == {"id": "42"}


def test_route_params_ilegivel_e_preservado_em_vez_de_derrubar(sample_events):
    raw = dict(sample_events["screen_view"], route_params="nao-e-json{{{")
    assert _linha(raw)["route_params"] == {"raw": "nao-e-json{{{"}


def test_ano_do_modelo_em_texto_vira_inteiro(sample_events):
    raw = dict(sample_events["session"], device_model_year="2019")
    assert _linha(raw)["device_model_year"] == 2019


def test_ano_do_modelo_nao_numerico_e_preservado_no_payload(sample_events):
    """ "unknown" e valor REAL do parque, nao lixo.

    A coluna e integer, entao o texto nao cabe la. Mas descartar esta fora de
    questao -- e a mesma regra do `_extra` da bronze, de nunca perder o que a
    origem mandou. A coluna fica nula e o original vai para o payload.
    """
    linha = _linha(dict(sample_events["session"], device_model_year="unknown"))
    assert linha["device_model_year"] is None
    assert linha["payload"]["device_model_year"] == "unknown"


def test_nulo_nao_entra_no_payload(sample_events):
    linha = _linha(sample_events["vitals"])
    assert all(v is not None for v in linha["payload"].values())
