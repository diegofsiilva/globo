# Entendimento do Negócio

## 1. Matriz de Avaliação de Valor (Oceano Azul)

### 1.1. Contexto da comparação

&emsp; O projeto responde a uma pergunta específica: como identificar de forma automática, em minutos, a causa provável de uma degradação de streaming, sem depender de um especialista por componente. A matriz compara três formas de responder a ela.

&emsp; **Prática atual: monitoração em silos com triagem humana.** Cada componente da cadeia de entrega (player, CDN, backend, identidade, catálogo) é operado por uma área distinta, com painel, vocabulário de métricas e especialistas próprios. O incidente percorre uma fila por vez até alguém identificar o responsável, e a correlação entre fontes é feita manualmente. Não custa nada implantar, porque já existe, mas cobra caro por incidente.

&emsp; **Consolidação em uma suíte de observabilidade de mercado.** Uma plataforma comercial de APM e Real User Monitoring reúne as fontes em um painel único, com alertas por limiar e detecção de anomalia. Reduz a fragmentação, mas parte de duas premissas frágeis neste contexto: base de dispositivos homogênea e compatível com padrões modernos de coleta, e cobrança proporcional ao volume e à cardinalidade dos dados observados.

&emsp; **Solução proposta pelo grupo.** Sistema distribuído proprietário de telemetria, com API única de ingestão que aceita protocolos modernos e legados, normalização dos eventos sob vocabulário comum (`request`, `vitals`, `screen_view`, `video_view`, `session`, `error`), pipeline de alta escala sem perdas e camada agêntica de correlação, que devolve uma linha do tempo única do incidente e uma hipótese de causa provável ranqueada, com o recorte afetado explícito.

&emsp; A matriz avalia as abordagens de solução, e não o Globoplay. Características do produto e da audiência entram como justificativa do valor de cada atributo, não como objeto de avaliação.

### 1.2. Escala e critérios de atribuição das notas

&emsp; As notas vão de 1 (baixa entrega de valor) a 5 (alta entrega de valor para o Grupo Globo). Para reduzir subjetividade, foram atribuídas segundo cinco critérios:

- Aderência ao problema: a abordagem produz hipótese, recorte e linha do tempo, ou apenas mais dados?
- Cobertura da superfície de falha: enxerga a combinação de plataforma, modelo, versão, UF e operadora em que o problema se manifesta?
- Impacto no tempo de resolução, medido entre o sintoma e a hipótese acionável.
- Custo humano por incidente, em horas de especialista, reunião e plantão.
- Viabilidade operacional, incluindo esforço de implantação e robustez sob evento ao vivo.

&emsp; No atributo 8 a escala foi invertida em relação ao esforço: nota alta significa menor esforço de implantação e menor custo de propriedade. Sem essa inversão, o eixo seria lido em sentido contrário aos demais e a curva perderia consistência.

### 1.3. Matriz de avaliação de valor

| Atributo de valor para o Grupo Globo                       | Prática atual (silos + triagem humana) | Suíte de observabilidade de mercado | Solução proposta pelo grupo | Justificativa das notas                                                                                                                                                                                                                                                                                                                                                                             |
| ---------------------------------------------------------- | -------------------------------------: | ----------------------------------: | --------------------------: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. Tempo até a hipótese de causa provável                  |                                      1 |                                   3 |                           5 | Hoje o tempo de resolução é a soma das filas: gasta-se mais para descobrir quem conserta do que para consertar. A suíte comercial encurta o caminho ao reunir sinais em um painel, mas ainda entrega gráficos que alguém precisa interpretar. Só a solução proposta tem como produto final uma hipótese ranqueada, e não um conjunto de séries temporais.                                           |
| 2. Correlação ponta a ponta em uma linha do tempo única    |                                      1 |                                   3 |                           5 | A experiência do assinante é ponta a ponta, mas a observabilidade não é: nenhum painel atual acompanha a jornada inteira do play. A suíte comercial resolve isso quando todas as fontes são de fato integradas, o que raramente se completa numa cadeia com mais de dez fontes heterogêneas. A solução proposta faz o agrupamento por filtros, que proporciona o olhar de uma linha do tempo única. |
| 3. Detecção de degradação que não gera erro                |                                      2 |                                   3 |                           5 | Buffer alto e tempo de início ruim não produzem taxa de erro, e o painel tradicional não acende. Ferramentas de mercado detectam anomalia, mas sobre métricas agregadas, em que a degradação de um recorte se dilui. A solução proposta parte de eventos de QoE coletados no cliente, em que o sintoma percebido pelo assinante é o próprio dado primário.                                          |
| 4. Granularidade nos recortes de investigação              |                                      2 |                                   2 |                           5 | Uma falha que atinge meio por cento das sessões pode ser a totalidade das sessões de um modelo de TV numa região. A prática atual dilui isso na média nacional. A suíte comercial é penalizada pelo próprio modelo de cobrança: cada dimensão adicional vira custo e empurra o time de volta ao agregado. Na solução proposta, a granularidade é decidida pela necessidade analítica.               |
| 5. Cobertura da base real de dispositivos e protocolos     |                                      2 |                                   2 |                           5 | Sete plataformas e centenas de modelos convivem no parque, e parte relevante deles não suporta os padrões modernos de coleta que as plataformas de mercado assumem. Nem a prática atual nem a suíte resolvem isso, porque a limitação está na borda e não no backend. A API única multiprotocolo ataca a causa do ponto cego.                                                                       |
| 6. Independência de especialista e custo humano da triagem |                                      1 |                                   3 |                           4 | Hoje o diagnóstico vira reunião: como nenhum time enxerga o todo, a correlação exige uma sala de especialistas, o recurso mais caro da casa gasto em triagem. Um painel unificado reduz parte disso. A nota 4 da solução proposta reconhece que a hipótese automática ainda dependerá de validação humana enquanto não houver histórico suficiente para calibrar sua confiabilidade.                |
| 7. Sustentação sob pico de evento ao vivo                  |                                      3 |                                   4 |                           3 | Aqui a solução proposta não é superior. A prática atual, embora lenta, sobrevive a picos porque não depende de infraestrutura nova. As suítes comerciais operam infraestrutura endurecida por anos de produção. A solução proposta precisa demonstrar ingestão sem perdas em cenários de milhões de sessões simultâneas, e essa capacidade ainda é hipótese de engenharia.                          |
| 8. Baixo esforço de implantação e custo de propriedade     |                                      5 |                                   3 |                           2 | A prática atual não custa nada para implantar, por definição. Consolidar em suíte comercial é um projeto de migração relevante, com custo recorrente proporcional ao volume. Construir plataforma própria é a alternativa mais cara em desenvolvimento, operação e plantão, e cria um sistema que passa a precisar ele próprio de monitoração.                                                      |

![Gráfico da matriz de avaliação de valor](../assets/oceano-azul.svg)

<figcaption style="text-align: center;">
 Figura 1: Curva de valor da matriz
</figcaption>

### 1.4. Leitura estratégica da matriz

&emsp; A curva da solução proposta concentra valor nos cinco primeiros atributos, que traduzem o problema a resolver, e aceita ser pior nos dois últimos, que dizem respeito a conveniência e maturidade.

&emsp; O cruzamento entre os atributos 4 e 8 resume o dilema. Nas suítes comerciais, granularidade e custo são grandezas acopladas: observar cada combinação de modelo, firmware, UF e operadora aumenta a fatura, o que leva o time a agregar métricas e a perder justamente o sinal de que precisa. A solução proposta desacopla parcialmente essas dimensões e paga por isso em custo de construção. A escolha é entre pagar em licença e perder granularidade, ou pagar em engenharia e ganhá-la.

&emsp; A prática atual tem uma leitura própria que costuma passar despercebida. Ela pontua alto só no atributo 8, e de forma enganosa: custo zero de implantação convive com custo altíssimo por incidente, concentrado em horas de especialista e em tempo de assinante impactado. Esse custo é real e não aparece em nenhuma linha de orçamento de ferramenta.

### 1.5. Trade-offs explícitos da solução proposta

&emsp; Os principais trade-offs assumidos são:

- Uma causa provável errada durante um evento ao vivo é pior do que hipótese nenhuma, porque direciona o esforço da equipe para o componente errado no pior momento. A saída precisa vir ranqueada e com evidência auditável, e sua qualidade depende de um histórico de incidentes rotulados que talvez ainda não exista em volume suficiente.
- A camada de inferência só gera valor sobre eventos confiáveis. Investir na inteligência antes de estabilizar ingestão e olhar para os eventos corretos produziria diagnóstico automático sobre dado incompleto, resultado pior do que a triagem manual de hoje.
- Ao internalizar a telemetria, o Globoplay passa a depender de um sistema que precisa estar disponível exatamente quando a operação está sob estresse. A indisponibilidade da plataforma de monitoração durante uma transmissão de alta audiência é um modo de falha que não existia enquanto o serviço era terceirizado.
- Armazenar eventos por dispositivo, versão, UF e operadora em alta escala continua caro, e a política de retenção e amostragem terá de ser decisão explícita de projeto, sob o risco de reproduzir internamente o mesmo incentivo a observar menos.

### 1.6. Evidências que reforçam a comparação

&emsp; **Contexto do produto.** Cerca de um em cada dez brasileiros acessa o Globoplay, com picos que chegam a 4,1 milhões de sessões em um único evento ao vivo. O produto é entregue em sete plataformas, sobre centenas de modelos de dispositivo, distribuídos por 27 unidades federativas e dezenas de provedores de acesso. A cadeia de entrega envolve mais de treze fontes de dados, produzidas por áreas diferentes, com formatos e janelas de agregação diferentes, e todas precisam ser lidas em conjunto para explicar um único play que deu errado. É esse espaço de busca que torna a varredura manual inviável em plantão.

&emsp; **Impacto econômico da degradação silenciosa.** O estudo de Krishnan e Sitaraman, apresentado no Internet Measurement Conference de 2012 sobre 23 milhões de visualizações na rede da Akamai, mostrou que o abandono começa quando o vídeo demora mais de cerca de 2 segundos para iniciar, com aumento aproximado de 5,8 pontos percentuais na taxa de abandono a cada segundo adicional. Travamentos equivalentes a 1% da duração reduzem em cerca de 5% o tempo assistido, e quem sofre falha de reprodução tem probabilidade cerca de 2,3% menor de voltar na mesma semana. O resultado sustenta o atributo 3: a degradação que não gera erro é justamente a que destrói engajamento.

&emsp; **Peso do custo de observabilidade.** A pesquisa da Grafana Labs de 2025 aponta que o gasto com observabilidade representa em média cerca de 17% do gasto total com infraestrutura de computação, sendo 10% a resposta mais frequente. Pesquisas do setor também indicam que a maioria dos times filtra, arquiva ou desloca dados para conter custo, reduzindo visibilidade para economizar. É esse comportamento que os atributos 4 e 8 pretendem transformar em decisão consciente.

### 1.7. Quatro ações do Oceano Azul aplicadas ao projeto

#### Eliminar

- A reunião de correlação como etapa obrigatória do diagnóstico, hoje necessária para formular a primeira hipótese.
- O alinhamento manual de horários e recortes entre painéis de fontes distintas.
- Os pontos cegos de dispositivos que não aparecem em painel algum por incompatibilidade de protocolo.

#### Reduzir

- O número de saltos entre filas até chegar ao time correto, substituindo triagem por eliminação por triagem com hipótese.
- A amostragem cega motivada por custo, e não por irrelevância analítica.
- O intervalo entre a degradação e a percepção interna dela, hoje dependente da reclamação do assinante.

#### Aumentar

- A resolução da análise, até o nível de modelo, firmware, UF, operadora e versão de aplicação.
- A cobertura efetiva da base instalada, incluindo aparelhos antigos e redes instáveis.
- A autonomia do time de atendimento, medida pelo quanto a primeira linha conclui sem escalar.

#### Criar

- Hipótese de causa provável ranqueada, com evidência associada, que nenhuma das alternativas entrega hoje.
- Linha do tempo única do incidente, atravessando componentes que só existem separados.
- API única de ingestão multiprotocolo, que trata a heterogeneidade do parque como característica permanente.

### 1.8. Como a solução gera diferenciação

&emsp; A diferenciação está em mudar a natureza da entrega, e não apenas sua qualidade. As duas alternativas comparadas entregam dados: uma os espalha em painéis por componente, a outra os reúne em um painel único. Em ambas, a inferência sobre a causa continua sendo tarefa de alguém que conheça o comportamento normal de cada peça da cadeia. A solução do grupo entrega inferência, movendo a fronteira da automação da coleta e da visualização para a formulação de hipótese.

&emsp; Porem ela não é absoluta. A solução é deliberadamente pior em facilidade de adoção e ainda precisa comprovar sustentação sob pico. Seu valor depende de uma decisão do parceiro: aceitar maior custo de propriedade e maior responsabilidade operacional em troca de granularidade, cobertura e velocidade de diagnóstico que nem a prática atual nem o mercado entregam para a realidade específica do Globoplay.

## 2. Matriz de Risco

---

## 3. Canvas da Proposta de Valor

## 4. Análise Financeira do Projeto

---

## 5. Análise de impacto do projeto na perspectivas dos ODS

---

## Referências

- KRISHNAN, S. Shunmuga; SITARAMAN, Ramesh K. _Video Stream Quality Impacts Viewer Behavior: Inferring Causality Using Quasi-Experimental Designs_. In: ACM Internet Measurement Conference (IMC), 2012. Disponível em: https://people.cs.umass.edu/~ramesh/Site/HOME_files/imc208-krishnan.pdf. Acesso em: ago. 2026.
- ANDROID DEVELOPERS. _ANRs | App quality_. Disponível em: https://developer.android.com/topic/performance/vitals/anr. Acesso em: ago. 2026.
- GOOGLE PLAY CONSOLE HELP. _Monitor your app's technical quality with Android vitals_. Disponível em: https://support.google.com/googleplay/android-developer/answer/9844486. Acesso em: ago. 2026.
- GRAFANA LABS. _Observability Survey Report 2025_. Disponível em: https://grafana.com/observability-survey/2025/. Acesso em: ago. 2026.
- BRASIL. _Lei nº 13.709, de 14 de agosto de 2018_ (Lei Geral de Proteção de Dados Pessoais).
