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
