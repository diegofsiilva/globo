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

---

## 5. Schemas do banco

&emsp; As migrations vivem em `apps/basica/db/migrations/`, aplicadas por
`tools/migrate.py` (um runner mínimo com `psycopg`, com controle em
`public.schema_migrations`). O Terraform não cria schema: provisiona a instância e
para aí. Separar as duas coisas é o que permite iterar o DDL sem `terraform apply`.

```
001_schemas_e_extensoes.sql
002_sim_relogio_e_falhas.sql
003_bronze_change_log.sql
004_bronze_corrente_argus.sql      (33 tabelas, geradas)
005_bronze_event.sql               (grain de sessão)
006_silver.sql
007_gold.sql
008_detect.sql
009_views_v.sql
010_merge_e_etl.sql                (funções de MERGE e de build das camadas)
011_poda_de_particao_nas_views.sql (ensina o planner a ignorar o futuro)
012_indice_de_observabilidade.sql  (lag_sim sem varrer o change_log)
013_relogio_pausavel.sql           (run pausado congela sim.now())
014_catalogo_de_fontes.sql         (/sources sem agregar 4,9 milhões de buckets)
015_etl_incremental.sql            (watermarks e os dois workers de ETL)
```

&emsp; As migrations `010` a `015` apareceram na implementação e na validação contra a
carga real, não no planejamento original. O `MERGE` do change log e o `build_*` de
cada camada precisavam existir como função no banco, e não como SQL montado em Python,
por duas razões: o loader e o merge worker aplicam a mesma regra de idempotência (só
sobrescreve quando o `_lsn` que chega é maior que o corrente), e duas cópias dela
divergiriam; além disso, `gold.rebuild_tudo()` precisa ser chamável de um `psql`
avulso, sem subir aplicação nenhuma. As migrations `011` e `012` corrigem planos de
execução medidos já com 68,7 milhões de linhas; a `013` torna a pausa do run e do
relógio atômica; a `014` substitui a agregação de 47,4 s de `/sources` por um catálogo
derivado pequeno; e a `015` implementa a ETL incremental por watermark que a seção 7
documenta. Até ali, o único caminho para popular silver/gold era
`gold.rebuild_tudo()`, que varre as tabelas de origem inteiras a cada chamada.

### 5.1 `sim`, o relógio virtual

&emsp; Define "o presente" para todo o resto do sistema, numa linha só, travada por
`CHECK`.

```sql
CREATE TABLE sim.clock (
  id          smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  sim_now     timestamptz NOT NULL,
  speed       numeric     NOT NULL DEFAULT 1.0,  -- 1.0 = tempo real; 60 = 1 min/s
  anchor_wall timestamptz NOT NULL,              -- relógio de parede no último set
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Deriva o instante virtual do relógio de parede: não precisa de tick.
CREATE FUNCTION sim.now() RETURNS timestamptz LANGUAGE sql STABLE AS $$
  SELECT sim_now + (now() - anchor_wall) * speed FROM sim.clock WHERE id = 1;
$$;

CREATE TABLE sim.run (
  run_id     bigserial PRIMARY KEY,
  seed       bigint      NOT NULL,   -- injeção de falhas determinística
  t0         timestamptz NOT NULL,
  t1         timestamptz NOT NULL,
  speed      numeric     NOT NULL,
  status     text        NOT NULL,   -- pending | running | paused | done
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sim.fault (
  fault_id bigserial PRIMARY KEY,
  run_id   bigint REFERENCES sim.run,
  kind     text  NOT NULL,   -- error_spike | latency | source_outage | ...
  target   jsonb NOT NULL,   -- {source, entity, metric} ou {device_model, uf}
  ts_start timestamptz NOT NULL,
  ts_end   timestamptz NOT NULL,
  params   jsonb NOT NULL DEFAULT '{}'
);
```

&emsp; `sim.now()` é `STABLE`, não `IMMUTABLE`: o planner pode avaliá-la uma vez por
statement, mas não pode cachear o resultado entre statements. Marcar como `IMMUTABLE`
congelaria o relógio dentro de uma view. A `seed` em `sim.run` é o que torna a
injeção de falhas reprodutível: duas execuções com a mesma seed produzem a mesma
sequência de falhas, o que permite comparar dois detectores sobre exatamente o mesmo
cenário.

### 5.2 `bronze.change_log`, o log append-only

&emsp; Genérico de propósito: cobre as 33 tabelas com schemas diferentes e absorve
coluna nova sem DDL.

```sql
CREATE TABLE bronze.change_log (
  lsn          bigserial   NOT NULL,
  source_table text        NOT NULL,
  op           char(1)     NOT NULL CHECK (op IN ('i','u','d','r')),  -- r = snapshot
  pk           jsonb       NOT NULL,
  before       jsonb,
  after        jsonb,
  captured_at  timestamptz NOT NULL,   -- quando a origem observou a mudança
  received_at  timestamptz NOT NULL DEFAULT now(),
  run_id       bigint,
  PRIMARY KEY (lsn)
) PARTITION BY RANGE (lsn);
```

&emsp; Partições de 10 milhões em `lsn`, mais uma `DEFAULT`. Índice em
`(source_table, lsn)` para o replay por tabela. Não há índice em `after`: o log é
escrito e relido em ordem, nunca consultado ad-hoc, então indexar `jsonb` aqui custaria
escrita sem comprar leitura. A distinção entre `captured_at` e `received_at` é o que
permite medir o `lag_sim`: quanto tempo virtual o pipeline está atrasado em relação à
origem.

### 5.3 `bronze` corrente, as 33 tabelas do Argus

&emsp; Geradas a partir de `data/parquet/_schema.json`, que já tem coluna e tipo das
33 tabelas. Um gerador (`tools/gen_ddl.py`) monta o DDL em vez de escrever as 33 à
mão, reaproveitando o mapa MySQL para Arrow que já existe em `tools/etl_dump.py`
(`ARROW_TYPE`), já que MySQL para PostgreSQL é o mesmo exercício.

&emsp; O padrão, com `signal_bucket` de exemplo:

```sql
CREATE TABLE bronze.signal_bucket (
  bts          bigint  NOT NULL,
  source       text    NOT NULL,
  entity       text    NOT NULL,
  metric       text    NOT NULL,
  value        double precision,
  _extra       jsonb   NOT NULL DEFAULT '{}',  -- coluna nova cai aqui, sem DDL
  _lsn         bigint  NOT NULL,
  _op          char(1) NOT NULL,
  _captured_at timestamptz NOT NULL,
  PRIMARY KEY (bts, source, entity, metric)
);
```

&emsp; A chave primária é a identidade natural documentada no dataset, o que torna o
`MERGE` idempotente sem precisar de coluna de controle extra.

&emsp; **Atenção ao nome da coluna de tempo.** Não existe um `ts` universal: cada
tabela herdou o nome da sua fonte (`ts`, `bts`, `hour_ts`, `bucket_ts`,
`bucket_ts_ms`, `epoch_ms`, `ts_ms`, `timestamp`, `start_ts`, `start_time_ms`,
`opened_at`, `ts_start`). O gerador lê isso do `_schema.json`; nada no código pode
assumir `ts`.

&emsp; **Particionadas por RANGE** (`bigint` epoch_ms, diária, com partição
`DEFAULT`):

| Tabela | Linhas |
|---|---|
| `prom_point` | 41.191.820 |
| `signal_point` | 18.218.743 |
| `signal_bucket` | 4.936.530 |
| `ca_point` | 1.399.048 |
| `device_hourly` | 933.436 |
| `operation_metrics` | 788.556 |

&emsp; As outras 27 são pequenas o bastante para tabela simples.

> **Nulos conhecidos.** Em `rpaas_bucket`, as colunas `p50_ms`, `p90_ms`, `p95_ms`,
> `p99_ms` e `latency_samples` vêm 100% nulas nas 52.560 linhas, o que apaga o sinal
> que separaria "borda lenta" de "borda falhando". As colunas foram mantidas e o fato
> registrado em `COMMENT ON COLUMN`, para que ninguém redescubra isso na análise.

### 5.4 `bronze.event`, o grain de sessão

&emsp; O segundo fluxo de ingestão. Envelope comum tipado (é por ele que as telas
Explorar e Recorte filtram), com campos específicos do tipo em `payload`.

```sql
CREATE TABLE bronze.event (
  event_id            text        NOT NULL,
  ts                  timestamptz NOT NULL,
  event_name          text        NOT NULL,  -- request | screen_view | session
                                             -- video_view | vitals | error
  session_id          text        NOT NULL,
  device_id           text,
  user_id             text,
  app_bucket          text,
  app_env             text,
  app_target          text,
  app_version         text,
  device_manufacturer text,
  device_model        text,
  device_model_year   integer,
  device_os           text,
  device_os_version   text,
  route_path          text,
  route_params        jsonb,
  duration            double precision,
  payload             jsonb NOT NULL DEFAULT '{}',  -- request_*, media_*,
                                                    -- error_*, capabilities_*
  _lsn                bigint NOT NULL,
  _captured_at        timestamptz NOT NULL,
  PRIMARY KEY (ts, event_id)
) PARTITION BY RANGE (ts);
```

&emsp; O envelope sai do schema real dos exports do BI e dos modelos Pydantic que já
existem em `apps/basica/worker/src/argus_worker/models.py`. Reusar `EVENT_TYPES` e o
fallback `GenericEvent`, que já resolve `event_name` desconhecido, é o mecanismo que
sustenta o requisito de suportar o parque de TVs que atualiza devagar: schema estrito
viraria perda de dado em massa. `tools/events_csv_to_json.py` faz a ponte de CSV para
JSON, incluindo a correção de timezone (o BI renderiza em BRT sem indicar) e o typo
`Dobly` para `Dolby` do fornecedor.

> **Item em aberto, não bloqueante.** As telas Explorar e Recorte filtram por UF e
> ISP, e o schema dos seis eventos não tem nenhum dos dois; o `request` carrega apenas
> `x-country-code: BR`. Ou o outro fluxo do Argus traz esses campos, ou vira
> enriquecimento na silver. Fica para resolver com o parceiro quando o fluxo for
> especificado; o `payload jsonb` acomoda os campos sem migração quando aparecerem.

### 5.5 `silver`, canonicalização e `available_at`

&emsp; Sem renormalização (decisão 6 da seção 1.1): `signal_point` e `signal_bucket`
chegam prontos da origem e são consumidos como vêm; o `build_signal_db.py` original não
é reimplementado. O que a silver faz é quatro coisas:

1. Converte `bigint` epoch_ms para `timestamptz`. Todo timestamp do dataset é
   milissegundo UTC, não segundo, não ISO, não horário de Brasília.
2. Converte as exceções em texto ISO-8601 para `timestamptz`: `signal_meta.
   last_run_at`, `cdn_entity_tier.updated_at`, `investigation_feedback.
   investigated_at` e as colunas das tabelas `*_run` legadas.
3. Converte `tags text` para `jsonb`, tolerando falha de parse: é JSON na maioria das
   fontes, mas a string literal `"live"` aparece em `youbora_player_live`, e `NULL`
   em várias outras.
4. Carimba `available_at`, o que faz o replay ser honesto.

```sql
CREATE TABLE silver.source_latency (
  source    text PRIMARY KEY,
  latency   interval NOT NULL,
  rationale text
);
-- youbora_* / npaw : 28h    latência estrutural do batch BigQuery
-- newrelic         : 5min ou 1h, granularidade mista
-- prometheus       : 1min
-- default          : 0

CREATE TABLE silver.signal_point (
  ts           timestamptz NOT NULL,
  source       text NOT NULL,
  entity       text NOT NULL,
  metric       text NOT NULL,
  value        double precision,
  tags         jsonb,
  available_at timestamptz NOT NULL,   -- ts + source_latency
  _lsn         bigint NOT NULL,
  PRIMARY KEY (ts, source, entity, metric)
) PARTITION BY RANGE (ts);

CREATE TABLE silver.session_event ( ... );  -- mesmo tratamento sobre bronze.event
```

&emsp; `available_at` é o que impede vazamento de futuro: uma métrica NPAW das 21 h só
fica visível à 01 h do dia seguinte, exatamente como em produção. Sem isso, qualquer
detector "acerta" usando dado que ele não teria em tempo real, e o resultado da
avaliação vira ficção.

### 5.6 `gold`, features e janelas

```sql
CREATE TABLE gold.feature_bucket (
  bucket_ts    timestamptz NOT NULL,   -- 15 min, alinhado ao signal_bucket
  source       text NOT NULL,
  entity       text NOT NULL,
  metric       text NOT NULL,
  value        double precision,
  hora_brt     smallint NOT NULL,      -- para modelar o ciclo circadiano
  dow          smallint NOT NULL,      -- para modelar o ciclo semanal
  tem_jogo     boolean  NOT NULL DEFAULT false,   -- feature exógena
  available_at timestamptz NOT NULL,
  PRIMARY KEY (bucket_ts, source, entity, metric)
) PARTITION BY RANGE (bucket_ts);

CREATE TABLE gold.circadian_state (    -- estado EWMA do baseline, estritamente causal
  series_key text NOT NULL,
  hora_brt   smallint NOT NULL,
  mean       double precision,
  var        double precision,
  n          integer,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (series_key, hora_brt)
);

CREATE TABLE gold.live_event_window (  -- calendário de transmissões ao vivo
  event_key   text NOT NULL,           -- identidade do confronto, estável entre feeds
  tid         integer NOT NULL,
  ts_start    timestamptz NOT NULL,
  ts_end      timestamptz NOT NULL,
  slug        text,
  channel     text,
  competition text,
  sport       text,
  team_home   text,
  team_away   text,
  event_date  date NOT NULL,           -- dia de programação em BRT
  first_seen  timestamptz,
  PRIMARY KEY (tid, ts_start)
);

CREATE TABLE gold.incident_window (
  window_id  bigserial PRIMARY KEY,
  ts_start   timestamptz NOT NULL,
  ts_end     timestamptz NOT NULL,
  origem     text NOT NULL,            -- incidents | incident_label | detector
  ref_id     text,
  verdict    text,                     -- internal | external | mixed
  severity   text,
  provenance text
);

CREATE TABLE gold.detection_match (
  window_id    bigint REFERENCES gold.incident_window,
  run_id       bigint,
  detection_id bigint,
  lead_time_s  integer,                -- negativo = detectou antes do ticket
  matched      boolean NOT NULL,
  PRIMARY KEY (window_id, run_id, detection_id)
);
```

&emsp; `gold.source_series` é um catálogo derivado de `feature_bucket`, com uma linha
por `(source, entity, metric)` e o primeiro `available_at`. Ele existe porque listar
fontes com dois `count(DISTINCT ...)` sobre os 4,9 milhões de buckets levou 47,4 s no
RDS do Learner Lab, acima do timeout de 30 s da API. A view `gold.v_source_series`
preserva o corte do relógio virtual; o catálogo é reconstruído junto de
`gold.rebuild_tudo()` e não cria uma segunda fonte de verdade.

&emsp; **`gold.live_event_window` tem duas armadilhas no ETL.** Primeira: `tid` 994 e
995 não são o mesmo canal em horários diferentes, são feeds simultâneos com jogos
diferentes, porque a Globo transmite partidas distintas em praças distintas no mesmo
horário. Agrupar por `start_ts` funde dois jogos num só; agrupar por `event_key` é o
correto. Segunda: popular `tem_jogo` com `EXISTS`, nunca com `JOIN`, porque o join
duplica o bucket justamente por causa dos dois feeds. E `slug` chega sempre como
`globo` (a família), enquanto a QoE vem por praça (`globo-rj`, `globo-sp`), então o
casamento é `LIKE 'globo%'`, tratado como agregado nacional, não como praça
específica.

&emsp; **`gold.incident_window` carrega `provenance` de propósito.** Sete dos vinte
rótulos de `incident_label` são `detector-derived`, criados olhando a saída do próprio
Argus. Avaliar um detector novo contra eles mede concordância com o baseline, não
acurácia: um modelo que encontre incidentes reais que o Argus perdeu seria penalizado.
A coluna existe para que a filtragem seja obrigatória e visível no schema, não uma
lembrança de quem escreve a query.

### 5.7 `detect`, saída do detector, por `run_id`

```sql
CREATE TABLE detect.run (
  run_id      bigserial PRIMARY KEY,
  sim_run_id  bigint REFERENCES sim.run,
  detector    text  NOT NULL,
  params      jsonb NOT NULL,
  started_at  timestamptz,
  finished_at timestamptz
);

CREATE TABLE detect.anomaly (
  run_id    bigint REFERENCES detect.run,
  bucket_ts timestamptz NOT NULL,
  source    text NOT NULL,
  entity    text NOT NULL,
  metric    text NOT NULL,
  z         double precision,
  score     double precision,
  n_sources smallint,
  PRIMARY KEY (run_id, bucket_ts, source, entity, metric)
);
```

&emsp; Tabelas criadas desde já, sem lógica que as popule (decisão 7 da seção 1.1). O
`run_id` entra desde já porque é o que permite rodar dois detectores sobre a mesma
janela e comparar; retrofitar identificador de execução depois seria caro.

### 5.8 As views `v_*`, o recorte do presente

```sql
CREATE VIEW gold.v_feature_bucket AS
  SELECT * FROM gold.feature_bucket
   WHERE available_at <= sim.now();
```

&emsp; Uma view por tabela consultável. É o único caminho de leitura da API: a Lambda
não recebe permissão de `SELECT` nas tabelas base, então a barreira contra vazamento de
futuro é do banco, imposta por `GRANT`, não da aplicação. A aplicação pode esquecer o
filtro; o `GRANT` não.

---

## 6. Justificativa da arquitetura e das tecnologias

### 6.1 RDS PostgreSQL com camadas bronze, silver e gold, não DynamoDB single-table

&emsp; O DynamoDB single-table fazia sentido quando o sistema controlava o schema dos
eventos que ele mesmo produzia. Consumindo CDC de 33 tabelas heterogêneas, com colunas
que a Globo pode acrescentar a qualquer momento sem aviso, a exigência mudou: o
armazenamento precisa acomodar mudança de schema sem migração. A separação entre
`bronze.change_log` e a corrente tipada (seção 4) resolve isso, e sustenta uma garantia
mais forte: nenhuma tabela de silver ou gold pode conter informação que não seja
derivável do `change_log`. Essa propriedade não existe de graça em DynamoDB, e é o
motivo direto de adotar um banco relacional com camadas explícitas em vez de manter o
modelo single-table.

### 6.2 Integração direta entre API Gateway e SQS, sem Lambda intermediária

&emsp; As rotas `POST /v1/changes` e `POST /v1/events` usam integração `AWS_PROXY`
direto para SQS (`SQS SendMessage`), sem uma Lambda de recepção no meio. O simulador é
o único emissor conhecido, e o contrato do payload já é o formato interno de change
event: não há transformação nem validação de negócio a fazer na borda que justifique
uma função adicional. Cada Lambda a mais nesse caminho seria custo e mais um ponto de
falha sem ganho de comportamento, então a integração direta do API Gateway com o SQS
foi preferida à alternativa mais comum (API Gateway, Lambda, SQS).

### 6.3 Dois workers, duas filas, sem duplicar a API

&emsp; A escolha de duas filas (`changes` e `events`) e dois serviços ECS consumidores
(`merge_worker` e `event_worker`), em vez de uma fila única com um worker que decide o
destino pelo conteúdo da mensagem, separa duas responsabilidades: mudança de estado da
tabela de origem (`change_log` para corrente) e evento de sessão (`bronze.event`), em
unidades de deploy e escala independentes, sem acoplar a lógica de roteamento a um
único processo. O custo dessa escolha é infraestrutura duplicada (duas filas, dois
serviços); o ganho é que cada worker pode escalar, falhar e ser reimplantado sem afetar
o outro.

### 6.4 ETL incremental como threads dentro de um único serviço ECS

&emsp; O ETL incremental roda como duas threads dentro do mesmo container
`processing` já provisionado, em vez de dois serviços ECS novos. A atomicidade de cada
ciclo mora no banco: cada chamada a `etl.executar_*()` é uma única transação SQL, com
watermark e dado avançando juntos, então threads bastam para orquestrar a cadência, e
evitam Terraform novo (task definition, log group, alarme de `RunningTaskCount`) para
algo que não precisa de isolamento de processo. O desenho completo, incluindo a regra
de guarda descoberta durante a implementação, está na seção 7.

### 6.5 Lambda para leitura, ECS Fargate para os workers

&emsp; A camada de leitura (`read_api`) roda em Lambda, enquanto ingestão,
processamento e simulação rodam em ECS Fargate. A diferença de perfil de carga
justifica a diferença de tecnologia: leitura de dashboard é intermitente e
correlacionada ao uso humano, um encaixe natural para o modelo de invocação sob
demanda da Lambda. Os workers de ingestão e o ETL, por outro lado, mantêm conexão de
pool com o RDS e um ciclo de vida contínuo (long polling, laços com cadência fixa);
cold start de Lambda e o limite de conexões simultâneas ao banco tornariam esse padrão
caro e frágil em Lambda. Fargate também foi a escolha original do worker de ingestão
desde o MVP anterior, motivada pela sazonalidade forte do tráfego da Globo (picos em
eventos ao vivo, shows e ofertas), um padrão que Lambda, com limite de concorrência por
conta, atenderia pior que containers de vida longa com auto scaling próprio.

### 6.6 Decisões de infraestrutura

&emsp; **Rede.** O RDS é publicamente acessível por padrão de ambiente de laboratório
(`var.db_publicly_accessible`, default `false`, ligado via `tfvars` do Learner Lab),
com ingress na porta 5432 restrito a um CIDR configurável, nunca `0.0.0.0/0`:

```hcl
resource "aws_security_group_rule" "rds_from_dev" {
  count = var.db_allowed_cidr != "" ? 1 : 0
  # ingress 5432 apenas do CIDR informado, nunca 0.0.0.0/0
}
```

&emsp; A alternativa de produção (RDS privado, Lambda dentro da VPC) fica documentada
como a postura correta, mas custa cold start de ENI na Lambda e impede inspecionar o
banco sem bastion, um custo que não se justifica em ambiente de desenvolvimento ou
laboratório.

&emsp; **Senha.** Dois modos: por padrão, `aws_secretsmanager_secret` com senha gerada
por `random_password`; se o Secrets Manager for negado pelo ambiente de laboratório,
cai para uma senha de `tfvars` (gitignored, marcada `sensitive`). Em nenhum caminho a
senha entra em arquivo versionado.

&emsp; **Dimensionamento da instância.** `db.t3.medium` com 100 GB gp3 foi
dimensionado para a bronze (cerca de 13 GB) e a silver (cerca de 6 GB, `signal_point`
duplicado), considerando que o PostgreSQL não comprime heap: os 199 MB de Parquet de
origem expandem para cerca de 2,1 GB de dados mais 1,2 GB de índice só em
`prom_point`. O ponto que sustenta essa escolha de instância sem virar gargalo é o
mesmo do corolário 1 da seção 4: as telas do dashboard nunca leem bronze, só
`gold.v_*`, o que desacopla o desempenho percebido do tamanho da camada bruta.

&emsp; **Proteção contra destruição.** `deletion_protection` e `skip_final_snapshot`
seguem `var.environment == "prod"`. Em laboratório, `skip_final_snapshot = true`: um
snapshot final de uma conta que vai deixar de existir é custo sem valor.

---

## 7. ETL incremental por watermarks

&emsp; Até a migration `015`, o único caminho para popular silver e gold era
`gold.rebuild_tudo()`: um recompute completo das tabelas de origem a cada chamada,
correto e idempotente (é o que sustenta o teste de rebuild da seção 8.4), mas que não
escala para rodar a cada 1 a 5 minutos sobre 18 milhões de linhas de `signal_point`. O
desenho abaixo, registrado primeiro numa publicação interna de apoio ("Watermarks e
workers de transição de camada", 20 de agosto de 2026) e implementado na migration
`015_etl_incremental.sql`, substitui isso por dois workers incrementais, cada um dono
do seu watermark, sem tocar nas funções `build_*` existentes além de acrescentar
parâmetros de faixa com `DEFAULT` (compatível com `gold.rebuild_tudo()`, que continua
chamando sem argumento nenhum).

| Worker | Watermark | Marcador | Cadência | Tabela de controle |
|---|---|---|---|---|
| bronze para silver | `etl.watermark_bronze_silver` | sequencial (`lsn`) | 60 s | `etl.execucoes` |
| silver para gold | `etl.watermark_silver_gold` | temporal (`available_at`, com margem que sempre reabre) | 900 s | `etl.execucoes` |

&emsp; Cada ciclo é uma única chamada SQL (`etl.executar_bronze_silver()` ou
`etl.executar_silver_gold()`): lê o watermark com `SELECT ... FOR UPDATE`, chama os
`build_*` na faixa certa, grava o resultado em `etl.execucoes` e avança o watermark,
tudo no mesmo commit, para que dado e watermark nunca fiquem inconsistentes entre si.

### 7.1 Onde este desenho diverge da publicação original

1. **Schema `etl`, não tabelas soltas.** A publicação original propunha
   `etl_watermark_bronze_silver` como tabela solta; aqui viraram
   `etl.watermark_bronze_silver` e assim por diante, num schema `etl` novo,
   consistente com a separação por schema que já organiza `bronze`, `silver`, `gold`,
   `sim` e `detect`.
2. **`live_event_window` e `incident_window` continuam de tabela inteira** dentro do
   ciclo silver para gold, em vez de também janelados por `available_at`. As origens
   (`bronze.live_event`, `bronze.incidents`, `bronze.incident_label`) são pequenas,
   centenas a poucos milhares de linhas, contra os quase 5 milhões de
   `signal_bucket`; recomputá-las por inteiro a cada ciclo custa menos do que o
   esforço de as tornar incrementais compraria. Só `gold.build_feature_bucket` ganhou
   janela.
3. **Watermark `silver_gold` semeado em 1º de julho de 2026, não em epoch.** A
   publicação original semeava 1º de janeiro de 1970. Como não há dado possível antes
   do limite inferior das partições de silver e gold, semear em epoch faria o primeiro
   dreno percorrer cerca de 56 anos em janelas de minutos até achar a primeira linha
   real, correto, só que muito lento.
4. **Dois workers, uma task ECS.** A publicação original (e o registro histórico do
   pivot, anterior a este documento) descrevia dois workers como unidades separadas,
   plausivelmente dois `RunTask` do EventBridge Scheduler. O que existe hoje
   (`ecs_processing.tf`) é um único serviço ECS sempre ativo, de laço próprio, não
   agendado por scheduler. Os dois workers viraram duas threads dentro do mesmo
   container (`argus_processing/__main__.py`), cada uma com seu laço, seu watermark e
   sua cadência, sem interferir uma na outra. Criar dois serviços ECS novos exigiria
   Terraform novo para separar uma cadência que duas threads já resolvem, já que a
   atomicidade de cada ciclo mora no banco (uma chamada SQL), não em memória
   compartilhada.
5. **Guarda de configuração nova, não prevista na publicação original.**
   `p_janela_max_segundos` (silver para gold) precisa ser estritamente maior que
   `margem_seguranca`; senão, o watermark não apenas trava, ele regride a cada
   chamada, porque a margem é subtraída nas duas pontas do ciclo (na leitura e no novo
   watermark). `etl.executar_silver_gold()` hoje falha alto (`RAISE EXCEPTION`) se
   essa condição não for satisfeita, em vez de deixar o worker girar para trás
   silenciosamente até alguém notar que a gold parou de crescer. Default em produção:
   `janela_max_segundos = 14400` (4h) contra `margem_seguranca = 2h`, dando 2h de
   progresso real por ciclo mesmo com backlog.
6. **Índice novo.** `silver.signal_bucket` não tinha índice em `available_at` (a
   migration `006` indexou `signal_point` e `session_event`, mas não
   `signal_bucket`), uma lacuna inofensiva enquanto o único leitor era o rebuild
   completo. O worker incremental filtra por `available_at` a cada ciclo; a migration
   `015` acrescenta o índice `signal_bucket_disponivel`.

### 7.2 Limitação conhecida, fora do escopo desta mudança

&emsp; Nem `gold.rebuild_tudo()` nem os novos `build_*` incrementais removem de
silver/gold uma linha cujo registro de origem foi apagado na bronze (o merge do log
processa `op = 'd'` fazendo `DELETE` na bronze corrente, mas os `build_*` são
`INSERT ... ON CONFLICT DO UPDATE`, nunca `DELETE`). Não é uma regressão desta
mudança, o comportamento já existia antes do ETL incremental, mas o desenho
incremental o torna mais visível, por rodar em produção de verdade em vez de só em
teste pontual. Fica registrado como pendência para decisão futura, não corrigido nesta
entrega.
