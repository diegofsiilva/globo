# Testes finais de carga, resiliência e observabilidade

Este artefato aprimora os testes dos requisitos não funcionais apresentados em
[`testes-carga-inicial.md`](testes-carga-inicial.md), da Sprint 3. A análise preserva
os resultados daquela entrega, incorpora as execuções posteriores na arquitetura
com Kubernetes e relaciona os achados às decisões de arquitetura.

**Estado em 04/10/2026 (horário de Brasília):** trabalho parcial, pausado após a
consolidação das evidências existentes e a preparação da reexecução. As medições
de setembro identificadas abaixo foram executadas; os
cenários identificados como pendentes ainda não possuem resultado da nova sessão
AWS. Este documento não declara aprovação integral da arquitetura final.

**Escopo da complementação:** aproveitar os resultados da Sprint 3 e das rodadas
posteriores do artefato funcional. A nova sessão prioriza o TI-05.2 após a
migration 030, a observação da elasticidade do HPA e as capturas de uma rodada
representativa no Grafana. Não se exige repetir toda a suíte para incorporar
sua análise a este documento. As evidências históricas mantêm data, ambiente e
limitações; as novas medições não substituem retroativamente seus resultados.

## 1. Evolução em relação à Sprint 3

### 1.1 Continuidade dos requisitos e mudança de arquitetura

A Sprint 3 é a referência dos requisitos, cenários e resultados. A arquitetura
final mantém API Gateway, SQS, workers e processamento em ECS Fargate e PostgreSQL
no RDS no caminho assíncrono. O caminho síncrono do dashboard e da API de leitura
passou a ser servido pelo Ingress do EKS, com Deployments, sondas e HPA. A Lambda
de leitura permanece como contingência. O desenho está em
[`arquitetura-final.md`](arquitetura-final.md).

Assim, a carga de consultas executada no EKS constitui evolução do teste de
leitura; ela não mede a capacidade de ingestão de eventos. Os testes locais no
kind demonstram mecanismos de resiliência, mas seus tempos não são apresentados
como medições do EKS. Resultados da arquitetura antiga permanecem identificados
pelo ambiente e pela data em que foram obtidos.

O exemplo de abertura de venda do enunciado é representado, no domínio do Argus,
por uma rajada de telemetria de 10.000 eventos/minuto. Não há fluxo de venda na
aplicação.

| RNF | Evidência da Sprint 3 | Aprimoramento e evidência posterior | Situação da comprovação |
|---|---|---|---|
| RNF01 — capacidade | Pico de 10.000 eventos/min; 12.152 eventos aceitos e persistidos incluindo aquecimento; lotes de 150 mil a 600 mil | Separação entre requisições, eventos, drenagem e disponibilidade na leitura; plano de reexecução identificado por rodada | Comprovado no ambiente histórico; reexecução na nova sessão pendente |
| RNF02 — tempo de consulta | 4.587 consultas, máximo de 1.581 ms; ressalva sobre a representatividade da base | Seis telas, limiares agregados e por tela, rodadas comparáveis e estresse no EKS | Há resultados no EKS até 100 usuários e reprovações documentadas em carga maior |
| RNF03 — escalabilidade | Uma e duas tasks, carga de 1.000 e 2.000 eventos/min, com reconciliação | Diagnóstico do HPA sem métrica e reexecução após instalação do `metrics-server` | Escala manual da ingestão comprovada no histórico; aumento efetivo de réplicas no EKS pendente |
| RNF04 — tolerância a evento inválido | 18/18 falhas identificadas e 150/150 eventos válidos processados | Preservar verificação por evento, causa na DLQ e continuidade do consumidor na revisão final | Evidência histórica disponível; não houve nova execução em outubro |
| RNF05 — recuperação | Backlog de 1.001 eventos reconciliado; ensaios maiores de mudanças sem reconciliação completa | Recuperação com identificação dos eventos; testes posteriores de remoção de pod e rollout no kind | Recuperação local demonstrada; reconciliação das falhas maiores e reexecução remota pendentes |
| RNF11 — registros de falha | Causas de rejeição consultáveis, sem amostra suficiente de todos os campos exigidos | Exigir horário, componente, erro e correlação em cada falha controlada, com registros sanitizados | Parcial; dashboards não substituem a evidência dos registros |

### 1.2 Tratamento do feedback dos testes funcionais

O feedback recebido reconheceu a análise de carga e a busca do limite entre 100
e 200 usuários. As pendências foram incorporadas ao trabalho de evolução:

| Pendência apontada | Tratamento neste artefato | Evidência necessária para encerrar |
|---|---|---|
| Reexecutar TI-05.2 na AWS após migration 030 | Pré-condição para avaliar o caminho completo entre ingestão e leitura, seção 3.5 | Migration confirmada, execução remota, tempo de aparecimento e saída do teste |
| Medir elasticidade do HPA | Cenário CF04, com observação da criação e prontidão das réplicas | Série de CPU, réplicas atuais/desejadas, evento de escala e resultados k6 sincronizados |
| Corrigir texto residual do CT13c | Correção no artefato funcional: recusa da promoção não oculta as 500 hipóteses geradas | Coerência entre texto, tabela, migrations 032/033 e teste existente |
| Atualizar referências `apps/basica/` | Comandos de reprodução usam `apps/fullstack/`; logs antigos conservam sua origem histórica | Novas execuções terão caminhos atuais, data e versão, sem reescrever saídas antigas |
| Anexar capturas do Grafana | Seção 4 distingue capturas históricas de capturas ainda necessárias | Painéis legíveis da janela da nova execução, com fonte, unidade e cenário |

## 2. Método, ambiente e critérios

### 2.1 Registro por execução

Cada nova rodada deve preservar: `test_id`, início e fim em UTC, commit e tag das
imagens, ambiente, caminho de entrada, versão e origem do gerador, duração por
fase, taxa oferecida e atingida, base consultada, recursos e quantidade de
réplicas. O dimensionamento deve permanecer registrado também depois da falha ou
da escala. A base precisa ser caracterizada por volume, período e cardinalidade;
uma base vazia não reproduz os ensaios históricos das telas.

Os JSONs e logs da suíte k6 ficam em
`apps/fullstack/tests/carga/resultados/`, que não é versionado. As cópias
sanitizadas que sustentarem conclusões devem ser preservadas em
`artefatos/evidencias/`, junto das capturas pertinentes. Tokens, credenciais,
identificadores de conta e endpoints não fazem parte das evidências públicas.

**Verificação de preparação em 04/10/2026:** o perfil AWS `g4` autenticou no
Ubuntu/WSL e permitiu consultas de inventário em `us-east-1`. A conta consultada
não continha instâncias RDS, clusters EKS/ECS, repositórios ECR ou buckets S3.
O checkout também não continha state/configuração local do Terraform nem a base
histórica naquele momento. A base foi fornecida e verificada posteriormente no
mesmo dia, conforme o registro abaixo. A infraestrutura foi recriada, mas a
carga validada da base continua sendo pré-condição das novas medições. Ver
[registro inicial de preparação](evidencias/testes-carga-finais/preparacao-aws-2026-10-04.json).

**Origem da base identificada.** O
[plano de carga inicial](plano-argus-v3.md#6-carga-inicial) documenta o dump MySQL
do parceiro `argus_dump.sql`, aproximadamente 4 GB e 68,7 milhões de linhas,
convertido por `tools/etl_dump.py` para `data/parquet/`. A pasta inclui
`_manifest.json`, com `row_counts`, `empty_tables`, `total_rows` e dados da
conversão. O loader transfere os Parquets do bucket de origem e confere as
contagens carregadas no PostgreSQL contra esse manifesto.

Há bases diferentes conforme o teste: a ingestão usa eventos sintéticos gerados
pelo k6; o RNF02 inicial descreve cerca de 24 mil eventos sintéticos; a carga das
telas na implantação posterior consulta as camadas derivadas da base histórica.
A reexecução no EKS em 24/09 declara explicitamente RDS carregado com as 32
tabelas do manifesto. O arquivo fornecido em 04/10 contém 33 tabelas no schema,
32 com registros e `investigation_feedback` sem registros, confirmando essa
distinção para a base recebida. Os 33 nomes coincidem com a migration 004.

Apesar de se chamar `argus_dump.sql`, o arquivo recebido é **gzip**: possui
515.082.641 bytes comprimidos e 4.148.103.553 bytes de SQL após descompressão.
A leitura integral verificou a integridade gzip e contou **68.717.811 registros**,
dos quais 41.191.820 em `prom_point` e 18.218.743 em `signal_point`. Esses valores
correspondem às dimensões documentadas para o dataset Argus. Foram preservados
os hashes SHA-256 e as contagens por tabela no
[registro de verificação da base](evidencias/testes-carga-finais/verificacao-base-2026-10-04.json).

O dump e os Parquets não são versionados. O original recebido permaneceu
inalterado; o conversor existente foi executado sobre uma cópia descomprimida.
A verificação identifica a base esperada, mas as evidências
históricas consultadas não contêm o hash do arquivo de setembro para comparação
byte a byte. A conversão terminou com **68.717.811 registros e zero descartes**;
as contagens das 32 tabelas conferem com a leitura independente do dump. O
[manifesto sanitizado](evidencias/testes-carga-finais/conversao-base-2026-10-04.json)
preserva essa conferência. A conferência da carga no RDS é uma etapa separada.

A infraestrutura foi recriada com EKS 1.33, PostgreSQL 16.13 em `db.t3.medium`
com 100 GiB e imagens do commit `326769cbb9d9`. A consulta ao banco confirmou
as 33 migrations e o índice `bronze.event_lsn` válido; ver
[verificação remota](evidencias/testes-carga-finais/migrations-aws-2026-10-04.json).
As duas réplicas do backend e as duas do frontend ficaram prontas, e o HPA
passou a receber CPU pelo `metrics-server`. Isso valida a preparação, sem
antecipar o resultado da carga nem a ocorrência de escala.

**Pausa da execução:** a conversão e o envio da base ao S3 terminaram, mas a
carga no RDS foi interrompida antes da validação integral. Os dados já gravados
foram preservados para retomada. Não foram executados nesta sessão o TI-05.2,
a rodada representativa das telas nem a medição de elasticidade. A retomada
exige conferir o estado da carga e concluir a preparação do processamento.

### 2.2 Medidas e interpretação

| Medida | Definição e limite de interpretação |
|---|---|
| Latência HTTP | Tempo de uma requisição observado pelo k6; o aceite da ingestão não inclui toda a execução assíncrona |
| Throughput HTTP | Requisições concluídas por segundo na fase observada |
| Throughput de eventos | Eventos aceitos/processados por segundo; deve considerar o conteúdo de cada lote |
| Erros por segundo | Contagem de falhas na janela dividida por sua duração; percentual de erros é apresentado separadamente |
| Drenagem após retomada | Tempo entre a retomada do consumidor e a conclusão da persistência dos eventos aceitos, com verificação das filas |
| Persistência em bronze | Diferença entre o instante real de envio e a gravação em `bronze.event` |
| Frescor ponta a ponta | Diferença entre o instante real de envio e a primeira observação do evento na API; registrar o intervalo de polling |
| CPU | Valor acompanhado de componente e denominador: utilização do serviço/instância ou percentual da CPU requisitada pelo pod |
| Recuperação | Tempo até restabelecer o serviço e, separadamente, até concluir o processamento do acúmulo |

A SQS conta mensagens, que podem conter vários eventos. Fila visível zerada,
isoladamente, não demonstra ausência de perda: devem ser verificadas também as
mensagens em processamento, a DLQ e a reconciliação dos identificadores do teste.
Duplicidades são contadas separadamente. Para eventos válidos, a conclusão de
persistência integral exige todos os eventos aceitos localizados no destino.

O relógio virtual `sim.now()` determina a visibilidade do dado do domínio. A
medição de atraso usa o tempo real, como `load_test_sent_at`; os dois relógios
não devem ser subtraídos um do outro.

Na preparação da nova rodada, está planejado congelar o relógio em
`2026-08-02T12:00:00Z`, dentro do período do dump, para consultar uma janela com
histórico acumulado; essa etapa não foi executada antes da pausa. O resumo de 24/09 registra
`2026-07-12T00:49:03.430489+00:00`, próximo ao início dos dados. Portanto, mesmo
com o mesmo volume em bronze, a quantidade visível nas views pode ser diferente.
A nova rodada complementa a evidência da arquitetura; seus números não isolam
o efeito do HPA em uma comparação direta de antes/depois com setembro.

### 2.3 Planos de teste aprimorados

Os critérios originais permanecem vinculados a
[`requisitos.md`](requisitos.md). Limiares auxiliares do k6 e a margem de drenagem
adotada na Sprint 3 são critérios operacionais do ensaio, não novos requisitos
atribuídos ao parceiro.

| Cenário | RNF e procedimento | Critério e evidência | Estado |
|---|---|---|---|
| CF01 — nominal, pico e recuperação | RNF01: executar 1.000, 10.000 e 1.000 eventos/min no roteiro existente; registrar aquecimento e intervalos | Taxa atingida, zero rejeição/descarte do gerador, p95 abaixo dos limites declarados por fase e reconciliação integral | Script pronto; nova medição pendente |
| CF02 — lote e fila acumulada | RNF01/05: lote nominal de 150.000; depois dois lotes com `event-worker` parado, seguido de retomada; três/quatro lotes são extensão | Zero rejeição, DLQ sem eventos válidos, contagem por `test_id` e filas drenadas; referência operacional de 450 s adotada na Sprint 3, com origem do cronômetro explícita | Script de injeção pronto; captura coordenada e nova medição pendentes |
| CF03 — consultas e telas | RNF02: mesmas seis telas, 5/25/100 VUs, base caracterizada; limiares por nível e por tela | Erros <1%, requisição p95 <3 s e p99 <5 s, abertura p95 <5 s, telas completas >99%; máximo também deve ser reportado para verificar o teto de 5 s do RNF02 original | Executado no EKS em setembro; resultados na seção 3.2 |
| CF04 — elasticidade | RNF03: repetir carga crescente com HPA recebendo CPU; sustentar cada fase tempo suficiente para medir reação, incluindo retorno à carga baixa | Observar réplicas desejadas, criadas e prontas, tempo até atender tráfego e efeito em latência/erros; manter limiares do CF03 e registrar o maior nível aprovado | Métrica do HPA disponível em 24/09; escala efetiva no EKS pendente |
| CF05 — falhas e recuperação | RNF05: distinguir timeout de cliente, interrupção do worker e indisponibilidade de dependência; marcar início/fim da falha | Cliente detecta timeout; serviço retoma; eventos aceitos reconciliados; rejeições e duração da indisponibilidade explícitas | Timeout de cliente e interrupção têm evidência histórica; timeout interno exige cenário próprio |
| CF06 — eventos inválidos | RNF04: lote misto de entradas válidas e inválidas | Válidos antes/depois persistidos, inválidos identificáveis por causa e continuidade do consumidor | Evidência da Sprint 3 disponível |
| CF07 — registros de falha | RNF11: coletar amostras durante CF02/CF05/CF06 | Horário, etapa/componente, causa e correlação; cenários distinguíveis e ausência de dado sensível desnecessário | Comprovação ainda parcial |
| CF08 — ingestão até leitura | RNF05 e frescor: confirmar migration 030 e executar TI-05.2 na AWS; depois medir amostra/lote com identificação | Evento consultável em até 300 s no TI-05.2, campos preservados e redação de dado pessoal; uma amostra não é um p95 | Correção local validada; reexecução AWS pendente |

O pico de CF01 dura **um minuto** no script atual. Uma janela sustentada maior
requer parametrização antes da execução; repetir o roteiro não converte esse
pico em um ensaio contínuo de longa duração. No CF04, o objetivo é observar a
elasticidade após a correção do HPA. A carga deve aumentar com acompanhamento,
sem presumir que ultrapassar 900 VUs seja condição necessária para disparar a
escala.

O cenário de “fila cheia” é operacionalizado como acúmulo de mensagens com o
consumidor interrompido, seguido de retomada e reconciliação. Esse ensaio mede
pressão e recuperação da fila; não declara ter atingido uma quota da SQS.

## 3. Resultados existentes e análise de desempenho e resiliência

### 3.1 Referência da Sprint 3: ingestão, lotes e recuperação

As medições abaixo pertencem à implantação histórica, conforme os
[resultados de 02/09](assets/performance/evidencias-2026-09-02.json) e os
[resultados por lote de 09/09](assets/performance/evidencias-lotes-2026-09-09.json).

| Ensaio | Resultado observado | Conclusão sustentada |
|---|---|---|
| Pico de ingestão | 10.000 eventos na fase de pico; p95 161,8 ms; 12.152/12.152 persistidos incluindo as demais fases e aquecimento | Capacidade de aceite e persistência naquele pico e ambiente |
| Lote de 150.000 | Injeção 10,078 s; drenagem registrada de 120 s; 150.000 itens gravados; DLQ 0 | Recuperação e integridade registradas para esse lote |
| Dois lotes, 300.000 | Drenagem 191 s; 300.000 itens gravados; DLQ 0 | Recuperação do acúmulo no ambiente histórico |
| Três lotes, 450.000 | Drenagem 259 s; 450.000 itens gravados; DLQ 0 | Recuperação do acúmulo no ambiente histórico |
| Quatro lotes, 600.000 | Drenagem 346 s; 600.000 itens gravados; DLQ 0 | Drenagem 104 s abaixo do limite operacional adotado de 450 s |
| Eventos inválidos | 18/18 falhas identificadas e 150/150 válidos preservados | Isolamento das entradas inválidas no cenário executado |
| Backlog de eventos | Fila 0 → 1.001 → 0 e banco +1.001 | Recuperação sem perda no recorte reconciliado |
| Falhas do fluxo de mudanças | 96.020 aceitos no backlog e 28.800 na interrupção do worker, sem reconciliação completa | Retomada observada; ausência de perda ainda não comprovada nesses dois ensaios |

Os lotes demonstram recuperação de acúmulo, e não equivalência automática a uma
taxa contínua de 10.000 eventos/min. Da mesma forma, a latência do fragmento HTTP
não mede o atraso até a disponibilidade na leitura.

### 3.2 Evolução das consultas: do ASG ao EKS

O teste de carga documentado em
[`testes-funcionais.md`](testes-funcionais.md#testes-de-carga) é incorporado como
evidência de evolução dos RNFs de desempenho. O roteiro
[`carga_ui.js`](../apps/fullstack/tests/carga/carga_ui.js) reproduz as requisições
das seis telas; não mede renderização visual de navegador. O indicador de
abertura corresponde à conclusão das chamadas que compõem cada tela.

| Rodada | Ambiente/origem do gerador | Requisições reportadas | Níveis | p95 de requisição a 100 VUs | Resultado e alcance |
|---|---|---:|---|---:|---|
| 18/09 | API em EC2/ASG, k6 em EC2 na VPC | 25.501 de carga | 5/25/100 VUs, 2 min por nível | 802 ms | Critérios atendidos; novas instâncias não entraram em serviço durante a janela |
| 21/09 — A | Ingress do EKS, k6 em EC2 na VPC | 25.576 no total | 5/25/100 VUs, 2 min por nível | 662 ms | Zero erros; duas réplicas; HPA sem métrica |
| 24/09 — A repetida | Ingress do EKS, k6 local fora da VPC | 24.177 no total | 5/25/100 VUs, 2 min por nível | 841 ms | Zero erros, limiares por tela atendidos; HPA com métrica, sem aumento de réplicas |

Os totais dos JSONs do EKS incluem uma requisição adicional de preparação. As
requisições de carga dos níveis somam 25.575 em 21/09 e 24.176 em 24/09. Essa
diferença deve ser mantida ao comparar totais ou calcular taxas.

**Análise.** As rodadas de 18 e 21/09 usaram o mesmo roteiro e gerador dentro da
VPC e sustentam a comparação entre caminhos. A variação do p95 a 100 usuários
não estabelece superioridade geral de uma plataforma: são execuções pontuais.
A rodada de 24/09 acrescenta latência de rede externa e valida a configuração
com `metrics-server`; não deve ser interpretada como regressão causada por ele.

Evidências: [carga original](evidencias/testes-carga.txt),
[rodada A de 21/09](evidencias/carga-kubernetes/rodada-a-resultado.json),
[rodada de 24/09](evidencias/carga-kubernetes-2026-09-24/carga-ui_resultado_20260925T004042Z.json)
e [estado do HPA](evidencias/carga-kubernetes-2026-09-24/hpa-e-cluster.txt).

### 3.3 Busca do limite e elasticidade ainda não medida

| VUs na rodada B de 21/09 | Requisições de carga | Erros | p95 por requisição | p95 de abertura | Resultado |
|---:|---:|---:|---:|---:|---|
| 200 | 29.448 | 0% | 2.766 ms | 3.076 ms | Reprovado nos limiares por tela |
| 450 | 37.254 | 15,21% | 9.486 ms | 10.166 ms | Reprovado |
| 900 | 31.171 | 24,80% | 30.001 ms | 30.120 ms | Reprovado, com esgotamento do prazo |

A 200 VUs, a tela Agora alcançou p95 de 5.075 ms na abertura e 4.441 ms por
requisição; Recorte alcançou 3.189 ms por requisição. Portanto, o agregado não
autoriza aprovar esse nível. O maior nível aprovado observado foi 100 e o
primeiro reprovado foi 200. Esse intervalo caracteriza **a configuração de duas
réplicas com HPA sem métricas**, não o teto universal da aplicação.

O diagnóstico registrou `FailedGetResourceMetric` e ausência da API de métricas.
Após a inclusão do add-on, a rodada de 24/09 registrou
`ScalingActive=True`/`ValidMetricFound`, mas permaneceu em duas réplicas. A
disponibilidade da métrica está comprovada; a elasticidade no EKS ainda não.

Na próxima rodada devem ser correlacionados: aumento da demanda, CPU dos pods,
réplicas desejadas, chegada de pods prontos, distribuição do tráfego e recuperação
da latência. A causa de eventual saturação deve ser investigada também no banco
e nas conexões; CPU isolada não determina o gargalo.

Evidências: [rodada B](evidencias/carga-kubernetes/rodada-b-resultado.json),
[saída k6](evidencias/carga-kubernetes/rodada-b-saida-k6.txt) e
[diagnóstico do cluster](evidencias/carga-kubernetes.txt).

### 3.4 Resiliência posterior: alcance dos ensaios locais

| Ensaio no kind em 24/09 | Resultado observado | Relação com a arquitetura |
|---|---|---|
| Remover pod com uma réplica | Reposição em 8,3 s; 354 falhas em 2.470 requisições, 14,3% | Reposição do processo não garante continuidade quando não existe outra réplica pronta |
| Remover um dos dois pods | Reposição em 6,2 s; 2.262 requisições sem falhas | Sustenta a escolha de redundância no recorte local testado |
| Rollout, imagem inválida e undo | 5.394 requisições, cinco timeouts, 0,09%; pods anteriores atenderam durante a imagem inválida | Demonstra o mecanismo de atualização/retorno; não houve zero falhas na janela completa |
| Indisponibilidade do PostgreSQL | Backend saiu de Ready, permaneceu sem reinício e voltou após restauração do banco/schema | Demonstra separação entre prontidão e vida; houve timeouts/503 durante a indisponibilidade |

As medições constam em
[autocura](evidencias/resiliencia-kind-01-autocura.txt),
[rollout/undo](evidencias/resiliencia-kind-02-rollout-e-undo.txt) e
[perda do banco](evidencias/resiliencia-kind-03-perda-do-banco.txt).
Não substituem a reconciliação de eventos do fluxo SQS nem comprovam esses
tempos de recuperação na AWS.

### 3.5 TI-05.2, migration 030 e frescor

O TI-05.2 de 17/09 aceitou e persistiu o evento em bronze, mas ele não apareceu
na leitura em 300 s. A investigação encontrou backlog histórico e varreduras
por `_lsn` sem índice em `bronze.event`. A
[migration 030](../apps/fullstack/db/migrations/030_indice_lsn_em_evento.sql)
adicionou o índice; o
[teste do plano SQL](../apps/fullstack/processing/tests/test_plano_da_etl.py)
validou localmente a mudança do acesso. Essa validação local não comprova a
latência final na AWS nem a resolução de todo o backlog.

O valor histórico de **38 min 32 s** do relatório da Sprint 3 corresponde a
uma sentinela, após intervenção manual no watermark. É uma observação única,
não p95. O script
[`drenagem_lotes.sql`](../apps/fullstack/tools/loadtest/drenagem_lotes.sql)
calcula percentis até a gravação em bronze; ele não calcula sozinho a distribuição
até a disponibilidade na API.

A reexecução deve confirmar migration e estado do processamento, manter o prazo
de 300 s do TI-05.2 e registrar o caminho de leitura utilizado. Para avaliar a
arquitetura final, a leitura deve atravessar o Ingress; a verificação específica
do authorizer em TI-05.1 exige o API Gateway e deve permanecer separada. Após o
teste funcional, o frescor sob carga exige várias observações ou instrumentação
da disponibilidade, com percentis e tamanho da amostra explícitos. Não se deve
avançar manualmente o watermark durante a medição e atribuir o resultado à
operação automática do pipeline.

**Resultado da nova sessão:** pendente. O relato da reprovação e da correção
está em [`testes-funcionais.md`](testes-funcionais.md#diagnóstico-do-caso-reprovado).

## 4. Observabilidade e evidências visuais

### 4.1 Fontes e indicadores

A stack em [`observability/`](../apps/fullstack/observability/) usa Prometheus
para métricas do k6 e Grafana para as fontes Prometheus/CloudWatch. O
`metrics-server` usado pelo HPA é um componente distinto: sua existência não
implica coleta histórica de CPU dos pods pelo Prometheus.

| Indicador | Fonte e painel | O que observar na nova rodada |
|---|---|---|
| Latência | k6/Prometheus, percentis por cenário/rota | Alteração no pico e durante recuperação; p95/p99 com unidade em ms |
| Throughput | k6/Prometheus, `rate(k6_http_reqs_total[1m])` | Requisições/s atingidas; eventos/s em contador próprio quando houver lotes |
| Erros/s | k6/Prometheus, contador de respostas inesperadas por segundo | Início, duração e fim da degradação, além do percentual de erros |
| CPU dos workers e banco | ECS/RDS via CloudWatch no Grafana | Média e máximo na mesma janela da carga |
| CPU e réplicas do EKS | Amostras da API de métricas e dos objetos HPA/Deployment, preservadas com horário UTC | Relação entre demanda, alvo do HPA, escala e pods prontos |
| Filas | SQS via CloudWatch | Mensagens visíveis/em voo, DLQ e idade da mais antiga |

Exemplos já usados pelo dashboard, com filtro da execução:

```promql
sum(rate(k6_http_reqs_total{testid=~"$testid"}[1m]))
sum(rate(k6_http_reqs_total{testid=~"$testid",expected_response="false"}[1m]))
```

Na configuração histórica do painel de API Gateway, `Count`, `4xx` e `5xx`
são consultados como `Sum` em períodos de 60 s. Antes de apresentar esses
valores como taxas por segundo, é necessário conferir a conversão por 60; a
unidade visual do eixo não faz essa conversão. Os percentis do cliente também
devem conservar a identificação de rota/cenário, sem tratar o máximo entre
percentis como um percentil global de todas as requisições.

### 4.2 Capturas históricas reaproveitadas

As figuras abaixo pertencem aos ensaios de ingestão/resiliência documentados na
Sprint 3. Demonstram a visualização já implementada. Não são capturas da nova
sessão AWS nem das rodadas de carga das telas no EKS. O dashboard versionado de
resiliência consulta CloudWatch para esses componentes; as figuras não devem
ser atribuídas automaticamente ao Prometheus apenas por estarem no Grafana.

**Figura 1 — Latência histórica da ingestão de mudanças.** A variação de cauda
deve ser lida junto da janela do cenário, não como distribuição das consultas
do dashboard.

![Grafana: latência histórica da ingestão](assets/captura_dashboard_latencia.png)

**Figura 2 — Requisições e erros históricos da ingestão.** A conversão de
contagens por período para taxas deve ser auditada conforme a seção 4.1.

![Grafana: throughput e erros históricos](assets/captura_dashboard_throughput.png)

**Figura 3 — CPU histórica dos serviços ECS.** O consumo dos workers auxilia a
análise da interrupção e retomada; não representa CPU dos pods do EKS.

![Grafana: CPU histórica dos serviços ECS](assets/captura_dashboard_cpu_ecs.png)

**Figura 4 — CPU histórica do RDS.** Deve ser correlacionada à latência e às
consultas para investigar pressão no banco.

![Grafana: CPU histórica do RDS](assets/captura_dashboard_cpu_rds.png)

**Figura 5 — Fila de mudanças e DLQ.** Crescimento e drenagem demonstram o
comportamento operacional; a integridade depende também da reconciliação.

![Grafana: fila e DLQ históricas](assets/captura_dashboard_fila_changes_dlq.png)

Fonte das cinco figuras: equipe do projeto, evidências preservadas da Sprint 3.

### 4.3 Evidências a acrescentar na reexecução

As novas capturas devem usar intervalo absoluto em UTC, `test_id`, legenda,
unidade e componente identificados. A janela deve incluir antes/durante/depois
da carga ou falha. Para CF04, marcar a solicitação de escala e a entrada das
novas réplicas em serviço. Um painel vazio não é evidência de zero erros.

O executor local com `COM_GRAFANA=1` envia métricas k6 ao Prometheus. Para esta
complementação, foi preparada uma extensão local do executor existente
[`gerador_ec2.sh`](../apps/fullstack/tests/carga/gerador_ec2.sh), preservada fora
do commit desta pausa. O protótipo executa Prometheus restrito ao loopback da
EC2, recebe as métricas reais do k6 por Remote Write e preserva um snapshot
antes de encerrar a instância. Também registra início/fim UTC e `vmstat`, para
verificar a capacidade do gerador. Sua incorporação à suíte permanece pendente.
O envio usa as estatísticas de tendência do
[Remote Write do k6](https://grafana.com/docs/k6/latest/results-output/real-time/prometheus-remote-write/)
e marca as séries como inativas ao terminar. Percentis de séries distintas não
são somados nem promediados para representar o percentil global.

No procedimento preparado para a retomada, as amostras do cluster devem conservar
seus horários de coleta. A conversão para
OpenMetrics mantém esses timestamps; os blocos são importados, com o servidor
parado, em uma instância local separada de Prometheus. Não há interpolação de
CPU nem reconstrução de séries a partir dos resumos k6. Os auxiliares Python
usados nessa coleta/importação são temporários e não integram o código entregue.
O novo dashboard e sua fonte também foram guardados localmente para continuidade.
Os painéis já existentes permanecem versionados em
[`observability/`](../apps/fullstack/observability/); a configuração específica
da nova rodada ainda precisa ser incorporada e validada com a carga completa.

Uma execução curta do cenário de timeout confirmou o caminho EC2 → snapshot →
Prometheus local. Ela ocorreu antes da carga da base, serviu à validação da
coleta e não é apresentada como medição de capacidade das telas.

**Situação:** novas capturas pendentes da retomada e execução. Os resumos
JSON existentes sustentam os resultados numéricos, mas não permitem reconstruir
uma série temporal real que não tenha sido preservada.

## 5. Impactos nas decisões de arquitetura

| Observação do teste | Decisão/correção | Verificação disponível e limite |
|---|---|---|
| Ingestão aceitou rajadas e drenou lotes após recuperação | Manter recepção desacoplada por SQS e consumidores independentes | Evidência histórica de aceite, drenagem e contagem; repetir no ambiente final para atualizar a comprovação |
| Fragmentos próximos de 240 KB produziram HTTP 414 | Adotar fragmentação com teto operacional validado de 40.000 bytes no teste por lote | Lotes seguintes aceitos sem esse erro; preservar tamanho e distribuição do payload no comparativo |
| Consultas do pipeline filtravam `_lsn` sem índice | Migration 030 adiciona índice em `bronze.event` | Plano SQL validado localmente; efeito remoto e TI-05.2 pendentes |
| Backlog da carga inicial concorreu com novos eventos | Rever inicialização/gestão dos watermarks e acompanhar atraso por etapa | Diagnóstico existente; não há evidência de solução automática completa na nova sessão |
| HPA não recebeu métricas no EKS | Declarar add-on `metrics-server` na infraestrutura | Métrica confirmada em 24/09; elasticidade ainda precisa de execução |
| Uma réplica ficou indisponível ao remover pod; duas mantiveram atendimento no kind | Manter redundância e avaliar rollout/prontidão sob carga | Comportamento medido localmente; tempos não extrapolados para EKS |
| Rodada antiga apresentou 502 associados à conexão persistente | Revisão do keep-alive documentada nos testes funcionais | Rodada corrigida passou; conservar configuração no ambiente comparado |

Cada decisão distingue o problema observado da hipótese sobre sua causa. Uma
correção implementada ou um recurso configurado não equivale, por si só, a
resultado aprovado na nova arquitetura.

## 6. Reprodução e trabalho restante

Os comandos abaixo usam Bash, executados a partir da raiz, depois de preparar
o ambiente e suas variáveis locais. O perfil desta sessão é `g4`.

```bash
export AWS_PROFILE=g4 AWS_REGION=us-east-1
make -C apps/fullstack observabilidade-up
make -C apps/fullstack observabilidade-check

make -C apps/fullstack teste-performance CENARIO=rnf01 COM_GRAFANA=1
make -C apps/fullstack teste-lote-drenagem COM_GRAFANA=1
make -C apps/fullstack teste-performance CENARIO=falha-timeout COM_GRAFANA=1
```

Para a leitura no EKS, selecionar explicitamente o Ingress. `make env` usa a
Lambda de contingência como endereço inicial; usar esse valor sem revisão
testaria outro caminho.

```bash
ARGUS_URL_EKS="$(make -s -C apps/fullstack k8s-url)"
make -C apps/fullstack teste-carga-ui \
  ARGUS_API_URL="$ARGUS_URL_EKS" COM_GRAFANA=1
```

O acúmulo exige parar apenas o consumidor do cenário, confirmar sua parada,
registrar a fila e restaurar o dimensionamento anterior. A injeção é executada
por `make -C apps/fullstack teste-lotes-acumulados LOTES=2 COM_GRAFANA=1`;
esse comando sozinho não interrompe o consumidor nem comprova drenagem. O alvo
`resiliencia-timeout` interrompe uma task; o nome não deve ser usado para
classificar o resultado como timeout interno. Detalhes operacionais estão no
[guia da suíte](../apps/fullstack/tests/carga/README.md).

| Prioridade | Trabalho restante | Condição para encerrar |
|---|---|---|
| 1 | Retomar o ambiente provisionado, concluir a carga e preparar o processamento | Implantação saudável, migrations/versões registradas e contagens conferidas com o manifesto |
| 2 | Executar TI-05.2 após migration 030 | Saída remota e tempo observado, com aprovação ou reprovação explícita |
| 3 | Medir elasticidade efetiva no EKS | Aumento observado, tempo de reação, desempenho por fase e retorno após a carga |
| 4 | Atualizar ingestão, acúmulo e recuperação | Eventos identificados/reconciliados, filas e DLQ verificadas |
| 5 | Completar observabilidade e RNF11 | Novas capturas da janela medida e amostras sanitizadas de falha |
| 6 | Atualizar a matriz de resultados | Cada conclusão ligada à evidência correspondente, mantendo limitações e resultados reprovados |

Até a conclusão desses itens, a entrega comprova a evolução documentada em
setembro e explicita o que ainda não foi medido. Nenhum cenário pendente deve
receber resultado ou captura estimados.
