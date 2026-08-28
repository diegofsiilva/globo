"""Testes das rotas de leitura, com o formato real de item no DynamoDB."""

from datetime import timedelta

import pytest

from tests.conftest import REFERENCE_NOW

# --------------------------------------------------------------------------- #
# Busca (RF08, RF09)
# --------------------------------------------------------------------------- #


def test_lista_eventos(client, seeded):
    response = client.get("/api/v1/events?limit=50")

    assert response.status_code == 200
    assert len(response.json["items"]) == 6
    assert response.json["query"]["strategy"] == "particao_por_tempo"


def test_resposta_expoe_o_custo_da_consulta(client, seeded):
    """`scanned` versus `returned` mostra quanto o filtro custou -- num banco
    que cobra por item lido, uma tela barata e uma cara nao podem parecer
    iguais para quem esta construindo o dashboard.
    """
    response = client.get("/api/v1/events?limit=2")

    query = response.json["query"]
    assert query["scanned"] >= query["returned"]
    assert query["strategy"]
    assert query["queries"] >= 1


def test_filtra_por_tipo(client, seeded):
    response = client.get("/api/v1/events?event_name=error&limit=10")

    assert response.status_code == 200
    assert [item["event_name"] for item in response.json["items"]] == ["error"]
    assert response.json["query"]["strategy"] == "indice_tipo_e_tempo"


def test_filtros_cumulativos(client, seeded):
    response = client.get("/api/v1/events?app_bucket=S3&device_os=Linux&limit=50")

    assert response.status_code == 200
    for item in response.json["items"]:
        assert item["app_bucket"] == "S3"
        assert item["device_os"] == "Linux"


def test_filtra_por_periodo(client, seeded):
    vazio = client.get("/api/v1/events?from=2026-08-01T00:00:00Z&limit=50")
    cheio = client.get("/api/v1/events?from=2026-07-01T00:00:00Z&limit=50")

    assert vazio.json["items"] == []
    assert len(cheio.json["items"]) == 6


def test_periodo_invalido_e_422(client, seeded):
    response = client.get("/api/v1/events?from=ontem")

    assert response.status_code == 422
    assert response.json["field"] == "from"


def test_limite_fora_da_faixa_e_422(client, seeded):
    assert client.get("/api/v1/events?limit=0").status_code == 422
    assert client.get("/api/v1/events?limit=99999").status_code == 422


def test_cursor_invalido_e_422_e_nao_500(client, seeded):
    response = client.get("/api/v1/events?cursor=lixo!!!")

    assert response.status_code == 422
    assert response.json["field"] == "cursor"


def test_paginacao_por_cursor(client, seeded):
    vistos = []
    url = "/api/v1/events?limit=2"
    for _ in range(10):
        payload = client.get(url).json
        vistos.extend(item["event_id"] for item in payload["items"])
        if not payload["next_cursor"]:
            break
        url = f"/api/v1/events?limit=2&cursor={payload['next_cursor']}"

    assert len(vistos) == 6
    assert len(set(vistos)) == 6


# --------------------------------------------------------------------------- #
# Investigacao (RF16)
# --------------------------------------------------------------------------- #


def test_linha_do_tempo_da_sessao(client, seeded, sample_events):
    sessao = sample_events["error"]["session_id"]
    response = client.get(f"/api/v1/sessions/{sessao}")

    assert response.status_code == 200
    assert response.json["session_id"] == sessao
    assert response.json["query"]["strategy"] == "indice_sessao"

    horarios = [item["occurred_at"] for item in response.json["events"]]
    assert horarios == sorted(horarios), "a linha do tempo deve ser cronologica"


def test_resumo_da_sessao(client, seeded, sample_events):
    sessao = sample_events["error"]["session_id"]
    resumo = client.get(f"/api/v1/sessions/{sessao}").json["summary"]

    assert resumo["event_count"] >= 1
    assert resumo["error_count"] == 1
    assert resumo["device"]["manufacturer"] == "Philco"
    assert resumo["app"]["target"] == "dom-philco-netrange-2021"


def test_sessao_inexistente_e_404(client, seeded):
    assert client.get("/api/v1/sessions/nao-existe").status_code == 404


def test_detalhe_do_evento(client, seeded, sample_events):
    sessao = sample_events["error"]["session_id"]
    evento = client.get(f"/api/v1/sessions/{sessao}").json["events"][0]

    response = client.get(f"/api/v1/sessions/{sessao}/events/{evento['event_id']}")

    assert response.status_code == 200
    assert response.json["event_id"] == evento["event_id"]
    assert response.json["attributes"]["error_name"] == "Erro ao reproduzir vídeo"


def test_historico_do_aparelho(client, seeded, sample_events):
    aparelho = sample_events["error"]["device_id"]
    response = client.get(f"/api/v1/devices/{aparelho}")

    assert response.status_code == 200
    assert response.json["query"]["strategy"] == "indice_aparelho"
    assert all(item["device_id"] == aparelho for item in response.json["items"])


# --------------------------------------------------------------------------- #
# Agregacao (RF11, RF12, RF14)
# --------------------------------------------------------------------------- #


def test_breakdown_por_tipo(client, seeded):
    response = client.get("/api/v1/metrics/breakdown?dimension=event_name&limit=10")

    assert response.status_code == 200
    assert response.json["total"] == 6
    assert len(response.json["groups"]) == 6
    # share e arredondado em 4 casas para a tela; a soma de percentuais
    # arredondados nao fecha exatamente em 1.
    assert sum(grupo["share"] for grupo in response.json["groups"]) == pytest.approx(1.0, abs=1e-3)


def test_breakdown_por_fabricante(client, seeded):
    response = client.get("/api/v1/metrics/breakdown?dimension=device_manufacturer")

    chaves = {grupo["key"] for grupo in response.json["groups"]}
    assert "Samsung" in chaves


def test_breakdown_sem_dimensao_e_422(client, seeded):
    response = client.get("/api/v1/metrics/breakdown")

    assert response.status_code == 422
    assert response.json["field"] == "dimension"


def test_breakdown_com_dimensao_invalida_e_422(client, seeded):
    """user_id nunca pode virar dimensao de agrupamento (RNF10)."""
    response = client.get("/api/v1/metrics/breakdown?dimension=user_id")

    assert response.status_code == 422


def test_timeseries(client, seeded):
    response = client.get("/api/v1/metrics/timeseries?interval=60&from=2026-07-01T00:00:00Z")

    assert response.status_code == 200
    assert response.json["total"] == 6
    assert response.json["buckets"]


def test_timeseries_compara_com_periodo_anterior(client, seeded, inserir, sample_events):
    """RF14: comparar o periodo atual com o anterior de mesma duracao."""
    inserir(dict(sample_events["error"], timestamp="2026-07-12T23:04:11Z"))

    response = client.get(
        "/api/v1/metrics/timeseries?from=2026-07-13T00:00:00Z&to=2026-07-14T00:00:00Z&compare=true"
    )

    assert response.status_code == 200
    assert response.json["total"] == 6
    assert response.json["previous"]["total"] == 1
    assert response.json["change"]["absolute"] == 5
    assert response.json["change"]["ratio"] == 5.0


def test_comparacao_sem_periodo_e_422(client, seeded):
    response = client.get("/api/v1/metrics/timeseries?compare=true")

    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Sugestao de filtros (RF10)
# --------------------------------------------------------------------------- #


def test_facets(client, seeded):
    response = client.get("/api/v1/facets?field=event_name&field=device_manufacturer")

    assert response.status_code == 200
    facets = response.json["facets"]
    assert len(facets["event_name"]) == 6
    assert "Philco" in facets["device_manufacturer"]


def test_facet_de_campo_sensivel_e_422(client, seeded):
    assert client.get("/api/v1/facets?field=user_id").status_code == 422


# --------------------------------------------------------------------------- #
# Privacidade (RNF10)
# --------------------------------------------------------------------------- #


def test_nenhuma_resposta_expoe_user_id(client, seeded, sample_events):
    cru = sample_events["error"]["user_id"]
    sessao = sample_events["error"]["session_id"]

    for url in (
        "/api/v1/events?limit=50",
        f"/api/v1/sessions/{sessao}",
        "/api/v1/metrics/breakdown?dimension=event_name",
    ):
        assert cru not in client.get(url).get_data(as_text=True), f"user_id vazou em {url}"


def test_nenhuma_resposta_expoe_authorization(client, seeded):
    corpo = client.get("/api/v1/events?event_name=request&limit=10").get_data(as_text=True)

    assert "authorization" not in corpo.lower()


def test_evento_serializado_traz_hash_e_nao_o_identificador(client, seeded):
    item = client.get("/api/v1/events?event_name=error&limit=1").json["items"][0]

    assert item["user_id_hash"]
    assert "user_id" not in item


# --------------------------------------------------------------------------- #
# Tipo desconhecido
# --------------------------------------------------------------------------- #


def test_tipo_novo_aparece_na_api(client, inserir):
    """O pipeline aceita event_name desconhecido de proposito; se a API o
    escondesse, o dado entraria no banco e sumiria da tela.
    """
    inserir(
        {
            # Data fixa, dentro da janela de REFERENCE_NOW: com o relogio real o
            # teste dependia de estar perto da data das fixtures.
            "timestamp": "2026-07-13T23:07:00Z",
            "event_name": "ad_impression",
            "session_id": "s-novo",
            "device_id": "d-novo",
            "ad_provider": "gam",
        }
    )

    response = client.get("/api/v1/events?limit=10")
    nomes = [item["event_name"] for item in response.json["items"]]

    assert "ad_impression" in nomes


# --------------------------------------------------------------------------- #
# Regiao / operadora -- uf, isp (RF09)
# --------------------------------------------------------------------------- #


def _inserir_sessao(pool, *, event_id, session_id, uf=None, isp=None, ts=None):
    """Insere direto em `silver.session_event` com `uf`/`isp` explicitos.

    NAO usa `inserir`/`_inserir_eventos` (helper compartilhado com o worker,
    em `conftest.py`): aquele grava `uf`/`isp` como `NULL` sempre, porque
    nenhum dos seis tipos reais de evento traz essas colunas hoje (comentario
    em `006_silver.sql`). Este teste verifica o MECANISMO do filtro -- que
    `EventFilters`/`filters_from_query` agora leem `uf`/`isp` da query string
    e que o `WHERE` os aplica -- nao dado de producao real, que ainda nao
    existe para essas duas colunas.
    """
    instante = ts or REFERENCE_NOW - timedelta(hours=1)
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO silver.session_event
              (ts, event_id, event_name, session_id, device_id, uf, isp,
               payload, available_at, _lsn)
            VALUES (%s, %s, 'error', %s, %s, %s, %s, '{}', %s, 1)
            """,
            (instante, event_id, session_id, session_id, uf, isp, instante),
        )


def test_filtro_uf_restringe_a_regiao(client, pool):
    _inserir_sessao(pool, event_id="e-rj", session_id="s-rj", uf="RJ")
    _inserir_sessao(pool, event_id="e-sp", session_id="s-sp", uf="SP")

    response = client.get("/api/v1/events?uf=RJ&limit=10")

    assert response.status_code == 200
    assert len(response.json["items"]) == 1
    assert response.json["items"][0]["session_id"] == "s-rj"


def test_filtro_isp_restringe_a_operadora(client, pool):
    _inserir_sessao(pool, event_id="e-claro", session_id="s-claro", isp="Claro")
    _inserir_sessao(pool, event_id="e-vivo", session_id="s-vivo", isp="Vivo")

    response = client.get("/api/v1/events?isp=Claro&limit=10")

    assert response.status_code == 200
    assert len(response.json["items"]) == 1
    assert response.json["items"][0]["session_id"] == "s-claro"


def test_filtro_uf_e_isp_sao_cumulativos_com_os_demais(client, pool):
    _inserir_sessao(pool, event_id="e-1", session_id="s-1", uf="RJ", isp="Claro")
    _inserir_sessao(pool, event_id="e-2", session_id="s-2", uf="RJ", isp="Vivo")

    response = client.get("/api/v1/events?uf=RJ&isp=Claro&limit=10")

    assert len(response.json["items"]) == 1
    assert response.json["items"][0]["session_id"] == "s-1"


def test_breakdown_por_uf_ja_aceitava_a_dimensao_antes_do_fix(client, pool):
    """`breakdown`/`facets` ja tinham `uf` na whitelist de agrupamento antes
    desta mudanca (`COLUNAS_AGRUPAVEIS` em `postgres.py`) -- o gap era so no
    filtro de busca (`EventFilters`). Este teste documenta que a parte que ja
    funcionava continua funcionando, sem depender do fix novo.
    """
    _inserir_sessao(pool, event_id="e-rj3", session_id="s-rj3", uf="RJ")
    _inserir_sessao(pool, event_id="e-sp3", session_id="s-sp3", uf="SP")

    response = client.get("/api/v1/metrics/breakdown?dimension=uf")

    chaves = {grupo["key"] for grupo in response.json["groups"]}
    assert {"RJ", "SP"} <= chaves


# --------------------------------------------------------------------------- #
# Crosstab -- heatmap de duas dimensoes (RF16)
# --------------------------------------------------------------------------- #


def test_crosstab_agrupa_por_duas_dimensoes(client, seeded):
    response = client.get(
        "/api/v1/metrics/crosstab?dimension_x=device_manufacturer&dimension_y=event_name"
    )

    assert response.status_code == 200
    assert response.json["dimension_x"] == "device_manufacturer"
    assert response.json["dimension_y"] == "event_name"
    total = sum(celula["count"] for celula in response.json["cells"])
    assert total == 6  # as seis fixtures, uma linha por combinacao (x, y)


def test_crosstab_bate_com_dois_breakdowns_separados(client, seeded):
    """Cada celula do crosstab tem que caber dentro do total do breakdown de
    uma dimensao so -- e a garantia de que o GROUP BY 1, 2 nao esta duplicando
    nem perdendo linha.
    """
    breakdown = client.get("/api/v1/metrics/breakdown?dimension=device_manufacturer&limit=100").json
    crosstab = client.get(
        "/api/v1/metrics/crosstab?dimension_x=device_manufacturer&dimension_y=event_name"
    ).json

    por_fabricante = {}
    for celula in crosstab["cells"]:
        por_fabricante[celula["x"]] = por_fabricante.get(celula["x"], 0) + celula["count"]

    for grupo in breakdown["groups"]:
        assert por_fabricante.get(grupo["key"], 0) == grupo["count"]


def test_crosstab_sem_dimension_x_e_422(client, seeded):
    response = client.get("/api/v1/metrics/crosstab?dimension_y=event_name")

    assert response.status_code == 422


def test_crosstab_com_dimensao_invalida_e_422(client, seeded):
    """`session_id`/`device_id` sao filtraveis mas nao agrupaveis -- alta
    cardinalidade, o mesmo motivo que ja vale para `breakdown`.
    """
    response = client.get(
        "/api/v1/metrics/crosstab?dimension_x=device_manufacturer&dimension_y=session_id"
    )

    assert response.status_code == 422
