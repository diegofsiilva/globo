# Back-end

&emsp; Este artefato descreve a estrutura e a implementação do back-end da
plataforma de Monitoração Agêntica: organização do código, segurança,
autenticação, testes de endpoints e integração com o front-end, conforme a
especificação do módulo. Atualizado em 27/08/2026 após o merge de
`feat/rotas-backend` em `develop`: as rotas descritas aqui já estão na
`develop`, junto com o motor de hipóteses e o novo design do front, feitos
por outros integrantes do time. A seção 6 lista o que falta para atender a
rubrica por completo; hoje só o vídeo de demonstração está pendente.

&emsp; Divergência de nomenclatura entre a especificação e o repositório:
a especificação referencia a pasta de código-fonte como `/apps/backend`; no
repositório o caminho real é [`apps/basica/backend`](../apps/basica/backend)
(a API de leitura) e [`apps/basica/worker`](../apps/basica/worker) (a
ingestão), já que `basica` é o nome do produto dentro do monorepo, decisão
anterior a este artefato. Referências neste documento usam o caminho real.

## 1. Objetivo

&emsp; Apresentar a API de leitura (`apps/basica/backend`) que serve o
dashboard: como o código está organizado, quais endpoints existem, como cada
um foi testado, e o estado atual de persistência, autenticação e log,
incluindo o que está pendente.

## 2. Escopo coberto por este artefato

&emsp; Este artefato cobre a **API de leitura**, responsável pelos endpoints
que o dashboard consome. A **ingestão** (API Gateway → SQS → worker →
banco) é um serviço separado, com ciclo de vida e testes próprios em
`apps/basica/worker`, e não é o foco aqui; é citada apenas onde necessário
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

## 3. Organização do código

&emsp; `apps/basica/backend/src/telemetry/` segue arquitetura hexagonal, em
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
(`apps/basica/worker`), o que elimina duas superfícies de validação
divergentes; ver `interfaces/http.py`, docstring do módulo.

## 5. Itens da especificação

### 5.1 (1) Relatório

#### 5.1.a Testes dos endpoints com Postman

&emsp; Unificadas em uma coleção só:
[`artefatos/postman/argus.postman_collection.json`](postman/argus.postman_collection.json)
(environment em
[`artefatos/postman/environment.example.json`](postman/environment.example.json)).
Não foi um merge mecânico: a pasta de leitura (herdada da coleção de
14/08/2026) tinha asserções escritas contra o **DynamoDB v2**
(`query.strategy` esperando `table:scan`, `gsi1:fanout`, `table:session`,
`gsi2:device`, e um teste que exigia fan-out de mais de uma query). Nenhum
desses nomes existe no back-end Postgres atual, então foram corrigidos para
os nomes reais (`particao_por_tempo`, `indice_tipo_e_tempo`, `indice_sessao`,
`indice_aparelho`, `queries === 1`), conferidos contra
`postgres.py::_estrategia`. A pasta **2. POST, API de ingestão** (legada)
**não foi revisada nesta rodada**, pois pertence a `apps/basica/worker`,
fora do escopo investigado aqui; ficou um aviso dentro da própria pasta na
coleção.

&emsp; Pastas da coleção final: `0. Diagnóstico`, `1. Leitura, eventos e
métricas` (corrigida), `2. POST, API de ingestão` (legada, não executada
nesta rodada, ver nota abaixo), `3. Verificação end-to-end` (legada, idem),
`4. Agora`, `5. Comparar`, `6. Timeline`, `7. Recorte`, `8. Filtros de
região/operadora`.

&emsp; **Executada em 27/08/2026** contra um PostgreSQL 16 local (`make
db-local`, migrations 001 a 023 aplicadas sem erro) com um servidor Flask
de desenvolvimento real (`flask.run`, não um duble) e uma massa mínima de
dado inserida à mão em `gold.feature_bucket`, `gold.deploy_event`,
`gold.incident_window` e `silver.session_event`, via `newman` (CLI oficial
do Postman). Resultado das pastas `0`, `1`, `4` a `8` (30 requisições, as
que este artefato cobre):

```
requests: 30, failed: 0
assertions: 37, failed: 0
total run duration: 741ms
```

&emsp; As pastas `2` e `3` (ingestão, legadas) não foram executadas nesta
rodada, pois dependem de um endpoint de ingestão que não faz parte do escopo
investigado aqui (ver seção 2); continuam com o aviso registrado na própria
coleção.

&emsp; Além do Postman, a suíte automatizada (`pytest`,
`apps/basica/backend/tests/`) também rodou contra o mesmo banco:

```
126 passed in 97.46s
```

&emsp; Rodar de verdade (e não só revisar por leitura) encontrou 3 bugs
reais nos testes que nenhuma leitura de código tinha pego: URLs montadas
com `f"...{data.isoformat()}"` sem escapar o `+` do fuso horário (vira
espaço na query string, quebra o parse ISO 8601 no servidor e devolve 422
em vez de 200, 12 ocorrências, em `test_signals.py` e `test_gold.py`) e
um `conn.executemany(...)` que não existe na `Connection` do psycopg3 (só
em `Cursor`). Os três foram corrigidos; ver o commit `fix: corrige bugs
reais achados rodando a suite contra Postgres de verdade`.

#### 5.1.b Matriz de rastreabilidade

&emsp; Requisitos funcionais pertinentes à API de leitura, endpoint que
atende cada um e teste automatizado correspondente. Todas as linhas desta
frente (RF08–RF16) foram confirmadas rodando de verdade: suíte `pytest`
(126 testes) e coleção Postman (30 requisições, 37 asserções), ambas contra
PostgreSQL 16 real, em 27/08/2026 (seção 5.1.a).

| RF | Descrição resumida | Endpoint(s) | Teste automatizado |
|---|---|---|---|
| RF08 | Pesquisa por tipo, período e demais atributos | `GET /events` | `test_api.py::test_lista_eventos` e correlatos |
| RF09 | Filtros cumulativos numa mesma consulta | `EventFilters` (todas as rotas de busca) | `test_api.py::test_filtro_uf_e_isp_sao_cumulativos_com_os_demais` |
| RF10 | Sugestão de valores existentes nos filtros | `GET /facets` | `test_api.py::test_facets`, `test_repository.py::test_facets_lista_valores_existentes` |
| RF11 | Agrupamento por critério, incluindo região | `GET /metrics/breakdown`, `GET /metrics/crosstab` | `test_api.py::test_breakdown_por_uf_ja_aceitava_a_dimensao_antes_do_fix`, `test_crosstab_bate_com_dois_breakdowns_separados` |
| RF12 | Gráficos e indicadores a partir dos eventos | `GET /metrics/timeseries`, `GET /series` | `test_api.py::test_timeseries`, `test_gold.py::test_series_devolve_os_pontos_disponiveis` |
| RF13 | Consultas simples para falhas críticas | `GET /events?event_name=error`, `GET /anomalies` | `test_gold.py::test_anomalies_devolve_vazio_sem_detector` (cobertura parcial, a rota responde e é testada, mas o detector que a alimenta é responsabilidade de outra frente, ver `processing/`) |
| RF14 | Comparação com período anterior | `GET /metrics/timeseries?compare=true`, `GET /references/*` | `test_gold.py::test_stable_window_*`, `test_last_live_peak_*` |
| RF15 | Destaque de aumentos relevantes (picos) | `GET /signals` | `test_signals.py` (11 testes) |
| RF16 | Informações para investigar um problema | `GET /sessions/{id}`, `GET /devices/{id}`, `GET /timeline`, `GET /changes`, `GET /metrics/crosstab` | `test_gold.py::test_timeline_*`, `test_changes_*`; sessão/dispositivo já cobertos em `test_api.py` |
| RF17 | Causas prováveis (hipóteses) | `GET /hypotheses`, `GET /hypotheses/{id}`, `POST /hypotheses/{id}/feedback`, `GET /hypothesis-runs`, implementadas por outro integrante, já em `develop` | `test_hypotheses.py` (existe na suíte, 8 testes; não é desta frente, não auditado aqui) |

&emsp; RF01 a RF07 (ingestão) não aparecem nesta matriz por pertencerem ao
worker de ingestão, fora do escopo deste artefato (seção 2).

### 5.2 (2) Código dos endpoints

&emsp; Coberto pelas seções 3 e 4. Qualidade verificada por `ruff check`
(zero violação) e `ruff format --check` em todo arquivo novo ou alterado
desta etapa; modularidade garantida pela separação hexagonal (seção 3).

&emsp; **A API de leitura roda em AWS Lambda, não numa instância EC2**
(confirmado em `apps/basica/infra/`: só existe `aws_lambda_function`, sem
recurso de EC2 no desenho). A escolha é deliberada, não uma pendência: o
tráfego de consulta do dashboard é variável ao longo do dia, com picos
quando há transmissão ao vivo e vale quase morto fora desses horários, e
isso não justifica manter um servidor sempre ligado. Lambda escala
automaticamente com o volume de requisições e cobra por execução, não por
tempo ocioso; o API Gateway já expõe o HTTP na frente da função,
dispensando a camada de sistema operacional, patch e processo sempre no ar
que uma instância EC2 exigiria. É por isso que as APIs deste projeto não
passam por uma máquina EC2: rodam como função gerenciada, sem servidor
dedicado.

### 5.3 (3) Persistência RDS, autenticação e log centralizado

| Requisito | Status | Detalhe |
|---|---|---|
| Persistência em RDS | ✅ Feito | PostgreSQL RDS, schemas `bronze`/`silver`/`gold`/`sim`/`detect`, migrations 001 a 023 (`apps/basica/db/migrations/`), aplicação confirmada rodando de verdade em 27/08/2026 (`make db-local`, sem erro) |
| Log centralizado | ✅ Feito | Todo `stdout`/`stderr` da função Lambda vai automaticamente para um CloudWatch Log Group central (comportamento padrão da plataforma, não precisa de configuração extra), e é isso que torna o log centralizado. Não é log **estruturado** (sem JSON, sem id de correlação por requisição): isso é uma melhoria possível, não um requisito desta rubrica, e fica registrado como ideia futura, não pendência. |
| Autenticação segura | 🔴 **Não implementada** | Nenhuma das duas APIs exige credencial hoje, confirmado no código (`app.py`, `interfaces/`), não é suposição. Não é algo que uma nova checagem resolve: falta decidir o mecanismo (API key via API Gateway é o mais simples de encaixar sem tocar a assinatura das rotas; IAM auth é a alternativa nativa da AWS) e implementar. |

&emsp; **Pendente:** implementar autenticação (ex.: API key via API Gateway,
ou IAM auth) nas duas APIs, único item de código ainda em aberto
desta frente. Se quiser, posso implementar uma versão simples (API key)
agora; é uma decisão de arquitetura, por isso não fiz de passagem.

### 5.4 (4) Vídeo de demonstração

&emsp; **Pendente.** Vídeo de 2 a 3 minutos demonstrando a execução dos
testes (Postman e/ou pytest) e a persistência em banco de dados. Link a
preencher aqui após gravação:

&emsp; Link: *(pendente)*

## 6. Pendências consolidadas

&emsp; Atualizado em 27/08/2026: com o merge de `feat/rotas-backend` em
`develop` e a suíte/coleção rodadas de verdade contra Postgres real (seção
5.1), restam dois itens:

1. Decidir e, se aprovado, implementar autenticação nas duas APIs (seção
   5.3), único item de código ainda em aberto.
2. Gravar o vídeo de demonstração e linkar aqui (seção 5.4).

## 7. Documentos relacionados

&emsp; Referências internas ao repositório (não são fonte externa, por isso
fora do padrão ABNT de referências):

- [`artefatos/plano-argus-v3.md`](plano-argus-v3.md): arquitetura de dado
  em vigor (schemas bronze/silver/gold, decisão Lambda).
- [`artefatos/requisitos.md`](requisitos.md): lista completa de RF/RNF.
- `apps/basica/backend/src/telemetry/interfaces/openapi.py`: especificação
  OpenAPI 3.1 gerada a partir do mesmo código que valida a API, servida em
  `/openapi.json` e `/docs`.
