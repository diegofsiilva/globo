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

## 5. Teste de tratamento de eventos inválidos (RNF04)

&emsp; O objetivo central deste teste é garantir que um evento incorreto não interrompa o recebimento dos demais e que a causa da falha seja identificável posteriormente. Foram exercitados cinco tipos de item inválido dentro de um lote misto, cada um repetido três vezes: tabela de origem ausente, tabela desconhecida, tipo de operação inválido, chave primária vazia e atualização sem o conteúdo alterado. Além desses, foi enviado um corpo de requisição inteiro malformado, que não chega a ser separado em itens individuais.

&emsp; A rejeição acontece de forma assíncrona, dentro do worker de mesclagem, e não no momento da requisição: a integração entre o API Gateway e a fila encaminha o conteúdo recebido sem validá-lo, de modo que toda requisição desta suíte retorna sucesso imediato. O worker é quem separa os itens válidos dos inválidos, processa os primeiros normalmente e desvia os segundos para a fila de rejeitados na primeira tentativa, sem esperar o número máximo de tentativas nativo do serviço de fila.

| Critério de aceite | Resultado |
|---|---|
| Cada caso de item inválido é identificável na fila de rejeitados | 18 de 18 casos aparecem com a causa específica registrada |
| Eventos válidos do mesmo lote de um item inválido continuam sendo processados | 150 de 150 eventos válidos confirmados no log de mudanças, sem perda |
| O caso de corpo inteiro malformado não contamina eventos válidos do mesmo corpo | confirmado: nenhum evento válido do mesmo corpo malformado aparece como processado |
| O worker não trava nem reinicia por causa de payload malformado | confirmado por observação da contagem de tarefas em execução durante o teste |

&emsp; A tabela a seguir reproduz uma amostra real capturada da fila de rejeitados nesta sprint, com o motivo exato registrado pelo worker para cada tipo de caso (o mesmo gerador de evento inválido foi reaproveitado no cenário de aprofundamento da seção 7, o que permitiu recapturar a mesma amostra em outra execução).

| Caso enviado | Motivo registrado na fila de rejeitados |
|---|---|
| Chave primária vazia (`pk: {}`) | `pk vazia: o MERGE nao tem como identificar a linha` |
| Tabela de origem desconhecida | `tabela desconhecida: 'tabela_fantasma_k6'. Tabela nova exige migration` |
| Tipo de operação inválido (`op: "x"`) | `Input should be 'i', 'u', 'd' or 'r'` |
| Campo `source_table` ausente | `source_table: Field required` |
| Atualização sem conteúdo alterado (`op: "u"` sem `after`) | `op='u' exige after, que veio vazio` |
| Corpo inteiro do POST malformado | `JSON invalido: Expecting value: line 1 column 15` |

&emsp; Cada linha identifica exatamente o campo e a regra de validação que causou a rejeição, e não apenas o fato de que algo falhou. É essa especificidade que permite a um operador diferenciar, sem consultar o código, se um evento foi rejeitado por um problema de schema, de tipo, ou de conteúdo ausente, o que resolve diretamente a exigência de que a falha seja identificável posteriormente.

&emsp; O resultado confirma que a rejeição funciona por item dentro de um lote misto, e não por lote inteiro, exceto no caso degenerado de um corpo de requisição que não pode nem ser interpretado como uma lista de itens, situação em que a perda se limita ao próprio corpo malformado e não se propaga a outras requisições.

## 6. Teste de recuperação após falha temporária (RNF05)

&emsp; O objetivo central deste teste é verificar se o sistema retoma o processamento sozinho após uma falha controlada, sem perder silenciosamente eventos já aceitos pela API. As subseções 6.1 e 6.2 exercitam o pipeline de mudanças (fluxo do CDC simulado, worker de mesclagem); a subseção 6.3 exercita o pipeline de eventos de frontend (mesmo fluxo dos RNF01 a RNF03), com um método mais leve mas contra um consumidor real.

### 6.1 Pipeline de mudanças: cenário de fila cheia

&emsp; O worker de mesclagem foi desligado por completo, e uma carga sustentada de dez mil eventos por minuto foi mantida por dez minutos contra a rota de ingestão de mudanças, com o worker desligado durante toda a janela. Em seguida o worker foi religado e o esvaziamento da fila foi acompanhado até se aproximar do volume de tráfego contínuo já gerado pelo simulador de eventos em segundo plano.

| Critério de aceite | Resultado |
|---|---|
| A API continua aceitando eventos mesmo com o worker desligado | 96.020 eventos enviados, 100% aceitos, 0% de falha de requisição |
| Latência da requisição de ingestão permanece estável sob carga | percentil 95 de 266 milissegundos, percentil 99 de 908 milissegundos |
| A fila de rejeitados não cresce por causa do acúmulo | contagem de mensagens na fila de rejeitados idêntica antes e depois do cenário |
| O tempo de esvaziamento é documentado | pico de aproximadamente 21.750 mensagens visíveis reduzido ao volume de tráfego ambiente em cerca de 16 minutos após religar o worker |

&emsp; O resultado confirma o desacoplamento entre a aceitação do evento e o seu processamento: a fila absorve o acúmulo integralmente enquanto o consumidor está fora do ar, sem rejeitar nenhuma requisição e sem gerar perda quando o consumo é retomado. As figuras 1 a 3, extraídas do painel Grafana implementado (detalhado na seção 10), mostram esse comportamento a partir de três ângulos diferentes: o tamanho da fila, a latência percebida pelo cliente e o uso de CPU do worker.

<div align="center">

<sub>Figura 1 - Tamanho da fila de mudanças e da fila de rejeitados durante o cenário de fila cheia</sub>

![Painel Grafana: fila changes e DLQ](./assets/captura_dashboard_fila_changes_dlq.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; A linha verde é o número de mensagens visíveis na fila principal, e a linha amarela é a idade em segundos da mensagem mais antiga ainda não processada. As duas sobem de forma constante enquanto o worker está desligado, o que é esperado: sem consumidor, toda mensagem nova se soma ao acúmulo e a mais antiga só fica mais velha. A queda abrupta de ambas as linhas marca o instante em que o worker foi religado e a fila esvaziou em questão de minutos. A linha azul, a fila de rejeitados, permanece em zero durante toda a janela, o que confirma visualmente o critério de aceite de que o acúmulo não gera rejeição.

<div align="center">

<sub>Figura 2 - Latência da rota de ingestão de mudanças durante o cenário de fila cheia</sub>

![Painel Grafana: latência p50, p90 e p99](./assets/captura_dashboard_latencia.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; A Figura 2 mostra a latência da própria requisição de ingestão, não do processamento da mensagem. Os picos do percentil 99, que chegam perto de um segundo e meio, acontecem justamente na janela em que a carga estava mais alta, e ainda assim a mediana (percentil 50) permanece próxima de zero durante todo o teste. Isso mostra que a variação de latência ficou restrita a uma fração pequena das requisições, coerente com o percentil 95 de 266 milissegundos relatado na tabela acima, e reforça que a fila absorveu a carga sem que a maioria dos clientes percebesse lentidão.

<div align="center">

<sub>Figura 3 - Utilização de CPU dos serviços em container durante o cenário de fila cheia</sub>

![Painel Grafana: CPU do merge-worker, event-worker e processing](./assets/captura_dashboard_cpu_ecs.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Na Figura 3, a linha verde do `merge-worker` cai a zero exatamente na janela em que ele foi desligado para o teste, o que é a evidência mais direta de que o desligamento realmente aconteceu. Os dois picos de aproximadamente setenta por cento logo depois marcam o esforço de drenar o acúmulo assim que o worker volta a rodar, e o retorno gradual a um patamar mais baixo acompanha o esvaziamento da fila mostrado na Figura 1. As linhas do `event-worker` e do `processing` permanecem baixas durante todo o intervalo, o que é esperado, já que nenhum dos dois participa do fluxo de mudanças testado aqui.

### 6.2 Pipeline de mudanças: cenário de timeout de processamento

&emsp; Com carga sustentada em andamento, uma tarefa do worker de mesclagem foi interrompida à força no meio do processamento de um lote, simulando uma falha de infraestrutura em vez de um desligamento planejado. A mensagem em processamento no momento da interrupção não recebe confirmação de entrega e volta a ficar visível na fila após o tempo de invisibilidade configurado, sendo então entregue a uma nova instância do worker.

| Critério de aceite | Resultado |
|---|---|
| A API continua aceitando eventos durante a interrupção | 28.800 eventos enviados, 0% de falha de requisição |
| O serviço se recupera sozinho, sem intervenção manual | orquestrador de containers reiniciou a tarefa automaticamente, sem ficar abaixo da capacidade desejada |
| Não há perda nem entrada indevida na fila de rejeitados | fila de rejeitados sem crescimento, fila de mudanças zerada ao final do teste |

&emsp; A garantia de corretude neste cenário não depende de evitar duplicidade no registro de mudanças, que é um log de acréscimo apenas e pode legitimamente registrar a mesma mensagem mais de uma vez após uma reentrega. A garantia está na regra de mesclagem da tabela corrente, que só aplica uma atualização se o identificador sequencial da mudança for mais recente que o já registrado, o que torna reaplicar o mesmo conteúdo uma operação sem efeito adicional.

### 6.3 Pipeline de eventos: backlog e timeout de cliente

&emsp; Como o SQS Standard não possui limite de "fila cheia" literal, o teste sobre o pipeline de eventos substitui essa expressão pelo risco operacional equivalente: consumidor indisponível e backlog crescente. Os dois workers (`event-worker` e `merge-worker`) foram reduzidos a zero, a API recebeu 1.000 eventos por minuto, o backlog e o banco foram observados, e os workers foram restaurados em seguida. Com os dois workers em zero, 1.001 de 1.001 eventos receberam 2xx, o SQS passou de 0 para 1.001 mensagens e o banco permaneceu em 27.509 linhas; após restaurar uma task de cada worker, a fila voltou a zero e o banco passou a 28.510 linhas, ou seja, 1.001 de 1.001 eventos persistidos.

&emsp; O timeout foi induzido no cliente com limite de 1 milissegundo em 100 requisições. Após 35 segundos, cinco requisições usaram o timeout normal de 7 segundos e deveriam responder 200 em até 5 segundos. Este cenário valida a detecção e a recuperação do lado do cliente, não afirma ter provocado timeout interno da Lambda. Na execução, as 100 de 100 requisições com limite de 1 ms expiraram como planejado e, em seguida, as 5 de 5 requisições responderam 200, com p95 de recuperação de 1.631,7 ms, abaixo do limite de 5 s.

&emsp; Estes dois resultados, obtidos com um método mais leve que o das subseções 6.1 e 6.2 (um único ciclo de queda e restauração de workers, em vez de dez minutos de carga sustentada), confirmam o mesmo comportamento de recuperação sem perda também no pipeline de eventos de frontend, complementando a cobertura do RNF05 sobre os dois fluxos de ingestão do sistema.

## 7. Cenário aprofundado: fila cheia e evento inválido simultâneos (pipeline de mudanças)

&emsp; Como aprofundamento dos cenários da seção 6.1, foi testada a combinação dos dois mecanismos de falha ao mesmo tempo, para verificar que a quarentena de eventos inválidos não fica represada atrás do acúmulo normal da fila. O worker foi desligado, e uma carga válida sustentada de cinco minutos foi disparada simultaneamente com uma segunda carga contendo os cinco tipos de item inválido da seção 5. O worker foi religado, e a fila de rejeitados foi observada em intervalos curtos durante o esvaziamento, em vez de conferida apenas ao final.

| Critério de aceite | Resultado |
|---|---|
| A causa de cada evento inválido aparece na fila de rejeitados durante o esvaziamento, não só ao final | confirmado: a fila de rejeitados cresceu de 22 para 39 já na terceira amostra, quarenta e cinco segundos após religar o worker, com a fila principal ainda em 2.107 mensagens visíveis |
| O acúmulo normal esvazia da mesma forma que no cenário isolado | de cerca de 2.100 a 2.400 mensagens, oscilando com o tráfego contínuo do simulador, a zero em aproximadamente 105 segundos |
| A carga válida é aceita normalmente durante o teste | 48.000 eventos enviados, 0% de falha de requisição |

&emsp; Este foi o resultado mais nítido entre os cenários executados: o mecanismo de quarentena por conteúdo age por mensagem, na primeira vez que ela é recebida, e por isso não espera o esvaziamento completo da fila para identificar um item inválido, mesmo quando o volume de tráfego normal é alto.

## 8. Verificação de regressão dos marcadores incrementais do ETL

&emsp; O pipeline de transformação entre as camadas bronze, silver e gold é incremental e depende de dois marcadores, um por identificador sequencial de mudança e outro por instante de disponibilidade do dado, que nunca podem regredir entre execuções bem sucedidas. Um defeito desse tipo já havia sido identificado e corrigido em sprint anterior, quando uma configuração de janela e margem de segurança incompatíveis fazia o marcador andar para trás a cada execução.

&emsp; Ao final dos cenários das seções 5 a 7, uma consulta específica confirmou que nenhuma execução bem sucedida registrada durante toda a sequência de testes desta sprint apresentou marcador novo menor que o marcador anterior, tanto para o marcador sequencial quanto para o marcador temporal, num total de 853 execuções bem sucedidas somadas entre os dois processos. O resultado indica que a correção aplicada anteriormente continua válida sob a carga e as interrupções produzidas pelos cenários de resiliência.

## 9. Limitação identificada: redirecionamento nativo pela fila

&emsp; Como aprofundamento adicional, foi investigado um cenário que provoca o redirecionamento nativo de mensagens para a fila de rejeitados pelo próprio serviço de fila, após esgotar o número máximo de tentativas de entrega, em vez de pela quarentena explícita do worker. O objetivo era distinguir os dois mecanismos: uma mensagem redirecionada pelo serviço de fila não carrega o motivo específico da falha, enquanto uma mensagem quarentenada pelo worker sempre carrega.

&emsp; A abordagem testada foi revogar temporariamente a permissão de rede do worker até o banco de dados, esperando que uma mensagem em processamento falhasse repetidamente até esgotar as tentativas. O resultado não reproduziu o cenário esperado, e a investigação revelou uma limitação estrutural do desenho atual: o worker abre a conexão com o banco de forma bloqueante, antes de começar a consumir a fila. Uma instância que já estava conectada antes da revogação continua operando pela conexão já estabelecida, já que a permissão de rede da nuvem afeta apenas conexões novas, e uma instância nova, iniciada depois da revogação, falha na própria abertura de conexão antes de chegar a receber qualquer mensagem da fila, o que impede o contador de tentativas de avançar para qualquer mensagem específica.

&emsp; Reproduzir esse cenário de forma controlada exigiria interromper uma consulta em andamento sem derrubar a conexão inteira do worker, uma intervenção mais cirúrgica do que a testada. A limitação foi registrada como um achado de engenharia sobre o desenho atual do worker, e não impede o cumprimento dos critérios de aceite do RNF05 nem do RNF11, já que ambos os mecanismos de rejeição (quarentena explícita e redirecionamento nativo) foram descritos e o primeiro foi validado de ponta a ponta nos cenários anteriores.
