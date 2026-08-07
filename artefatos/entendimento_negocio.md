# Entendimento do Negócio

## 1. Matriz de Avaliação de Valor (Oceano Azul)

---

## 2. Matriz de Risco

---

## 3. Canvas da Proposta de Valor

### 3.1. Value Proposition Canvas

&nbsp; O Canvas da Proposta de Valor é uma ferramenta estratégica que permite compreender de forma visual e objetiva a relação entre o que uma organização oferece e as necessidades de seu público-alvo. Ele é dividido em dois lados complementares: o Perfil do Cliente, que identifica as tarefas, dores e ganhos esperados, e o Mapa de Valor, que apresenta como os produtos e serviços propostos aliviam essas dores e criam benefícios. Neste projeto, a ferramenta é utilizada para relacionar uma solução própria de coleta e análise de telemetria aos desafios enfrentados pelo time de tecnologia da Globo durante o monitoramento e a resolução de incidentes do Globoplay.

<div align="center">

<sub>Figura 3 - Value Proposition Canvas</sub>

  <img src="../assets/value-proposition-canvas.png">

<sup>Fonte: Material produzido pelos autores (2026)</sup>

</div>

##### PROPOSTA DE VALOR

###### Produtos & Serviços

&nbsp; Esta seção detalha os produtos e serviços que compõem a proposta de valor entregue ao cliente.

- **1 -** SDKs e agentes próprios para coleta de telemetria em dispositivos de TV, mobile e web.
- **2 -** API para receber diretamente os eventos enviados pelos dispositivos.
- **3 -** Pipeline escalável, executado na AWS, para processamento dos eventos coletados.
- **4 -** Camada de normalização dos eventos coletados diretamente dos dispositivos, convertendo protocolos modernos e legados para um formato unificado.
- **5 -** Armazenamento centralizado das informações processadas.
- **6 -** Dashboard para visualização de incidentes, impactos e alertas operacionais.
- **7 -** Mecanismo para identificação de incidentes e degradações a partir dos eventos coletados.

###### Criadores de Ganhos (*Gain Creators*)

&nbsp; Esta seção detalha os elementos da solução que atuam como criadores de ganhos para o cliente, fortalecendo a proposta de valor.

- **1 -** A consolidação das informações no dashboard reduz o tempo de análise e diagnóstico.
- **2 -** A integração dos dados de TV, mobile e web proporciona uma visão mais ampla da experiência dos assinantes.
- **3 -** A classificação pelo alcance e impacto facilita a priorização dos incidentes mais críticos.
- **4 -** A coleta própria elimina parte das limitações impostas pelas ferramentas de mercado e amplia o controle da Globo sobre a evolução da plataforma.
- **5 -** A disponibilidade de telemetria em nível de dispositivo facilita a identificação da causa provável dos incidentes.
- **6 -** O direcionamento mais preciso dos chamados reduz retrabalho e aumenta a produtividade.
- **7 -** A detecção e a investigação mais rápidas apoiam o cumprimento dos acordos de nível de serviço (SLA).
- **8 -** A redução do tempo de resposta contribui para diminuir a duração e o impacto das falhas percebidas pelos assinantes.

###### Aliviadores de Dores (*Pain Relievers*)

&nbsp; Esta seção apresenta os elementos da solução que atuam como aliviadores das dores identificadas no perfil do cliente.

- **1 -** A coleta própria permite monitorar dispositivos que não são plenamente suportados pelas soluções de mercado, reduzindo a dependência dessas ferramentas no escopo coberto pelo projeto.
- **2 -** A normalização converte eventos de diferentes plataformas para um formato comum, reduzindo a fragmentação.
- **3 -** O armazenamento e o dashboard centralizam informações anteriormente distribuídas.
- **4 -** A análise contínua da telemetria permite identificar degradações mesmo quando não há erros explícitos registrados.
- **5 -** A correlação entre eventos, dispositivos, plataformas e sessões reduz o tempo necessário para encontrar a causa provável do incidente.
- **6 -** A visualização do alcance e do impacto ajuda a evitar a priorização inadequada dos incidentes.
- **7 -** As informações consolidadas apoiam o encaminhamento do chamado para a equipe responsável.
- **8 -** O processamento escalável permite lidar com o volume de eventos sem comprometer a análise operacional.

---

##### PERFIL DO CLIENTE (Público-Alvo Ideal)

&nbsp; O cliente analisado neste projeto corresponde ao time de tecnologia da Globo responsável pelo monitoramento e pela resolução de incidentes do Globoplay. Embora as equipes técnicas sejam as usuárias diretas da solução, os assinantes são beneficiados indiretamente pela redução do impacto e da duração das falhas.

###### Tarefas do Cliente (*Customer Jobs*)

&nbsp; Esta seção descreve as principais responsabilidades, objetivos e desafios enfrentados pelo cliente, que orientam o desenvolvimento da solução.

- **1 -** Monitorar continuamente a experiência do Globoplay em TV, mobile e web. 
- **2 -** Detectar incidentes e degradações, inclusive quando não há erros explícitos. 
- **3 -** Correlacionar eventos e métricas técnicas provenientes de diferentes dispositivos e plataformas. 
- **4 -** Identificar evidências que apoiem a investigação da causa provável dos incidentes. 
- **5 -** Mensurar o alcance e o impacto dos incidentes sobre os assinantes. 
- **6 -** Priorizar incidentes conforme sua criticidade e impacto. 
- **7 -** Encaminhar os chamados para a equipe responsável e acompanhar sua resolução. 
- **8 -** Cumprir os SLAs e demonstrar eficiência operacional para outras áreas da Globo. 
- **9 -** Tomar decisões com segurança, mesmo sob pressão durante incidentes críticos.

###### Ganhos Desejados (*Gains*)

&nbsp; Esta seção apresenta os ganhos esperados pelo cliente com a adoção da solução.

- **1 -** Reduzir o tempo necessário para detectar, analisar e diagnosticar incidentes.
- **2 -** Obter visibilidade sobre dispositivos anteriormente pouco observáveis.
- **3 -** Identificar mais rapidamente evidências relacionadas à causa provável dos incidentes.
- **4 -** Conhecer o alcance e o impacto de cada incidente sobre os assinantes.
- **5 -** Priorizar adequadamente os incidentes mais críticos.
- **6 -** Reduzir o tempo gasto na identificação da equipe responsável pelo incidente, acelerando todo o fluxo de resolução.
- **7 -** Aumentar a autonomia e o controle da Globo sobre seus dados de telemetria.
- **8 -** Reduzir a dependência tecnológica de soluções externas para observabilidade.
- **9 -** Reduzir retrabalho e aumentar a produtividade das equipes técnicas.
- **10 -** Apoiar o cumprimento dos SLAs e aumentar a confiança durante a tomada de decisão.
- **11 -** Diminuir a duração e o impacto percebido das falhas pelos assinantes.

###### Dores (*Pains*)

&nbsp; Esta seção descreve os principais desafios e obstáculos enfrentados pelo cliente.

- **1 -** Dependência de ferramentas de mercado para coletar e disponibilizar dados de observabilidade.
- **2 -** Dados de telemetria fragmentados e apresentados em formatos diferentes entre TV, mobile e web.
- **3 -** Perda de contexto durante o encaminhamento do incidente entre diferentes equipes e filas.
- **4 -** Degradações de desempenho nem sempre geram erros explícitos, dificultando sua detecção pelas ferramentas tradicionais.
- **5 -** Dificuldade para correlacionar informações e encontrar evidências sobre a causa provável dos incidentes.
- **6 -** Priorização inadequada quando o impacto real do incidente não está claro.
- **7 -** O tempo de resolução é elevado porque parte significativa do esforço é gasta identificando qual equipe é responsável pelo problema.
- **8 -** Encaminhamento de chamados para equipes incorretas, causando retrabalho e atraso na resolução.
- **9 -** Pressão e insegurança na tomada de decisão durante incidentes críticos.
- **10 -** Prolongamento das falhas, com risco de descumprimento dos SLAs e prejuízo à experiência dos assinantes.

&nbsp; Dessa forma, o modelo demonstra que a solução proposta é baseada em coleta própria. Por meio de SDKs e agentes próprios, os eventos são coletados diretamente nos dispositivos de TV, mobile e web e enviados à infraestrutura da plataforma na AWS, onde são processados, normalizados, armazenados e apresentados em um dashboard. A solução foi concebida para substituir, dentro do escopo do MVP e conforme o rollout dos SDKs e agentes próprios, parte das funcionalidades atualmente desempenhadas por ferramentas de observabilidade de mercado. O valor central da proposta permanece a ampliação da visibilidade necessária para investigar incidentes, reduzir o tempo perdido entre filas e equipes, apoiar o cumprimento dos SLAs e diminuir o impacto das falhas percebidas pelos assinantes do Globoplay.



## 4. Análise Financeira do Projeto

---

## 5. Análise de impacto do projeto na perspectivas dos ODS

---

## Referências
