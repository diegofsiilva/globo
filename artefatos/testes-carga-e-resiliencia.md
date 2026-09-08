# Testes de carga e resiliência (RNF01, RNF02, RNF03, RNF04, RNF05, RNF11)

&emsp; Este documento registra a execução e os resultados dos testes de carga e resiliência da plataforma Argus, cobrindo os dois fluxos de ingestão independentes descritos em `plano-argus-v3.md`: o fluxo de eventos de frontend (API Gateway, fila `events`, `event worker`) e o fluxo de mudanças do CDC simulado (API Gateway, fila `changes`, `merge worker`), ambos gravando no mesmo PostgreSQL com as camadas bronze, silver e gold. O objetivo é duplo: comprovar que o sistema aceita o volume e o pico de tráfego exigidos com tempo de resposta controlado (RNF01, RNF02, RNF03), e comprovar que uma falha, seja um evento malformado ou uma interrupção de infraestrutura, não derruba o sistema nem causa perda silenciosa de dado (RNF04, RNF05). O documento cobre ainda a verificação de integridade dos marcadores incrementais do ETL e a visualização implementada para acompanhar latência, throughput, erros e uso de CPU (RNF11).

## Resultado executivo

| Requisito | Evidência principal | Resultado |
|---|---|---|
| RNF01 (capacidade de ingestão) | pico real de 10.000 eventos/min, p95 161,8 ms, 100% aceito, 0 descarte e persistência 12.152/12.152 | Aprovado |
| RNF02 (tempo de resposta) | 4.587 consultas, 11 rotas, 10 usuários, 600/min, 0% acima de 5 s, máximo 1.581 ms | Aprovado |
| RNF03 (escalabilidade) | recursos 1×→2×, carga 1.000→2.000/min, 100% aceito, 3.203/3.203 persistidos | Aprovado no fator 2× |
| RNF04 (eventos inválidos, pipeline de mudanças) | 18/18 casos inválidos identificados na fila de rejeitados, 150/150 eventos válidos confirmados, zero perda | Aprovado |
| RNF05 (fila cheia, pipeline de mudanças) | 96.020 eventos aceitos, 100% sucesso, fila drenada em ~16 min sem crescer a fila de rejeitados | Aprovado |
| RNF05 (timeout de processamento, pipeline de mudanças) | 28.800 eventos aceitos, tarefa reiniciada sozinha, sem perda nem entrada indevida na DLQ | Aprovado |
| RNF05 (backlog, pipeline de eventos) | workers 1→0→1, fila 0→1.001→0, banco +1.001 após recuperação | Aprovado |
| RNF05 (timeout de cliente, pipeline de eventos) | 100 timeouts induzidos; 5/5 consultas recuperadas, p95 1.631,7 ms | Aprovado |
| Cenário aprofundado (fila cheia + evento inválido) | causa específica na DLQ em ~45 s, fila principal ainda em milhares de mensagens | Aprovado |
| Watermarks do ETL | 853 execuções bem sucedidas somadas, zero regressão | Aprovado |
| RNF11 (observabilidade) | dashboard de resiliência com 5 painéis validados com dado real; dashboard de carga com 8 painéis, 74–92 séries/teste confirmadas via API | Parcialmente comprovado (ver seção 10) |

&emsp; Esta tabela consolida a evidência das duas frentes de teste da sprint, executadas por integrantes diferentes da equipe sobre os dois pipelines de ingestão do sistema: a frente de capacidade e tempo de resposta (RNF01–03), medida contra o fluxo de eventos de frontend, e a frente de resiliência (RNF04, RNF05, RNF11), medida majoritariamente contra o fluxo de mudanças do CDC, com um complemento de RNF05 também sobre o fluxo de eventos. As seções a seguir detalham cada um separadamente.

## 1. Ferramental e ambiente

&emsp; A carga foi gerada com K6, escolhido por suportar taxa de chegada constante de requisições e por rodar tanto localmente quanto em container, sem depender de infraestrutura adicional. Os RNF01 a RNF03 têm como alvo a rota de ingestão de eventos de frontend e a API de leitura; os RNF04 e RNF05 (pipeline de mudanças) têm como alvo a rota de ingestão de mudanças, que aceita o evento, grava numa fila e devolve a confirmação de forma assíncrona, antes de qualquer validação de conteúdo.

&emsp; A execução de RNF01, RNF02 e RNF03 aconteceu em 2 de setembro de 2026 contra uma implantação real do Argus no AWS Academy Learner Lab (`us-east-1`), com as imagens ARM64 da aplicação publicadas sob a tag imutável `66b4fbe59313` e migrations e serviços ECS validados antes da carga. Nenhuma credencial, token ou endpoint foi incluído neste artefato; os valores estruturados dessa execução estão em [`assets/performance/evidencias-2026-09-02.json`](assets/performance/evidencias-2026-09-02.json), e logs e summaries completos do k6 ficam em `apps/basica/tests/carga/resultados/` (gitignored). As credenciais temporárias do Learner Lab usadas nessa execução expiraram junto com a sessão: reproduzir a coleta exige um perfil novo e, para o CloudWatch no Grafana, reiniciar o datasource.

&emsp; A visualização une CloudWatch e Prometheus num único Grafana local. As quatro métricas exigidas pelo RNF11 (latência, throughput, erros por segundo e CPU) já existem nativamente no CloudWatch: API Gateway expõe contagem de requisições e latência por percentil, SQS expõe o tamanho e a idade das mensagens nas filas, e ECS e RDS expõem utilização de CPU por serviço e por instância de banco, o que basta para os cenários de resiliência do pipeline de mudanças. Já os testes de RNF01 a RNF03 também precisam da latência e do throughput percebidos pelo próprio cliente k6, que só o Prometheus (alimentado por Remote Write) fornece. Cada frente de teste havia montado sua própria stack local de Grafana, uma só com CloudWatch e outra com Prometheus e CloudWatch, com nomes de container e portas coincidentes entre si. Nesta sprint as duas foram unificadas: um único `docker compose` (`apps/basica/observability/docker-compose.yml`), subido por `make -C apps/basica observabilidade-up`, provisiona os dois datasources e os dois dashboards no mesmo Grafana, detalhado na seção 10.

&emsp; Durante a preparação dos testes de resiliência do pipeline de mudanças, a instância de banco então em uso na sprint esgotou seu espaço de armazenamento por causa do volume acumulado de eventos do simulador, o que interrompeu a ingestão por um período. Diante da limitação de custo do ambiente acadêmico, que impede redimensionar ou restaurar uma instância existente, a equipe optou por provisionar uma instância de teste isolada, com o mesmo esquema aplicado do zero, para não misturar o resultado dos testes de resiliência com o incidente de capacidade. Essa instância de teste não substitui o ambiente de referência do projeto e não faz parte do desenho de arquitetura descrito em `plano-argus-v3.md`.

&emsp; Um erro real foi encontrado e corrigido durante a preparação dos testes de resiliência: a função que mescla o log de mudanças na tabela corrente do bronze não incorporava a chave primária enviada separadamente do conteúdo alterado, o que fazia colunas obrigatórias chegarem vazias e o registro ser rejeitado. A correção passou a fundir a chave com o conteúdo antes da gravação, e o gerador de carga foi reescrito com um construtor de evento por tabela de origem, já que as seis tabelas monitoradas têm esquemas e chaves diferentes entre si.

## 2. Teste de capacidade de ingestão (RNF01)

&emsp; Objetivo: aceitar o volume nominal e o pico solicitado sem erro ou descarte do gerador, mantendo latência controlada e persistindo de forma assíncrona.

| Fase | Taxa | Duração | Critérios |
|---|---:|---:|---|
| Aquecimento | 300/min | 30 s | prepara conexões, não decide aprovação |
| Nominal | 1.000/min | 1 min | ao menos 1.000 aceitos, erro abaixo de 1%, p95 abaixo de 2 s, 0 descartes |
| Pico | 10.000/min | 1 min | ao menos 10.000 aceitos, erro abaixo de 5%, p95 abaixo de 5 s, 0 descartes |
| Recuperação | 1.000/min | 1 min | ao menos 1.000 aceitos, erro abaixo de 1%, p95 abaixo de 2 s, 0 descartes |

&emsp; Como a API retorna antes do consumo pela fila, o status 2xx sozinho não comprova o requisito. A aceitação foi comparada com a diferença de `count(*)` em `bronze.event`, e a fila deveria terminar sem mensagens visíveis ou em voo.

&emsp; Execução `rnf01-final-20260902T193419Z`, de 19:34:19 a 19:38:40 UTC:

| Fase | Aceitos | Rejeitados | Sucesso | p95 | Descartes |
|---|---:|---:|---:|---:|---:|
| Nominal | 1.001 | 0 | 100% | 188,6 ms | 0 |
| Pico 10k | 10.000 | 0 | 100% | 161,8 ms | 0 |
| Recuperação | 1.000 | 0 | 100% | 170,0 ms | 0 |

&emsp; O Prometheus observou pico de 167,10 requisições por segundo, coerente com 10.000 por minuto. O total incluindo aquecimento foi 12.152, e `bronze.event` passou de 12.154 para 24.306 linhas, diferença de 12.152, com a fila terminando em 0 mensagens visíveis e 0 em voo. A CPU do `event-worker` teve média de 28,87% e pico de 78,02% no CloudWatch. O resultado confirma o RNF01 aprovado tanto na borda HTTP quanto no processamento assíncrono, sem perda detectada.

## 3. Teste de tempo de resposta (RNF02)

&emsp; Objetivo: toda consulta simples deve terminar em até cinco segundos. O plano de teste cobriu onze rotas executadas cinco vezes cada, dez usuários concorrentes por dois minutos, cinco validações semânticas do filtro `event_name + app_target` e uma carga sustentada de 600 consultas por minuto por dois minutos, com critérios de zero erro HTTP, zero resposta acima de 5 s, p95 abaixo de 3 s, p99 abaixo de 5 s, 100% dos filtros corretos e zero descarte na fase sustentada.

&emsp; Execução `rnf02-final-20260902T194059Z`, de 19:40:59 a 19:47:00 UTC: 4.587 consultas registradas, 100% de sucesso HTTP e 0% acima de cinco segundos, filtros cumulativos 100% corretos, p50 de 155,3 ms e p95 de 181,2 ms, com o maior p99 observado entre rotas e cenários no Prometheus de 1.412,5 ms e máximo individual de 1.581,0 ms, sem nenhuma iteração interrompida ou descartada.

&emsp; Na janela ampliada do CloudWatch, a Lambda registrou 4.598 invocações (inclui o preflight das 11 rotas), zero erro, zero throttle, duração média de 13,18 ms e máxima de 196,38 ms; a diferença para a latência percebida pelo k6 inclui API Gateway, authorizer, rede e TLS. O conjunto usado neste teste contém aproximadamente 24 mil eventos sintéticos variados, não o dump completo de 4 GB: ele valida contratos, filtros e concorrência, mas não representa a cardinalidade máxima de produção. O RNF02 fica aprovado com margem de mais de três segundos até o limite.

## 4. Teste de escalabilidade (RNF03)

&emsp; O mesmo script, endpoint e formato de evento foi executado em duas fases, com a capacidade de consumo como única mudança intencional:

| Fase | Event worker | Merge worker | Taxa medida |
|---|---:|---:|---:|
| Baseline | 1 task | 1 task | 1.000 eventos/min |
| Escalado | 2 tasks | 2 tasks | 2.000 eventos/min |

&emsp; Critérios: capacidade de pelo menos 2×, 99% ou mais de sucesso, p95 abaixo de 5 s, zero descarte, mesmo contrato e persistência igual ao total emitido.

| Métrica | Baseline 1× | Escalado 2× |
|---|---:|---:|
| Alvo por minuto | 1.000 | 2.000 |
| Aceitos na medição | 1.000 | 2.001 |
| Sucesso | 100% | 100% |
| p95 | 185,7 ms | 178,1 ms |
| p99 | 213,8 ms | 218,7 ms |
| Descartes | 0 | 0 |
| Total com aquecimento | 1.101 | 2.102 |
| Persistidos | 1.101 | 2.102 |
| CPU ECS média | 16,21% | 14,75% |
| CPU ECS máxima | 42,12% | 38,80% |

&emsp; A taxa dobrou, o contrato permaneceu igual, não houve perda, e a latência não se degradou de forma relevante; a redução percentual de CPU é compatível com a distribuição do trabalho entre mais tasks. O RNF03 fica aprovado para o fator testado de 2×, mas este ensaio comprova capacidade mantida após escalar, não localiza o ponto de saturação nem prova que uma única task falharia em 2.000 eventos por minuto. Um teste de capacidade até ruptura, com fatores de 5× e 10×, é uma melhoria futura que exigiria novas fases com mudança proporcional de recursos e orçamento do laboratório, não deve ser inferido destes dados.
