# Arquitetura da Solução — Argus v3

&emsp; Este artefato detalha a arquitetura da plataforma de Monitoração Agêntica no seu
estado atual, batizado internamente de **Argus v3**: o diagrama de implantação dos
componentes na AWS, a descrição de cada nó e como eles se conectam, a justificativa
técnica das decisões de arquitetura e tecnologia adotadas, e o plano de deploy dos
recursos AWS envolvidos. O detalhamento de schema de banco, DDL completo e passo a
passo de migração vive em [`plano-argus-v3.md`](plano-argus-v3.md); este documento
referencia esse material onde apropriado, sem duplicá-lo, e foca no que a rubrica de
arquitetura pede: nós, conexões, justificativa e deploy.

&emsp; O sistema descrito aqui é o resultado de um pivot de escopo em relação ao MVP
original (ver [`mvp-inicial.md`](mvp-inicial.md)): em vez de um coletor próprio de
telemetria de frontend, a solução passou a ser um **consumidor de change data
capture (CDC)** das tabelas já tratadas pelo Argus — o correlator de incidentes já em
produção na Globo — mantendo-as replicadas e atualizadas na infraestrutura do projeto,
e derivando delas as camadas analíticas que alimentam o dashboard. A justificativa
completa dessa mudança de premissa está na seção 3.1.

---

## 1. Diagrama de implantação

&emsp; A Figura 1 mostra o diagrama de implantação do Argus v3, no padrão UML de nós
(estereótipo `«device»` para infraestrutura gerenciada como armazenamento, e
`«execution environment»` para ambientes que executam código próprio) e artefatos de
software (estereótipo `«artifact»`) hospedados dentro de cada nó. As setas indicam
caminhos de comunicação entre nós, rotuladas com o protocolo ou mecanismo usado. O nó
com borda tracejada laranja (`Amazon EventBridge Scheduler`) está marcado como
planejado: aparece no desenho original da arquitetura, mas ainda não existe como
recurso Terraform aplicado — ver a pendência registrada na seção 5.

<div align="center">

<sub>Figura 1 - Diagrama de implantação do Argus v3, com nós, artefatos de software e
caminhos de comunicação, no estado atual do Terraform em `apps/basica/infra/`</sub>

![Diagrama de implantação do Argus v3](assets/arquitetura-implantacao-v3.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; O diagrama é organizado da esquerda para a direita seguindo o fluxo do dado: a
fonte (bucket S3 de origem) alimenta a carga inicial e o simulador; o simulador emite
change events por HTTPS para a camada de ingestão (API Gateway e SQS); dois serviços
ECS consomem essas filas e escrevem no RDS PostgreSQL, o nó central que hospeda as
quatro camadas do desenho medallion (bronze, silver, gold, detect); um serviço de
processamento roda o ETL incremental sobre esse banco; e a camada de consulta (Lambda
mais API Gateway) expõe as views a um dashboard estático servido via S3, acessado pelo
navegador do usuário. Uma faixa transversal na base do diagrama reúne os nós de
operação, segurança e observabilidade, comuns a todos os serviços acima.

---

## 2. Nós e componentes de software

&emsp; Esta seção descreve cada nó do diagrama da Figura 1, os artefatos de software
que ele hospeda, e como eles se conectam aos nós vizinhos.

### 2.1 Fonte e carga inicial

&emsp; **Amazon S3 — bucket `origem/`** (`s3_origem.tf`) é o nó de armazenamento
imutável e versionado da fonte de dados: o dump `argus_dump.sql.gz` e o Parquet
derivado (33 arquivos, um por tabela do Argus, gerados por `tools/etl_dump.py`). É a
partir dele que a carga inicial acontece.

&emsp; **Amazon ECS Fargate — task `loader`** (`ecs_loader.tf`, one-shot, não é um
serviço de longa duração) lê o Parquet do bucket `origem/` e faz `COPY` em lote direto
para a corrente de bronze no RDS, sem passar pela API de ingestão — é um caminho de
carga separado do fluxo de change events, usado uma única vez por ambiente. O loader
valida o total de linhas carregado contra o `_manifest.json` do Parquet e falha alto em
caso de divergência.

### 2.2 Simulação de produção

&emsp; **Amazon ECS Fargate — serviço `simulator`** (`ecs_simulator.tf`) resolve a
ausência de acesso real ao Argus de produção: ele lê a janela de bronze/silver à frente
do relógio virtual (`sim.clock`), aplica um injetor de falhas com seed fixa
(reprodutibilidade), e emite os change events resultantes (`op`/`before`/`after`/`lsn`)
via HTTPS para a API de ingestão. É esse serviço que faz o papel do CDC que, em
produção real, viria de fora.

### 2.3 Ingestão

&emsp; **Amazon API Gateway (HTTP API) `events`** (`apigateway.tf` +
`apigateway_changes.tf`) expõe duas rotas, `POST /v1/changes` e `POST /v1/events`, cada
uma integrada **diretamente** a uma fila SQS via `AWS_PROXY`/`SQS SendMessage` — sem
Lambda no meio. **Amazon SQS** hospeda as duas filas (`changes` e `events`), cada uma
com sua DLQ própria, redirecionando a mensagem após 5 tentativas de entrega.

&emsp; **Amazon ECS Fargate — serviço `merge_worker`** consome a fila `changes` por
long polling, grava em `bronze.change_log` (append-only) e aplica o `MERGE` por `lsn`
na corrente de bronze — só aplica a mudança se o `lsn` recebido for maior que o
corrente, o que torna o consumo idempotente e tolerante a reentrega do SQS. **Amazon
ECS Fargate — serviço `event_worker`** é o segundo consumidor, com a mesma estrutura,
lendo a fila `events` e escrevendo em `bronze.event` (o grain de sessão).

### 2.4 Persistência — Amazon RDS PostgreSQL

&emsp; O nó central do diagrama é a instância **Amazon RDS PostgreSQL 16**
(`db.t3.medium`, 100 GB gp3, `rds.tf`), que hospeda o desenho medallion inteiro dentro
do próprio banco, em vez de espalhar as camadas por serviços gerenciados diferentes:

- **`sim`** — o relógio virtual (`sim.clock`) e a configuração de falhas (`sim.fault`,
  `sim.run`), consultáveis por qualquer processo via `sim.now()`.
- **`bronze`** — `change_log` (append-only, chave `lsn` + `captured_at`, `jsonb`
  genérico) e a corrente tipada das 33 tabelas do Argus mais `bronze.event`.
- **`silver`** — canonicalização de tipo e tempo sobre a bronze, com a coluna
  `available_at` (padrão bitemporal: separa quando o dado ocorreu de quando ficou
  visível).
- **`gold`** — `feature_bucket`, `circadian_state`, `incident_window`,
  `detection_match`, `live_event_window`: as tabelas que o dashboard de fato lê.
- **`detect`** — saída do detector de anomalias, por `run_id`.
- **`etl`** — `watermark_bronze_silver`, `watermark_silver_gold` e `execucoes`: o
  controle do ETL incremental (ver seção 4.4).
- **views `v_*`** — o recorte que todas as leituras usam, filtrando por
  `available_at <= sim.now()` para nunca vazar "futuro" do replay.

### 2.5 Processamento

&emsp; **Amazon ECS Fargate — serviço `processing`** roda, dentro do mesmo container,
duas threads independentes que chamam as funções `etl.executar_bronze_silver()` (a
cada 60 s) e `etl.executar_silver_gold()` (a cada 900 s) por `JDBC/SQL` — cada chamada
é um ciclo atômico, watermark e dado avançando no mesmo commit. O detector de anomalias
(EWMA circadiano) e o canário de qualidade seguem **no-op**: a infraestrutura já está
provisionada e observável, mas a lógica ainda não foi implementada.

### 2.6 Consulta e apresentação

&emsp; **AWS Lambda `read_api`** (`api_read.tf`) consulta as views `v_*` via
`DATABASE_URL` e é exposta por um segundo **Amazon API Gateway (HTTP API) `read`**.
**Amazon S3 — bucket `frontend`** hospeda o dashboard Next.js como website estático
(export puro, sem servidor). O navegador do usuário acessa o bucket diretamente por
HTTPS para o dashboard e o API Gateway de leitura para os dados — não há CloudFront na
frente de nenhum dos dois (ver pendência na seção 6).

### 2.7 Operação, segurança e observabilidade

&emsp; Transversal a todos os nós acima: **Amazon ECR** guarda as imagens de container
de todas as tasks ECS (`loader`, `simulator`, `merge_worker`, `event_worker`,
`processing`); **AWS IAM** define as roles e policies por serviço, com separação entre
execution role e task role; **Amazon CloudWatch** concentra os log groups e um
conjunto de alarmes de métrica (DLQ não vazia, backlog de fila, serviço fora do ar,
5xx da API, CPU/armazenamento/conexões do RDS, `lag_sim` e heartbeat por fonte);
**Amazon SNS** recebe os alarmes do CloudWatch e distribui por e-mail. O **Amazon
EventBridge Scheduler** aparece no desenho original como o mecanismo que dispararia o
processamento e o detector por agendamento, mas ainda não tem recurso Terraform
aplicado — hoje o serviço `processing` roda como um serviço de longa duração com laços
internos, não como uma execução agendada.

---

## 3. Justificativa da arquitetura e das tecnologias

### 3.1 De coletor a consumidor de CDC

&emsp; A arquitetura anterior (documentada em `mvp-inicial.md`) partia da premissa de
que o sistema **produzia** o dado: API Gateway → SQS → worker Fargate → DynamoDB, um
desenho de firehose de ingestão. O entendimento aprofundado com o parceiro derrubou
essa premissa — o Argus já existe em produção na Globo, já tem 33 tabelas com o dado
tratado, da fonte bruta (Prometheus, New Relic, Apollo, RPaaS, Cloud Armor, Tsuru) até
a camada canônica e o ground truth de incidentes. O papel do projeto deixou de ser
coletar telemetria e passou a ser **ler, replicar e manter atualizadas** essas tabelas,
construindo em cima delas as camadas analíticas do dashboard. Essa mudança de natureza
do sistema — de coletor para consumidor de CDC com replay — é a raiz de todas as
demais decisões de arquitetura descritas abaixo.

### 3.2 RDS PostgreSQL com camadas bronze/silver/gold, não DynamoDB single-table

&emsp; O DynamoDB single-table fazia sentido quando o sistema controlava o schema dos
eventos que ele mesmo produzia. Consumindo CDC de 33 tabelas heterogêneas, com colunas
que a Globo pode acrescentar a qualquer momento sem aviso, a exigência mudou: o
armazenamento precisa acomodar mudança de schema **sem migração**. A separação entre
`bronze.change_log` (append-only, `jsonb` genérico, absorve qualquer coluna nova sem
DDL) e a corrente tipada resolve isso — e sustenta uma garantia mais forte, a de que
nenhuma tabela de silver ou gold pode conter informação que não seja derivável do
`change_log`. Enquanto o log estiver íntegro, `TRUNCATE` em silver e gold seguido de
replay reconstrói tudo, o que torna a iteração do ETL barata: mudar uma transformação
custa um rebuild, não uma migração de dado. Essa propriedade não existe de graça em
DynamoDB, e é o motivo direto de adotar um banco relacional com camadas explícitas em
vez de manter o modelo single-table.

### 3.3 Integração direta API Gateway → SQS, sem Lambda intermediária

&emsp; As rotas `POST /v1/changes` e `POST /v1/events` usam integração `AWS_PROXY`
direto para SQS (`SQS SendMessage`), sem uma Lambda de recepção no meio. O simulador é
o único emissor conhecido e o contrato do payload já é o formato interno de change
event — não há transformação nem validação de negócio a fazer na borda que justifique
uma função adicional. Cada Lambda a mais nesse caminho seria custo e mais um ponto de
falha sem ganho de comportamento, então a integração direta do API Gateway com o SQS
foi preferida à alternativa mais comum (API Gateway → Lambda → SQS).

### 3.4 Dois workers, duas filas, sem duplicar a API

&emsp; A escolha de duas filas (`changes` e `events`) e dois serviços ECS consumidores
(`merge_worker` e `event_worker`) em vez de uma fila única com um worker que
decide o destino pelo conteúdo da mensagem separa as duas responsabilidades — mudança
de estado da tabela de origem (`change_log` → corrente) e evento de sessão (`bronze.
event`) — em unidades de deploy e escala independentes, sem acoplar a lógica de
roteamento a um único processo. O custo dessa escolha é infraestrutura duplicada (duas
filas, dois serviços); o ganho é que cada worker pode escalar, falhar e ser reimplantado
sem afetar o outro.

### 3.5 ETL incremental como threads dentro de um único serviço ECS

&emsp; O ETL incremental de bronze→silver (cadência de 60 s) e silver→gold (cadência
de 900 s) roda como duas threads dentro do mesmo container `processing` já
provisionado, em vez de dois serviços ECS novos. A atomicidade de cada ciclo mora no
banco — cada chamada a `etl.executar_*()` é uma única transação SQL, watermark e dado
avançando juntos — então threads bastam para orquestrar a cadência, e evitam Terraform
novo (task definition, log group, alarme de `RunningTaskCount`) para algo que não
precisa de isolamento de processo. Essa decisão trouxe consigo uma regra de guarda
descoberta durante a implementação: se a janela máxima do ciclo silver→gold não for
estritamente maior que a margem de segurança de reabertura, o watermark não trava —
**regride** a cada chamada, porque a margem é subtraída nas duas pontas do ciclo.
`etl.executar_silver_gold()` hoje falha alto (`RAISE EXCEPTION`) nessa condição.

### 3.6 Lambda para leitura, ECS Fargate para os workers

&emsp; A camada de leitura (`read_api`) roda em Lambda, enquanto ingestão,
processamento e simulação rodam em ECS Fargate. A diferença de perfil de carga
justifica a diferença de tecnologia: leitura de dashboard é *bursty* e correlacionada
ao uso humano, um encaixe natural para o modelo de invocação sob demanda da Lambda. Os
workers de ingestão e o ETL, por outro lado, mantêm conexão de pool com o RDS e um
ciclo de vida contínuo (long polling, laços com cadência fixa) — cold start de Lambda
e o limite de conexões simultâneas ao banco tornariam esse padrão caro e frágil em
Lambda. Fargate também foi a escolha original do worker de ingestão desde o MVP
anterior, motivada pela sazonalidade forte do tráfego da Globo (picos em eventos ao
vivo, shows e ofertas) — um padrão que Lambda, com limite de concorrência por conta,
atenderia pior que containers de vida longa com auto scaling próprio.

### 3.7 Decisões de infraestrutura

&emsp; **Rede.** O RDS é publicamente acessível por padrão de ambiente de laboratório
(`var.db_publicly_accessible`, default `false`, ligado via `tfvars` do Learner Lab),
com ingress na porta 5432 restrito a um CIDR configurável — nunca `0.0.0.0/0`. A
alternativa de produção (RDS privado, Lambda dentro da VPC) fica documentada como a
postura correta, mas custa cold start de ENI na Lambda e impede inspecionar o banco sem
bastion — um custo que não se justifica em ambiente de desenvolvimento/laboratório.

&emsp; **Senha.** Dois modos: por padrão, `aws_secretsmanager_secret` com senha
gerada por `random_password`; se o Secrets Manager for negado pelo ambiente de
laboratório, cai para uma senha de `tfvars` (gitignored, marcada `sensitive`). Em
nenhum caminho a senha entra em arquivo versionado.

&emsp; **Dimensionamento da instância.** `db.t3.medium` com 100 GB gp3 foi dimensionado
para a bronze (~13 GB) e a silver (~6 GB, `signal_point` duplicado), considerando que
o PostgreSQL não comprime heap — os 199 MB de Parquet de origem expandem para cerca de
2,1 GB de dados mais 1,2 GB de índice só em `prom_point`. O ponto que sustenta essa
escolha de instância sem virar gargalo é o mesmo da seção 3.2: as telas do dashboard
nunca leem bronze, só `gold.v_*`, o que desacopla o desempenho percebido do tamanho da
camada bruta.

&emsp; **Proteção contra destruição.** `deletion_protection` e `skip_final_snapshot`
seguem `var.environment == "prod"`. Em laboratório, `skip_final_snapshot = true` — um
snapshot final de uma conta que vai deixar de existir é custo sem valor.

---

## 4. Plano de deploy detalhado com recursos AWS

### 4.1 Inventário de mudanças no Terraform (`apps/basica/infra/`)

&emsp; A tabela a seguir resume o que foi removido, criado e modificado em relação à
arquitetura anterior (DynamoDB), servindo de checklist do que o `terraform plan`
precisa mostrar.

**Removido**

| Arquivo | Motivo |
|---|---|
| `dynamodb.tf` | Toda a persistência migrou para o RDS PostgreSQL (seção 3.2) |

**Novo**

| Arquivo | Conteúdo |
|---|---|
| `rds.tf` | Subnet group, parameter group, security group, `aws_db_instance`, gestão de senha |
| `s3_origem.tf` | Bucket `origem/` com versionamento, para o dump e o Parquet imutáveis |
| `sqs_changes.tf` | Fila de change events e DLQ, espelhando `sqs.tf` |
| `apigateway_changes.tf` | Rota `POST /v1/changes` → SQS, integração direta sem Lambda |
| `ecs_simulator.tf` | Serviço do simulador (relógio, falhas com seed fixa, emissor) |
| `ecs_processing.tf` | Serviço do worker de processamento (ETL incremental; detector/canário no-op) |
| `ecs_loader.tf` | Task definition one-shot da carga inicial |

**Modificado**

| Arquivo | Mudança |
|---|---|
| `ecs.tf` | Workers de merge e evento passam a falar PostgreSQL (`DATABASE_URL` no lugar de `EVENTS_TABLE_NAME`); egress 5432 liberado para o security group do RDS |
| `api_read.tf` | Lambda passa a ler as views (`DATABASE_URL` no lugar de `GSI1_SHARDS`) |
| `iam.tf` | Sai `dynamodb:*`; entram `secretsmanager:GetSecretValue` e `s3:GetObject` restrito a `origem/` |
| `observability.tf` | Sai o alarme de throttle do DynamoDB; entram alarmes de CPU, armazenamento e conexões do RDS, `lag_sim` e heartbeat por fonte |
| `variables.tf`, `locals.tf`, `outputs.tf` | Bloco de variáveis do DynamoDB sai, entra o do RDS; outputs passam a expor o endpoint do RDS e a URL de `/v1/changes` |

### 4.2 Carga inicial

&emsp; A carga inicial segue a cadeia `argus_dump.sql.gz` (fonte de verdade) →
`tools/etl_dump.py` → Parquet (199 MB, 33 tabelas, formato de transporte) → `aws s3
sync` para `s3://<nome>-origem-<conta>/parquet/` → task ECS `loader` (one-shot), que lê
os arquivos em batches via `pyarrow` e faz `COPY ... FROM STDIN` na corrente de bronze,
gravando também `change_log` com `op = 'r'` (snapshot). Os requisitos não negociáveis
dessa carga são: `COPY` por lote, nunca `INSERT` linha a linha; índices criados
**depois** da carga de cada tabela; `ANALYZE` ao final; e validação obrigatória contra
o `row_counts` do `_manifest.json` — divergência é falha, não aviso. O alvo de tempo é
20 a 30 minutos para as 68,7 milhões de linhas, dimensionado para caber com folga numa
sessão do Learner Lab.

### 4.3 Ordem de execução

| # | Passo |
|---|---|
| 1 | Migrations do schema (001 a 015) escritas e validadas contra PostgreSQL 16 local (Docker) |
| 2 | `tools/migrate.py` aplica as migrations no ambiente alvo |
| 3 | Terraform: `rds.tf` e `s3_origem.tf` primeiro, com `terraform plan` isolado |
| 4 | Terraform: remoção do DynamoDB e ajuste de `iam.tf` / `observability.tf` / `api_read.tf` |
| 5 | Loader e carga inicial; validação contra `_manifest.json` |
| 6 | Serviços `merge_worker` e `event_worker` |
| 7 | Serviço `simulator` |
| 8 | Serviço `processing` (ETL incremental) |
| 9 | Lambda de leitura sobre as views |

&emsp; Os passos 1 e 2 são pré-condição para todo o resto. Os blocos 3–4 (Terraform de
persistência) e a preparação do Parquet para o passo 5 são independentes entre si e
podem ser tocados em paralelo por pessoas diferentes.

### 4.4 Verificação pós-deploy

&emsp; Antes de considerar o deploy concluído, quatro verificações fecham o ciclo:
(1) `sim.now()` avança sozinho e as views ignoram linhas com `available_at` no futuro
do relógio virtual; (2) o rebuild funciona — truncar silver e gold e reprocessar o
`change_log` reproduz as mesmas contagens, a propriedade que sustenta a decisão da
seção 3.2; (3) `terraform plan` não mostra nenhuma destruição fora do escopo esperado
(DynamoDB e IAM associado); (4) um change event sintético enviado a `POST /v1/changes`
aparece em `bronze.change_log`, é mesclado na corrente, processado pelo ETL, e só fica
visível em `gold.v_*` quando `sim.now()` ultrapassa o `available_at` do registro.

---

## 5. Riscos e pendências conhecidas

| Risco / pendência | Situação |
|---|---|
| CloudFront aparece no desenho original da arquitetura, mas não foi implementado | O bucket S3 do frontend atende como website estático; CloudFront fica registrado como melhoria futura, não bloqueia o uso atual |
| Amazon EventBridge Scheduler não tem recurso Terraform aplicado | O serviço `processing` roda como serviço de longa duração com laços internos, não como execução agendada; ver seção 2.7 |
| `build_*`/`gold.rebuild_tudo()` não propagam `DELETE` de bronze para silver/gold | Limitação conhecida e não corrigida — os dois só fazem upsert; pré-existente à introdução do ETL incremental |
| Classe de instância do RDS pode ser negada ou limitada pelo Learner Lab | Confirmar com `aws rds describe-orderable-db-instance-options` assim que o laboratório subir; plano B é `db.t3.small`/`micro`, sustentável porque as telas só leem `gold.v_*` |
| Detector de anomalias (EWMA circadiano) e canário de qualidade | Seguem no-op; infraestrutura provisionada e observável para quando a lógica for implementada |

---

## 6. Conclusão

&emsp; A arquitetura descrita neste artefato reflete um sistema que já saiu do papel: o
pivot de DynamoDB para RDS PostgreSQL com camadas bronze/silver/gold, o simulador de
produção com relógio virtual, e o ETL incremental por watermarks estão implementados e
mergeados em `develop`, com suíte de testes própria (worker, simulador, processamento e
backend) e `make lint` passando. As pendências registradas na seção 5 — CloudFront, o
EventBridge Scheduler e a propagação de `DELETE` — não bloqueiam o funcionamento atual
do pipeline, mas ficam como próximos passos explícitos para a evolução do projeto junto
ao parceiro Globo.
