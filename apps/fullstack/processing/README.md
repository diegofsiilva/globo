# Processamento, detecção e geração de hipóteses

Este diretório contém o backend determinístico de análise do Argus. O código do
repositório é a fonte de verdade; a imagem que ainda estiver executando na AWS
pode estar defasada.

O serviço ECS `processing` executa três threads no mesmo processo:

1. Bronze → Silver e materialização append-only dos fatos de análise;
2. Silver → Gold e publicação de checkpoints;
3. canário, detector, regras, score e persistência de hipóteses.

Não há classificador supervisionado, LLM, fila adicional ou serviço contínuo
novo. Uma hipótese é uma explicação candidata e auditável para revisão humana,
não uma causa-raiz confirmada.

## Estado da implementação

As migrations `016_gold_checkpoint.sql` e `017_analysis_coordination.sql` são o
baseline concluído de checkpoint, claim, lease, heartbeat, takeover e fencing.
Elas não devem ser alteradas.

O restante do contrato está implementado em:

| Migration | Contrato |
|---|---|
| `018_analysis_inputs.sql` | `silver.analysis_fact_version`, canonicalização por mudança do `change_log`, tombstones e barreira de LSN na Gold. |
| `019_detection_contract.sql` | manifesto, cursor serial, fotografia de entrada, baseline circadiano e anomalias explicáveis. |
| `020_source_quality.sql` | execução e resultado do canário por fonte. |
| `021_hypothesis_engine.sql` | grupos, hipóteses, evidências, features, feedback, revisões e estatísticas. |
| `022_hypothesis_views.sql` | views públicas temporais e função estreita de feedback. |

Os fatos de análise são derivados diretamente de `bronze.change_log`. Isso é
necessário para conservar duas mudanças da mesma PK que cheguem antes do próximo
ciclo do ETL. A tabela é append-only por trigger; `TRUNCATE` continua disponível
para rebuild administrativo e testes.

## Fluxo consistente

```text
change_log append-only
       ↓
analysis_fact_version (fact_key, version_lsn)
       ↓
gold_checkpoint (ready_through, source_lsn)
       ↓
claim + captura REPEATABLE READ
       ↓
run_input_fact + input_digest
       ↓
canário → EWMA → anomalias → 11 regras → score
       ↓
commit protegido por fencing
       ↓
views sombra/publicadas → Lambda
```

O claim:

- trava o cursor de `manifest_hash + stream_key`;
- escolhe o checkpoint mais antigo ainda não concluído;
- define `run.sim_now = checkpoint.ready_through`;
- define `run.input_lsn = checkpoint.source_lsn`;
- escolhe a última versão de cada fato com `version_lsn <= input_lsn` e
  `available_at <= sim_now`;
- persiste as referências exatas em `detect.run_input_fact` e calcula um digest
  canônico;
- libera a transação antes dos cálculos mais longos.

Retries usam o mesmo `input_lsn` e `sim_now`. Digest diferente encerra a tentativa
com `input_digest_mismatch` e não avança o cursor. Mais de 250 mil fatos encerra a
tentativa com `input_limit_exceeded`; entradas nunca são truncadas silenciosamente.

O processamento usa lease de 120 segundos e heartbeat de 30 segundos. Baseline,
qualidade, anomalias, hipóteses, estatísticas e avanço do cursor são confirmados
na mesma transação de `commit_protegido`. Um worker zumbi não consegue publicar.

## Fatos canônicos

`silver.analysis_fact_version` representa:

- `signal_bucket` para séries já canônicas de Prometheus, New Relic, Apollo,
  Cloud Armor e demais fontes;
- RPaaS apenas como volume e taxas 4xx/5xx;
- deploys e eventos do Tsuru;
- player, dispositivo e geo por hora;
- QoE ao vivo, sessões ativas e atribuição/categoria de erros;
- eventos editoriais ao vivo.

Restrições dos dados reais:

- UF e ISP são dimensões marginais separadas; não existe `UF × ISP`;
- percentis de latência do RPaaS não participam porque são nulos;
- RPaaS 4xx só sustenta playback em vhost explicitamente catalogado;
- NPAW/Youbora tem atraso causal de 28 horas;
- valores `?` e `(desconhecido)` não formam escopo;
- ground truth de incidentes não entra nos fatos nem no score online.

## Detector e qualidade

O detector usa EWMA causal com `alpha=0,20`, separado em 24 slots BRT. O bucket
é avaliado antes de atualizar o estado. Cada slot aquece por 12 observações.

```text
sigma = max(sqrt(variância), piso da métrica, 5% de |esperado|)
anomalia: |z| >= 3,5
força A: min(|z| / 6, 1)
```

Contagens e latências usam `log1p`; taxas, percentuais e Apdex permanecem na
escala original. Materialidade e direção vêm de `catalogs/metrics.json`.
Melhorias só geram anomalia para métricas marcadas como bidirecionais.

O canário calcula freshness, completeness, validity e consistency. O score é:

```text
Q = 0,35 freshness + 0,35 completeness + 0,15 validity + 0,15 consistency
```

Estados: `healthy`, `delayed`, `incomplete`, `silent`, `invalid` e `unknown`.
O `t1` congelado de um replay limita a janela e não cria silêncio artificial.

## As 11 famílias

| Família | Regra central |
|---|---|
| `deploy_regression` | Deploy explicitamente relacionado, anterior ao efeito e até 60 min; meia-vida de 15 min. |
| `backend_internal` | Erro, latência ou Apdex interno em ±15 min; RPaaS 4xx isolado é descartado. |
| `playback_authorization` | 4xx de vhost de playback, acesso, atribuição ou startup error; taxas exigem volume 100. |
| `cdn_degradation` | Erro de CDN obrigatório; QoE independente corrobora e origem anterior reduz especificidade. |
| `origin_encoding` | Origem precede/coincide com CDN ou QoE; downstream anterior contradiz. |
| `regional_or_isp` | Uma UF ou um ISP, 500 sessões, lift 2 e diferença 1 pp contra pares saudáveis. |
| `waf_block` | Bloqueio do Cloud Armor precede o impacto em até 15 min; impacto anterior contradiz. |
| `player_or_device` | Player ou dispositivo separados, 200 sessões, lift 2 e diferença 1 pp. |
| `qoe_without_error` | QoE degradada com métrica de erro disponível e normal; indisponibilidade é insuficiência. |
| `expected_live_peak` | Volume alto dentro de evento compatível, somente com erro e QoE normais; `kind=context`. |
| `source_data_delay` | Canário ruim gera `kind=data_quality`, nunca queda operacional inventada. |

Joins entre fontes usam chave normalizada exata, alias ou relação explicitamente
versionada em `catalogs/entity_relations.json`; não há fuzzy matching. Todas as
fontes NPAW compartilham o mesmo grupo de independência.

## Score, cobertura e revisão

O agrupamento é determinístico e não exclusivo. Para corroboração, só a evidência
mais forte de cada grupo de independência participa:

```text
C = 1 - produto(1 - força × alinhamento × qualidade)
T = 2^(-delta_minutos / meia_vida)
```

Pesos: `A=0,25`, `T=0,20`, `C=0,20`, `E=0,15`, `I=0,15`, `Q=0,05`, com
penalidade `30X`. Features indisponíveis reduzem cobertura; não viram zero nem
contradição. `X >= 0,80` descarta. Evidência required ausente produz
`insufficient_evidence`.

Uma hipótese é `generated` com score ≥ 40, cobertura ≥ 0,50 e sem contradição
determinante. Confiança alta exige score ≥ 80, cobertura ≥ 0,80 e Q ≥ 0,70;
média exige score ≥ 60 e cobertura ≥ 0,60.

Limites por run: 10 mil candidatos, 2 mil por família e 500 hipóteses geradas.
O corte estável usa força, impacto e chave canônica e é auditado em
`gold.hypothesis_run_stats`.

`evaluation_status` é imutável (`generated`, `insufficient_evidence`,
`discarded`). `review_status` é derivado do feedback (`unreviewed`, `confirmed`,
`partially_confirmed`, `rejected`). Evidência tardia cria nova revisão e aponta
`supersedes_hypothesis_id`; revisões anteriores não são atualizadas.

## API e segurança

As views públicas só mostram runs concluídos de manifestos publicados, a revisão
mais recente elegível e evidência disponível até `run.sim_now`.

Endpoints:

- `GET /api/v1/hypothesis-runs`;
- `GET /api/v1/hypotheses` com filtros e paginação keyset;
- `GET /api/v1/hypotheses/{id}`;
- `POST /api/v1/hypotheses/{id}/feedback`.

O feedback exige UUID de idempotência, devolve 201 na criação e 200 no replay.
Reuso da chave com payload diferente devolve conflito. `reviewer_verified` é
sempre `false`. O payload máximo é 4 KiB e a rota tem throttle 5 req/s, burst 10.

`argus_reader` recebe somente `SELECT` nas views e `EXECUTE` em
`gold.submit_hypothesis_feedback`. A função é `SECURITY DEFINER`, fixa
`search_path`, valida o payload e exige hipótese publicada. Não há permissão nas
tabelas base.

## Configuração operacional

| Variável | Default |
|---|---:|
| `ANALYSIS_ENABLED` | `true` |
| `ANALYSIS_POLL_SECONDS` | `30` |
| `ANALYSIS_LEASE_SECONDS` | `120` |
| `ANALYSIS_HEARTBEAT_SECONDS` | `30` |
| `ANALYSIS_MAX_INPUT_ROWS` | `250000` |
| `ANALYSIS_MAX_CANDIDATES` | `10000` |
| `ANALYSIS_MAX_CANDIDATES_PER_FAMILY` | `2000` |
| `ANALYSIS_MAX_GENERATED` | `500` |

O pool do processamento permite oito conexões. A task começa com 512 CPU e
1.024 MiB. O replay deve ser repetido com 1.024 CPU/2.048 MiB se ultrapassar 70%
de CPU, 80% de memória ou não terminar antes do próximo checkpoint.

A imagem inclui o runner e os SQLs. `aws_ecs_task_definition.migration` aplica
migrations na VPC e security group atuais; o RDS não precisa ser aberto ao IP
local. `terraform output migration_run_command` imprime o comando de execução.

Métricas EMF incluem runs, duração, input, anomalias, hipóteses por status,
truncamento, takeover, fencing, backlog e lag simulado. Alarmes cobrem três
falhas consecutivas, takeover por lease expirado, backlog de três checkpoints,
truncamento e 30 minutos sem run concluído.

## Sombra e promoção

1. publicar a imagem com análise habilitada;
2. não publicar o manifesto ainda;
3. reiniciar o simulador em `t0` e executar replay causal completo;
4. inspecionar runs e hipóteses internos enquanto as views permanecem vazias;
5. executar `analysisctl evaluate-and-promote` com as medições do replay;
6. usar `analysisctl withdraw` para ocultar append-only sem apagar histórico.

Exemplo:

```bash
analysisctl evaluate-and-promote \
  --suite-ok \
  --precision-at-5 0.65 \
  --api-p95-ms 1200 \
  --api-max-ms 2400 \
  --checkpoint-sla-ok
```

O comando recusa promoção se houver falha, divergência de digest, violação
temporal, truncamento, família ausente, precision@5 abaixo de 0,60, API fora de
3 s p95/5 s máximo ou processamento mais lento que o checkpoint seguinte.

## Desenvolvimento e verificação

```bash
make -C apps/fullstack db-local
make -C apps/fullstack test-processing
make -C apps/fullstack test-backend

cd apps/fullstack/processing
uv run ruff check .
uv run ruff format --check .

cd ../infra
terraform fmt -check
terraform validate
```

A suíte cobre instalação limpa, upgrade 017→022, versionamento e tombstones,
EWMA causal (cold start, variância zero, transformação, direção e
materialidade), qualidade por cadência, atraso estrutural da NPAW e fim do
simulador, as 11 famílias em quatro cenários cada (positivo, contraditório,
indisponível e semanticamente não relacionado), determinismo e budgets,
captura as-of, retry, takeover, fencing, latência causal de 28 h, revisão
append-only, exclusão do ground truth, portão de promoção, publicação sombra e
feedback público.
Nenhuma rotina automática de expurgo está habilitada; retenção será definida
depois de medir o volume real dos novos artefatos.
