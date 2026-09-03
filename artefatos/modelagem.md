# Modelagem de Software - Casos de Uso

## 1. Objetivo

Este artefato descreve o comportamento da Plataforma Argus a partir do diagrama de casos de uso e dos requisitos já definidos para o projeto. O foco está nas interações observáveis entre a plataforma, as fontes de telemetria, o usuário operacional, o evento temporal que inicia o processamento e o serviço de apoio à observabilidade.

As descrições foram escritas em nível essencial: apresentam a intenção dos atores e as responsabilidades do sistema sem transformar decisões internas de implementação em passos do usuário. Detalhes técnicos relevantes aparecem apenas em **Requisitos especiais**, quando representam restrições de segurança, desempenho, confiabilidade, rastreabilidade ou qualidade dos dados.

A fronteira considerada é a **Plataforma Argus**, desde o recebimento da telemetria até a apresentação de evidências e o registro da avaliação humana. A correção da aplicação monitorada, o tratamento de chamados e a execução de mudanças em produção não fazem parte desta fronteira.

## 2. Atores

| Ator | Tipo | Responsabilidade e interesse principal |
|---|---|---|
| **Fontes de telemetria** | Sistema externo | Publicar eventos de sessão e mudanças das fontes monitoradas para que sejam armazenados e analisados pelo Argus. |
| **Novo checkpoint disponível** | Evento temporal | Informar que uma nova fotografia consistente da camada analítica está pronta para processamento. Não representa uma pessoa, mas o estímulo temporal que inicia o UC02. |
| **Usuário Operacional** | Ator humano principal | Monitorar a plataforma, explorar dados e investigar degradações. Abrange, sobretudo, os perfis de Engenharia de Observabilidade e Suporte N2 definidos no entendimento de UX. |
| **Amazon CloudWatch** | Sistema de apoio | Disponibilizar logs, métricas e alarmes sobre a saúde da ingestão e dos componentes da plataforma. |

O ator **Usuário Operacional** aparece duas vezes no diagrama somente para reduzir o cruzamento de associações. As duas figuras representam o mesmo papel e possuem as mesmas permissões conceituais.

## 3. Diagrama de casos de uso

<div align="center">

<sub>Figura 1 - Diagrama de casos de uso da Plataforma Argus</sub>

![Diagrama de casos de uso da Plataforma Argus](./assets/diagrama_casos_uso.jpg)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

O diagrama separa os comportamentos em três grupos. **Processamento Automático** contém a entrada e a análise contínua da telemetria. **Monitoramento e Investigação Inicial** reúne as ações que ajudam o operador a reconhecer e começar a apurar um problema. **Diagnóstico e Avaliação** contém os aprofundamentos usados para explicar, delimitar e revisar uma degradação.

### 3.1 Relações entre os casos de uso

| Caso base | Relação | Caso relacionado | Interpretação |
|---|---|---|---|
| UC02 - Processar telemetria e detectar | `<<include>>` | UC03 - Produzir hipóteses de causa provável | Toda execução válida tenta produzir explicações candidatas; o resultado pode conter zero hipóteses quando não há evidência suficiente. |
| UC06 - Investigar uma degradação | `<<include>>` | UC07 - Identificar e ajustar o recorte afetado | Delimitar a população afetada faz parte de toda investigação. |
| UC06 - Investigar uma degradação | `<<include>>` | UC08 - Comparar com períodos anteriores | Toda investigação confronta a janela atual com uma referência adequada. |
| UC06 - Investigar uma degradação | `<<extend>>` | UC10 - Analisar hipóteses de causa provável | A análise de hipóteses ocorre quando existem hipóteses publicadas e o operador decide aprofundá-las. |
| UC06 - Investigar uma degradação | `<<extend>>` | UC11 - Reconstruir a timeline do incidente | A reconstrução temporal é usada quando a ordem dos sinais e mudanças é relevante para o diagnóstico. |
| UC07 - Identificar e ajustar o recorte afetado | `<<extend>>` | UC12 - Consultar a trajetória de uma sessão | Uma sessão representativa pode ser aberta para validar o comportamento observado no agregado. |
| UC10 - Analisar hipóteses de causa provável | `<<extend>>` | UC13 - Registrar validade sobre uma hipótese | Depois de avaliar as evidências, o operador pode registrar sua conclusão sobre a hipótese. |

Em UML, `<<include>>` indica um comportamento obrigatório do caso base. `<<extend>>` representa um comportamento condicional, executado somente quando sua condição de extensão é satisfeita.

## 4. Visão geral e rastreabilidade

| ID | Caso de uso | Ator iniciador | Relação principal | Requisitos relacionados |
|---|---|---|---|---|
| UC01 | Ingerir telemetria | Fontes de telemetria | Independente | RF01 a RF07; RNF01, RNF03 a RNF06, RNF09 a RNF11 |
| UC02 | Processar telemetria e detectar | Novo checkpoint disponível | Inclui UC03 | RF15 e RF17; RNF04, RNF05 e RNF11 |
| UC03 | Produzir hipóteses de causa provável | UC02 | Incluído por UC02 | RF17 e RNF08 |
| UC04 | Monitorar o estado atual da plataforma | Usuário Operacional | Independente | RF12, RF13, RF15 e RF16 |
| UC05 | Explorar a telemetria coletada | Usuário Operacional | Independente | RF08 a RF12 |
| UC06 | Investigar uma degradação | Usuário Operacional | Inclui UC07 e UC08; pode ser estendido por UC10 e UC11 | RF13 a RF17 |
| UC07 | Identificar e ajustar o recorte afetado | UC06 | Incluído por UC06; pode ser estendido por UC12 | RF08 a RF11 e RF16 |
| UC08 | Comparar com períodos anteriores | UC06 | Incluído por UC06 | RF14 |
| UC09 | Acompanhar a integridade da ingestão | Usuário Operacional | Apoiado pelo Amazon CloudWatch | RNF04, RNF05 e RNF11 |
| UC10 | Analisar hipóteses de causa provável | Usuário Operacional | Extensão de UC06; pode ser estendido por UC13 | RF17 e RNF08 |
| UC11 | Reconstruir a timeline do incidente | Usuário Operacional | Extensão de UC06 | RF16; US01 |
| UC12 | Consultar a trajetória de uma sessão | Usuário Operacional | Extensão de UC07 | RF08 e RF16; US06 e US08 |
| UC13 | Registrar validade sobre uma hipótese | Usuário Operacional | Extensão de UC10 | RF17 |

A rastreabilidade indica afinidade entre cada caso de uso e os requisitos, sem impor uma relação de um para um. Um requisito pode participar de mais de um objetivo do usuário, assim como um caso de uso pode reunir vários requisitos complementares.

## 5. Descrições dos casos de uso

### UC01 - Ingerir telemetria

**Escopo.** Plataforma Argus, da recepção de um evento até sua persistência rastreável na camada de entrada.

**Nível.** Objetivo de sistema externo.

**Atores.** Ator iniciador: Fontes de telemetria. Atores de apoio: serviço de autorização e infraestrutura de mensageria, considerados mecanismos internos à fronteira do Argus.

**Interessados e interesses.** As fontes de telemetria desejam entregar os dados sem acoplamento à capacidade instantânea de processamento. O usuário operacional precisa de dados íntegros, recentes e identificáveis. A equipe de plataforma precisa de reprocessamento, idempotência e falhas rastreáveis. Segurança e privacidade exigem autenticação e ausência de dados pessoais desnecessários.

**Pré-condições.** A fonte conhece o contrato da rota correspondente; possui credencial válida com audiência de ingestão; e o endpoint de ingestão está publicado. Para eventos de mudança, a tabela de origem e a chave da linha precisam pertencer ao catálogo aceito.

**Pós-condições.** Em caso de sucesso, o evento foi aceito, enfileirado, validado e persistido no histórico de entrada apropriado, ficando disponível para os ciclos posteriores. Em caso de falha, nenhum estado válido anterior é corrompido e o motivo pode ser localizado por logs, métricas ou fila de mensagens não processadas.

**Fluxo Básico.**

1. A fonte prepara um evento de telemetria conforme o contrato aplicável.
2. A fonte envia o evento ao ponto único de ingestão por uma conexão segura e apresenta sua credencial.
3. O Argus autentica a origem e identifica se o conteúdo representa um evento de sessão ou uma mudança de dado monitorado.
4. O Argus aceita a mensagem e a encaminha para o fluxo assíncrono correspondente.
5. O consumidor valida o envelope, os identificadores, o instante, o tipo e os demais campos obrigatórios.
6. O Argus registra o evento no histórico de entrada e atualiza a visão corrente quando aplicável.
7. O consumidor confirma o processamento da mensagem e registra métricas e informações de rastreabilidade.

**Fluxos alternativos.**

Alternativos:

- **A1 - Evento de sessão:** a mensagem recebida contém a trajetória de uso de uma aplicação cliente e é persistida com os identificadores de evento, sessão e dispositivo.
- **A2 - Evento de mudança:** a mensagem informa operação, chave, estado anterior, estado posterior, posição da origem e instante de captura; o Argus a adiciona ao log de mudanças e materializa a versão mais recente.
- **A3 - Reentrega:** se a mesma mensagem for entregue novamente, o Argus reconhece sua identidade ou posição e mantém apenas o efeito esperado, sem duplicar o estado lógico.
- **A4 - Mudança fora de ordem:** se uma mudança possui posição anterior à já aplicada, ela permanece rastreável no histórico, mas não sobrescreve o estado corrente mais novo.

Exceções:

- **E1 - Credencial ausente ou inválida:** a requisição é recusada antes de alcançar a fila.
- **E2 - Payload inválido:** o consumidor rejeita a mensagem, registra o motivo e permite que as mensagens válidas seguintes continuem sendo processadas.
- **E3 - Falha temporária de persistência:** a mensagem volta a ficar disponível para nova tentativa; depois do limite de tentativas, segue para a fila de mensagens não processadas.
- **E4 - Fonte ou operação não permitida:** o evento não altera as tabelas correntes e a ocorrência fica registrada para investigação.

**Requisitos especiais.** A ingestão deve suportar inicialmente pelo menos 1.000 requisições por minuto; usar autenticação com audiência exclusiva de ingestão; tolerar reentregas; preservar a ordem lógica por posição da origem; não perder silenciosamente mensagens já aceitas; e produzir rastreabilidade sem registrar tokens ou dados pessoais desnecessários.

**Lista de variantes.** Rotas de evento de sessão e de mudança; plataformas web, móveis e TVs; protocolos modernos e legados priorizados; operações de inclusão, atualização e exclusão; eventos `request`, `vitals`, `screen_view`, `video_view`, `session` e `error`.

**Frequência de ocorrência.** Contínua e alta, acompanhando o volume das fontes; a meta inicial de capacidade é de 1.000 requisições por minuto em operação normal.

**Problemas em aberto.** Confirmar com o parceiro a lista definitiva de plataformas e protocolos do MVP; definir a política de retenção e expurgo dos dados de entrada; e calibrar limites de reentrega, alarme e capacidade com volume de produção.

### UC02 - Processar telemetria e detectar

**Escopo.** Plataforma Argus, do reconhecimento de um novo checkpoint analítico até a publicação de uma execução consistente de qualidade, detecção e hipóteses.

**Nível.** Objetivo de processamento automático.

**Atores.** Ator iniciador: Novo checkpoint disponível. O serviço de processamento executa o comportamento dentro da fronteira do Argus.

**Interessados e interesses.** O usuário operacional precisa que as degradações sejam detectadas com dados que realmente estariam disponíveis naquele instante. A equipe de dados deseja resultados determinísticos e reproduzíveis. A equipe de plataforma precisa evitar publicação duplicada ou incompleta quando houver concorrência, falha ou retomada de workers.

**Pré-condições.** Um checkpoint Gold foi concluído com `ready_through` e posição de origem conhecidas; existe um manifesto de análise habilitado; e as versões de fatos até a barreira do checkpoint estão disponíveis.

**Pós-condições.** Em caso de sucesso, a execução guarda sua fotografia de entrada, resultado de qualidade, estado do baseline, anomalias e hipóteses, e avança o cursor de análise na mesma confirmação protegida. Em caso de falha, a execução não é publicada como concluída nem avança o cursor indevidamente.

**Fluxo Básico.**

1. Um novo checkpoint analítico fica disponível.
2. O Argus identifica o checkpoint elegível ainda não concluído para o manifesto ativo.
3. O Argus reserva o trabalho, define o instante simulado e a posição máxima da origem e obtém uma concessão temporária exclusiva.
4. O Argus captura uma fotografia consistente contendo somente fatos com versão e disponibilidade compatíveis com o checkpoint.
5. O Argus calcula e registra um resumo verificável das entradas da execução.
6. O Argus avalia a qualidade e a recência de cada fonte.
7. O Argus compara as séries com seus baselines causais e identifica anomalias materiais.
8. O Argus executa o UC03 - Produzir hipóteses de causa provável.
9. O Argus confirma, numa única operação protegida, os resultados e o avanço do cursor.
10. O Argus publica métricas sobre duração, volume, anomalias, hipóteses, atraso e fila de checkpoints.

**Fluxos alternativos.**

Alternativos:

- **A1 - Nenhum checkpoint novo:** o ciclo termina sem criar uma execução.
- **A2 - Trabalho já reservado:** outra réplica mantém uma concessão válida; a réplica atual não processa o mesmo checkpoint.
- **A3 - Retomada:** uma concessão expirada permite que outra réplica retome o checkpoint com novo token de exclusão.
- **A4 - Nenhuma anomalia material:** a execução é concluída com resultado vazio de incidentes e hipóteses, preservando o registro de qualidade e baseline.
- **A5 - Fonte atrasada ou incompleta:** o canário registra o estado da fonte; a ausência reduz cobertura e pode originar diagnóstico de qualidade, sem inventar uma degradação operacional.

Exceções:

- **E1 - Fotografia acima do limite:** a tentativa termina com `input_limit_exceeded`; entradas não são truncadas silenciosamente.
- **E2 - Resumo de entrada divergente numa retentativa:** a tentativa termina com `input_digest_mismatch` e o cursor não avança.
- **E3 - Perda de concessão ou token de exclusão:** o worker antigo não pode publicar seus resultados.
- **E4 - Falha de cálculo ou banco:** a transação final é revertida e o checkpoint permanece elegível para nova tentativa.

**Requisitos especiais.** A execução deve respeitar causalidade (`available_at` menor ou igual ao instante da execução), isolamento consistente, determinismo, idempotência, concessão de 120 segundos, heartbeat de 30 segundos, limite de 250 mil fatos por fotografia e confirmação protegida por fencing. O processamento deve terminar antes que o acúmulo de checkpoints comprometa a atualidade do diagnóstico.

**Lista de variantes.** Execução simulada ou ao vivo; primeira tentativa ou retomada; fonte saudável, atrasada, incompleta, silenciosa, inválida ou desconhecida; série de contagem/latência transformada ou taxa/percentual em escala original.

**Frequência de ocorrência.** A cada checkpoint elegível. O serviço consulta trabalho novo periodicamente, com intervalo operacional padrão de 30 segundos.

**Problemas em aberto.** Calibrar os limites de anomalia e materialidade com dados de produção; medir se a capacidade atual conclui cada execução antes do próximo checkpoint; e definir retenção para fotografias, execuções e artefatos analíticos.

### UC03 - Produzir hipóteses de causa provável

**Escopo.** Motor de hipóteses do Argus, desde as anomalias detectadas até a persistência de explicações candidatas e suas evidências.

**Nível.** Subfunção incluída no processamento automático.

**Atores.** Iniciador indireto: UC02 - Processar telemetria e detectar.

**Interessados e interesses.** O usuário operacional deseja uma lista curta, ordenada e explicável de possíveis causas. A equipe de observabilidade precisa entender por que uma hipótese recebeu determinada pontuação. O parceiro precisa evitar afirmações conclusivas sem validação humana. A equipe de dados exige resultados reproduzíveis e temporalmente corretos.

**Pré-condições.** Existe uma execução com fotografia consistente, resultados do canário e pelo menos a avaliação do detector. O catálogo de regras, métricas, fontes e relações entre entidades está versionado.

**Pós-condições.** As hipóteses geradas, descartadas ou não avaliáveis são persistidas com estado, pontuação, cobertura, confiança, fatores, evidências, versão das regras e vínculo com a execução. Nenhuma hipótese é marcada automaticamente como causa confirmada.

**Fluxo Básico.**

1. O motor recebe as anomalias e o contexto disponíveis na fotografia da execução.
2. O Argus agrupa achados relacionados sem obrigar que um achado pertença a apenas um grupo.
3. O motor avalia as assinaturas das famílias de hipótese aplicáveis.
4. Para cada candidata, o motor coleta evidências favoráveis, contrárias e indisponíveis, respeitando alinhamento temporal e relação conhecida entre entidades.
5. O motor calcula força, coincidência temporal, corroboração, especificidade, impacto e qualidade.
6. O motor aplica penalidades, calcula score, cobertura e confiança e registra a contribuição de cada fator.
7. O motor classifica a candidata como gerada, descartada ou com evidência insuficiente.
8. O Argus ordena as hipóteses geradas e persiste candidatos, fatores, evidências e estatísticas da execução.
9. O resultado fica disponível para publicação e posterior análise humana.

**Fluxos alternativos.**

Alternativos:

- **A1 - Evidência suficiente:** a hipótese atinge os limites de score e cobertura e é publicada como candidata gerada.
- **A2 - Evidência indisponível:** a ausência é registrada como indisponível e reduz a cobertura, mas não é tratada automaticamente como contradição.
- **A3 - Evidência contrária determinante:** a candidata é descartada e preserva a justificativa.
- **A4 - Pico ao vivo esperado:** o motor produz contexto de aumento esperado quando volume cresce durante um evento compatível sem piora proporcional de erro ou experiência.
- **A5 - Problema na própria fonte:** baixa qualidade pode produzir uma hipótese de atraso ou falha de dados, separada das causas operacionais.

Exceções:

- **E1 - Catálogo ou manifesto inválido:** a execução não é publicada e registra o erro de configuração.
- **E2 - Limite de candidatos excedido:** o corte determinístico é aplicado e auditado; se houver truncamento incompatível com o portão de qualidade, o manifesto não pode ser promovido.
- **E3 - Relação semântica desconhecida:** o motor não usa aproximação textual para ligar entidades; a evidência permanece não relacionada.
- **E4 - Falha ao persistir:** nenhuma publicação parcial é confirmada.

**Requisitos especiais.** Toda hipótese deve partir de ao menos uma detecção, usar somente evidências disponíveis no instante analisado e manter linguagem não conclusiva. A mesma entrada e configuração devem gerar o mesmo resultado. Hipótese gerada exige score mínimo de 40 e cobertura mínima de 0,50; confiança alta exige score mínimo de 80, cobertura mínima de 0,80 e qualidade mínima de 0,70. Os limites operacionais são de 10 mil candidatos, 2 mil por família e 500 hipóteses geradas por execução.

**Lista de variantes.** Regressão após deploy; falha interna de backend; playback ou autorização; degradação de CDN; origem ou encoding; região ou ISP; bloqueio de WAF; player ou dispositivo; QoE sem erro explícito; pico ao vivo esperado; atraso ou falha de fonte.

**Frequência de ocorrência.** Uma tentativa por execução válida do UC02; a quantidade de hipóteses resultantes varia de zero até o limite configurado.

**Problemas em aberto.** Validar com especialistas os pesos e limites de cada família; ampliar o conjunto rotulado para medir precisão e cobertura; revisar relações entre entidades conforme o catálogo evoluir; e definir a política de retenção das revisões.

### UC04 - Monitorar o estado atual da plataforma

**Escopo.** Dashboard Argus, na visão consolidada do estado operacional atual.

**Nível.** Objetivo do usuário.

**Atores.** Ator iniciador: Usuário Operacional.

**Interessados e interesses.** Engenharia de Observabilidade quer reconhecer rapidamente desvios relevantes. Suporte N2 deseja saber se um relato isolado coincide com uma degradação ampla. Produto e operação precisam compreender impacto, severidade e abrangência sem interpretar dados brutos.

**Pré-condições.** O usuário possui acesso de leitura autorizado; existe uma janela temporal corrente; e há dados publicados nas visões de consulta, ainda que algumas fontes estejam atrasadas ou indisponíveis.

**Pós-condições.** O usuário visualiza uma fotografia coerente do estado atual, com sinais, severidade, tendência, baseline e escopo. A consulta não altera os dados analíticos. O período e os filtros selecionados permanecem disponíveis para aprofundamento.

**Fluxo Básico.**

1. O usuário abre a visão atual do dashboard.
2. O Argus identifica o instante de referência, o período e o escopo ativos.
3. O sistema consulta sinais e anomalias publicados para essa janela.
4. O Argus apresenta os principais indicadores e destaca as degradações por severidade e impacto.
5. O usuário seleciona um sinal para compreender valor atual, referência, limiar, tendência e contexto.
6. O Argus mostra os detalhes e os caminhos disponíveis para hipóteses, timeline e recorte.
7. O usuário decide encerrar o acompanhamento ou iniciar o UC06 - Investigar uma degradação.

**Fluxos alternativos.**

Alternativos:

- **A1 - Operação sem degradação:** o Argus apresenta estado saudável e mantém visíveis a atualidade e a cobertura das fontes.
- **A2 - Mais de uma degradação:** o sistema ordena os sinais por severidade e impacto, permitindo que o usuário escolha um deles.
- **A3 - Alteração de período ou escopo:** o Argus preserva os filtros cumulativos e atualiza indicadores e sinais.
- **A4 - Dados parciais ou antigos:** o último resultado válido pode ser mantido com indicação explícita de parcialidade ou desatualização.

Exceções:

- **E1 - Falha ou timeout de consulta:** o sistema diferencia falha de resultado vazio, mostra uma referência rastreável e oferece nova tentativa.
- **E2 - Resposta inválida:** os dados não são apresentados como válidos; o usuário recebe uma mensagem compreensível.
- **E3 - Acesso não autorizado:** a plataforma impede a visualização e não expõe dados operacionais.

**Requisitos especiais.** Consultas simples devem responder em até cinco segundos. A tela deve distinguir carregamento, atualização, vazio, parcial, desatualizado e erro; funcionar por teclado; apresentar nomes acessíveis; respeitar redução de movimento; e evitar exposição de identificadores ou atributos pessoais desnecessários.

**Lista de variantes.** Janelas de 15 minutos, 30 minutos, 3 horas e 24 horas; temas claro e escuro; visualização larga, tablet ou móvel; estado saudável, degradado, parcial ou desatualizado; escopo por plataforma, fabricante, região e versão do aplicativo.

**Frequência de ocorrência.** Frequente durante todo o turno operacional, com atualização periódica e novas consultas sempre que período ou escopo mudam.

**Problemas em aberto.** Validar com o parceiro os limiares e nomes de severidade; definir quais degradações devem ocupar a visão principal; e consolidar a cobertura regional e de fontes no ambiente definitivo.

### UC05 - Explorar a telemetria coletada

**Escopo.** Dashboard e API de leitura do Argus, para pesquisa, agrupamento e visualização dos dados coletados.

**Nível.** Objetivo do usuário.

**Atores.** Ator iniciador: Usuário Operacional.

**Interessados e interesses.** O operador deseja responder perguntas ad hoc sem escrever consultas técnicas. Suporte N2 precisa localizar padrões por sessão, dispositivo, plataforma ou erro. Engenharia de Observabilidade quer avaliar volume, distribuição e comportamento temporal. Segurança exige campos e dimensões de consulta controlados.

**Pré-condições.** O usuário está autorizado; existe telemetria publicada para leitura; e as dimensões consultáveis estão registradas em uma lista segura.

**Pós-condições.** O Argus apresenta o conjunto, série ou agrupamento correspondente ao período e aos filtros escolhidos. O estado da investigação é preservado para refinamento ou navegação. Nenhum dado de origem é alterado.

**Fluxo Básico.**

1. O usuário abre a área de exploração.
2. O Argus apresenta a janela temporal atual, os filtros ativos e um resumo dos dados disponíveis.
3. O usuário escolhe um tipo de evento ou métrica.
4. O usuário aplica um ou mais filtros de escopo.
5. O usuário escolhe como agrupar ou cruzar os resultados.
6. O Argus valida os parâmetros e consulta as visões publicadas.
7. O sistema apresenta indicadores, série temporal e distribuição por grupo, mantendo visíveis período, filtros e unidade.
8. O usuário refina a consulta, abre um recorte relevante ou encerra a exploração.

**Fluxos alternativos.**

Alternativos:

- **A1 - Sugestão de filtros:** ao escolher uma dimensão, o Argus oferece somente valores existentes e permitidos no conjunto consultável.
- **A2 - Filtros cumulativos:** cada novo filtro restringe a consulta anterior; remover ou limpar filtros recalcula o resultado.
- **A3 - Outro agrupamento:** o usuário alterna entre fonte, entidade, métrica, tipo, modelo, versão, rota ou intervalo de tempo.
- **A4 - Resultado paginado:** quando houver mais itens, o Argus entrega um cursor para continuar a leitura sem repetir ou saltar registros.
- **A5 - Nenhum resultado:** a plataforma informa que o recorte é vazio e permite rever os filtros.

Exceções:

- **E1 - Dimensão ou intervalo inválido:** a API recusa a consulta com erro de validação e o dashboard preserva o estado anterior.
- **E2 - Timeout, rede indisponível ou resposta inválida:** o sistema identifica o tipo de falha e oferece nova tentativa.
- **E3 - Campo sensível solicitado:** o Argus recusa a dimensão não autorizada e não retorna seus valores como sugestão.

**Requisitos especiais.** Consultas simples devem retornar em até cinco segundos; filtros devem ser cumulativos; datas devem usar UTC/ISO 8601 no contrato; dimensões devem ser controladas por lista permitida; paginação deve ser estável; e estados de carregamento, vazio e erro devem ser acessíveis e distintos.

**Lista de variantes.** Eventos ou séries Gold; lista, indicador, gráfico temporal, agrupamento ou matriz de duas dimensões; filtros de sessão, dispositivo, tipo, aplicativo, sistema operacional, fabricante, modelo, rota, fonte, entidade e métrica; intervalos de agregação configuráveis.

**Frequência de ocorrência.** Sob demanda, normalmente várias vezes durante uma investigação ou análise exploratória.

**Problemas em aberto.** Confirmar quais dimensões regionais e de ISP podem ser combinadas; definir busca segura por códigos presentes em atributos livres; e revisar limites de paginação e agregação com o volume definitivo.

### UC06 - Investigar uma degradação

**Escopo.** Plataforma Argus, da seleção de uma degradação até a reunião de evidências suficientes para orientar uma decisão humana.

**Nível.** Objetivo do usuário.

**Atores.** Ator iniciador: Usuário Operacional.

**Interessados e interesses.** Engenharia de Observabilidade quer reduzir o tempo de diagnóstico e distinguir causa interna, externa ou de qualidade de dados. Suporte N2 precisa relacionar sintomas de usuários a um problema conhecido. O parceiro deseja evidências atribuídas às fontes e conclusões apresentadas como hipóteses, não certezas automáticas.

**Pré-condições.** O usuário está autorizado; existe um sinal, anomalia, hipótese ou relato que justifique a investigação; e a plataforma possui ao menos uma janela de dados consultável.

**Pós-condições.** O problema fica descrito por janela, escopo afetado, comparação histórica e evidências disponíveis. O usuário pode formar uma conclusão provisória, registrar feedback sobre hipótese ou reconhecer que ainda faltam dados. A consulta não altera a telemetria original.

**Fluxo Básico.**

1. O usuário seleciona uma degradação ou inicia a investigação a partir de um sinal, hipótese, sessão ou relato.
2. O Argus preserva a janela, o escopo e a âncora que originaram a investigação.
3. O sistema apresenta o resumo do problema, incluindo métricas desviantes, severidade, início e impacto conhecido.
4. O Argus executa o UC07 - Identificar e ajustar o recorte afetado.
5. O Argus executa o UC08 - Comparar com períodos anteriores.
6. O usuário confronta o recorte, a referência histórica e as fontes disponíveis.
7. Quando necessário, o usuário aprofunda a análise por hipótese, timeline ou sessão.
8. O Argus mantém as evidências e sua proveniência vinculadas ao mesmo contexto de investigação.
9. O usuário encerra a análise com uma conclusão provisória ou registra que são necessárias mais evidências.

**Fluxos alternativos.**

Alternativos:

- **A1 - Investigação iniciada por sinal:** o contexto inicial contém a métrica, a entidade e o instante do desvio.
- **A2 - Investigação iniciada por hipótese:** o contexto começa com a explicação candidata, suas evidências e o segmento associado.
- **A3 - Investigação iniciada por sessão:** o Argus parte da trajetória individual e amplia para o recorte agregado.
- **A4 - Hipóteses publicadas:** o usuário pode executar o UC10 - Analisar hipóteses de causa provável.
- **A5 - Ordem temporal relevante:** o usuário pode executar o UC11 - Reconstruir a timeline do incidente.
- **A6 - Dados parciais:** o usuário continua com o último resultado válido, desde que a plataforma destaque quais fontes ou períodos estão ausentes.

Exceções:

- **E1 - Contexto inicial inexistente ou removido:** o Argus informa que o item não está disponível e oferece retorno à visão atual.
- **E2 - Nenhuma referência histórica adequada:** a investigação prossegue sem comparação, com a limitação registrada.
- **E3 - Falha numa consulta complementar:** o sistema preserva os resultados já válidos e permite repetir somente a etapa que falhou.
- **E4 - Perda de autorização:** a investigação é interrompida sem expor dados adicionais.

**Requisitos especiais.** Período, filtros, sinal, hipótese e âncora temporal devem permanecer coerentes entre as telas. Toda evidência deve indicar fonte e instante. Informações ausentes não podem ser apresentadas como evidência contrária. A interface deve evitar linguagem conclusiva e permitir navegação acessível entre resumo e detalhe.

**Lista de variantes.** Início por sinal, hipótese, sessão ou monitoramento manual; degradação global ou segmentada; fonte saudável, parcial ou atrasada; investigação curta pelo resumo ou aprofundada por recorte, comparação, timeline e hipótese.

**Frequência de ocorrência.** Sempre que uma degradação relevante é detectada ou relatada; pode ocorrer várias vezes para o mesmo incidente à medida que chegam novas evidências.

**Problemas em aberto.** Definir critérios formais de abertura e encerramento de uma investigação; decidir como persistir e compartilhar seu contexto entre operadores; e integrar o resultado com o processo externo de incidentes ou chamados, que permanece fora da fronteira atual.

### UC07 - Identificar e ajustar o recorte afetado

**Escopo.** Área de diagnóstico do Argus responsável por delimitar a população, as entidades e as dimensões relacionadas a uma degradação.

**Nível.** Subfunção obrigatória de objetivo do usuário.

**Atores.** Iniciador indireto: UC06 - Investigar uma degradação. Ator participante: Usuário Operacional.

**Interessados e interesses.** O operador precisa distinguir um problema global de uma concentração em plataforma, modelo, versão, região, rota, entidade ou fonte. Suporte N2 quer reconhecer usuários e aparelhos representativos. Produto deseja estimar alcance e participação no tráfego sem confundir volume com taxa de erro.

**Pré-condições.** Uma investigação está ativa com janela inicial definida; há dados agregados para pelo menos uma dimensão; e o usuário possui acesso de leitura.

**Pós-condições.** O recorte ativo contém dimensões, valores, janela, volume, participação, taxa e cobertura conhecidos. O contexto atualizado fica disponível para comparação, hipóteses, timeline e consulta de sessões.

**Fluxo Básico.**

1. O Argus recebe a janela e o escopo da investigação.
2. O sistema apresenta a distribuição do sinal ou dos erros entre dimensões relevantes.
3. O usuário seleciona uma dimensão com concentração significativa.
4. O Argus aplica o valor escolhido ao conjunto de filtros cumulativos.
5. O sistema recalcula volume, participação no tráfego, participação nos erros, taxa e diferença em relação aos demais grupos.
6. O usuário adiciona, substitui ou remove filtros até obter um recorte explicativo e com cobertura suficiente.
7. O Argus registra o recorte ativo no contexto da investigação.
8. O usuário confirma o recorte ou abre uma sessão representativa pelo UC12.

**Fluxos alternativos.**

Alternativos:

- **A1 - Sugestões existentes:** o Argus oferece valores presentes nos dados para reduzir filtros inválidos.
- **A2 - Problema global:** nenhuma dimensão concentra o desvio; o usuário mantém o recorte amplo.
- **A3 - Mais de um segmento afetado:** o usuário compara grupos e mantém o conjunto de filtros que melhor representa o impacto.
- **A4 - Sessão representativa disponível:** o usuário executa o UC12 - Consultar a trajetória de uma sessão.
- **A5 - Dimensão ausente:** a análise continua com menor especificidade e a cobertura é apresentada explicitamente.

Exceções:

- **E1 - Combinação não suportada:** o Argus impede cruzamentos sem contrato ou sem granularidade compatível e explica a limitação.
- **E2 - Filtro inválido ou sensível:** a consulta é recusada sem expor valores não permitidos.
- **E3 - Recorte sem dados:** o sistema informa o vazio e permite desfazer o último ajuste.
- **E4 - Falha de consulta:** o recorte anterior permanece visível como último resultado válido, marcado como desatualizado quando necessário.

**Requisitos especiais.** Os filtros devem ser cumulativos e reproduzíveis. As métricas de participação precisam distinguir tráfego de erros. Valores desconhecidos não devem formar recortes específicos. Dimensões opcionais reduzem cobertura, mas não invalidam análises que não dependem delas. Consultas devem respeitar as listas seguras de facetas e agrupamentos.

**Lista de variantes.** Recorte por fonte, entidade, métrica, plataforma, sistema operacional, fabricante, modelo, versão, região, ISP, rota, sessão ou dispositivo; agrupamento simples ou matriz de duas dimensões; escopo global, segmentado ou sem resultado.

**Frequência de ocorrência.** Uma ou mais vezes por investigação, com refinamentos sucessivos até que o escopo esteja claro.

**Problemas em aberto.** A base possui UF e ISP como dimensões marginais separadas, sem garantir o cruzamento entre ambas; também é necessário validar com o parceiro os mínimos de volume, lift e diferença usados para considerar um recorte material.

### UC08 - Comparar com períodos anteriores

**Escopo.** Área de comparação do Argus, responsável por confrontar a janela investigada com uma referência histórica equivalente.

**Nível.** Subfunção obrigatória de objetivo do usuário.

**Atores.** Iniciador indireto: UC06 - Investigar uma degradação. Ator participante: Usuário Operacional.

**Interessados e interesses.** O usuário operacional quer saber o que realmente mudou, evitando interpretar padrões sazonais como incidentes. Engenharia de Observabilidade precisa comparar valor, variação e dispersão. Produto deseja distinguir pico esperado de degradação de experiência.

**Pré-condições.** A investigação possui janela e filtros definidos; existem dados históricos potencialmente comparáveis; e o usuário está autorizado.

**Pós-condições.** A plataforma apresenta a janela atual e a referência com duração, escopo, valores e variações coerentes. A referência escolhida fica associada ao contexto da investigação. Se nenhuma referência for adequada, a limitação fica explícita.

**Fluxo Básico.**

1. O Argus recebe a janela e o recorte atuais.
2. O sistema sugere uma referência histórica compatível.
3. O usuário confirma ou escolhe outra referência.
4. O Argus valida se as janelas possuem duração, granularidade e filtros comparáveis.
5. O sistema consulta os dados atuais e históricos sem incluir informações futuras ao instante analisado.
6. O Argus apresenta as séries alinhadas, os valores de cada janela, a variação absoluta e percentual e, quando disponível, a significância estatística.
7. O sistema destaca mudanças de infraestrutura, eventos editoriais ou diferenças de cobertura relevantes entre os períodos.
8. O usuário incorpora a comparação à investigação.

**Fluxos alternativos.**

Alternativos:

- **A1 - Período imediatamente anterior:** o Argus compara com uma janela contígua de mesma duração.
- **A2 - Ontem ou semana anterior:** o sistema alinha o mesmo horário em outro dia, preservando duração e fuso de apresentação.
- **A3 - Última janela estável:** o Argus utiliza uma janela anterior sem incidente compatível.
- **A4 - Último pico ao vivo:** o sistema seleciona um evento editorial anterior comparável.
- **A5 - Outra referência:** o usuário escolhe manualmente uma janela válida.

Exceções:

- **E1 - Referência não encontrada:** o sistema informa a ausência e permite escolher outro tipo de comparação.
- **E2 - Janela ou duração inválida:** o Argus recusa os parâmetros e preserva a seleção anterior.
- **E3 - Cobertura desigual:** a comparação é exibida com ressalva ou bloqueada quando a diferença inviabiliza uma leitura responsável.
- **E4 - Falha de consulta:** a plataforma não calcula variações com dados parciais apresentados como completos e oferece nova tentativa.

**Requisitos especiais.** As janelas devem usar a mesma duração, granularidade, unidade e escopo, salvo quando a diferença for explicitamente mostrada. Baselines devem ser causais. Horários devem ser transportados em UTC e apresentados com fuso identificável. Consultas simples devem concluir em até cinco segundos.

**Lista de variantes.** Período anterior, ontem no mesmo horário, semana anterior, janela estável, pico ao vivo anterior ou intervalo manual; comparação de contagem, taxa, percentual, latência, Apdex ou QoE; referência encontrada ou ausente.

**Frequência de ocorrência.** Ao menos uma vez por investigação, podendo ser repetida com referências diferentes.

**Problemas em aberto.** Definir o critério definitivo de janela estável; estabelecer como selecionar eventos ao vivo equivalentes; validar o cálculo de significância e envelope histórico; e tratar mudanças de cobertura entre fontes.

### UC09 - Acompanhar a integridade da ingestão

**Escopo.** Operação da Plataforma Argus, com uso de métricas, logs e alarmes para avaliar a saúde do caminho de entrada dos dados.

**Nível.** Objetivo do usuário.

**Atores.** Ator iniciador: Usuário Operacional. Ator de apoio: Amazon CloudWatch.

**Interessados e interesses.** O operador precisa distinguir ausência real de sinal de atraso ou falha no pipeline. A equipe de plataforma deseja detectar backlog, mensagens não processadas, serviços indisponíveis e latência crescente. Segurança exige observabilidade sem vazamento de credenciais ou identificadores sensíveis.

**Pré-condições.** Os componentes publicam métricas e logs operacionais; o usuário possui acesso autorizado à visão correspondente; e o CloudWatch está recebendo as observações configuradas.

**Pós-condições.** O usuário conhece o estado de cada fluxo de ingestão, sua recência, backlog, falhas e alarmes ativos. Quando existe anomalia operacional, a evidência necessária para encaminhar a investigação fica identificada. Nenhuma mensagem é removida manualmente por este caso de uso.

**Fluxo Básico.**

1. O usuário abre a visão de integridade da ingestão ou recebe indicação de um alarme.
2. O Argus consulta o estado publicado das fontes, filas, consumidores e persistência.
3. O CloudWatch fornece métricas, logs e alarmes dos componentes monitorados.
4. A plataforma apresenta recência, volume recebido, backlog, tentativas, mensagens não processadas, saúde dos serviços e atraso dos checkpoints.
5. O usuário compara o comportamento atual com os limites operacionais.
6. O usuário seleciona um componente ou uma fonte com desvio.
7. O Argus mostra a referência da falha, o período e a evidência disponível para diagnóstico.
8. O usuário registra ou encaminha a ocorrência pelo processo operacional externo.

**Fluxos alternativos.**

Alternativos:

- **A1 - Operação saudável:** todos os fluxos estão dentro dos limites e as filas de mensagens não processadas permanecem vazias.
- **A2 - Atraso estrutural conhecido:** o Argus diferencia a latência esperada da fonte de um atraso anormal.
- **A3 - Backlog transitório:** a fila cresce, mas os consumidores continuam avançando; o sistema acompanha a recuperação antes de elevar a severidade.
- **A4 - Falha de uma fonte:** o Argus marca resultados analíticos dependentes como parciais e evita interpretar silêncio como melhora.

Exceções:

- **E1 - CloudWatch indisponível:** o sistema informa que a observabilidade de apoio está indisponível e não declara a ingestão como saudável.
- **E2 - Consumidor sem progresso:** o Argus destaca heartbeat ausente, idade da fila ou mensagens na fila de falhas para investigação.
- **E3 - Persistência indisponível:** as mensagens permanecem para nova tentativa; após o limite configurado, são isoladas de forma rastreável.
- **E4 - Métricas incoerentes:** a condição é tratada como problema de observabilidade, não como confirmação de perda de dados.

**Requisitos especiais.** Logs devem ser estruturados e incluir identificador de requisição, componente, status e latência. Tokens nunca podem ser registrados; parâmetros sensíveis devem ser redigidos. Alarmes devem cobrir filas de falha, idade e backlog das filas, réplicas abaixo do desejado, falhas consecutivas de análise, perda de concessão e ausência prolongada de execução concluída.

**Lista de variantes.** Fluxo de eventos de sessão ou de mudanças; acompanhamento preventivo ou iniciado por alarme; fonte com latência imediata, de minutos ou batch; falha na API, fila, worker, banco, processamento ou mecanismo de observabilidade.

**Frequência de ocorrência.** Contínua por métricas e alarmes, com consulta humana recorrente durante o turno e sempre que houver alerta.

**Problemas em aberto.** Validar limites de alarme com a carga real; definir objetivos formais de atualidade por fonte; documentar o procedimento de reprocessamento das filas de falha; e integrar a tela do Argus ao fluxo de resposta operacional do parceiro.

### UC10 - Analisar hipóteses de causa provável

**Escopo.** Dashboard e API de hipóteses do Argus, da listagem das explicações candidatas até a avaliação detalhada de uma delas.

**Nível.** Extensão de objetivo do usuário.

**Atores.** Ator iniciador: Usuário Operacional, durante o UC06 - Investigar uma degradação.

**Interessados e interesses.** O operador deseja priorizar caminhos de investigação e compreender cada evidência. Especialistas de domínio precisam distinguir suporte, contradição e indisponibilidade. O parceiro exige que a solução apoie, mas não substitua, a decisão humana.

**Pré-condições.** Existe uma investigação ativa; há uma execução publicada do motor de hipóteses compatível com a janela; e o usuário possui autorização de leitura.

**Pós-condições.** O usuário compreende a hipótese selecionada, seu score, confiança, cobertura, fatores, evidências e limitações. A seleção pode orientar a timeline, o recorte ou o registro de validade. A simples consulta não altera o estado de revisão.

**Fluxo Básico.**

1. O usuário solicita as hipóteses associadas à investigação.
2. O Argus lista as hipóteses publicadas em ordem de relevância e apresenta um resumo do escopo e das fontes.
3. O usuário seleciona uma hipótese.
4. O sistema apresenta a explicação candidata, o estado da revisão e a execução que a produziu.
5. O Argus detalha score, confiança, cobertura e contribuição dos fatores.
6. O sistema separa evidências favoráveis, contrárias e indisponíveis, indicando origem e instante.
7. O usuário confronta a hipótese com o recorte e a comparação da investigação.
8. O usuário pode abrir a âncora na timeline, revisar o recorte afetado ou executar o UC13 - Registrar validade sobre uma hipótese.

**Fluxos alternativos.**

Alternativos:

- **A1 - Hipótese com confiança alta, média ou baixa:** a ordenação e a apresentação deixam claro o nível atribuído sem transformar confiança em certeza.
- **A2 - Evidência insuficiente:** o Argus apresenta a candidata como não avaliável e mostra quais informações faltaram.
- **A3 - Hipótese descartada:** quando disponibilizada para auditoria, a tela exibe a evidência contrária e o motivo do descarte separadamente das hipóteses geradas.
- **A4 - Revisão posterior:** o sistema apresenta a revisão mais recente elegível e mantém a referência à versão anterior substituída.
- **A5 - Nenhuma hipótese publicada:** a investigação continua por recorte, comparação e timeline.

Exceções:

- **E1 - Hipótese inexistente ou não publicada:** o Argus não expõe dados internos e informa que o item não está disponível.
- **E2 - Timeout, falha de rede ou servidor:** o sistema preserva o contexto e oferece nova tentativa.
- **E3 - Resposta inválida:** a tela recusa o conteúdo e não calcula score ou confiança a partir de campos inconsistentes.
- **E4 - Evidência temporalmente indisponível:** o dado não é mostrado como se existisse no instante da execução.

**Requisitos especiais.** A linguagem deve usar termos como “possível”, “provável” ou “as evidências sugerem”. A soma das contribuições deve corresponder ao score e os pesos devem formar o total esperado. Evidências precisam indicar fonte, instante e disponibilidade. Apenas execuções concluídas e manifestos publicados podem aparecer ao usuário.

**Lista de variantes.** Hipótese operacional, de contexto ou de qualidade de dados; confiança alta, média ou baixa; estado não revisado, confirmado, parcialmente confirmado ou rejeitado; revisão original ou posterior; evidência favorável, contrária ou indisponível.

**Frequência de ocorrência.** Sob demanda, normalmente para cada degradação que possua uma ou mais hipóteses publicadas.

**Problemas em aberto.** Validar a redação e a explicabilidade com os operadores; definir quando hipóteses descartadas devem ficar visíveis; verificar identidade individual do revisor; e medir utilidade e precisão com feedback real.

### UC11 - Reconstruir a timeline do incidente

**Escopo.** Área de timeline do Argus, responsável por ordenar sinais, mudanças e contexto de múltiplas fontes ao redor de uma degradação.

**Nível.** Extensão de objetivo do usuário.

**Atores.** Ator iniciador: Usuário Operacional, durante o UC06 - Investigar uma degradação.

**Interessados e interesses.** Engenharia de Observabilidade quer reconhecer precedência e coincidência temporal entre deploy, infraestrutura, backend, experiência, identidade e incidentes. Suporte N2 precisa de uma narrativa compreensível do que aconteceu. Auditoria deseja preservar a fonte de cada item.

**Pré-condições.** Existe uma investigação com janela ou âncora temporal; pelo menos uma fonte possui dados disponíveis; e o usuário está autorizado.

**Pós-condições.** O usuário visualiza uma cronologia ordenada, atribuída às fontes e limitada à disponibilidade temporal da investigação. O contexto pode ser usado para avaliar hipóteses ou ajustar o recorte, sem alterar os eventos originais.

**Fluxo Básico.**

1. O usuário abre a timeline a partir da investigação.
2. O Argus recupera a âncora, a janela e o escopo ativos.
3. O sistema consulta sinais e eventos disponíveis nas fontes relacionadas.
4. O Argus normaliza os instantes para uma escala comum, preservando o horário e a granularidade originais.
5. O sistema ordena os itens e os distribui por fonte ou domínio operacional.
6. A plataforma apresenta a timeline visual e uma cronologia textual equivalente.
7. O usuário seleciona um item para ler valor, descrição, origem e relação com a degradação.
8. O usuário ajusta a janela, retorna à hipótese ou continua a investigação pelo recorte.

**Fluxos alternativos.**

Alternativos:

- **A1 - Abertura por hipótese:** a timeline é centralizada no instante de referência da hipótese.
- **A2 - Abertura por sinal:** a cronologia destaca a série e a entidade que apresentaram desvio.
- **A3 - Fonte sem eventos na janela:** a raia permanece identificada como vazia ou indisponível, sem ser confundida com comportamento normal.
- **A4 - Granularidades diferentes:** o sistema associa os dados ao intervalo compatível e conserva a precisão declarada da fonte.
- **A5 - Janela ampliada:** o usuário expande o período para procurar causas anteriores ou efeitos posteriores.

Exceções:

- **E1 - Âncora ou intervalo inválido:** o Argus solicita uma janela válida e preserva o contexto anterior.
- **E2 - Falha parcial de fonte:** os demais itens são apresentados com aviso de cobertura incompleta.
- **E3 - Nenhuma fonte disponível:** o sistema informa que a timeline não pode ser reconstruída e não exibe uma cronologia vazia como evidência.
- **E4 - Falha de consulta:** a tela mostra referência rastreável e permite nova tentativa.

**Requisitos especiais.** Os itens devem ser ordenados de forma determinística, exibir fonte e horário, respeitar `available_at` e não misturar relógio real de infraestrutura com relógio simulado sem identificação. A representação visual deve possuir alternativa textual acessível e funcionar em telas estreitas.

**Lista de variantes.** Timeline iniciada por sinal ou hipótese; janela curta ou ampliada; fontes de experiência, Prometheus, New Relic, Apollo, Tsuru, identidade, atendimento ou eventos ao vivo; visão por raias ou cronologia textual.

**Frequência de ocorrência.** Sob demanda, principalmente quando a sequência dos fatos pode diferenciar causas concorrentes.

**Problemas em aberto.** Consolidar o conjunto definitivo de raias; melhorar o relacionamento entre entidades de fontes diferentes sem correspondência explícita; e definir o nível de detalhe adequado para janelas longas.

### UC12 - Consultar a trajetória de uma sessão

**Escopo.** Consulta de eventos do Argus, para reconstruir a sequência individual de uma sessão ou, como variação, o histórico de um dispositivo.

**Nível.** Extensão de subfunção de investigação.

**Atores.** Ator iniciador: Usuário Operacional, a partir do UC07 - Identificar e ajustar o recorte afetado.

**Interessados e interesses.** Suporte N2 deseja compreender o que ocorreu antes e depois de um erro relatado. Engenharia de Observabilidade quer validar se o padrão agregado aparece numa trajetória real. Privacidade exige exposição apenas dos atributos necessários à investigação.

**Pré-condições.** O usuário está autorizado; o recorte possui uma sessão ou dispositivo representativo; e o identificador selecionado está disponível na consulta.

**Pós-condições.** O usuário visualiza os eventos ordenados e os atributos permitidos da sessão ou do dispositivo. A trajetória permanece ligada ao recorte que a originou. Nenhum dado é alterado.

**Fluxo Básico.**

1. O usuário seleciona uma sessão representativa no recorte.
2. O Argus valida o identificador e consulta os eventos da sessão.
3. O sistema ordena os eventos pelo instante de ocorrência e apresenta o resumo do dispositivo e do aplicativo.
4. O Argus destaca eventos relevantes, como início, navegação, reprodução, requisições e erros.
5. O usuário seleciona um evento para consultar seus detalhes permitidos.
6. O sistema apresenta tipo, instante, código de erro, duração, rota e contexto técnico disponível.
7. O usuário relaciona a trajetória ao comportamento agregado e retorna ao recorte ou à investigação.

**Fluxos alternativos.**

Alternativos:

- **A1 - Histórico do dispositivo:** o usuário amplia a análise para outras sessões do mesmo dispositivo dentro de uma janela autorizada.
- **A2 - Sessão longa:** o Argus pagina os eventos e fornece continuação estável.
- **A3 - Evento sem atributos opcionais:** a trajetória é exibida com os campos disponíveis, sem preencher valores ausentes por inferência.
- **A4 - Relógio do dispositivo divergente:** o Argus sinaliza possível `clock_skew` e preserva os instantes recebidos e de ingestão para análise.

Exceções:

- **E1 - Sessão ou dispositivo inexistente:** a API devolve não encontrado e a interface mantém o recorte anterior.
- **E2 - Evento não pertence à sessão:** o detalhe não é retornado.
- **E3 - Limite ou cursor inválido:** a consulta é recusada com orientação para corrigir o parâmetro.
- **E4 - Atributo sensível:** o campo é omitido ou redigido antes da apresentação.

**Requisitos especiais.** Os eventos devem manter ordem determinística e paginação sem duplicidade. Campos identificadores devem ser usados apenas quando necessários. O dashboard não deve expor dados pessoais desnecessários. Estados de carregamento, vazio, não encontrado e erro precisam ser distintos e acessíveis.

**Lista de variantes.** Consulta por sessão ou dispositivo; sessão completa ou paginada; detalhe de evento; plataformas modernas ou legadas; trajetória com ou sem erro; presença ou ausência de divergência de relógio.

**Frequência de ocorrência.** Sob demanda durante triagens e investigações de recortes específicos; pode ser repetida para várias sessões representativas.

**Problemas em aberto.** Definir quais identificadores e atributos podem ser expostos a cada perfil; estabelecer retenção e anonimização; e decidir quantas sessões devem compor uma amostra representativa do recorte.

### UC13 - Registrar validade sobre uma hipótese

**Escopo.** API de feedback e histórico de revisões do Argus, para registrar a avaliação humana de uma hipótese publicada.

**Nível.** Extensão de objetivo do usuário.

**Atores.** Ator iniciador: Usuário Operacional, após analisar uma hipótese no UC10.

**Interessados e interesses.** O operador deseja registrar se as evidências confirmam, confirmam parcialmente ou rejeitam a hipótese. A equipe de dados precisa de feedback auditável para avaliação e calibração. Auditoria exige histórico imutável e proteção contra duplicidade. O parceiro precisa distinguir avaliação humana de conclusão automática.

**Pré-condições.** A hipótese existe, está publicada e foi apresentada ao usuário; o usuário possui autorização para enviar feedback; e a solicitação possui uma chave de idempotência válida.

**Pós-condições.** Um feedback válido é persistido de forma auditável e passa a compor o estado de revisão da hipótese. Reenvios idênticos não duplicam o registro. A avaliação automática original e as revisões anteriores permanecem inalteradas.

**Fluxo Básico.**

1. O usuário conclui a análise das evidências de uma hipótese.
2. O usuário escolhe um veredito: concorda, concorda parcialmente ou discorda.
3. Opcionalmente, o usuário informa uma observação dentro do limite aceito.
4. O dashboard envia a hipótese, o veredito e uma chave única de idempotência.
5. O Argus valida autorização, publicação da hipótese, tamanho e conteúdo do pedido.
6. O sistema registra o feedback em estrutura append-only.
7. O Argus recalcula o estado de revisão derivado da hipótese.
8. O sistema confirma o registro e apresenta o novo estado ao usuário.

**Fluxos alternativos.**

Alternativos:

- **A1 - Confirmação:** o estado de revisão passa a confirmado.
- **A2 - Confirmação parcial:** o estado registra que apenas parte da causa ou do escopo foi validada.
- **A3 - Rejeição:** o estado de revisão passa a rejeitado, sem apagar a hipótese original.
- **A4 - Reenvio idêntico:** a mesma chave e o mesmo conteúdo retornam o resultado já criado, sem novo registro lógico.
- **A5 - Nova revisão da hipótese:** o feedback permanece associado à versão analisada; uma hipótese posterior referencia a anterior sem reescrever seu histórico.

Exceções:

- **E1 - Veredito ou payload inválido:** o Argus rejeita a solicitação e explica os campos inválidos.
- **E2 - Hipótese inexistente ou não publicada:** nenhum feedback é criado.
- **E3 - Conflito de idempotência:** a mesma chave usada com conteúdo diferente é recusada.
- **E4 - Acesso sem permissão:** a solicitação é negada e não altera o estado da hipótese.
- **E5 - Falha de persistência:** a operação é revertida e pode ser repetida com a mesma chave.

**Requisitos especiais.** O feedback deve ser idempotente, append-only e vinculado à execução e à revisão avaliadas. O corpo da requisição deve ter no máximo 4 KiB. A rota possui limite inicial de 5 requisições por segundo e rajada de 10. Enquanto não existir identidade individual verificada, o campo de verificação do revisor permanece falso e não pode ser apresentado como autoria comprovada.

**Lista de variantes.** Veredito de concordância, concordância parcial ou discordância; feedback com ou sem observação; primeira submissão ou reenvio idempotente; hipótese original ou revisão posterior.

**Frequência de ocorrência.** Eventual, depois de uma análise humana concluída; idealmente ao menos uma vez para cada hipótese efetivamente investigada.

**Problemas em aberto.** Implementar identidade individual e trilha de autoria verificável; definir governança para divergência entre revisores; decidir se o feedback poderá ser complementado sem alterar o registro anterior; e integrar os rótulos ao processo de avaliação do motor.
