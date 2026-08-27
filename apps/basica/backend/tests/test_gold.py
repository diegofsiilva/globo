"""Testes das rotas da camada gold: relogio virtual, series e janelas."""

from datetime import timedelta

import pytest

from tests.conftest import REFERENCE_NOW


@pytest.fixture
def com_series(pool):
    """Popula gold.feature_bucket com duas fontes de latencia diferente."""
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO gold.feature_bucket
              (bucket_ts, source, entity, metric, value, hora_brt, dow,
               tem_jogo, available_at)
            VALUES
              (%s, 'prometheus', 'pop-fortaleza', 'p95_ms', 368, 8, 1, true, %s),
              (%s, 'prometheus', 'pop-fortaleza', 'p95_ms', 412, 8, 1, true, %s),
              -- Ja aconteceu, mas so fica disponivel daqui a 28 h: e a latencia
              -- estrutural do batch BigQuery da NPAW.
              (%s, 'youbora', 'globo', 'bufferratio', 0.021, 8, 1, false, %s)
            """,
            (
                REFERENCE_NOW - timedelta(hours=2), REFERENCE_NOW - timedelta(hours=1),
                REFERENCE_NOW - timedelta(hours=1), REFERENCE_NOW - timedelta(minutes=30),
                REFERENCE_NOW - timedelta(hours=2), REFERENCE_NOW + timedelta(hours=26),
            ),
        )
        conn.execute("SELECT gold.refresh_source_series()")
    return pool


@pytest.fixture
def com_incidentes(pool):
    """Popula gold.incident_window com um ticket e dois rotulos."""
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO gold.incident_window
              (ts_start, ts_end, origem, ref_id, verdict, severity, provenance)
            VALUES
              (%s, %s, 'incidents', 'INC0012345', 'external', '1', 'servicenow'),
              (%s, %s, 'incident_label', 'label-humano', 'internal', 'high', 'manual'),
              (%s, %s, 'incident_label', 'label-derivado', 'internal', 'high',
               'detector-derived')
            """,
            (
                REFERENCE_NOW - timedelta(hours=3), REFERENCE_NOW - timedelta(hours=2),
                REFERENCE_NOW - timedelta(hours=5), REFERENCE_NOW - timedelta(hours=4),
                REFERENCE_NOW - timedelta(hours=7), REFERENCE_NOW - timedelta(hours=6),
            ),
        )
    return pool


# --------------------------------------------------------------------------- #
# Relogio
# --------------------------------------------------------------------------- #


def test_clock_devolve_o_instante_virtual(client, pool):
    """O 'agora' das telas vem do BANCO, nao do relogio do navegador."""
    resposta = client.get("/api/v1/clock")

    assert resposta.status_code == 200
    assert resposta.json["sim_now"].startswith("2026-07-14T12:00:00")
    assert resposta.json["speed"] == 0


def test_close_run_congela_o_relogio(pool):
    """Pausar o run e o clock precisa ser uma unica operacao no banco."""
    pausa = REFERENCE_NOW + timedelta(hours=3)
    with pool.connection() as conn:
        run_id = conn.execute(
            """
            INSERT INTO sim.run (seed, t0, t1, speed, status)
            VALUES (20260824, %s, %s, 60, 'running')
            RETURNING run_id
            """,
            (REFERENCE_NOW, REFERENCE_NOW + timedelta(days=1)),
        ).fetchone()[0]
        conn.execute("SELECT sim.set_clock(%s, 60)", (REFERENCE_NOW,))
        congelado = conn.execute(
            "SELECT sim.close_run(%s, 'paused', %s)", (run_id, pausa)
        ).fetchone()[0]
        estado = conn.execute(
            "SELECT status FROM sim.run WHERE run_id = %s", (run_id,)
        ).fetchone()[0]
        clock = conn.execute(
            "SELECT sim.now(), speed FROM sim.clock WHERE id = 1"
        ).fetchone()

    assert congelado == pausa
    assert estado == "paused"
    assert clock == (pausa, 0)


# --------------------------------------------------------------------------- #
# Series
# --------------------------------------------------------------------------- #


def test_series_devolve_os_pontos_disponiveis(client, com_series):
    resposta = client.get("/api/v1/series?window_hours=24")

    assert resposta.status_code == 200
    fontes = {item["source"] for item in resposta.json["items"]}
    assert fontes == {"prometheus"}, "o ponto do youbora ainda nao esta disponivel"


def test_series_esconde_o_que_o_relogio_nao_alcancou(client, com_series, pool):
    """A propriedade central: a view corta em sim.now(), nao a aplicacao."""
    antes = client.get("/api/v1/series?window_hours=24").json["count"]

    # Avanca o relogio para depois do available_at do youbora (+28 h).
    with pool.connection() as conn:
        conn.execute(
            "SELECT sim.set_clock(%s, 0)", (REFERENCE_NOW + timedelta(hours=30),)
        )

    depois = client.get("/api/v1/series?window_hours=48").json
    assert depois["count"] == antes + 1
    assert "youbora" in {item["source"] for item in depois["items"]}


def test_series_filtra_por_fonte_e_metrica(client, com_series):
    resposta = client.get("/api/v1/series?source=prometheus&metric=p95_ms&window_hours=24")

    assert resposta.status_code == 200
    assert resposta.json["count"] == 2
    assert all(item["metric"] == "p95_ms" for item in resposta.json["items"])


def test_series_traz_as_features_do_ciclo_circadiano(client, com_series):
    item = client.get("/api/v1/series?window_hours=24").json["items"][0]

    assert item["hora_brt"] == 8
    assert item["dow"] == 1
    assert item["tem_jogo"] is True


def test_sources_lista_o_que_existe(client, com_series):
    resposta = client.get("/api/v1/sources")

    assert resposta.status_code == 200
    assert len(resposta.json["items"]) == 1
    prometheus = resposta.json["items"][0]
    assert prometheus["source"] == "prometheus"
    assert prometheus["entidades"] == 1
    assert prometheus["metricas"] == 1


def test_sources_respeita_available_at(client, com_series, pool):
    antes = {item["source"] for item in client.get("/api/v1/sources").json["items"]}
    assert antes == {"prometheus"}

    with pool.connection() as conn:
        conn.execute(
            "SELECT sim.set_clock(%s, 0)", (REFERENCE_NOW + timedelta(hours=30),)
        )

    depois = {item["source"] for item in client.get("/api/v1/sources").json["items"]}
    assert depois == {"prometheus", "youbora"}


# --------------------------------------------------------------------------- #
# Incidentes
# --------------------------------------------------------------------------- #


def test_incidents_exclui_rotulo_derivado_por_padrao(client, com_incidentes):
    """Sete dos vinte rotulos sao `detector-derived`.

    Avaliar um detector novo contra eles mede concordancia com o baseline, nao
    acuracia -- um modelo que encontrasse incidentes reais que o Argus perdeu
    seria PENALIZADO. Por isso o padrao exclui.
    """
    resposta = client.get("/api/v1/incidents")

    refs = {item["ref_id"] for item in resposta.json["items"]}
    assert "label-humano" in refs
    assert "label-derivado" not in refs


def test_incidents_inclui_derivado_quando_pedido_explicitamente(client, com_incidentes):
    resposta = client.get("/api/v1/incidents?include_derived=true")

    refs = {item["ref_id"] for item in resposta.json["items"]}
    assert "label-derivado" in refs


def test_incidents_expoe_provenance_na_resposta(client, com_incidentes):
    """A coluna vai na saida de proposito: quem consome PRECISA poder decidir."""
    item = client.get("/api/v1/incidents").json["items"][0]
    assert "provenance" in item


def test_incidents_filtra_por_origem(client, com_incidentes):
    resposta = client.get("/api/v1/incidents?origem=incidents")

    assert resposta.json["count"] == 1
    assert resposta.json["items"][0]["origem"] == "incidents"


def test_incidents_esconde_o_que_ainda_nao_comecou(client, pool):
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO gold.incident_window (ts_start, ts_end, origem, ref_id)
            VALUES (%s, %s, 'incidents', 'INC-do-futuro')
            """,
            (REFERENCE_NOW + timedelta(hours=1), REFERENCE_NOW + timedelta(hours=2)),
        )

    refs = {item["ref_id"] for item in client.get("/api/v1/incidents").json["items"]}
    assert "INC-do-futuro" not in refs


# --------------------------------------------------------------------------- #
# Transmissoes
# --------------------------------------------------------------------------- #


def test_live_events_agrupa_feeds_simultaneos_por_confronto(client, pool):
    """tid 994 e 995 sao jogos DIFERENTES no mesmo horario, nao o mesmo canal.

    Agrupar por horario funde os dois; agrupar por event_key os separa e ainda
    mostra quais feeds carregaram cada um.
    """
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO gold.live_event_window
              (event_key, tid, ts_start, ts_end, slug, competition,
               team_home, team_away, event_date)
            VALUES
              ('fla-flu', 994, %s, %s, 'globo', 'Brasileirao',
               'Flamengo', 'Fluminense', %s),
              ('gre-int', 995, %s, %s, 'globo', 'Brasileirao',
               'Gremio', 'Internacional', %s)
            """,
            (
                REFERENCE_NOW - timedelta(hours=3), REFERENCE_NOW - timedelta(hours=1),
                (REFERENCE_NOW - timedelta(hours=3)).date(),
                REFERENCE_NOW - timedelta(hours=3), REFERENCE_NOW - timedelta(hours=1),
                (REFERENCE_NOW - timedelta(hours=3)).date(),
            ),
        )

    itens = client.get("/api/v1/live-events").json["items"]

    assert len(itens) == 2, "os dois feeds simultaneos viraram um jogo so"
    chaves = {item["event_key"] for item in itens}
    assert chaves == {"fla-flu", "gre-int"}


# --------------------------------------------------------------------------- #
# Deteccao (decisao 7: existe, mas ninguem popula ainda)
# --------------------------------------------------------------------------- #


def test_anomalies_devolve_vazio_sem_detector(client, pool):
    """A rota existe para o dashboard ser escrito contra o contrato final."""
    resposta = client.get("/api/v1/anomalies")

    assert resposta.status_code == 200
    assert resposta.json["items"] == []
