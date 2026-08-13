from __future__ import annotations

from datetime import UTC, datetime, timedelta

from argus_worker.keys import build_event_id, build_item, shard_for
from argus_worker.models import parse_event

INGESTED_AT = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)

BUILD_KWARGS = {
    "ingested_at": INGESTED_AT,
    "retention_days": 90,
    "gsi1_shards": 10,
    "max_clock_skew_days": 365,
}


def _item(raw: dict, **overrides):
    event, _ = parse_event(raw)
    return build_item(event, **{**BUILD_KWARGS, **overrides})


def test_event_id_e_deterministico(sample_events):
    a, _ = parse_event(sample_events["error"])
    b, _ = parse_event(sample_events["error"])
    assert build_event_id(a) == build_event_id(b)


def test_event_id_muda_com_o_conteudo(sample_events):
    a, _ = parse_event(sample_events["error"])
    modificado = dict(sample_events["error"], error_message="outra coisa")
    b, _ = parse_event(modificado)
    assert build_event_id(a) != build_event_id(b)


def test_event_id_do_cliente_tem_prioridade(sample_events):
    raw = dict(sample_events["error"], event_id="id-fornecido-pelo-cliente")
    event, _ = parse_event(raw)
    assert build_event_id(event) == "id-fornecido-pelo-cliente"


def test_chaves_da_tabela_e_dos_indices(sample_events):
    item = _item(sample_events["error"])
    assert item["pk"] == "SESSION#0e04ba2e-c2df-4ec0-9c1b-a752caf2e7fa"
    assert item["sk"].startswith("2026-07-13T23:04:11.000Z#")
    assert item["gsi1pk"].startswith("EVT#error#2026-07-13#")
    assert item["gsi2pk"] == "DEV#F4Ed5f8a0cff"
    assert item["gsi1sk"] == item["sk"]
    assert item["gsi2sk"] == item["sk"]


def test_sort_key_ordena_cronologicamente(sample_events):
    """A sk precisa ordenar por tempo como texto, senao a query da sessao mente."""
    sks = sorted(_item(raw)["sk"] for raw in sample_events.values())
    horarios = [sk.split("#")[0] for sk in sks]
    assert horarios == sorted(horarios)
    assert horarios[0].startswith("2026-07-13T23:04:11")  # error, o mais antigo
    assert horarios[-1].startswith("2026-07-13T23:06:07")  # vitals, o mais novo


def test_shard_distribui_e_e_estavel():
    import hashlib

    # Precisa ser hash de verdade: o shard le event_id[:8], entao ids
    # sequenciais tem prefixo identico e cairiam todos no mesmo shard.
    ids = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(1000)]
    shards = [shard_for(i, 10) for i in ids]

    assert set(shards) == set(range(10)), "shard nao esta distribuindo"
    # nenhum shard pode concentrar mais que o dobro da media
    for shard in range(10):
        assert shards.count(shard) < 200
    # mesmo id, mesmo shard, sempre
    assert shard_for(ids[7], 10) == shard_for(ids[7], 10)


def test_shard_unico_desliga_o_sharding():
    assert shard_for("ffffffff", 1) == 0


def test_ttl_conta_da_ingestao_nao_do_evento(sample_events):
    """Replay de dado historico nao pode nascer expirado."""
    item = _item(sample_events["error"], retention_days=90)
    esperado = int((INGESTED_AT + timedelta(days=90)).timestamp())
    assert item["expires_at"] == esperado
    assert item["expires_at"] > INGESTED_AT.timestamp()


def test_clock_skew_grosseiro_e_sinalizado():
    item = _item(
        {
            "timestamp": "1970-01-01T00:00:00Z",  # relogio de TV zerado
            "event_name": "vitals",
            "session_id": "s1",
            "device_id": "d1",
        }
    )
    assert item["clock_skew"] is True
    assert item["clock_skew_days"] > 365


def test_replay_historico_normal_nao_e_sinalizado(sample_events):
    """Evento de 30 dias atras e replay legitimo, nao relogio quebrado."""
    item = _item(sample_events["error"])
    assert "clock_skew" not in item


def test_campos_do_evento_sao_preservados_no_item(sample_events):
    item = _item(sample_events["session"])
    assert item["capabilities_https"] is True
    assert item["device_user_agent"].startswith("Opera/9.80")
    assert item["duration"] == 6.486
    assert item["event_date"] == "2026-07-13"
