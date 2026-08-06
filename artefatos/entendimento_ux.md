## 1. Contexto e escopo do projeto

&emsp; O projeto consiste no desenvolvimento de uma plataforma distribuída de backend para coleta, normalização, processamento e consulta de eventos de telemetria provenientes das aplicações frontend do Globoplay. A solução busca atender a diferentes tipos de dispositivos, sistemas operacionais, versões de aplicativos e condições de conectividade, incluindo equipamentos legados que não oferecem suporte completo aos padrões modernos de observabilidade.

&emsp; Atualmente, os componentes relacionados ao login, ao player de vídeo e à distribuição de conteúdo por CDN possuem padrões de monitoração distintos. Essa fragmentação dificulta a comparação das informações, exige correlação manual entre diferentes fontes e reduz a visibilidade sobre falhas que afetam plataformas ou dispositivos específicos.

&emsp; A solução proposta deverá oferecer uma API unificada de ingestão, suporte a formatos modernos e legados, normalização dos eventos recebidos e disponibilização de consultas e visualizações operacionais. Entre os eventos previstos estão `request`, `vitals`, `screen_view`, `video_view`, `session` e `error`.

&emsp; O principal usuário da plataforma será a equipe técnica responsável pela observabilidade e investigação de incidentes. Entretanto, os benefícios da solução também alcançam indiretamente os assinantes do Globoplay, especialmente aqueles que utilizam dispositivos antigos ou enfrentam condições de conectividade menos favoráveis.

---

## 2. Metodologia

&emsp; A metodologia adotada orienta-se pelos princípios do Human-Centered Design (HCD) e do Design Thinking, buscando compreender tanto as necessidades dos usuários diretos da plataforma quanto os efeitos da solução sobre os usuários finais do Globoplay.

&emsp; Como fontes primárias, foram consideradas as entrevistas, reuniões e sessões de alinhamento realizadas com os stakeholders da Globo. Essas interações contribuíram para o entendimento do contexto operacional, das limitações das ferramentas atuais, das características dos dispositivos legados e das necessidades das equipes de engenharia e observabilidade.

&emsp; Como fontes secundárias, foram utilizados o documento TAPI, o anexo técnico sobre as fontes de dados e os exemplos de eventos de telemetria disponibilizados pelo parceiro. Esses materiais permitiram compreender os tipos de mensagens recebidas, os campos associados a dispositivos e sessões, as fontes de QoS e QoE e os desafios relacionados à normalização e correlação das informações.

&emsp; A construção das personas ocorreu a partir da identificação de padrões de comportamento, objetivos, necessidades, dores e cenários de interação relacionados ao problema. Inicialmente, foram levantadas hipóteses pelo grupo de desenvolvimento e, posteriormente, essas hipóteses foram refinadas com base nas informações fornecidas pelo parceiro.

&emsp; Foram definidos dois perfis principais. O primeiro representa o usuário direto da solução, responsável pela monitoração e investigação de incidentes. O segundo representa o usuário final do Globoplay, que não interage diretamente com a plataforma de observabilidade, mas é impactado pela qualidade das análises e das decisões tomadas pelas equipes técnicas.

---

## 3. Personas

&emsp; Personas são representações fictícias de usuários reais, construídas a partir de padrões de comportamento, necessidades e objetivos. Funcionam como ferramentas estratégicas que humanizam dados abstratos e orientam decisões de produto, mantendo o foco nos usuários ao longo do processo de desenvolvimento (COOPER et al., 2014).

&emsp; As personas deste projeto foram construídas a partir da análise da problemática apresentada pela Globo, dos documentos disponibilizados pelo parceiro e dos alinhamentos realizados com os stakeholders. As representações foram elaboradas a partir das hipóteses iniciais do grupo e refinadas conforme o entendimento do contexto de observabilidade, dos dispositivos legados e dos impactos das falhas sobre os assinantes do Globoplay (PRUITT; ADLIN, 2006).

&emsp; Foram identificados dois perfis com relações diferentes com a solução. Rafael Santos representa a persona principal e usuária direta da plataforma, pois utiliza os dados e as ferramentas de observabilidade para investigar falhas e orientar decisões técnicas. Luísa Silva dos Santos representa uma persona secundária e indireta, pois não utiliza o sistema desenvolvido, mas é beneficiada pelas melhorias que ele pode proporcionar à experiência de reprodução.

### 3.1 Persona 1 - Rafael Santos, engenheiro de observabilidade

<div align="center">

<sub>Figura 1 - Persona: Rafael Santos, engenheiro de observabilidade</sub>

![Persona Rafael Santos](./assets/persona_rafael.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Rafael Santos, 30 anos, é engenheiro de observabilidade na Globo e lidera tecnicamente a evolução da plataforma interna de observabilidade da empresa. Atuou anteriormente como engenheiro sênior de Site Reliability Engineering (SRE) e participou da construção de uma plataforma voltada à centralização da gestão de SLIs e SLOs, à automação de testes de desempenho e à aplicação de práticas de Chaos Engineering.

&emsp; Atualmente, Rafael define o roadmap técnico dessa frente e prioriza iniciativas entre diferentes áreas de engenharia. No Globoplay, os componentes de login, player e CDN evoluíram com padrões de monitoração próprios e pouco integrados. Como consequência, a investigação de incidentes exige a consulta e a correlação manual de dados provenientes de ferramentas diferentes.

&emsp; Parte dos dispositivos utilizados para acessar o Globoplay, incluindo televisores antigos e versões legadas do aplicativo, não suporta os protocolos modernos de telemetria que Rafael utilizaria como padrão. Isso reduz a cobertura de monitoração e dificulta a criação de indicadores de confiabilidade para o frontend semelhantes aos já utilizados no backend.

&emsp; Entre suas principais dores estão a falta de um padrão único para a coleta de eventos, a ausência de normalização entre os componentes, a baixa cobertura de dispositivos legados e a dificuldade de obter dados granulares suficientes para apoiar a definição de SLIs e SLOs para o frontend.

&emsp; Rafael necessita de uma plataforma que centralize os eventos de login, player e CDN, aceite dados provenientes de dispositivos modernos e legados e disponibilize informações comparáveis para consulta e análise. Seu objetivo é reduzir o esforço manual empregado na investigação de incidentes, ampliar a cobertura da observabilidade e melhorar a capacidade de identificar padrões de falha.

&emsp; A solução proposta auxilia Rafael ao oferecer uma API unificada de ingestão, uma camada de normalização mínima e interfaces de consulta capazes de organizar eventos por dispositivo, versão, componente, sessão e período. A plataforma não necessariamente determina de forma automática a causa raiz de cada problema, mas oferece evidências que apoiam a formulação e a validação de hipóteses durante a investigação.

#### Cenário de interação

&emsp; Durante uma transmissão ao vivo de grande audiência, ocorre um aumento de falhas em televisores fabricados em 2015. Sem uma visão unificada, Rafael e a equipe precisam consultar separadamente dados de login, player, CDN e infraestrutura para entender o alcance do problema.

&emsp; Com a solução, os eventos são recebidos por uma interface comum e normalizados desde a ingestão. Rafael aplica filtros por período, modelo de dispositivo, versão da aplicação, região e tipo de erro. A análise mostra que a maior concentração de falhas ocorre em um conjunto específico de televisores e em determinada região, permitindo que a equipe direcione a investigação técnica com maior rapidez.

### 3.2 Persona 2 - Luísa Silva dos Santos, assinante do Globoplay

<div align="center">

<sub>Figura 2 - Persona: Luísa Silva dos Santos, assinante do Globoplay</sub>

![Persona Luísa dos Santos](./assets/persona_luisa.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Luísa Silva dos Santos, 77 anos, é assinante e usuária frequente do Globoplay, principalmente para assistir a novelas. Ela utiliza uma televisão antiga e possui pouca familiaridade com configurações técnicas, atualizações de software e mensagens de erro.

&emsp; Durante o uso da plataforma, Luísa enfrenta travamentos e interrupções na reprodução. As mensagens apresentadas na televisão nem sempre são suficientemente claras para que ela compreenda a natureza do problema ou saiba como agir. Como resultado, sente-se frustrada e pode interpretar a falha como um problema permanente da plataforma.

&emsp; Entre suas principais dores estão os travamentos frequentes, a falta de clareza das mensagens exibidas e a dificuldade de resolver problemas técnicos sem auxílio. Suas necessidades incluem uma experiência de reprodução mais estável e orientações simples quando uma falha puder ser resolvida por uma ação do usuário.

&emsp; Luísa não utilizará diretamente o dashboard ou a API desenvolvida pelo projeto. Sua relação com a solução é indireta. Ao ampliar a visibilidade sobre falhas em dispositivos legados, a plataforma permite que as equipes técnicas identifiquem quais modelos, versões ou condições de uso apresentam maior incidência de problemas.

&emsp; A solução auxilia Luísa ao fornecer dados mais completos para as equipes responsáveis pela manutenção do Globoplay. Esses dados podem apoiar a correção de falhas, a manutenção da compatibilidade com aparelhos antigos e a priorização de melhorias que reduzam travamentos e interrupções.

&emsp; A geração de mensagens explicativas diretamente na televisão não está necessariamente contemplada no escopo atual. Para que isso ocorra, seria necessária uma integração entre os diagnósticos ou classificações produzidos pela plataforma e a interface do aplicativo utilizada pelo assinante.

#### Cenário de impacto

&emsp; Luísa tenta assistir a uma novela, mas a reprodução apresenta interrupções repetidas. Os eventos enviados pelo dispositivo registram falhas de requisição, erros do player e informações sobre o modelo e a versão do aplicativo.

&emsp; A equipe de observabilidade identifica que o mesmo padrão ocorre em outros aparelhos semelhantes. Com base nessa evidência, os responsáveis podem priorizar a investigação, desenvolver uma correção compatível com o dispositivo ou orientar o suporte sobre uma possível ação de mitigação. Dessa forma, Luísa é beneficiada pela solução mesmo sem interagir diretamente com ela.

---

## 4. Relação entre as personas e a solução

&emsp; As duas personas representam níveis diferentes de interação com o projeto. Rafael é o usuário direto da plataforma e necessita de recursos de consulta, filtragem, correlação e visualização dos eventos. Luísa é uma usuária indireta, cuja experiência depende da capacidade das equipes técnicas de identificar e corrigir falhas que afetam seu dispositivo.

| Persona | Relação com a solução | Principais necessidades | Benefício esperado |
|---|---|---|---|
| Rafael Santos | Usuário direto | Dados normalizados, filtros, cobertura de dispositivos legados e apoio à investigação | Redução do tempo de identificação e análise de falhas |
| Luísa Silva dos Santos | Usuária indireta | Estabilidade, compatibilidade e orientações compreensíveis | Melhoria da experiência em dispositivos antigos |

&emsp; Essa distinção é importante para orientar as decisões de UX. O protótipo principal deverá ser desenvolvido para Rafael e outros profissionais de observabilidade, uma vez que são eles que interagem diretamente com o dashboard. As necessidades de Luísa devem ser consideradas como impactos esperados da solução e como critérios para avaliar a relevância das análises realizadas.


## 4. User Stories

&emsp; As User Stories conseguem traduzir ações específicas que precisam cumprir na solução, dada alguma necessidade/dor. Elas se tornam essenciais no Entendimento da Experiência do Usuário ao permitir uma validação de dores e necessidades que fazem sentido em relação à solução do problema, seguindo as boas práticas no formato INVEST que amplia a qualidade destas histórias. O acrônimo I.N.V.E.S.T. (Independente, Negociável, Valiosa, Estimável, Pequena e Testável) resumi-se à um framework que auxilia na estruturação das User Stories (Bonilha, Diego; 2020).

| # | User Story | Persona | Dor atendida | Critérios de aceite |
|---|------------|---------|--------------|---------------------|
| US01 | Como Especialista de Políticas de Crédito, eu quero ajustar parâmetros de política de limite (multiplicadores de alavancagem, limite máximo por faixa de risco, restrições de capacidade de pagamento) e visualizar imediatamente o impacto resultante em métricas de risco e negócio, para validar novas políticas de forma autônoma, reduzindo o tempo de validação de semanas para horas e eliminando a dependência de requisições ao time de Data Science. | Mariana Silva | Dependência operacional de Data Science para cada teste de cenário, gerando atrasos de dias a semanas. | Interface permite ajustar multiplicadores por faixa de PD sem intervenção técnica; visualização imediata do impacto em inadimplência física, financeira, volume e retorno; comparação lado a lado entre cenário ajustado e baseline; possibilidade de salvar cenários para auditoria; histórico de testes registrado para rastreabilidade. |
| US02 | Como Especialista de Políticas de Crédito, eu quero comparar as recomendações de limite geradas pela solução linear com as recomendações do modelo não-linear atualmente em produção, identificando convergências e divergências entre os dois algoritmos, para fundamentar decisões de limite com mais robustez técnica perante a liderança, baseando-me em duas fontes de validação independentes em vez de confiar em um único modelo. | Mariana Silva | Dificuldade em validar decisões do modelo atual de forma independente; confia em um único algoritmo sem mecanismo de validação cruzada. | Plataforma permite importar resultados do modelo não-linear para mesma safra; comparação visual lado a lado das recomendações por cliente/segmento; identificação automática de divergências significativas (diferença superior a 10%); análise por segmento mostrando convergências e divergências com possíveis causas; geração de relatório executivo de validação dual para apresentação à liderança. |
| US03 | Como Especialista de Políticas de Crédito, eu quero que todas as ofertas de limite geradas respeitem automaticamente as regras obrigatórias do banco (limite mínimo de R$200, múltiplos de R$50, restrições de alavancagem por segmento) e visualizar relatórios de conformidade em dashboard, para eliminar a auditoria manual exaustiva atualmente necessária para validar regras básicas, garantindo 100% de conformidade sem esforço operacional repetitivo. | Mariana Silva | Auditoria manual exaustiva para verificar conformidade com regras básicas de negócio em ofertas geradas. | Modelo aplica automaticamente regras obrigatórias durante a otimização (não em pós-processamento); dashboard mostra percentual de conformidade em tempo real para cada regra; relatório identifica clientes rejeitados por violação de cada restrição específica; possibilidade de editar regras de conformidade com preview de impacto; relatório de conformidade exportável para auditoria interna em formato padronizado. |
| US04 | Como Especialista de Políticas de Crédito, eu quero criar e armazenar múltiplos cenários de política (ex: cenário conservador, agressivo, balanceado) com diferentes configurações de parâmetros, e compará-los lado a lado em métricas-chave, para apresentar opções fundamentadas à liderança executiva com suporte quantitativo claro, facilitando tomada de decisão estratégica sobre direcionamento de política de crédito. | Mariana Silva | Necessidade de fundamentação técnica robusta para defender decisões de limite perante liderança executiva, com comparação clara de alternativas. | Plataforma permite criar e nomear múltiplos cenários (ex: "Conservador_2026", "Agressivo_Volume"); cada cenário armazena parâmetros configurados, métricas resultantes e validação cruzada com modelo não-linear; visualização comparativa entre até quatro cenários simultaneamente com métricas principais destacadas; geração de relatório executivo com gráficos comparativos, trade-offs e recomendação fundamentada; possibilidade de marcar cenário como "Recomendado" com justificativa documentada; histórico de cenários comparados registrado para rastreabilidade. |
| US05 | Como Especialista de Políticas de Crédito, eu quero monitorar continuamente o desempenho da política implementada em produção através de dashboard com métricas-chave (inadimplência real versus projetada, volume aprovado, taxa de aceitação, conformidade) atualizadas por safra, para identificar desvios em relação ao esperado e tomar decisões corretivas rápidas antes que problemas se materializem na carteira. | Mariana Silva | Falta de visibilidade contínua sobre desempenho real das políticas implementadas, dificultando ajustes proativos quando há desvios. | Dashboard exibe métricas de risco e negócio atualizadas por safra; comparação automática entre projetado e realizado para inadimplência física, financeira, volume e retorno; alertas configuráveis quando métricas saem de bounds esperados (ex: inadimplência real 20% acima da projetada); drill-down por segmento de risco para identificar onde estão os desvios; histórico de safras anteriores disponível para análise de tendência; integração com cockpit operacional para ajustes rápidos de política caso desvios sejam identificados. |---

## 5. Jornada do Usuário (Persona: Rafael)

&emsp; A Jornada do Usuário é uma ferramenta de design que mapeia, de forma cronológica, as etapas percorridas por uma persona ao interagir com um sistema, produto ou processo; registrando suas ações, pensamentos e estados emocionais em cada fase. Mais do que descrever o que o usuário faz, a jornada evidencia onde estão os pontos de dor, os gargalos operacionais e as oportunidades de melhoria, tornando visível a experiência real do usuário antes e depois da solução (KALBACH, 2016).
Neste projeto, foram mapeadas duas jornadas complementares para José Lopez, Diretor de Data Science do Banco Pan: a jornada antes da solução, que expõe as limitações do processo atual de auditoria e análise de limites de crédito, e a jornada com a solução, que demonstra como o modelo de otimização transforma sua rotina ao fornecer uma base comparativa estruturada e reduzir a dependência de análises manuais.

### 5.1. Jornada do Usuário Rafael

<div align='center'>

<sub>Figura 4 - Jornada do usuário atual/sub>

![Jornada do Usuário pré solução](./assets/jornada_usuario_atual.png)

<sup>Fonte: Material produzido pelos autores (2026)</sup>

</div>

&emsp; A jornada anterior à solução revela uma rotina marcada por retrabalho e falta de embasamento formal. Sem uma referência comparativa ao algoritmo vigente, José não consegue responder com segurança se os limites concedidos pelo modelo atual são ótimos, toda análise parte do zero. Solicitações do time de Políticas de Crédito interrompem seu fluxo de trabalho, e apresentações à liderança carecem de sustentação matemática. A curva emocional oscila entre frustração, incerteza e bloqueio, refletindo um processo que depende mais de esforço individual do que de estrutura técnica.

### 5.2. Jornada do Usuário Luísa

<div align='center'>

<sub>Figura 5 - Jornada do usuário depois da futura</sub>

![Jornada do Usuário pós solução](./assets/jornada_usuario_futura.png)

<sup>Fonte: Material produzido pelos autores (2026)</sup>

</div>

&emsp; Com o modelo de otimização em operação, a jornada de José se torna estruturada e orientada por dados. Ele passa a receber outputs comparáveis ao algoritmo atual, identificar divergências com embasamento técnico e apresentar resultados auditáveis à liderança sem depender de análises pontuais sob demanda. Quando Mariana, do time de Políticas de Crédito, aciona José com dúvidas sobre o modelo, ele consegue explicar a decisão com base nas restrições aplicadas, sem precisar alterar o código. A curva emocional evolui de confiança para satisfação e alívio, indicando que a solução não apenas resolve os pontos de dor anteriores, mas também amplia a autonomia técnica do time.

### 5.3 Conclusão

&emsp; A comparação entre as duas jornadas deixa evidente o papel central que o modelo de otimização exerce na rotina de José Lopez. A solução não substitui o algoritmo já em produção, mas fornece a ele algo que antes não existia: uma referência objetiva, matematicamente documentada, para questionar e aprimorar continuamente as decisões de concessão de crédito. Ao eliminar análises manuais, reduzir o gargalo técnico entre Data Science e Políticas de Crédito e tornar as decisões de limite rastreáveis e defensáveis, a solução transforma uma prática empírica em um processo científico, sistemático e escalável, alinhado às metas estratégicas do Banco Pan.

---

## 6. Referências

BANCO PAN. **Documento TAPI: Definição Ótima de Limites Pré-aprovados de Crédito**. São Paulo: Banco Pan, 2026. Documento interno compartilhado com os desenvolvedores.

BONILHA, Diego. **User Stories e o formato INVEST**. 2020. Disponível em fontes técnicas de metodologias ágeis. Acesso em: 29 abr. 2026.

COOPER, Alan; REIMANN, Robert; CRONIN, David; NOESSEL, Christopher. **About Face: The Essentials of Interaction Design**. 4. ed. Indianápolis: John Wiley & Sons, 2014.

KALBACH, James. **Mapping Experiences: A Complete Guide to Creating Value through Journeys, Blueprints, and Diagrams**. 1. ed. Sebastopol: O'Reilly Media, 2016.

PRUITT, John; ADLIN, Tamara. **The Persona Lifecycle: Keeping People in Mind Throughout Product Design**. São Francisco: Morgan Kaufmann, 2006.
