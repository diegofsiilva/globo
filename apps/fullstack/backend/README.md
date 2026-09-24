# API de telemetria e hipóteses

API Flask que serve telemetria e hipóteses para o dashboard. A entrada de
eventos continua no pipeline `API Gateway → SQS → ECS Fargate → RDS PostgreSQL`.
A única escrita desta API é o feedback idempotente de uma hipótese publicada.

Publicada em Lambda + API Gateway.

Ela lê dois grains diferentes, e por isso tem dois adaptadores:

| Adaptador | Grain | Serve |
|---|---|---|
| `infrastructure/postgres.py` | evento individual de sessão | busca, filtros, breakdown, série, facetas |
| `infrastructure/gold.py` | bucket agregado de 15 min | relógio, séries, incidentes, transmissões e anomalias |
| `infrastructure/hypotheses.py` | hipótese publicada | runs, listagem, detalhe, evidências e feedback |

São separados de propósito: um repositório único teria dois conjuntos de métodos
que nunca se cruzam, e a `EventFilters` acabaria com campos que só metade dos
métodos usa.

## A regra que vale para toda consulta

**Nenhuma leitura toca uma tabela base.** Todas apontam para uma view `v_*`.
O feedback chama apenas a função `SECURITY DEFINER`
`gold.submit_hypothesis_feedback`.

O usuário do banco que a Lambda usa (`argus_reader`) tem `SELECT` só nas views —
não é uma convenção que se possa esquecer de seguir, é um `GRANT`. Uma consulta
escrita contra a tabela base falha com permissão negada.

Isso existe porque o dataset é um dump do passado sendo reproduzido por um
relógio virtual. Sem a barreira, a API mostraria dados que, na linha do tempo
simulada, ainda não teriam acontecido — e um detector treinado sobre eles estaria
enxergando o futuro.

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
cd apps/fullstack/infra
terraform output -raw read_api_url
```

---

## Rotas

### Eventos de sessão

| Rota | Para quê | Requisito |
|---|---|---|
| `GET /api/v1/events` | busca com filtros cumulativos | RF08, RF09 |
| `GET /api/v1/sessions/{id}` | linha do tempo de uma sessão + resumo | RF16 |
| `GET /api/v1/sessions/{id}/events/{event_id}` | detalhe de um evento | RF16 |
| `GET /api/v1/devices/{id}` | histórico de um aparelho | RF16 |
| `GET /api/v1/metrics/breakdown?dimension=` | agrupamento e contagem | RF11 |
| `GET /api/v1/metrics/timeseries?compare=true` | série temporal e comparação | RF12, RF14, RF15 |
| `GET /api/v1/facets?field=` | valores existentes para os filtros | RF10 |

### Telemetria e hipóteses (camada gold)

| Rota | Para quê |
|---|---|
| `GET /api/v1/clock` | o instante virtual, a velocidade e o último reposicionamento |
| `GET /api/v1/series` | pontos de `gold.feature_bucket`, por fonte/entidade/métrica |
| `GET /api/v1/sources` | as fontes disponíveis via `gold.v_source_series` e o quão recente é cada uma |
| `GET /api/v1/incidents` | janelas de incidente rotuladas |
| `GET /api/v1/live-events` | calendário de transmissões ao vivo |
| `GET /api/v1/anomalies` | saída do detector |
| `GET /api/v1/hypothesis-runs` | runs concluídos de manifestos publicados |
| `GET /api/v1/hypotheses` | listagem filtrável com paginação keyset |
| `GET /api/v1/hypotheses/{id}` | linhagem, findings, evidências, qualidade e score |
| `POST /api/v1/hypotheses/{id}/feedback` | feedback idempotente; payload máximo de 4 KiB |
| `POST /api/v1/hypotheses/{id}/refinement` | resposta Ollama ancorada na hipótese e em suas evidências |

| Rota | Para quê |
|---|---|
| `GET /health/live` · `GET /health/ready` | saúde |
| `GET /docs` · `GET /openapi.json` | documentação |

`/clock` não é curiosidade: a tela é marcada "ao vivo", então ela precisa saber
que horas são no mundo virtual. Sem isso, "agora" no dashboard seria o relógio do
navegador, que não tem relação nenhuma com o que o banco está mostrando — e a
tela pareceria vazia sem explicar por quê.

`/sources` não agrega `gold.v_feature_bucket` a cada request. Com a carga real,
os dois `count(DISTINCT ...)` sobre 4,9 milhões de buckets levaram 47,4 s e
estouraram o timeout da Lambda. A rota lê o catálogo derivado
`gold.v_source_series` e faz apenas uma sondagem indexada por fonte para obter o
bucket mais recente; o mesmo `sim.now()` continua impedindo vazamento de futuro.

As views de hipóteses ficam vazias durante o modo sombra. Um manifesto só aparece
depois do evento append-only `published`; `withdrawn` volta a ocultá-lo sem apagar
o histórico.

`/incidents` **exclui** por padrão os rótulos `detector-derived`: sete dos vinte
rótulos de `incident_label` foram criados olhando a saída do próprio Argus, e
avaliar um detector novo contra eles mediria concordância com o baseline, não
acurácia. Para incluí-los é preciso pedir explicitamente.

Filtros aceitos em `/events` e nas métricas, todos combináveis: `session_id`,
`device_id`, `event_name`, `app_env`, `app_target`, `app_version`, `app_bucket`,
`device_os`, `device_manufacturer`, `device_model`, `route_path`, `from`, `to`,
`limit`, `cursor`.

### Exemplos

```bash
source ../.env       # define ARGUS_API_URL
API="$ARGUS_API_URL"

curl "$API/api/v1/clock"
curl "$API/api/v1/series?source=prometheus&metric=error_rate&window_hours=48"
curl "$API/api/v1/incidents?limit=10"
curl "$API/api/v1/events?event_name=error&device_os=WebOS&limit=20"
curl "$API/api/v1/metrics/breakdown?dimension=device_manufacturer"
curl "$API/api/v1/facets?field=event_name&field=app_target"
```

---

## Duas coisas que a resposta te diz

**`query`** aparece em toda busca:

```json
{"strategy": "indice_tipo_e_tempo", "scanned": 50, "returned": 5}
```

Isso não é debug — é o custo da consulta. `strategy` diz qual caminho de acesso
foi usado:

| `strategy` | Quando | Custo |
|---|---|---|
| `indice_sessao` | você passou `session_id` | índice, exato |
| `indice_aparelho` | você passou `device_id` | índice |
| `indice_tipo_e_tempo` | você passou `event_name` | índice composto |
| `particao_por_tempo` | nenhum dos três | varre as partições da janela |

Na v2 a diferença era de custo por item lido; aqui é entre usar índice e varrer
partição. **Sempre que puder, informe `event_name`, `session_id` ou
`device_id`.**

**`next_cursor`** pagina. Passe de volta em `?cursor=`. É paginação por *keyset*
e não por `OFFSET`: o cursor carrega a posição exata da última linha lida, então
o custo da página 200 é igual ao da página 1. É opaco (base64) porque o formato
interno é livre para mudar.

Cursor corrompido devolve **422**, não a primeira página em silêncio: um laço de
paginação com token quebrado giraria para sempre lendo o mesmo trecho.

---

## Privacidade (RNF10)

A bronze guarda o evento como o aparelho enviou — `user_id` em claro e o header
`authorization` inclusive, porque é isso que a origem manda. **A redação
acontece na saída da API**, não na entrada:

- `user_id` → `user_id_hash` (SHA-256 com salt, truncado em 16 caracteres)
- `request_headers` → só a allowlist em `application/redaction.py`
- `request_url` → query string sem `token`, `access_token`, `user_id`
- `response_headers` → removido inteiro

O salt é fixo, o que preserva o agrupamento: dá para dizer "estes 40 eventos são
do mesmo usuário" sem saber de quem. O dado bruto continua no banco para quem
tiver acesso direto e justificativa; o que trafega para a tela é a versão
reduzida.

---

## Rodar local

Com um PostgreSQL local (`make -C .. db-local`):

```bash
make -C .. api
```

Ou direto, apontando para onde você quiser:

```bash
DATABASE_URL=postgresql://argus:argus@localhost:55432/argus \
  uv run --extra dev python lambda_handler.py
```

Contra o banco publicado, monte a URL com `make -C .. db-url`. Repare que a
Lambda em produção usa o usuário `argus_reader`, não o dono do schema — se você
rodar local com o dono, consultas que a produção recusaria vão passar.

### Variáveis

| Variável | Padrão | Observação |
|---|---|---|
| `DATABASE_URL` | — | obrigatória; sem ela o `/health/ready` falha |
| `AWS_REGION` | `us-east-1` | |
| `USER_ID_HASH_SALT` | `local-development-only` | trocar reembaralha os hashes |
| `DEFAULT_WINDOW_HOURS` | `168` | janela quando não se informa período |
| `MAX_ITEMS_SCANNED` | `20000` | teto de linhas lidas numa agregação |
| `CORS_ORIGINS` | `*` | restringir antes de produção |
| `OLLAMA_URL` | — | habilita o refinamento; com SSH pode ser `http://ollama.internal:11434` |
| `OLLAMA_MODEL` | — | opcional; vazio seleciona o primeiro modelo instalado |
| `OLLAMA_TIMEOUT_SECONDS` | `90` | timeout total da inferência; o modelo remoto atual tem 30B |
| `OLLAMA_SSH_HOST` | — | host SSH fornecido pelo parceiro |
| `OLLAMA_SSH_PORT` | `22` | porta SSH |
| `OLLAMA_SSH_USER` | — | usuário SSH |
| `OLLAMA_SSH_PASSWORD` | — | senha somente no `.env` ignorado pelo Git |
| `OLLAMA_REMOTE_HOST` | `127.0.0.1` | endereço do Ollama visto pelo servidor remoto |
| `OLLAMA_REMOTE_PORT` | `11434` | porta do Ollama no servidor remoto |

### Ollama remoto por SSH

O refinamento acontece depois da leitura da hipótese publicada; ele não altera o
motor determinístico, o score ou as evidências. Cada afirmação devolvida precisa
citar ids presentes na hipótese. Formato inválido, citação inexistente ou falha
de rede resulta em `503`, sem resposta parcialmente aterrada.

Preencha no `.env` apenas os dados recebidos:

```env
OLLAMA_SSH_HOST=10.8.8.10
OLLAMA_SSH_USER=<usuario>
OLLAMA_SSH_PASSWORD=<senha>
OLLAMA_URL=http://ollama.internal:11434
```

Ao iniciar o backend, o adaptador prepara uma sessão SSH persistente. Quando a
tela recebe uma hipótese, ela solicita o refinamento automaticamente e o backend
executa o cliente HTTP no próprio servidor remoto; não há botão nem comando de
túnel, e não é necessário habilitar port forwarding no SSH. Se
`OLLAMA_MODEL` estiver vazio, o backend consulta `/api/tags` pelo mesmo canal e
usa o primeiro modelo instalado. A senha existe somente no `.env` local, que é
ignorado pelo Git.

Se a conta foi criada com senha temporária, faça uma única conexão interativa
com `ssh <usuario>@10.8.8.10`, defina a nova senha solicitada pelo servidor e
atualize `OLLAMA_SSH_PASSWORD`. As inferências seguintes são inteiramente
automáticas e não usam o terminal.

Exemplo de chamada:

```bash
curl -X POST "$API/api/v1/hypotheses/42/refinement" \
  -H "Content-Type: application/json" \
  -d '{"question":"Quais evidencias sustentam esta hipotese?"}'
```

O pool nasce com `min_size=0` de propósito, o oposto do que se faz num worker:
uma Lambda ociosa é congelada, e conexões ociosas de centenas de execuções
congeladas esgotariam o `max_connections` do RDS sem ninguém estar usando nada.

## Testes

```bash
make -C .. db-local      # sobe o PostgreSQL de teste
make -C .. test-backend
```

Os testes rodam contra um PostgreSQL **de verdade**, e não contra um dublê. Duas
razões:

1. A parte difícil deste adaptador é o SQL — o keyset da paginação, o `date_bin`
   da série temporal, o `GROUP BY` do breakdown. Um dublê que respondesse "ok" a
   tudo isso testaria apenas o dublê, que foi exatamente o defeito encontrado no
   backend anterior.

2. A barreira contra vazamento de futuro é do **banco** (o `GRANT` em
   `argus_reader` mais o `WHERE available_at <= sim.now()` da view). Só dá para
   verificar isso contra um banco que tem `GRANT` e tem view.

O dado entra pelas mesmas fixtures que o worker usa, e monta a linha com o mesmo
`build_row` — é o que impede a API e o worker de divergirem em silêncio sobre o
que é envelope e o que é payload. Sem `TEST_DATABASE_URL`, os testes que precisam
de banco são **pulados**, não quebrados.

## Deploy

```bash
./scripts/build_lambda.sh                       # gera dist/telemetry-read-api.zip
cd ../infra && terraform apply
```

O `psycopg[binary]` **entra** no zip, e é a parte delicada do empacotamento: a
Lambda roda ARM64, então o wheel precisa ser o `manylinux2014_aarch64` — instalar
sem `--platform` numa máquina x86 (ou num Mac ARM) produz um zip que importa
localmente e estoura em produção. O script força a plataforma e depois **confere**
que `psycopg_binary` foi parar no pacote.

O `boto3` não entra: o runtime da Lambda já o traz.

---

## Arquitetura

Hexagonal: `EventRepository` é um `Protocol` em `ports/`, e `infrastructure/` é a
única camada que sabe qual é o banco. A troca de DynamoDB para PostgreSQL foi
exatamente isso — um adaptador novo, com `domain/`, `ports/` e `application/`
intocados.

```
domain/entities.py         TelemetryEvent, alinhado ao que o worker grava
ports/                     contrato de leitura (filtros, página, métricas)
infrastructure/postgres.py adaptador de eventos: roteamento de índice, keyset
infrastructure/gold.py     adaptador da camada gold: relógio, séries, janelas
application/use_cases.py   orquestração das consultas do dashboard
application/redaction.py   remoção de dado pessoal na saída
interfaces/http.py         rotas Flask
interfaces/openapi.py      a spec, montada a partir das constantes do adaptador
```
