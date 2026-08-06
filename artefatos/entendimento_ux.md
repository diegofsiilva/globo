## 1. Contexto e escopo do projeto

&emsp; A solução proposta é utilizada por profissionais internos do Banco Pan inseridos na estrutura de crédito da instituição. O usuário direto é o analista do time de Políticas de Crédito, que opera a solução para definir, de forma sistemática, quais limites pré-aprovados de cartão de crédito serão ofertados a cada cliente correntista elegível. Esse profissional precisa que o sistema apoie decisões que equilibrem rentabilidade esperada e controle de inadimplência, física e financeira, sem violar regras de negócio como limite mínimo de R$200 e discretização em múltiplos de R$50. Em paralelo, o time de Data Science interage com o software para validar tecnicamente os resultados, comparar os limites sugeridos com os previamente concedidos e garantir a integrabilidade do código Python ao motor de crédito do banco. Ambos os perfis estão diretamente vinculados ao problema central do projeto: substituir uma prática empírica de concessão de limites por um modelo de otimização linear que maximize o retorno ajustado ao risco.

---

## 2. Metodologia

&emsp; A metodologia adotada orienta-se pelos princípios do Human-Centered Design (HCD) e do Design Thinking. As fontes primárias englobam entrevistas e sessões de alinhamento com os stakeholders do Banco Pan (Eduardo, Mateus e Felipe), que foram fundamentais para mapear e validar as dores das áreas de Data Science e Políticas de Crédito. Como fontes secundárias, utilizou-se a análise do documento TAPI e a exploração da base de dados de três safras fornecida pelo parceiro. Essa abordagem foi selecionada porque garante que a complexidade e o rigor do modelo de otimização matemático sejam traduzidos em uma interface e um fluxo de valor úteis e amigáveis para quem realmente opera o sistema no dia a dia.

---

## 3. Personas

&emsp; Personas são representações fictícias de usuários reais, construídas a partir de padrões de comportamento, necessidades e objetivos. Funcionam como ferramentas estratégicas que humanizam dados abstratos, orientando decisões de produto ao manter o foco no usuário final durante todo o ciclo de desenvolvimento (COOPER et al., 2014).

&emsp; As personas deste projeto foram construídas a partir da análise da problemática descrita no documento TAPI pelo Banco Pan, bem como do alinhamento com os stakeholders e da compreensão do atual ambiente operacional de concessão de crédito. Estruturadas a partir das hipóteses iniciais do grupo de desenvolvimento e posteriormente validadas junto ao parceiro de negócios, essas representações refletem com precisão os desafios reais enfrentados pelos principais usuários da solução proposta (PRUITT; ADLIN, 2006).

&emsp; Dentre os três perfis identificados, a persona principal e usuária direta da solução é Mariana Silva, Especialista de Políticas de Crédito. Ela atua na operação diária validando e aplicando os parâmetros de concessão, precisando que os limites sugeridos pelo modelo cheguem conformes às regras de negócio vigentes (como piso de R$200 e discretização em múltiplos de R$50) sem elevar o risco da carteira. De maneira complementar e essencial à mecânica do sistema, está José Lopez, Diretor de Data Science, que personifica o usuário técnico-estratégico, sendo o responsável por exigir que o modelo seja formulado matematicamente, documentado, executável em Python e integrável ao motor de decisão. Por fim, Rodrigo Santos, Cliente do banco Pan, representa a ponta deste ecossistema, sendo o beneficiário final impactado pela adequação da oferta. Essas três perspectivas asseguram que a solução equilibre rigor matemático na modelagem com aplicabilidade direta no processo de concessão, gerando inclusão financeira e mitigando o risco sistêmico.

### 3.1 Persona 1 — [Mariana Silva, Especialista de Políticas de Crédito]

<div align='center'>

<sub>Figura 1 - Persona: Mariana Silva, Especialista de Políticas de Crédito</sub>

![Persona Mariana Silva](./assets/persona_mariana_silva.png)

<sup>Fonte: Material produzido pelos autores (2026)</sup>

</div>

&emsp; Mariana Silva, 32 anos, é Especialista de Políticas de Crédito e atua como a usuária principal da solução, sendo a responsável direta por validar e aplicar as regras de negócio de limite de crédito de forma autônoma. Atualmente, ela sofre com um gargalo de tempo considerável em sua rotina, dependendo inteiramente do time de Data Science (José) para testar o impacto de novos parâmetros que deseja aplicar. Em sua integração com o ecossistema, Mariana atua como a guardiã do risco e da rentabilidade: é o trabalho dela que define e afina as "travas" matemáticas projetadas por José, garantindo que o limite de fato entregue na ponta obedeça fielmente às diretrizes do banco e resguarde a segurança da carteira, permitindo assim uma oferta de limite mais precisa e saudável para Rodrigo, o cliente final.

### 3.2 Persona 2 — [José Lopez, Diretor de Data Science]

<div align='center'>

<sub>Figura 2 - Persona: José Lopez, Diretor de Data Science</sub>

![Persona José Lopez](./assets/persona_jose_lopez.png)

<sup>Fonte: Material produzido pelos autores (2026)</sup>

</div>

&emsp; José Lopez, 35 anos, Diretor de Data Science, atua como o alicerce técnico e estratégico da solução, sendo o responsável pela integração da modelagem matemática e atestar sua eficiência. Suas maiores dores residem na exaustão operacional que surge ao tentar explicar decisões tomadas em um modelo sem base comparativa sólida e na frequente interrupção de sua rotina técnica para rodar cenários sob demanda para o time de negócios (equipe de Mariana). Em relação à integração do ecossistema, José complementa Mariana desenvolvendo todo o "motor" seguro e documentado, reduzindo dessa forma o seu trabalho manual, para que ela não dependa do time técnico na tomada de decisões diárias.

### 3.3 Persona 3 — [Rodrigo Santos, Cliente do banco Pan]

<div align='center'>

<sub>Figura 3 - Persona: Rodrigo Santos, Cliente do Banco Pan</sub>

![Persona Rodrigo Santos](./assets/persona_rodrigo_santos.png)

<sup>Fonte: Material produzido pelos autores (2026)</sup>

</div>

&emsp; Rodrigo Santos, 28 anos, representa o cliente correntista do Banco Pan e a ponta final deste fluxo, recebendo diretamente as consequências da operação definida por José (Data Science) e operada por Mariana (Políticas de Crédito). Suas principais dores relacionam-se aos extremos gerados por modelos empíricos ou de "achismo" não parametrizáveis: limites excessivamente generosos que o induzem ao superendividamento ou ofertas baixas que o impedem de efetuar compras maiores. Na interação do ciclo, o Rodrigo valida o quão eficazes foram as decisões de Mariana na ferramenta de otimização desenvolvida por José, transformando a precisão metodológica do modelo, por fim, em melhor experiência e segurança financeira de forma responsável para o usuário em sua jornada diária com o cartão.

### 3.4 Conclusão

&emsp; Em suma, as três personas operam em uma engrenagem iterativa que valida a necessidade e o impacto da solução. O fluxo inicia-se com José Lopez (Data Science) arquitetando o "motor" matemático que garante o rigor científico e metodológico do modelo. Mariana Silva (Políticas de Crédito), como usuária principal, assume o controle desse motor por meio da ferramenta, aplicando parâmetros e restrições de negócio de forma totalmente autônoma. Essa autonomia quebra definitivamente o ciclo de dependência técnica: José é liberado da execução de cenários operacionais exaustivos sob demanda, enquanto Mariana ganha agilidade para aprovar limites e auditar o risco de forma independente. Como consequência direta da fluidez dessa dinâmica interna, Rodrigo Santos (Cliente) recebe na ponta limites de crédito otimizados, precisos e condizentes com seu perfil de risco, promovendo sua inclusão financeira segura e consolidando os objetivos estratégicos do Banco.

---

## 4. User Stories

&emsp; As User Stories conseguem traduzir ações específicas que precisam cumprir na solução, dada alguma necessidade/dor. Elas se tornam essenciais no Entendimento da Experiência do Usuário ao permitir uma validação de dores e necessidades que fazem sentido em relação à solução do problema, seguindo as boas práticas no formato INVEST que amplia a qualidade destas histórias. O acrônimo I.N.V.E.S.T. (Independente, Negociável, Valiosa, Estimável, Pequena e Testável) resumi-se à um framework que auxilia na estruturação das User Stories (Bonilha, Diego; 2020).

| # | User Story | Persona | Dor atendida | Critérios de aceite |
|---|------------|---------|--------------|---------------------|
| US01 | Como Especialista de Políticas de Crédito, eu quero ajustar parâmetros de política de limite (multiplicadores de alavancagem, limite máximo por faixa de risco, restrições de capacidade de pagamento) e visualizar imediatamente o impacto resultante em métricas de risco e negócio, para validar novas políticas de forma autônoma, reduzindo o tempo de validação de semanas para horas e eliminando a dependência de requisições ao time de Data Science. | Mariana Silva | Dependência operacional de Data Science para cada teste de cenário, gerando atrasos de dias a semanas. | Interface permite ajustar multiplicadores por faixa de PD sem intervenção técnica; visualização imediata do impacto em inadimplência física, financeira, volume e retorno; comparação lado a lado entre cenário ajustado e baseline; possibilidade de salvar cenários para auditoria; histórico de testes registrado para rastreabilidade. |
| US02 | Como Especialista de Políticas de Crédito, eu quero comparar as recomendações de limite geradas pela solução linear com as recomendações do modelo não-linear atualmente em produção, identificando convergências e divergências entre os dois algoritmos, para fundamentar decisões de limite com mais robustez técnica perante a liderança, baseando-me em duas fontes de validação independentes em vez de confiar em um único modelo. | Mariana Silva | Dificuldade em validar decisões do modelo atual de forma independente; confia em um único algoritmo sem mecanismo de validação cruzada. | Plataforma permite importar resultados do modelo não-linear para mesma safra; comparação visual lado a lado das recomendações por cliente/segmento; identificação automática de divergências significativas (diferença superior a 10%); análise por segmento mostrando convergências e divergências com possíveis causas; geração de relatório executivo de validação dual para apresentação à liderança. |
| US03 | Como Especialista de Políticas de Crédito, eu quero que todas as ofertas de limite geradas respeitem automaticamente as regras obrigatórias do banco (limite mínimo de R$200, múltiplos de R$50, restrições de alavancagem por segmento) e visualizar relatórios de conformidade em dashboard, para eliminar a auditoria manual exaustiva atualmente necessária para validar regras básicas, garantindo 100% de conformidade sem esforço operacional repetitivo. | Mariana Silva | Auditoria manual exaustiva para verificar conformidade com regras básicas de negócio em ofertas geradas. | Modelo aplica automaticamente regras obrigatórias durante a otimização (não em pós-processamento); dashboard mostra percentual de conformidade em tempo real para cada regra; relatório identifica clientes rejeitados por violação de cada restrição específica; possibilidade de editar regras de conformidade com preview de impacto; relatório de conformidade exportável para auditoria interna em formato padronizado. |
| US04 | Como Especialista de Políticas de Crédito, eu quero criar e armazenar múltiplos cenários de política (ex: cenário conservador, agressivo, balanceado) com diferentes configurações de parâmetros, e compará-los lado a lado em métricas-chave, para apresentar opções fundamentadas à liderança executiva com suporte quantitativo claro, facilitando tomada de decisão estratégica sobre direcionamento de política de crédito. | Mariana Silva | Necessidade de fundamentação técnica robusta para defender decisões de limite perante liderança executiva, com comparação clara de alternativas. | Plataforma permite criar e nomear múltiplos cenários (ex: "Conservador_2026", "Agressivo_Volume"); cada cenário armazena parâmetros configurados, métricas resultantes e validação cruzada com modelo não-linear; visualização comparativa entre até quatro cenários simultaneamente com métricas principais destacadas; geração de relatório executivo com gráficos comparativos, trade-offs e recomendação fundamentada; possibilidade de marcar cenário como "Recomendado" com justificativa documentada; histórico de cenários comparados registrado para rastreabilidade. |
| US05 | Como Especialista de Políticas de Crédito, eu quero monitorar continuamente o desempenho da política implementada em produção através de dashboard com métricas-chave (inadimplência real versus projetada, volume aprovado, taxa de aceitação, conformidade) atualizadas por safra, para identificar desvios em relação ao esperado e tomar decisões corretivas rápidas antes que problemas se materializem na carteira. | Mariana Silva | Falta de visibilidade contínua sobre desempenho real das políticas implementadas, dificultando ajustes proativos quando há desvios. | Dashboard exibe métricas de risco e negócio atualizadas por safra; comparação automática entre projetado e realizado para inadimplência física, financeira, volume e retorno; alertas configuráveis quando métricas saem de bounds esperados (ex: inadimplência real 20% acima da projetada); drill-down por segmento de risco para identificar onde estão os desvios; histórico de safras anteriores disponível para análise de tendência; integração com cockpit operacional para ajustes rápidos de política caso desvios sejam identificados. |---

## 5. Jornada do Usuário (Persona: José Lopez)

&emsp; A Jornada do Usuário é uma ferramenta de design que mapeia, de forma cronológica, as etapas percorridas por uma persona ao interagir com um sistema, produto ou processo; registrando suas ações, pensamentos e estados emocionais em cada fase. Mais do que descrever o que o usuário faz, a jornada evidencia onde estão os pontos de dor, os gargalos operacionais e as oportunidades de melhoria, tornando visível a experiência real do usuário antes e depois da solução (KALBACH, 2016).
Neste projeto, foram mapeadas duas jornadas complementares para José Lopez, Diretor de Data Science do Banco Pan: a jornada antes da solução, que expõe as limitações do processo atual de auditoria e análise de limites de crédito, e a jornada com a solução, que demonstra como o modelo de otimização transforma sua rotina ao fornecer uma base comparativa estruturada e reduzir a dependência de análises manuais.

### 5.1. Jornada do Usuário Atual José

<div align='center'>

<sub>Figura 4 - Jornada do usuário atual/sub>

![Jornada do Usuário pré solução](./assets/jornada_usuario_atual.png)

<sup>Fonte: Material produzido pelos autores (2026)</sup>

</div>

&emsp; A jornada anterior à solução revela uma rotina marcada por retrabalho e falta de embasamento formal. Sem uma referência comparativa ao algoritmo vigente, José não consegue responder com segurança se os limites concedidos pelo modelo atual são ótimos, toda análise parte do zero. Solicitações do time de Políticas de Crédito interrompem seu fluxo de trabalho, e apresentações à liderança carecem de sustentação matemática. A curva emocional oscila entre frustração, incerteza e bloqueio, refletindo um processo que depende mais de esforço individual do que de estrutura técnica.

### 5.2. Jornada do Usuário Futura José

<div align='center'>

<sub>Figura 5 - Jornada do usuário depois da futura</sub>

![Jornada do Usuário pós solução](./assets/jornada_usuario_futura.png)

<sup>Fonte: Material produzido pelos autores (2026)</sup>

</div>

&emsp; Com o modelo de otimização em operação, a jornada de José se torna estruturada e orientada por dados. Ele passa a receber outputs comparáveis ao algoritmo atual, identificar divergências com embasamento técnico e apresentar resultados auditáveis à liderança sem depender de análises pontuais sob demanda. Quando Mariana, do time de Políticas de Crédito, aciona José com dúvidas sobre o modelo, ele consegue explicar a decisão com base nas restrições aplicadas, sem precisar alterar o código. A curva emocional evolui de confiança para satisfação e alívio, indicando que a solução não apenas resolve os pontos de dor anteriores, mas também amplia a autonomia técnica do time.

### 5.3. Jornada do Usuário Mariana

<div align='center'>

<sub>Figura 6 - Jornada do usuário Mariana</sub>

![Jornada do Usuário Mariana](./assets/jornada_usuario_mariana.png)

<sup>Fonte: Material produzido pelos autores (2026)</sup>

</div>

&emsp; Com o modelo de otimização em operação, a jornada de Mariana se torna autônoma e orientada por validação cruzada. Ela passa a testar cenários de política diretamente na nova plataforma operacional, ajustando parâmetros e visualizando impacto em tempo real, sem precisar acionar o time de Data Science a cada novo teste. Quando recebe demandas da liderança para validar propostas de ajuste, Mariana consegue cruzar as recomendações da solução linear com o algoritmo não-linear em produção, identificando convergências e divergências por segmento e fundamentando suas decisões em duas fontes de validação independentes. A conformidade com regras obrigatórias do banco (R$200 mín, múltiplos de R$50, restrições de alavancagem) é garantida automaticamente, eliminando o esforço de auditoria manual. A curva emocional evolui de confiança para determinação e alívio, indicando que a solução não apenas resolve a dependência operacional anterior, mas também fortalece a fundamentação técnica das decisões de política de crédito.

### 5.3 Conclusão

&emsp; A comparação entre as duas jornadas deixa evidente o papel central que o modelo de otimização exerce na rotina de José Lopez. A solução não substitui o algoritmo já em produção, mas fornece a ele algo que antes não existia: uma referência objetiva, matematicamente documentada, para questionar e aprimorar continuamente as decisões de concessão de crédito. Ao eliminar análises manuais, reduzir o gargalo técnico entre Data Science e Políticas de Crédito e tornar as decisões de limite rastreáveis e defensáveis, a solução transforma uma prática empírica em um processo científico, sistemático e escalável, alinhado às metas estratégicas do Banco Pan.

---

## 6. Referências

BANCO PAN. **Documento TAPI: Definição Ótima de Limites Pré-aprovados de Crédito**. São Paulo: Banco Pan, 2026. Documento interno compartilhado com os desenvolvedores.

BONILHA, Diego. **User Stories e o formato INVEST**. 2020. Disponível em fontes técnicas de metodologias ágeis. Acesso em: 29 abr. 2026.

COOPER, Alan; REIMANN, Robert; CRONIN, David; NOESSEL, Christopher. **About Face: The Essentials of Interaction Design**. 4. ed. Indianápolis: John Wiley & Sons, 2014.

KALBACH, James. **Mapping Experiences: A Complete Guide to Creating Value through Journeys, Blueprints, and Diagrams**. 1. ed. Sebastopol: O'Reilly Media, 2016.

PRUITT, John; ADLIN, Tamara. **The Persona Lifecycle: Keeping People in Mind Throughout Product Design**. São Francisco: Morgan Kaufmann, 2006.
