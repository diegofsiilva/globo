# Requisitos Funcionais, Não Funcionais e Restrições do Projeto

&emsp;A definição de requisitos representa uma etapa importante para transformar as necessidades apresentadas pelo parceiro em características que possam orientar o desenvolvimento e, posteriormente, ser verificadas pela equipe. No projeto de Monitoração Agêntica, esse entendimento foi construído a partir da análise do TAPI e das conversas realizadas com representantes do Grupo Globo durante o kick-off e os primeiros alinhamentos.

## Requisitos funcionais

&emsp;Segundo o livro [Engenharia de Software Moderna](https://engsoftmoderna.info/cap3.html), os requisitos funcionais descrevem os serviços que um sistema deve oferecer, isto é, as funcionalidades que estarão disponíveis para seus usuários ou para outros sistemas. Neste projeto, eles representam as ações necessárias para receber, tratar, armazenar e consultar os eventos de telemetria gerados pelas aplicações frontend do Globoplay.

&emsp;A tabela a seguir apresenta os requisitos funcionais identificados. A coluna **Evidência** relaciona cada requisito às necessidades levantadas junto ao parceiro, enquanto a coluna **Fonte da evidência** indica onde essa necessidade foi registrada ou discutida.


| Requisito funcional | Descrição | Evidência | Fonte da evidência |
|---|---|---|---|
| RF01 | O sistema deve receber eventos de telemetria por meio de uma API única de ingestão. | O MVP deve possuir um ponto unificado para o recebimento dos eventos. | TAPI |
| RF02 | O sistema deve receber eventos originados de diferentes plataformas, como TVs, dispositivos móveis e aplicações web. | O Globoplay está presente em diferentes plataformas e dispositivos. | TAPI e kick-off |
| RF03 | O sistema deve receber eventos provenientes dos protocolos modernos e legados selecionados pelo parceiro para o MVP. | Parte dos dispositivos utilizados não suporta os padrões modernos de coleta de telemetria. | TAPI e kick-off |
| RF04 | O sistema deve verificar se os eventos recebidos possuem as informações mínimas esperadas para o seu tipo. | Os dados precisam estar adequados antes de serem armazenados e analisados. | Elicitação com o parceiro |
| RF05 | O sistema deve padronizar os eventos recebidos em um formato comum. | O MVP prevê a normalização mínima dos eventos provenientes de diferentes dispositivos. | TAPI |
| RF06 | O sistema deve armazenar os eventos processados para permitir consultas e análises posteriores. | O MVP prevê um fluxo de ingestão e armazenamento de eventos em escala. | TAPI e kick-off |
| RF07 | O sistema deve coletar, no mínimo, eventos dos tipos `request`, `vitals`, `screen_view`, `video_view`, `session` e `error`. | Esses foram os eventos mínimos definidos para o MVP. | TAPI |
| RF08 | O sistema deve permitir a pesquisa de eventos por tipo, período e demais informações disponíveis sobre a aplicação ou o dispositivo. | Os usuários precisam localizar eventos específicos para investigar falhas. | Elicitação com o parceiro |
| RF09 | O sistema deve permitir a utilização de mais de um filtro em uma mesma consulta. | O dashboard deve possuir filtros cumulativos. | TAPI |
| RF10 | O sistema deve sugerir valores existentes nos dados durante o preenchimento dos filtros. | O MVP prevê sugestão de valores recebidos nos filtros. | TAPI |
| RF11 | O sistema deve permitir o agrupamento de eventos por critérios disponíveis, como tipo, período, plataforma ou região. | O agrupamento facilita a análise da frequência e da distribuição dos eventos. | Elicitação com o parceiro |
| RF12 | O sistema deve apresentar gráficos e indicadores construídos a partir dos eventos coletados. | O MVP prevê um dashboard para navegação pelos dados e gráficos dos eventos. | TAPI |
| RF13 | O sistema deve disponibilizar consultas simples para análise das falhas consideradas críticas pelo parceiro. | A consulta de falhas críticas faz parte do escopo mínimo do projeto. | TAPI |
| RF14 | O sistema deve permitir a comparação entre eventos e métricas do período atual e de um período anterior selecionado. | A comparação histórica pode ajudar a reconhecer mudanças no comportamento da aplicação. | Elicitação com o parceiro |
| RF15 | O sistema deve destacar aumentos relevantes na ocorrência de eventos, como picos de erros ou de latência, segundo critérios definidos com o parceiro. | Os times precisam perceber com clareza os problemas que estão ocorrendo no momento. | Elicitação com o parceiro |
| RF16 | O sistema deve exibir informações que auxiliem a investigação de um problema, como tipo de evento, período, quantidade de ocorrências e dispositivos relacionados. | O sistema deve contribuir para a identificação de padrões e para a análise de falhas. | TAPI e elicitação com o parceiro |
| RF17 | O sistema poderá apresentar possíveis causas para um problema, ordenando as hipóteses por relevância e indicando os dados que contribuíram para a análise. | Durante a elicitação, foi levantada a possibilidade de apoiar a identificação da causa raiz por meio de hipóteses. | Elicitação com o parceiro |

&emsp;Os requisitos RF01 a RF13 estão diretamente relacionados ao escopo mínimo apresentado no TAPI. Os requisitos RF14 a RF16 complementam a experiência de análise discutida durante a elicitação. Já o RF17 deve ser tratado inicialmente como uma possível evolução, pois depende da quantidade e da qualidade dos dados coletados e ainda precisa ser validado com o parceiro. Caso seja implementado, suas hipóteses deverão apoiar a investigação humana, sem serem apresentadas como conclusões definitivas.

## Requisitos não funcionais

&emsp;Ainda conforme o livro [Engenharia de Software Moderna](https://engsoftmoderna.info/cap3.html), os requisitos não funcionais estabelecem características de qualidade e restrições sobre o funcionamento do sistema. Eles não descrevem uma funcionalidade isolada, mas definem condições importantes para que as funcionalidades sejam utilizadas de forma adequada.

&emsp;Os requisitos abaixo foram organizados de acordo com características de qualidade presentes na norma ISO/IEC 25010. As metas numéricas já discutidas pela equipe foram mantidas, enquanto definições ainda não fornecidas pelo parceiro foram registradas de maneira mais aberta para evitar compromissos que não tenham sido validados.

| Requisito não funcional | Descrição | Aspecto de qualidade relacionado à ISO 25010 | Fonte da evidência |
|---|---|---|---|
| RNF01 | A API de ingestão deve processar, inicialmente, pelo menos 1.000 requisições por minuto em condições normais de operação. | Eficiência de desempenho - capacidade | Definição inicial da equipe |
| RNF02 | Consultas simples realizadas no dashboard sobre dados já processados devem apresentar o resultado em até 3 segundos. | Eficiência de desempenho - comportamento em relação ao tempo | Definição inicial da equipe |
| RNF03 | A solução deve permitir o aumento gradual de sua capacidade de ingestão e processamento sem alterar a forma como os sistemas enviam eventos. | Flexibilidade - escalabilidade | TAPI |
| RNF04 | Um evento inválido não deve impedir o recebimento dos eventos válidos seguintes, e sua falha deve ser identificável. | Confiabilidade - tolerância a falhas | TAPI e elicitação com o parceiro |
| RNF05 | Após uma falha temporária, o sistema deve voltar a receber e processar novos eventos sem perder silenciosamente os eventos que já tenham sido aceitos. | Confiabilidade - recuperabilidade | TAPI |
| RNF06 | A API deve receber eventos das plataformas e dos protocolos modernos e legados selecionados pelo parceiro para o MVP. | Compatibilidade - interoperabilidade | TAPI e kick-off |
| RNF07 | Os usuários devem conseguir localizar eventos, aplicar filtros e interpretar os principais gráficos sem orientação técnica detalhada. | Capacidade de interação - operabilidade | TAPI e elicitação com o parceiro |
| RNF08 | Caso sejam apresentadas hipóteses, o sistema deve indicar os eventos ou métricas que justificam a relação sugerida com o problema. | Capacidade de interação - reconhecibilidade da adequação | Elicitação com o parceiro |
| RNF09 | O acesso às consultas e aos dados deve ser permitido apenas a usuários ou serviços autorizados. | Segurança - confidencialidade e autenticidade | Necessidade identificada pela equipe |
| RNF10 | Os eventos devem conter apenas as informações necessárias para a monitoração e não devem expor dados pessoais desnecessários no dashboard. | Segurança - confidencialidade | Necessidade identificada pela equipe |
| RNF11 | O sistema deve registrar informações suficientes sobre falhas de ingestão e processamento para apoiar sua investigação. | Capacidade de manutenção - analisabilidade | Objetivo do projeto e elicitação com o parceiro |
| RNF12 | Eventos equivalentes enviados por plataformas diferentes devem resultar em informações padronizadas e comparáveis após o processamento. | Adequação funcional - correção funcional | TAPI |

## Planos de teste dos requisitos não funcionais

&emsp;Os planos de teste a seguir apresentam uma forma inicial de verificar cada requisito não funcional. As condições de infraestrutura, o volume representativo de dados e os protocolos utilizados deverão ser refinados conforme o desenvolvimento do MVP.

