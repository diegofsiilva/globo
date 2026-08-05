# Entendimento do Negócio

## 1. Matriz de Avaliação de Valor (Oceano Azul)

---

## 2. Matriz de Risco

<img src="/artefatos/assets/riscos.png">


| Descrição (Risco)                           | Classificação na matriz                                    | Explicação                                                                                                                                                                                                                       | Plano de Ação                                                                                                                                                          |
| ------------------------------------------- | ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **R01: Conhecimento concentrado**           | **Risco alto** — Probabilidade: 70%; Impacto: muito alto   | Ocorre quando somente um integrante domina componentes críticos, como a API de ingestão, o banco de dados, a infraestrutura ou o dashboard. A ausência dessa pessoa pode bloquear a equipe e dificultar a manutenção da solução. | Realizar atualizações diárias nos rituais Scrum, revisões cruzadas de código, rodízio entre componentes e documentação técnica contínua.                               |
| **R02: Distribuição e atrasos**             | **Risco alto** - Probabilidade: 90%; Impacto: moderado     | Alguns integrantes podem concentrar atividades críticas, enquanto outros permanecem com demandas menores. Essa distribuição desigual pode provocar sobrecarga, erros, desmotivação e atrasos.                                    | Dividir as entregas em tarefas menores e revisar semanalmente a carga de cada integrante, permitindo redistribuições quando necessário.                                |
| **R03: Privacidade e confidencialidade**    | **Risco alto** - Probabilidade: 30%; Impacto: muito alto   | Os eventos coletados podem conter identificadores ou informações sensíveis. Além da LGPD, o TAPI estabelece que os dados e desafios do projeto não sejam compartilhados com terceiros.                                           | Mapear os dados coletados e aplicar minimização, anonimização, controle de acesso, criptografia e políticas de retenção.                                               |
| **R04: Performance em escala**              | **Risco alto** - Probabilidade: 90%; Impacto: alto         | A API, o processamento ou o armazenamento podem não suportar o volume de eventos gerado pelo Globoplay, causando lentidão, acúmulo de mensagens e indisponibilidade.                                                             | Definir metas de eventos por segundo, latência e disponibilidade, além de executar testes progressivos de carga, pico e resistência.                                   |
| **R05: Dependências mal planejadas**        | **Risco moderado** - Probabilidade: 50%; Impacto: moderado | Uma atividade pode depender de uma API, schema, componente ou ambiente que ainda não está disponível, deixando integrantes bloqueados e comprometendo o cronograma.                                                              | Mapear as dependências no planejamento das sprints, priorizando contratos, interfaces, schemas e mocks antes dos componentes consumidores.                             |
| **R06: Dados não representativos**          | **Risco moderado** - Probabilidade: 70%; Impacto: baixo    | Os dados sintéticos podem não representar adequadamente a diversidade de dispositivos, conexões, erros e picos de utilização do Globoplay.                                                                                       | Solicitar amostras anonimizadas e estatísticas agregadas e desenvolver um gerador capaz de simular diferentes dispositivos, condições de rede e padrões de utilização. |
| **R07: Consultas lentas**                   | **Risco baixo** - Probabilidade: 30%; Impacto: baixo       | O alto volume de dados, os filtros cumulativos e a elevada cardinalidade podem tornar as consultas e os dashboards demorados ou caros.                                                                                           | Utilizar índices, particionamentos, agregações, paginação e limites para períodos e cardinalidade, avaliando diferentes combinações de filtros em testes.              |
| **R08: Incompatibilidade com dispositivos** | **Risco alto** - Probabilidade: 70%; Impacto: alto         | Dispositivos antigos podem não suportar os protocolos, formatos de eventos ou mecanismos de segurança adotados pela solução.                                                                                                     | Criar uma matriz de compatibilidade, acompanhada de contratos mínimos, adaptadores e testes para os dispositivos prioritários.                                         |
| **R09: Inconsistência de eventos**          | **Risco alto** - Probabilidade: 50%; Impacto: muito alto   | Falhas de conexão e tentativas automáticas de reenvio podem provocar perda, duplicação ou desordenação de eventos, gerando métricas incorretas.                                                                                  | Utilizar identificadores únicos, operações idempotentes, timestamps, filas persistentes, políticas de retry e mecanismos de dead-letter queue.                         |
| **R10: Schemas incompatíveis**              | **Risco baixo** - Probabilidade: 50%; Impacto: baixo       | Diferentes versões de eventos podem ser enviadas pelas aplicações e dispositivos. Alterações não controladas podem interromper a ingestão ou gerar dados incompletos.                                                            | Adotar versionamento de schemas, compatibilidade retroativa, validação de eventos na entrada e testes automatizados de contrato.                                       |
| **R11: Indisponibilidade do pipeline**      | **Risco alto** - Probabilidade: 10%; Impacto: muito alto   | Uma falha na API, na fila, no processador ou no banco de dados pode interromper o fluxo de telemetria.                                                                                                                           | Desacoplar os componentes por meio de filas e implementar health checks, timeouts, circuit breakers, armazenamento temporário e mecanismos de recuperação.             |
| **R12: Alertas não confiáveis**             | **Risco baixo** - Probabilidade: 50%; Impacto: muito baixo | Limites inadequados podem gerar falsos positivos ou deixar de identificar falhas relevantes. O excesso de notificações também pode causar fadiga de alertas.                                                                     | Definir níveis de severidade, janelas temporais e regras de agrupamento, revisando periodicamente os falsos positivos e negativos.                                     |
| **R13: Custos de infraestrutura**           | **Risco moderado** - Probabilidade: 30%; Impacto: moderado | A coleta, o processamento e o armazenamento de eventos em alta escala podem gerar despesas superiores ao previsto.                                                                                                               | Definir políticas de retenção, agregação, amostragem e compressão e monitorar os custos de processamento, armazenamento e transferência.                               |
| **R14: Critérios de aceite**                | **Risco moderado** - Probabilidade: 70%; Impacto: moderado | Expressões como “alta escala”, “sem perdas” e “falhas críticas” podem não possuir valores mensuráveis, dificultando a validação do MVP.                                                                                          | Converter os requisitos em indicadores objetivos, como taxa de eventos por segundo, latência máxima, disponibilidade, retenção e taxa aceitável de perda.              |
| **R15: Escopo do MVP**                      | **Risco alto** - Probabilidade: 90%; Impacto: muito alto   | A quantidade e a complexidade das entregas previstas, como API única, protocolos legados, pipeline escalável, normalização, consultas e dashboard, podem superar o tempo disponível.                                             | Classificar os requisitos como essenciais, desejáveis ou futuros, priorizando inicialmente um fluxo completo de ponta a ponta.                                         |
| **R16: Falta de observabilidade**           | **Risco baixo** - Probabilidade: 30%; Impacto: muito baixo | A ausência de métricas internas pode dificultar a diferenciação entre uma falha do Globoplay e um problema na própria plataforma de monitoração.                                                                                 | Instrumentar a solução com métricas, logs e rastreamento, acompanhando latência, erros, backlog, throughput, descarte de eventos e disponibilidade.                    |



---

## 3. Canvas da Proposta de Valor



## 4. Análise Financeira do Projeto

---

## 5. Análise de impacto do projeto na perspectivas dos ODS

---

## Referências

