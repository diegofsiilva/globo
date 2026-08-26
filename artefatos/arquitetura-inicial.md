# Arquitetura do Argus v3

&emsp; Este artefato reúne, em um único documento, a arquitetura da plataforma de
Monitoração Agêntica no seu estado atual, batizado internamente de **Argus v3**. Ele
consolida o que antes estava dividido entre um artefato de arquitetura resumido e o
plano técnico completo da migração (o antigo `plano-argus-v3.md`, hoje incorporado a
este documento): o porquê da mudança de arquitetura, o diagrama de implantação dos
componentes na AWS, a descrição de cada nó e como eles se conectam, o desenho completo
do banco de dados, a justificativa técnica das decisões de arquitetura e tecnologia
adotadas, o desenho do ETL incremental, o plano de deploy dos recursos AWS, e o
registro de riscos e da proveniência de cada decisão.

&emsp; O sistema descrito aqui é o resultado de um pivot de escopo em relação ao MVP
original (ver [`mvp-inicial.md`](mvp-inicial.md)): em vez de um coletor próprio de
telemetria de frontend, a solução passou a ser um **consumidor de change data capture
(CDC)** das tabelas já tratadas pelo Argus, o correlator de incidentes já em produção
na Globo, mantendo-as replicadas e atualizadas na infraestrutura do projeto, e
derivando delas as camadas analíticas que alimentam o dashboard. A seção 1 detalha essa
mudança de premissa.

---

## 1. Por que a arquitetura mudou

&emsp; A arquitetura anterior (documentada em [`mvp-inicial.md`](mvp-inicial.md)) foi
desenhada para um firehose de telemetria: API Gateway, SQS, worker Fargate, DynamoDB,
com Lambda de leitura por cima. Ela funcionava e chegou a ir ao ar. Mas partia de uma
premissa que o entendimento aprofundado com o parceiro derrubou: a de que o sistema
**produz** o dado.

&emsp; Na prática, o Argus já existe em produção na Globo e já tem 33 tabelas com o
dado tratado, desde fonte bruta (Prometheus, New Relic, Apollo, RPaaS, Cloud Armor,
Tsuru) até camada canônica (`signal_point`, `signal_bucket`), ground truth
(`incidents`, `incident_label`) e saída do sistema atual (`dashboard_artifact`). O que
o projeto precisa fazer é **ler dessas tabelas**, replicá-las na infraestrutura do
grupo, e construir em paralelo um esquema que simule como o fluxo funcionaria em
produção, mantendo essas tabelas atualizadas ao longo do tempo.

&emsp; Isso muda a natureza do sistema: ele deixa de ser um coletor e passa a ser um
**consumidor de change data capture com replay**, que recebe as mudanças que a origem
publica, materializa o estado corrente, e deriva as camadas analíticas a partir disso.

### 1.1 As sete decisões que orientam a arquitetura

| # | Decisão | Consequência |
|---|---|---|
| 1 | Substituir o DynamoDB por completo | `dynamodb.tf` sai; toda a persistência vira PostgreSQL |
| 2 | Carregar as 33 tabelas inteiras, incluindo `prom_point` | 68,7 milhões de linhas; justificativa na seção 1.2 |
| 3 | Dois fluxos de ingestão | CDC das tabelas já mapeadas e eventos de grain de sessão, que chegam por outro fluxo do Argus |
| 4 | Bronze otimizada para mudar, não para performance | O ETL ainda está em aprimoramento; o custo de errar precisa ser baixo |
| 5 | Carga inicial via Parquet | `tools/etl_dump.py` converte o dump e gera os 33 arquivos (199 MB) |
| 6 | Não renormalizar `signal_point` | A silver faz canonicalização de tipo e tempo, não normalização multifonte |
| 7 | Detecção segue embrionária; ETL deixou de ser no-op | O worker de processamento roda o ETL incremental (seção 7); detector e canário seguem no-op, com infraestrutura provisionada e observável para quando chegarem |

### 1.2 Por que `prom_point` entra, apesar de ser 60% das linhas

&emsp; `prom_point` é a tabela-fato do Prometheus, com 41,2 milhões das 68,7 milhões
de linhas do dump. É camada de fonte bruta, e o `signal_bucket` já traz o Prometheus
normalizado, então a tentação de deixá-la de fora é real. Três telas do dashboard não
fecham sem ela:

- **Timeline**: "CDN, Prometheus VTS" é uma das seis raias nomeadas do eixo de tempo,
  e a cronologia reconstruída tem entradas que são fatos do Prometheus (por exemplo,
  "p95 na borda do PoP Fortaleza sobe de 368 ms para 412 ms"). O painel lateral conta
  "fontes com desvio: 3 de 13", as 13 fontes do vocabulário do dataset.
- **Hipóteses**: o fator de score "ausência de causa concorrente" afirma que CDN,
  Globo-ID e backend não desviaram na janela. Provar ausência exige a série inteira,
  não só os pontos anômalos; o motor de descarte consome mais dado bruto que o de
  detecção, e é ele que separa 4 hipóteses de 11 descartadas.
- **Comparar**: "p95 de borda 412 ms vs 368 ms, +12%, 1,2σ". O σ vem da distribuição
  histórica da série.

&emsp; O argumento decisivo é de granularidade. O gráfico da tela Comparar declara
"bucket de 1 min", e a Timeline resolve eventos em 19:58, 20:00, 20:02, 20:04, 20:06 e
20:07. O `signal_bucket` é de 15 minutos, o que colapsaria a janela de correlação
inteira em um único ponto; só o `prom_point` tem cadência de 1 minuto. Soma-se que
`prom_series.labels_json` traz `pop` em claro (é de lá que sai "PoP Fortaleza") e
`prom_query.section` dá o agrupamento das raias, e que as fontes NPAW têm cerca de 28 h
de latência estrutural: para uma tela marcada ao vivo, o sinal de infraestrutura
quase-real-time é Prometheus (1 min) e `rpaas_bucket` (15 min).

---

## 2. Diagrama de implantação

&emsp; A Figura 1 mostra o diagrama de implantação do Argus v3, no padrão UML de nós
(estereótipo `«device»` para infraestrutura gerenciada como armazenamento, e
`«execution environment»` para ambientes que executam código próprio) e artefatos de
software (estereótipo `«artifact»`) hospedados dentro de cada nó. As setas indicam
caminhos de comunicação entre nós, rotuladas com o protocolo ou mecanismo usado. O nó
com borda tracejada laranja (`Amazon EventBridge Scheduler`) está marcado como
planejado: aparece no desenho original da arquitetura, mas ainda não existe como
recurso Terraform aplicado; ver a pendência registrada na seção 9.

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

## 3. Nós e componentes de software

&emsp; Esta seção descreve cada nó do diagrama da Figura 1, os artefatos de software
que ele hospeda, e como se conecta aos nós vizinhos.

### 3.1 Fonte e carga inicial

&emsp; **Amazon S3, bucket `origem/`** (`s3_origem.tf`) é o nó de armazenamento
imutável e versionado da fonte de dados: o dump `argus_dump.sql.gz` e o Parquet
derivado (33 arquivos, um por tabela do Argus, gerados por `tools/etl_dump.py`). É a
partir dele que a carga inicial acontece.

&emsp; **Amazon ECS Fargate, task `loader`** (`ecs_loader.tf`, one-shot, não é um
serviço de longa duração) lê o Parquet do bucket `origem/` e faz `COPY` em lote direto
para a corrente de bronze no RDS, sem passar pela API de ingestão: é um caminho de
carga separado do fluxo de change events, usado uma única vez por ambiente. O loader
valida o total de linhas carregado contra o `_manifest.json` do Parquet e falha alto em
caso de divergência.

### 3.2 Simulação de produção

&emsp; **Amazon ECS Fargate, serviço `simulator`** (`ecs_simulator.tf`) resolve a
ausência de acesso real ao Argus de produção: ele lê a janela de bronze/silver à frente
do relógio virtual (`sim.clock`), aplica um injetor de falhas com seed fixa
(reprodutibilidade), e emite os change events resultantes (`op`/`before`/`after`/`lsn`)
via HTTPS para a API de ingestão. É esse serviço que faz o papel do CDC que, em
produção real, viria de fora.

### 3.3 Ingestão

&emsp; **Amazon API Gateway (HTTP API) `events`** (`apigateway.tf` mais
`apigateway_changes.tf`) expõe duas rotas, `POST /v1/changes` e `POST /v1/events`, cada
uma integrada diretamente a uma fila SQS via `AWS_PROXY`/`SQS SendMessage`, sem Lambda
no meio. **Amazon SQS** hospeda as duas filas (`changes` e `events`), cada uma com sua
DLQ própria, redirecionando a mensagem após 5 tentativas de entrega.

&emsp; **Amazon ECS Fargate, serviço `merge_worker`** consome a fila `changes` por
long polling, grava em `bronze.change_log` (append-only) e aplica o `MERGE` por `lsn`
na corrente de bronze, só aplicando a mudança se o `lsn` recebido for maior que o
corrente, o que torna o consumo idempotente e tolerante a reentrega do SQS. **Amazon
ECS Fargate, serviço `event_worker`** é o segundo consumidor, com a mesma estrutura,
lendo a fila `events` e escrevendo em `bronze.event` (o grain de sessão).

### 3.4 Persistência em Amazon RDS PostgreSQL

&emsp; O nó central do diagrama é a instância **Amazon RDS PostgreSQL 16**
(`db.t3.medium`, 100 GB gp3, `rds.tf`), que hospeda o desenho medallion inteiro dentro
do próprio banco, em vez de espalhar as camadas por serviços gerenciados diferentes:

- **`sim`**: o relógio virtual (`sim.clock`) e a configuração de falhas (`sim.fault`,
  `sim.run`), consultáveis por qualquer processo via `sim.now()`.
- **`bronze`**: `change_log` (append-only, chave `lsn` mais `captured_at`, `jsonb`
  genérico) e a corrente tipada das 33 tabelas do Argus mais `bronze.event`.
- **`silver`**: canonicalização de tipo e tempo sobre a bronze, com a coluna
  `available_at` (padrão bitemporal, que separa quando o dado ocorreu de quando ficou
  visível).
- **`gold`**: `feature_bucket`, `circadian_state`, `incident_window`,
  `detection_match`, `live_event_window`, as tabelas que o dashboard de fato lê.
- **`detect`**: saída do detector de anomalias, por `run_id`.
- **`etl`**: `watermark_bronze_silver`, `watermark_silver_gold` e `execucoes`, o
  controle do ETL incremental (seção 7).
- **views `v_*`**: o recorte que todas as leituras usam, filtrando por
  `available_at <= sim.now()` para nunca vazar "futuro" do replay.

&emsp; O desenho completo de cada schema, com o DDL relevante, está na seção 5; o
raciocínio que sustenta separar log e corrente está na seção 4.

### 3.5 Processamento

&emsp; **Amazon ECS Fargate, serviço `processing`** roda, dentro do mesmo container,
duas threads independentes que chamam as funções `etl.executar_bronze_silver()` (a
cada 60 s) e `etl.executar_silver_gold()` (a cada 900 s) por `JDBC/SQL`, cada chamada
sendo um ciclo atômico, com watermark e dado avançando no mesmo commit. O detector de
anomalias (EWMA circadiano) e o canário de qualidade seguem no-op: a infraestrutura já
está provisionada e observável, mas a lógica ainda não foi implementada. O desenho
completo do ETL incremental está na seção 7.

### 3.6 Consulta e apresentação

&emsp; **AWS Lambda `read_api`** (`api_read.tf`) consulta as views `v_*` via
`DATABASE_URL` e é exposta por um segundo **Amazon API Gateway (HTTP API) `read`**.
**Amazon S3, bucket `frontend`** hospeda o dashboard Next.js como website estático
(export puro, sem servidor). O navegador do usuário acessa o bucket diretamente por
HTTPS para o dashboard e o API Gateway de leitura para os dados; não há CloudFront na
frente de nenhum dos dois (ver pendência na seção 9).

### 3.7 Operação, segurança e observabilidade

&emsp; Transversal a todos os nós acima: **Amazon ECR** guarda as imagens de container
de todas as tasks ECS (`loader`, `simulator`, `merge_worker`, `event_worker`,
`processing`); **AWS IAM** define as roles e policies por serviço, com separação entre
execution role e task role; **Amazon CloudWatch** concentra os log groups e um
conjunto de alarmes de métrica (DLQ não vazia, backlog de fila, serviço fora do ar,
5xx da API, CPU, armazenamento e conexões do RDS, `lag_sim` e heartbeat por fonte);
**Amazon SNS** recebe os alarmes do CloudWatch e distribui por e-mail. O **Amazon
EventBridge Scheduler** aparece no desenho original como o mecanismo que dispararia o
processamento e o detector por agendamento, mas ainda não tem recurso Terraform
aplicado: hoje o serviço `processing` roda como um serviço de longa duração com laços
internos, não como uma execução agendada.

---

## 4. O princípio que sustenta a arquitetura de camadas

&emsp; A bronze precisa acomodar a Globo acrescentar uma coluna nova ao longo do
tempo, sem que isso vire migração. Isso é resolvido pela separação entre log e
corrente: o `bronze.change_log` guarda `jsonb` genérico, que absorve qualquer coluna
nova sem DDL; a partir dele, um `MERGE` por `lsn` popula a corrente (tipada), que
alimenta a silver, que alimenta a gold. Enquanto o log estiver íntegro, `TRUNCATE` em
silver e gold seguido de replay reconstrói tudo. É isso que torna a iteração do ETL
barata: mudar uma transformação não custa migração de dado, custa um rebuild.

> **Requisito de projeto.** Nenhuma tabela de silver ou gold pode conter informação
> que não seja derivável do `change_log`. Se precisar, ela vira uma coluna do log.

&emsp; Dois corolários importantes decorrem disso:

1. **As telas nunca consultam bronze.** Elas leem `gold.v_*`. Isso desacopla o
   desempenho do dashboard do tamanho do `prom_point`, e é o que faz a classe da
   instância RDS deixar de ser um bloqueio de projeto.
2. **A bronze corrente é tipada, com escape.** Cada tabela tem as colunas conhecidas
   tipadas mais um `_extra jsonb`. Coluna nova cai no `_extra` sem DDL, e vira promoção
   explícita a coluna real quando estabilizar. É o desenho que dá plano de execução
   bom para as telas ao vivo e custo zero para absorver mudança de schema.
