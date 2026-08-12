# Diagrama de Casos de Uso — Requisitos Funcionais

&emsp;O diagrama de casos de uso representa, em notação UML, os requisitos funcionais descritos em [requisitos.md](./requisitos.md). Ele mostra quem interage com a plataforma (atores), quais serviços o sistema oferece (casos de uso) e como esses serviços se relacionam entre si. O arquivo editável está em `assets/diagrama_casos_de_uso.drawio` e pode ser aberto no [diagrams.net](https://app.diagrams.net).

<div align="center">

<sub>Figura 1 - Diagrama de casos de uso dos requisitos funcionais</sub>

![Diagrama de casos de uso](./assets/diagrama_casos_de_uso.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp;A disposição segue dois blocos. No bloco superior, o ator emissor aparece à esquerda e os casos de uso executados como parte da ingestão ficam à direita do caso de uso base. No bloco inferior, os casos de uso iniciados pelos usuários ficam próximos aos atores, e os casos auxiliares foram deslocados para a coluna da esquerda. As associações dos atores humanos são roteadas por um corredor vertical à direita da fronteira do sistema, de modo que nenhuma linha atravesse um caso de uso ao qual não pertence.

## Atores

| Ator | Tipo | Papel no sistema |
|---|---|---|
| Aplicação frontend do Globoplay | Sistema externo | Emite os eventos de telemetria. Representa o conjunto das plataformas em que o Globoplay está presente, sem enumerá-las, uma vez que cada uma pode apresentar falhas próprias e a lista definitiva ainda será priorizada com o parceiro. |
| Usuário do dashboard | Ator generalizado | Reúne o comportamento de consulta e análise comum aos dois perfis operacionais. Não é instanciado diretamente. |
| Engenheiro de Observabilidade | Ator especializado | Investiga padrões de falha, acompanha limites de confiabilidade e compara períodos. |
| Analista de Suporte N2 | Ator especializado | Faz a triagem de chamados a partir dos eventos registrados. |

&emsp;O ator "Aplicação frontend do Globoplay" foi mantido genérico de forma proposital. O RF02 e o RF03 tratam de plataformas e protocolos diversos, incluindo dispositivos legados, e enumerar categorias no diagrama daria a impressão de um escopo fechado. A definição das plataformas e dos protocolos priorizados para o MVP é registrada nos próprios requisitos e validada com o parceiro.

## Relação entre os atores e as personas

&emsp;Os atores do diagrama derivam diretamente das personas definidas em [entendimento_ux.md](./entendimento_ux.md). A correspondência é a seguinte:

| Persona | Relação com a solução | Ator correspondente | Casos de uso associados |
|---|---|---|---|
| Rafael Santos — engenheiro de observabilidade | Usuário direto (persona principal) | Engenheiro de Observabilidade | Todos os casos do "Usuário do dashboard", além de comparar períodos (RF14), acompanhar picos de erro e latência (RF15) e consultar hipóteses de causa raiz (RF17) |
| Mariana Souza — analista de suporte N2 | Usuária direta (operacional) | Analista de Suporte N2 | Casos herdados do "Usuário do dashboard": consultar eventos (RF08), agrupar (RF11), dashboard (RF12), falhas críticas (RF13) e investigar problema (RF16) |
| Luísa Silva dos Santos — assinante do Globoplay | Usuária indireta | Não é modelada como ator | Nenhum |

&emsp;Luísa não aparece como ator porque não interage com a plataforma. Em UML, um ator representa quem troca informação com o sistema, e a relação de Luísa é de benefício indireto: seus eventos chegam pelo ator "Aplicação frontend do Globoplay" e o resultado da investigação se traduz em correções no dispositivo dela. Representá-la como ator sugeriria uma interação que não existe.

&emsp;A distinção entre os dois atores diretos segue a diferença registrada nas User Stories: as histórias US01 a US05, de Rafael, tratam de cobertura, confiabilidade da ingestão e definição de limites de confiabilidade; as histórias US06 a US08, de Mariana, tratam de triagem por sessão, dispositivo e região. Como ambas partem das mesmas consultas ao dashboard, a generalização evita repetir as mesmas associações duas vezes.

&emsp;O perfil de produto, citado no documento de requisitos como um dos públicos do dashboard, não foi modelado como ator porque não possui persona correspondente no entendimento de UX. Caso venha a ser considerado um usuário do MVP, será necessário criar a persona antes de incluí-lo no diagrama.

## Rastreabilidade entre casos de uso e requisitos

| Caso de uso | Ator ou caso de uso de origem | Requisitos atendidos |
|---|---|---|
| Enviar evento de telemetria | Aplicação frontend do Globoplay | RF01, RF02, RF03, RF07 |
| Validar campos mínimos do evento | «include» de "Enviar evento de telemetria" | RF04 |
| Normalizar evento em formato comum | «include» de "Enviar evento de telemetria" | RF05 |
| Armazenar evento processado | «include» de "Enviar evento de telemetria" | RF06 |
| Consultar eventos por tipo, período e atributos | Usuário do dashboard | RF08 |
| Aplicar filtros cumulativos | «include» de "Consultar eventos" | RF09 |
| Sugerir valores existentes nos filtros | «extend» de "Aplicar filtros cumulativos" | RF10 |
| Agrupar eventos por critério | Usuário do dashboard | RF11 |
| Visualizar dashboard de gráficos e indicadores | Usuário do dashboard | RF12 |
| Consultar falhas críticas | Usuário do dashboard | RF13 |
| Investigar problema com dados de contexto | Usuário do dashboard | RF16 |
| Consultar hipóteses de causa raiz | «extend» de "Investigar problema" | RF17 |
| Comparar período atual com período anterior | Engenheiro de Observabilidade | RF14 |
| Acompanhar picos de erro e latência | Engenheiro de Observabilidade | RF15 |

&emsp;Todos os requisitos funcionais de RF01 a RF17 estão representados. O diagrama contempla apenas os requisitos funcionais: os requisitos não funcionais descrevem qualidades do sistema, e não serviços oferecidos aos atores, de modo que sua verificação permanece nos planos de teste do documento de requisitos.

## Convenções adotadas

- **«include»** indica um comportamento sempre executado como parte do caso de uso base. É o caso da validação, da normalização e do armazenamento, que ocorrem em toda ingestão de evento.
- **«extend»** indica um comportamento opcional, executado apenas em determinadas condições. Foi aplicado ao RF10 (sugestão de valores) e ao RF17 (hipóteses de causa raiz).
- O RF17 aparece com contorno tracejado por ser tratado como possível evolução, conforme registrado em [requisitos.md](./requisitos.md), e depende de validação com o parceiro.
