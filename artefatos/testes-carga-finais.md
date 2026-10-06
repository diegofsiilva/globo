# Testes finais de carga, resiliência e observabilidade

Este documento amplia os [testes de carga da Sprint 3](testes-carga-inicial.md)
para avaliar a arquitetura atual. Os cenários acompanham o recebimento de
eventos, o acesso às telas, a recuperação de falhas e o aumento automático de
réplicas. Os resultados relacionam os requisitos não funcionais, identificados
pela sigla RNF, às decisões de arquitetura.

A carga foi gerada pelo k6 e acompanhada no Grafana. Também foi repetido o
teste de integração que verifica se um evento enviado fica disponível na API,
identificado como TI-05.2 no artefato funcional. Os códigos CF identificam os
cenários de carga deste documento.

Como na Sprint 3, os resultados ficam concentrados em dois JSONs: um com
os [cenários gerais](evidencias/testes-carga-finais/evidencias-2026-10-05.json)
e outro com as [remessas de eventos](evidencias/testes-carga-finais/evidencias-lotes-2026-10-05.json).
Cada remessa contém 150.000 eventos. Nesta rodada, foram enviadas duas
remessas juntas, com o consumidor parado; os ensaios de uma, três e quatro
remessas continuam como evidência histórica, sem nova execução.

## 1. Evolução dos testes e critérios de aprovação

### 1.1 O que foi aproveitado da Sprint 3

O recebimento de eventos mantém API Gateway, fila SQS, consumidores no ECS
Fargate e PostgreSQL no RDS. A API de leitura passou a ser atendida pelo
Kubernetes no EKS. Nesse caminho, o Ingress encaminha as consultas à aplicação,
e o HPA ajusta a quantidade de réplicas conforme o uso de CPU.

| Evidência anterior | Resultado e contribuição para esta etapa |
|---|---|
| Pico de eventos na Sprint 3 | 10.000 eventos/min e 12.152 eventos aceitos e gravados no ensaio completo. Os lotes de 150 mil a 600 mil demonstraram recuperação do acúmulo |
| Consultas na Sprint 3 | 4.587 consultas, com máximo de 1.581 ms e ressalva sobre a representatividade da base |
| Carga das telas no artefato funcional | Aprovação até 100 usuários. A rodada com 200 usuários ultrapassou limites por tela, mesmo com os indicadores agregados dentro dos limites |
| Eventos inválidos | 18/18 falhas identificadas e 150/150 eventos válidos preservados. O RNF04 mantém essa evidência, sem nova execução nesta etapa |
| Recuperação local no kind | A remoção de um dos dois pods não causou falhas nas 2.262 requisições. O resultado sustenta a redundância naquele ambiente, sem extrapolar os tempos para a AWS |

Os [resultados iniciais](assets/performance/evidencias-2026-09-02.json),
os [ensaios por lote](assets/performance/evidencias-lotes-2026-09-09.json) e os
[testes funcionais](testes-funcionais.md#testes-de-carga) preservam a análise
histórica. A [rodada A no EKS](evidencias/carga-kubernetes/rodada-a-resultado.json)
e a [rodada B](evidencias/carga-kubernetes/rodada-b-resultado.json) registram os
testes anteriores à correção da coleta de métricas do HPA. A
[repetição após o ajuste](evidencias/carga-kubernetes-2026-09-24/carga-ui_resultado_20260925T004042Z.json)
confirmou a coleta, mas ainda sem aumento de réplicas.

### 1.2 Planos de teste aprimorados

No Argus, o exemplo de abertura de venda é representado por uma rajada de
telemetria de 10 mil eventos/minuto. O cenário de “fila cheia” foi representado
pelo acúmulo de mensagens com o consumidor parado, seguido de retomada. Ele
avalia a recuperação da fila, sem afirmar que uma cota da SQS foi atingida.

| Cenário e requisito | Procedimento | Resultado esperado |
|---|---|---|
| Pico de eventos, CF01 / RNF01 | Enviar 1.000, 10.000 e 1.000 eventos/min, por 60 s em cada fase, além do aquecimento | Aceitar ao menos 1.000/10.000/1.000 eventos; p95 <2 s/<5 s/<2 s nas respectivas fases; zero rejeições e descartes do gerador; gravar todos os aceitos sem duplicidade e terminar com fila e DLQ vazias |
| Acúmulo e recuperação, CF02 / RNF01 e RNF05 | Enviar dois lotes de 150.000 eventos com o consumidor parado e depois retomar o consumo | Aceitar todos os eventos, gravá-los sem perda ou duplicação e esvaziar as filas. Referência de recuperação de 450 s a partir do pedido de retomada |
| Acesso às telas, CF03 / RNF02 | Executar as chamadas das seis telas com 5/25/100 usuários virtuais, por dois minutos em cada nível | Erros <1%, p95 HTTP <3 s, p99 HTTP <5 s, p95 de abertura <5 s e telas completas >99%, no conjunto e por tela. Conferir também o máximo de 5 s do RNF02 |
| Escala automática, CF04 | Usar 200/450/1.200 usuários virtuais por cinco minutos em cada nível, acompanhando também a recuperação | Observar criação, disponibilidade e redução de réplicas, mantendo os critérios de desempenho do CF03 |
| Timeout do cliente, CF05 / RNF05 | Limitar 100 consultas a 1 ms e iniciar cinco consultas com prazo de 7 s aos 35 s do ensaio | Detectar ao menos um timeout; obter HTTP 200 nas cinco consultas posteriores, zero falhas e p95 <5 s |
| Eventos inválidos, CF06 / RNF04 | Preservar a verificação de entradas válidas e inválidas da Sprint 3 | Identificar a causa das rejeições e manter o processamento dos eventos válidos |
| Registros de falha, CF07 / RNF11 | Conferir amostras das falhas observadas | Identificar horário, etapa e erro, distinguindo os cenários |
| Disponibilidade na API, CF08 / TI-05.2 | Enviar um evento e consultar a API após a correção do índice no banco | Encontrar o evento em até 300 s, com os campos preservados e sem expor `user_id` |

Os critérios vêm de [requisitos.md](requisitos.md) e do
[plano registrado antes da execução](evidencias/testes-carga-finais/evidencias-2026-10-05.json),
preservado no campo `plano_execucao`.
Os limites auxiliares do k6 e os 450 s de recuperação são critérios do ensaio.
No CF01, o roteiro também exige falhas <1%/<5%/<1% por fase; a exigência
adicional de zero rejeições é mais restritiva. O veredito combina os limites
do k6 com a conferência posterior no banco, não apenas `aprovado_http`.
O RNF03 trata de ampliar a capacidade de ingestão de pelo menos 1.000 para
2.000 requisições/minuto. Sua evidência continua sendo a da Sprint 3, pois o
CF04 avalia a escala das consultas.

## 2. Ambiente e forma de medição

Os testes usaram a base histórica do parceiro, com **68.717.811 registros em
32 tabelas**, carregada a partir de `argus_dump.sql`. A camada bronze guarda os
dados recebidos, a silver contém os dados tratados e a gold reúne resultados
para consulta. Essas camadas foram preparadas antes da carga, sem avanço manual
dos marcadores de processamento.

| Componente | Configuração utilizada |
|---|---|
| Gerador de carga | k6 0.54.0 em EC2 `t4g.large`, dentro da rede privada da AWS |
| Aplicação | EKS 1.33, com duas réplicas iniciais da API e possibilidade de chegar a seis. Imagens do commit `326769cbb9d9` |
| Banco | PostgreSQL 16.13 em `db.t3.medium`, com 100 GiB |
| Escala automática | HPA com alvo de 60% dos `250m` de CPU requisitados por pod. Redução com janela de estabilização de 300 s |
| Processamento regular | Lotes de 5.000 registros a cada 60 s entre bronze e silver, e ciclo de 900 s entre silver e gold |
| Registro das execuções | Identificador `test_id`, roteiro, versão, horários, critérios, base e recursos disponíveis |

A configuração, as contagens e os intervalos da base estão no campo `ambiente`
das [evidências consolidadas](evidencias/testes-carga-finais/evidencias-2026-10-05.json).
Os registros completos de preparação estão no pacote detalhado da seção 6.

A nova rodada consultou uma janela com mais histórico acumulado. A rodada
anterior usava o relógio virtual próximo ao início dos dados. Por isso, os
resultados não isolam apenas o efeito da mudança de arquitetura ou do HPA.
As estatísticas da base e os registros das execuções preservam essas condições.

Para interpretar os resultados, foram consideradas as seguintes medidas:

- **Usuários virtuais (VUs):** sequências de chamadas executadas pelo k6. Nos testes das telas, há pausa de 2 s entre aberturas. Mais usuários não representam uma taxa fixa de requisições.
- **p95 e p99:** tempos até os quais se encontram 95% e 99% das medições. O máximo mostra a resposta mais lenta.
- **Throughput:** quantidade de requisições ou eventos por segundo. Uma mensagem da SQS pode conter vários eventos.
- **Recuperação:** tempo para retomar o serviço e processar o acúmulo. A fila vazia é conferida junto dos registros no banco e da DLQ, a fila de mensagens que não foram processadas normalmente.

A confirmação de recebimento de um evento, sua gravação na bronze e sua
disponibilidade na API são etapas distintas. A comparação entre eventos
aceitos e gravados, chamada de reconciliação, verifica perdas e duplicidades.
O tempo de resposta também é analisado junto dos erros, pois uma falha pode
ser devolvida rapidamente.

## 3. Execução e resultados

### 3.1 Evento disponível para consulta na API (TI-05.2)

TI significa teste de integração. O código TI-05.2 identifica o segundo caso
do conjunto que verifica a aplicação publicada na AWS. Ele envia um evento
por `POST /v1/events` e consulta `GET /api/v1/events` até encontrá-lo ou atingir
o prazo de 300 s.

Na execução original, o evento foi gravado, mas não apareceu na consulta.
A investigação encontrou dados pendentes e buscas por `_lsn` sem índice.
A [migration 030](../apps/fullstack/db/migrations/030_indice_lsn_em_evento.sql),
um script de alteração do banco, adicionou esse índice.

**Procedimento:** repetir o teste com a base preparada, as migrations
001 a 033 aplicadas e a leitura pelo Ingress do EKS.

| Verificação | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|
| Disponibilidade na API | Evento consultável em até 300 s | Encontrado na 24ª consulta, após 242,24 s | Aprovado |
| Conteúdo e proteção dos dados | Sessão, nome e dispositivo preservados, sem `user_id` | Campos conferidos e `user_id` ausente | Aprovado |

O resultado considera a correção do índice e a preparação da base. Como foi
medido um evento, ele não representa um p95 nem comprova o comportamento sob
carga. As consultas foram feitas em intervalos, então o tempo indica quando o
evento foi encontrado. O caso de autorização de acesso, TI-05.1, permanece
separado, pois usa outro caminho de entrada.

**Evidências:** [resultado consolidado, campo `resultados.TI-05.2`](evidencias/testes-carga-finais/evidencias-2026-10-05.json)
e [diagnóstico original](testes-funcionais.md#diagnóstico-do-caso-reprovado).

### 3.2 Acesso às telas no Kubernetes (CF03-A)

**Procedimento:** executar as chamadas das seis telas com 5/25/100 usuários,
por dois minutos em cada nível e pausa de 30 s, usando a base preparada e o
HPA com métricas disponíveis.

**Resultado esperado:** atender aos critérios de tempo, erros e telas
completas do CF03, tanto no conjunto quanto por tela.

| VUs | Requisições de carga | Erros | p95 HTTP | p99 HTTP | Máximo HTTP | p95 de abertura | Telas completas |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 5 | 124 | 20,16% | 30.001 ms | 30.001 ms | 30.001 ms | 30.002 ms | 42,86% |
| 25 | 598 | 85,62% | 30.001 ms | 30.001 ms | 30.006 ms | 30.004 ms | 1,75% |
| 100 | 8.368 | 98,29% | 30.000 ms | 30.001 ms | 30.005 ms | 30.002 ms | 1,00% |

**Resultado obtido: reprovado nos três níveis.** Foram 9.090 requisições de
carga, além de uma de preparação, e 8.762 falhas HTTP. O aumento do volume no
último nível veio principalmente de respostas de erro rápidas. Por isso, a
mediana de 1 ms a 100 usuários não indica melhora.

O banco atingiu 100% de CPU na média de um minuto. O HPA manteve duas réplicas,
com uso de até 54% da CPU requisitada, abaixo do alvo de 60%. Os pods somaram
oito reinícios e houve intervalos sem backend disponível.

Uma consulta isolada de sinais já havia falhado em 15,485 s, com timeout SQL
de 15 s. A aplicação recalcula uma referência de sete dias nessa consulta,
mas o custo de cada operação ainda precisa ser confirmado no plano SQL.
O compartilhamento dos processos HTTP com as verificações de saúde dos pods
também precisa ser investigado.

Na tela Hipóteses, o processamento recusou 7.696.798 entradas, acima da
proteção de 250.000. A preparação das camadas de dados, portanto, não garantiu
a geração das hipóteses. O teste revelou um limite de consulta com histórico
acumulado, sem permitir atribuir a diferença apenas ao código.

**Evidências:** [campo `resultados.CF03-A`](evidencias/testes-carga-finais/evidencias-2026-10-05.json),
com resultados por nível e tela, HPA, CPU do banco e diagnósticos.

### 3.3 Aumento automático de réplicas (CF04)

**Procedimento:** usar 200/450/1.200 usuários por cinco minutos em cada nível,
acompanhando o HPA durante a carga e a recuperação.

**Resultado esperado:** observar aumento e redução de réplicas, mantendo os
critérios de desempenho das consultas.

| VUs | Requisições de carga | Erros | p95 HTTP | p99 HTTP | Máximo HTTP | p95 de abertura | Telas completas |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 200 | 55.142 | 98,95% | 24.082 ms | 30.001 ms | 30.044 ms | 27.782 ms | 0,39% |
| 450 | 188.424 | 99,98% | 57 ms | 29.874 ms | 30.026 ms | 89 ms | 0,00% |
| 1.200 | 242.643 | 99,92% | 30.000 ms | 30.002 ms | 30.185 ms | 30.002 ms | 0,01% |

**Resultado obtido: escala observada, desempenho reprovado.** Foram 486.209
requisições de carga e uma de preparação. A quantidade de réplicas passou de
duas para três e depois voltou a duas. O novo pod ficou disponível cerca de
13,85 s após sua criação, mas o atendimento continuou instável.

O uso de CPU chegou a 144% do valor requisitado pelos pods, e houve 15
reinícios adicionais. Após o fim da carga, os três pods foram observados
disponíveis em 281,34 s. A observação continuou por mais de nove minutos e
registrou a redução para duas réplicas. Houve falhas transitórias na coleta
de métricas, diferentes da ausência permanente observada na rodada antiga.

O p95 de 57 ms a 450 usuários acompanha 99,98% de erros. Assim, a escala
funcionou, mas não resolveu o tempo das consultas nem a indisponibilidade.
O gerador manteve ao menos 52% de CPU ociosa, sem indício de saturação de CPU,
embora isso não elimine possíveis limites de rede.

**Evidências:** [campo `resultados.CF04`](evidencias/testes-carga-finais/evidencias-2026-10-05.json),
com resultados por nível e tela, réplicas, CPU do banco e gerador.

### 3.4 Pico de recebimento de eventos (CF01)

**Procedimento:** executar aquecimento, carga normal, pico e retorno à carga
normal. Depois, comparar os eventos aceitos com os registros no banco.

**Resultado esperado:** aceitar ao menos 1.000/10.000/1.000 eventos, com p95
<2 s/<5 s/<2 s, sem rejeições ou descartes; gravar todos os aceitos sem
duplicidade e terminar com fila e DLQ vazias.

| Fase | Taxa programada | Duração | Eventos aceitos | Rejeitados | Execuções descartadas | p95 do recebimento |
|---|---:|---:|---:|---:|---:|---:|
| Normal | 1.000/min | 60 s | 1.001 | 0 | 0 | 60,7 ms |
| Pico | 10.000/min | 60 s | 10.001 | 0 | 0 | 30,5 ms |
| Recuperação | 1.000/min | 60 s | 1.000 | 0 | 0 | 34,1 ms |

**Resultado obtido: aprovado.** Com os 151 eventos do aquecimento, foram
12.153 eventos aceitos e gravados na bronze, sem duplicidade. A fila e a DLQ
terminaram vazias, e o máximo HTTP foi de 1.175,12 ms. As pequenas diferenças
entre a taxa programada e a contagem decorrem do agendamento do roteiro.

A aprovação vale para o pico de um minuto e a gravação no banco. Não mede
sustentação prolongada nem disponibilidade na API. Os eventos usam o instante
real do envio, posterior à janela do relógio virtual de leitura. A conferência
foi feita por `load_test_id`, sem calcular atraso de persistência, pois esse
roteiro não registra `load_test_sent_at`.

**Evidências:** [campo `resultados.CF01`](evidencias/testes-carga-finais/evidencias-2026-10-05.json),
com resultado do k6 e conferência de eventos e filas.

### 3.5 Duas remessas de eventos e recuperação da fila (CF02)

**Procedimento:** parar o `event-worker`, enviar dois lotes de 150.000 eventos
com 50 usuários e fragmentos de até 40.000 bytes, e retomar o consumidor.
A injeção levou 28,035 s, com p95 de 429,9 ms e máximo de 1.452,5 ms por fragmento.

| Remessa | Eventos programados | Gravados na bronze | Diferença |
|---|---:|---:|---:|
| 1 | 150.000 | 149.927 | 73 |
| 2 | 150.000 | 150.000 | 0 |
| **Total** | **300.000** | **299.927** | **73** |

A separação vem da conferência por lote no banco. Os tempos abaixo foram
medidos para o conjunto das duas remessas; não há tempo isolado por remessa.

**Resultado esperado:** aceitar os 300.000 eventos e, após o pedido de
retomada, gravá-los sem perda ou duplicação e esvaziar as filas dentro da
referência de 450 s.

| Verificação | Resultado obtido |
|---|---|
| Recebimento | 299.927 eventos aceitos e 73 rejeitados |
| Falhas HTTP | Uma resposta 500 em 4.155 requisições |
| Fila antes da retomada | 4.154 mensagens visíveis, sem mensagens em processamento ou na DLQ |
| Primeira task em execução | 23,69 s após o pedido de retomada |
| Eventos aceitos gravados | 299.927 na bronze aos 137,70 s, sem duplicidade |
| Fila e DLQ vazias | Conferência concluída aos 165,01 s |
| Tempo entre envio e gravação | p95 de 205,16 s e máximo de 211,28 s, para os 299.927 aceitos |

**Resultado obtido: recuperação aprovada, cenário completo reprovado.**
Todos os eventos aceitos foram gravados dentro da referência de recuperação,
mas as 73 rejeições impediram a aprovação do recebimento integral. O erro 500
foi registrado pelo API Gateway, sem informação suficiente para atribuir sua
causa à fila, ao banco ou à parada do consumidor.

O p95 até a gravação inclui a espera anterior à retomada. Ele é diferente do
tempo de recuperação e não mede quando todo o lote ficou disponível na API.

**Evidências:** [resultados por remessa](evidencias/testes-carga-finais/evidencias-lotes-2026-10-05.json),
com injeção, recuperação, conferência no banco e registro do erro 500.

### 3.6 Timeout do cliente e recuperação (CF05)

**Procedimento:** limitar a espera a 1 ms em 100 consultas a `/api/v1/clock`
para provocar timeouts. Após a pausa, realizar cinco consultas com prazo de 7 s.

| Verificação | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|
| Prazo reduzido | Ao menos um timeout detectado em 100 consultas com prazo de 1 ms | 100 timeouts | Aprovado |
| Consultas posteriores | Cinco HTTP 200, zero falhas e p95 <5 s, com prazo de 7 s por consulta | Zero falhas e p95 de 12,3 ms | Aprovado |

A aprovação comprova a leitura após os timeouts do cliente. A indisponibilidade
do banco e uma carga prolongada não foram provocadas nesse cenário.

O requisito de registro de falhas, RNF11, continua parcialmente comprovado.
O timeout SQL apresentou horário, componente e causa, mas sem identificador
que acompanhasse a requisição entre serviços. O erro do API Gateway apresentou
`requestId`, mas sem detalhe da causa. Esses registros ajudam na investigação,
mas não cobrem todos os cenários do requisito. A correlação entre serviços
permanece como melhoria adicional.

**Evidências:** [campo `resultados.CF05` e critérios em `plano_execucao`](evidencias/testes-carga-finais/evidencias-2026-10-05.json).

## 4. Indicadores de observabilidade

O Grafana reúne as métricas do k6 armazenadas no Prometheus e os indicadores
da AWS coletados no CloudWatch. Os painéis usam o identificador da execução e
o mesmo intervalo de observação para relacionar carga, erros e consumo de
recursos.

| Indicador | O que foi analisado |
|---|---|
| Latência | p95 e p99 por cenário e rota, junto da proporção de respostas com sucesso |
| Throughput | Requisições por segundo, distinguindo todas as respostas das respostas esperadas |
| Erros por segundo | Taxa de respostas inesperadas e contador total de falhas |
| CPU | Uso do banco e dos consumidores, além da CPU requisitada pelos pods usada como referência pelo HPA |
| Réplicas e filas | Quantidade de pods disponíveis, aumento e redução de réplicas, acúmulo de mensagens e recuperação |

As consultas abaixo calculam requisições e erros por segundo:

```promql
sum(rate(k6_http_reqs_total{testid=~"$testid"}[1m]))
sum(rate(k6_http_reqs_total{testid=~"$testid",expected_response="false"}[1m]))
```

As capturas usam medições reais preservadas após os testes. As métricas do k6
foram enviadas ao Prometheus por Remote Write, e seu histórico foi importado
em um Prometheus local para consulta no Grafana. As amostras do Kubernetes
foram coletadas aproximadamente a cada 12 s, e o CloudWatch forneceu médias
de 60 s. A coleta do HPA é separada do histórico do Prometheus.

O painel de latência mostra o **maior p95 entre as rotas**, enquanto os
resultados do k6 preservam os percentis agregados. Ausência de amostra não
representa zero. O painel do HPA descarta valores com mais de 25 s, e o painel do CF02
não prolonga amostras do CloudWatch além de 75 s.

**Figura 1: acesso às telas, CF03-A.** O aumento dos erros acompanha tempos
próximos de 30 s, CPU elevada no banco e perda de disponibilidade dos pods.
O HPA permaneceu com duas réplicas.

![Grafana: carga das telas](evidencias/testes-carga-finais/grafana-cf03-a.png)

**Figura 2: escala automática, CF04.** As réplicas aumentam e depois diminuem,
mas o volume de erros permanece elevado. O banco volta a atingir 100% de CPU.

![Grafana: escala automática](evidencias/testes-carga-finais/grafana-cf04.png)

**Figura 3: pico de eventos, CF01.** O throughput acompanha a taxa programada,
e a fila acumulada é consumida. A confirmação da gravação de todos os eventos
vem da conferência no banco apresentada no resultado.

![Grafana: pico de eventos](evidencias/testes-carga-finais/grafana-cf01.png)

**Figura 4: recuperação da fila, CF02.** A fila cresce com o consumidor parado
e volta a zero após a retomada. O contador registra uma falha HTTP anterior
à primeira amostra remota. Por isso, a taxa de erros aparece em zero nessa
janela, embora o total registre a falha. A análise considera ambos.

![Grafana: recuperação da fila](evidencias/testes-carga-finais/grafana-cf02.png)

As séries, as amostras do CloudWatch e os dashboards das quatro figuras
estão no [pacote detalhado](evidencias/testes-carga-finais/registros-detalhados-2026-10-05.zip).
Os dashboards preservam expressões e unidades; sua importação exige associar
a fonte `prometheus-final` ao histórico preservado. As capturas antigas continuam no
[artefato da Sprint 3](testes-carga-inicial.md).

## 5. O que os resultados mostraram e os impactos na arquitetura

O pico de eventos e a consulta do evento no teste de integração foram
aprovados. A recuperação dos eventos aceitos também foi confirmada, mas a
rejeição de parte do lote impediu a aprovação completa desse cenário.
Nas telas, aumentar réplicas não resolveu o tempo das consultas nem os erros.

| Observação | Decisão e situação |
|---|---|
| Eventos aceitos foram gravados após a recuperação da fila | Manter o recebimento separado do consumo por SQS. Investigar o erro de entrada e definir repetição segura sem duplicar eventos |
| Consultas demoradas, CPU elevada no banco e reinícios da API | Analisar o plano SQL, a concorrência e as verificações de saúde dos pods. Materialização ou cache do cálculo de referência são propostas ainda não implementadas nem medidas |
| HPA ajustou as réplicas, sem recuperar o atendimento | Manter a coleta de métricas e avaliar a política de escala junto da capacidade do banco. Mais réplicas, isoladamente, não resolveram o problema |
| Ausência de índice em `_lsn` | Correção aplicada pela migration 030. A reexecução foi aprovada com a base preparada, sem isolar apenas o efeito do índice |
| Inicialização de hipóteses acima do limite de 250 mil entradas | Dividir o processamento inicial em janelas menores, mantendo a proteção de entrada |
| Fragmentos próximos de 240 KB produziram HTTP 414 | Manter o teto de 40.000 bytes validado nos testes por lote |
| Falhas com informações incompletas nos logs | Completar a comprovação do RNF11 e acrescentar um identificador que acompanhe a requisição entre os serviços |

Uma próxima execução pode sustentar 10.000 eventos/min por 15 minutos,
avaliando cada minuto e o total, com os mesmos limites de aceite e p95 do
pico e reconciliação final. Para comparar uma otimização, repetir antes e
depois a mesma base restaurada, relógio virtual, filtros, aquecimento, carga,
recursos e configuração de processamento, alterando apenas a otimização.
Esses ensaios estão **propostos, não executados**. O RNF04 conserva a evidência
histórica; RNF05 não comprova recuperação de dependência indisponível, e
RNF11 permanece parcial.

## 6. Evidências e reprodução

Seguindo a organização da Sprint 3, a entrega reúne:

- [Evidências gerais](evidencias/testes-carga-finais/evidencias-2026-10-05.json): ambiente, plano, pico, consultas, escala, timeout e integração.
- [Evidências por remessa](evidencias/testes-carga-finais/evidencias-lotes-2026-10-05.json): duas remessas de 150 mil eventos, aceite, recuperação e integridade.
- As quatro capturas da seção 4.
- [Registros detalhados](evidencias/testes-carga-finais/registros-detalhados-2026-10-05.zip): 39 arquivos originais e um manifesto SHA-256, para auditoria e reprodução sem espalhar os registros intermediários pela entrega.

O [guia original da suíte](../apps/fullstack/tests/carga/README.md) reúne os
comandos dos testes anteriores. Seus roteiros e os quatro registros de
preparação já existentes foram mantidos nos caminhos originais, sem alterações.
Consolidar as evidências desta rodada não representa nova execução.

Para repetir as medições, é necessário preparar a mesma base, registrar o
relógio virtual, usar um novo `K6_TEST_ID` e selecionar o Ingress do EKS.
O endereço padrão de `make env` aponta para a Lambda e avaliaria outro
caminho. A origem da carga também deve ser mantida na EC2 para comparação.

O teste de acúmulo exige parar e depois restaurar o consumidor, além de
conferir as filas e os eventos no banco. O comando de envio, isoladamente,
não realiza essas etapas. Os resumos de CF01 e CF02 incorporam agora a
conferência posterior, com referência ao arquivo e aos campos de origem;
o aceite parcial de CF02 e a disponibilidade não medida na API permanecem explícitos.

Conferir os JSONs, as capturas e o pacote detalhado dispensa a AWS; uma nova
medição exige o ambiente ativo. A reprodução integral da observabilidade
depende dos snapshots do Prometheus e dos auxiliares locais de coleta,
que não integram esta entrega. Os dashboards contêm consultas, não o histórico
bruto do k6. Os registros no pacote podem ser extraídos com um descompactador.

Os registros brutos do k6 e a extração local do pacote ficam em
`apps/fullstack/tests/carga/resultados/`, um diretório ignorado pelo Git.
Os arquivos públicos preservam os resultados sem tokens, credenciais ou
endpoints do ambiente.
