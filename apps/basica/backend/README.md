# API de leitura dos eventos

API Flask que serve os eventos de telemetria para a dashboard. **Somente
leitura**: a entrada de eventos é o pipeline
`API Gateway → SQS → ECS Fargate → DynamoDB` (ver [`worker/`](../worker) e
[`infra/`](../infra)).

Publicada em Lambda + API Gateway.

## Documentação interativa

A própria API se documenta:

| Rota | O que é |
|---|---|
| `GET /docs` | Swagger UI |
| `GET /openapi.json` | especificação OpenAPI 3.1 |

A spec é montada em código, importando as mesmas constantes que o adaptador usa
para validar — documentação que deriva da regra não consegue divergir dela. Há
teste travando isso nos dois sentidos: rota sem documentação e documentação sem
rota quebram a suíte.

## Como obter a URL

**A URL não está escrita em lugar nenhum do repositório**, de propósito. Pegue
do Terraform e guarde no `.env` (que é gitignored):

```bash
cd apps/basica/infra
terraform output -raw read_api_url
```

Depois, no `.env` da raiz:

```bash
ARGUS_API_URL=https://...
```

---

## Rotas

| Rota | Para quê | Requisito |
|---|---|---|
| `GET /api/v1/events` | busca com filtros cumulativos | RF08, RF09 |
| `GET /api/v1/sessions/{id}` | linha do tempo de uma sessão + resumo | RF16 |
| `GET /api/v1/sessions/{id}/events/{event_id}` | detalhe de um evento | RF16 |
| `GET /api/v1/devices/{id}` | histórico de um aparelho | RF16 |
| `GET /api/v1/metrics/breakdown?dimension=` | agrupamento e contagem | RF11 |
| `GET /api/v1/metrics/timeseries?compare=true` | série temporal e comparação | RF12, RF14, RF15 |
| `GET /api/v1/facets?field=` | valores existentes para os filtros | RF10 |
| `GET /health/live` · `GET /health/ready` | saúde | — |
| `GET /docs` · `GET /openapi.json` | documentação | — |

Filtros aceitos em `/events` e nas métricas, todos combináveis: `session_id`,
`device_id`, `event_name`, `app_env`, `app_target`, `app_version`, `app_bucket`,
`device_os`, `device_manufacturer`, `device_model`, `route_path`, `from`, `to`,
`limit`, `cursor`.

### Exemplos

```bash
source ../../.env       # define ARGUS_API_URL
API="$ARGUS_API_URL"

curl "$API/api/v1/events?event_name=error&device_os=WebOS&limit=20"
curl "$API/api/v1/metrics/breakdown?dimension=device_manufacturer"
curl "$API/api/v1/metrics/timeseries?from=2026-08-01T00:00:00Z&to=2026-08-12T00:00:00Z&compare=true"
curl "$API/api/v1/facets?field=event_name&field=app_target"
```

---

## Duas coisas que a resposta te diz

**`query`** aparece em toda busca:

```json
{"strategy": "gsi1:fanout", "queries": 80, "scanned": 50, "returned": 5}
```

Isso não é debug — é o custo da consulta. Num banco que cobra por item lido, a
diferença entre `scanned` e `returned` é a conta do filtro que roda depois da
query, e `strategy` diz qual caminho de acesso foi usado:

| `strategy` | Quando | Custo |
|---|---|---|
| `table:session` | você passou `session_id` | 1 query, exato |
| `gsi2:device` | você passou `device_id` | 1 query |
| `gsi1:fanout` | você passou `event_name` | N queries paralelas (dias × shards) |
| `table:scan` | nenhum dos três | varre a tabela |

**Sempre que puder, informe `event_name`, `session_id` ou `device_id`.** Sem
nenhum deles não existe chave de partição e só resta varrer.

**`next_cursor`** pagina. Passe de volta em `?cursor=`. É opaco: no fan-out ele
guarda a posição de cada partição, porque as partições avançam em ritmos
diferentes no merge por tempo.

---

## Privacidade (RNF10)

O worker grava o evento como o aparelho enviou, então o DynamoDB tem `user_id`
em claro e o header `authorization`. **A redação acontece na saída da API**, não
na entrada:

- `user_id` → `user_id_hash` (SHA-256 com salt, truncado)
- `request_headers` → só a allowlist em `application/redaction.py`
- `request_url` → query string sem `token`, `access_token`, `user_id`
- `response_headers` → removido inteiro

O dado bruto continua no banco para quem tiver acesso direto e justificativa; o
que trafega para a tela é a versão reduzida.

---

## Rodar local

```bash
cd apps/basica/backend
uv run --with flask --with boto3 python lambda_handler.py
```

Aponta para o DynamoDB real usando o profile da sua AWS:

```bash
AWS_PROFILE=g4 EVENTS_TABLE_NAME=argus-events-dev GSI1_SHARDS=10 \
  uv run --with flask --with boto3 python lambda_handler.py
```

Ou via compose (ver [`compose.yaml`](compose.yaml), que também explica como
usar um DynamoDB local).

### Variáveis

| Variável | Padrão | Observação |
|---|---|---|
| `EVENTS_TABLE_NAME` | `argus-events-dev` | tabela que o worker escreve |
| `AWS_REGION` | `us-east-1` | |
| `GSI1_SHARDS` | `10` | **precisa bater** com o Terraform e o worker |
| `USER_ID_HASH_SALT` | `local-development-only` | trocar reembaralha os hashes |
| `DEFAULT_WINDOW_HOURS` | `168` | janela quando não se informa período |
| `MAX_ITEMS_SCANNED` | `20000` | teto de itens lidos numa agregação |
| `CORS_ORIGINS` | `*` | restringir antes de produção |

> `GSI1_SHARDS` é o valor mais perigoso da lista. Ele monta a chave da GSI1 na
> escrita e na leitura; se divergir, a API consulta partições onde o worker
> nunca gravou e devolve **vazio, sem erro nenhum**.

## Testes

```bash
uv run --with flask --with boto3 --with 'moto[dynamodb]' --with pytest --with pydantic \
  python -m pytest
```

Os testes gravam itens no formato **exato** que o worker produz, e
`test_formato_do_item_espelha_o_worker` importa a implementação real do worker
para comparar as chaves. Sem essa trava, os testes passariam com um formato
conveniente enquanto a API quebra contra o banco de verdade.

## Deploy

```bash
./scripts/build_lambda.sh                       # gera dist/telemetry-read-api.zip
cd ../infra && terraform apply
```

O `boto3` não entra no zip — o runtime da Lambda já o traz. Sobram Flask e
apig-wsgi, ambos Python puro, o que faz o mesmo pacote servir ARM64 e x86.

---

## Arquitetura

Hexagonal, como o backend original: `EventRepository` é um `Protocol` em
`ports/`, e `infrastructure/dynamo.py` é a única peça que sabe que o banco é
DynamoDB. Trocar de banco é escrever outro adaptador.

```
domain/entities.py       TelemetryEvent, alinhado ao que o worker grava
ports/                   contrato de leitura (filtros, página, métricas)
infrastructure/dynamo.py adaptador: roteamento de índice, fan-out, cursor
application/use_cases.py orquestração das consultas do dashboard
application/redaction.py remoção de dado pessoal na saída
interfaces/http.py       rotas Flask
```
