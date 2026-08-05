# Entendimento do Negócio

## 1. Matriz de Avaliação de Valor (Oceano Azul)

---

## 2. Matriz de Risco

---

## 3. Canvas da Proposta de Valor

### 3.1. Introdução

O Canvas Proposta de Valor tem como objetivo demonstrar como a plataforma proposta atende às necessidades dos usuários internos responsáveis pela operação, monitoramento e resolução de incidentes do Globoplay.

A solução busca reduzir o tempo necessário para identificar a causa provável de falhas por meio da centralização, normalização e correlação automática de dados de observabilidade provenientes de diferentes sistemas. Dessa forma, contribui para aumentar a eficiência operacional, melhorar o cumprimento dos acordos de nível de serviço (SLA) e proporcionar uma experiência mais consistente aos usuários finais da plataforma de streaming.

> **Figura X – Canvas de Proposta de Valor**
> Inserir a imagem do Canvas de Proposta de Valor.

### 3.2. Perfil do Cliente

O cliente analisado neste projeto corresponde ao time de tecnologia da Globo, especialmente às equipes responsáveis pela observabilidade, engenharia de software e DevOps. Esses profissionais utilizam ferramentas de monitoramento para investigar incidentes, identificar causas raiz e restaurar rapidamente o funcionamento da plataforma.

Embora o usuário direto seja composto pelas equipes técnicas, a solução também beneficia indiretamente os assinantes do Globoplay, que passam a experimentar menor tempo de indisponibilidade e melhor qualidade na reprodução de conteúdo.

#### Tarefas do Cliente (*Customer Jobs*)

- Monitorar continuamente a saúde dos sistemas do Globoplay;
- Detectar rapidamente incidentes e degradações na experiência do usuário;
- Correlacionar informações provenientes de diferentes ferramentas de observabilidade;
- Identificar a causa provável dos problemas com o menor tempo possível;
- Priorizar incidentes conforme o impacto nos usuários;
- Direcionar corretamente os chamados para a equipe responsável;
- Reduzir o tempo de resolução e cumprir os SLAs estabelecidos.

#### Dores (*Pains*)

- Dados distribuídos entre diversas ferramentas de monitoramento, dificultando a análise integrada;
- Necessidade de especialistas de diferentes áreas para interpretar informações fragmentadas;
- Alto tempo gasto na identificação da causa raiz dos incidentes;
- Chamados encaminhados para equipes incorretas antes da identificação do problema;
- Baixa visibilidade sobre problemas localizados que afetam apenas determinados dispositivos, regiões ou versões do aplicativo;
- Grande diversidade de plataformas, sistemas operacionais e dispositivos suportados pelo Globoplay;
- Dificuldade em correlacionar automaticamente métricas técnicas provenientes de diferentes componentes;
- Elevado custo operacional causado pela demora na investigação de incidentes.

#### Ganhos (*Gains*)

- Identificação mais rápida da causa provável dos incidentes;
- Redução significativa do tempo de diagnóstico;
- Centralização das informações em uma única plataforma;
- Correlação automática entre diferentes fontes de observabilidade;
- Visualização clara dos dispositivos, versões e regiões afetadas;
- Maior eficiência operacional das equipes técnicas;
- Priorização adequada dos incidentes mais críticos;
- Cumprimento dos SLAs de atendimento;
- Redução do impacto das falhas na experiência dos assinantes;
- Maior confiabilidade no processo de monitoramento.

#### Conclusão do Perfil do Cliente

O perfil analisado evidencia que as principais necessidades das equipes técnicas estão relacionadas à redução do tempo de diagnóstico, à integração de dados hoje fragmentados e à identificação precisa do impacto de cada incidente. Entre os pontos mais relevantes, destacam-se a dificuldade de correlacionar informações de diferentes ferramentas, o encaminhamento inadequado de chamados e a necessidade de cumprir os SLAs sem aumentar o esforço operacional. Essas necessidades orientam o desenvolvimento de uma solução centralizada capaz de normalizar dados de observabilidade, correlacionar eventos e apoiar a identificação da causa provável das falhas.

### 3.3. Mapa de Valor

#### Produtos e Serviços

- Plataforma distribuída para coleta de eventos de telemetria;
- API unificada de ingestão de dados;
- Suporte a protocolos modernos e dispositivos legados;
- Pipeline escalável para processamento de eventos;
- Camada de normalização de diferentes padrões de telemetria;
- Sistema de correlação automática entre métricas;
- Mecanismo de identificação da causa provável dos incidentes utilizando IA;
- Visualização dos grupos de usuários e dispositivos afetados;
- Geração de alertas para apoio à tomada de decisão.

#### Aliviadores de Dores (*Pain Relievers*)

- **Dados espalhados em várias ferramentas:** a solução centraliza as informações em uma única plataforma;
- **Dificuldade de correlação entre métricas:** os dados são normalizados e correlacionados automaticamente entre diferentes sistemas;
- **Alto tempo de investigação:** a solução sugere a causa provável do incidente e reduz a necessidade de investigação manual;
- **Dependência de especialistas:** o conhecimento é consolidado em uma interface única, diminuindo a necessidade de consultar diversas equipes;
- **Problemas localizados que passam despercebidos:** a solução identifica padrões por dispositivo, região, sistema operacional e versão do aplicativo;
- **Chamados encaminhados incorretamente:** as evidências coletadas ajudam a direcionar a investigação para a equipe com maior probabilidade de resolver o problema;
- **Diversidade tecnológica do Globoplay:** diferentes protocolos e dispositivos são atendidos por uma arquitetura única.

#### Criadores de Ganhos (*Gain Creators*)

- **Diagnóstico mais rápido:** a solução ranqueia automaticamente hipóteses de causa provável;
- **Melhor tomada de decisão:** o dashboard apresenta informações consolidadas e contextualizadas;
- **Maior produtividade das equipes:** diminui o tempo gasto na busca por informações em múltiplas ferramentas;
- **Cumprimento dos SLAs:** reduz o intervalo entre a detecção e a resolução do incidente;
- **Melhor experiência dos assinantes:** permite que os problemas sejam identificados e solucionados mais rapidamente;
- **Redução de custos operacionais:** exige menor esforço manual durante a investigação e reduz a dependência de ferramentas externas;
- **Aprendizado contínuo:** utiliza o histórico de incidentes para aprimorar os modelos de IA e aumentar a precisão dos diagnósticos.

A relação entre o perfil do cliente e o mapa de valor demonstra que a solução proposta responde diretamente aos principais desafios operacionais do Globoplay. A centralização e a normalização dos dados tratam a fragmentação das ferramentas; a correlação automática e o apoio de IA reduzem o tempo de diagnóstico; e a visualização contextualizada do impacto ajuda a priorizar e direcionar os incidentes. Dessa forma, o desenvolvimento deve concentrar-se nesses recursos essenciais para aumentar a eficiência das equipes técnicas, favorecer o cumprimento dos SLAs e reduzir os efeitos das falhas percebidos pelos usuários finais.



## 4. Análise Financeira do Projeto

---

## 5. Análise de impacto do projeto na perspectivas dos ODS

---

## Referências
