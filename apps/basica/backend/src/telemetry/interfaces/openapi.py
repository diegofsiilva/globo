"""Especificacao OpenAPI 3.1 da API de leitura.

A spec e montada em codigo, e nao mantida num YAML ao lado, por dois motivos:

- As listas de valores aceitos (`dimension`, `field`, filtros) sao importadas
  das MESMAS constantes que o adaptador usa para validar. Documentacao que
  deriva da regra nao consegue divergir dela; um YAML paralelo divergiria no
  primeiro campo novo.
- Evita empacotar um arquivo de dados e um parser de YAML na Lambda.

O campo `servers` e preenchido a partir do host da requisicao. A URL real da
API nao aparece em nenhum arquivo do repositorio -- quem abre /docs ja esta no
host certo, e quem le o codigo nao descobre o endereco.
"""

from typing import Any

from flask import request

from telemetry.infrastructure.postgres import (
    COLUNAS_AGRUPAVEIS,
    COLUNAS_FILTRAVEIS,
)

# Na v2 havia duas listas: os filtros que escolhiam o indice e os que rodavam
# DEPOIS da consulta, em Python. No PostgreSQL essa distincao some -- todo
# filtro vai para o mesmo WHERE e o planner decide o que fazer com ele.
BREAKDOWN_FIELDS = COLUNAS_AGRUPAVEIS
FACET_FIELDS = COLUNAS_AGRUPAVEIS
POST_FILTERS = sorted(COLUNAS_FILTRAVEIS - {"session_id", "device_id", "event_name"})

API_VERSION = "1.0.0"

# Filtros que valem em /events e nas metricas.
_FILTER_PARAMS = [
    ("session_id", "Restringe a uma sessao. Caminho mais barato: uma particao."),
    ("device_id", "Restringe a um aparelho. Usa a GSI2."),
    ("event_name", "Tipo do evento. Usa a GSI1 com fan-out por dia e shard."),
    *[(name, f"Filtro por {name}, cumulativo com os demais (RF09).") for name in POST_FILTERS],
]


def _parameter(name: str, description: str, **schema: Any) -> dict[str, Any]:
    """Cria um objeto de parâmetro OpenAPI para query string.

    Args:
        name (str): Nome do parâmetro.
        description (str): Descrição do parâmetro.
        **schema (Any): Atributos adicionais do esquema OpenAPI.

    Returns:
        dict[str, Any]: Dicionário formatado no padrão de parâmetro OpenAPI.
    """
    return {
        "name": name,
        "in": "query",
        "required": False,
        "description": description,
        "schema": {"type": "string", **schema},
    }


def _common_query_parameters() -> list[dict[str, Any]]:
    """Gera a lista de parâmetros de busca reutilizáveis para endpoints de consulta.

    Returns:
        list[dict[str, Any]]: Lista de definições de parâmetros OpenAPI.
    """
    params = [_parameter(name, description) for name, description in _FILTER_PARAMS]
    params += [
        _parameter(
            "from",
            "Inicio do periodo, ISO 8601. Sem periodo, a API usa a janela padrao.",
            format="date-time",
        ),
        _parameter("to", "Fim do periodo, ISO 8601.", format="date-time"),
    ]
    return params


def _pagination_parameters() -> list[dict[str, Any]]:
    """Gera os parâmetros de paginação por limite e cursor para a documentação OpenAPI.

    Returns:
        list[dict[str, Any]]: Lista de parâmetros de paginação.
    """
    return [
        {
            "name": "limit",
            "in": "query",
            "required": False,
            "description": "Quantidade de eventos por pagina.",
            "schema": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
        },
        _parameter(
            "cursor",
            "Cursor opaco devolvido em `next_cursor`. Ausente significa ultima pagina.",
        ),
    ]


def _event_schema() -> dict[str, Any]:
    """Constrói o esquema JSON Schema para TelemetryEvent na especificação OpenAPI.

    Returns:
        dict[str, Any]: Dicionário do esquema da entidade de evento.
    """
    return {
        "type": "object",
        "description": (
            "Evento de telemetria. Campos especificos de cada tipo (error_*, media_*, "
            "capabilities_*, request_*) ficam em `attributes`, porque os seis tipos "
            "tem colunas diferentes."
        ),
        "properties": {
            "event_id": {
                "type": "string",
                "description": (
                    "Identificador do evento: sha256 do conteudo, 64 caracteres hex. "
                    "Nao e UUID. Derivar do conteudo e o que torna a ingestao "
                    "idempotente."
                ),
                "example": ("3b5d31ce4020a1f8d4c9e2b7a6f0123456789abcdef123456789abcdef1234"),
            },
            "event_name": {
                "type": "string",
                "description": (
                    "Tipo do evento. Os seis conhecidos sao request, screen_view, "
                    "session, video_view, vitals e error, mas a lista NAO e fechada: "
                    "o pipeline aceita tipo novo sem alteracao de codigo, e ele "
                    "aparece aqui no mesmo dia."
                ),
                "example": "error",
            },
            "occurred_at": {
                "type": "string",
                "format": "date-time",
                "description": "Quando o evento aconteceu no aparelho, em UTC.",
            },
            "ingested_at": {
                "type": ["string", "null"],
                "format": "date-time",
                "description": (
                    "Quando o worker gravou. A diferenca para `occurred_at` e o "
                    "atraso da ingestao, e em replay de dado historico ela e grande "
                    "de proposito."
                ),
            },
            "session_id": {"type": "string"},
            "device_id": {"type": "string"},
            "user_id_hash": {
                "type": ["string", "null"],
                "description": (
                    "Hash com salt do identificador de usuario. O valor original "
                    "nunca sai da API (RNF10). Estavel: serve para agrupar eventos "
                    "do mesmo usuario sem saber quem ele e."
                ),
            },
            "duration_ms": {
                "type": ["number", "null"],
                "description": (
                    "Duracao em milissegundos. O banco guarda segundos; a conversao e feita aqui."
                ),
            },
            "action": {"type": ["string", "null"], "example": "open"},
            "route_path": {"type": ["string", "null"], "example": "vod"},
            "app_bucket": {"type": ["string", "null"]},
            "app_env": {"type": ["string", "null"]},
            "app_target": {"type": ["string", "null"], "example": "dom-philco-netrange-2021"},
            "app_version": {"type": ["string", "null"]},
            "app_resolution": {"type": ["string", "null"]},
            "device_manufacturer": {"type": ["string", "null"], "example": "Philco"},
            "device_model": {"type": ["string", "null"]},
            "device_model_year": {
                "oneOf": [{"type": "integer"}, {"type": "string"}, {"type": "null"}],
                "description": (
                    "Ano do modelo. Aceita texto porque boa parte do parque responde "
                    "'unknown', e recusar esses eventos descartaria dois dos seis tipos."
                ),
            },
            "device_os": {"type": ["string", "null"], "example": "NetRange"},
            "device_os_version": {"type": ["string", "null"]},
            "device_resolution": {"type": ["string", "null"]},
            "clock_skew": {
                "type": "boolean",
                "description": (
                    "Relogio do aparelho muito fora do esperado. O evento e guardado "
                    "mesmo assim; a marca existe para o dashboard poder filtrar."
                ),
            },
            "attributes": {
                "type": "object",
                "additionalProperties": True,
                "description": (
                    "Campos especificos do tipo do evento, ja com dado pessoal removido."
                ),
            },
        },
        "required": ["event_id", "event_name", "occurred_at", "session_id", "device_id"],
    }


def _next_cursor_schema() -> dict[str, Any]:
    """Gera o esquema OpenAPI para o atributo de próximo cursor da paginação.

    Returns:
        dict[str, Any]: Esquema do cursor.
    """
    return {
        "type": ["string", "null"],
        "description": (
            "Cursor da proxima pagina. Nulo significa que nao ha mais "
            "resultados. Opaco: no fan-out ele guarda a posicao de cada "
            "particao, porque elas avancam em ritmos diferentes."
        ),
    }


def _query_stats_schema() -> dict[str, Any]:
    """Gera o esquema OpenAPI para as estatísticas de custo da consulta.

    Returns:
        dict[str, Any]: Esquema de estatísticas da query.
    """
    return {
        "type": "object",
        "description": (
            "Custo da consulta. Nao e debug: num banco que cobra por item lido, a "
            "diferenca entre `scanned` e `returned` e a conta do filtro que roda "
            "depois da consulta ao indice."
        ),
        "properties": {
            "strategy": {
                "type": "string",
                "enum": ["table:session", "gsi2:device", "gsi1:fanout", "table:scan"],
                "description": (
                    "Caminho de acesso usado. `table:scan` significa que nenhum "
                    "filtro permitiu usar indice e a tabela foi varrida -- informe "
                    "event_name, session_id ou device_id para evitar."
                ),
            },
            "queries": {"type": "integer", "description": "Consultas disparadas ao banco."},
            "scanned": {"type": "integer", "description": "Itens lidos (e cobrados)."},
            "returned": {"type": "integer", "description": "Itens devolvidos apos os filtros."},
        },
    }


def build_spec() -> dict[str, Any]:
    """Constrói o documento de especificação OpenAPI 3.1 da API de telemetria.

    Returns:
        dict[str, Any]: Especificação completa da API no padrão OpenAPI 3.1.0.
    """
    event_schema = _event_schema()
    common = _common_query_parameters()

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Argus — API de leitura de eventos",
            "version": API_VERSION,
            "description": (
                "Consulta dos eventos de telemetria do app de TV, para o dashboard.\n\n"
                "**Somente leitura.** A entrada de eventos e o pipeline "
                "`API Gateway -> SQS -> ECS Fargate -> DynamoDB`; esta API nao "
                "recebe, altera nem apaga evento.\n\n"
                "### Custo das consultas\n\n"
                "Toda busca devolve um bloco `query` com a estrategia usada e "
                "quantos itens foram lidos. Informar `event_name`, `session_id` ou "
                "`device_id` leva a uma consulta indexada; sem nenhum deles nao ha "
                "chave de particao e a tabela e varrida.\n\n"
                "### Privacidade\n\n"
                "`user_id` sai como hash com salt e o header `authorization` nunca "
                "e devolvido (RNF10). O dado bruto permanece no banco para quem "
                "tiver acesso direto e justificativa."
            ),
        },
        # Preenchido no request: a URL real nao fica escrita no repositorio.
        "servers": [{"url": _server_url(), "description": "Host atual"}],
        "tags": [
            {"name": "Eventos", "description": "Busca e detalhe"},
            {"name": "Investigacao", "description": "Sessao e aparelho"},
            {"name": "Metricas", "description": "Agregacoes para os graficos"},
            {
                "name": "Gold",
                "description": (
                    "Series, janelas e o relogio virtual. Tudo cortado em "
                    "sim.now() pela propria view"
                ),
            },
            {"name": "Saude", "description": "Sondas de disponibilidade"},
        ],
        "paths": {
            "/api/v1/events": {
                "get": {
                    "tags": ["Eventos"],
                    "summary": "Busca eventos com filtros cumulativos",
                    "description": (
                        "Todos os filtros combinam entre si. A ordem e do mais "
                        "recente para o mais antigo."
                    ),
                    "parameters": common + _pagination_parameters(),
                    "responses": {
                        "200": {
                            "description": "Pagina de eventos",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "items": {"type": "array", "items": event_schema},
                                            "next_cursor": _next_cursor_schema(),
                                            "query": _query_stats_schema(),
                                        },
                                    }
                                }
                            },
                        },
                        "422": {"$ref": "#/components/responses/Invalido"},
                    },
                }
            },
            "/api/v1/sessions/{session_id}": {
                "get": {
                    "tags": ["Investigacao"],
                    "summary": "Linha do tempo de uma sessao",
                    "description": (
                        "Consulta mais barata do sistema (uma particao) e a mais "
                        "util para investigar um incidente: mostra o que o usuario "
                        "fez antes do erro. Ordem cronologica crescente."
                    ),
                    "parameters": [
                        {
                            "name": "session_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 1000,
                                "default": 200,
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Eventos da sessao e resumo",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "session_id": {"type": "string"},
                                            "events": {"type": "array", "items": event_schema},
                                            "summary": {
                                                "type": "object",
                                                "description": "Cabecalho da tela de investigacao.",
                                                "properties": {
                                                    "event_count": {"type": "integer"},
                                                    "error_count": {"type": "integer"},
                                                    "by_event_name": {"type": "object"},
                                                    "started_at": {"type": "string"},
                                                    "ended_at": {"type": "string"},
                                                    "duration_seconds": {"type": "number"},
                                                    "device": {"type": "object"},
                                                    "app": {"type": "object"},
                                                },
                                            },
                                            "next_cursor": _next_cursor_schema(),
                                            "query": _query_stats_schema(),
                                        },
                                    }
                                }
                            },
                        },
                        "404": {"$ref": "#/components/responses/NaoEncontrado"},
                    },
                }
            },
            "/api/v1/sessions/{session_id}/events/{event_id}": {
                "get": {
                    "tags": ["Investigacao"],
                    "summary": "Detalhe de um evento",
                    "description": (
                        "A sessao faz parte da rota porque a chave da tabela e "
                        "(sessao, tempo+id): nao existe caminho para achar um evento "
                        "so pelo event_id sem varrer a tabela."
                    ),
                    "parameters": [
                        {
                            "name": "session_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "event_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Evento",
                            "content": {"application/json": {"schema": event_schema}},
                        },
                        "404": {"$ref": "#/components/responses/NaoEncontrado"},
                    },
                }
            },
            "/api/v1/devices/{device_id}": {
                "get": {
                    "tags": ["Investigacao"],
                    "summary": "Historico de um aparelho",
                    "parameters": [
                        {
                            "name": "device_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ]
                    + common
                    + _pagination_parameters(),
                    "responses": {
                        "200": {
                            "description": "Eventos do aparelho",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "items": {"type": "array", "items": event_schema},
                                            "next_cursor": _next_cursor_schema(),
                                            "query": _query_stats_schema(),
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/metrics/breakdown": {
                "get": {
                    "tags": ["Metricas"],
                    "summary": "Agrupa e conta por uma dimensao",
                    "parameters": common
                    + [
                        {
                            "name": "dimension",
                            "in": "query",
                            "required": True,
                            "description": "Campo pelo qual agrupar.",
                            "schema": {"type": "string", "enum": sorted(BREAKDOWN_FIELDS)},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "description": "Quantos grupos devolver, do maior para o menor.",
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 20,
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Grupos ordenados por contagem",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "dimension": {"type": "string"},
                                            "total": {"type": "integer"},
                                            "groups": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "key": {"type": "string"},
                                                        "count": {"type": "integer"},
                                                        "share": {
                                                            "type": "number",
                                                            "description": (
                                                                "Fracao do total,"
                                                                " arredondada em 4 casas."
                                                            ),
                                                        },
                                                        "average_duration_ms": {
                                                            "type": ["number", "null"]
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                    }
                                }
                            },
                        },
                        "422": {"$ref": "#/components/responses/Invalido"},
                    },
                }
            },
            "/api/v1/metrics/timeseries": {
                "get": {
                    "tags": ["Metricas"],
                    "summary": "Serie temporal do volume de eventos",
                    "description": (
                        "Com `compare=true`, devolve tambem a janela imediatamente "
                        "anterior de mesma duracao e a variacao entre as duas -- e o "
                        "que permite dizer 'os erros dobraram' em vez de so mostrar "
                        "a curva. Exige `from` e `to`."
                    ),
                    "parameters": common
                    + [
                        {
                            "name": "interval",
                            "in": "query",
                            "required": False,
                            "description": "Tamanho do balde, em minutos.",
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 1440,
                                "default": 60,
                            },
                        },
                        {
                            "name": "compare",
                            "in": "query",
                            "required": False,
                            "description": "Compara com o periodo anterior de mesma duracao.",
                            "schema": {"type": "boolean", "default": False},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Baldes e, opcionalmente, comparacao",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "interval_minutes": {"type": "integer"},
                                            "total": {"type": "integer"},
                                            "buckets": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "bucket": {
                                                            "type": "string",
                                                            "format": "date-time",
                                                        },
                                                        "count": {"type": "integer"},
                                                        "by_event_name": {"type": "object"},
                                                    },
                                                },
                                            },
                                            "previous": {
                                                "type": "object",
                                                "description": "Presente apenas com compare=true.",
                                            },
                                            "change": {
                                                "type": "object",
                                                "description": "Variacao absoluta e proporcional.",
                                                "properties": {
                                                    "absolute": {"type": "integer"},
                                                    "ratio": {"type": ["number", "null"]},
                                                },
                                            },
                                        },
                                    }
                                }
                            },
                        },
                        "422": {"$ref": "#/components/responses/Invalido"},
                    },
                }
            },
            "/api/v1/facets": {
                "get": {
                    "tags": ["Metricas"],
                    "summary": "Valores existentes para preencher os filtros",
                    "description": (
                        "Alimenta o autocompletar dos filtros do dashboard. "
                        "Campos que carregam dado pessoal nao sao aceitos."
                    ),
                    "parameters": [
                        {
                            "name": "field",
                            "in": "query",
                            "required": False,
                            "description": "Repetivel. Sem valor, devolve um conjunto padrao.",
                            "schema": {
                                "type": "array",
                                "items": {"type": "string", "enum": sorted(FACET_FIELDS)},
                            },
                            "style": "form",
                            "explode": True,
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 100,
                                "default": 20,
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Valores por campo",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "facets": {
                                                "type": "object",
                                                "additionalProperties": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                },
                                            }
                                        },
                                    }
                                }
                            },
                        },
                        "422": {"$ref": "#/components/responses/Invalido"},
                    },
                }
            },
            "/api/v1/clock": {
                "get": {
                    "tags": ["Gold"],
                    "summary": "O instante VIRTUAL, que e o 'agora' de todas as telas",
                    "description": (
                        "Sem esta rota o dashboard usaria o relogio do navegador como "
                        "'agora', e as telas apareceriam vazias sem explicar por que: "
                        "o simulador pode estar replicando uma janela de julho enquanto "
                        "o navegador marca agosto."
                    ),
                    "responses": {
                        "200": {
                            "description": "Relogio virtual",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "sim_now": {"type": "string", "format": "date-time"},
                                            "speed": {"type": "number"},
                                            "updated_at": {
                                                "type": "string",
                                                "format": "date-time",
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/series": {
                "get": {
                    "tags": ["Gold"],
                    "summary": "Serie de telemetria em bucket de 15 min",
                    "description": (
                        "Le `gold.v_feature_bucket`. So devolve o que ja passou de "
                        "`available_at` no relogio virtual -- e o filtro e da VIEW, "
                        "nao da aplicacao."
                    ),
                    "parameters": [
                        _parameter("source", "Fonte (prometheus, youbora, rpaas...)."),
                        _parameter("entity", "Entidade dentro da fonte."),
                        _parameter("metric", "Metrica."),
                        _parameter("from", "Inicio da janela, ISO-8601."),
                        _parameter("to", "Fim da janela, ISO-8601."),
                        {
                            "name": "window_hours",
                            "in": "query",
                            "required": False,
                            "description": (
                                "Janela assumida quando from/to nao vem, "
                                "contada de sim.now()."
                            ),
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 8760,
                                "default": 24,
                            },
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 20000,
                                "default": 5000,
                            },
                        },
                    ],
                    "responses": {
                        "200": {"description": "Pontos da serie"},
                        "422": {"$ref": "#/components/responses/Invalido"},
                    },
                }
            },
            "/api/v1/sources": {
                "get": {
                    "tags": ["Gold"],
                    "summary": "Fontes disponiveis e quao recente esta cada uma",
                    "description": (
                        "`ultimo_bucket` e o que sustenta o 'fontes com desvio: 3 de 13' "
                        "do painel lateral: uma fonte cujo ultimo bucket ficou para tras "
                        "parou de reportar."
                    ),
                    "responses": {"200": {"description": "Fontes"}},
                }
            },
            "/api/v1/incidents": {
                "get": {
                    "tags": ["Gold"],
                    "summary": "Janelas de incidente do ground truth",
                    "description": (
                        "Por padrao EXCLUI os rotulos `detector-derived`: sete dos vinte "
                        "foram criados olhando a saida do proprio Argus, e avaliar um "
                        "detector novo contra eles mede concordancia com o baseline, nao "
                        "acuracia. Inclui-los exige `include_derived=true`, explicitamente."
                    ),
                    "parameters": [
                        {
                            "name": "origem",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "enum": ["incidents", "incident_label", "detector"],
                            },
                        },
                        {
                            "name": "include_derived",
                            "in": "query",
                            "required": False,
                            "description": "Inclui os rotulos derivados do proprio detector.",
                            "schema": {"type": "boolean", "default": False},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 1000,
                                "default": 100,
                            },
                        },
                    ],
                    "responses": {
                        "200": {"description": "Janelas de incidente"},
                        "422": {"$ref": "#/components/responses/Invalido"},
                    },
                }
            },
            "/api/v1/live-events": {
                "get": {
                    "tags": ["Gold"],
                    "summary": "Calendario de transmissoes ao vivo",
                    "description": (
                        "Agrupado por `event_key` e nao por horario: os tid 994 e 995 sao "
                        "feeds SIMULTANEOS com jogos diferentes, porque a Globo transmite "
                        "partidas distintas em pracas distintas no mesmo horario. O campo "
                        "`feeds` traz os tid agregados de cada confronto."
                    ),
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 500,
                                "default": 50,
                            },
                        }
                    ],
                    "responses": {"200": {"description": "Transmissoes"}},
                }
            },
            "/api/v1/anomalies": {
                "get": {
                    "tags": ["Gold"],
                    "summary": "Anomalias da execucao mais recente do detector",
                    "description": (
                        "Devolve lista VAZIA enquanto nao houver detector (decisao 7 do "
                        "plano: processamento e deteccao seguem embrionarios). A rota "
                        "existe desde ja para que o dashboard seja escrito contra o "
                        "contrato final e nao precise mudar quando a deteccao chegar."
                    ),
                    "parameters": [
                        {
                            "name": "run_id",
                            "in": "query",
                            "required": False,
                            "description": "Execucao. Sem valor, usa a mais recente.",
                            "schema": {"type": "integer"},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 2000,
                                "default": 200,
                            },
                        },
                    ],
                    "responses": {"200": {"description": "Anomalias"}},
                }
            },
            "/health/live": {
                "get": {
                    "tags": ["Saude"],
                    "summary": "A aplicacao respondeu",
                    "responses": {"200": {"description": "Viva"}},
                }
            },
            "/health/ready": {
                "get": {
                    "tags": ["Saude"],
                    "summary": "A aplicacao alcanca o banco",
                    "responses": {
                        "200": {"description": "Pronta"},
                        "503": {"description": "Banco inalcancavel"},
                    },
                }
            },
        },
        "components": {
            "responses": {
                "Invalido": {
                    "description": "Parametro invalido",
                    "content": {
                        "application/problem+json": {
                            "schema": {"$ref": "#/components/schemas/Problema"}
                        }
                    },
                },
                "NaoEncontrado": {
                    "description": "Recurso inexistente",
                    "content": {
                        "application/problem+json": {
                            "schema": {"$ref": "#/components/schemas/Problema"}
                        }
                    },
                },
            },
            "schemas": {
                "Evento": event_schema,
                "Problema": {
                    "type": "object",
                    "description": "Erro no formato RFC 7807.",
                    "properties": {
                        "type": {"type": "string"},
                        "title": {"type": "string"},
                        "status": {"type": "integer"},
                        "detail": {"type": "string"},
                        "instance": {"type": "string"},
                        "field": {
                            "type": "string",
                            "description": "Parametro que causou a recusa, quando aplicavel.",
                        },
                    },
                },
            },
        },
    }


def _server_url() -> str:
    """URL base derivada da requisicao.

    Fora de um contexto de requisicao devolve um caminho relativo -- assim a
    spec pode ser gerada em build ou em teste sem depender de host nenhum, e
    sem nunca embutir o endereco real.
    """
    try:
        return request.url_root.rstrip("/")
    except RuntimeError:
        return "/"


SWAGGER_UI = """<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Argus — API de leitura</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  </head>
  <body>
    <div id="swagger"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
      window.ui = SwaggerUIBundle({
        url: "./openapi.json",
        dom_id: "#swagger",
        deepLinking: true,
        docExpansion: "list",
        defaultModelsExpandDepth: 1,
      });
    </script>
  </body>
</html>
"""
