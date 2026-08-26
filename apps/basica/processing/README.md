# Processamento, correlação e geração de hipóteses

Este documento registra a decisão final para desenvolver a etapa de detecção,
correlação, geração de evidências, hipóteses e score do Argus. Ele complementa o
plano geral da arquitetura v3 e descreve como transformar o desenho conceitual em
uma implementação funcional dentro do repositório atual.

O objetivo da primeira versão é construir um **sistema especialista determinístico,
explicável e auditável**. O sistema utiliza regras de domínio explícitas; não depende
de modelo de linguagem, aprendizado supervisionado ou outra forma de machine
learning para produzir uma hipótese.

Uma hipótese continua sendo uma explicação candidata para investigação humana. Ela
não representa causa-raiz confirmada.

## 1. Resultado esperado

Ao final desta etapa, o pipeline deverá conseguir:

1. verificar se as fontes necessárias estão saudáveis;
2. comparar sinais com um baseline causal;
3. registrar anomalias encontradas pelo detector;
4. localizar anomalias potencialmente relacionadas;
5. selecionar famílias de hipótese compatíveis;
6. executar correlações temporais, semânticas, entre fontes, por concentração,
   propagação, contexto e contradição;
7. transformar as correlações em evidências auditáveis;
8. calcular score, cobertura e confiança;
9. persistir candidatos gerados, descartados e não avaliáveis;
10. expor hipóteses concluídas por views para a API de leitura.

O deploy é apenas um possível evento contextual para uma das famílias de hipótese.
O motor não será desenhado em torno dele.

## 2. Modelo mental do pipeline

```text
sinal
  ↓
baseline
  ↓
anomalia ou achado
  ↓
vizinhança de busca
  ↓
famílias de hipótese compatíveis
  ↓
correlações
  ↓
evidências
  ↓
features A, T, C, E, I, Q e X
  ↓
score, cobertura e confiança
  ↓
hipóteses ordenadas para investigação humana
```

Cada etapa responde a uma pergunta diferente:

| Etapa | Pergunta respondida |
|---|---|
| Sinal | Qual valor foi observado? |
| Baseline | Qual valor seria esperado naquele contexto? |
| Anomalia | O que ficou diferente do esperado? |
| Vizinhança | Quais achados podem merecer análise conjunta? |
| Correlação | Quais relações relevantes existem entre os fatos? |
| Evidência | Como um fato favorece, contradiz ou limita uma hipótese? |
| Hipótese | Qual explicação é compatível com o conjunto de evidências? |
| Score | Qual candidato deve ser investigado primeiro? |

## 3. Encaixe na arquitetura atual

Não será criado um novo fluxo de ingestão, uma nova fila ou um novo banco. O motor
entra no serviço ECS `processing`, que já possui acesso ao PostgreSQL e atualmente
executa o ETL incremental.

```text
App / Simulador
       ↓
API Gateway → SQS
       ↓
Event worker / Merge worker
       ↓
RDS — bronze
       ↓
Processing worker
  ├── Bronze → Silver
  ├── Silver → Gold + checkpoint
  ├── Canário de qualidade
  ├── Detector
  └── Motor de hipóteses
       ├── vizinhanças
       ├── regras
       ├── correlações
       ├── evidências
       └── score
       ↓
RDS — detect + gold
       ↓
Views → Lambda → Dashboard
```

Responsabilidades por schema:

| Schema | Responsabilidade |
|---|---|
| `bronze` | Dado recebido, change log e representação corrente da origem. |
| `silver` | Sinais canônicos, tempos normalizados e `available_at`. |
| `gold` | Features, contexto, qualidade, grupos, evidências e hipóteses. |
| `detect` | Coordenação da análise, execuções do detector e anomalias. |
| `etl` | Watermarks, execuções de transição e checkpoints publicados. |

## 4. Decisões obrigatórias do domínio

### 4.1 Nenhum dado futuro

Toda execução congela um `sim_now`. Um registro só pode participar quando:

```text
registro.available_at <= run.sim_now
```

O tempo utilizado para decidir disponibilidade é o tempo simulado. Horários reais
da AWS são guardados separadamente para medir operação e latência.

### 4.2 Baseline causal

O bucket atual é comparado com estado construído somente com dados anteriores e
disponíveis. O valor atual é avaliado antes de atualizar o baseline.

Cada anomalia persiste o valor observado, o valor esperado e a referência ou
fotografia do baseline utilizado. Uma execução histórica não depende do estado
atual e mutável de `gold.circadian_state` para ser explicada.

### 4.3 Anomalia não é hipótese

O detector responde o que ficou anormal. O motor de hipóteses tenta encontrar
explicações compatíveis. Uma anomalia nunca recebe causa diretamente no detector.

### 4.4 Vizinhança não é causa nem cluster exclusivo

O agrupador cria uma vizinhança de busca em torno de uma anomalia usando tempo,
semântica, escopo e direção. Depois, cada família escolhe os membros relevantes.

Uma mesma anomalia pode alimentar hipóteses concorrentes. Isso evita decidir cedo
demais que um conjunto inteiro possui uma única causa.

O agrupamento é determinístico e versionado. Mudanças na ordem de entrada não podem
alterar o resultado.

### 4.5 Papel da fonte

Cada regra classifica suas fontes:

| Papel | Comportamento |
|---|---|
| `required` | Sem a fonte, o candidato fica `insufficient_evidence`. |
| `supporting` | A ausência reduz cobertura, mas não impede a hipótese. |
| `optional` | Acrescenta contexto e pode não afetar a avaliação quando ausente. |
| `subject` | A saúde da própria fonte é o objeto investigado. |

Ausência de dado não é evidência contrária. Uma contradição só existe quando o dado
foi consultado, estava confiável e apresentou comportamento incompatível.

### 4.6 Score, cobertura e confiança são diferentes

- **score:** força relativa do candidato com as features disponíveis;
- **cobertura:** quanto das evidências aplicáveis estava disponível;
- **confiança:** classificação derivada de score, cobertura, qualidade e
  contradições.

O score não é probabilidade.

### 4.7 Histórico não é sobrescrito

Dados atrasados, regras novas ou catálogos novos criam outra execução ou revisão.
Resultados antigos permanecem preservados.

## 5. Coordenação e concorrência

### 5.1 Checkpoint imutável da Gold

Cada ciclo concluído de Silver → Gold publica uma linha append-only em
`etl.gold_checkpoint`. A atualização da Gold e a criação do checkpoint acontecem
na mesma transação PostgreSQL.

Por MVCC, o analisador enxerga uma destas fotografias:

```text
Gold anterior + checkpoint anterior
ou
Gold atualizada + checkpoint novo
```

Ele não enxerga uma Gold parcialmente confirmada. Não será criado um advisory lock
global para o dataset Gold.

### 5.2 Captura curta e processamento fora de transação

O worker abre uma transação curta `REPEATABLE READ`, seleciona o último checkpoint
confirmado e carrega uma janela limitada de dados para memória. Depois faz commit.

Canário, detector, agrupamento, correlação e score rodam fora dessa transação. Uma
segunda transação curta persiste os resultados.

Essa divisão evita manter uma fotografia PostgreSQL aberta durante segundos ou
minutos e reduz impacto sobre autovacuum e retenção de versões antigas.

### 5.3 Claim curto

`pg_try_advisory_xact_lock` é utilizado somente para reivindicar um trabalho. O
lock é transacional e liberado automaticamente no commit ou rollback.

No MVP, o lock de claim é global porque sua seção crítica dura apenas o tempo de
selecionar um checkpoint e registrar o proprietário. O processamento não ocorre
sob esse lock.

### 5.4 Lease e heartbeat

O claim possui proprietário, vencimento e heartbeat. Enquanto processa, o worker
renova o lease. Se o lease expirar, outra tentativa pode assumir o trabalho.

Uma tentativa anterior que perdeu o lease fica `abandoned` e nunca volta para
`running`.

### 5.5 Fencing token global

Cada claim ou takeover recebe um token de uma única sequência global:

```text
detect.fencing_token_seq — bigint, NO CYCLE, CACHE 1
```

Regras da sequência:

- tokens nunca são reiniciados nem reutilizados;
- lacunas causadas por rollback são normais;
- heartbeat e renovação normal do mesmo lease não geram novo token;
- takeover, retry ou novo trabalho geram novo token;
- o token não tem significado de negócio;
- `detect.run.fencing_token` é único.

Antes de gravar qualquer resultado, o worker precisa provar que ainda possui o
token ativo. A transação muda o run de `running` para `committing` com um `UPDATE`
condicional. Se nenhuma linha for atualizada, a tentativa perdeu a posse e toda a
transação é abortada.

Tabelas filhas não precisam repetir o token: elas são inseridas somente dentro da
transação protegida pelo run pai.

### 5.6 Estados da execução

```text
claimed
   ↓
running
   ├──→ committing ──→ completed
   │         └────────→ failed
   ├──────────────────→ failed
   └──────────────────→ abandoned
```

| Estado | Significado |
|---|---|
| `claimed` | Trabalho atribuído; captura ainda não começou. |
| `running` | Captura ou processamento em andamento. |
| `committing` | Fencing validado; resultados sendo persistidos. |
| `completed` | Resultados confirmados no banco. |
| `failed` | Falha conhecida na tentativa. |
| `abandoned` | Lease venceu e outra tentativa assumiu. |

## 6. Idempotência e revisões

### 6.1 Manifesto da execução

O manifesto identifica todo comportamento capaz de mudar um resultado:

```text
detector_version
grouping_version
rules_version
weights_version
semantic_catalog_version
metric_catalog_version
git_commit
container_image_digest
```

Além das versões legíveis, a execução guarda hashes dos conteúdos. O
`manifest_hash` participa da identificação lógica do trabalho:

```text
checkpoint_id + manifest_hash
```

### 6.2 Chaves de hipótese

Antes de calcular hashes, timestamps são convertidos para UTC, IDs são ordenados,
listas são deduplicadas e objetos JSON têm suas chaves ordenadas.

- `dedup_key`: família + período + escopo + anomalias; evita duplicação exata
  dentro de um run;
- `lineage_key`: família + período normalizado + escopo; relaciona revisões da
  mesma hipótese em runs diferentes.

Os dois valores são SHA-256 de uma representação canônica.

## 7. Controle de candidatos

Para evitar explosão combinatória, a avaliação possui três níveis:

1. **vizinhança:** limita tempo, escopo, fontes, métricas e quantidade de membros;
2. **prefiltro da regra:** verifica gatilho, direção, volume e dimensões mínimas;
3. **correlação completa:** executa somente para candidatos que passaram pelo
   prefiltro.

Falhas de prefiltro são registradas de forma agregada em
`gold.hypothesis_run_stats`. Não é criada uma linha de hipótese para cada
combinação que falhou antes de virar candidato.

Resultados após avaliação completa são persistidos:

| Resultado | Persistência |
|---|---|
| Não passou pelo prefiltro | Contador agregado por regra e motivo. |
| Contradito após avaliação | Hipótese `discarded` com evidências. |
| Faltaram dados necessários | Hipótese `insufficient_evidence`. |
| Evidência mínima encontrada | Hipótese `generated`. |

Cada execução terá orçamentos configuráveis, como quantidade máxima de vizinhanças
e candidatos. Se ocorrer truncamento, o run registra o motivo e quantos candidatos
deixaram de ser avaliados. Uma execução truncada não pode declarar cobertura total.

## 8. Estrutura Python planejada

Arquivos novos dentro de `src/argus_processing`:

```text
src/argus_processing/
├── orchestration.py
├── canonical.py
├── manifest.py
│
├── quality/
│   ├── __init__.py
│   ├── models.py
│   ├── canary.py
│   └── repository.py
│
├── detection/
│   ├── __init__.py
│   ├── models.py
│   ├── ewma.py
│   ├── directions.py
│   └── repository.py
│
├── hypotheses/
│   ├── __init__.py
│   ├── models.py
│   ├── engine.py
│   ├── grouping.py
│   ├── rules.py
│   ├── scoring.py
│   ├── repository.py
│   └── correlation/
│       ├── __init__.py
│       ├── temporal.py
│       ├── semantic.py
│       ├── cross_source.py
│       ├── concentration.py
│       ├── propagation.py
│       ├── external_context.py
│       └── contradiction.py
│
└── config/
    ├── __init__.py
    ├── metric_catalog.py
    ├── entity_relations.py
    └── hypothesis_rules.py
```

Responsabilidades:

| Arquivo | Responsabilidade |
|---|---|
| `orchestration.py` | Claim, captura, heartbeat, execução e commit protegido. |
| `canonical.py` | JSON canônico, `dedup_key`, `lineage_key` e `input_digest`. |
| `manifest.py` | Versões e hashes das regras, pesos e catálogos. |
| `quality/canary.py` | Atualidade, completude, validade e consistência por fonte. |
| `detection/ewma.py` | Baseline e força da anomalia. |
| `detection/directions.py` | Define aumento, redução ou ambos como degradação. |
| `hypotheses/grouping.py` | Vizinhanças determinísticas e não exclusivas. |
| `hypotheses/rules.py` | Contrato e seleção das famílias de hipótese. |
| `hypotheses/scoring.py` | Score, cobertura, confiança e contribuições. |
| `hypotheses/engine.py` | Coordena regras, correlacionadores e candidatos. |
| `*/repository.py` | Único local de SQL usado pelo respectivo domínio. |

As funções matemáticas, regras e correlacionadores não devem consultar o banco
diretamente. Eles recebem objetos Python e devolvem resultados. Isso permite testes
unitários rápidos e previsíveis.

## 9. Migrations planejadas

As migrations existentes `001` a `017` são imutáveis e **não serão alteradas**.

### 9.1 `016_gold_checkpoint.sql`

Cria `etl.gold_checkpoint` como log append-only e publica o checkpoint na mesma
transação de Silver → Gold.

Campos mínimos:

```text
checkpoint_id
etl_execution_id
sim_run_id
ready_through
source_lsn
created_at
row_counts
```

### 9.2 `017_analysis_coordination.sql`

Cria:

```text
detect.fencing_token_seq
detect.work_claim
```

E evolui `detect.run` com:

```text
checkpoint_id
manifest_hash
sim_now
status
claimed_by
lease_expires_at
heartbeat_at
fencing_token
attempt
retry_of
input_lsn
input_digest
error_message
```

### 9.3 `018_detection_contract.sql`

Evolui `detect.anomaly` com:

```text
anomaly_id
observed
expected
direction
deviation
available_at
baseline_snapshot
```

### 9.4 `019_source_quality.sql`

Cria:

```text
gold.source_quality_run
gold.source_quality
```

### 9.5 `020_hypothesis_engine.sql`

Cria:

```text
gold.hypothesis_run
gold.finding_group
gold.finding_group_member
gold.hypothesis
gold.hypothesis_finding
gold.hypothesis_evidence
gold.hypothesis_feedback
gold.hypothesis_run_stats
```

### 9.6 `021_hypothesis_views.sql`

Cria views temporais para a API:

```text
gold.v_hypothesis_run
gold.v_hypothesis
gold.v_hypothesis_detail
gold.v_hypothesis_evidence
```

Somente as views recebem `SELECT` para `argus_reader`. Nenhuma tabela base nova é
liberada diretamente para a Lambda.

## 10. Arquivos que serão criados

### 10.1 Banco

```text
db/migrations/016_gold_checkpoint.sql
db/migrations/017_analysis_coordination.sql
db/migrations/018_detection_contract.sql
db/migrations/019_source_quality.sql
db/migrations/020_hypothesis_engine.sql
db/migrations/021_hypothesis_views.sql
```

### 10.2 Processamento

Todos os arquivos apresentados na estrutura da seção 8 serão novos. O código novo
fica isolado por responsabilidade, reduzindo alterações nos módulos atuais.

### 10.3 Testes

```text
tests/test_checkpoint.py
tests/test_claim.py
tests/test_fencing.py
tests/test_canonical.py
tests/test_quality.py
tests/test_detector.py
tests/test_grouping.py
tests/test_rules.py
tests/test_correlations.py
tests/test_scoring.py
tests/test_hypothesis_repository.py
tests/test_analysis_pipeline.py
```

Fixtures de cenários serão adicionadas em:

```text
tests/fixtures/analysis/
├── regional_isp.json
├── cdn_qoe.json
├── source_silent.json
├── expected_live_peak.json
└── unrelated_anomalies.json
```

### 10.4 API, em etapa posterior

Para reduzir alterações no adaptador atual de Gold, serão preferidos arquivos novos:

```text
backend/src/telemetry/infrastructure/hypotheses.py
backend/src/telemetry/interfaces/hypotheses_http.py
backend/tests/test_hypotheses.py
```

## 11. Arquivos existentes que terão mudanças

Alterações em arquivos existentes serão pequenas e concentradas.

### 11.1 Mudanças necessárias para o motor

| Arquivo | Mudança necessária | Motivo |
|---|---|---|
| `processing/src/argus_processing/__main__.py` | Importar e iniciar o laço de análise; encerrar a nova thread no shutdown. | Integrar o motor ao ECS já existente. |

O objetivo é manter `__main__.py` apenas como composição e ciclo de vida. Regras,
SQL e cálculos não serão implementados nele.

O módulo `processing/src/argus_processing/etl.py` não precisa mudar: a publicação do
checkpoint será incorporada à função SQL existente por uma migration nova, e o novo
repository de orquestração consultará o checkpoint separadamente.

### 11.2 Mudanças de infraestrutura

| Arquivo | Mudança provável | Motivo |
|---|---|---|
| `infra/ecs_processing.tf` | Adicionar variáveis de ambiente de análise, lease, heartbeat e limites. | Configuração operacional sem alterar código. |
| `infra/variables.tf` | Declarar as novas configurações. | Permitir ajuste por ambiente. |
| `infra/terraform.tfvars.example` | Documentar valores sugeridos. | Facilitar deploy reproduzível. |
| `infra/observability.tf` | Adicionar métricas/alarmes de run parado, lease expirado e atraso da análise. | Operação e diagnóstico. |

Essas mudanças podem ser adiadas no desenvolvimento local usando defaults seguros no
Python. Elas serão necessárias antes do deploy do motor na AWS.

### 11.3 Mudanças da API

| Arquivo | Mudança necessária | Motivo |
|---|---|---|
| `backend/src/telemetry/app.py` | Registrar o blueprint de hipóteses. | Expor as novas rotas. |
| `backend/src/telemetry/interfaces/openapi.py` | Documentar contratos de listagem e detalhe. | Manter OpenAPI como contrato real da API. |

O adaptador `infrastructure/gold.py` não precisa ser alterado se a leitura de
hipóteses ficar no novo `infrastructure/hypotheses.py`.

### 11.4 Mudanças de documentação

| Arquivo | Mudança | Momento |
|---|---|---|
| `README.md` da raiz | Atualizar o estado de detector e motor após a implementação. | Quando a funcionalidade estiver ativa. |
| `artefatos/plano-argus-v3.md` | Registrar que detector, canário e hipóteses deixaram de ser no-op. | Após validação do pipeline. |
| `backend/README.md` | Adicionar endpoints de hipóteses. | Junto da API. |

### 11.5 Arquivos que não devem mudar

```text
db/migrations/001_*.sql até 015_*.sql
worker/src/argus_worker/*
loader/*
simulator/*
common/src/argus_common/db.py
```

Os workers de ingestão continuam responsáveis somente por Bronze. O loader e o
simulador não recebem lógica de detecção ou hipótese. O acesso transacional já
oferecido por `argus_common.Database` é suficiente para a primeira versão.

O `processing/pyproject.toml` também não precisa mudar enquanto regras e catálogos
forem definidos em Python e forem utilizadas apenas biblioteca padrão e
`argus-common`.

## 12. Passo a passo de desenvolvimento

### Etapa 0 — Inventário dos dados

Antes das regras:

1. listar combinações reais de `source`, `entity` e `metric`;
2. identificar granularidade e direção de cada métrica;
3. identificar dimensões disponíveis para canal, dispositivo, UF, ISP e serviço;
4. mapear relações entre entidades de fontes diferentes;
5. escolher duas ou três famílias possíveis com os dados existentes.

Saída: primeira versão de `metric_catalog.py`, `entity_relations.py` e
`hypothesis_rules.py`.

### Etapa 1 — Checkpoint e coordenação

1. criar a migration `016`;
2. garantir publicação atômica da Gold e do checkpoint;
3. criar a migration `017`;
4. implementar claim, lease, heartbeat e fencing;
5. testar dois workers disputando o mesmo checkpoint;
6. testar expiração e takeover;
7. testar que um worker zumbi não consegue fazer commit.

Saída: uma unidade de trabalho pode ser reivindicada, acompanhada e encerrada com
segurança, ainda sem detector real.

> **Estado: concluída.** As migrations
> [`016_gold_checkpoint.sql`](../db/migrations/016_gold_checkpoint.sql) e
> [`017_analysis_coordination.sql`](../db/migrations/017_analysis_coordination.sql)
> implementam as garantias de banco. O módulo
> [`orchestration.py`](src/argus_processing/orchestration.py) implementa claim,
> lease, heartbeat, takeover e commit protegido. Os cenários concorrentes estão
> cobertos por [`test_claim.py`](tests/test_claim.py) e
> [`test_fencing.py`](tests/test_fencing.py).

### Etapa 2 — Contratos do detector

1. criar a migration `018`;
2. implementar modelos de finding e baseline;
3. criar catálogo de direção das métricas;
4. implementar EWMA causal;
5. persistir observado, esperado, direção e score;
6. testar corte por `run.sim_now`;
7. testar cold start e variância próxima de zero.

Saída: um checkpoint produz um `detect.run` concluído e anomalias explicáveis.

### Etapa 3 — Qualidade das fontes

1. criar a migration `019`;
2. criar contratos de cadência esperada sem confundir cadência com latência;
3. calcular freshness, completeness, validity e consistency;
4. classificar fontes como `healthy`, `delayed`, `incomplete`, `silent` ou
   `unknown`;
5. persistir a fotografia de qualidade do run;
6. implementar os papéis `required`, `supporting`, `optional` e `subject`;
7. testar ausência versus contradição.

Saída: toda regra pode decidir se baixa qualidade bloqueia, reduz cobertura ou é a
própria evidência investigada.

### Etapa 4 — Núcleo puro do motor

1. implementar modelos de hipótese e evidência;
2. implementar JSON canônico e hashes;
3. implementar score, cobertura e confiança;
4. implementar vizinhanças determinísticas;
5. implementar contrato de prefiltro;
6. implementar orçamento e truncamento;
7. testar tudo sem banco, usando objetos Python.

Saída: o motor recebe findings sintéticos e devolve resultados determinísticos.

### Etapa 5 — Primeiro recorte vertical

Implementar duas ou três famílias com características diferentes. Seleção inicial
sugerida, condicionada ao inventário real:

- possível degradação regional ou por operadora;
- possível degradação de CDN com piora de QoE;
- possível falha ou atraso de fonte.

Para cada família:

1. declarar gatilhos e papéis das fontes;
2. declarar correlações aplicáveis;
3. definir volume mínimo e janela;
4. definir contradições;
5. definir features e pesos;
6. criar cenário positivo;
7. criar cenário contraditório;
8. criar cenário com fonte indisponível;
9. criar cenário semanticamente não relacionado.

Saída: ciclo finding → candidato → evidências → score funcionando com fixtures.

### Etapa 6 — Persistência do motor

1. criar a migration `020`;
2. implementar repositories;
3. validar fencing antes de inserir resultados;
4. persistir grupos, membros, candidatos, findings e evidências na mesma
   transação;
5. implementar `dedup_key` e `lineage_key`;
6. registrar estatísticas de prefiltro;
7. testar rollback e retry idempotente.

Saída: resultados permanecem auditáveis no RDS e sobrevivem ao reinício do worker.

### Etapa 7 — Orquestração completa

1. implementar `orchestration.py`;
2. capturar janela limitada em `REPEATABLE READ`;
3. calcular `input_digest`;
4. processar fora da transação;
5. renovar heartbeat;
6. persistir em transação curta protegida pelo fencing;
7. integrar uma nova thread em `__main__.py`;
8. medir duração, quantidade de candidatos e atraso.

Saída: processamento contínuo no container atual.

### Etapa 8 — Views e API

1. criar a migration `021`;
2. conceder leitura somente às views;
3. criar repository de hipóteses;
4. criar endpoints de lista e detalhe;
5. documentar OpenAPI;
6. testar que dados futuros e candidatos internos não aparecem indevidamente.

Saída: dashboard pode consultar resultados já processados.

### Etapa 9 — AWS e observabilidade

1. expor configurações no Terraform;
2. publicar métricas de runs, lease, checkpoint, atraso, truncamento e duração;
3. criar alarmes para análise parada e falhas repetidas;
4. validar CPU, memória, pool de conexões e duração dos lotes;
5. testar desligamento e retomada do ECS.

Saída: motor operável no ambiente AWS atual, sem nova fila ou serviço obrigatório.

## 13. Estratégia de testes

### 13.1 Testes unitários

- agrupamento não depende da ordem;
- proximidade temporal respeita janela máxima;
- relação semântica incompatível impede associação forte;
- fonte `required` indisponível gera `insufficient_evidence`;
- fonte `supporting` indisponível reduz cobertura;
- ausência não aumenta contradição;
- score permanece entre 0 e 100;
- feature `not_applicable` não reduz cobertura;
- hashes são iguais para objetos semanticamente iguais;
- limites de candidatos geram marca de truncamento.

### 13.2 Testes PostgreSQL

- checkpoint e Gold são publicados atomicamente;
- somente um worker reivindica o mesmo trabalho;
- lease expirado permite takeover;
- fencing antigo não consegue transicionar para `committing`;
- falha na persistência faz rollback completo;
- retry não duplica hipótese;
- views respeitam o tempo simulado;
- `argus_reader` não lê tabelas base.

### 13.3 Testes de cenário

- anomalias próximas e não relacionadas não viram evidência forte;
- uma anomalia pode alimentar hipóteses concorrentes;
- evento ao vivo contextualiza volume sem esconder piora de QoE;
- fonte silenciosa não vira queda operacional;
- fonte atrasada pode gerar revisão posterior sem alterar o run original.

## 14. Observabilidade mínima

Métricas recomendadas:

```text
AnalysisRunsStarted
AnalysisRunsCompleted
AnalysisRunsFailed
AnalysisRunsAbandoned
AnalysisLeaseTakeovers
AnalysisFencingRejected
AnalysisDuration
AnalysisInputRows
AnalysisInputBytes
AnalysisCandidatesPrefiltered
AnalysisCandidatesEvaluated
AnalysisCandidatesTruncated
AnalysisHypothesesGenerated
AnalysisHypothesesDiscarded
AnalysisInsufficientEvidence
AnalysisLagSimulated
```

Logs devem incluir `checkpoint_id`, `run_id`, `fencing_token`, `manifest_hash` e
status, sem incluir informações pessoais desnecessárias.

## 15. Retenção inicial

Política inicial, ajustável depois de medir volume:

| Resultado | Retenção inicial |
|---|---:|
| `generated` e revisado por pessoa | Sem expurgo automático no MVP |
| `insufficient_evidence` | 90 dias reais |
| `discarded` detalhado | 30 dias reais |
| Estatísticas agregadas de prefiltro | 180 dias reais |
| Runs com erro ou abandono | 90 dias reais |

O tempo simulado é preservado como dado de domínio. A política operacional de
expurgo utiliza o tempo real de criação.

Nenhuma rotina de exclusão deve ser criada antes de existirem métricas reais de
volume e uma decisão explícita de operação.

## 16. Critérios de aceite da primeira versão

1. O mesmo checkpoint e manifesto não produzem dois runs concluídos.
2. Um worker com fencing token antigo não consegue persistir resultados.
3. Nenhuma consulta usa dado posterior ao `run.sim_now`.
4. O detector preserva observado, esperado, direção e baseline.
5. Agrupamento é determinístico e não exclusivo.
6. Prefiltros impedem explosão combinatória sem falha silenciosa.
7. Fontes possuem papel explícito por regra.
8. Ausência de dado não é contradição.
9. Score, cobertura e confiança são calculados separadamente.
10. Cada contribuição pode ser explicada pela API.
11. Retry não duplica grupos, hipóteses ou evidências.
12. Dados atrasados geram revisão sem sobrescrever histórico.
13. O frontend não executa detector, correlação ou score.
14. `argus_reader` continua restrito a views.
15. Pelo menos duas famílias diferentes funcionam de ponta a ponta.
