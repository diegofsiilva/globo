"""Testes de `GET /api/v1/signals` (tela Agora, v1 simplificada).

Mesma estrategia de `test_gold.py`: insere direto em `gold.feature_bucket`
(bypassa o ETL, testa so a leitura) com `hora_brt` explicito -- e o que
permite montar cenario de baseline determinístico sem depender de dias reais
de historico, mesmo com `signals_repository` usando uma janela curta de
baseline (ver fixture em `conftest.py`).
"""

from datetime import timedelta
from urllib.parse import quote

from telemetry.application.signals import LIMIAR_SINAL, GenerateSignals
from tests.conftest import REFERENCE_NOW

DESDE = REFERENCE_NOW - timedelta(hours=1)
ATE = REFERENCE_NOW
BASELINE_DESDE = DESDE - timedelta(hours=6)  # baseline_hours=6 na fixture de teste

# O '+' do fuso em isoformat() (ex.: ...+00:00) precisa ser escapado na query
# string -- sem isso, o werkzeug decodifica '+' como espaco (convencao de
# application/x-www-form-urlencoded) e a data para de ser ISO 8601 valida.
JANELA_QS = f"from={quote(DESDE.isoformat())}&to={quote(ATE.isoformat())}"


def _inserir_bucket(
    pool,
    *,
    bucket_ts,
    value,
    hora_brt=8,
    available_at=None,
    source="prometheus",
    entity="pop-fortaleza",
    metric="p95_ms",
    tem_jogo=False,
):
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO gold.feature_bucket
              (bucket_ts, source, entity, metric, value, hora_brt, dow,
               tem_jogo, available_at)
            VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s)
            """,
            (
                bucket_ts,
                source,
                entity,
                metric,
                value,
                hora_brt,
                tem_jogo,
                available_at or bucket_ts,
            ),
        )


def _inserir_baseline(pool, valores, *, hora_brt=8, **grupo):
    """Tres (ou mais) pontos de baseline com o MESMO hora_brt da janela --
    e o que faz o JOIN de `desvios()` achar historico, sem precisar de dias
    de calendario reais dentro da janela curta de baseline do teste.
    """
    passo = BASELINE_DESDE
    for valor in valores:
        _inserir_bucket(pool, bucket_ts=passo, value=valor, hora_brt=hora_brt, **grupo)
        passo += timedelta(hours=1)


def _inserir_sinal(pool, **grupo):
    """Baseline estavel (media 50, desvio 2) mais um pico -- um sinal critico."""
    _inserir_baseline(pool, [48, 50, 52], **grupo)
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=150, **grupo)


def test_sem_dado_devolve_lista_vazia(client, pool):
    resposta = client.get(f"/api/v1/signals?{JANELA_QS}")

    assert resposta.status_code == 200
    assert resposta.json == {"items": [], "count": 0, "truncated": False}


def test_resposta_permite_cache_curto_entre_pollings(client, pool):
    resposta = client.get(f"/api/v1/signals?{JANELA_QS}")

    assert resposta.headers["Cache-Control"] == ("public, max-age=30, stale-while-revalidate=30")


def test_caso_de_uso_antecipa_limiar_ao_repositorio():
    """O banco deve descartar séries normais antes de montar as tendências."""

    class Repository:
        chamada = None

        def desvios(self, desde, ate, limiar, escopo=None):
            self.chamada = (desde, ate, limiar, escopo)
            return []

    repository = Repository()

    assert GenerateSignals(repository).execute(DESDE, ATE) == {
        "items": [],
        "count": 0,
        "truncated": False,
    }
    assert repository.chamada == (DESDE, ATE, LIMIAR_SINAL, None)


def test_caso_de_uso_repassa_escopo_ao_repositorio():
    """O filtro da tela precisa chegar ao SQL, e nao ser aplicado em memoria:
    filtrar depois traria a janela inteira do banco a cada consulta.
    """

    class Repository:
        chamada = None

        def desvios(self, desde, ate, limiar, escopo=None):
            self.chamada = (desde, ate, limiar, escopo)
            return []

    repository = Repository()
    escopo = {"source": "prometheus", "tem_jogo": "true"}

    GenerateSignals(repository).execute(DESDE, ATE, escopo=escopo)

    assert repository.chamada[3] == escopo


def test_desvio_forte_vira_sinal_critico(client, pool):
    _inserir_baseline(pool, [48, 50, 52])  # media 50, desvio 2
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=150)

    itens = client.get(f"/api/v1/signals?{JANELA_QS}").json["items"]

    assert len(itens) == 1
    sinal = itens[0]
    assert sinal["source"] == "prometheus"
    assert sinal["entity"] == "pop-fortaleza"
    assert sinal["metric"] == "p95_ms"
    assert sinal["baseline"] == 50
    assert sinal["current_value"] == 150
    assert sinal["severity"] == "critical"  # z = (150-50)/2 = 50


def test_desvio_fraco_vira_sinal_estavel(client, pool):
    _inserir_baseline(pool, [40, 50, 60])  # media 50, desvio 10
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=72)  # z=2.2

    sinal = client.get(f"/api/v1/signals?{JANELA_QS}").json["items"][0]

    assert sinal["severity"] == "stable"


def test_desvio_medio_vira_sinal_de_atencao(client, pool):
    _inserir_baseline(pool, [40, 50, 60])  # media 50, desvio 10
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=80)  # z=3.0

    sinal = client.get(f"/api/v1/signals?{JANELA_QS}").json["items"][0]

    assert sinal["severity"] == "warning"


def test_trend_e_serie_numerica_nao_categoria(client, pool):
    """Contrato exigido pelo mock do frontend (agora/_mocks/scenario.ts):
    `trend` precisa ser number[], nao a string categorica -- essa virou
    `direction`.
    """
    _inserir_baseline(pool, [48, 50, 52])
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=45), value=120)
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=150)

    sinal = client.get(f"/api/v1/signals?{JANELA_QS}").json["items"][0]

    assert sinal["trend"] == [120, 150]
    assert sinal["direction"] in {"subindo", "descendo", "estavel"}
    assert sinal["direction"] == "subindo"  # z do ultimo bucket > z do anterior


def test_consecutive_buckets_conta_so_a_sequencia_final(client, pool):
    """So os buckets seguidos ACIMA do limiar, contados do fim pra tras --
    um pico isolado no meio da janela nao deve inflar a contagem.
    """
    _inserir_baseline(pool, [48, 50, 52])
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=45), value=150)
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=51)  # recupera
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=15), value=140)
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW, value=145)

    sinal = client.get(f"/api/v1/signals?{JANELA_QS}").json["items"][0]

    assert sinal["consecutive_buckets_over_threshold"] == 2
    assert sinal["detected_at"] == (REFERENCE_NOW - timedelta(minutes=15)).isoformat()


def test_sinal_recuperado_no_ultimo_bucket_nao_aparece(client, pool):
    """'Ativo agora', nao 'desviou em algum momento da janela' -- o ultimo
    bucket voltando ao normal remove o grupo da lista.
    """
    _inserir_baseline(pool, [48, 50, 52])
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=150)
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=5), value=51)

    itens = client.get(f"/api/v1/signals?{JANELA_QS}").json["items"]

    assert itens == []


def test_sem_historico_de_baseline_suficiente_nao_vira_sinal(client, pool):
    """`desvios()` exige n >= 3 amostras de baseline; com menos, z fica None."""
    _inserir_baseline(pool, [48, 52])  # so 2 pontos
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=150)

    itens = client.get(f"/api/v1/signals?{JANELA_QS}").json["items"]

    assert itens == []


def test_respeita_o_relogio_virtual(client, pool):
    """Um bucket com `available_at` no futuro simulado nao pode aparecer --
    mesma barreira de `gold.v_feature_bucket` usada no resto da API.
    """
    _inserir_baseline(pool, [48, 50, 52])
    _inserir_bucket(
        pool,
        bucket_ts=REFERENCE_NOW - timedelta(minutes=30),
        value=150,
        available_at=REFERENCE_NOW + timedelta(hours=2),
    )

    itens = client.get(f"/api/v1/signals?{JANELA_QS}").json["items"]

    assert itens == []


def test_janela_padrao_sem_from_to_usa_sim_now(client, pool):
    """Sem `from`/`to`, a janela e as ultimas 6 h ate `sim.now()`
    (`JANELA_PADRAO_HORAS` em `signals_http.py`) e a baseline olha as 6 h
    ANTES disso -- diferente da janela de 1 h usada no resto deste arquivo,
    entao os pontos de baseline aqui precisam de outro deslocamento.
    """
    desde_padrao = REFERENCE_NOW - timedelta(hours=6)
    baseline_desde_padrao = desde_padrao - timedelta(hours=6)
    passo = baseline_desde_padrao
    for valor in (48, 50, 52):
        _inserir_bucket(pool, bucket_ts=passo, value=valor)
        passo += timedelta(hours=1)
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=150)

    resposta = client.get("/api/v1/signals")

    assert resposta.status_code == 200
    assert len(resposta.json["items"]) == 1


def test_threshold_value_converte_z_para_unidade_nativa(client, pool):
    """`threshold_value` e `baseline +- threshold_z * stddev`, do lado em que
    o desvio esta acontecendo -- e o que permite o front mostrar o limiar na
    unidade da metrica, sem o operador precisar interpretar z-score.
    """
    _inserir_baseline(pool, [48, 50, 52])  # media 50, desvio 2
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=150)

    sinal = client.get(f"/api/v1/signals?{JANELA_QS}").json["items"][0]

    assert sinal["threshold_value"] == 54  # 50 + 2.0 * 2 (z positivo: limiar acima do baseline)


def test_sessions_impacted_indisponivel_sem_vinculo_causal(client, seeded, pool):
    """feature_bucket não possui session_id para atribuir sessões ao sinal."""
    _inserir_baseline(pool, [48, 50, 52])
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=150)

    sinal = client.get(f"/api/v1/signals?{JANELA_QS}").json["items"][0]

    assert sinal["sessions_impacted"] is None


# --------------------------------------------------------------------------- #
# Filtros de escopo, limite e truncamento
#
# Sao os mesmos filtros que Explorar, Comparar e Recorte usam. Antes desta
# versao a tela Agora exibia controles de plataforma/fabricante/regiao que a
# rota ignorava: o operador mudava o filtro e a lista continuava igual.
# --------------------------------------------------------------------------- #


def test_filtra_por_source(client, pool):
    _inserir_sinal(pool, source="prometheus")
    _inserir_sinal(pool, source="newrelic")

    itens = client.get(f"/api/v1/signals?{JANELA_QS}&source=newrelic").json["items"]

    assert [item["source"] for item in itens] == ["newrelic"]


def test_filtra_por_entity(client, pool):
    _inserir_sinal(pool, entity="pop-fortaleza")
    _inserir_sinal(pool, entity="pop-recife")

    itens = client.get(f"/api/v1/signals?{JANELA_QS}&entity=pop-recife").json["items"]

    assert [item["entity"] for item in itens] == ["pop-recife"]


def test_filtra_por_metric(client, pool):
    _inserir_sinal(pool, metric="p95_ms")
    _inserir_sinal(pool, metric="erro_pct")

    itens = client.get(f"/api/v1/signals?{JANELA_QS}&metric=erro_pct").json["items"]

    assert [item["metric"] for item in itens] == ["erro_pct"]


def test_filtra_por_tem_jogo(client, pool):
    _inserir_sinal(pool, entity="pop-com-jogo", tem_jogo=True)
    _inserir_sinal(pool, entity="pop-sem-jogo", tem_jogo=False)

    itens = client.get(f"/api/v1/signals?{JANELA_QS}&tem_jogo=true").json["items"]

    assert [item["entity"] for item in itens] == ["pop-com-jogo"]


def test_filtro_restringe_tambem_o_baseline(client, pool):
    """O baseline precisa sair do MESMO recorte da janela.

    Com baseline global, um grupo cujo historico so existe fora do recorte
    apareceria como desvio -- a rota estaria medindo a diferenca entre os
    recortes, e nao um desvio dentro do recorte pedido.
    """
    # Baseline so em buckets SEM jogo; o pico esta num bucket COM jogo.
    _inserir_baseline(pool, [48, 50, 52], tem_jogo=False)
    _inserir_bucket(
        pool,
        bucket_ts=REFERENCE_NOW - timedelta(minutes=30),
        value=150,
        tem_jogo=True,
    )

    itens = client.get(f"/api/v1/signals?{JANELA_QS}&tem_jogo=true").json["items"]

    assert itens == []


def test_dimensao_desconhecida_e_ignorada_e_nao_vira_sql(client, pool):
    """Parametro fora de `DIMENSOES` nao entra na consulta.

    O nome da coluna nunca vem do cliente; um parametro estranho e simplesmente
    ignorado, e nao um 500 nem uma clausula injetada.
    """
    _inserir_sinal(pool)

    resposta = client.get(f"/api/v1/signals?{JANELA_QS}&drop_table=1")

    assert resposta.status_code == 200
    assert len(resposta.json["items"]) == 1


def test_limit_corta_pelos_desvios_mais_fortes(client, pool):
    _inserir_baseline(pool, [48, 50, 52], entity="pop-a")
    _inserir_bucket(pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=80, entity="pop-a")
    _inserir_baseline(pool, [48, 50, 52], entity="pop-b")
    _inserir_bucket(
        pool, bucket_ts=REFERENCE_NOW - timedelta(minutes=30), value=150, entity="pop-b"
    )

    corpo = client.get(f"/api/v1/signals?{JANELA_QS}&limit=1").json

    assert corpo["count"] == 1
    assert corpo["truncated"] is True
    # O que sobra e o desvio MAIOR, nao o primeiro que o banco devolveu.
    assert corpo["items"][0]["entity"] == "pop-b"


def test_sem_truncamento_quando_tudo_cabe(client, pool):
    _inserir_sinal(pool)

    corpo = client.get(f"/api/v1/signals?{JANELA_QS}").json

    assert corpo["count"] == 1
    assert corpo["truncated"] is False


def test_limit_fora_da_faixa_e_422(client, pool):
    assert client.get(f"/api/v1/signals?{JANELA_QS}&limit=101").status_code == 422
    assert client.get(f"/api/v1/signals?{JANELA_QS}&limit=0").status_code == 422


def test_resposta_cabe_no_orcamento_de_banda(client, pool):
    """RNF02: `/signals` abaixo de 100 KB.

    Com o limite padrao de 25 sinais e a sparkline de cada um, o corpo fica
    uma ordem de grandeza abaixo do teto -- o teste existe para que uma
    ampliacao futura do payload por sinal nao passe despercebida.
    """
    for indice in range(40):
        _inserir_sinal(pool, entity=f"pop-{indice:03d}")

    resposta = client.get(f"/api/v1/signals?{JANELA_QS}")

    assert resposta.json["count"] == 25
    assert resposta.json["truncated"] is True
    assert len(resposta.data) < 100 * 1024
