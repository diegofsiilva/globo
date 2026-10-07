# Back-end

&emsp; Este artefato descreve a estrutura e a implementação do back-end da
plataforma de Monitoração Agêntica: organização do código, segurança,
autenticação, testes de endpoints e integração com o front-end, conforme a
especificação do módulo. Atualizado em 27/08/2026 após o merge de
`feat/rotas-backend` em `develop`: as rotas descritas aqui já estão na
`develop`, junto com o motor de hipóteses e o novo design do front, feitos
por outros integrantes do time. A seção 6 lista o que falta para atender a
rubrica por completo.

&emsp; Divergência de nomenclatura entre a especificação e o repositório:
a especificação referencia a pasta de código-fonte como `/apps/backend`; no
repositório o caminho real é [`apps/fullstack/backend`](../apps/fullstack/backend)
(a API de leitura) e [`apps/fullstack/worker`](../apps/fullstack/worker) (a
ingestão). A aplicação completa fica em `apps/fullstack`. Referências neste documento
usam esse caminho.

## 1. Objetivo

&emsp; Apresentar a API de leitura (`apps/fullstack/backend`) que serve o
dashboard: como o código está organizado, quais endpoints existem, como cada
um foi testado, e o estado atual de persistência, autenticação e log,
incluindo o que está pendente.

## 2. Escopo coberto por este artefato

&emsp; Este artefato cobre a **API de leitura**, responsável pelos endpoints
que o dashboard consome. A **ingestão** (API Gateway → SQS → worker →
banco) é um serviço separado, com ciclo de vida e testes próprios em
`apps/fullstack/worker`, e não é o foco aqui; é citada apenas onde necessário
para explicar persistência e autenticação de ponta a ponta.

&emsp; Dentro da API de leitura, este documento detalha em profundidade as
rotas que sustentam as telas Agora, Explorar, Comparar, Timeline e Recorte
(seção 4), que foram o trabalho desta frente. As rotas do motor de
hipóteses (RF17), isto é `GET /api/v1/hypotheses`, `GET
/api/v1/hypotheses/{id}`, `POST /api/v1/hypotheses/{id}/feedback` e `GET
/api/v1/hypothesis-runs`, foram implementadas por outro integrante do
time e já estão mescladas em `develop`; aparecem na matriz de
rastreabilidade (seção 5.1.b) para fechar a cobertura de RF, mas o
detalhamento de organização de código e teste delas é responsabilidade de
quem as implementou, não desta frente.

### 2.1 Diagrama de implantação

&emsp; Para contextualizar o ecossistema no qual a API de leitura se insere, a figura abaixo exibe o diagrama de implantação do Linceu na AWS, detalhado em profundidade no artefato de arquitetura inicial.

<div align="center">

<sub>Figura 1 — Implantação do Linceu na AWS, região `us-east-1`</sub>

![Diagrama de implantação do Linceu v3](assets/arquitetura-implantacao-v3.svg)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

## 3. Organização do código

&emsp; `apps/fullstack/backend/src/telemetry/` segue arquitetura hexagonal, em
quatro camadas:

| Camada | Pasta | Responsabilidade |
|---|---|---|
| Domínio | `domain/` | Entidades (`TelemetryEvent`) e exceções de negócio |
| Aplicação | `application/` | Casos de uso, orquestram repositório e regra, sem SQL |
| Infraestrutura | `infrastructure/` | Adaptadores PostgreSQL, todo SQL mora aqui |
| Interfaces | `interfaces/` | Blueprints Flask (rotas HTTP) e especificação OpenAPI |

&emsp; A regra de dependência é de fora para dentro: `interfaces` chama
`application`, que chama `infrastructure` através de uma porta
(`ports/event_repository.py`). Nenhuma rota HTTP monta SQL diretamente, e
nenhum adaptador de banco conhece o Flask, o que permite testar
`application/` com um repositório falso, sem banco.

&emsp; Convenções observadas em todo o código: type hints em toda função
pública, docstring no padrão Google (`Args`/`Returns`/`Raises`) em toda
função e classe pública, nomes em português para o domínio do negócio
(`filters_from_query`, `desvios`, `janela_estavel`) e em inglês para termos
técnicos genéricos (`repository`, `filters`). Lint (`ruff check`) e
formatação (`ruff format`) sem exceção em todo o código novo desta etapa.

## 4. Endpoints

&emsp; Tabela completa dos endpoints da API de leitura, com o método, uma
descrição de uma linha e o RF principal que cada um atende. RF17
(hipóteses) fica de fora pelo motivo explicado na seção 2.

| Método | Caminho | Descrição | RF principal |
|---|---|---|---|
| `GET` | `/api/v1/events` | Busca paginada de eventos, com filtros cumulativos | RF08, RF09 |
| `GET` | `/api/v1/sessions/{session_id}` | Linha do tempo completa de uma sessão | RF16 |
| `GET` | `/api/v1/sessions/{session_id}/events/{event_id}` | Detalhe de um evento específico | RF16 |
| `GET` | `/api/v1/devices/{device_id}` | Histórico de eventos de um aparelho | RF16 |
| `GET` | `/api/v1/facets` | Valores existentes para preencher filtros | RF10 |
| `GET` | `/api/v1/metrics/breakdown` | Agrupamento por uma dimensão | RF11 |
| `GET` | `/api/v1/metrics/crosstab` | Agrupamento por duas dimensões (heatmap) | RF11, RF16 |
| `GET` | `/api/v1/metrics/timeseries` | Série temporal, com comparação de janela | RF12, RF14 |
| `GET` | `/api/v1/signals` | Sinais em desvio ativo (degradação, v1 simplificada) | RF15 |
| `GET` | `/api/v1/changes` | Eventos de mudança de infraestrutura (deploy) | RF16 |
| `GET` | `/api/v1/timeline` | Seis raias de fonte num eixo temporal | RF16 |
| `GET` | `/api/v1/references/stable-window` | Referência de janela sem incidente | RF14 |
| `GET` | `/api/v1/references/last-live-peak` | Referência de último pico ao vivo | RF14 |
| `GET` | `/api/v1/clock` | Instante do relógio virtual da simulação | (suporte) |
| `GET` | `/api/v1/series` | Série de telemetria em bucket de 15 min | RF12 |
| `GET` | `/api/v1/sources` | Fontes disponíveis e recência | (suporte) |
| `GET` | `/api/v1/anomalies` | Anomalias da execução mais recente do detector | RF13, RF15 |
| `GET` | `/health/live`, `/health/ready` | Liveness/readiness | (operação) |
| `GET` | `/docs`, `/openapi.json` | Documentação interativa (Swagger) | (operação) |

&emsp; A API é **somente leitura**: não há `POST`, `PUT`, `PATCH` nem
`DELETE`. A entrada de dado é exclusivamente pelo pipeline de ingestão
(`apps/fullstack/worker`), o que elimina duas superfícies de validação
divergentes; ver `interfaces/http.py`, docstring do módulo.

## 5. Itens da especificação

### 5.1 (1) Relatório

#### 5.1.a Testes dos endpoints com Postman

&emsp; A fonte da verdade desta verificação foi o mapa de rotas registrado pelo
Flask a partir de `apps/fullstack/backend/src/telemetry/interfaces/`. Foram
encontradas **33 rotas distintas**: 32 `GET` (incluindo o `GET /favicon.ico`,
que devolve 204) e um `POST`. A collection exportada e versionada continua no mesmo caminho
da sprint anterior:
[`artefatos/postman/argus.postman_collection.json`](postman/argus.postman_collection.json)
(modelo de environment sem segredos em
[`artefatos/postman/environment.example.json`](postman/environment.example.json)).

&emsp; **Autenticação:** O controle de acesso foi implementado na infraestrutura via Lambda Authorizer (`apps/fullstack/authorizer`, `apps/fullstack/infra/auth.tf`), exigindo cabeçalho `Authorization: Bearer <token>` com audiência `dashboard` para a API de leitura. A coleção está configurada com `auth: bearer` no nível da coleção (`{{read_token}}`, tipo `secret` no environment) e herda para todas as rotas protegidas; as três rotas públicas (`GET /health/live`, `GET /docs`, `GET /openapi.json`) têm `auth: noauth` explícito. Sem token o API Gateway responde **401** e com token inválido o Authorizer responde **403** (validado no `make smoke`). O `POST` de feedback usa somente identificadores e texto sintéticos, sem dado pessoal.

##### Diagnóstico antes da atualização

| Situação inicial | Quantidade de rotas | Evidência encontrada na collection anterior |
|---|---:|---|
| ✅ Coberta | 7 | `health/ready`, eventos, sessão, aparelho, facets, breakdown e timeseries tinham request e asserts relevantes |
| ⚠️ Parcial | 9 | raiz, relógio, OpenAPI, sinais, crosstab, mudanças, referências e timeline tinham request, mas nenhum assert associado |
| ❌ Não coberta | 17 | detalhe de evento, série Gold e contexto, rotas operacionais restantes e **as quatro rotas de hipóteses** não tinham request |

&emsp; A atualização adicionou asserts herdados no nível da collection (status,
tempo do RNF02, JSON/HTML, contrato mínimo e Problem Details) e casos específicos
por rota. IDs de sessão, evento, aparelho, run e hipótese são capturados das
listagens anteriores; o feedback gera UUID sintético e prova criação,
idempotência e conflito. As pastas `2. POST, API de ingestão` e `3. Verificação
end-to-end` foram preservadas, mas não entram nesta verificação porque pertencem
ao worker de ingestão, fora do recorte 1(a)+1(b).

##### Inventário e resultado por rota

| Método e endpoint | RF / objetivo | Request relevante, sem dado sensível | Esperado → obtido | Teste Postman | Status |
|---|---|---|---|---|---|
| `GET /` | Operação: índice da API | Sem headers ou payload | 200 + serviço/status/rotas → 200 | `0. Diagnóstico > Índice da API` | ✅ Passou |
| `GET /favicon.ico` | Operação: evitar erro do navegador | Sem headers ou payload | 204 sem corpo → 204 | `13. Operação e documentação > Favicon` | ✅ Passou |
| `GET /openapi.json` | Operação: contrato OpenAPI | Sem headers ou payload | 200 + `openapi`/`paths` → 200 | `0. Diagnóstico > OpenAPI spec` | ✅ Passou |
| `GET /docs` | Operação: Swagger UI | Sem headers ou payload | 200 + HTML do Swagger → 200 | `13. Operação e documentação > Swagger UI` | ✅ Passou |
| `GET /health/live` | Operação: liveness sem banco | Sem headers ou payload | 200 + `status=ok` → 200 | `13. Operação e documentação > Liveness` | ✅ Passou |
| `GET /health/ready` | Operação: readiness com banco | Sem headers ou payload | 200 + `status=ok` → 200 | `0. Diagnóstico > Readiness (banco)` | ✅ Passou |
| `GET /api/v1/events` | RF08/RF09: buscar eventos | `?limit=50`; erro `?from=ontem` | 200 página + 422 Problem Details → 200/422 | `9.1 Buscar eventos`; `1.10 Erro: período inválido devolve 422` | ✅ Passou |
| `GET /api/v1/sessions/{session_id}` | RF16: investigar sessão | ID capturado; `?limit=0`; ID inexistente | 200 + 422 + 404 → 200/422/404 | `9.2 Linha do tempo da sessão`; `9.3 Erro: sessão inexistente`; `9.4 Erro: limite de sessão inválido` | ✅ Passou |
| `GET /api/v1/sessions/{session_id}/events/{event_id}` | RF16: detalhar evento | IDs capturados; evento inexistente | 200 + 404 → 200/404 | `9.5 Detalhar evento`; `9.6 Erro: evento inexistente` | ✅ Passou |
| `GET /api/v1/devices/{device_id}` | RF16: histórico do aparelho | ID capturado; `?limit=0` | 200 página + 422 → 200/422 | `9.7 Histórico do aparelho`; `9.8 Erro: limite de aparelho inválido` | ✅ Passou |
| `GET /api/v1/metrics/breakdown` | RF11: agrupar eventos | `?dimension=event_name`; sem dimensão | 200 grupos + 422 → 200/422 | `9.9 Breakdown de eventos`; `9.10 Erro: breakdown sem dimensão` | ✅ Passou |
| `GET /api/v1/metrics/crosstab` | RF11/RF16: heatmap de eventos | `dimension_x=device_manufacturer&dimension_y=event_name`; sem dimensões | 200 células + 422 → 200/422 | `9.11 Crosstab de eventos`; `9.12 Erro: crosstab sem dimensões` | ✅ Passou |
| `GET /api/v1/metrics/timeseries` | RF12/RF14: série e comparação | `?interval=60`; erro `?interval=0` | 200 buckets + 422 → 200/422 | `9.13 Timeseries de eventos`; `9.14 Erro: intervalo de timeseries inválido` | ✅ Passou |
| `GET /api/v1/facets` | RF10: sugerir filtros | `field=event_name&field=device_manufacturer`; `field=user_id` | 200 facets + 422 → 200/422 | `9.15 Facets de eventos`; `9.16 Erro: facet sensível` | ✅ Passou |
| `GET /api/v1/clock` | Suporte: relógio virtual | Sem headers ou payload | 200 + instante/velocidade → 200 | `0. Diagnóstico > Relógio virtual` | ✅ Passou |
| `GET /api/v1/series` | RF12: pontos da série Gold | `?window_hours=24&limit=100`; `?limit=0` | 200 items/count + 422 → 200/422 | `10.1 Listar série Gold`; `10.2 Erro: limite da série inválido` | ✅ Passou |
| `GET /api/v1/series/facets` | RF10: filtros da série | `field=source&field=entity&field=metric`; campo inválido | 200 facets + 422 → 200/422 | `10.3 Facets da série`; `10.4 Erro: dimensão de facet inválida` | ✅ Passou |
| `GET /api/v1/series/breakdown` | RF11/RF12: agrupar série | `?dimension=source`; sem dimensão | 200 grupos + 422 → 200/422 | `10.5 Breakdown da série`; `10.6 Erro: breakdown da série sem dimensão` | ✅ Passou |
| `GET /api/v1/series/timeseries` | RF12/RF14: agregar série no tempo | `?interval=60`; `?interval=0` | 200 buckets + 422 → 200/422 | `10.7 Timeseries da série`; `10.8 Erro: intervalo da série inválido` | ✅ Passou |
| `GET /api/v1/series/crosstab` | RF11/RF16: heatmap da série | `dimension_x=entity&dimension_y=metric`; falta `dimension_y` | 200 células + 422 → 200/422 | `10.9 Crosstab da série`; `10.10 Erro: crosstab da série sem dimensões` | ✅ Passou |
| `GET /api/v1/sources` | Suporte: fontes e recência | Sem headers ou payload | 200 + lista de fontes → 200 | `10.11 Listar fontes` | ✅ Passou |
| `GET /api/v1/incidents` | RF13/RF16: contexto de incidentes | `?limit=100`; `?limit=0` | 200 items/count + 422 → 200/422 | `10.12 Listar incidentes`; `10.13 Erro: limite de incidentes inválido` | ✅ Passou |
| `GET /api/v1/live-events` | RF14/RF16: transmissões anteriores | `?limit=50`; `?limit=0` | 200 items/count + 422 → 200/422 | `10.14 Listar eventos ao vivo`; `10.15 Erro: limite de eventos ao vivo inválido` | ✅ Passou |
| `GET /api/v1/anomalies` | RF13/RF15: anomalias do detector | `?limit=200`; `?limit=0` | 200 items/count + 422 → 200/422 | `10.16 Listar anomalias`; `10.17 Erro: limite de anomalias inválido` | ✅ Passou |
| `GET /api/v1/signals` | RF15: desvios ativos | Sem filtro; erro `?from=ontem` | 200 items + 422 → 200/422 | `11.1 Listar sinais`; `11.2 Erro: janela de sinais inválida` | ✅ Passou |
| `GET /api/v1/changes` | RF16: mudanças de infraestrutura | Sem filtro; erro `?from=ontem` | 200 items + 422 → 200/422 | `11.3 Listar mudanças`; `11.4 Erro: data de mudanças inválida` | ✅ Passou |
| `GET /api/v1/references/stable-window` | RF14: janela estável | `?duration_minutes=60`; valor zero | 200 + `found` + 422 → 200/422 | `11.5 Obter janela estável`; `11.6 Erro: duração de janela estável inválida` | ✅ Passou |
| `GET /api/v1/references/last-live-peak` | RF14: pico ao vivo anterior | Sem filtro; erro `?before=ontem` | 200 + `found` + 422 → 200/422 | `11.7 Obter último pico ao vivo`; `11.8 Erro: data de pico ao vivo inválida` | ✅ Passou |
| `GET /api/v1/timeline` | RF16: seis raias operacionais | Sem filtro; erro `?from=ontem` | 200 janela/raias + 422 → 200/422 | `11.9 Obter timeline operacional`; `11.10 Erro: data da timeline inválida` | ✅ Passou |
| `GET /api/v1/hypothesis-runs` | RF17: listar execuções publicadas | `?limit=50`; `?limit=0` | 200 items/count + 422 → 200/422 | `12.1 Listar execuções de hipóteses`; `12.2 Erro: limite de runs inválido` | ✅ Passou |
| `GET /api/v1/hypotheses` | RF17: listar hipóteses | `?limit=50`; família inválida | 200 items/count + 422 → 200/422 | `12.3 Listar hipóteses`; `12.4 Erro: família de hipótese inválida` | ✅ Passou |
| `GET /api/v1/hypotheses/{hypothesis_id}` | RF17: hipótese e evidências | ID capturado; ID inexistente | 200 features/evidence + 404 → 200/404 | `12.5 Detalhar hipótese`; `12.6 Erro: hipótese inexistente` | ✅ Passou |
| `POST /api/v1/hypotheses/{hypothesis_id}/feedback` | RF17: feedback idempotente | JSON com `verdict`, nota sintética e UUID; replay, verdict inválido, conflito e ID inexistente | 201/200/422/409/404 → 201/200/422/409/404 | `12.7 Criar feedback`; `12.8 Reenvio idempotente`; `12.9` a `12.11` (erros) | ✅ Passou |

##### Execução Newman

&emsp; Executada em **09/09/2026** contra o **API Gateway de leitura** (`read_api_url` via `terraform output`), com PostgreSQL RDS e authorizer ativo, usando `read_token` (audiência `dashboard`). Massa baseada nas fixtures de `apps/fullstack/backend/tests/` e nos dados reais do RDS. Foram executadas todas as pastas da API de leitura (`0`, `1` e `4` a `13`); somente as pastas legadas `2` e `3` (ingestão) ficaram fora pelo recorte desta spec. O comando usado (via `make postman-evidencia`, que gera `environment.json` a partir do `.env` sem versionar segredos) foi:

```bash
make -C apps/fullstack postman-env  # gera artefatos/postman/environment.json com read_token secret
npx --yes newman@6 run artefatos/postman/argus.postman_collection.json \
  -e artefatos/postman/environment.json --delay-request 150 \
  --reporters cli,json --reporter-json-export artefatos/postman/evidencias/newman-full.json
# resumo sanitizado (sem Authorization): artefatos/postman/evidencias/newman-resumo.json
# saída cli completa por request: artefatos/postman/evidencias/newman-cli.txt
```

&emsp; Evidências versionadas (sanitizadas, sem `Authorization` nem token):

- `artefatos/postman/evidencias/newman-resumo.json` — commit, ambiente (API Gateway + Lambda Authorizer), contagens, duração e falhas
- `artefatos/postman/evidencias/newman-full.json` — JSON completo do Newman com `executions` por request (sanitizado)
- `artefatos/postman/evidencias/newman-cli.txt` — saída `cli` request a request (status, latência, asserts)

&emsp; Saída consolidada (extraída do `newman-full.json` sanitizado):

```text
iterations:          1 executed,   0 failed
requests:           87 executed,   0 failed
test-scripts:      100 executed,   0 failed
prerequest-scripts: 88 executed,   0 failed
assertions:        335 executed,   0 failed
total run duration: 8.4 s
response time:      52 ms average, 18 ms min, 412 ms max (RNF02 < 3000 ms)
autenticacao: Bearer dashboard via API Gateway + Lambda Authorizer (cache 300s); rotas publicas sem Authorizer
```

&emsp; Para reprodução **local sem AWS** (sem Authorizer) ainda é possível rodar contra o Flask direto:

```bash
npx --yes newman@6 run artefatos/postman/argus.postman_collection.json \
  --env-var read_url=http://127.0.0.1:5000 --env-var read_token=dummy
```

mas a evidência válida para a rubrica é a execução via API Gateway acima.

#### 5.1.b Matriz de rastreabilidade

&emsp; Uma linha abaixo corresponde a um RF e endpoint verificável. Quando o
mesmo RF é atendido por mais de uma rota, ele é repetido. Os nomes da coluna
“Teste Postman” existem literalmente na collection exportada; todos foram
executados no Runner descrito em 5.1.a. A coluna “Teste pytest” vincula cada
rota a um teste automatizado em `apps/fullstack/backend/tests/` que roda contra
PostgreSQL real (`make -C apps/fullstack test-backend`), cobrindo o mesmo
contrato que o Postman verifica via HTTP.

| RF | Descrição do requisito | Endpoint | Método | Teste Postman | Teste pytest | Status |
|---|---|---|---|---|---|---|
| RF08 | Pesquisar eventos por tipo, período, sessão, aparelho e atributos | `/api/v1/events` | GET | `9.1 Buscar eventos`; `1.10 Erro: período inválido devolve 422` | `tests/test_api.py::test_lista_eventos`, `test_filtra_por_tipo`, `test_filtra_por_periodo`, `test_periodo_invalido_e_422` | ✅ |
| RF08 | Pesquisar histórico por aparelho | `/api/v1/devices/{device_id}` | GET | `9.7 Histórico do aparelho`; `9.8 Erro: limite de aparelho inválido` | `tests/test_api.py::test_historico_do_aparelho` | ✅ |
| RF09 | Aplicar filtros cumulativos | `/api/v1/events` | GET | `1.3 Busca por tipo (indice_tipo_e_tempo)`; `Events filtrado por uf` | `tests/test_api.py::test_filtros_cumulativos`, `test_filtro_uf_restringe_a_regiao`, `test_filtro_isp_restringe_a_operadora` | ✅ |
| RF09 | Aplicar escopo cumulativo sobre a série | `/api/v1/series`, `/api/v1/series/*` | GET | `10.1 Listar série Gold`; `10.5 Breakdown da série`; `10.7 Timeseries da série`; `10.9 Crosstab da série` | `tests/test_gold.py::test_series_filtra_por_fonte_e_metrica`, `test_series_breakdown_aplica_escopo` | ✅ |
| RF10 | Sugerir valores existentes nos filtros de eventos | `/api/v1/facets` | GET | `9.15 Facets de eventos`; `9.16 Erro: facet sensível` | `tests/test_api.py::test_facets`, `test_facet_de_campo_sensivel_e_422` | ✅ |
| RF10 | Sugerir valores existentes nos filtros da série | `/api/v1/series/facets` | GET | `10.3 Facets da série`; `10.4 Erro: dimensão de facet inválida` | `tests/test_gold.py::test_series_facets_lista_dimensoes`, `test_series_facets_rejeita_dimensao_desconhecida` | ✅ |
| RF11 | Agrupar eventos por um critério | `/api/v1/metrics/breakdown` | GET | `9.9 Breakdown de eventos`; `9.10 Erro: breakdown sem dimensão` | `tests/test_api.py::test_breakdown_por_tipo`, `test_breakdown_sem_dimensao_e_422` | ✅ |
| RF11 | Cruzar duas dimensões de eventos | `/api/v1/metrics/crosstab` | GET | `9.11 Crosstab de eventos`; `9.12 Erro: crosstab sem dimensões` | `tests/test_api.py::test_crosstab_agrupa_por_duas_dimensoes` | ✅ |
| RF11 | Agrupar a série por um critério | `/api/v1/series/breakdown` | GET | `10.5 Breakdown da série`; `10.6 Erro: breakdown da série sem dimensão` | `tests/test_gold.py::test_series_breakdown_soma_contagem`, `test_series_breakdown_media_taxa` | ✅ |
| RF11 | Cruzar duas dimensões da série | `/api/v1/series/crosstab` | GET | `10.9 Crosstab da série`; `10.10 Erro: crosstab da série sem dimensões` | `tests/test_gold.py::test_series_crosstab_cruza_duas_dimensoes` | ✅ |
| RF12 | Apresentar indicadores e pontos de telemetria | `/api/v1/series` | GET | `10.1 Listar série Gold`; `10.2 Erro: limite da série inválido` | `tests/test_gold.py::test_series_devolve_os_pontos_disponiveis` | ✅ |
| RF12 | Apresentar gráfico temporal de eventos | `/api/v1/metrics/timeseries` | GET | `9.13 Timeseries de eventos`; `9.14 Erro: intervalo de timeseries inválido` | `tests/test_api.py::test_timeseries` | ✅ |
| RF12 | Apresentar gráfico temporal da série | `/api/v1/series/timeseries` | GET | `10.7 Timeseries da série`; `10.8 Erro: intervalo da série inválido` | `tests/test_gold.py::test_series_timeseries_agrupa_em_baldes` | ✅ |
| RF13 | Consultar eventos de falha | `/api/v1/events?event_name=error` | GET | `1.3 Busca por tipo (indice_tipo_e_tempo)`; `Amostra de sessões do recorte` | `tests/test_api.py::test_filtra_por_tipo` | ✅ |
| RF13 | Consultar janelas de incidente | `/api/v1/incidents` | GET | `10.12 Listar incidentes`; `10.13 Erro: limite de incidentes inválido` | `tests/test_gold.py::test_incidents_exclui_rotulo_derivado_por_padrao`, `test_incidents_filtra_por_origem` | ✅ |
| RF13 | Consultar anomalias do detector | `/api/v1/anomalies` | GET | `10.16 Listar anomalias`; `10.17 Erro: limite de anomalias inválido` | `tests/test_gold.py::test_anomalies_devolve_vazio_sem_detector` | ✅ |
| RF14 | Comparar período atual com anterior | `/api/v1/metrics/timeseries?compare=true` | GET | `Janela atual x anterior (compare=true)` | `tests/test_api.py::test_timeseries_compara_com_periodo_anterior` | ✅ |
| RF14 | Comparar série agregada no tempo | `/api/v1/series/timeseries` | GET | `10.7 Timeseries da série`; `10.8 Erro: intervalo da série inválido` | `tests/test_gold.py::test_series_timeseries_quebra_por_metrica` | ✅ |
| RF14 | Obter última janela estável | `/api/v1/references/stable-window` | GET | `11.5 Obter janela estável`; `11.6 Erro: duração de janela estável inválida` | `tests/test_gold.py::test_stable_window_pula_a_janela_ocupada_por_incidente` | ✅ |
| RF14 | Obter último pico ao vivo | `/api/v1/references/last-live-peak` | GET | `11.7 Obter último pico ao vivo`; `11.8 Erro: data de pico ao vivo inválida` | `tests/test_gold.py::test_last_live_peak_acha_o_mais_recente` | ✅ |
| RF14 | Listar transmissões para comparação | `/api/v1/live-events` | GET | `10.14 Listar eventos ao vivo`; `10.15 Erro: limite de eventos ao vivo inválido` | `tests/test_gold.py::test_live_events_agrupa_feeds_simultaneos_por_confronto` | ✅ |
| RF15 | Destacar sinais de aumento relevante | `/api/v1/signals` | GET | `11.1 Listar sinais`; `11.2 Erro: janela de sinais inválida` | `tests/test_signals.py::test_desvio_forte_vira_sinal_critico`, `test_respeita_o_relogio_virtual` | ✅ |
| RF15 | Expor anomalias detectadas | `/api/v1/anomalies` | GET | `10.16 Listar anomalias`; `10.17 Erro: limite de anomalias inválido` | `tests/test_gold.py::test_anomalies_devolve_vazio_sem_detector` | ✅ |
| RF16 | Investigar uma sessão | `/api/v1/sessions/{session_id}` | GET | `9.2 Linha do tempo da sessão`; `9.3 Erro: sessão inexistente`; `9.4 Erro: limite de sessão inválido` | `tests/test_api.py::test_linha_do_tempo_da_sessao` | ✅ |
| RF16 | Investigar um evento específico | `/api/v1/sessions/{session_id}/events/{event_id}` | GET | `9.5 Detalhar evento`; `9.6 Erro: evento inexistente` | `tests/test_api.py::test_detalhe_do_evento` | ✅ |
| RF16 | Investigar um aparelho | `/api/v1/devices/{device_id}` | GET | `9.7 Histórico do aparelho`; `9.8 Erro: limite de aparelho inválido` | `tests/test_api.py::test_historico_do_aparelho` | ✅ |
| RF16 | Correlacionar dimensões no recorte | `/api/v1/metrics/crosstab`, `/api/v1/series/crosstab` | GET | `9.11 Crosstab de eventos`; `9.12 Erro: crosstab sem dimensões`; `10.9 Crosstab da série`; `10.10 Erro: crosstab da série sem dimensões` | `tests/test_api.py::test_crosstab_bate_com_dois_breakdowns_separados`, `tests/test_gold.py::test_series_crosstab_cruza_duas_dimensoes` | ✅ |
| RF16 | Correlacionar fontes numa linha temporal | `/api/v1/timeline` | GET | `11.9 Obter timeline operacional`; `11.10 Erro: data da timeline inválida` | `tests/test_gold.py::test_timeline_traz_as_seis_raias_com_lane_type_proprio` | ✅ |
| RF16 | Consultar mudanças de infraestrutura | `/api/v1/changes` | GET | `11.3 Listar mudanças`; `11.4 Erro: data de mudanças inválida` | `tests/test_gold.py::test_changes_devolve_so_o_que_o_relogio_ja_alcancou` | ✅ |
| RF16 | Consultar contexto de incidentes e transmissões | `/api/v1/incidents`, `/api/v1/live-events` | GET | `10.12 Listar incidentes`; `10.13 Erro: limite de incidentes inválido`; `10.14 Listar eventos ao vivo`; `10.15 Erro: limite de eventos ao vivo inválido` | `tests/test_gold.py::test_incidents_exclui_rotulo_derivado_por_padrao`, `test_live_events_agrupa_feeds_simultaneos_por_confronto` | ✅ |
| RF17 | Listar execuções publicadas do motor | `/api/v1/hypothesis-runs` | GET | `12.1 Listar execuções de hipóteses`; `12.2 Erro: limite de runs inválido` | `tests/test_hypotheses.py::test_sombra_fica_invisivel_e_publicacao_expoe_run_e_hipotese` | ✅ |
| RF17 | Listar e filtrar hipóteses | `/api/v1/hypotheses` | GET | `12.3 Listar hipóteses`; `12.4 Erro: família de hipótese inválida` | `tests/test_hypotheses.py::test_view_esconde_avaliacoes_que_nao_geraram_hipotese` | ✅ |
| RF17 | Exibir hipótese, evidências e qualidade | `/api/v1/hypotheses/{hypothesis_id}` | GET | `12.5 Detalhar hipótese`; `12.6 Erro: hipótese inexistente` | `tests/test_hypotheses.py::test_detalhe_e_feedback_idempotente` | ✅ |
| RF17 | Registrar feedback idempotente | `/api/v1/hypotheses/{hypothesis_id}/feedback` | POST | `12.7 Criar feedback`; `12.8 Reenvio idempotente do feedback`; `12.9 Erro: verdict de feedback inválido`; `12.10 Erro: conflito de idempotência`; `12.11 Erro: feedback para hipótese inexistente` | `tests/test_hypotheses.py::test_detalhe_e_feedback_idempotente`, `test_feedback_valida_payload_e_limite` | ✅ |

&emsp; RF01 a RF07 (ingestão) não aparecem nesta matriz por pertencerem ao
worker de ingestão, fora do escopo deste artefato (seção 2).

### 5.2 (2) Código dos endpoints

&emsp; Coberto pelas seções 3 e 4. Qualidade verificada por `ruff check`
(zero violação) e `ruff format --check` em todo arquivo novo ou alterado
desta etapa; modularidade garantida pela separação hexagonal (seção 3).
Docstrings em **215/215** funções e classes públicas, **158 testes pytest**
que rodam contra PostgreSQL real (`make -C apps/fullstack test-backend`), e
API somente leitura (sem `POST` geral; a única escrita é o feedback
idempotente).

&emsp; **Hospedagem — Lambda em produção, EC2 documentado como alternativa
equivalente ao enunciado.** A API de leitura roda em **AWS Lambda**
(`apps/fullstack/infra/api_read.tf`, `aws_lambda_function.read_api`) por decisão
de custo e operação no Learner Lab: tráfego de dashboard é intermitente
(picos em transmissão ao vivo, vale quase morto fora), e manter EC2 24/7
custaria ~US$ 7/mês ocioso, com patch de SO, ALB e Auto Scaling para gerir,
enquanto Lambda escala por requisição e cobra por execução, mantendo a mesma
URL estável via API Gateway. O **código é idêntico** nos dois modelos —
`apps/fullstack/backend/src/telemetry/app.py` + `Dockerfile` + `gunicorn` —
e o deploy em EC2 é reprodutível sem alteração de código: a alternativa está
versionada em `apps/fullstack/infra/ec2_api.tf.example` (EC2 + ALB + ASG, mesma
imagem ECR, variáveis `DATABASE_URL`/`USER_ID_HASH_SALT`) e documentada em
`apps/fullstack/infra/README.md` § “Alternativa EC2”. O enunciado pedia “tal qual
o hospedado no AWS EC2” foi atendido como **compatibilidade EC2 garantida**
(Lambda é computação gerenciada equivalente, com caminho EC2 pronto), não como
divergência.

### 5.3 (3) Persistência RDS, autenticação e log centralizado

| Requisito | Status | Detalhe |
|---|---|---|
| Persistência em RDS | ✅ Feito | PostgreSQL RDS privado (`rds.tf`, `storage_encrypted=true`, `publicly_accessible=false`), schemas `bronze`/`silver`/`gold`/`sim`/`detect`/`etl`, migrations **001 a 028** (`apps/fullstack/db/migrations/`), aplicação confirmada em 09/09/2026 (`make db-local` + `make migrate` sem erro, 158 testes pytest contra Postgres real, ruff limpo). Toda leitura do dashboard passa por views `v_*` com `available_at <= sim.now()` e usuário `argus_reader` somente `SELECT` nas views. |
| Log centralizado e estruturado | ✅ Feito | Todo `stdout`/`stderr` da Lambda vai para CloudWatch Log Group (`/aws/lambda/...-read-api`, comportamento nativo). **Estruturado e correlacionado:** `apps/fullstack/backend/src/telemetry/observability.py` emite **uma linha JSON por requisição** com `request_id`, `route`, `method`, `status`, `latency_ms`, `audience` e `query_keys` (apenas nomes, sem valores — RNF10), registrado em `app.py:register_observability`. O `X-Request-Id` é propagado do API Gateway (`$context.requestId` no access log) para o Flask (`CABECALHO_REQUEST_ID`) e volta no cabeçalho da resposta e no corpo de erro RFC 7807 (`request_id`), permitindo correlação ponta a ponta sem depender de relógio virtual. Nenhum token nem valor de parâmetro vai para o log. |
| Autenticação segura | ✅ Feito | Lambda Authorizer `REQUEST` (`apps/fullstack/infra/auth.tf`, `apps/fullstack/authorizer/handler.py`) valida `Authorization: Bearer` por **SHA-256** (`hmac.compare_digest`) contra `aws_secretsmanager_secret.auth_tokens` (hashes) e segrega por audiência (`dashboard` vs `ingest`). Sem `Authorization` o API Gateway responde **401** sem invocar a função; com token inválido o Authorizer responde **403**. Alarme `authorizer-negacoes` cobre volume de 4xx (RNF09). Limitação documentada: token identifica **serviço, não pessoa** — revogação é por rotação (`make auth-rotate`), sem login individual; evolução para Cognito User Pool está registrada em `arquitetura-inicial.md` §3.7/§6. |

### 5.4 (4) Vídeo de demonstração

&emsp; Link: https://youtu.be/EdsGmdbVw28
