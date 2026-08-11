## 1. Contexto e escopo do projeto

&emsp; O projeto consiste no desenvolvimento de uma plataforma que atua como ponto central para o recebimento, o processamento e a consulta de eventos de telemetria das aplicações frontend do Globoplay. Esses eventos são produzidos por diferentes fontes e componentes, como login, player de vídeo e CDN, e podem chegar a partir de dispositivos modernos ou legados.

&emsp; No cenário atual, os eventos ficam distribuídos entre componentes e ferramentas de monitoração diferentes. Essa fragmentação dificulta a reconstrução do que aconteceu em uma sessão, a comparação entre dados relacionados e a identificação de padrões de falha. O problema se torna mais evidente em dispositivos antigos e versões legadas das aplicações, cuja cobertura de telemetria pode ser menor e gerar pontos cegos para as equipes técnicas.

&emsp; A solução proposta busca reunir eventos como `request`, `vitals`, `screen_view`, `video_view`, `session` e `error` em um fluxo centralizado. Ao preservar informações como origem, tipo, timestamp e dados do dispositivo quando disponíveis, a plataforma oferece uma base comum para consultas e análises. A partir dessa base, profissionais de observabilidade e suporte podem relacionar evidências, investigar comportamentos e formular hipóteses sobre possíveis causas de incidentes.

&emsp; O escopo da plataforma está concentrado na recepção e na disponibilização confiável dos eventos para investigação. A solução não realiza, por si só, o diagnóstico definitivo nem corrige automaticamente as falhas identificadas. Seus usuários diretos são profissionais de observabilidade e suporte, enquanto os assinantes do Globoplay são beneficiados indiretamente pela ampliação da cobertura e pela redução do tempo necessário para compreender e tratar problemas, especialmente em dispositivos legados.

## 2. Metodologia

&emsp; A metodologia adotada foi inspirada nos princípios de Human-Centered Design (HCD) e Design Thinking, que orientam a compreensão do contexto de uso e das necessidades das pessoas afetadas antes da definição da solução (ISO, 2019; BROWN, 2009). A abordagem foi aplicada de forma exploratória e documental, buscando transformar as informações fornecidas pelo parceiro em insumos claros para o desenho da experiência.

&emsp; A etapa de levantamento teve caráter documental e utilizou como fontes os alinhamentos realizados com stakeholders da Globo, o documento TAPI, o anexo técnico sobre as fontes de dados e os exemplos de eventos de telemetria fornecidos pelo parceiro. Esses materiais permitiram compreender a fragmentação da monitoração, as limitações de cobertura em diferentes dispositivos e os impactos dessas lacunas nos processos de investigação e suporte.

&emsp; Em seguida, as informações foram organizadas em dores, necessidades, objetivos, cenários de uso e requisitos derivados. Essa síntese permitiu conectar o problema de negócio ao comportamento esperado da solução, especialmente nos pontos relacionados ao recebimento centralizado dos eventos, à cobertura de dispositivos modernos e legados, à confiabilidade da ingestão e ao uso dos dados para apoiar investigações humanas.

&emsp; Como resultado dessa análise, foram elaboradas personas e User Stories para organizar as decisões de UX em torno de usos concretos da plataforma. Não foram realizadas, nesta etapa, entrevistas, observações de campo ou testes com usuários representativos; por isso, os artefatos produzidos devem ser entendidos como uma primeira estruturação do problema, sujeita a validação posterior com profissionais de observabilidade, analistas de suporte e assinantes.

## 3. Personas

&emsp; Personas são representações fictícias de usuários reais, construídas a partir de padrões de comportamento, necessidades e objetivos. Funcionam como ferramentas estratégicas que humanizam dados abstratos e orientam decisões de produto, mantendo o foco nos usuários ao longo do processo de desenvolvimento (COOPER et al., 2014).

&emsp; Neste projeto, elas funcionam como uma síntese dos principais pontos de vista envolvidos no uso e no impacto da solução. Por se tratar de uma etapa inicial, as representações devem ser lidas como hipóteses fundamentadas, úteis para orientar decisões de escopo, fluxos e priorização, mas ainda abertas a validação e refinamento com usuários representativos (PRUITT; ADLIN, 2006).

&emsp; Foram identificados três perfis com relações diferentes com a solução. Rafael Santos representa a persona principal e o usuário direto responsável por investigar falhas e orientar decisões técnicas. Mariana Souza representa uma persona operacional e também usuária direta, pois utiliza os eventos coletados para realizar a triagem de chamados e encaminhar incidentes às equipes responsáveis. Luísa Silva dos Santos representa a persona indireta: ela não utiliza a plataforma desenvolvida, mas é beneficiada pelas melhorias que a ampliação da observabilidade pode proporcionar à experiência de reprodução.

### 3.1 Persona 1 - Rafael Santos, engenheiro de observabilidade

<div align="center">

<sub>Figura 1 - Persona: Rafael Santos, engenheiro de observabilidade</sub>

![Persona Rafael Santos](./assets/persona_rafael.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Rafael Santos, 30 anos, atua como engenheiro de observabilidade na Globo e usa dados de telemetria para investigar incidentes no frontend. No projeto, ele é o usuário técnico principal: precisa que eventos de diferentes fontes e dispositivos cheguem a um fluxo centralizado antes de iniciar análises mais profundas. O valor da plataforma para Rafael está na confiabilidade da base disponível para investigação. Com maior cobertura de dispositivos modernos e legados, e sem perdas ou duplicidades na ingestão, ele consegue formular hipóteses com mais segurança, sem depender de um diagnóstico automático produzido pela solução.

### 3.2 Persona 2 - Mariana Souza, analista de suporte

<div align="center">

<sub>Figura 2 - Persona: Mariana Souza, analista de suporte</sub>

![Persona Mariana Souza](./assets/persona_mariana.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; No suporte Nível 2 do Globoplay, Mariana Souza, 28 anos, lida com chamados que precisam ser qualificados antes de chegar às equipes técnicas. A plataforma entra em sua rotina como apoio à triagem, oferecendo eventos e contexto para transformar relatos pouco específicos em evidências mais objetivas. Sua necessidade principal é reconstruir a sessão com rapidez e comparar o caso com recortes relevantes, como dispositivo, região ou tipo de evento. Com isso, Mariana ganha mais segurança para decidir se o chamado parece isolado, recorrente ou mal direcionado, mantendo a análise humana como parte central do processo.

### 3.3 Persona 3 - Luísa Silva dos Santos, assinante do Globoplay

<div align="center">

<sub>Figura 3 - Persona: Luísa Silva dos Santos, assinante do Globoplay</sub>

![Persona Luísa dos Santos](./assets/persona_luisa.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Luísa Silva dos Santos, 77 anos, representa o impacto final da solução fora do ambiente técnico. Como assinante do Globoplay, ela não acessa a plataforma nem interage com ferramentas de observabilidade; sua presença no estudo serve para lembrar que falhas pouco visíveis para as equipes podem ser bastante concretas para quem assiste. Quando eventos de dispositivos antigos passam a ser recebidos e analisados, problemas que antes poderiam ficar dispersos ganham maior chance de investigação e priorização. O benefício para Luísa, portanto, é indireto: reduzir o tempo até uma possível correção ou mitigação de falhas que afetam a reprodução em dispositivos legados.


### 3.4 Relação entre as personas e a solução

&emsp; A relação entre as personas e a solução orienta quais funcionalidades devem ser priorizadas no projeto. As necessidades de Rafael e Mariana direcionam os fluxos principais do dashboard, enquanto a experiência de Luísa funciona como indicador do impacto final esperado: reduzir falhas percebidas pelos assinantes por meio de uma monitoração mais completa e acionável.

| Persona | Relação com a solução | Principais necessidades | Benefício esperado |
|---|---|---|---|
| Rafael Santos | Usuário direto | Recebimento centralizado, filtros, cobertura de dispositivos legados e apoio à formulação de hipóteses | Redução do tempo de identificação e análise de falhas |
| Mariana Souza | Usuária direta (operacional) | Timeline unificada, filtros por dispositivo e região, visibilidade de dispositivos legados | Encaminhamento assertivo de chamados e redução do tempo de resolução |
| Luísa Silva dos Santos | Usuária indireta | Estabilidade, compatibilidade e cobertura de eventos em dispositivos legados | Melhoria da experiência em dispositivos antigos |

&emsp; Assim, as decisões de UX devem equilibrar profundidade técnica e clareza operacional. O protótipo precisa permitir análises detalhadas para investigação de incidentes, mas também oferecer caminhos simples para triagem e encaminhamento de problemas, mantendo como referência o efeito dessas decisões na experiência do assinante.


## 4. User Stories

&emsp; As User Stories traduzem ações específicas que as personas precisam cumprir na solução diante de necessidades e dores identificadas. Elas se tornam essenciais no Entendimento da Experiência do Usuário ao permitir a validação de necessidades relacionadas ao problema, seguindo as boas práticas do formato INVEST. O acrônimo I.N.V.E.S.T. (Independente, Negociável, Valiosa, Estimável, Pequena e Testável) resume um framework que auxilia na estruturação das User Stories (BONILHA, 2020).

| # | User Story | Persona | Dor atendida | Critérios de aceite |
|---|------------|---------|--------------|---------------------|
| US01 | Como Engenheiro de Observabilidade, eu quero um ponto central de recebimento de eventos de diferentes fontes, para reunir esses dados em um único fluxo e possibilitar a criação de hipóteses a partir deles. | Rafael Santos | Os eventos chegam hoje por fontes e componentes diferentes, sem um ponto comum que permita concentrar os dados antes da análise e da formulação de hipóteses. | Um ponto central recebe eventos de diferentes fontes frontend; cada evento recebido mantém identificação de origem, tipo e timestamp; os dados ficam disponíveis em um fluxo unificado para consulta e criação posterior de hipóteses. |
| US02 | Como Engenheiro de Observabilidade, eu quero que a plataforma receba eventos de diferentes tipos de dispositivos, incluindo dispositivos modernos e legados, para reduzir pontos cegos na telemetria. | Rafael Santos | Parte do parque de dispositivos fica fora da observabilidade por limitações de instrumentação ou coleta, impedindo que seus eventos sejam considerados na análise. | Eventos de dispositivos modernos e legados chegam ao mesmo fluxo centralizado; cada evento identifica dispositivo, modelo e versão quando disponível; dispositivos legados aparecem nas consultas junto com os demais. |
| US03 | Como Engenheiro de Observabilidade, eu quero visibilidade sobre a cobertura de instrumentação por dispositivo e componente, para identificar de forma objetiva onde ainda existem pontos cegos. | Rafael Santos | Hoje não há um jeito claro de saber quais dispositivos ou regiões estão mal cobertos até que um incidente revele a lacuna. | Painel mostra volume de eventos recebidos por tipo de dispositivo e componente; é possível identificar dispositivos com volume de eventos abaixo do esperado para o tráfego estimado. |
| US04 | Como Engenheiro de Observabilidade, eu quero que o pipeline de ingestão não perca nem duplique eventos durante picos de tráfego, para manter a confiabilidade dos dados justamente nos momentos de maior audiência. | Rafael Santos | Eventos perdidos ou duplicados em picos comprometem a análise exatamente quando o volume de usuários afetados é maior, podendo distorcer métricas e hipóteses. | Pipeline sustenta o pico de throughput informado pelo parceiro sem descarte de eventos; reenvios do mesmo evento são tratados de forma idempotente; testes de carga validam a ausência de perda e duplicação indevida. |
| US05 | Como Engenheiro de Observabilidade, eu quero definir SLIs e SLOs para o frontend com base nos dados coletados, para aplicar ao lado cliente a mesma disciplina de confiabilidade já usada no backend. | Rafael Santos | Hoje não há dados granulares suficientes do frontend para propor metas de confiabilidade equivalentes às já existentes no backend. | Dashboard permite acompanhar métricas de referência (ex: taxa de erro, latência) por período; é possível definir um limite aceitável e visualizar quando ele é ultrapassado. |
| US06 | Como Analista de Suporte, eu quero consultar a timeline de eventos de um usuário específico, para entender o que aconteceu na sessão sem depender de relatos subjetivos como "o vídeo não abre". | Mariana Souza | O diagnóstico inicial depende de relatos subjetivos do usuário, forçando a analista a adivinhar a causa para direcionar o chamado. | É possível localizar a sessão de um usuário e visualizar os eventos registrados nela em ordem cronológica; a timeline mostra ao menos os eventos de session, screen_view, video_view e error. |
| US07 | Como Analista de Suporte, eu quero filtrar eventos de erro por modelo de dispositivo e região, para identificar se um problema reportado é um caso isolado ou um padrão concentrado em um recorte específico. | Mariana Souza | Erros concentrados em dispositivos legados ou regiões específicas ficam mascarados pelas métricas nacionais agregadas, e a analista não consegue diferenciar isso na triagem. | Dashboard permite filtrar eventos por modelo de dispositivo e localização geográfica; é possível visualizar o volume de erros do recorte filtrado comparado ao total. |
| US08 | Como Analista de Suporte, eu quero visualizar em quais dispositivos legados os eventos estão sendo coletados, para confirmar que o suporte a um usuário de TV antiga não vai depender de investigação manual em outras ferramentas. | Mariana Souza | Dispositivos legados, como TVs de 2013 a 2015, não aparecem em logs ou métricas, dificultando a ajuda a esses usuários. | Dashboard exibe eventos de dispositivos legados no mesmo painel usado para dispositivos modernos; é possível confirmar, para um dispositivo legado específico, se ele está gerando eventos de request, session e error. |

&emsp; As oito User Stories contemplam as principais dores de Rafael e Mariana, cobrindo desde o recebimento centralizado de eventos de diferentes fontes e dispositivos até a confiabilidade da ingestão e a consulta por dispositivo, região e sessão. As histórias de Rafael (US01 a US05) concentram as necessidades de engenharia de observabilidade, com a US01 estabelecendo a base para reunir dados e permitir a criação posterior de hipóteses. Já as histórias de Mariana (US06 a US08) endereçam a triagem operacional de chamados. Juntas, essas histórias também beneficiam Luísa de forma indireta, uma vez que a ampliação da cobertura e a agilidade na investigação resultam em correções mais rápidas para dispositivos legados.


## 6. Referências

BONILHA, Diego. **User Stories e o formato INVEST**. 2020. Disponível em fontes técnicas de metodologias ágeis. Acesso em: 29 abr. 2026.

BROWN, Tim. **Change by Design: How Design Thinking Transforms Organizations and Inspires Innovation**. Nova York: HarperBusiness, 2009.

COOPER, Alan; REIMANN, Robert; CRONIN, David; NOESSEL, Christopher. **About Face: The Essentials of Interaction Design**. 4. ed. Indianápolis: John Wiley & Sons, 2014.

INTERNATIONAL ORGANIZATION FOR STANDARDIZATION. **ISO 9241-210:2019: Ergonomics of Human-System Interaction — Part 210: Human-Centred Design for Interactive Systems**. Genebra: ISO, 2019.

KALBACH, James. **Mapping Experiences: A Complete Guide to Creating Value through Journeys, Blueprints, and Diagrams**. 1. ed. Sebastopol: O'Reilly Media, 2016.

PRUITT, John; ADLIN, Tamara. **The Persona Lifecycle: Keeping People in Mind Throughout Product Design**. São Francisco: Morgan Kaufmann, 2006.
