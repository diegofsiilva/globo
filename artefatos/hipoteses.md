# Arquitetura de Geração de Hipóteses

## 1. Objetivo

&emsp;Este documento descreve como estruturar a geração, o ranqueamento, a apresentação e a validação de hipóteses de causa provável na plataforma de Monitoração Agêntica. A proposta considera a arquitetura-alvo baseada em simulação de produção, eventos de mudança, processamento em camadas e persistência no Amazon RDS PostgreSQL.

&emsp;A solução será inicialmente um **sistema especialista**. Regras explícitas representam o conhecimento disponível sobre o domínio, enquanto um score ponderado organiza as hipóteses e mostra como cada evidência contribuiu para o resultado. Essa abordagem é adequada enquanto ainda não existe um conjunto rotulado suficiente para treinar um modelo supervisionado confiável.

&emsp;Uma hipótese não representa causa-raiz confirmada. Ela é uma explicação candidata, construída com dados que já estariam disponíveis no instante simulado, e deve ser validada por uma pessoa.

## 2. Visão da arquitetura-alvo

&emsp;A arquitetura está organizada nos seguintes blocos:

```text
S3 — dump SQL imutável
          ↓ snapshot inicial
Simulador de produção — ECS Fargate
  ├── sim.clock: relógio virtual
  ├── injeção de falhas com seed fixa
  └── emissor de change events
          ↓ POST /v1/changes
API Gateway
          ↓
SQS change-events ── após tentativas ──→ DLQ
          ↓ long polling
ECS Fargate merge worker
          ↓
Amazon RDS PostgreSQL
  ├── bronze: histórico das mudanças
  ├── silver: sinais canônicos
  ├── gold: features, contexto, detecções e hipóteses
  └── views: somente dados disponíveis em sim.now
          ↑
Processamento agendado
  ├── ETL bronze → silver → gold
  ├── canário de qualidade
  ├── detector EWMA circadiano
  └── motor de hipóteses
          ↓
Lambda de consulta → API Gateway → CloudFront/S3 → Dashboard Next.js
```

&emsp;O Amazon ECR armazena as imagens dos componentes executados em contêineres. O AWS IAM controla permissões, o Amazon CloudWatch recebe métricas de atraso, saúde e disponibilidade, e o Amazon SNS pode notificar falhas operacionais. O EventBridge Scheduler coordena execuções periódicas do ETL, do detector e do motor de hipóteses.

## 3. Conceitos temporais fundamentais

&emsp;A simulação introduz mais de um conceito de tempo. Eles não devem ser tratados como equivalentes.

| Campo | Significado |
|---|---|
| `event_at` | Instante em que o fato teria ocorrido na produção simulada. |
| `captured_at` | Instante em que a mudança foi capturada pelo emissor. |
| `available_at` | Primeiro instante em que o dado poderia ser consultado pelo sistema. |
| `processed_at` | Instante em que uma etapa de processamento produziu seu resultado. |
| `sim.now` | Presente definido pelo relógio virtual. |

### RT01 — Nenhum componente pode consultar o futuro

&emsp;Detectores, regras, API e frontend só podem utilizar registros que satisfaçam:

```sql
available_at <= sim.now
```

&emsp;Essa condição é essencial para impedir vazamento temporal. Um dado pode possuir `event_at` anterior ao presente, mas ainda não estar disponível devido à latência de sua fonte.

### RT02 — Baselines devem ser causais

&emsp;O baseline de um bucket deve ser construído apenas com buckets anteriores e disponíveis no instante da execução. Reprocessamentos não podem alterar silenciosamente o conjunto de evidências visto por uma execução histórica.

### RT03 — Atraso de fonte deve ser preservado

&emsp;Fontes com disponibilidade tardia, como dados batch de experiência do usuário, não podem aparecer retroativamente em uma hipótese online como se estivessem disponíveis no momento do incidente. Elas podem gerar uma revisão posterior, identificada como nova tentativa ou nova versão da hipótese.

## 4. Responsabilidade de cada camada

### 4.1 Fonte imutável

&emsp;O dump SQL no S3 representa o conjunto original de dados e não deve ser alterado durante a simulação. Ele fornece o snapshot inicial e os registros que serão reproduzidos como mudanças.

### 4.2 Simulador de produção

&emsp;O simulador controla a reprodução determinística do cenário:

- `sim.clock` define o presente virtual;
- a injeção de falhas usa seed fixa para permitir repetição;
- o emissor produz change events com operação, estado anterior, estado posterior e LSN;
- `before` e `after` permitem representar inclusão, alteração e remoção;
- o LSN permite ordenar e tornar a aplicação das mudanças idempotente.

### 4.3 Ingestão

&emsp;A API de mudanças recebe os eventos e os envia à fila `change-events`. O merge worker consome por long polling, registra cada mudança no bronze e atualiza a representação corrente. Falhas permanentes seguem para a DLQ após a política configurada de tentativas.

### 4.4 Bronze

&emsp;A camada bronze possui duas responsabilidades:

- manter um log append-only das mudanças, incluindo LSN e `captured_at`;
- manter a versão corrente de cada registro por meio de `MERGE` ordenado por LSN.

&emsp;O log append-only fornece auditoria e reprocessamento. A tabela corrente facilita o ETL sem perder a origem de cada alteração.

### 4.5 Silver

&emsp;A camada silver recebe os dados validados e canônicos. Seu ativo central é o `silver.signal_point`:

```text
(ts, source, entity, metric, value, tags, available_at, source_lsn)
```

&emsp;O formato canônico permite processar fontes heterogêneas sem exigir que todas possuam localização, dispositivo, região ou outros campos opcionais. A identidade semântica de uma série é:

```text
source + entity + metric
```

&emsp;Os `tags` adicionam contexto quando disponível, mas não são requisito global para geração de hipóteses.

### 4.6 Gold

&emsp;A camada gold contém dados preparados para detecção, correlação, avaliação e consulta:

- `gold.feature_bucket`: features alinhadas em buckets, inicialmente de 15 minutos;
- `gold.circadian_state`: estado causal utilizado pelo detector EWMA;
- `gold.detection_run`: metadados de cada execução do detector;
- `gold.detection_anomaly`: anomalias produzidas, identificadas por `run_id`;
- `gold.live_event_window`: contexto de eventos ao vivo;
- `gold.incident_window`: janelas de incidentes para avaliação;
- `gold.detection_match`: correspondência entre detecções e incidentes, incluindo lead time;
- tabelas de hipóteses e feedback propostas neste documento.

### 4.7 Views de consulta

&emsp;As views `v_*` devem aplicar a regra de disponibilidade temporal e expor somente resultados compatíveis com `sim.now`. A Lambda de leitura consulta essas views para retornar séries, facetas, detecções e hipóteses ao frontend.

## 5. Posição do motor de hipóteses

&emsp;O motor de hipóteses deve ser executado **depois do detector EWMA circadiano** e não dentro da requisição do frontend.

```text
silver.signal_point
        ↓
gold.feature_bucket + gold.circadian_state
        ↓
Detector EWMA circadiano
        ↓
gold.detection_anomaly por run_id
        ↓
Motor de hipóteses
  ├── agrupa achados
  ├── consulta contexto disponível
  ├── gera candidatos
  ├── calcula features e score
  └── persiste evidências
        ↓
gold.hypothesis_* → views → API → frontend
```

&emsp;O detector responde **o que ficou anormal**. O motor de hipóteses tenta explicar **qual causa é compatível com as anomalias e com o contexto disponível**.

## 6. Entradas e saídas do motor

### 6.1 Entradas obrigatórias

- `run_id` da execução do detector;
- `sim_now` utilizado pela execução;
- anomalias de `gold.detection_anomaly`;
- features correspondentes de `gold.feature_bucket`;
- estado ou referência do baseline utilizado;
- resultado do canário de qualidade das fontes envolvidas.

### 6.2 Entradas contextuais

- deploys e eventos de plataforma originados do Tsuru;
- atribuição de erro por `playback_api`, `edge_isp`, `core` ou `other`;
- sinais de CDN, origem, RPaaS, Apollo, New Relic, Prometheus e Cloud Armor;
- dados de player, dispositivo, canal, geografia e ISP;
- `gold.live_event_window`;
- incidentes históricos e rótulos disponíveis no instante da execução.

### 6.3 Saídas

- hipóteses geradas e ordenadas;
- hipóteses descartadas por evidência contrária;
- candidatos não avaliáveis por falta de dados;
- score, cobertura e confiança;
- contribuição de cada feature;
- evidências favoráveis, contrárias e indisponíveis;
- referências aos achados, buckets e sinais consultados;
- versão da regra e dos pesos;
- feedback humano posterior.

## 7. Modelo de domínio

### 7.1 Achado

&emsp;Um achado é uma anomalia observada, ainda sem atribuição de causa.

```json
{
  "finding_id": "finding-001",
  "run_id": "run-20260820-2000",
  "bucket_start": "2026-08-20T20:00:00Z",
  "source": "cdn_live_errors",
  "entity": "pfc1",
  "metric": "err_rate",
  "observed": 14.0,
  "expected": 0.8,
  "anomaly_score": 8.7,
  "direction": "increase",
  "available_at": "2026-08-20T20:15:00Z"
}
```

### 7.2 Evidência

```json
{
  "evidence_id": "evidence-001",
  "type": "temporal_proximity",
  "relation": "supports",
  "availability": "available",
  "feature_value": 0.76,
  "weight": 0.25,
  "contribution": 19.0,
  "description": "Deploy ocorrido 6 minutos antes do início da anomalia.",
  "source_reference": {
    "schema": "silver",
    "table": "tsuru_event",
    "record_id": "event-123"
  }
}
```

### 7.3 Hipótese

```json
{
  "hypothesis_id": "hypothesis-001",
  "run_id": "run-20260820-2000",
  "type": "deployment_regression",
  "title": "Possível regressão após deploy no serviço de playback",
  "verdict": "internal",
  "score": 84,
  "coverage": 0.80,
  "confidence": "high",
  "status": "generated",
  "started_at": "2026-08-20T20:00:00Z",
  "available_at": "2026-08-20T20:15:00Z",
  "rule_version": "1.0.0",
  "weights_version": "1.0.0",
  "finding_ids": ["finding-001", "finding-002"]
}
```

### 7.4 Estados

| Estado | Significado |
|---|---|
| `candidate` | A assinatura inicial da regra foi encontrada. |
| `generated` | Existem evidências mínimas para apresentar a hipótese. |
| `insufficient_evidence` | Faltam dados necessários para avaliar a causa. |
| `discarded` | Evidências observadas contradizem a causa candidata. |
| `confirmed` | A hipótese foi confirmada por uma pessoa. |
| `partially_confirmed` | A causa ou o escopo foram parcialmente confirmados. |
| `rejected` | A hipótese foi rejeitada por uma pessoa. |

## 8. Regras gerais do sistema especialista

### RN-H01 — Toda hipótese deve partir de uma detecção

&emsp;Uma hipótese deve referenciar pelo menos uma anomalia de `gold.detection_anomaly`. Eventos contextuais, como deploys ou jogos, não são suficientes isoladamente para criar uma hipótese de incidente.

### RN-H02 — A semântica depende da fonte

&emsp;O sistema deve interpretar `entity` e `metric` junto com `source`. Métricas com o mesmo nome em fontes distintas não devem ser combinadas sem uma transformação explícita.

### RN-H03 — Correlação somente com dados disponíveis

&emsp;Toda consulta de evidências deve aplicar `available_at <= sim_now` da execução. A regra vale mesmo quando o evento ocorreu antes da anomalia.

### RN-H04 — Alinhamento temporal

&emsp;Sinais com granularidades distintas devem ser associados ao bucket mais grosso relevante. O bucket padrão será de 15 minutos, mas a precisão original da evidência deve ser preservada.

### RN-H05 — Dimensões opcionais

&emsp;Região, dispositivo, versão, ISP, canal e demais dimensões são opcionais. Sua ausência reduz a especificidade ou a cobertura, mas não impede hipóteses que não dependam delas.

### RN-H06 — Ausência não é contradição

&emsp;Uma evidência ausente deve ser registrada como `unavailable`. O estado `discarded` exige dado consultado que contradiga a hipótese.

### RN-H07 — Qualidade antes da causalidade

&emsp;Antes de interpretar ausência ou queda de sinal, o motor deve verificar o canário de qualidade e o atraso da fonte. Uma fonte atrasada ou divergente pode gerar uma hipótese de problema de dados, mas não deve sustentar uma causa operacional sem ressalva.

### RN-H08 — Hipótese de fonte única é permitida

&emsp;Uma única fonte pode gerar hipótese quando a anomalia for forte, houver materialidade e a causa puder ser naturalmente isolada, como regressão de player ou dispositivo. Corroboração entre fontes aumenta o score, mas não funciona como gate obrigatório.

### RN-H09 — Materialidade mínima

&emsp;Anomalias estatísticas sem volume ou impacto suficiente não devem gerar cards prioritários. Limites de tráfego, sessões, erros e duração devem ser configuráveis por fonte e métrica.

### RN-H10 — Reprodutibilidade

&emsp;Cada resultado deve guardar `run_id`, `sim_now`, watermarks ou LSNs consumidos, versão da regra, versão dos pesos e referências às evidências. Reexecutar com as mesmas entradas e configurações deve produzir o mesmo resultado.

### RN-H11 — Linguagem não conclusiva

&emsp;O frontend deve usar “possível”, “provável” ou “evidências sugerem”. Somente feedback ou ground truth humano pode alterar o estado para confirmado.

## 9. Catálogo inicial de hipóteses

### RN-H12 — Possível regressão após deploy

&emsp;Gerar candidato quando houver deploy anterior à anomalia e compatibilidade entre o alvo do deploy e a entidade afetada.

&emsp;Evidências favoráveis:

- deploy disponível antes do início do efeito;
- curta distância temporal;
- erros ou degradação surgindo após o deploy;
- propagação por componentes relacionados;
- ausência de causa externa mais específica.

&emsp;Um evento `autoscale.run` não comprova saturação, pois pode representar reaplicação de regra em lote.

### RN-H13 — Possível falha interna de backend ou API

&emsp;Gerar candidato quando as anomalias se propagarem pela cadeia interna, como RPaaS, Apollo, New Relic, Prometheus, Redis ou dependências.

&emsp;Indicadores incluem aumento de 5xx, latência, erros GraphQL, falhas de dependência e queda de Apdex. Para Apdex, valores menores representam piora.

### RN-H14 — Possível falha de playback ou autorização

&emsp;Gerar candidato quando houver aumento de 4xx nos vhosts de playback, crescimento de `startup_errors`, erros classificados como acesso ou atribuição `playback_api`.

&emsp;Taxas elevadas de 4xx fora do catálogo de playback podem ser comportamento estrutural e não devem, isoladamente, gerar a hipótese.

### RN-H15 — Possível degradação de CDN

&emsp;Gerar candidato quando sinais de CDN estiverem anômalos e houver impacto correspondente na experiência do usuário. A assinatura mais forte é a degradação de CDN e QoE no mesmo canal.

&emsp;Entidades de CDN com tier de maior audiência devem receber impacto superior. Zeros emitidos pelos gates de CDN não devem ser tratados como prova forte de ausência de erro.

### RN-H16 — Possível falha de origem ou encoding

&emsp;Gerar candidato quando `origin_live_errors` ou erros classificados como origem coincidirem com degradação no mesmo canal. O sistema deve distinguir entrega/CDN de defeitos de empacotamento, encoder ou stream.

### RN-H17 — Possível falha regional, ISP ou last-mile

&emsp;Gerar candidato quando erros estiverem concentrados em UF e operadora, outras operadoras permanecerem normais ou houver atribuição `edge_isp`.

&emsp;Uma medida de especificidade pode usar lift:

\[
lift = \frac{participação\ do\ recorte\ nos\ erros}{participação\ do\ recorte\ nas\ sessões}
\]

### RN-H18 — Possível ataque ou bloqueio de WAF

&emsp;Gerar candidato quando `ca_blocked_rps` aumentar antes ou junto da degradação e o app protegido for compatível com as entidades afetadas. Essa causa pode explicar crescimento de tráfego e CPU sem regressão interna.

### RN-H19 — Possível regressão de player ou dispositivo

&emsp;Gerar candidato quando a degradação estiver concentrada em player, plataforma ou modelo e os demais segmentos permanecerem próximos do baseline. A hipótese pode ser sustentada por uma única fonte quando possuir volume suficiente.

### RN-H20 — Possível regressão de QoE sem erro explícito

&emsp;Taxa de erro normal não descarta degradação de experiência. Aumento de `jointime`, `bufferratio`, `stalls`, latência ou frames perdidos pode sustentar a hipótese.

### RN-H21 — Pico associado a evento ao vivo

&emsp;Quando houver `gold.live_event_window`, aumento de audiência e ausência de degradação proporcional, o sistema deve produzir contexto de pico esperado e reduzir o peso de hipóteses baseadas apenas em volume.

&emsp;A existência de jogo não descarta um incidente ocorrido durante a transmissão. Se QoE e erros também piorarem, as hipóteses de falha continuam válidas.

### RN-H22 — Possível falha ou atraso de fonte

&emsp;Quando o canário indicar atraso, ausência ou divergência de uma fonte, o sistema deve gerar uma hipótese de qualidade de dados e impedir que o desaparecimento do sinal seja interpretado automaticamente como incidente de produção.

## 10. Proteções contra falsos positivos

### 10.1 RPaaS amostrado

&emsp;Contagens absolutas do RPaaS não representam o volume real quando a origem está amostrada. Devem ser priorizadas taxas, e buckets com volume insuficiente não devem sustentar hipóteses.

### 10.2 Artefatos de memória

&emsp;Valores de memória que sejam potências exatas de dois e maiores ou iguais a 256 MiB podem representar limite de cgroup. Eles devem ser marcados como possíveis artefatos.

### 10.3 Direção da anomalia

&emsp;O motor não deve assumir globalmente que apenas aumentos representam falha. Queda de sessões e de Apdex pode ser incidente, enquanto redução de latência geralmente não é.

### 10.4 Categorias desconhecidas

&emsp;Valores como `"(desconhecido)"` e `"?"` representam ausência de informação e não devem produzir hipóteses atribuídas a um segmento chamado “desconhecido”.

### 10.5 Ground truth circular

&emsp;Rótulos `detector-derived` não devem ser usados como verdade independente para avaliar o mesmo detector ou treinar o futuro modelo.

## 11. Score explicável

### 11.1 Features

&emsp;Cada regra transforma suas evidências em features normalizadas entre 0 e 1.

| Feature | Símbolo | Interpretação |
|---|---:|---|
| Força da anomalia | `A` | Distância do valor observado para o baseline. |
| Proximidade temporal | `T` | Proximidade entre causa candidata e efeito. |
| Corroboração | `C` | Concordância entre fontes ou sinais independentes. |
| Especificidade | `E` | Concentração da falha em um recorte. |
| Impacto | `I` | Audiência, sessões ou entidades relevantes afetadas. |
| Contradição | `X` | Força das evidências contrárias. |
| Qualidade | `Q` | Saúde, completude e atualidade das fontes. |

&emsp;Uma configuração heurística inicial pode usar:

\[
score = 100 \times \frac{\sum w_i f_i}{\sum w_i} - penalidades
\]

&emsp;A soma deve considerar somente features aplicáveis e disponíveis. Os pesos iniciais são decisões de especialistas, não probabilidades aprendidas.

### 11.2 Onde entra o decaimento exponencial

&emsp;O decaimento exponencial é usado para calcular a feature `T`, depois que uma regra encontra uma causa candidata anterior ao efeito e antes do cálculo do score.

```text
anomalia detectada
      ↓
busca de causas candidatas disponíveis
      ↓
cálculo de Δt entre causa e início do efeito
      ↓
decaimento exponencial → feature T
      ↓
score da hipótese
```

&emsp;A função recomendada, expressa por meia-vida, é:

\[
T(\Delta t) = 2^{-\frac{\Delta t}{h}}
\]

&emsp;Onde `h` representa a quantidade de minutos necessária para a força temporal cair pela metade.

```python
from math import exp, log


def temporal_proximity(delta_minutes: float, half_life_minutes: float) -> float:
    if delta_minutes < 0:
        return 0.0
    return exp(-log(2) * delta_minutes / half_life_minutes)
```

&emsp;Com meia-vida de 15 minutos:

| Distância | Feature temporal |
|---:|---:|
| 0 min | 1,00 |
| 6 min | 0,76 |
| 15 min | 0,50 |
| 30 min | 0,25 |
| 45 min | 0,125 |

### 11.3 Restrições temporais do decaimento

&emsp;O cálculo deve usar o tempo de ocorrência para medir proximidade, mas a causa candidata só pode participar se já estivesse disponível:

```text
cause.event_at <= effect.event_at
cause.available_at <= run.sim_now
```

&emsp;Cada família pode configurar meia-vida e janela máxima diferentes:

```yaml
temporal_decay:
  deployment_to_anomaly:
    half_life_minutes: 15
    maximum_window_minutes: 120

  backend_to_qoe:
    half_life_minutes: 10
    maximum_window_minutes: 60

  waf_block_to_error:
    half_life_minutes: 5
    maximum_window_minutes: 30
```

&emsp;Se a hipótese não possuir evento causal identificável, `T` será `not_applicable` e seu peso será retirado do denominador. A hipótese não deve ser penalizada por isso.

### 11.4 Cobertura e confiança

- **score:** força relativa da hipótese;
- **cobertura:** proporção das evidências aplicáveis que estavam disponíveis;
- **confiança:** classificação derivada do score, cobertura e qualidade das fontes.

&emsp;Uma hipótese com score alto e baixa cobertura não deve ser apresentada como de alta confiança.

### 11.5 Evolução dos pesos

&emsp;Quando houver rótulos suficientes, as mesmas features poderão alimentar uma regressão logística:

\[
P(y=1) = \sigma(\beta_0 + \beta_1A + \beta_2T + \beta_3C + \beta_4E + \beta_5I - \beta_6X + \beta_7Q)
\]

&emsp;A evolução altera a forma de definir e calibrar os pesos, mas preserva as regras de disponibilidade temporal, a persistência das evidências e o contrato do frontend.

## 12. Persistência no PostgreSQL

&emsp;A persistência relacional permite manter execuções, hipóteses, evidências e feedbacks de forma auditável.

### 12.1 Execução do motor

```sql
CREATE TABLE gold.hypothesis_run (
    run_id              uuid PRIMARY KEY,
    detection_run_id    uuid NOT NULL,
    sim_now             timestamptz NOT NULL,
    started_at          timestamptz NOT NULL,
    completed_at        timestamptz,
    input_lsn           text,
    rules_version       text NOT NULL,
    weights_version     text NOT NULL,
    status              text NOT NULL,
    error_message       text
);
```

### 12.2 Hipótese

```sql
CREATE TABLE gold.hypothesis (
    hypothesis_id       uuid PRIMARY KEY,
    run_id              uuid NOT NULL REFERENCES gold.hypothesis_run(run_id),
    hypothesis_key      text NOT NULL,
    hypothesis_type     text NOT NULL,
    title               text NOT NULL,
    verdict             text,
    score               numeric(5,2) NOT NULL,
    coverage            numeric(5,4) NOT NULL,
    confidence          text NOT NULL,
    status              text NOT NULL,
    bucket_start        timestamptz NOT NULL,
    bucket_end          timestamptz NOT NULL,
    affected_scope      jsonb NOT NULL DEFAULT '{}',
    available_at        timestamptz NOT NULL,
    created_at          timestamptz NOT NULL,
    UNIQUE (run_id, hypothesis_key)
);
```

### 12.3 Evidência

```sql
CREATE TABLE gold.hypothesis_evidence (
    evidence_id         uuid PRIMARY KEY,
    hypothesis_id       uuid NOT NULL REFERENCES gold.hypothesis(hypothesis_id),
    evidence_type       text NOT NULL,
    relation            text NOT NULL,
    availability        text NOT NULL,
    feature_name        text,
    feature_value       numeric,
    weight              numeric,
    contribution        numeric,
    description         text NOT NULL,
    source_ref          jsonb,
    source_available_at timestamptz
);
```

### 12.4 Feedback

```sql
CREATE TABLE gold.hypothesis_feedback (
    feedback_id         uuid PRIMARY KEY,
    hypothesis_id       uuid NOT NULL REFERENCES gold.hypothesis(hypothesis_id),
    vote                text NOT NULL,
    corrected_verdict   text,
    corrected_causes    text[],
    critique            text,
    resolution          text,
    author_id           text NOT NULL,
    created_at          timestamptz NOT NULL
);
```

### 12.5 Idempotência

&emsp;O `hypothesis_key` deve ser derivado de campos estáveis, como tipo da hipótese, bucket, escopo e conjunto de achados. A restrição por `run_id` impede duplicação durante retry da mesma execução.

## 13. Orquestração do processamento

&emsp;Uma execução completa deve seguir uma ordem controlada:

1. o merge worker aplica mudanças até determinado watermark ou LSN;
2. o ETL atualiza silver e gold respeitando `available_at`;
3. o canário valida atualidade, completude e divergência por fonte;
4. o detector EWMA produz `detection_run` e anomalias;
5. o motor de hipóteses recebe o `detection_run_id` concluído;
6. o motor consulta somente contexto disponível em `sim_now`;
7. candidatos são gerados, pontuados e persistidos;
8. views tornam os resultados visíveis para a API;
9. métricas de execução e atraso são enviadas ao CloudWatch.

&emsp;O frontend não inicia esse processamento. Ele consulta o último run concluído e disponível para o relógio virtual atual.

## 14. Views e API de leitura

### 14.1 View de hipóteses disponíveis

```sql
CREATE VIEW gold.v_hypothesis_available AS
SELECT h.*
FROM gold.hypothesis h
JOIN sim.clock c ON true
WHERE h.available_at <= c.now
  AND h.status IN ('generated', 'confirmed', 'partially_confirmed');
```

&emsp;Na implementação real, o mecanismo de exposição do `sim.now` deve ser compatível com a forma escolhida para armazenar o relógio virtual e com o isolamento entre execuções.

### 14.2 Endpoints

```http
GET /api/v1/hypotheses?from=...&to=...&status=generated&type=...
GET /api/v1/hypotheses/{hypothesis_id}
POST /api/v1/hypotheses/{hypothesis_id}/feedback
```

&emsp;A listagem retorna título, score, cobertura, confiança, período, escopo e estado. O detalhe retorna fatores, evidências, achados e referências para abrir a timeline ou o recorte afetado.

## 15. Apresentação no frontend

### 15.1 Lista

&emsp;Cada card deve apresentar:

- score e confiança;
- título em linguagem não conclusiva;
- família da hipótese;
- escopo afetado;
- horário de início e fim;
- quantidade de fontes corroborando;
- cobertura das evidências;
- estado da investigação.

### 15.2 Detalhe

&emsp;O painel “Como este score foi calculado” deve mostrar:

- feature;
- peso;
- valor normalizado;
- contribuição em pontos;
- explicação textual;
- fonte e registro consultados;
- evidências contrárias;
- dados indisponíveis.

&emsp;Exemplo:

```text
Proximidade temporal — contribuiu 19,0 pontos

O deploy ocorreu 6 minutos antes do início da anomalia. Com meia-vida de
15 minutos, a evidência temporal recebeu força 0,76.
```

### 15.3 Navegação temporal

&emsp;Os botões “Abrir na timeline” e “Ver recorte afetado” devem manter o mesmo `sim.now` e a mesma janela da hipótese. O frontend não pode consultar dados posteriores apenas porque o relógio real avançou.

## 16. Feedback e rótulos

### RN-H23 — Toda hipótese investigada deve aceitar feedback

&emsp;O operador deve poder registrar `agree`, `partial` ou `disagree`, além de corrigir veredito, causas e escopo.

### RN-H24 — Feedback deve referenciar a execução original

&emsp;O rótulo deve permanecer ligado ao `run_id`, à versão da regra, à versão dos pesos e ao conjunto de evidências exibido ao usuário.

### RN-H25 — Ausência de feedback não é rótulo negativo

&emsp;Hipótese não investigada ou incidente sem ticket não deve ser considerado automaticamente incorreto.

### RN-H26 — Revisões devem ser preservadas

&emsp;Quando uma fonte atrasada disponibilizar nova evidência, o sistema deve criar nova tentativa ou novo run. A hipótese anterior e o que estava visível naquele momento devem permanecer auditáveis.

## 17. Avaliação

&emsp;A avaliação deve considerar:

- `precision@k` das hipóteses mais bem ranqueadas;
- alarmes falsos por dia simulado;
- tempo de detecção e lead time em relação às janelas de incidente;
- concordância humana por família de hipótese;
- cobertura média;
- impacto da indisponibilidade de fontes;
- estabilidade do ranking entre runs;
- comparação com o baseline atual do Argus.

&emsp;Não se recomenda acurácia global, pois a maioria dos buckets representa comportamento normal. Rótulos fora da janela de telemetria e rótulos derivados do próprio detector devem ser separados na avaliação.

## 18. Plano de implementação

### Etapa 1 — Contratos e persistência

- confirmar schemas de `silver.signal_point`, `gold.feature_bucket` e detecções;
- definir `event_at`, `captured_at`, `available_at` e `processed_at` em todas as camadas;
- criar tabelas `hypothesis_run`, `hypothesis`, `hypothesis_evidence` e `hypothesis_feedback`;
- criar índices por período, status, tipo e `run_id`.

### Etapa 2 — Núcleo do sistema especialista

- implementar objetos de achado, evidência e hipótese;
- implementar catálogo e interface comum das regras;
- implementar normalização das features;
- implementar score, cobertura e confiança;
- implementar decaimento exponencial configurável;
- garantir idempotência por `run_id` e `hypothesis_key`.

### Etapa 3 — Primeiro recorte vertical

- consumir anomalias de um `detection_run` concluído;
- implementar regressão após deploy;
- implementar degradação CDN/origem no mesmo canal;
- implementar regressão de player ou dispositivo;
- persistir evidências e fatores do score.

### Etapa 4 — API e frontend

- criar views com gate de `sim.now`;
- implementar listagem e detalhe na Lambda de leitura;
- implementar a tela específica de hipóteses;
- conectar timeline e recorte;
- implementar feedback.

### Etapa 5 — Ampliação e calibração

- adicionar backend/API, playback, ISP, WAF e eventos ao vivo;
- executar cenários determinísticos com seeds conhecidas;
- revisar pesos e meias-vidas com especialistas;
- coletar rótulos;
- avaliar futura regressão logística.

## 19. Critérios de aceite iniciais

1. Nenhuma hipótese utiliza registro com `available_at > run.sim_now`.
2. Cada hipótese referencia um `detection_run` concluído e ao menos uma anomalia.
3. Retry do mesmo run não duplica hipóteses ou evidências.
4. Pelo menos três famílias produzem resultados em cenários simulados determinísticos.
5. Score, cobertura, confiança, pesos e contribuições ficam persistidos.
6. Evidência ausente é diferenciada de evidência contrária.
7. O decaimento temporal utiliza meia-vida configurável e respeita uma janela máxima.
8. O frontend exibe os fatores e as fontes consultadas.
9. Timeline e recorte preservam o relógio virtual da hipótese.
10. O usuário consegue registrar feedback estruturado.
11. Uma fonte atrasada pode produzir revisão posterior sem alterar o run histórico.
12. A consulta usa resultados pré-calculados e atende à meta de resposta do dashboard.

## 20. Decisões em aberto

- forma definitiva de persistência e isolamento do `sim.clock`;
- frequência e dependências do EventBridge Scheduler;
- política de watermark entre merge, ETL, detector e hipóteses;
- contrato exato de `gold.feature_bucket`;
- formato de `gold.detection_anomaly` e identidade de achado;
- mapeamento de dependência entre entidades de fontes diferentes;
- meia-vida e janela máxima por família;
- limites de materialidade por fonte;
- política de revisão quando chega fonte atrasada;
- retenção de runs, hipóteses, evidências e feedbacks;
- responsáveis pela confirmação humana.

## 21. Rastreabilidade com os requisitos

&emsp;A funcionalidade está relacionada principalmente a:

- **RF14:** comparação com períodos anteriores;
- **RF15:** identificação de aumentos relevantes;
- **RF16:** informações para investigação;
- **RF17:** hipóteses ordenadas por relevância;
- **RNF02:** consultas do dashboard em até cinco segundos;
- **RNF08:** apresentação das evidências utilizadas;
- **RNF10:** proteção de informações sensíveis;
- **RNF11:** registros suficientes para investigação e auditoria.

&emsp;A arquitetura também exige requisitos específicos para causalidade temporal, idempotência de processamento, rastreabilidade por run, coleta de feedback e preservação de resultados históricos.

## Referências

- Globo e Inteli. *Argus — Documentação do Dataset*, versão 1.0, 2026.
- Globo e Inteli. *Anexo — Fontes de Dados: Monitoração Agêntica*, 2026.
- Diagrama da arquitetura-alvo fornecido pela equipe.

