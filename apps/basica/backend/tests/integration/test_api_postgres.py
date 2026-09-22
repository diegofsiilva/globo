"""TI-02 -- integracao entre a camada de aplicacao e o banco de dados.

Componentes atravessados, na ordem em que a requisicao os encontra:

    rota Flask (`telemetry.interfaces`)
        -> caso de uso (`telemetry.application.use_cases`)
            -> porta de repositorio (`telemetry.ports`)
                -> adaptador `PostgresEventRepository`
                    -> PostgreSQL (`silver.session_event`)

O que se verifica NAO e o comportamento de nenhuma dessas partes isolada -- isso
ja e coberto pelos testes unitarios em `tests/unit/`. O que se verifica e a
COMUNICACAO entre elas: que um registro gravado no banco pelo mesmo codigo que o
worker de ingestao usa atravessa as quatro camadas e reaparece na resposta HTTP
com o conteudo certo, e que a travessia aplica a barreira de privacidade do
RNF10 -- o banco guarda `user_id` em claro, a API so pode devolver o hash.

Requisitos exercitados: RF06 (armazenar para consulta posterior), RF08 (pesquisa
por tipo, periodo e atributos), RF09 (filtros cumulativos) e RNF10 (nao expor
dado pessoal desnecessario).

Pre-condicao: PostgreSQL de teste no ar (`make -C apps/basica db-local`). Sem
ele a suite e PULADA, nao quebrada -- ver `tests/conftest.py`.
"""

from tests.conftest import SALT

# Um evento com todos os campos que os filtros cumulativos usam. Valores
# proprios deste teste (sufixo `-ti02`) para nao colidir com as seis fixtures
# reais que o resto da suite carrega.
EVENTO = {
    "timestamp": "2026-07-13T23:10:00Z",
    "event_name": "error",
    "session_id": "sessao-ti02",
    "device_id": "device-ti02",
    "user_id": "usuario-ti02",
    "app_bucket": "S3",
    "app_env": "production",
    "app_version": "2026.3.0",
    "device_manufacturer": "Philco",
    "device_model": "BTV32D10N5SKH",
    "device_os": "NetRange",
    "route_path": "vod",
    "error_name": "Erro ao reproduzir video",
}


def _linha_crua(pool, event_id_ou_sessao: str) -> dict:
    """Le a linha direto do PostgreSQL, sem passar pela aplicacao.

    E o outro lado da comparacao: o teste so prova que as camadas conversam se
    souber, de forma independente, o que o banco realmente guardou.

    Args:
        pool: Pool de conexao com o banco de teste.
        event_id_ou_sessao (str): Identificador de sessao a procurar.

    Returns:
        dict: Colunas cruas da linha encontrada.
    """
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT event_name, session_id, device_id, user_id, app_bucket,
                   device_os, route_path
              FROM silver.session_event
             WHERE session_id = %s
            """,
            (event_id_ou_sessao,),
        )
        colunas = [descricao.name for descricao in cur.description]
        return dict(zip(colunas, cur.fetchone(), strict=True))


def test_ti02_evento_gravado_no_banco_atravessa_as_camadas_ate_a_resposta_http(
    client, inserir, pool
):
    """TI-02.1 -- o dado persistido chega intacto ao consumidor HTTP.

    Entrada: um evento `error` gravado em `silver.session_event` pelo mesmo
    `build_row` que o worker de ingestao usa.

    Resultado esperado: `GET /api/v1/events` com dois filtros cumulativos
    (`event_name` + `device_os`) devolve 200 e exatamente esse evento, com cada
    campo igual ao que o SQL le direto da tabela.
    """
    inserir(EVENTO)

    # 1. O banco guardou o que se esperava -- lido sem a aplicacao no meio.
    linha = _linha_crua(pool, "sessao-ti02")
    assert linha["event_name"] == "error"
    assert linha["device_os"] == "NetRange"

    # 2. A mesma linha, agora pedida pela borda HTTP com filtros cumulativos.
    response = client.get("/api/v1/events?event_name=error&device_os=NetRange&limit=10")

    assert response.status_code == 200
    itens = [item for item in response.json["items"] if item["session_id"] == "sessao-ti02"]
    assert len(itens) == 1, "o evento gravado nao voltou pela API"

    # 3. Campo a campo: o que saiu da rota e o que esta na tabela.
    item = itens[0]
    assert item["event_name"] == linha["event_name"]
    assert item["session_id"] == linha["session_id"]
    assert item["device_id"] == linha["device_id"]
    assert item["app_bucket"] == linha["app_bucket"]
    assert item["device_os"] == linha["device_os"]
    assert item["route_path"] == linha["route_path"]

    # 4. O adaptador reporta ao consumidor o custo real da consulta no banco.
    assert response.json["query"]["returned"] >= 1
    assert response.json["query"]["scanned"] >= response.json["query"]["returned"]


def test_ti02_a_travessia_troca_o_identificador_do_usuario_pelo_hash(client, inserir, pool):
    """TI-02.2 -- RNF10 na fronteira entre o banco e a API.

    Entrada: o mesmo evento, cujo `user_id` o banco guarda em claro porque a
    ingestao nao o transforma.

    Resultado esperado: a resposta HTTP nunca contem `usuario-ti02`; traz
    `user_id_hash`, deterministico para o salt de teste, e nao traz a chave
    `user_id`.
    """
    import hashlib

    inserir(EVENTO)

    # O banco guarda o identificador cru -- e essa a premissa do teste.
    assert _linha_crua(pool, "sessao-ti02")["user_id"] == "usuario-ti02"

    response = client.get("/api/v1/events?session_id=sessao-ti02&limit=10")
    corpo = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "usuario-ti02" not in corpo, "user_id cru vazou na travessia banco -> API"

    item = next(item for item in response.json["items"] if item["session_id"] == "sessao-ti02")
    assert "user_id" not in item
    # 16 hexadecimais, e nao 32: ver `PostgresEventRepository._hash_user`.
    esperado = hashlib.sha256(f"{SALT}usuario-ti02".encode()).hexdigest()[:16]
    assert item["user_id_hash"] == esperado


def test_ti02_filtro_sem_correspondencia_devolve_lista_vazia_e_nao_erro(client, inserir):
    """TI-02.3 -- o caso negativo da mesma travessia.

    Entrada: o evento esta no banco, mas o filtro pede um `device_os` que nao
    existe em nenhuma linha.

    Resultado esperado: 200 com `items` vazio. O banco responde uma consulta
    legitima sem resultado, e a aplicacao traduz isso como ausencia de dado --
    nao como falha. Um 500 aqui significaria que as camadas so conversam no
    caminho feliz.
    """
    inserir(EVENTO)

    response = client.get("/api/v1/events?event_name=error&device_os=SistemaInexistente&limit=10")

    assert response.status_code == 200
    assert response.json["items"] == []
    assert response.json["query"]["returned"] == 0
