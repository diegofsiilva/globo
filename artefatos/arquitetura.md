# Arquitetura da plataforma de telemetria

Plataforma que recebe os eventos emitidos pelo app de TV, armazena em escala e
os devolve ao dashboard para investigação de incidentes.

São dois fluxos independentes ligados por um banco em comum:

- **Ingestão** — aceita o evento na borda, enfileira, valida de forma assíncrona
  e grava.
- **Leitura** — consulta o que foi gravado, agrega e serve o dashboard.

**Status:** ambos aplicados e validados ponta a ponta em AWS Academy Learner
Lab. Endpoints e identificadores de conta ficam no `.env` local, nunca no
repositório (ver §9.4).

---

## 1. Visão geral

```
   App de TV (7 plataformas, centenas de modelos)
        │
        │  POST /v1/events
        ▼
┌────────────────────┐
│  API Gateway       │  HTTP API, integração direta SQS-SendMessage
│  (ingestão)        │  sem Lambda no caminho
└─────────┬──────────┘
          ▼
┌────────────────────┐      ┌────────────────────┐
│  SQS               │─────▶│  SQS DLQ           │
│  argus-events      │ 5 t. │  investigação      │
└─────────┬──────────┘      └────────────────────┘
          │  long polling (20s)          ▲
          ▼                              │ payload inválido
┌────────────────────┐                   │ (direto, sem gastar
│  ECS Fargate       │───────────────────┘  as tentativas)
│  worker (Python)   │
└─────────┬──────────┘
          │  BatchWriteItem (25/chamada)
          ▼
┌────────────────────────────────────────────────┐
│  DynamoDB — tabela única                       │
│  tabela: sessão · GSI1: tipo+dia · GSI2: device│
└─────────┬──────────────────────────────────────┘
          │  Query / Scan
          ▼
┌────────────────────┐
│  AWS Lambda        │  Flask (apig-wsgi)
│  API de leitura    │  roteamento de índice, agregação, redação
└─────────┬──────────┘
          ▼
┌────────────────────┐
│  API Gateway       │  HTTP API separado do de ingestão
│  (leitura)         │
└─────────┬──────────┘
          ▼
┌────────────────────┐
│  Dashboard         │  Next.js estático (output: export)
└────────────────────┘
```

| Etapa | Papel | Por que assim |
|---|---|---|
| API Gateway (ingestão) | aceita e enfileira | responde rápido; a TV não espera a gravação |
| SQS | absorve pico e garante entrega | pico de audiência não derruba a ingestão |
| Fargate | valida e grava | processo longo com polling contínuo |
| DynamoDB | armazena | escrita barata, schemaless, TTL nativo |
| Lambda | consulta e agrega | uso intermitente; container ocioso seria desperdício |
| API Gateway (leitura) | expõe ao dashboard | HTTPS e URL estável de graça |

**Por que dois API Gateways.** São serviços com exigências opostas: um recebe
evento de TV em volume alto e não pode recusar nada; o outro serve consulta
para uma tela interna e vai precisar de autenticação. Separar deixa throttling,
CORS e authorizer independentes, e HTTP API cobra por requisição e não por API
— ter dois não custa a mais.

---

## 2. Os eventos

Seis tipos, extraídos dos exports do parceiro:

| `event_name` | O que registra | Campos próprios |
|---|---|---|
| `request` | chamada HTTP do app | método, url, status, headers |
| `screen_view` | entrada numa tela | `route_path`, `route_params` |
| `session` | ciclo de vida da sessão | 7 `capabilities_*`, resolução, user agent |
| `video_view` | reprodução de vídeo | `media_id`, `media_kind`, `media_ads`, `media_drm` |
| `vitals` | saúde do player | `action` (ex.: `frozen`), `duration` |
| `error` | erro exibido ao usuário | `error_name`, `error_message`, `error_stack` |

Envelope comum: `timestamp`, `event_name`, `session_id`, `device_id`, `app_*`,
`device_*`, e quase sempre `user_id`, `duration`, `route_path`.

**A lista não é fechada.** O pipeline aceita `event_name` desconhecido e o grava
como evento genérico; a API o devolve normalmente. Um tipo novo no app aparece
no dashboard no mesmo dia, sem alteração de código dos dois lados.

### 2.1 Os timestamps estavam 3 horas deslocados

O export traz `"July 13, 2026 20:04:44"` **sem timezone**. No evento `request`,
o header `date` da própria resposta HTTP diz `23:04:44 GMT` — mesma requisição,
três horas de diferença.

O BI renderiza em `America/Sao_Paulo` e omite o fuso. Tratar como UTC deslocaria
silenciosamente todo dashboard de horário em 3 horas — o tipo de erro que
ninguém percebe até perguntarem por que o pico de audiência é de madrugada.

**Decisão:** `apps/basica/tools/events_csv_to_json.py` assume `America/Sao_Paulo` e
converte para UTC. A API espera ISO-8601; timestamp sem fuso é tratado como UTC.

### 2.2 Formato do payload

Campos em `snake_case` plano, espelhando 1:1 as colunas do export:
`"App Bucket"` → `app_bucket`. `route_params` e headers continuam objetos.

Aninhar (`app: {bucket, env}`) ficaria mais bonito, mas plano mapeia direto para
o vocabulário que o time de dados já usa no BI e simplifica projeção e filtro no
DynamoDB.

Uma correção na fronteira: o export escreve `Capabilities Audio Dobly Atmos`.
É *Dolby*. O typo do fornecedor é corrigido na conversão para não virar nome de
coluna permanente.

---

## 3. Ingestão

### 3.1 HTTP API com integração direta ao SQS, sem Lambda

O subtype `SQS-SendMessage` deixa o próprio API Gateway publicar na fila.

**Ganho:** sem cold start, um ponto de falha a menos, e HTTP API custa
US$ 1,00/milhão contra US$ 3,50 do REST API.

**Custo:** HTTP API **não tem request validator** (só o REST API tem). Não há
validação de schema na borda — o payload entra cru na fila e quem valida é o
worker.

**Por que aceitar:** para telemetria, aceitar rápido e validar assíncrono é
melhor que segurar a TV do usuário esperando validação. O evento inválido não se
perde: vai para a DLQ com o motivo anexado.

Duas consequências confirmadas no ambiente real, que quem consome a API precisa
saber:

- **Payload inválido recebe HTTP 200.** A rejeição é assíncrona. Um cliente que
  mandar lixo recebe sucesso e só descobre olhando a DLQ.
- **A resposta é o XML do SQS**, não JSON. O API Gateway repassa a resposta crua
  do serviço, e HTTP API não transforma corpo — só cabeçalho e status. Cliente
  de telemetria é fire-and-forget e ignora o corpo, mas não dá para prometer
  contrato de resposta JSON sem colocar um Lambda no caminho, ou migrar para
  REST API (que tem mapping template).

### 3.2 SQS Standard, não FIFO

FIFO garantiria ordem e deduplicação, mas limita a ~3.000 msg/s e custa mais.

Não precisamos de nenhuma das duas: a ordem é reconstruída na leitura pela sort
key, e a deduplicação vem da chave derivada do hash do conteúdo (§4.2) — que
inclusive pega duplicata separada por mais de 5 minutos, fora da janela do FIFO.

### 3.3 Validação permissiva, de propósito

Só quatro campos são obrigatórios: `timestamp`, `event_name`, `session_id`,
`device_id`. O resto é opcional, campos desconhecidos são preservados, e
`event_name` novo cai num evento genérico em vez de virar erro.

**Por quê:** o parque de TVs atualiza devagar e de forma desigual. Um modelo
estrito transformaria qualquer mudança de schema no app em perda de dados em
massa — e não dá para fazer hotfix numa TV.

A validação não some, vira observabilidade: campo recomendado ausente
incrementa `EventsIncomplete`, tipo novo incrementa `EventsUnknownType`.

### 3.4 Fargate, não Lambda

Lambda com trigger de SQS seria mais simples e escalaria a zero. Mas o worker se
beneficia de conexão persistente e long polling de 20s, uma task 24/7 sai
~US$ 7/mês sem cold start, e não há limite de 15 minutos nem concorrência a
gerenciar.

ARM64 (Graviton) custa ~20% menos que x86 — e a máquina de desenvolvimento do
time é Apple Silicon, então o build é nativo, sem emulação.

**Quando reconsiderar:** abaixo de ~150 eventos/segundo sustentados, Lambda sai
mais barato. Acima disso, Fargate ganha e a diferença cresce com o volume.

### 3.5 Rede sem NAT Gateway

Subnet pública com IP público e security group **sem nenhuma regra de entrada**.
A task alcança as APIs da AWS, mas ninguém alcança a task.

Isso evita o NAT Gateway, que a ~US$ 32/mês seria o item mais caro do fluxo
inteiro — mais que o dobro de todo o resto somado.

---

## 4. Armazenamento

Tabela única no DynamoDB, compartilhada pelos dois fluxos. O desenho de chaves é
o contrato entre o worker e a API.

### 4.1 Modelo de dados

| Índice | Chave | Responde |
|---|---|---|
| tabela | `pk=SESSION#<id>`, `sk=<ts>#<event_id>` | linha do tempo de uma sessão |
| GSI1 | `gsi1pk=EVT#<tipo>#<data>#<shard>` | "todos os erros de 13/07" |
| GSI2 | `gsi2pk=DEV#<device_id>` | histórico de um aparelho |

**Sharding da GSI1.** Sem o sufixo `#<shard>`, todo evento `request` de um dia
cairia na mesma partição — e uma partição do DynamoDB satura em 1000 WCU. Esse é
o gargalo clássico de ingestão de série temporal.

O shard vem do hash do evento (uniforme e determinístico). O preço é que a
leitura vira fan-out de `GSI1_SHARDS` queries em paralelo.

> `gsi1_shards` (Terraform), `GSI1_SHARDS` (worker) e `GSI1_SHARDS` (API)
> **precisam ser iguais**. Os três montam a mesma chave; divergir faz a leitura
> consultar partições onde a escrita nunca colocou nada — e o resultado é uma
> consulta vazia, **sem erro nenhum**.

**TTL contado da ingestão**, não do horário do evento — senão replay de dado
histórico nasceria já expirado.

### 4.2 Idempotência sem leitura prévia

`event_id = sha256(conteúdo canônico do evento)`, e a chave do item deriva dele.

Duas entregas do mesmo evento produzem a mesma chave, então a reentrega
*at-least-once* do SQS vira um overwrite idêntico em vez de linha duplicada.
Sem `ConditionExpression` (que gastaria WCU na falha) e sem leitura prévia.

**Cuidado que isso exige:** o `BatchWriteItem` rejeita a requisição **inteira**
se dois `PutRequest` tiverem a mesma chave. Como duplicata aqui é rotina e não
exceção, sem deduplicar antes do lote uma reentrega derrubaria os outros 24
itens junto.

### 4.3 O que fica cru no banco

O worker grava o evento como o aparelho enviou, sem transformar. Portanto o
DynamoDB contém `user_id` em claro e o header `authorization` dentro de
`request_headers`. **A remoção desses dados acontece na saída da API** (§5.4),
não na entrada — ver §8 para as implicações.

---

## 5. API de leitura

Flask em Lambda, arquitetura hexagonal: `EventRepository` é um `Protocol`, e o
adaptador DynamoDB é a única peça que conhece o banco.

### 5.1 Somente leitura

Sem POST e sem DELETE. A entrada de eventos é o pipeline de ingestão, que já
resolve idempotência, retry e DLQ; uma segunda porta significaria duas
validações para manter em sincronia e dois caminhos que divergem com o tempo.
O expurgo é feito pelo TTL — a task role do worker nem tem `DeleteItem`.

### 5.2 O roteamento de índice é o que governa o custo

A API escolhe o caminho mais barato que os filtros permitem:

| Estratégia | Quando | Custo |
|---|---|---|
| `table:session` | há `session_id` | 1 query, exata |
| `gsi2:device` | há `device_id` | 1 query |
| `gsi1:fanout` | há `event_name` | N queries paralelas (dias × shards) |
| `table:scan` | nenhum dos três | varre a tabela |

O `Scan` existe porque não há alternativa: sem `event_name` não há chave de
partição, e fazer fan-out pelos tipos conhecidos esconderia os tipos novos que o
pipeline aceita de propósito. **Preferimos ler demais a esconder evento.**

Toda resposta traz um bloco `query` com a estratégia usada e quantos itens foram
lidos. Não é debug: num banco que cobra por item lido, a diferença entre
`scanned` e `returned` é a conta do filtro pós-query, e uma tela barata não pode
parecer igual a uma cara para quem constrói o dashboard.

**O fan-out roda em paralelo.** Uma semana de busca por tipo são 80 queries; em
sequência isso somava 11 segundos — quatro vezes o teto de 3s do RNF02 — com o
banco ocioso, porque o custo era o round-trip e não o trabalho. Em paralelo cai
para ~1,5s.

### 5.3 Agregação em memória

`breakdown` (RF11), `timeseries` (RF12, RF14, RF15) e `facets` (RF10) são
calculados na aplicação: **o DynamoDB não tem `GROUP BY` nem `SELECT DISTINCT`**.

O custo é ler o período inteiro para contar, limitado por `MAX_ITEMS_SCANNED`.
Funciona no volume do MVP; o caminho para escalar é manter contadores
pré-agregados alimentados por DynamoDB Streams — decisão adiada
conscientemente, não esquecida.

### 5.4 Paginação por cursor

O DynamoDB não tem `OFFSET`. O cursor é opaco e carrega, no fan-out, a posição
de **cada partição** — elas avançam em ritmos diferentes no merge por tempo.

No caminho de `Scan` a paginação é por deslocamento e não pela chave do banco:
o Scan devolve em ordem de hash, não de tempo, então responder "mais recentes
primeiro" exige ler o conjunto e ordenar. Retomar pela chave entregaria a página
seguinte da ordem errada.

### 5.5 Documentação que não pode divergir

`GET /docs` serve Swagger UI e `GET /openapi.json` a especificação OpenAPI 3.1.

A spec é montada em código, importando as **mesmas constantes** que o adaptador
usa para validar (`FACET_FIELDS`, `BREAKDOWN_FIELDS`, `POST_FILTERS`).
Documentação derivada da regra não consegue divergir dela. Dois testes travam
isso nos dois sentidos: rota sem entrada na spec, e entrada na spec sem rota.

O campo `servers` é preenchido a partir do host da requisição — o endereço real
não fica escrito em nenhum arquivo do repositório.

---

## 6. Dashboard

Next.js com `output: "export"` — **site estático**, sem servidor Node. A tela é
renderizada no navegador e busca os dados da API de leitura.

Isso simplifica o deploy: são arquivos, não um processo. S3 + CloudFront
resolve por ~US$ 1/mês, com HTTPS incluso e URL estável.

Consequência para a API: como o dashboard vem de outra origem, o CORS é
obrigatório. Ele é tratado nos dois lugares — no API Gateway, para responder ao
preflight `OPTIONS` sem acordar a Lambda, e no Flask, para a resposta em si.

> CORS **não é controle de acesso**. Ele só impede JavaScript de outra origem de
> *ler* a resposta; `curl` e qualquer cliente servidor ignoram por completo. Ver
> §8.

---

## 7. Garantias de entrega

- **At-least-once** (SQS) + **escrita idempotente** (§4.2) = efeito de
  exactly-once no DynamoDB.
- A mensagem só é apagada da fila depois que **todos** os eventos dela foram
  gravados ou desviados para a DLQ.
- Payload que **nunca** vai funcionar (JSON quebrado, envelope inválido, item
  acima de 400 KB) vai direto para a DLQ com o motivo, em vez de queimar as 5
  tentativas do redrive para chegar no mesmo lugar.
- Um evento inválido no meio de um lote não derruba os válidos da mesma
  mensagem.
- `SIGTERM` do ECS encerra após o ciclo atual, sem largar mensagem em voo.
- Durante o deploy, duas tasks consomem a mesma fila simultaneamente
  (blue/green) — janela que a escrita idempotente cobre.

---

## 8. Segurança e privacidade

### 8.1 Estado atual: as duas APIs são públicas

**Nenhuma das duas tem autenticação.** Verificado na infraestrutura:
`authorizers=0` e `authorizationType=NONE` em todas as rotas. Uma requisição sem
credencial nenhuma responde `HTTP 200` com os dados.

Três coisas que costumam confundir:

- **CORS não protege.** Restringir origens parece segurança, mas só afeta
  JavaScript no navegador.
- **Throttling não é controle de acesso.** Limita volume, não quem entra.
- **A URL não é segredo.** Hoje ela é, na prática, a única barreira — e é por
  isso que ela não pode ser commitada (§9.4).

**Exposição na leitura:** qualquer pessoa com a URL lê todos os eventos —
`device_id` e `session_id`, modelo e versão de TV, mensagens de erro, URLs
requisitadas e IDs de conteúdo.

**Exposição na ingestão:** qualquer pessoa pode publicar eventos falsos e poluir
a base.

Isso **não atende o RNF09**, que exige acesso restrito a usuários autorizados.
É a lacuna mais séria do sistema hoje.

### 8.2 O que já é feito (RNF10)

A redação acontece na **saída** da API, não na entrada, porque o worker grava o
evento cru (§4.3). Se ficasse na entrada, nunca rodaria.

| Dado | Tratamento |
|---|---|
| `user_id` | vira `user_id_hash` (SHA-256 com salt) |
| `request_headers` | allowlist; `authorization` nunca sai |
| `request_url` | query string sem `token`, `access_token`, `user_id` |
| `response_headers` | removido inteiro |
| campos de facet e agrupamento | lista fechada, sem campos pessoais |

Redigir na saída preserva a investigação: o dado bruto continua no banco para
quem tiver acesso direto e justificativa.

### 8.3 Lacunas conhecidas

- **`device_id` sai em claro.** Foi hasheado o `user_id`, mas não o
  identificador de aparelho — que também é dado pessoal sob LGPD, por ser
  persistente. Não corrigido porque a rota de histórico por aparelho depende
  dele; exige decisão entre hash com tabela reversa interna ou restringir por
  autenticação.
- **O salt padrão é uma string conhecida** (`trocar-em-producao`). Quem lê o
  Terraform consegue recalcular os hashes. Precisa vir do Secrets Manager.
- **CORS em `*`** nas duas APIs.

---

## 9. Operação

### 9.1 Comandos

Tudo pelo `make` na raiz. `make` sozinho lista os alvos.

| Alvo | O que faz |
|---|---|
| `make install` | prepara os ambientes Python |
| `make test` · `make lint` · `make check` | qualidade |
| `make api` | sobe a API local contra o DynamoDB real |
| `make deploy` | testa, empacota e publica a API de leitura |
| `make worker-deploy` | publica a imagem do worker |
| `make smoke` | verifica a API publicada |
| `make dlq` | mostra os eventos rejeitados, com o motivo |
| `make pause` · `make resume` | desliga e religa o worker |

### 9.2 Custo estimado (~1 M eventos/mês)

| Item | Estimativa |
|---|---|
| Fargate 0.25 vCPU / 0.5 GB ARM, 24/7 | ~US$ 7 |
| DynamoDB on-demand (escrita + 2 GSI) | ~US$ 4 |
| API Gateway (ingestão + leitura) | ~US$ 1 |
| Lambda da API de leitura | ~US$ 0 |
| SQS | ~US$ 0 (free tier) |
| CloudWatch Logs + alarmes | ~US$ 2 |
| **Total** | **~US$ 14/mês** |

Cada GSI multiplica o custo de escrita: uma escrita vira três. O item que **não**
está aqui e seria o maior de todos é o NAT Gateway (~US$ 32/mês), evitado por
`assign_public_ip = true`.

### 9.3 Observabilidade

Métricas em EMF no namespace `Argus/Ingestion` — extraídas do próprio log, sem
chamada de `PutMetricData`.

`EventsUnknownType` subindo é o sinal de que o app começou a mandar um evento
novo. `EventsDeduplicated` é a taxa de reentrega do SQS. `CycleLatency` mede só
o processamento; a espera do long polling vai em `PollWait`, separada — somar as
duas faria a métrica reportar 13s onde o trabalho real levou 400ms.

Cinco alarmes cobrem os modos de falha silenciosa: DLQ com mensagem, fila
atrasada, worker fora do ar, 5xx na borda, throttle de escrita.

### 9.4 Endpoints e segredos

**Nenhuma URL de API ou ID de conta é versionado.** Os valores vivem no `.env`
local (gitignored); o `.env.example` mostra as chaves e como obtê-las via
`terraform output`. `make env` gera o arquivo.

Enquanto as APIs não tiverem autenticação, a URL é o que separa os dados de
qualquer pessoa na internet — publicá-la no repositório é entregar o acesso
junto com o código.

### 9.5 Ambiente de laboratório

O AWS Academy Learner Lab exige duas concessões, ambas por variável:

- `create_iam_roles = false` — o ambiente nega `iam:CreateRole` e obriga a usar
  a `LabRole` pronta, que é **muito** mais permissiva que o necessário. Em conta
  normal, `true` dá permissão mínima a cada componente.
- `dynamodb_kms_managed_key = false` — a chave gerenciada `aws/dynamodb` não
  existe e não pode ser criada. Isso **não** deixa a tabela sem criptografia: o
  DynamoDB criptografa em repouso sempre, a flag só escolhe qual chave.

A sessão expira e derruba o acesso (`voc-cancel-cred` nega tudo). Os recursos
sobrevivem; basta reiniciar o lab e atualizar as credenciais.

---

## 10. Validação

| O quê | Resultado |
|---|---|
| Testes do worker | 58 passando |
| Testes da API | 72 passando |
| `ruff` + `terraform fmt`/`validate` | limpo |
| Imagem do worker (ARM64) | 278 MB |
| Pacote da API de leitura | 628 KB |
| End-to-end da ingestão | ver §10.1 |
| End-to-end da leitura | ver §10.2 |

### 10.1 Ingestão

Requisições HTTP partindo da máquina local:

| Teste | Resultado |
|---|---|
| 1 evento, worker desligado | HTTP 200 em 0,54 s, chegou no SQS |
| 6 eventos reais (1 já enviado antes) | **6 itens, não 7** — idempotência |
| 6 num POST só, todos repetidos | continua 6 |
| JSON quebrado / envelope inválido | DLQ, com o motivo e o campo faltante |
| `event_name` desconhecido | gravado, com os campos customizados |
| 500 eventos únicos, 20 conexões | 500/500, ~320 ev/s, DLQ intacta |

Batching real: 21 ciclos processaram 59 mensagens / 514 eventos, média de 24,5
eventos por ciclo.

### 10.2 Leitura

| Teste | Resultado |
|---|---|
| Os seis tipos reais são lidos | ok — o backend anterior recusava dois |
| Campos `error_*` e `media_*` sobrevivem | ok — eram descartados antes |
| `user_id` e `authorization` não vazam | ok, em todas as rotas |
| Filtros cumulativos, período, cursor | ok |
| Agrupamento e série temporal | ok, contra os 708 eventos reais |
| Latência (RNF02: 3s) | 0,47 s a 1,5 s |

### 10.3 Defeitos encontrados durante a construção

Registrados porque são armadilhas não óbvias do DynamoDB e da AWS:

1. **`BatchWriteItem` derrubado por chave repetida.** Rejeita o lote inteiro, e
   a idempotência por hash faz duplicata colidir de propósito.
2. **`CycleLatency` misturava espera com trabalho**, reportando 13s onde o
   processamento real era de 450ms.
3. **Fan-out sequencial**: 80 round-trips em série, 11 segundos. Paralelizado,
   1,5s.
4. **Janela truncada pelo lado errado**: o corte por `max_days` mantinha os dias
   mais antigos, então uma busca ampla varria o passado e não achava nada do mês
   atual.
5. **Paginação**: partição "esgotada no banco" tratada como "consumida", e no
   Scan retomar pela chave do DynamoDB quando a ordem é por hash e não por
   tempo.
6. **Lambda com 512 MB**: a fatia de CPU é proporcional à memória; 1024 MB
   levou a busca por tipo de ~2,8s para ~1,5s.

Todos com teste de regressão.

---

## 11. Estrutura do repositório

```
apps/
  backend/    API de leitura (Flask em Lambda)
    src/telemetry/
      domain/          entidade alinhada ao que o worker grava
      ports/           contrato de leitura
      infrastructure/  adaptador DynamoDB
      application/     casos de uso e redação de dado pessoal
      interfaces/      rotas Flask e OpenAPI
  worker/     worker de ingestão (SQS → DynamoDB)
  infra/      Terraform de tudo
  tools/      conversão de CSV, replay de eventos, ETL do dump
  frontend/   dashboard Next.js
artefatos/    documentação do projeto
Makefile      comandos
```

