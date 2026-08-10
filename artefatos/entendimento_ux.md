## 1. Contexto e escopo do projeto

&emsp; O projeto consiste no desenvolvimento de uma plataforma para coleta, normalização, processamento e consulta de eventos de telemetria das aplicações frontend do Globoplay, incluindo dispositivos modernos e legados.

&emsp; Hoje, componentes como login, player de vídeo e CDN possuem padrões de monitoração diferentes, o que dificulta a comparação dos dados e a identificação rápida de falhas. A solução proposta busca unificar a ingestão, normalizar eventos como `request`, `vitals`, `screen_view`, `video_view`, `session` e `error`, e apoiar a equipe técnica na investigação de incidentes.

&emsp; Os usuários diretos da plataforma são profissionais de observabilidade e suporte. Os assinantes do Globoplay são beneficiados indiretamente, principalmente quando usam dispositivos antigos ou enfrentam problemas de conectividade.

## 2. Metodologia

&emsp; A metodologia adotada foi baseada em Human-Centered Design (HCD) e Design Thinking, com foco na identificação das necessidades, dores e objetivos dos usuários envolvidos na solução.

&emsp; Para isso, foram considerados os alinhamentos com stakeholders da Globo, o documento TAPI, o anexo técnico sobre fontes de dados e os exemplos de eventos de telemetria fornecidos pelo parceiro.

&emsp; A partir dessas informações, foram definidas três personas: um engenheiro de observabilidade, uma analista de suporte e uma assinante do Globoplay impactada indiretamente pela qualidade da monitoração.

## 3. Personas

&emsp; Personas são representações fictícias de usuários reais, construídas a partir de padrões de comportamento, necessidades e objetivos. Funcionam como ferramentas estratégicas que humanizam dados abstratos e orientam decisões de produto, mantendo o foco nos usuários ao longo do processo de desenvolvimento (COOPER et al., 2014).

&emsp; As personas deste projeto foram construídas a partir da análise da problemática apresentada pela Globo, dos documentos disponibilizados pelo parceiro e dos operacionalalinhamentos realizados com os stakeholders. As representações foram elaboradas a partir das hipóteses iniciais do grupo e refinadas conforme o entendimento do contexto de observabilidade, dos dispositivos legados e dos impactos das falhas sobre os assinantes do Globoplay (PRUITT; ADLIN, 2006).

&emsp; Foram identificados três perfis com relações diferentes com a solução. Rafael Santos representa a persona principal e usuária direta da plataforma, pois utiliza os dados e as ferramentas de observabilidade para investigar falhas e orientar decisões técnicas. Mariana Souza representa uma persona  e também usuária direta, pois utiliza a plataforma para apoiar a triagem de chamados e o encaminhamento assertivo de incidentes às equipes responsáveis. Luísa Silva dos Santos representa uma persona secundária e indireta, pois não utiliza o sistema desenvolvido, mas é beneficiada pelas melhorias que ele pode proporcionar à experiência de reprodução.

### 3.1 Persona 1 - Rafael Santos, engenheiro de observabilidade

<div align="center">

<sub>Figura 1 - Persona: Rafael Santos, engenheiro de observabilidade</sub>

![Persona Rafael Santos](./assets/persona_rafael.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Rafael Santos, 30 anos, é engenheiro de observabilidade na Globo e representa o usuário principal da plataforma. Sua principal dor é a fragmentação dos dados entre login, player e CDN, além da baixa visibilidade sobre dispositivos legados. Na solução, Rafael utiliza filtros por dispositivo, versão, componente e período para investigar padrões de falha. Em uma transmissão ao vivo com aumento de erros em TVs antigas, por exemplo, ele consegue isolar o modelo e a região mais afetados.

### 3.2 Persona 2 - Mariana Souza, analista de suporte

<div align="center">

<sub>Figura 2 - Persona: Mariana Souza, analista de suporte</sub>

![Persona Mariana Souza](./assets/persona_mariana.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Mariana Souza, 28 anos, é Analista de Suporte Nível 2 no Globoplay e representa uma persona operacional secundária da solução. Sua principal dor é depender de relatos vagos dos usuários e de ferramentas fragmentadas para direcionar chamados. Na solução, Mariana consulta eventos por dispositivo, região e sessão para fazer uma triagem mais precisa. Ao receber uma reclamação de uma Smart TV de 2015 em Manaus, por exemplo, ela identifica se há erros recorrentes naquele recorte antes de encaminhar o chamado.


### 3.3 Persona 3 - Luísa Silva dos Santos, assinante do Globoplay

<div align="center">

<sub>Figura 3 - Persona: Luísa Silva dos Santos, assinante do Globoplay</sub>

![Persona Luísa dos Santos](./assets/persona_luisa.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Luísa Silva dos Santos, 77 anos, é assinante do Globoplay e representa a usuária impactada indiretamente pela solução. Sua principal dor são travamentos frequentes em sua televisão antiga e a dificuldade de resolver problemas técnicos sozinha. Embora não utilize a plataforma, Luísa se beneficia quando os eventos do seu dispositivo ajudam a equipe técnica a identificar falhas recorrentes. Ao enfrentar interrupções durante uma novela, por exemplo, seus eventos podem contribuir para priorizar uma correção em aparelhos semelhantes.


### 3.4. Relação entre as personas e a solução

&emsp; A relação entre as personas e a solução orienta quais funcionalidades devem ser priorizadas no projeto. As necessidades de Rafael e Mariana direcionam os fluxos principais do dashboard, enquanto a experiência de Luísa funciona como indicador do impacto final esperado: reduzir falhas percebidas pelos assinantes por meio de uma monitoração mais completa e acionável.

| Persona | Relação com a solução | Principais necessidades | Benefício esperado |
|---|---|---|---|
| Rafael Santos | Usuário direto | Dados normalizados, filtros, cobertura de dispositivos legados e apoio à investigação | Redução do tempo de identificação e análise de falhas |
| Mariana Souza | Usuária direta (operacional) | Timeline unificada, filtros por dispositivo e região, visibilidade de dispositivos legados | Encaminhamento assertivo de chamados e redução do tempo de resolução |
| Luísa Silva dos Santos | Usuária indireta | Estabilidade, compatibilidade e orientações compreensíveis | Melhoria da experiência em dispositivos antigos |

&emsp; Assim, as decisões de UX devem equilibrar profundidade técnica e clareza operacional. O protótipo precisa permitir análises detalhadas para investigação de incidentes, mas também oferecer caminhos simples para triagem e encaminhamento de problemas, mantendo como referência o efeito dessas decisões na experiência do assinante.


## 4. User Stories

&emsp; As User Stories traduzem ações específicas que as personas precisam cumprir na solução diante de necessidades e dores identificadas. Elas se tornam essenciais no Entendimento da Experiência do Usuário ao permitir a validação de necessidades relacionadas ao problema, seguindo as boas práticas do formato INVEST. O acrônimo I.N.V.E.S.T. (Independente, Negociável, Valiosa, Estimável, Pequena e Testável) resume um framework que auxilia na estruturação das User Stories (BONILHA, 2020).

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
