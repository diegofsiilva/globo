# MVP inicial

Primeiro protótipo funcional da plataforma de telemetria, implantado em AWS.

O sistema recebe eventos emitidos pelo app de TV, valida e grava em escala, e os
devolve a um dashboard para investigação de incidentes. Este documento registra o
que está no ar, como o dado é modelado, e o resultado dos testes de GET e POST
executados contra o ambiente real.

O detalhamento das decisões de arquitetura está em [`arquitetura.md`](arquitetura.md);
aqui ficam a implantação e a evidência.

---

## 1. O que está no ar

```
   App de TV                                   Dashboard (S3)
       │                                             ▲
       │ POST /v1/events                             │ GET /api/v1/*
       ▼                                             │
┌──────────────────┐                        ┌────────┴─────────┐
│  API Gateway     │                        │  API Gateway     │
│  ingestão        │                        │  leitura         │
└────────┬─────────┘                        └────────▲─────────┘
         │ integração direta                         │
         ▼ (sem Lambda)                              │
┌──────────────────┐     ┌──────────┐       ┌────────┴─────────┐
│  SQS             │────▶│ SQS DLQ  │       │  Lambda          │
│  argus-events    │ 5t. │ inválido │       │  Flask + apig    │
└────────┬─────────┘     └──────────┘       └────────▲─────────┘
         │ long polling 20s                          │
         ▼                                           │
┌──────────────────┐                                 │
│  ECS Fargate     │                                 │
│  worker (Python) │                                 │
└────────┬─────────┘                                 │
         │ BatchWriteItem                            │
         ▼                                           │
┌─────────────────────────────────────────────────┐  │
│  DynamoDB — tabela única + GSI1 + GSI2          │──┘
└─────────────────────────────────────────────────┘
```

**Recursos provisionados**, verificados na conta do AWS Academy Learner Lab
(`us-east-1`) no dia da entrega:

| Serviço | Recurso | Estado |
|---|---|---|
| API Gateway (HTTP) | ingestão — `POST /v1/events` → SQS | ativo, sem autenticação |
| API Gateway (HTTP) | leitura — `ANY /{proxy+}` → Lambda | ativo, sem autenticação |
| SQS | `argus-events-dev` + DLQ com redrive de 5 tentativas | 0 mensagens em espera |
| ECS Fargate | worker, ARM64, 0.25 vCPU / 0.5 GB | 1/1 task rodando |
| DynamoDB | `argus-events-dev`, on-demand, 2 GSI | 718 itens · 513 KB |
| Lambda | `argus-events-dev-read-api`, Python 3.12 ARM64 | 1024 MB, timeout 30 s |
| S3 | site estático do dashboard | público, website hosting |

Os endereços das duas APIs não são versionados (ver §7). Obtêm-se com
`terraform output`.

---

## 2. Modelo de dados

### 2.1 Modelo lógico

![Modelo lógico dos eventos](assets/der-dynamodb-logico.png)
<sup>Fonte: material produzido pelos autores (2026).</sup>

Um **evento** é o fato central, e carrega referências para as entidades de
contexto: a **sessão** em que ocorreu, o **aparelho** que o emitiu, a **versão do
app** e, quase sempre, o **usuário**.

Os seis tipos conhecidos (`request`, `screen_view`, `session`, `video_view`,
`vitals`, `error`) são especializações que acrescentam campos próprios ao mesmo
envelope. **A lista não é fechada:** um `event_name` desconhecido cai em
`GenericEvent` e é gravado do mesmo jeito, com os campos extras preservados. Isso
não é teoria — a base tem hoje um evento `ad_impression`, tipo que nenhuma linha
de código conhece, gravado e legível pela API.

A razão é operacional: o parque de TVs atualiza devagar e de forma desigual, e um
modelo estrito transformaria qualquer mudança de schema no app em perda de dados
em massa — sem chance de hotfix num aparelho.

### 2.2 Modelo físico

![Modelo físico single-table](assets/der-dynamodb-fisico.png)
<sup>Fonte: material produzido pelos autores (2026).</sup>

Tabela única no DynamoDB, com três caminhos de acesso. O desenho das chaves é o
contrato entre o worker que grava e a API que lê:

| Índice | Chave | Responde |
|---|---|---|
| tabela | `pk=SESSION#<id>` · `sk=<ts>#<event_id[:12]>` | linha do tempo de uma sessão |
| GSI1 | `gsi1pk=EVT#<tipo>#<data>#<shard>` | eventos de um tipo num dia |
| GSI2 | `gsi2pk=DEV#<device_id>` | histórico de um aparelho |

Dois pontos que o diagrama registra e que não são óbvios:

**O sufixo `#<shard>` na GSI1.** Sem ele, todo evento de um mesmo tipo num mesmo
dia cairia na mesma partição, e uma partição do DynamoDB satura em 1000 WCU — o
gargalo clássico de ingestão de série temporal. O shard vem do hash do evento,
que é uniforme e determinístico. O preço é que a leitura vira um fan-out de N
queries paralelas.

**O TTL é contado da ingestão, não do horário do evento.** Se fosse do evento, um
replay de dado histórico nasceria já expirado.

---

## 3. A aplicação: GET e POST

### 3.1 POST — ingestão

```
POST <ingest_url>
Content-Type: application/json
```

Aceita um evento, uma lista, ou o envelope `{"events": [...]}`. Quatro campos são
obrigatórios: `timestamp`, `event_name`, `session_id`, `device_id`. O resto é
opcional e campos desconhecidos são preservados.

```json
{
  "timestamp": "2026-08-13T14:20:00Z",
  "event_name": "error",
  "session_id": "sessao-123",
  "device_id": "dev-000492",
  "error_name": "Erro ao reproduzir vídeo",
  "error_stack": "dash_shaka_playback:6_6002"
}
```

O API Gateway publica direto no SQS, sem Lambda no caminho. Duas consequências
que quem consome a API precisa saber, e que os testes documentam em §4.3:
a resposta é o **XML do SQS**, não JSON, e **payload inválido recebe HTTP 200** —
a rejeição é assíncrona, na DLQ.

### 3.2 GET — leitura

```
GET <read_url>/api/v1/events?event_name=error&device_os=Tizen&limit=50
```

| Rota | O que devolve |
|---|---|
| `GET /api/v1/events` | busca paginada com filtros cumulativos |
| `GET /api/v1/sessions/{id}` | linha do tempo da sessão + resumo |
| `GET /api/v1/sessions/{id}/events/{event_id}` | detalhe de um evento |
| `GET /api/v1/devices/{id}` | histórico do aparelho |
| `GET /api/v1/metrics/breakdown?dimension=…` | agrupamento e contagem |
| `GET /api/v1/metrics/timeseries?compare=true` | série temporal e comparação |
| `GET /api/v1/facets?field=…` | valores existentes para os filtros |
| `GET /docs` · `GET /openapi.json` | Swagger UI e especificação OpenAPI 3.1 |

Toda resposta de busca traz um bloco `query` com a estratégia usada e quantos
itens foram lidos:

```json
{
  "items": [ … ],
  "next_cursor": null,
  "query": { "strategy": "gsi1:fanout", "queries": 40, "scanned": 119, "returned": 20 }
}
```

Isso não é debug. Num banco que cobra por item lido, a diferença entre `scanned` e
`returned` é a conta do filtro que roda depois da consulta ao índice — e uma tela
barata não pode parecer igual a uma cara para quem constrói o dashboard.

---

## 4. Relatório de testes — Postman

### 4.1 Metodologia

A coleção está em [`postman/argus.postman_collection.json`](postman/argus.postman_collection.json)
e roda contra o ambiente implantado, não contra mock. São 17 requisições em três
grupos:

1. **GET** na API de leitura — os quatro caminhos de acesso, agregações, e os
   casos de erro
2. **POST** na API de ingestão — evento único, lote, reenvio, tipo desconhecido e
   payload inválido
3. **Verificação end-to-end** — consulta pela API de leitura a sessão que o grupo
   2 criou pela API de ingestão

O grupo 3 é o que dá valor ao conjunto: em vez de testar as duas APIs em
isolamento, ele fecha o ciclo `POST → SQS → worker → DynamoDB → GET` e verifica o
resultado. Como o worker faz long polling de 20 s, a requisição repete a si mesma
até os eventos aparecerem, com teto de 20 tentativas.

Execução por linha de comando, para que o resultado seja reproduzível:

```bash
make postman
```

### 4.2 Resultados

**51 asserções, 0 falhas.** Execução de 13/08/2026, duração total 34,7 s.

| Caso | Método | Status | Tempo | Asserts |
|---|---|---|---|---|
| 1.1 Saúde da API | GET | 200 | 592 ms | 2/2 |
| 1.2 Busca sem filtro (`table:scan`) | GET | 200 | 977 ms | 5/5 |
| 1.3 Busca por tipo (`gsi1:fanout`) | GET | 200 | 1308 ms | 5/5 |
| 1.4 Linha do tempo da sessão (`table:session`) | GET | 200 | 228 ms | 5/5 |
| 1.5 Histórico do aparelho (`gsi2:device`) | GET | 200 | 180 ms | 3/3 |
| 1.6 Valores para os filtros (facets) | GET | 200 | 218 ms | 3/3 |
| 1.7 Agrupamento por fabricante | GET | 200 | 721 ms | 3/3 |
| 1.8 Série temporal com comparação | GET | 200 | 1130 ms | 3/3 |
| 1.9 Privacidade: sem `user_id` nem `authorization` | GET | 200 | 1291 ms | 4/4 |
| 1.10 Erro: período inválido | GET | **422** | 218 ms | 3/3 |
| 1.11 Erro: sessão inexistente | GET | **404** | 205 ms | 1/1 |
| 2.1 Evento único | POST | 200 | 553 ms | 3/3 |
| 2.2 Lote de três eventos | POST | 200 | 206 ms | 1/1 |
| 2.3 Reenvio idêntico | POST | 200 | 232 ms | 1/1 |
| 2.4 Tipo de evento desconhecido | POST | 200 | 204 ms | 1/1 |
| 2.5 Payload inválido | POST | 200 | 236 ms | 2/2 |
| 3.1 Os eventos postados chegaram ao banco | GET | 200 | 193 ms | 6/6 |

Latência: mínima 180 ms, média 511 ms, máxima 1308 ms. **O RNF02 exige resposta
em até 3 s** — a consulta mais cara ficou em 44% do orçamento.

A consulta mais cara é a busca por tipo (1.3), e o motivo está no modelo: ela abre
uma query por (dia × shard). É o custo escolhido quando se resolveu o gargalo de
partição da GSI1.

### 4.3 Achados

**A ingestão é idempotente, e isso é verificável.** O caso 2.3 reenvia um corpo
byte a byte idêntico ao de 2.1. Como o `event_id` é o sha256 do conteúdo, os dois
produzem a mesma chave e o segundo vira um overwrite idêntico. O caso 3.1 confirma:
a sessão tem **5 eventos, não 6**.

**Tipo desconhecido entra e sai inteiro.** O caso 2.4 envia `postman_probe`, que
não existe em nenhuma linha de código, com dois campos inventados. O caso 3.1
confirma que o evento foi gravado e que `campo_que_o_backend_nunca_viu` sobreviveu
até a resposta da API.

**Payload inválido recebe HTTP 200 — e isso é deliberado.** O caso 2.5 envia um
evento sem `timestamp`, `session_id` nem `device_id`. A resposta é 200. O motivo é
que a integração direta API Gateway → SQS não tem request validator (só o REST API
tem; o HTTP API não), então o payload entra cru na fila e quem valida é o worker.

A rejeição acontece, só que assíncrona. Verificado na DLQ:

```
corpo:  {"event_name": "error", "sem_timestamp": true, …}
motivo: validacao: 3 validation errors for ErrorEvent
        timestamp — Field required
```

É uma troca consciente: para telemetria, aceitar rápido e validar depois é melhor
que segurar a TV do usuário esperando validação, e o evento inválido não se perde.
Mas **quem consome a API precisa saber que 200 aqui significa "enfileirado", não
"válido"** — e é por isso que este caso está na coleção em vez de ser escondido.

**A redação de dado pessoal funciona em todas as rotas.** O caso 1.9 varre o corpo
da resposta atrás do header `authorization` e do `user_id` cru. O worker grava o
evento como o aparelho enviou, então os dois estão no banco; a remoção acontece na
saída da API (RNF10).

---

## 5. Frontend

Dashboard em Next.js com `output: "export"` — site estático, sem servidor Node —
hospedado em **S3 com website hosting**. Ele consome a API de leitura pelo
navegador e mostra os eventos em tempo quase real.

![Dashboard servido pelo S3](assets/dashboard-s3.jpg)
<sup>Fonte: material produzido pelos autores (2026).</sup>

A entrega aceitava S3 ou EC2. Escolhemos S3 por uma razão prática: **o Learner Lab
desliga as instâncias EC2 ao fim da sessão, e o IP público muda ao religar** — o
link deste relatório e do vídeo morreria entre a gravação e a correção. O endereço
do bucket é estável e atravessa o ciclo do lab. O deploy também vira um
`aws s3 sync`, sem nginx e sem instância para manter viva.

Custo aceito: o website endpoint do S3 é HTTP puro, sem TLS. O caminho para HTTPS
é CloudFront na frente, registrado como evolução.

> **Vídeo de demonstração:** `<INSERIR O LINK AQUI>`

---

## 6. Como executar

### Local

```bash
git clone <repo> && cd g04
cp .env.example .env          # preencha com os terraform output
make install                  # ambientes Python do backend e do worker
make test                     # 58 testes do worker + 72 do backend
make frontend-install
make frontend-dev             # dashboard local contra a API publicada
```

O backend também sobe sozinho com `python apps/basica/backend/run.py`, ou pelo
**Run and Debug** do VS Code (configuração `Backend Flask`, em
`apps/basica/backend/.vscode/`).

### AWS

```bash
cd apps/basica/infra
terraform init && terraform apply

cd ../../..
make deploy            # empacota e publica a API de leitura
make worker-deploy     # publica a imagem do worker
make frontend-deploy   # build do dashboard e sync no S3
make smoke             # verifica a API publicada
make postman           # roda a coleção de testes
```

O lab exige duas concessões, ambas por variável: `create_iam_roles = false` (o
ambiente nega `iam:CreateRole` e obriga a usar a `LabRole`) e
`dynamodb_kms_managed_key = false` (a chave `aws/dynamodb` não existe ali). A
segunda não deixa a tabela sem criptografia — o DynamoDB sempre criptografa em
repouso, a flag só escolhe qual chave.

---

## 7. Limitações conhecidas

Registradas porque escondê-las não as resolve.

**As duas APIs são públicas.** Nenhuma tem autenticação: `authorizationType=NONE`
em todas as rotas, verificado na infraestrutura. Qualquer pessoa com a URL lê
todos os eventos e pode publicar eventos falsos. Isso não atende o **RNF09**, e é
a lacuna mais séria do sistema hoje.

**Publicar o dashboard tornou a URL da API descobrível.** A URL entra no bundle
JavaScript em tempo de build, e o bundle está num bucket público. Até aqui a
política do repositório era não versionar a URL, tratando-a como barreira de
acesso — mas ela nunca foi controle de acesso, e agora isso é demonstrável. A
conclusão prática: **autenticação na API deixou de ser opcional.** O caminho mais
barato é um Lambda authorizer com token no SSM; Cognito é o correto para produção
e permite login no dashboard.

**Outras pendências**, em ordem de risco: `device_id` sai em claro (é dado pessoal
sob LGPD por ser persistente); o salt da pseudonimização tem valor padrão conhecido
e precisa vir do Secrets Manager; CORS está em `*` nas duas APIs; o estado do
Terraform é local, o que impede dois `apply` simultâneos com segurança.

**Sobre os dados de teste:** a execução da coleção deixa 10 eventos sintéticos na
base, identificáveis por `session_id` começando com `postman-`, e as mensagens
correspondentes na DLQ. Eles expiram sozinhos pelo TTL de 90 dias.

---

## Referências

- [`arquitetura.md`](arquitetura.md) — decisões de arquitetura e trade-offs
- [`requisitos.md`](requisitos.md) — RF e RNF referenciados aqui
- [`postman/argus.postman_collection.json`](postman/argus.postman_collection.json) — a coleção executada
- [`assets/der-dynamodb.drawio`](assets/der-dynamodb.drawio) — fonte editável dos diagramas
