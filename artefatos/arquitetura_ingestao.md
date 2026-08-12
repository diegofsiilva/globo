# Arquitetura — ingestão de eventos de telemetria

Fluxo de ingestão dos eventos emitidos pelo app de TV: aceita o evento na borda,
enfileira, valida de forma assíncrona e grava no DynamoDB.

**Status:** aplicado e validado ponta a ponta na AWS Academy Learner Lab
(conta `<conta>`, us-east-1). Ver §5.

---

## 1. Visão geral

```
   App de TV                                              
       │                                                   
       │  POST /v1/events                                  
       ▼                                                   
┌──────────────────┐                                       
│  API Gateway     │  HTTP API (v2)                        
│  HTTP API        │  integração direta SQS-SendMessage    
└────────┬─────────┘  sem Lambda no meio                   
         │                                                 
         ▼                                                 
┌──────────────────┐        ┌──────────────────┐          
│  SQS             │───────▶│  SQS DLQ         │          
│  argus-events    │ 5 tent. │  investigação    │          
└────────┬─────────┘        └──────────────────┘          
         │  long polling (20s)          ▲                  
         ▼                              │ payload inválido 
┌──────────────────┐                    │ (direto, sem     
│  ECS Fargate     │────────────────────┘  gastar retry)   
│  worker (Python) │                                       
└────────┬─────────┘                                       
         │  BatchWriteItem (25/chamada)                    
         ▼                                                 
┌──────────────────┐                                       
│  DynamoDB        │  tabela única + GSI1 + GSI2 + TTL     
└──────────────────┘                                       
```

Cada etapa e o porquê dela:

| Etapa | Papel | Por que assim |
|---|---|---|
| API Gateway | aceita e enfileira | responde rápido; a TV não espera a gravação |
| SQS | absorve pico e garante entrega | pico de audiência não derruba a ingestão |
| Fargate | valida e grava | processo longo, com polling — não cabe em Lambda barato |
| DynamoDB | armazena | escrita barata, schemaless, TTL nativo |

---

## 2. Os eventos

Seis tipos, extraídos dos exports em `Downloads/Events`:

| `event_name` | O que registra | Campos próprios |
|---|---|---|
| `request` | chamada HTTP do app | método, url, status, headers |
| `screen_view` | entrada numa tela | `route_path`, `route_params` |
| `session` | ciclo de vida da sessão | 7 `capabilities_*`, resolução, user agent |
| `video_view` | reprodução de vídeo | `media_id`, `media_kind`, `media_ads`, `media_drm` |
| `vitals` | saúde do player | `action` (ex.: `frozen`), `duration` |
| `error` | erro exibido ao usuário | `error_name`, `error_message`, `error_stack` |

Envelope comum a todos: `timestamp`, `event_name`, `session_id`, `device_id`,
`app_*`, `device_*`, e quase sempre `user_id`, `duration`, `route_path`.

### 2.1 Timestamps estavam 3 horas deslocados

O export do BI traz `"July 13, 2026 20:04:44"` **sem timezone**. No evento
`request`, o header `date` da própria resposta HTTP diz `23:04:44 GMT` — mesma
requisição, 3 horas de diferença.

Ou seja: o BI renderiza em `America/Sao_Paulo` e omite o fuso. Tratar isso como
UTC deslocaria silenciosamente todo dashboard de horário em 3 horas — o tipo de
erro que ninguém percebe até alguém perguntar por que o pico de audiência é de
madrugada.

**Decisão:** `tools/events_csv_to_json.py` assume `America/Sao_Paulo` e converte
para UTC. A API espera ISO-8601; timestamp sem fuso é tratado como UTC.

### 2.2 Formato do payload

Campos em `snake_case` plano, espelhando 1:1 as colunas do export:
`"App Bucket"` → `app_bucket`. `route_params` e os headers continuam objetos.

Aninhar (`app: {bucket, env}`) ficaria mais bonito, mas plano mapeia direto para
o vocabulário que o time de dados já usa no BI e simplifica projeção e filtro no
DynamoDB.

Uma correção na fronteira: o export escreve `Capabilities Audio Dobly Atmos`.
É *Dolby*. O typo do fornecedor é corrigido na conversão para não virar nome de
coluna permanente.

---

## 3. Decisões e trade-offs

### 3.1 HTTP API com integração direta ao SQS, sem Lambda

`SQS-SendMessage` deixa o próprio API Gateway publicar na fila.

**Ganho:** sem cold start, um ponto de falha a menos, e HTTP API custa
US$ 1,00/milhão contra US$ 3,50 do REST API.

**Custo:** HTTP API **não tem request validator** (só o REST API tem). Não há
validação de schema na borda — o payload entra cru na fila e quem valida é o
worker.

**Por que aceitar:** para telemetria, aceitar rápido e validar assíncrono é
melhor que segurar a TV do usuário esperando validação. O evento inválido não se
perde: vai para a DLQ com o motivo anexado. Se um dia for preciso rejeitar na
borda, o caminho é trocar para REST API com JSON Schema — mais caro e mais lento.

Duas consequências confirmadas no ambiente real, que quem consumir a API precisa
saber:

- **Payload inválido recebe HTTP 200.** A rejeição é assíncrona. Um cliente que
  mandar lixo recebe sucesso e só descobre o problema olhando a DLQ.
- **A resposta é o XML do SQS**, não JSON. O API Gateway repassa a resposta crua
  do serviço, e HTTP API não transforma corpo — só cabeçalho e status. Na prática
  cliente de telemetria é fire-and-forget e ignora o corpo, mas não dá para
  prometer um contrato de resposta JSON sem colocar um Lambda no caminho.

### 3.2 SQS Standard, não FIFO

FIFO daria ordem e deduplicação, mas limita a ~3.000 msg/s e custa mais.

Não precisamos de nenhuma das duas: a ordem é reconstruída na leitura pela sort
key (timestamp), e a deduplicação vem da chave derivada do hash do conteúdo
(§3.4) — que inclusive pega duplicata separada por mais de 5 minutos, coisa que
a janela de deduplicação do FIFO não pegaria.

### 3.3 Modelo de dados no DynamoDB

Tabela única, três padrões de acesso:

| Índice | Chave | Responde |
|---|---|---|
| tabela | `pk=SESSION#<id>`, `sk=<ts>#<event_id>` | linha do tempo de uma sessão |
| GSI1 | `gsi1pk=EVT#<tipo>#<data>#<shard>` | "todos os erros de 13/07" |
| GSI2 | `gsi2pk=DEV#<device_id>` | histórico de um aparelho |

**Sharding da GSI1.** Sem o sufixo `#<shard>`, todo evento `request` de um dia
cairia na mesma partição — e uma partição do DynamoDB satura em 1000 WCU. Esse é
o gargalo clássico de ingestão de série temporal, e com telemetria de um parque
de TVs ele apareceria rápido.

O shard vem do hash do evento (uniforme e determinístico). O preço é que a
leitura vira fan-out de `GSI1_SHARDS` queries em paralelo — mesmo custo de
leitura, só mais uma chamada. Em dev dá para usar `gsi1_shards = 1`.

> `gsi1_shards` (Terraform) e `GSI1_SHARDS` (worker) **precisam ser iguais**.
> Mudar um sem o outro torna os dados antigos invisíveis para a query nova.

**TTL contado da ingestão, não do horário do evento** — senão replay de dado
histórico nasceria já expirado.

### 3.4 Idempotência sem leitura prévia

`event_id = sha256(conteúdo canônico do evento)`, e a chave do item deriva dele.

Duas entregas do mesmo evento produzem a mesma chave, então a reentrega
*at-least-once* do SQS vira um overwrite idêntico em vez de linha duplicada.
Sem `ConditionExpression` (que gastaria WCU na falha) e sem leitura prévia.

Se o cliente mandar `event_id`, ele tem prioridade.

**Cuidado que isso exige:** o `BatchWriteItem` rejeita a requisição **inteira**
se dois `PutRequest` tiverem a mesma chave. Como duplicata aqui é rotina e não
exceção, sem deduplicar antes do lote uma reentrega derrubaria os outros 24
itens junto. O worker deduplica antes de montar o lote
(`repository._dedupe`), e há teste de regressão para isso.

### 3.5 Validação permissiva, de propósito

Só quatro campos são obrigatórios: `timestamp`, `event_name`, `session_id`,
`device_id`. O resto é opcional, campos desconhecidos são preservados
(`extra="allow"`), e `event_name` novo cai num `GenericEvent` em vez de virar
erro.

**Por quê:** o parque de TVs atualiza devagar e de forma desigual. Um modelo
estrito transformaria qualquer mudança de schema no app em perda de dados em
massa — e não dá para fazer hotfix numa TV.

A validação não some, ela vira observabilidade: campo recomendado ausente
incrementa `EventsIncomplete`, tipo novo incrementa `EventsUnknownType`. O dado
entra; o time fica sabendo.

### 3.6 Fargate, não Lambda

Lambda com trigger de SQS seria mais simples e escalaria a zero. Mas:

- o worker se beneficia de conexão persistente e de long polling de 20s;
- 1 task Fargate 24/7 sai ~US$ 9/mês, previsível e sem cold start;
- não há limite de 15 minutos nem de concorrência para gerenciar.

ARM64 (Graviton) custa ~20% menos que x86 — e a máquina de desenvolvimento do
time é Apple Silicon, então o build é nativo, sem emulação.

**Quando reconsiderar:** se o tráfego for muito intermitente (silêncio a maior
parte do dia), Lambda ficaria mais barato.

### 3.7 Rede sem NAT Gateway

Subnet pública com IP público e security group **sem nenhuma regra de entrada**.
A task alcança as APIs da AWS, mas ninguém alcança a task.

Isso evita o NAT Gateway, que a ~US$ 32/mês seria o item mais caro do fluxo
inteiro — mais que o dobro de todo o resto somado. A alternativa privada está
documentada em `infra/README.md`.

---

## 4. Garantias de entrega

- **At-least-once** (SQS) + **escrita idempotente** (§3.4) = efeito de
  exactly-once no DynamoDB.
- A mensagem só é apagada da fila depois que **todos** os eventos dela foram
  gravados ou desviados para a DLQ. Falha de escrita segura o delete, o SQS
  devolve a mensagem, o redrive tenta de novo.
- Payload que **nunca** vai funcionar (JSON quebrado, envelope inválido, item
  acima de 400 KB) vai direto para a DLQ com o motivo, em vez de queimar as 5
  tentativas do redrive para chegar no mesmo lugar.
- Um evento inválido no meio de um lote não derruba os válidos da mesma
  mensagem.
- `SIGTERM` do ECS encerra após o ciclo atual, sem largar mensagem em voo.

---

## 5. Validação feita

| O quê | Resultado |
|---|---|
| `pytest` (worker) | 58 testes passando |
| `ruff check` + `format` | limpo |
| `docker build --platform linux/arm64` | ok, imagem de 278 MB |
| `terraform validate` | válido |
| `terraform apply` na Learner Lab | 23 recursos criados |
| End-to-end real, da máquina para a AWS | ver §5.2 |

### 5.2 End-to-end na AWS real

Requisições HTTP partindo da máquina local para
`$ARGUS_INGEST_URL/v1/events`:

| Teste | Esperado | Resultado |
|---|---|---|
| 1 evento, worker desligado | chega no SQS | HTTP 200 em 0,54 s, 1 msg na fila |
| 6 eventos reais (1 já enviado antes) | 6 itens, não 7 | **6** — idempotência |
| 6 eventos num POST só, todos repetidos | continua 6 | **6** |
| JSON quebrado | DLQ com motivo | DLQ, `JSON invalido: ...` |
| Evento sem envelope mínimo | DLQ com motivo | DLQ, nomeia `timestamp` e `device_id` |
| `event_name` desconhecido | gravado, não recusado | gravado com `ad_provider` e `ad_duration` |
| Carga: 500 eventos únicos, 20 conexões | tudo grava, nada na DLQ | **500/500**, DLQ intacta |
| Carga: 200 eventos após redeploy | delta exato | **+200**, sem perda nem duplicata |

Outras verificações:

- shards da GSI1 idênticos aos do teste local (2, 8, 4, 2, 4, 1) — a derivação é
  determinística entre ambientes;
- fan-out da GSI1 em 10 shards recuperou os 6 eventos do dia;
- GSI2 devolveu o histórico do aparelho;
- batching real: 21 ciclos processaram 59 mensagens / 514 eventos, média de 24,5
  eventos por ciclo;
- durante o redeploy, **duas tasks consumiram a mesma fila simultaneamente**
  (blue/green com `minimum_healthy_percent = 100`) e nada duplicou — a janela de
  sobreposição é exatamente o que a escrita idempotente cobre;
- throughput observado na borda: ~320 eventos/s com 20 conexões, sem erro.

### Bugs encontrados no caminho

**1. `BatchWriteItem` derrubado por chave repetida.**

A primeira versão quebrava quando o mesmo evento chegava duas vezes no mesmo
lote: o `BatchWriteItem` rejeita a requisição inteira em caso de chave repetida,
e como a idempotência faz duplicata colidir **de propósito**, isso derrubaria
lotes inteiros em produção sempre que o SQS reentregasse. Corrigido com
deduplicação antes do lote (§3.4), com teste de regressão.

**2. `CycleLatency` misturava espera ociosa com trabalho.** Descoberto nas
métricas do deploy real: um ciclo aparecia com 13,7 s. Não era processamento
lento — o cronômetro começava antes do `receive`, e o long polling bloqueia até
20 s esperando mensagem. Num painel isso pareceria latência de 13 s quando o
processamento real levava ~450 ms. Separado em `CycleLatency` (só trabalho:
15–243 ms medidos) e `PollWait` (espera).

---

## 6. Estrutura

```
infra/                      Terraform (nada aplicado)
worker/
  src/argus_worker/
    config.py               configuração por variável de ambiente
    models.py               schemas pydantic dos 6 tipos + fallback genérico
    keys.py                 event_id determinístico e chaves do DynamoDB
    repository.py           BatchWriteItem, retry, deduplicação
    consumer.py             loop SQS, quarentena, delete condicional
    observability.py        logs JSON e métricas EMF
  tests/                    58 testes, fixtures dos 6 eventos reais
  Dockerfile                multi-stage, ARM64, usuário não-root
tools/
  events_csv_to_json.py     export do BI → payload da API
  replay_events.py          replay contra a API publicada
```

---

## 7. Pendências antes de produção

1. **Autenticação na API.** Hoje o endpoint é público, protegido só por
   throttling (500 req/s). Aceitável para POC, não para produção. O HTTP API
   suporta autorizador JWT ou Lambda — decidir qual.
2. **Restringir o CORS.** `api_cors_allow_origins` está em `["*"]`.
3. **Estado remoto do Terraform** antes de mais alguém rodar `apply`.
4. **Pipeline de CD.** Se um pipeline passar a chamar
   `aws ecs update-service --task-definition`, adicionar
   `ignore_changes = [task_definition]` no service — senão os dois brigam pelo
   controle. Hoje está sem, de propósito: o deploy é pelo próprio Terraform.
5. **Autoscaling** por profundidade de fila, se o volume justificar.
6. **`user_id` e headers com dado pessoal.** Os eventos carregam `user_id` e
   headers `authorization` (mascarados como `***` no export, mas confirmar se
   chegam mascarados em produção também). Definir política de retenção e
   anonimização com quem cuida de privacidade — o TTL de 90 dias é um começo,
   não uma política.
