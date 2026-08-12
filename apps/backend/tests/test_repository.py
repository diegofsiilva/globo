"""Testes do adaptador DynamoDB contra o formato real de item."""

from datetime import UTC, datetime

import pytest

from telemetry.domain.exceptions import ValidationError
from telemetry.ports.event_repository import EventFilters
from tests.conftest import build_item

# --------------------------------------------------------------------------- #
# Compatibilidade com o que o worker grava
# --------------------------------------------------------------------------- #


def test_le_os_seis_tipos_reais(repository, seeded, sample_events):
    """Regressao: o backend anterior recusava screen_view e session."""
    page = repository.search(EventFilters(limit=50))

    nomes = {event.event_name for event in page.items}
    assert nomes == set(sample_events), f"faltou ler: {set(sample_events) - nomes}"


def test_event_id_e_hash_e_nao_uuid(repository, seeded):
    page = repository.search(EventFilters(limit=50))
    for event in page.items:
        assert len(event.event_id) == 64, "event_id do worker e sha256, nao UUID"
        int(event.event_id, 16)  # levanta se nao for hexadecimal


def test_device_model_year_aceita_texto(repository, seeded):
    """'unknown' e valor real do parque; recusar descartava dois tipos."""
    page = repository.search(EventFilters(event_name="session", limit=10))
    assert page.items[0].device_model_year == "unknown"


def test_campos_do_evento_error_sobrevivem(repository, seeded):
    """O dashboard mostra os tres; o backend anterior descartava todos."""
    page = repository.search(EventFilters(event_name="error", limit=10))
    attributes = page.items[0].attributes

    assert attributes["error_name"] == "Erro ao reproduzir vídeo"
    assert attributes["error_message"] == "Para assistir, tente carregar novamente"
    assert attributes["error_stack"] == "dash_shaka_playback:6_6002"


def test_campos_de_video_sobrevivem(repository, seeded):
    page = repository.search(EventFilters(event_name="video_view", limit=10))
    attributes = page.items[0].attributes

    assert attributes["media_id"] == "4452349"
    assert attributes["media_kind"] == "live"
    assert attributes["media_ads"] is True
    assert page.items[0].action == "open"


def test_capabilities_da_sessao_sobrevivem(repository, seeded):
    page = repository.search(EventFilters(event_name="session", limit=10))
    attributes = page.items[0].attributes

    assert attributes["capabilities_https"] is True
    assert attributes["capabilities_video_hdr"] is False


def test_duration_convertido_de_segundos_para_ms(repository, seeded):
    """O DynamoDB guarda segundos, como o app envia; o dashboard usa ms."""
    page = repository.search(EventFilters(event_name="request", limit=10))
    assert page.items[0].duration_ms == 33.0  # 0.033 s


def test_tipo_desconhecido_e_lido(repository, table):
    """O pipeline aceita event_name novo de proposito; a leitura tambem deve."""
    table.put_item(
        Item=build_item(
            {
                "timestamp": "2026-08-12T10:00:00Z",
                "event_name": "ad_impression",
                "session_id": "s-novo",
                "device_id": "d-novo",
                "ad_provider": "gam",
            }
        )
    )
    page = repository.search(EventFilters(limit=10))

    assert page.items[0].event_name == "ad_impression"
    assert page.items[0].attributes["ad_provider"] == "gam"


# --------------------------------------------------------------------------- #
# Privacidade na saida (RNF10)
# --------------------------------------------------------------------------- #


def test_user_id_sai_como_hash(repository, seeded, sample_events):
    page = repository.search(EventFilters(event_name="error", limit=10))
    event = page.items[0]

    assert event.user_id_hash is not None
    assert event.user_id_hash != sample_events["error"]["user_id"]
    assert sample_events["error"]["user_id"] not in str(event.attributes)


def test_header_authorization_nao_sai(repository, seeded):
    """O worker grava o header cru; a redacao acontece aqui, na leitura."""
    page = repository.search(EventFilters(event_name="request", limit=10))
    headers = page.items[0].attributes.get("request_headers", {})

    assert "authorization" not in headers
    assert "x-user-id" not in headers
    assert "x-client-version" in headers  # o que e seguro permanece


def test_response_headers_nao_saem(repository, seeded):
    page = repository.search(EventFilters(event_name="request", limit=10))
    assert "response_headers" not in page.items[0].attributes


# --------------------------------------------------------------------------- #
# Caminhos de acesso
# --------------------------------------------------------------------------- #


def test_busca_por_sessao_usa_a_tabela(repository, seeded, sample_events):
    sessao = sample_events["error"]["session_id"]
    page = repository.search(EventFilters(session_id=sessao, limit=10))

    assert page.stats.strategy == "table:session"
    assert page.stats.queries == 1
    assert all(event.session_id == sessao for event in page.items)


def test_busca_por_aparelho_usa_a_gsi2(repository, seeded, sample_events):
    aparelho = sample_events["error"]["device_id"]
    page = repository.search(EventFilters(device_id=aparelho, limit=10))

    assert page.stats.strategy == "gsi2:device"
    assert page.items[0].device_id == aparelho


def test_busca_por_tipo_usa_a_gsi1_com_fanout(repository, seeded):
    page = repository.search(
        EventFilters(
            event_name="error",
            occurred_from=datetime(2026, 7, 13, tzinfo=UTC),
            occurred_to=datetime(2026, 7, 14, tzinfo=UTC),
            limit=10,
        )
    )

    assert page.stats.strategy == "gsi1:fanout"
    # 2 dias x 4 shards
    assert page.stats.queries == 8
    assert len(page.items) == 1


def test_busca_sem_chave_cai_no_scan(repository, seeded):
    page = repository.search(EventFilters(limit=10))
    assert page.stats.strategy == "table:scan"


def test_filtros_cumulativos(repository, seeded):
    """RF09: mais de um filtro na mesma consulta."""
    page = repository.search(EventFilters(app_bucket="S3", device_os="Linux", limit=50))

    assert page.items, "esperava ao menos um evento S3 + Linux"
    for event in page.items:
        assert event.app_bucket == "S3"
        assert event.device_os == "Linux"


def test_filtro_por_periodo(repository, table, sample_events):
    antigo = dict(sample_events["error"], timestamp="2026-01-01T00:00:00Z")
    table.put_item(Item=build_item(antigo))
    table.put_item(Item=build_item(sample_events["error"]))

    page = repository.search(EventFilters(occurred_from=datetime(2026, 6, 1, tzinfo=UTC), limit=50))

    assert len(page.items) == 1
    assert page.items[0].occurred_at.year == 2026
    assert page.items[0].occurred_at.month == 7


def test_ordena_do_mais_recente_para_o_mais_antigo(repository, seeded):
    page = repository.search(EventFilters(limit=50))
    horarios = [event.occurred_at for event in page.items]
    assert horarios == sorted(horarios, reverse=True)


def test_get_exige_sessao(repository, seeded, sample_events):
    sessao = sample_events["error"]["session_id"]
    encontrado = repository.search(EventFilters(session_id=sessao, limit=1)).items[0]

    assert repository.get(sessao, encontrado.event_id) is not None
    assert repository.get("sessao-que-nao-existe", encontrado.event_id) is None


# --------------------------------------------------------------------------- #
# Paginacao por cursor
# --------------------------------------------------------------------------- #


def test_cursor_percorre_sem_repetir_nem_pular(repository, seeded):
    vistos = []
    cursor = None
    for _ in range(10):
        page = repository.search(EventFilters(limit=2, cursor=cursor))
        vistos.extend(event.event_id for event in page.items)
        cursor = page.next_cursor
        if not cursor:
            break

    assert len(vistos) == len(set(vistos)), "cursor repetiu evento"
    assert len(vistos) == 6, "cursor pulou evento"


def test_cursor_no_fanout_da_gsi1(repository, seeded, table, sample_events):
    for i in range(5):
        table.put_item(Item=build_item(dict(sample_events["error"], session_id=f"sessao-{i}")))

    vistos = []
    cursor = None
    for _ in range(10):
        page = repository.search(
            EventFilters(
                event_name="error",
                occurred_from=datetime(2026, 7, 13, tzinfo=UTC),
                occurred_to=datetime(2026, 7, 14, tzinfo=UTC),
                limit=2,
                cursor=cursor,
            )
        )
        vistos.extend(event.event_id for event in page.items)
        cursor = page.next_cursor
        if not cursor:
            break

    assert len(vistos) == len(set(vistos))
    assert len(vistos) == 6  # 5 novos + o original


def test_cursor_invalido_e_erro_do_cliente(repository, seeded):
    with pytest.raises(ValidationError):
        repository.search(EventFilters(cursor="nao-e-base64-valido!!!"))


# --------------------------------------------------------------------------- #
# Agregacao
# --------------------------------------------------------------------------- #


def test_breakdown_agrupa_e_conta(repository, seeded):
    grupos = repository.breakdown(EventFilters(limit=500), "event_name")

    assert sum(grupo.count for grupo in grupos) == 6
    assert {grupo.key for grupo in grupos} == {
        "request",
        "screen_view",
        "session",
        "video_view",
        "vitals",
        "error",
    }


def test_breakdown_por_fabricante(repository, seeded):
    grupos = repository.breakdown(EventFilters(limit=500), "device_manufacturer")
    chaves = {grupo.key for grupo in grupos}

    assert "Samsung" in chaves
    assert "Philco" in chaves


def test_breakdown_calcula_media_de_duracao(repository, seeded):
    grupos = repository.breakdown(EventFilters(limit=500), "event_name")
    request = next(grupo for grupo in grupos if grupo.key == "request")

    assert request.average_duration_ms == 33.0


def test_breakdown_recusa_dimensao_invalida(repository, seeded):
    with pytest.raises(ValueError):
        repository.breakdown(EventFilters(), "user_id")


def test_timeseries_agrupa_por_janela(repository, seeded):
    buckets = repository.timeseries(EventFilters(limit=500), interval_minutes=60)

    assert sum(bucket.count for bucket in buckets) == 6
    assert all(bucket.bucket.tzinfo is not None for bucket in buckets)


def test_timeseries_separa_por_tipo(repository, seeded):
    buckets = repository.timeseries(EventFilters(limit=500), interval_minutes=1440)
    total = {}
    for bucket in buckets:
        for nome, quantidade in bucket.by_event_name.items():
            total[nome] = total.get(nome, 0) + quantidade

    assert total["error"] == 1
    assert len(total) == 6


def test_facets_lista_valores_existentes(repository, seeded):
    """RF10: sugerir valores enquanto o usuario preenche os filtros."""
    facets = repository.facets(["event_name", "device_manufacturer"])

    assert set(facets["event_name"]) == {
        "request",
        "screen_view",
        "session",
        "video_view",
        "vitals",
        "error",
    }
    assert "Samsung" in facets["device_manufacturer"]


def test_facets_recusa_campo_invalido(repository, seeded):
    with pytest.raises(ValueError):
        repository.facets(["user_id"])


def test_ping(repository, table):
    assert repository.ping() is True


# --------------------------------------------------------------------------- #
# Guarda contra divergencia com o worker
# --------------------------------------------------------------------------- #


def test_formato_do_item_espelha_o_worker(sample_events):
    """Trava a duplicacao de logica entre conftest.build_item e o worker.

    Se o worker mudar o formato da chave e este teste nao acusar, a API passa a
    ler de particoes onde a escrita nao coloca nada -- e devolve vazio, sem
    erro. Comparamos com a implementacao real importada do worker.
    """
    import sys
    from pathlib import Path

    worker_src = Path(__file__).resolve().parents[2] / "worker" / "src"
    if str(worker_src) not in sys.path:
        sys.path.insert(0, str(worker_src))

    try:
        from argus_worker.keys import build_item as worker_build_item
        from argus_worker.models import parse_event
    except ImportError:
        pytest.skip("worker nao disponivel neste ambiente")

    ingested = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    for nome, raw in sample_events.items():
        evento, _ = parse_event(raw)
        esperado = worker_build_item(
            evento,
            ingested_at=ingested,
            retention_days=90,
            gsi1_shards=4,
            max_clock_skew_days=365,
        )
        obtido = build_item(raw, ingested_at=ingested)

        for chave in ("pk", "sk", "gsi1pk", "gsi1sk", "gsi2pk", "gsi2sk", "event_id"):
            assert obtido[chave] == esperado[chave], f"{nome}: divergencia em {chave}"
