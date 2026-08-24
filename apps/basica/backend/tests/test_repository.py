"""Testes do adaptador PostgreSQL contra o formato real que o worker grava."""

from datetime import timedelta

import pytest

from telemetry.ports.event_repository import EventFilters
from tests.conftest import REFERENCE_NOW

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
        assert len(event.event_id) == 32, "event_id do worker e hash, nao UUID"
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
    assert page.items[0].attributes


def test_duration_convertido_de_segundos_para_ms(repository, seeded):
    """O banco guarda em SEGUNDOS, como o app envia; a tela usa milissegundos."""
    page = repository.search(EventFilters(limit=50))
    com_duracao = [e for e in page.items if e.duration_ms is not None]
    assert com_duracao, "nenhuma fixture tem duration"
    for evento in com_duracao:
        assert evento.duration_ms > 1.0, "parece que veio em segundos, sem converter"


# --------------------------------------------------------------------------- #
# Privacidade (RNF10)
# --------------------------------------------------------------------------- #


def test_user_id_sai_como_hash(repository, seeded, sample_events):
    """O banco guarda o identificador cru; o hash acontece na LEITURA."""
    crus = {e.get("user_id") for e in sample_events.values() if e.get("user_id")}
    assert crus, "nenhuma fixture tem user_id"

    page = repository.search(EventFilters(limit=50))
    saidas = {e.user_id_hash for e in page.items if e.user_id_hash}
    assert saidas, "nenhum hash na saida"
    assert not (saidas & crus), "o identificador cru vazou na resposta"
    for hash_ in saidas:
        assert len(hash_) == 16


def test_o_mesmo_usuario_agrupa_no_mesmo_hash(repository, seeded):
    """Hash com salt fixo: agrupar por usuario continua possivel sem expor quem."""
    page = repository.search(EventFilters(limit=50))
    por_hash = {}
    for evento in page.items:
        if evento.user_id_hash:
            por_hash.setdefault(evento.user_id_hash, []).append(evento)
    assert por_hash


# --------------------------------------------------------------------------- #
# Estrategia de leitura
# --------------------------------------------------------------------------- #


def test_busca_por_sessao(repository, seeded, sample_events):
    alvo = next(e["session_id"] for e in sample_events.values())
    page = repository.search(EventFilters(session_id=alvo, limit=50))

    assert page.items
    assert all(e.session_id == alvo for e in page.items)
    assert page.stats.strategy == "indice_sessao"


def test_busca_por_aparelho(repository, seeded, sample_events):
    alvo = next(e["device_id"] for e in sample_events.values())
    page = repository.search(EventFilters(device_id=alvo, limit=50))

    assert page.items
    assert page.stats.strategy == "indice_aparelho"


def test_busca_por_tipo(repository, seeded):
    page = repository.search(EventFilters(event_name="error", limit=50))
    assert all(e.event_name == "error" for e in page.items)
    assert page.stats.strategy == "indice_tipo_e_tempo"


def test_busca_sem_chave_usa_a_particao_de_tempo(repository, seeded):
    page = repository.search(EventFilters(limit=50))
    assert page.stats.strategy == "particao_por_tempo"


def test_filtros_cumulativos(repository, seeded, sample_events):
    """RF09: os filtros se somam, nao se substituem."""
    amostra = sample_events["error"]
    page = repository.search(
        EventFilters(event_name="error", app_env=amostra.get("app_env"), limit=50)
    )
    for evento in page.items:
        assert evento.event_name == "error"
        assert evento.app_env == amostra.get("app_env")


def test_filtro_por_periodo(repository, seeded):
    vazio = repository.search(
        EventFilters(
            occurred_from=REFERENCE_NOW + timedelta(days=1),
            occurred_to=REFERENCE_NOW + timedelta(days=2),
            limit=50,
        )
    )
    assert list(vazio.items) == []

    cheio = repository.search(
        EventFilters(
            occurred_from=REFERENCE_NOW - timedelta(days=30),
            occurred_to=REFERENCE_NOW,
            limit=50,
        )
    )
    assert cheio.items


def test_ordena_do_mais_recente_para_o_mais_antigo(repository, seeded):
    page = repository.search(EventFilters(limit=50))
    momentos = [e.occurred_at for e in page.items]
    assert momentos == sorted(momentos, reverse=True)


def test_get_exige_sessao(repository, seeded, sample_events):
    page = repository.search(EventFilters(limit=1))
    alvo = page.items[0]

    assert repository.get(alvo.session_id, alvo.event_id) is not None
    assert repository.get("sessao-que-nao-existe", alvo.event_id) is None


# --------------------------------------------------------------------------- #
# Paginacao por keyset
# --------------------------------------------------------------------------- #


def test_cursor_percorre_sem_repetir_nem_pular(repository, seeded, sample_events):
    vistos = []
    cursor = None
    for _ in range(20):  # teto de seguranca contra laco infinito
        page = repository.search(EventFilters(limit=2, cursor=cursor))
        vistos.extend(e.event_id for e in page.items)
        cursor = page.next_cursor
        if not cursor:
            break

    assert len(vistos) == len(set(vistos)), "o cursor repetiu evento"
    assert len(vistos) == len(sample_events), "o cursor pulou evento"


def test_cursor_invalido_e_erro_do_cliente(repository, seeded):
    """Cursor quebrado e 422, nao 500 e nao um silencioso "primeira pagina".

    Devolver a primeira pagina faria um laco de paginacao com token corrompido
    girar para sempre lendo o mesmo trecho, sem nunca dar sinal de erro.
    """
    from telemetry.domain.exceptions import ValidationError

    with pytest.raises(ValidationError):
        repository.search(EventFilters(limit=50, cursor="isso-nao-e-um-cursor"))


def test_ultima_pagina_nao_tem_cursor(repository, seeded):
    page = repository.search(EventFilters(limit=100))
    assert page.next_cursor is None


# --------------------------------------------------------------------------- #
# Agregacoes
# --------------------------------------------------------------------------- #


def test_breakdown_agrupa_e_conta(repository, seeded, sample_events):
    metricas = repository.breakdown(EventFilters(limit=100), "event_name")
    total = sum(m.count for m in metricas)
    assert total == len(sample_events)


def test_breakdown_ordena_do_maior_para_o_menor(repository, seeded):
    metricas = repository.breakdown(EventFilters(limit=100), "device_manufacturer")
    contagens = [m.count for m in metricas]
    assert contagens == sorted(contagens, reverse=True)


def test_breakdown_calcula_media_de_duracao_em_ms(repository, seeded):
    metricas = repository.breakdown(EventFilters(limit=100), "event_name")
    com_media = [m for m in metricas if m.average_duration_ms is not None]
    assert com_media
    assert all(m.average_duration_ms > 0 for m in com_media)


def test_breakdown_recusa_dimensao_invalida(repository, seeded):
    """A dimensao entra na instrucao como identificador: lista fechada ou injecao."""
    with pytest.raises(ValueError):
        repository.breakdown(EventFilters(limit=10), "payload; DROP TABLE bronze.event")


def test_breakdown_recusa_dimensao_de_alta_cardinalidade(repository, seeded):
    """Agrupar por session_id nao e agrupamento, e dump."""
    with pytest.raises(ValueError):
        repository.breakdown(EventFilters(limit=10), "session_id")


def test_timeseries_agrupa_por_janela(repository, seeded, sample_events):
    buckets = repository.timeseries(EventFilters(limit=100), interval_minutes=60)
    assert buckets
    assert sum(b.count for b in buckets) == len(sample_events)


def test_timeseries_separa_por_tipo(repository, seeded):
    buckets = repository.timeseries(EventFilters(limit=100), interval_minutes=1440)
    nomes = set()
    for bucket in buckets:
        nomes |= set(bucket.by_event_name)
    assert "error" in nomes


def test_timeseries_alinha_os_buckets_a_uma_origem_fixa(repository, seeded):
    """Sem alinhamento fixo, dois filtros diferentes dariam buckets deslocados.

    Os graficos da tela Comparar precisam se sobrepor; se cada consulta ancorasse
    no proprio primeiro evento, eles nunca coincidiriam.
    """
    a = repository.timeseries(EventFilters(limit=100), interval_minutes=60)
    b = repository.timeseries(EventFilters(event_name="error", limit=100), 60)
    if a and b:
        assert b[0].bucket in {bucket.bucket for bucket in a}


def test_facets_lista_valores_existentes(repository, seeded, sample_events):
    resultado = repository.facets(["event_name", "device_manufacturer"])
    assert set(resultado["event_name"]) == set(sample_events)
    assert resultado["device_manufacturer"]


def test_facets_recusa_campo_invalido(repository, seeded):
    with pytest.raises(ValueError):
        repository.facets(["1; DELETE FROM bronze.event"])


def test_ping(repository, seeded):
    assert repository.ping() is True


# --------------------------------------------------------------------------- #
# A barreira contra vazamento de futuro
# --------------------------------------------------------------------------- #


def test_evento_alem_do_relogio_virtual_nao_aparece(repository, pool, sample_events):
    """A propriedade central do sistema, verificada de ponta a ponta.

    Uma linha cujo `available_at` esta a frente de `sim.now()` nao pode aparecer
    -- e nao por causa de um filtro na aplicacao, mas porque a view a esconde.
    """
    from psycopg.types.json import Jsonb

    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO silver.session_event
              (ts, event_id, event_name, session_id, device_id, payload,
               available_at, _lsn)
            VALUES (%s, 'evento-do-futuro', 'error', 's-futuro', 'd-futuro',
                    %s, %s, 1)
            """,
            (
                REFERENCE_NOW - timedelta(minutes=5),
                Jsonb({}),
                # Ja aconteceu, mas so fica DISPONIVEL daqui a uma hora --
                # exatamente o caso das fontes NPAW, com 28 h de latencia.
                REFERENCE_NOW + timedelta(hours=1),
            ),
        )

    page = repository.search(EventFilters(limit=100))
    assert "evento-do-futuro" not in {e.event_id for e in page.items}

    # E aparece quando o relogio virtual alcanca o available_at.
    with pool.connection() as conn:
        conn.execute("SELECT sim.set_clock(%s, 0)", (REFERENCE_NOW + timedelta(hours=2),))

    page = repository.search(
        EventFilters(occurred_from=REFERENCE_NOW - timedelta(days=1), limit=100)
    )
    assert "evento-do-futuro" in {e.event_id for e in page.items}
