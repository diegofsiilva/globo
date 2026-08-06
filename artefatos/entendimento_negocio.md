# Entendimento do Negócio

## 1. Matriz de Avaliação de Valor (Oceano Azul)

---

## 2. Matriz de Risco

---

## 3. Canvas da Proposta de Valor

### 3.1. Introdução

O Canvas da Proposta de Valor é uma ferramenta utilizada para compreender as necessidades do cliente e relacioná-las ao valor oferecido por uma solução. Ele é dividido entre o perfil do cliente, que reúne suas tarefas, dores e ganhos esperados, e o mapa de valor, que apresenta os produtos e serviços, os aliviadores de dores e os criadores de ganhos. Neste projeto, o Canvas permite visualizar como a solução proposta se conecta aos desafios enfrentados pelas equipes responsáveis pela operação, pelo monitoramento e pela resolução de incidentes do Globoplay.

> **Figura X – Canvas de Proposta de Valor**

![Canvas da Proposta de Valor](../assets/Value%20proposition%20canvas.png)

### 3.2. Perfil do Cliente

O cliente analisado neste projeto corresponde ao time de tecnologia da Globo, especialmente às equipes responsáveis pela observabilidade, engenharia de software e DevOps.

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
- Alto tempo gasto na investigação das possíveis causas dos incidentes;
- Chamados encaminhados para equipes incorretas antes da identificação do problema;
- Baixa visibilidade sobre problemas localizados que afetam apenas determinados dispositivos, regiões ou versões do aplicativo;
- Grande diversidade de plataformas, sistemas operacionais e dispositivos suportados pelo Globoplay;
- Dificuldade em analisar conjuntamente métricas técnicas provenientes de diferentes componentes;
- Elevado custo operacional causado pela demora na investigação de incidentes.

#### Ganhos (*Gains*)

- Identificação mais rápida da causa provável dos incidentes;
- Redução significativa do tempo de diagnóstico;
- Centralização das informações em uma única plataforma;
- Análise integrada de diferentes fontes de observabilidade;
- Visualização clara dos dispositivos, versões e regiões afetadas;
- Maior eficiência operacional das equipes técnicas;
- Priorização adequada dos incidentes mais críticos;
- Cumprimento dos SLAs de atendimento;
- Redução do impacto das falhas na experiência dos assinantes;
- Maior confiabilidade no processo de monitoramento.

### 3.3. Mapa de Valor

O mapa de valor descreve como a solução proposta atende às necessidades do cliente. Os produtos e serviços representam as entregas concretas do projeto, os aliviadores de dores indicam como essas entregas reduzem dificuldades existentes e os criadores de ganhos apresentam os benefícios proporcionados às equipes e aos assinantes.

#### Produtos e Serviços

- Plataforma integrada de observabilidade;
- API para ingestão de dados de telemetria;
- Pipeline escalável para processamento de eventos;
- Camada de padronização de diferentes formatos de telemetria;
- Dashboard para visualização de incidentes e seus impactos;
- Alertas para apoio à tomada de decisão.

#### Aliviadores de Dores (*Pain Relievers*)

- **Dados espalhados em várias ferramentas:** centraliza as informações necessárias à investigação em uma única plataforma;
- **Formatos diferentes de telemetria:** padroniza os dados antes de apresentá-los às equipes técnicas;
- **Alto tempo de investigação:** reúne métricas, eventos e informações de impacto para facilitar a análise dos incidentes;
- **Baixa visibilidade de problemas localizados:** permite consultar os grupos de usuários, dispositivos, versões e regiões afetados;
- **Chamados encaminhados incorretamente:** apresenta evidências que apoiam o direcionamento do chamado para a equipe responsável;
- **Dificuldade de crescimento da infraestrutura:** utiliza a capacidade escalável da AWS para processar o volume de eventos.

#### Criadores de Ganhos (*Gain Creators*)

- **Análise mais ágil:** o dashboard torna as informações relevantes acessíveis em uma única visualização;
- **Priorização por impacto:** a contextualização dos dados ajuda as equipes a identificar os incidentes mais críticos;
- **Maior produtividade:** a centralização reduz o tempo gasto na busca por informações em diferentes fontes;
- **Melhor tomada de decisão:** os alertas e as informações consolidadas oferecem suporte à atuação das equipes;
- **Cumprimento dos SLAs:** a investigação mais eficiente contribui para reduzir o intervalo entre a detecção e a resolução;
- **Menor impacto para os assinantes:** a atuação mais rápida das equipes reduz a duração das falhas percebidas pelos usuários.

A relação entre o perfil do cliente e o mapa de valor demonstra que a solução proposta responde diretamente aos principais desafios operacionais do Globoplay. Entre os pontos mais relevantes estão a fragmentação dos dados, o tempo elevado de investigação e a dificuldade de priorizar e direcionar incidentes. Para enfrentá-los, a plataforma desenvolvida na AWS concentrará a ingestão e o processamento da telemetria, a padronização dos dados e sua apresentação em um dashboard contextualizado. A solução não realizará diagnósticos por IA; ela organizará as evidências necessárias para apoiar o trabalho das equipes técnicas, favorecer o cumprimento dos SLAs e reduzir os efeitos das falhas percebidos pelos assinantes.



## 4. Análise Financeira do Projeto

---

## 5. Análise de impacto do projeto na perspectivas dos ODS

---

## Referências
