## 1. Contexto e escopo do projeto

&emsp; O projeto consiste no desenvolvimento de uma plataforma distribuída de backend para coleta, normalização, processamento e consulta de eventos de telemetria provenientes das aplicações frontend do Globoplay. A solução busca atender a diferentes tipos de dispositivos, sistemas operacionais, versões de aplicativos e condições de conectividade, incluindo equipamentos legados que não oferecem suporte completo aos padrões modernos de observabilidade.

&emsp; Atualmente, os componentes relacionados ao login, ao player de vídeo e à distribuição de conteúdo por CDN (Content Delivery Network, rede de distribuição de conteúdo) possuem padrões de monitoração distintos. Essa fragmentação dificulta a comparação das informações, exige correlação manual entre diferentes fontes e reduz a visibilidade sobre falhas que afetam plataformas ou dispositivos específicos.

&emsp; A solução proposta deverá oferecer uma API unificada de ingestão, suporte a formatos modernos e legados, normalização dos eventos recebidos e disponibilização de consultas e visualizações operacionais. Entre os eventos previstos estão `request`, `vitals`, `screen_view`, `video_view`, `session` e `error`.

&emsp; O principal usuário da plataforma será a equipe técnica responsável pela observabilidade e investigação de incidentes. Entretanto, os benefícios da solução também alcançam indiretamente os assinantes do Globoplay, especialmente aqueles que utilizam dispositivos antigos ou enfrentam condições de conectividade menos favoráveis.

## 2. Metodologia

&emsp; A metodologia adotada orienta-se pelos princípios do Human-Centered Design (HCD) e do Design Thinking, buscando compreender tanto as necessidades dos usuários diretos da plataforma quanto os efeitos da solução sobre os usuários finais do Globoplay.

&emsp; Como fontes primárias, foram consideradas as entrevistas, reuniões e sessões de alinhamento realizadas com os stakeholders da Globo. Essas interações contribuíram para o entendimento do contexto operacional, das limitações das ferramentas atuais, das características dos dispositivos legados e das necessidades das equipes de engenharia e observabilidade.

&emsp; Como fontes secundárias, foram utilizados o documento TAPI, o anexo técnico sobre as fontes de dados e os exemplos de eventos de telemetria disponibilizados pelo parceiro. Esses materiais permitiram compreender os tipos de mensagens recebidas, os campos associados a dispositivos e sessões, as fontes de QoS e QoE e os desafios relacionados à normalização e correlação das informações.

&emsp; A construção das personas ocorreu a partir da identificação de padrões de comportamento, objetivos, necessidades, dores e cenários de interação relacionados ao problema. Inicialmente, foram levantadas hipóteses pelo grupo de desenvolvimento e, posteriormente, essas hipóteses foram refinadas com base nas informações fornecidas pelo parceiro.

&emsp; Foram definidos três perfis principais. O primeiro representa o usuário direto da solução, responsável pela monitoração e investigação de incidentes. O segundo representa uma usuária operacional, que utiliza a plataforma para apoiar a triagem e o encaminhamento de chamados de suporte. O terceiro representa o usuário final do Globoplay, que não interage diretamente com a plataforma de observabilidade, mas é impactado pela qualidade das análises e das decisões tomadas pelas equipes técnicas.

## 3. Personas

&emsp; Personas são representações fictícias de usuários reais, construídas a partir de padrões de comportamento, necessidades e objetivos. Funcionam como ferramentas estratégicas que humanizam dados abstratos e orientam decisões de produto, mantendo o foco nos usuários ao longo do processo de desenvolvimento (COOPER et al., 2014).

&emsp; As personas deste projeto foram construídas a partir da análise da problemática apresentada pela Globo, dos documentos disponibilizados pelo parceiro e dos alinhamentos realizados com os stakeholders. As representações foram elaboradas a partir das hipóteses iniciais do grupo e refinadas conforme o entendimento do contexto de observabilidade, dos dispositivos legados e dos impactos das falhas sobre os assinantes do Globoplay (PRUITT; ADLIN, 2006).

&emsp; Foram identificados três perfis com relações diferentes com a solução. Rafael Santos representa a persona principal e usuária direta da plataforma, pois utiliza os dados e as ferramentas de observabilidade para investigar falhas e orientar decisões técnicas. Mariana Souza representa uma persona operacional e também usuária direta, pois utiliza a plataforma para apoiar a triagem de chamados e o encaminhamento assertivo de incidentes às equipes responsáveis. Luísa Silva dos Santos representa uma persona secundária e indireta, pois não utiliza o sistema desenvolvido, mas é beneficiada pelas melhorias que ele pode proporcionar à experiência de reprodução.

### 3.1 Persona 1 - Rafael Santos, engenheiro de observabilidade

<div align="center">

<sub>Figura 1 - Persona: Rafael Santos, engenheiro de observabilidade</sub>

![Persona Rafael Santos](./assets/persona_rafael.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Rafael Santos, 30 anos, é engenheiro de observabilidade na Globo e representa o usuário principal da plataforma, sendo responsável por definir o roadmap técnico de monitoração e investigar incidentes no Globoplay. Suas principais dores estão na fragmentação dos dados entre login, player e CDN, com cada componente instrumentado de forma independente, e na baixa cobertura de dispositivos legados, que impede a definição de SLIs (Service Level Indicators, indicadores de nível de serviço) e SLOs (Service Level Objectives, metas de nível de serviço) para o frontend. Na interação com a solução, Rafael centraliza a ingestão e a normalização dos eventos em uma interface unificada, aplicando filtros por dispositivo, versão, componente e período para identificar padrões de falha com menor esforço manual e maior cobertura. Durante uma transmissão ao vivo com pico de falhas em TVs antigas, por exemplo, Rafael utiliza esses filtros para isolar a concentração de erros em um modelo e região específicos, o que agiliza a investigação técnica.

### 3.3 Persona 2 - Mariana Souza, analista de suporte

<div align="center">

<sub>Figura 2 - Persona: Mariana Souza, analista de suporte</sub>

![Persona Luísa dos Santos](./assets/persona_mariana.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Mariana Souza, 28 anos, é Analista de Suporte Nível 2 no Globoplay e representa a persona operacional da solução, atuando como ponte entre os relatos subjetivos dos usuários (como Luísa) e a investigação técnica conduzida por Rafael (Observabilidade). Suas principais dores estão na dependência de descrições vagas dos usuários para formular hipóteses, na fragmentação entre os silos de Login, Player e CDN, que faz chamados percorrerem múltiplas filas, e na invisibilidade de dispositivos legados nos logs convencionais. Na interação com a solução, Mariana utiliza o dashboard unificado para filtrar eventos por dispositivo, região e sessão, direcionando chamados de forma assertiva e eliminando o ciclo de tentativa e erro entre filas. Ao receber uma reclamação de um usuário de Smart TV de 2015 em Manaus, por exemplo, Mariana filtra pelo dispositivo e região no dashboard, identifica erros concentrados naquele recorte e encaminha o chamado diretamente à equipe correta.


### 3.2 Persona 3 - Luísa Silva dos Santos, assinante do Globoplay

<div align="center">

<sub>Figura 3 - Persona: Luísa Silva dos Santos, assinante do Globoplay</sub>

![Persona Luísa dos Santos](./assets/persona_luisa.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Luísa Silva dos Santos, 77 anos, é assinante do Globoplay e representa a persona indireta deste fluxo, sendo impactada pelas decisões técnicas de Rafael (Observabilidade) e pela triagem operacional de Mariana (Suporte). Suas principais dores estão nos travamentos frequentes durante a reprodução em sua televisão antiga, na falta de clareza das mensagens de erro e na dificuldade de resolver problemas sem auxílio técnico. A relação de Luísa com a plataforma de observabilidade é indireta, e ela é beneficiada quando a solução amplia a visibilidade sobre falhas em dispositivos legados, permitindo que as equipes identifiquem e corrijam problemas que afetam sua experiência de forma mais ágil. Ao enfrentar interrupções repetidas durante uma novela, por exemplo, os eventos do seu dispositivo são captados pela plataforma e a equipe de observabilidade identifica o padrão em aparelhos semelhantes, priorizando a correção de forma transparente para a usuária.


### 3.4. Relação entre as personas e a solução

&emsp; As três personas representam níveis diferentes de interação com o projeto. Rafael é o usuário direto da plataforma e necessita de recursos de consulta, filtragem, correlação e visualização dos eventos para investigação técnica. Mariana também é usuária direta, porém sua interação é orientada à triagem operacional e ao encaminhamento assertivo de chamados. Luísa é uma usuária indireta, cuja experiência depende da capacidade das equipes técnicas de identificar e corrigir falhas que afetam seu dispositivo.

| Persona | Relação com a solução | Principais necessidades | Benefício esperado |
|---|---|---|---|
| Rafael Santos | Usuário direto | Dados normalizados, filtros, cobertura de dispositivos legados e apoio à investigação | Redução do tempo de identificação e análise de falhas |
| Mariana Souza | Usuária direta (operacional) | Timeline unificada, filtros por dispositivo e região, visibilidade de dispositivos legados | Encaminhamento assertivo de chamados e redução do tempo de resolução |
| Luísa Silva dos Santos | Usuária indireta | Estabilidade, compatibilidade e orientações compreensíveis | Melhoria da experiência em dispositivos antigos |

&emsp; Essa distinção é importante para orientar as decisões de UX. O protótipo principal deverá ser desenvolvido para Rafael e Mariana, uma vez que são eles que interagem diretamente com o dashboard, Rafael sob a perspectiva de investigação técnica e Mariana sob a perspectiva de triagem operacional. As necessidades de Luísa devem ser consideradas como impactos esperados da solução e como critérios para avaliar a relevância das análises realizadas.


## 4. User Stories

&emsp; As User Stories conseguem traduzir ações específicas que precisam cumprir na solução, dada alguma necessidade/dor. Elas se tornam essenciais no Entendimento da Experiência do Usuário ao permitir uma validação de dores e necessidades que fazem sentido em relação à solução do problema, seguindo as boas práticas no formato INVEST que amplia a qualidade destas histórias. O acrônimo I.N.V.E.S.T. (Independente, Negociável, Valiosa, Estimável, Pequena e Testável) resume-se à um framework que auxilia na estruturação das User Stories (Bonilha, Diego; 2020).

| # | User Story | Persona | Dor atendida | Critérios de aceite |
|---|------------|---------|--------------|---------------------|
| US01 | Como Engenheiro de Observabilidade, eu quero uma API única de ingestão de eventos, para substituir as integrações separadas que hoje mantenho para login, player e CDN. | Rafael Santos | Cada componente foi instrumentado por um time diferente, sem padrão comum, o que exige uma integração específica a cada novo ponto de coleta. | Um único endpoint recebe eventos de qualquer componente frontend; suporte documentado para os tipos de evento mínimos (request, vitals, screen_view, video_view, session, error). |
| US02 | Como Engenheiro de Observabilidade, eu quero que a plataforma aceite tanto protocolos modernos quanto legados na coleta de eventos, para cobrir dispositivos que hoje ficam fora da telemetria (TVs antigas, apps desatualizados). | Rafael Santos | Parte do parque de dispositivos não suporta os protocolos modernos usados como padrão, criando pontos cegos permanentes de instrumentação. | Pipeline aceita eventos vindos de pelo menos um protocolo legado, além do moderno; eventos de dispositivos legados aparecem no mesmo dashboard que os demais, sem tratamento separado. |
| US03 | Como Engenheiro de Observabilidade, eu quero que os eventos recebidos passem por normalização mínima na ingestão, para que dados de login, player e CDN cheguem em formato comparável. | Rafael Santos | Sem normalização na origem, qualquer correlação entre componentes precisa ser feita manualmente por quem investiga um incidente. | Eventos de diferentes fontes usam o mesmo esquema de campos obrigatórios (timestamp, dispositivo, componente, status); divergências de formato entre fontes não impedem a consulta unificada dos dados. |
| US04 | Como Engenheiro de Observabilidade, eu quero visibilidade sobre a cobertura de instrumentação por dispositivo e componente, para identificar de forma objetiva onde ainda existem pontos cegos. | Rafael Santos | Hoje não há um jeito claro de saber quais dispositivos ou regiões estão mal cobertos até que um incidente revele a lacuna. | Painel mostra volume de eventos recebidos por tipo de dispositivo e componente; é possível identificar dispositivos com volume de eventos abaixo do esperado para o tráfego estimado. |
| US05 | Como Engenheiro de Observabilidade, eu quero que o pipeline de ingestão não perca eventos durante picos de tráfego, para manter a confiabilidade dos dados justamente nos momentos de maior audiência. | Rafael Santos | Eventos perdidos em picos comprometem a análise exatamente quando o volume de usuários afetados é maior. | Pipeline sustenta o pico de throughput de backend informado pelo parceiro sem descarte de eventos; testes de carga validam a ausência de perda antes de eventos sazonais de grande audiência. |
| US06 | Como Engenheiro de Observabilidade, eu quero definir SLIs e SLOs para o frontend com base nos dados coletados, para aplicar ao lado cliente a mesma disciplina de confiabilidade já usada no backend. | Rafael Santos | Hoje não há dados granulares suficientes do frontend para propor metas de confiabilidade equivalentes às já existentes no backend. | Dashboard permite acompanhar métricas de referência (ex: taxa de erro, latência) por período; é possível definir um limite aceitável e visualizar quando ele é ultrapassado. |
| US07 | Como Analista de Suporte, eu quero consultar a timeline de eventos de um usuário específico, para entender o que aconteceu na sessão sem depender de relatos subjetivos como "o vídeo não abre". | Mariana Souza | O diagnóstico inicial depende de relatos subjetivos do usuário, forçando a analista a adivinhar a causa para direcionar o chamado. | É possível localizar a sessão de um usuário e visualizar os eventos registrados nela em ordem cronológica; a timeline mostra ao menos os eventos de session, screen_view, video_view e error. |
| US08 | Como Analista de Suporte, eu quero filtrar eventos de erro por modelo de dispositivo e região, para identificar se um problema reportado é um caso isolado ou um padrão concentrado em um recorte específico. | Mariana Souza | Erros concentrados em dispositivos legados ou regiões específicas ficam mascarados pelas métricas nacionais agregadas, e a analista não consegue diferenciar isso na triagem. | Dashboard permite filtrar eventos por modelo de dispositivo e localização geográfica; é possível visualizar o volume de erros do recorte filtrado comparado ao total. |
| US09 | Como Analista de Suporte, eu quero visualizar em quais dispositivos legados os eventos estão sendo coletados, para confirmar que o suporte a um usuário de TV antiga não vai depender de investigação manual em outras ferramentas. | Mariana Souza | Dispositivos legados, como TVs de 2013 a 2015, não aparecem em logs ou métricas, dificultando a ajuda a esses usuários. | Dashboard exibe eventos de dispositivos legados no mesmo painel usado para dispositivos modernos; é possível confirmar, para um dispositivo legado específico, se ele está gerando eventos de request, session e error. |

### 4.1 Conclusão

&emsp; As nove User Stories contemplam as principais dores de Rafael e Mariana, cobrindo desde a ingestão unificada e a normalização dos eventos até a consulta por dispositivo, região e sessão. As histórias de Rafael (US01 a US06) concentram as necessidades de engenharia de observabilidade, enquanto as de Mariana (US07 a US09) endereçam a triagem operacional de chamados. Juntas, essas histórias também beneficiam Luísa de forma indireta, uma vez que a ampliação da cobertura e a agilidade na investigação resultam em correções mais rápidas para dispositivos legados.



## 6. Referências

BONILHA, Diego. **User Stories e o formato INVEST**. 2020. Disponível em fontes técnicas de metodologias ágeis. Acesso em: 29 abr. 2026.

COOPER, Alan; REIMANN, Robert; CRONIN, David; NOESSEL, Christopher. **About Face: The Essentials of Interaction Design**. 4. ed. Indianápolis: John Wiley & Sons, 2014.

KALBACH, James. **Mapping Experiences: A Complete Guide to Creating Value through Journeys, Blueprints, and Diagrams**. 1. ed. Sebastopol: O'Reilly Media, 2016.

PRUITT, John; ADLIN, Tamara. **The Persona Lifecycle: Keeping People in Mind Throughout Product Design**. São Francisco: Morgan Kaufmann, 2006.
