# Testes de carga, resiliência e observabilidade

Este relatório demonstra a execução dos testes relacionados aos requisitos não funcionais definidos na Sprint 1. O conteúdo está organizado pelos três critérios de avaliação: planos de teste revisados, resultados com análise e visualização de indicadores de observabilidade.

Foram avaliados os dois fluxos de ingestão do Argus: eventos de frontend, processados pelo `event-worker`, e mudanças do CDC simulado, processadas pelo `merge-worker`. Ambos usam API Gateway, SQS e PostgreSQL.

| Item avaliado | Peso | Seção |
|---|---:|---|
| Requisitos não funcionais e planos revisados | 3,0 | Seção 1 |
| Resultados e análise de desempenho e resiliência | 4,0 | Seção 2 |
| Indicadores em Grafana e Prometheus | 3,0 | Seção 3 |

## Resultado executivo

| Requisito ou cenário | Resultado principal | Situação |
|---|---|---|
| RNF01 — capacidade | pico real de 10.000 eventos/min, p95 de 161,8 ms e 12.152/12.152 eventos persistidos | Aprovado |
| RNF02 — tempo de resposta | 4.587 consultas, nenhuma acima de 5 s e máximo de 1.581 ms | Tempo aprovado; base parcialmente representativa |
| RNF03 — escalabilidade | recursos e carga ampliados em 2×, com 3.203/3.203 eventos persistidos | Aprovado no fator 2× |
| RNF04 — eventos inválidos | 18/18 falhas identificadas e 150/150 eventos válidos processados | Aprovado |
| RNF05 — backlog no fluxo de eventos | fila 0→1.001→0 e banco +1.001 após recuperação | Aprovado |
| RNF05 — falhas no fluxo de mudanças | serviço recuperado após fila cheia e interrupção do worker, sem reconciliação total dos eventos | Parcialmente comprovado |
| RNF11 — registros de falha | causas específicas presentes na DLQ; faltam evidências completas de horário, etapa e ausência de dado sensível | Parcialmente comprovado |
| Observabilidade | latência, throughput, erros, CPU e filas visualizados com dados reais | Implementado e validado |

## 1. Requisitos não funcionais e planos de teste revisados (peso 3,0)

### 1.1 Método e ambiente

A carga foi gerada com k6 contra uma implantação real no AWS Academy Learner Lab, região `us-east-1`. As execuções de RNF01, RNF02 e RNF03 ocorreram em 2 de setembro de 2026 com a imagem ARM64 `66b4fbe59313`. As métricas do cliente foram enviadas ao Prometheus por Remote Write; métricas de API Gateway, SQS, ECS e RDS vieram do CloudWatch e foram visualizadas no Grafana.

Os valores estruturados estão em [`assets/performance/evidencias-2026-09-02.json`](assets/performance/evidencias-2026-09-02.json). Logs completos do k6 ficam em `apps/basica/tests/carga/resultados/`, diretório ignorado pelo Git. Nenhuma credencial, token ou endpoint foi versionado.

Este relatório distingue três estados:

- **Preparado:** cenário e automação existem no repositório.
- **Executado:** o teste foi realizado contra uma implantação real.
- **Comprovado:** a execução possui métricas e reconciliação suficientes para sustentar a conclusão.

### 1.2 Planos revisados

| RNF | Objetivo | Cenário | Critérios de aceite | Evidência necessária |
|---|---|---|---|---|
| RNF01 | verificar capacidade de ingestão | 1.000 eventos/min, pico de 10.000/min e recuperação em 1.000/min | disponibilidade, sucesso HTTP, p95 dentro do limite e zero descarte | total aceito igual ao persistido após drenagem da fila |
| RNF02 | verificar tempo de consultas simples | 11 rotas repetidas cinco vezes, 10 usuários concorrentes e 600 consultas/min | todas as respostas em até 5 s e filtros corretos | resumo k6 e caracterização da base consultada |
| RNF03 | verificar crescimento sem mudar o contrato | mesmos eventos com recursos 1×/2× e carga 1.000/2.000 eventos/min | vazão mínima de 2×, sucesso ≥99%, p95 <5 s e zero descarte | recursos registrados e total emitido igual ao persistido |
| RNF04 | impedir que evento inválido interrompa os válidos | lote misto com erros de campo, formato, operação, tabela e chave | inválidos identificados e válidos anteriores e posteriores processados | motivo na DLQ e contagem dos eventos válidos |
| RNF05 | verificar recuperação após falha temporária | consumidor parado com backlog, interrupção forçada do worker e timeout do cliente | retomada do serviço, tempo de recuperação registrado e ausência de perda silenciosa | aceitos reconciliados com banco ou filas de reprocessamento |
| RNF11 | verificar utilidade dos registros de falha | evento incompleto, formato incorreto e indisponibilidade temporária | horário, etapa, indicação do erro, cenários distinguíveis e ausência de dado sensível | amostra sanitizada dos registros na janela do teste |

### 1.3 Decisões da revisão

- O mínimo do RNF01 continua sendo 1.000 eventos/min. O pico de 10.000 eventos/min foi acrescentado como cenário realista de estresse.
- Como SQS Standard não possui capacidade máxima fixa, “fila cheia” foi representada por consumidor indisponível e backlog crescente.
- Timeout de processamento e timeout do cliente são cenários distintos. Apenas a interrupção do worker representa falha interna de processamento.
- Resposta HTTP 2xx comprova aceitação pela fila, não persistência. Ausência de perda exige reconciliação com banco e filas.
- Os dashboards atendem ao critério visual da entrega, mas não substituem os campos de registro exigidos pelo RNF11.

## 2. Resultados e análise de desempenho e resiliência (peso 4,0)

### 2.1 RNF01 — capacidade de ingestão

**Objetivo.** Aceitar o volume nominal, um pico de 10.000 eventos/min e a recuperação sem indisponibilidade ou perda.

**Execução.** Rodada `rnf01-final-20260902T193419Z`, entre 19:34:19 e 19:38:40 UTC.

**Critérios e resultados.**

| Fase | Taxa | Aceitos | Erros | p95 | Descartes |
|---|---:|---:|---:|---:|---:|
| Nominal | 1.000/min | 1.001 | 0 | 188,6 ms | 0 |
| Pico | 10.000/min | 10.000 | 0 | 161,8 ms | 0 |
| Recuperação | 1.000/min | 1.000 | 0 | 170,0 ms | 0 |

**Análise.** O Prometheus registrou pico de 167,10 req/s, valor coerente com 10.000 eventos/min. Incluindo o aquecimento, foram aceitos 12.152 eventos. `bronze.event` cresceu de 12.154 para 24.306 linhas e a fila terminou sem mensagens visíveis ou em voo. A reconciliação de 12.152/12.152 sustenta a aprovação do RNF01.

### 2.2 RNF02 — tempo de resposta

**Objetivo.** Responder consultas simples em até cinco segundos e respeitar os filtros aplicados.

**Execução.** Rodada `rnf02-final-20260902T194059Z`, entre 19:40:59 e 19:47:00 UTC.

**Critérios e resultados.**

| Métrica | Resultado | Critério |
|---|---:|---:|
| Consultas | 4.587 | 11 rotas, repetição e concorrência previstas |
| Sucesso HTTP | 100% | 100% |
| Respostas acima de 5 s | 0% | 0% |
| p95 | 181,2 ms | <3 s |
| maior p99 | 1.412,5 ms | <5 s |
| máximo individual | 1.581 ms | ≤5 s |
| filtros corretos | 100% | 100% |

**Análise.** O limite temporal foi atendido com ampla margem. A base tinha aproximadamente 24 mil eventos sintéticos variados e validou contratos, filtros e concorrência, mas sua representatividade em volume e cardinalidade para o MVP não foi demonstrada. Por isso, o tempo está aprovado e a precondição da base permanece parcial.

### 2.3 RNF03 — escalabilidade

**Objetivo.** Dobrar a capacidade sem alterar endpoint ou formato dos eventos.

**Execução.** O mesmo script e contrato foram usados com uma e duas tasks por worker.

**Critérios e resultados.**

| Métrica | Baseline 1× | Escalado 2× |
|---|---:|---:|
| Taxa alvo | 1.000/min | 2.000/min |
| Aceitos na medição | 1.000 | 2.001 |
| Sucesso | 100% | 100% |
| p95 | 185,7 ms | 178,1 ms |
| p99 | 213,8 ms | 218,7 ms |
| Descartes | 0 | 0 |
| Total com aquecimento | 1.101 | 2.102 |
| Persistidos | 1.101 | 2.102 |
| CPU ECS máxima | 42,12% | 38,80% |

**Análise.** A vazão e os recursos dobraram, sem mudança de contrato, perda ou degradação relevante de latência. O RNF03 está aprovado para 2×. O ensaio não determina o ponto de saturação e não comprova fatores de 5× ou 10×.

### 2.4 RNF04 — tratamento de eventos inválidos

**Objetivo.** Identificar o evento incorreto sem interromper eventos válidos do mesmo lote.

**Execução.** Foram enviados casos de tabela ausente ou desconhecida, operação inválida, chave vazia, atualização sem conteúdo e corpo JSON malformado, misturados a eventos válidos.

**Critérios e resultados.**

| Critério | Resultado |
|---|---|
| Casos inválidos identificáveis | 18/18 com causa específica na DLQ |
| Eventos válidos preservados | 150/150 confirmados no log de mudanças |
| Continuidade do worker | nenhuma interrupção ou reinício pelo payload inválido |

| Exemplo de falha | Motivo registrado |
|---|---|
| chave primária vazia | `pk vazia: o MERGE nao tem como identificar a linha` |
| tabela desconhecida | `tabela desconhecida: 'tabela_fantasma_k6'. Tabela nova exige migration` |
| operação inválida | `Input should be 'i', 'u', 'd' or 'r'` |
| campo ausente | `source_table: Field required` |
| atualização sem conteúdo | `op='u' exige after, que veio vazio` |

**Análise.** A rejeição ocorreu por item e registrou uma causa consultável, enquanto os eventos válidos continuaram sendo processados. Isso sustenta a aprovação do RNF04.

### 2.5 RNF05 — recuperação após falha temporária

**Objetivo.** Retomar o processamento depois de uma falha controlada sem perder silenciosamente eventos aceitos.

**Execução.** Foram realizados quatro cenários complementares.

**Critérios e resultados.**

| Cenário | Resultado | Análise | Situação |
|---|---|---|---|
| Backlog no fluxo de mudanças | 96.020 eventos aceitos; p95 de 266 ms; fila drenada em cerca de 16 min | comprova aceitação e retomada, mas não reconcilia os 96.020 eventos com banco e DLQ | Parcial |
| Interrupção do `merge-worker` | 28.800 eventos aceitos; task reiniciada automaticamente; fila principal zerada | comprova recuperação do serviço, mas não reconcilia todos os aceitos | Parcial |
| Backlog no fluxo de eventos | fila 0→1.001→0; banco 27.509→28.510 | reconciliação de 1.001/1.001 comprova recuperação sem perda nesse recorte | Aprovado |
| Timeout do cliente | 100/100 requisições expiraram com limite de 1 ms; depois 5/5 responderam 200, p95 de 1.631,7 ms | comprova detecção e recuperação do cliente, não timeout interno da Lambda | Aprovado no escopo |

**Análise.** O sistema retomou o processamento nos cenários executados. A ausência de perda está comprovada no recorte de 1.001 eventos; os ensaios maiores permanecem parciais porque drenagem da fila, isoladamente, não substitui reconciliação entre aceitos, persistidos e rejeitados.

## 3. Visualização dos indicadores de observabilidade (peso 3,0)

### 3.1 Stack e indicadores

A stack local unificada usa Prometheus e Grafana em `apps/basica/observability/`. O Prometheus recebe métricas k6; o Grafana provisiona os dashboards **Argus — Testes de Carga (RNF01/02/03)** e **RNF04/05/11 — Resiliência Argus**, com Prometheus e CloudWatch como fontes.

| Indicador solicitado | Fonte | Visualização e evidência |
|---|---|---|
| Latência | k6/Prometheus e API Gateway/CloudWatch | p50, p90, p95 e p99 por rota e cenário; valores de RNF01–RNF03 e captura real de resiliência |
| Throughput | k6/Prometheus e API Gateway/CloudWatch | req/s e total; pico real de 167,10 req/s no RNF01 e captura da sessão de resiliência |
| Erros por segundo | k6/Prometheus e API Gateway/CloudWatch | respostas inesperadas, 4xx e 5xx por janela de teste |
| Uso de CPU | ECS e RDS/CloudWatch | média e máximo por serviço e instância; pico de 78,02% no `event-worker` durante RNF01 |
| Filas | SQS/CloudWatch | mensagens visíveis, mensagens em voo e idade da mais antiga durante crescimento e drenagem |

As métricas são reais. O Prometheus representa o ponto de vista do cliente k6; o CloudWatch representa aplicação e infraestrutura. Na execução de 2 de setembro, foram confirmadas via API entre 74 e 92 séries Prometheus por teste, separadas pela etiqueta `testid`.

### 3.2 Evidências visuais

<div align="center">

<sub>Figura 1 — Crescimento e drenagem da fila de mudanças e comportamento da DLQ</sub>

![Painel Grafana com fila changes e DLQ](./assets/captura_dashboard_fila_changes_dlq.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

<div align="center">

<sub>Figura 2 — Latência p50, p90 e p99 da rota de ingestão durante a carga</sub>

![Painel Grafana com latência da ingestão](./assets/captura_dashboard_latencia.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

<div align="center">

<sub>Figura 3 — CPU dos serviços ECS durante desligamento e recuperação do worker</sub>

![Painel Grafana com CPU dos serviços ECS](./assets/captura_dashboard_cpu_ecs.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

<div align="center">

<sub>Figura 4 — Throughput e erros 4xx/5xx durante a sessão de resiliência</sub>

![Painel Grafana com throughput e erros](./assets/captura_dashboard_throughput.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

<div align="center">

<sub>Figura 5 — Utilização de CPU da instância RDS</sub>

![Painel Grafana com CPU da instância RDS](./assets/captura_dashboard_cpu_rds.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

As cinco capturas comprovam a visualização real dos indicadores do fluxo de mudanças. O dashboard dos RNF01–RNF03 foi validado por API e pelas séries persistidas, mas não possui captura da execução original. Essa limitação não altera os resultados numéricos, porém impede tratá-lo como evidência visual completa.

### 3.3 Limite da cobertura do RNF11

Os dashboards comprovam capacidade de observação operacional. A DLQ também diferencia causas de payload inválido. Entretanto, não foram preservadas amostras suficientes para verificar horário, etapa afetada e ausência de dado sensível em todos os cenários de indisponibilidade; por isso o RNF11 permanece parcialmente comprovado.

## 4. Conclusão

Os três itens da entrega estão contemplados: os planos foram revisados com pico de 10.000 eventos/min, backlog e timeout; os resultados apresentam métricas e análise de desempenho e resiliência; e Grafana, Prometheus e CloudWatch exibem latência, throughput, erros, CPU e filas com dados reais.

RNF01, RNF03 e RNF04 foram comprovados nos fatores testados. O RNF02 atendeu ao limite de tempo, com ressalva sobre representatividade da base. No RNF05, a recuperação foi observada em todos os cenários, mas apenas o recorte de 1.001 eventos possui reconciliação completa. O RNF11 permanece parcial por falta de uma amostra completa e sanitizada dos registros. Essas limitações são mantidas explícitas para separar resultado observado de conclusão comprovada.
