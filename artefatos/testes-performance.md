# Evidência de testes de performance — RNF01, RNF02 e RNF03

Execução realizada em **2 de setembro de 2026** contra uma implantação real do
Argus no AWS Academy Learner Lab (`us-east-1`). As imagens ARM64 da aplicação
foram publicadas com a tag imutável `66b4fbe59313`; migrations e serviços ECS
foram validados antes da carga. Nenhuma credencial, token ou endpoint foi
incluído neste artefato.

Os valores estruturados usados neste documento estão em
[`assets/performance/evidencias-2026-09-02.json`](assets/performance/evidencias-2026-09-02.json).
Logs e summaries completos do k6 permanecem em
`apps/basica/tests/carga/resultados/` (gitignored).

## Resultado executivo

| Requisito | Evidência principal | Resultado |
|---|---|---|
| RNF01 | pico real de 10.000 eventos/min, p95 161,8 ms, 100% aceito, 0 descarte e persistência 12.152/12.152 | **Aprovado** |
| RNF02 | 4.587 consultas, 11 rotas, 10 usuários, 600/min, 0% acima de 5 s, máximo 1.581 ms | **Aprovado** |
| RNF03 | recursos 1×→2×, carga 1.000→2.000/min, 100% aceito, 3.203/3.203 persistidos | **Aprovado no fator 2×** |
| Backlog | workers 1→0→1, fila 0→1.001→0, banco +1.001 após recuperação | **Aprovado** |
| Timeout | 100 timeouts induzidos; 5/5 consultas recuperadas, p95 1.631,7 ms | **Aprovado** |
| Observabilidade | 8 painéis Grafana, 74–92 séries/teste, CPU ECS/RDS no CloudWatch | **Comprovada** |

## 1. Requisitos e planos revisados

### RNF01 — capacidade de ingestão

Objetivo: aceitar o volume nominal e o pico solicitado sem erro ou descarte do
gerador, mantendo latência controlada e persistindo de forma assíncrona.

| Fase | Taxa | Duração | Critérios |
|---|---:|---:|---|
| Aquecimento | 300/min | 30 s | prepara conexões; não decide aprovação |
| Nominal | 1.000/min | 1 min | ≥1.000 aceitos, erro <1%, p95 <2 s, 0 descartes |
| Pico | 10.000/min | 1 min | ≥10.000 aceitos, erro <5%, p95 <5 s, 0 descartes |
| Recuperação | 1.000/min | 1 min | ≥1.000 aceitos, erro <1%, p95 <2 s, 0 descartes |

Como a API retorna antes do consumo SQS, o status 2xx sozinho não comprova o
RNF. A aceitação é comparada com a diferença de `count(*)` em `bronze.event`, e
a fila deve terminar sem mensagens visíveis ou em voo.

### RNF02 — tempo de resposta

Objetivo: toda consulta simples deve terminar em até cinco segundos.

1. onze rotas executadas cinco vezes cada;
2. dez usuários concorrentes por dois minutos;
3. cinco validações semânticas do filtro `event_name + app_target`;
4. carga sustentada de 600 consultas/min por dois minutos.

Critérios: zero erro HTTP, zero resposta acima de 5 s, p95 <3 s, p99 <5 s,
100% dos filtros corretos e zero descarte na fase sustentada.

### RNF03 — escalabilidade

O mesmo script, endpoint e formato de evento é executado em duas fases. A única
mudança intencional é a capacidade de consumo:

| Fase | Event worker | Merge worker | Taxa medida |
|---|---:|---:|---:|
| Baseline | 1 task | 1 task | 1.000 eventos/min |
| Escalado | 2 tasks | 2 tasks | 2.000 eventos/min |

Critérios: capacidade de pelo menos 2×, 99% ou mais de sucesso, p95 <5 s, zero
descarte, mesmo contrato e persistência igual ao total emitido.

### Falha de fila e timeout

Uma fila SQS Standard não possui limite de “fila cheia”. O teste substitui essa
expressão pelo risco operacional correspondente: consumidor indisponível e
backlog crescente. Os workers são reduzidos a zero, a API recebe 1.000/min, o
backlog e o banco são observados, e os workers são restaurados.

O timeout é induzido no cliente com limite de 1 ms em 100 requisições. Após 35
segundos, cinco requisições usam timeout normal de 7 s e devem responder 200 em
até 5 s. Esse cenário valida detecção e recuperação do cliente; ele **não**
afirma ter provocado timeout interno da Lambda.

## 2. Resultados e análise

### RNF01

Execução `rnf01-final-20260902T193419Z`, 19:34:19–19:38:40 UTC.

| Fase | Aceitos | Rejeitados | Sucesso | p95 | Descartes |
|---|---:|---:|---:|---:|---:|
| Nominal | 1.001 | 0 | 100% | 188,6 ms | 0 |
| Pico 10k | 10.000 | 0 | 100% | 161,8 ms | 0 |
| Recuperação | 1.000 | 0 | 100% | 170,0 ms | 0 |

O Prometheus observou pico de **167,10 req/s**, coerente com 10.000/min. O
total incluindo aquecimento foi 12.152. `bronze.event` passou de 12.154 para
24.306 linhas, diferença de **12.152**, e a fila terminou em 0 visíveis/0 em
voo. A CPU do event-worker teve média 28,87% e pico 78,02% no CloudWatch.

Conclusão: RNF01 aprovado tanto na borda HTTP quanto no processamento
assíncrono, sem perda detectada.

### RNF02

Execução `rnf02-final-20260902T194059Z`, 19:40:59–19:47:00 UTC.

- 4.587 consultas registradas pelo teste;
- 100% de sucesso HTTP e 0% acima de cinco segundos;
- filtros cumulativos: 100% corretos;
- p50 155,3 ms; p95 181,2 ms;
- maior p99 observado entre rotas/cenários no Prometheus: 1.412,5 ms;
- máximo individual: 1.581,0 ms;
- zero iteração interrompida ou descartada.

Na janela ampliada do CloudWatch, a Lambda registrou 4.598 invocações (inclui
o preflight das 11 rotas), zero erro, zero throttle, duração média de 13,18 ms e
máxima de 196,38 ms. A diferença para a latência percebida pelo k6 inclui API
Gateway, authorizer, rede e TLS.

Conclusão: RNF02 aprovado com margem de mais de três segundos até o limite.

### RNF03

| Métrica | Baseline 1× | Escalado 2× |
|---|---:|---:|
| Alvo/min | 1.000 | 2.000 |
| Aceitos na medição | 1.000 | 2.001 |
| Sucesso | 100% | 100% |
| p95 | 185,7 ms | 178,1 ms |
| p99 | 213,8 ms | 218,7 ms |
| Descartes | 0 | 0 |
| Total com aquecimento | 1.101 | 2.102 |
| Persistidos | 1.101 | 2.102 |
| CPU ECS média | 16,21% | 14,75% |
| CPU ECS máxima | 42,12% | 38,80% |

A taxa dobrou, o contrato permaneceu igual, não houve perda, e a latência não
se degradou de forma relevante. A redução de CPU percentual é compatível com a
distribuição do trabalho entre mais tasks.

Conclusão: RNF03 aprovado para o fator testado de 2×. Este ensaio comprova
capacidade mantida após escalar, mas não localiza o ponto de saturação nem prova
que uma única task falharia em 2.000/min. Um teste de capacidade até ruptura é
uma melhoria futura, não deve ser inferido destes dados.

### Resiliência

Com os dois workers em zero, 1.001/1.001 eventos receberam 2xx, o SQS passou de
0 para 1.001 mensagens e o banco permaneceu em 27.509 linhas. Após restaurar
uma task de cada worker, a fila voltou a zero e o banco passou a 28.510:
**1.001/1.001 persistidos**.

No cenário de timeout, 100/100 requisições com limite de 1 ms expiraram como
planejado. Em seguida, 5/5 requisições responderam 200; o p95 de recuperação foi
1.631,7 ms, abaixo do limite de 5 s.

## 3. Observabilidade

A stack local ficou disponível em:

- Prometheus `:9090`, receiver de remote write habilitado, retenção de 7 dias;
- Grafana `:3001`, versão 11.1.0;
- dashboard UID `argus-k6-carga`, título **Argus — Testes de Carga
  (RNF01/02/03)**.

O dashboard provisionado contém oito painéis: throughput, p50/p90/p95/p99,
erros/s, taxa de sucesso, VUs, total de requisições, latência por cenário/rota
e bytes recebidos/enviados. O filtro `testid` isola cada execução. Foram
confirmadas 82 séries no RNF01, 92 no RNF02, 82 em cada fase do RNF03, 74 no
backlog e 82 no timeout.

A CPU não é uma métrica do k6. Ela foi coletada do CloudWatch para evitar uma
simulação artificial: ECS chegou a 78,02% no RNF01; o RDS teve média 5,55% e
pico 10,25% no período completo. O guia para adicionar o datasource CloudWatch
ao mesmo Grafana está no
[`README da suíte`](../apps/basica/tests/carga/README.md#cpu-real-da-aws-no-mesmo-grafana).

O navegador integrado não estava disponível para uma captura automática. A
saúde do Grafana, o datasource, o dashboard e suas consultas foram verificados
pelas APIs. Para a entrega visual, abrir o dashboard, selecionar cada `testid`
e capturar os painéis é o único passo manual pendente.

## Limitações declaradas

- O conjunto usado no RNF02 contém aproximadamente 24 mil eventos sintéticos
  variados, não o dump completo de 4 GB. Ele valida contratos, filtros e
  concorrência, mas não representa a cardinalidade máxima de produção.
- As credenciais temporárias do Learner Lab expiram; uma nova sessão exige
  atualizar o perfil e, para CloudWatch no Grafana, reiniciar o datasource.
- Prometheus e Grafana estão locais. Os resultados continuam reais, mas a
  retenção desaparece se os volumes Docker forem removidos.
- A evidência de RNF03 cobre 2×. Fatores 5× e 10× precisam de novas fases com
  mudança proporcional de recursos e orçamento do laboratório.

## Como reproduzir

Os comandos, variáveis, PromQL, passos de backlog e integração CloudWatch estão
documentados no [`README da suíte`](../apps/basica/tests/carga/README.md). O k6
envia métricas ao Prometheus por Remote Write, usando `testid` para separar
execuções; a configuração segue o fluxo recomendado pela documentação oficial
do Grafana k6. O datasource CloudWatch é nativo no Grafana e pode usar um
arquivo de credenciais com perfil, sem colocar chaves no YAML.
