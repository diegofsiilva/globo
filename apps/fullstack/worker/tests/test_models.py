"""Testes de validação, tipagem e normalização dos eventos."""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from argus_worker.changes import parse_change
from argus_worker.models import (
    ErrorEvent,
    GenericEvent,
    RequestEvent,
    SessionEvent,
    VideoViewEvent,
    parse_event,
)


def test_todas_as_fixtures_reais_validam(sample_events):
    """Os seis eventos exportados do BI precisam passar sem ajuste manual."""
    for name, raw in sample_events.items():
        event, is_known = parse_event(raw)
        assert is_known, f"{name} deveria ser um tipo conhecido"
        assert event.event_name == raw["event_name"]


def test_dispatch_por_event_name(sample_events):
    assert isinstance(parse_event(sample_events["request"])[0], RequestEvent)
    assert isinstance(parse_event(sample_events["session"])[0], SessionEvent)
    assert isinstance(parse_event(sample_events["error"])[0], ErrorEvent)
    assert isinstance(parse_event(sample_events["video_view"])[0], VideoViewEvent)


def test_campos_especificos_sao_tipados(sample_events):
    session, _ = parse_event(sample_events["session"])
    assert session.capabilities_https is True
    assert session.capabilities_video_hdr is False
    assert session.device_user_agent.startswith("Opera/9.80")

    request, _ = parse_event(sample_events["request"])
    assert request.request_status == 200
    assert request.request_method == "GET"
    assert request.response_headers["x-request-id"]


def test_timestamp_normalizado_para_utc(sample_events):
    event, _ = parse_event(sample_events["request"])
    assert event.timestamp.tzinfo is not None
    assert event.timestamp.utcoffset().total_seconds() == 0
    # 20:04:44 America/Sao_Paulo == 23:04:44 UTC
    assert event.timestamp.hour == 23


def test_timestamp_ingenuo_vira_utc_em_vez_de_erro():
    event, _ = parse_event(
        {
            "timestamp": "2026-07-13T23:04:44",
            "event_name": "vitals",
            "session_id": "s1",
            "device_id": "d1",
        }
    )
    assert event.timestamp.tzinfo == UTC


def test_timestamp_com_offset_e_convertido():
    event, _ = parse_event(
        {
            "timestamp": "2026-07-13T20:04:44-03:00",
            "event_name": "vitals",
            "session_id": "s1",
            "device_id": "d1",
        }
    )
    assert event.timestamp.hour == 23


def test_tipo_desconhecido_vira_generico_em_vez_de_erro():
    """Evento novo no app precisa entrar hoje, nao depois de mexer no worker."""
    event, is_known = parse_event(
        {
            "timestamp": "2026-07-13T23:04:44Z",
            "event_name": "ad_impression",  # ainda nao existe
            "session_id": "s1",
            "device_id": "d1",
            "ad_provider": "gam",
        }
    )
    assert is_known is False
    assert isinstance(event, GenericEvent)
    assert event.event_name == "ad_impression"
    # o campo desconhecido sobrevive
    assert event.model_dump()["ad_provider"] == "gam"


def test_campo_novo_em_tipo_conhecido_e_preservado():
    event, is_known = parse_event(
        {
            "timestamp": "2026-07-13T23:04:44Z",
            "event_name": "error",
            "session_id": "s1",
            "device_id": "d1",
            "error_severity": "fatal",  # campo que o app passou a mandar
        }
    )
    assert is_known is True
    assert event.model_dump()["error_severity"] == "fatal"


@pytest.mark.parametrize(
    "faltando", ["timestamp", "event_name", "session_id", "device_id"]
)
def test_envelope_minimo_e_obrigatorio(faltando):
    raw = {
        "timestamp": "2026-07-13T23:04:44Z",
        "event_name": "vitals",
        "session_id": "s1",
        "device_id": "d1",
    }
    del raw[faltando]
    with pytest.raises(ValidationError):
        parse_event(raw)


def test_session_id_vazio_e_rejeitado():
    with pytest.raises(ValidationError):
        parse_event(
            {
                "timestamp": "2026-07-13T23:04:44Z",
                "event_name": "vitals",
                "session_id": "   ",
                "device_id": "d1",
            }
        )


def test_campo_opcional_ausente_nao_invalida():
    """Faltar app_version nao pode derrubar o evento -- so sinalizar."""
    event, _ = parse_event(
        {
            "timestamp": "2026-07-13T23:04:44Z",
            "event_name": "screen_view",
            "session_id": "s1",
            "device_id": "d1",
        }
    )
    assert event.app_version is None


def test_nao_dict_e_rejeitado():
    with pytest.raises(TypeError):
        parse_event(["nao", "sou", "objeto"])


@pytest.mark.parametrize(
    "source_table",
    [
        "app_error",
        "app_error_model",
        "app_error_version",
        "cdn_vod_shadow",
        "isp_pop_daily",
        "live_event_sde",
    ],
)
def test_fontes_novas_sao_aceitas_pelo_change_event(source_table):
    """Toda tabela bronze nova precisa atravessar a fronteira do worker."""
    evento = parse_change(
        {
            "source_table": source_table,
            "op": "i",
            "pk": {"id": "fixture"},
            "after": {"id": "fixture"},
            "captured_at": "2026-07-13T23:04:44Z",
        }
    )

    assert evento["source_table"] == source_table
