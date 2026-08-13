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

O ponto que confunde quem chega agora: **o `.env` não é o primeiro passo, é uma
consequência do último.** As duas URLs que ele guarda são geradas pelo API
Gateway no primeiro `terraform apply` — antes disso não existe valor para
preencher, e copiar o `.env.example` só produz um arquivo de chaves vazias. A
ordem real é:

```
credenciais do lab  →  terraform apply  →  make env  →  deploy  →  URL do dashboard
```

Quem só quer inspecionar o código não precisa de nada disso: `make install &&
make test` roda as duas suítes contra um DynamoDB falso (moto), sem conta AWS.

### 6.1 Pré-requisitos

| Ferramenta | Para quê | Conferir com |
|---|---|---|
| Python 3.12+ | backend, worker e tools | `python3 --version` |
| [uv](https://docs.astral.sh/uv/) | monta os ambientes Python pelo `pyproject.toml` | `uv --version` |
| Node.js 20+ | build do dashboard e execução da coleção Postman | `node --version` |
| Docker | imagem ARM64 do worker | `docker info` |
| Terraform 1.x | toda a infraestrutura | `terraform version` |
| AWS CLI v2 | credenciais, `s3 sync`, logs e DLQ | `aws --version` |

```bash
git clone https://git.inteli.edu.br/graduacao/2026-2a/t15/g04.git && cd g04
```

### 6.2 Conectar o Terraform ao AWS Academy Learner Lab

O `providers.tf` não tem `access_key` nem `profile` de propósito: o provider AWS
lê a cadeia de credenciais padrão do SDK. Configurar o ambiente é, portanto, todo
o trabalho de autenticação — e nenhum segredo chega perto do repositório.

**1. Iniciar o laboratório.** No AWS Academy, abra o módulo do Learner Lab e
clique em **Start Lab**. Espere o indicador ao lado de **AWS** ficar verde; com
ele amarelo a conta ainda está sendo provisionada e as credenciais não funcionam.

**2. Copiar as credenciais.** Clique em **AWS Details**, no topo do painel, e
depois em **Show**, ao lado de *AWS CLI*. Aparece um bloco assim:

```ini
[default]
aws_access_key_id=ASIA...
aws_secret_access_key=...
aws_session_token=...
```

São credenciais temporárias (STS). O `aws_session_token` é parte obrigatória
delas — sem ele a AWS recusa a chamada — e **os três valores mudam a cada
reinício do lab**.

**3. Gravar num profile nomeado.** Cole o bloco em `~/.aws/credentials`,
trocando `[default]` por `[g4]`. O profile nomeado evita sobrescrever credenciais
de outra conta que você já tenha na máquina:

```ini
# ~/.aws/credentials
[g4]
aws_access_key_id=ASIA...
aws_secret_access_key=...
aws_session_token=...
```

```ini
# ~/.aws/config
[profile g4]
region=us-east-1
output=json
```

Aponte o ambiente para ele e confirme **antes de aplicar qualquer coisa**:

```bash
export AWS_PROFILE=g4
aws sts get-caller-identity
```

A resposta traz o número da conta e um `Arn` terminando em `user/voclabs` — é
assim que se sabe que é a conta do lab, e não outra. `ExpiredToken` ou
`InvalidClientTokenId` significa lab parado ou credencial de uma sessão anterior:
volte ao passo 1.

**4. Escrever o `terraform.tfvars`.** O lab exige duas concessões, ambas por
variável, nenhuma delas bifurcando o código:

```bash
cd apps/basica/infra
cp terraform.tfvars.example terraform.tfvars
```

Descomente o bloco `AWS Academy` do arquivo e preencha o ARN da `LabRole`. Para
montar o ARN sem abrir o console:

```bash
echo "arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/LabRole"
```

O conteúdo mínimo para o lab é:

```hcl
region      = "us-east-1"
environment = "dev"

# O lab nega iam:CreateRole e obriga a reusar a LabRole, que já confia em
# apigateway.amazonaws.com e ecs-tasks.amazonaws.com — os dois papéis de que
# este fluxo precisa. Numa conta normal, create_iam_roles = true dá permissão
# mínima a cada componente.
create_iam_roles  = false
existing_role_arn = "arn:aws:iam::<sua-conta>:role/LabRole"

# O lab não provisiona a chave gerenciada aws/dynamodb, e sem esta linha o
# CreateTable falha com "KMS validation error ... does not exist". A tabela
# continua criptografada em repouso: a flag só troca a chave gerenciada pela
# AWS-owned, que é a padrão.
dynamodb_kms_managed_key = false

assign_public_ip = true
gsi1_shards      = 10
```

`terraform.tfvars` está no `.gitignore`, porque guarda o número da conta.

### 6.3 Primeira subida, do zero até a URL

```bash
# 0. ambientes Python do backend e do worker
make install

# 1. empacotar a API de leitura ANTES do primeiro plan
make lambda-build
```

O passo 1 não é opcional e não pode vir depois: o Terraform calcula
`filebase64sha256` do zip da Lambda para decidir se a função mudou, e isso
acontece no **plan**. Sem o arquivo, o primeiro `terraform apply` aborta antes de
criar qualquer recurso.

```bash
# 2. criar a infraestrutura com o worker desligado
cd apps/basica/infra
terraform init
terraform apply -var="worker_desired_count=0"
```

O `-var` existe porque o ECR nasce vazio: subir o service ECS antes da primeira
imagem existir o deixa em crash loop. Não quebra nada, mas assusta e polui o log.

```bash
# 3. construir a imagem ARM64 do worker e publicá-la no ECR
cd ../../..
make worker-deploy

# 4. ligar o worker
cd apps/basica/infra && terraform apply -var="worker_desired_count=1"
cd ../../..
```

```bash
# 5. gerar o .env com as URLs que acabaram de nascer
make env
```

`make env` lê `terraform output` e escreve as quatro chaves do `.env.example`
já preenchidas — é o que substitui o `cp .env.example .env` feito à mão. Ele se
recusa a sobrescrever um `.env` existente, então apague o arquivo antes de
regerar. Se a infraestrutura ainda não tiver sido aplicada, o arquivo nasce com
os valores vazios: apague e repita depois do passo 2. O `AWS_PROFILE` gravado é o
que estiver no shell, então exporte `g4` antes (passo 3 de §6.2).

```bash
# 6. publicar o dashboard
make frontend-install
make frontend-deploy
```

O `frontend-deploy` injeta `ARGUS_API_URL` no bundle em tempo de build, sincroniza
o export estático no bucket e **imprime o endereço público do dashboard ao final**
— é esse o link que vai no relatório e no vídeo.

```bash
# 7. verificar
make smoke      # confere as rotas da API publicada
make postman    # roda as 17 requisições da coleção (§4)
make count      # conta os eventos armazenados
```

Nos deploys seguintes nada disso se repete: `make deploy` testa, empacota,
aplica e roda o smoke num comando só.

### 6.4 De onde vem cada URL

Todo endereço do sistema é um output do Terraform. Nenhum é versionado (§7), e é
por isso que o `.env.example` traz as chaves sem valor.

```bash
cd apps/basica/infra && terraform output
```

| Output | O que é | Quem consome |
|---|---|---|
| `read_api_url` | base da API de leitura | `.env` → `ARGUS_API_URL`; entra no bundle do dashboard |
| `ingest_url` | endpoint do `POST` de eventos | `.env` → `ARGUS_INGEST_URL`; `make replay` e a coleção Postman |
| `frontend_url` | endereço público do dashboard | o link do relatório e do vídeo |
| `table_name` · `dlq_url` · `log_group_worker` | nomes de recurso | `make count`, `make dlq`, `make logs-worker` |

Para um valor isolado, `-raw` devolve a string limpa, sem aspas:

```bash
terraform output -raw read_api_url
```

O environment do Postman segue a mesma regra: `make postman-env` o gera a partir
do `.env`, e o arquivo com as URLs reais fica fora do repositório.

### 6.5 Rodar local

```bash
make test                     # 58 testes do worker + 72 do backend, sem AWS
make api                      # API de leitura na porta 5000, contra o DynamoDB real
make frontend-install
make frontend-dev             # dashboard na porta 3000, contra a API publicada
```

`make test` e `make lint` não precisam de credencial nenhuma. `make api`,
`make frontend-dev` e os alvos de operação precisam do `.env` preenchido.

O backend também sobe sozinho com `python apps/basica/backend/run.py`, ou pelo
**Run and Debug** do VS Code (configuração `Backend Flask`, em
`apps/basica/backend/.vscode/`).

### 6.6 Quando o lab reinicia

A infraestrutura, o estado do Terraform e as URLs sobrevivem — foi exatamente por
isso que o dashboard foi para o S3 e a API de leitura para a Lambda (§5). O que
morre é a credencial: refaça os passos 1 a 3 de §6.2 com o token novo e siga de
onde parou, sem reaplicar nada.

Se um comando falhar com `ExpiredToken` no meio de um `apply`, o remédio é o
mesmo: renove a credencial e rode de novo, porque o Terraform retoma a partir do
estado. Se o worker não estiver consumindo a fila depois do reinício,
`make resume` recria a task e o consumo retoma de onde parou — a fila retém as
mensagens por 4 dias.



