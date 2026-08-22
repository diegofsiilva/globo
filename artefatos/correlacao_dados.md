# Correlação de dados para geração de hipóteses

## 1. Objetivo

&emsp;Este documento descreve como identificar padrões de correlação entre as
anomalias detectadas pelo Argus e os sinais de contexto disponíveis no projeto.
O resultado da correlação é um conjunto de evidências que pode sustentar,
enfraquecer ou impedir a avaliação de uma hipótese de causa provável.

&emsp;A correlação não confirma automaticamente uma causa-raiz. Ela organiza os
dados disponíveis para responder perguntas como:

- houve uma mudança relevante antes do início do problema?;
- o possível evento causador pertence ao mesmo serviço, canal ou recorte
  afetado?;
- fontes independentes apresentam degradações compatíveis?;
- o problema está concentrado em um segmento específico?;
- existe alguma evidência observada que contradiz a causa candidata?;
- as fontes estavam disponíveis e saudáveis no momento da análise?

## 2. Escopo e restrições

&emsp;A metodologia apresentada não altera a arquitetura atual. Não são propostos
novos serviços AWS, filas, bancos de dados ou fluxos de ingestão. A correlação é
descrita como uma responsabilidade lógica do processamento já previsto, usando
os sinais normalizados, buckets, anomalias, contexto e informações de qualidade
existentes.

&emsp;Fazem parte do escopo:

- definir o que significa correlacionar dados no domínio do Argus;
- descrever os tipos de correlação utilizados;
- mapear as features que participam da análise;
- relacionar fontes de dados a famílias de hipóteses;
- estabelecer regras temporais e semânticas;
- diferenciar evidência favorável, contrária e indisponível;
- propor um cálculo explicável para score, cobertura e confiança;
- definir proteções contra falsos positivos conhecidos.

&emsp;Não fazem parte do escopo:

- modificar o diagrama de arquitetura;
- escolher uma nova tecnologia de persistência;
- implementar o motor de hipóteses;
- afirmar causalidade a partir de coincidência temporal;
- treinar um modelo supervisionado;
- utilizar incidentes futuros ou dados indisponíveis no instante analisado.

## 3. Conceitos fundamentais

### 3.1 Sinal

&emsp;Um sinal é uma observação normalizada de uma fonte. Sua identidade semântica
é formada por:

```text
source + entity + metric
```

&emsp;O nome da métrica não deve ser interpretado isoladamente. Por exemplo,
`rpm` pode aparecer em fontes distintas com significados e formas de cálculo
diferentes.

### 3.2 Bucket

&emsp;Um bucket representa um intervalo de agregação. O intervalo padrão da camada
analítica é de 15 minutos. Fontes com granularidade mais fina são agregadas para
esse intervalo. Fontes horárias continuam representando uma janela de uma hora
e não devem receber uma precisão de minutos que não possuem.

### 3.3 Anomalia ou achado

&emsp;Uma anomalia é um desvio observado em relação ao baseline causal. Ela informa
o que apresentou comportamento inesperado, mas ainda não atribui uma causa.

```text
Anomalia: error_rate do playback-api acima do baseline
Não é ainda: deploy causou falha no playback-api
```

### 3.4 Evidência

&emsp;Uma evidência é um dado interpretado no contexto de uma hipótese. Ela deve
registrar sua origem, disponibilidade, valor normalizado, peso e contribuição.

| Relação | Interpretação |
|---|---|
| `supports` | O dado aumenta a força da hipótese. |
| `contradicts` | O dado foi consultado e enfraquece a hipótese. |
| `neutral` | O dado está disponível, mas não favorece nem contradiz a hipótese. |

| Disponibilidade | Interpretação |
|---|---|
| `available` | A evidência pôde ser consultada e avaliada. |
| `unavailable` | A fonte ou o campo ainda não estava disponível. |
| `not_applicable` | A feature não se aplica àquela família de hipótese. |
| `contradicts` | O dado consultado contradiz a hipótese. |

### 3.5 Hipótese

&emsp;Uma hipótese é uma explicação candidata para uma ou mais anomalias. Ela deve
ser apresentada em linguagem não conclusiva, como “possível regressão após
deploy” ou “evidências sugerem degradação de CDN”.

### 3.6 Correlação e causalidade

&emsp;Correlação indica que dois ou mais fatos possuem uma relação relevante no
tempo, no escopo ou no comportamento. Causalidade exige evidência de que um fato
produziu o outro. O sistema trabalha com correlação explicável para apoiar a
investigação humana; não declara causalidade automaticamente.

## 4. Dados utilizados na arquitetura atual

&emsp;A correlação utiliza as saídas já produzidas pelas camadas atuais.

| Dado lógico | Papel na correlação |
|---|---|
| Sinais canônicos da camada silver | Preservam fonte, entidade, métrica, valor e disponibilidade. |
| Buckets da camada gold | Alinham sinais no tempo e oferecem as features analisadas pelo detector. |
| Estado do baseline | Permite explicar por que um valor foi considerado anômalo. |
| Anomalias por `run_id` | São o ponto de partida obrigatório de cada hipótese. |
| Relógio virtual `sim.now` | Define quais registros podem participar da execução. |
| Canário de qualidade | Informa atraso, ausência, divergência e saúde das fontes. |
| Janela de evento ao vivo | Oferece contexto exógeno para interpretar picos de audiência. |
| Janela de incidente e correspondências | Servem para avaliação posterior, não como causa online. |
| Views condicionadas por `available_at` | Impedem que consultas utilizem informações futuras. |

&emsp;A correlação deve acontecer depois da conclusão de uma execução do detector.
O frontend não inicia o cálculo: ele consulta resultados associados a uma
execução concluída.

## 5. Invariantes temporais

### 5.1 Nenhum dado futuro

&emsp;Toda evidência consultada deve satisfazer:

```text
evidence.available_at <= run.sim_now
```

&emsp;Um fato pode ter ocorrido antes da anomalia e ainda assim não estar
disponível. Nesse caso, ele não participa da execução atual e deve ser registrado
como indisponível quando aplicável.

### 5.2 Causa candidata anterior ao efeito

&emsp;Para hipóteses que possuem evento causal identificável:

```text
cause.event_at <= effect.event_at
```

&emsp;Um deploy posterior ao começo da degradação não pode explicar o início do
problema, mesmo que esteja próximo no tempo.

### 5.3 Baseline causal

&emsp;O valor de um bucket deve ser comparado somente com observações anteriores e
disponíveis. Reprocessamentos não devem substituir silenciosamente as evidências
que estavam visíveis em uma execução histórica.

### 5.4 UTC, BRT e sazonalidade

&emsp;Timestamps operacionais permanecem em UTC. A conversão para BRT é utilizada
para features de hora do dia, dia da semana e horário nobre. O período de 20h a
23h BRT atravessa a meia-noite UTC, portanto agrupamentos diários de audiência
não devem usar diretamente o dia UTC.

### 5.5 Granularidade

| Fonte | Granularidade típica | Tratamento |
|---|---:|---|
| Prometheus | 1 minuto | Agregar para 15 minutos. |
| New Relic | 5 minutos ou 1 hora | Detectar a cadência antes de correlacionar. |
| RPaaS | 15 minutos | Alinhamento direto com o bucket padrão. |
| Sessões concorrentes ao vivo | 15 minutos | Alinhamento direto com o bucket padrão. |
| NPAW/Youbora | 1 hora | Correlacionar por sobreposição de janela, sem precisão artificial. |
| Deploy, incidente e evento editorial | Evento ou intervalo | Comparar início, fim e janela máxima da regra. |

## 6. Tipos de correlação

### 6.1 Correlação temporal

&emsp;Mede a proximidade entre uma causa candidata anterior e o início do efeito.
É necessária em hipóteses como regressão após deploy, bloqueio de WAF ou falha
upstream, mas não é suficiente para confirmar nenhuma delas.

### 6.2 Correlação semântica

&emsp;Verifica se os registros se referem ao mesmo domínio ou a componentes
relacionados. A comparação deve considerar a semântica da fonte.

Exemplos:

- `tsuru_event.target_value` relacionado à aplicação do New Relic;
- serviço do Prometheus relacionado ao mesmo backend;
- vhost do RPaaS relacionado ao fluxo de playback;
- `sinal` do NPAW igual à entidade das fontes CDN e origem;
- dispositivo ou player afetado comparado aos demais segmentos.

&emsp;O relacionamento entre nomes de entidades pode ser mantido como configuração
do processamento. Isso é uma regra de domínio e não exige alteração da
arquitetura física.

### 6.3 Correlação por propagação

&emsp;Procura uma sequência compatível ao longo da cadeia de entrega.

```text
causa upstream
    ↓
backend ou API degrada
    ↓
borda ou CDN apresenta erro
    ↓
experiência do usuário piora
```

&emsp;A ordem ajuda a diferenciar a raiz de componentes que apenas sofreram o
efeito. Uma anomalia presente em toda a cadeia sugere causa mais a montante. Uma
anomalia presente somente na experiência do usuário pode indicar player,
dispositivo, ISP ou last-mile.

### 6.4 Correlação entre fontes

&emsp;Mede a concordância entre fontes independentes. Por exemplo, erro no New
Relic, latência no Prometheus e 5xx no RPaaS formam uma corroboração mais forte
que três métricas derivadas do mesmo coletor.

### 6.5 Correlação por concentração

&emsp;Identifica se a degradação está desproporcionalmente concentrada em um
segmento. Pode ser medida por lift:

```text
       participação do recorte nos erros
lift = ----------------------------------
       participação do recorte no tráfego
```

&emsp;Aplicações típicas:

- player;
- modelo de dispositivo;
- estado e operadora;
- canal;
- vhost;
- versão ou serviço.

### 6.6 Correlação com contexto exógeno

&emsp;Eventos editoriais, como jogos, ajudam a interpretar aumento de audiência.
Um pico de volume durante um evento ao vivo pode ser esperado. Entretanto, a
existência do evento não descarta um incidente se erros e QoE também piorarem.

### 6.7 Correlação contrária

&emsp;Procura informações incompatíveis com a hipótese. Exemplos:

- a degradação começou antes do deploy;
- o deploy atingiu um serviço sem relação com o recorte afetado;
- somente uma operadora está degradada enquanto a hipótese aponta falha global;
- a origem está normal enquanto a hipótese aponta falha de origem;
- o canário indica que a fonte parou de atualizar.

## 7. Features explicáveis

&emsp;Cada regra transforma suas evidências em features normalizadas entre zero e
um. Features não aplicáveis devem ser retiradas do cálculo; features aplicáveis
mas indisponíveis reduzem a cobertura.

### 7.1 Força da anomalia (`A`)

&emsp;Representa a distância entre o valor observado e o baseline. Deve vir da
execução do detector, preservando direção, valor observado, valor esperado e
score original.

&emsp;A direção depende da métrica:

- aumento de erro, latência, buffering ou stalls costuma ser degradação;
- redução de Apdex pode ser degradação;
- redução de sessões pode indicar falha de player;
- redução de latência normalmente não representa incidente.

### 7.2 Proximidade temporal (`T`)

&emsp;Para uma causa candidata anterior ao efeito:

```text
T(delta) = 2 ^ (-delta_minutos / meia_vida_minutos)
```

&emsp;Com meia-vida de 15 minutos:

| Distância | `T` |
|---:|---:|
| 0 min | 1,00 |
| 6 min | 0,76 |
| 15 min | 0,50 |
| 30 min | 0,25 |
| 45 min | 0,125 |

&emsp;A meia-vida e a janela máxima devem ser configuradas por família. Se não
existir evento causal identificável, `T` é `not_applicable` e não penaliza a
hipótese.

### 7.3 Corroboração (`C`)

&emsp;Representa a concordância entre fontes ou sinais independentes. Deve
considerar:

- quantidade de fontes independentes;
- qualidade de cada fonte;
- compatibilidade temporal;
- coerência de direção;
- posição dos sinais na cadeia de dependência.

### 7.4 Especificidade (`E`)

&emsp;Representa quanto o problema está isolado em um recorte. Um lift próximo de
um indica comportamento proporcional ao tráfego. Valores maiores indicam
concentração.

### 7.5 Impacto (`I`)

&emsp;Representa a materialidade operacional. Pode utilizar:

- sessões ou sessões ativas afetadas;
- participação na audiência;
- volume de requisições;
- quantidade de entidades afetadas;
- importância do canal ou PoP;
- duração da degradação.

### 7.6 Qualidade (`Q`)

&emsp;Representa saúde, atualidade e completude das fontes. Deve ser derivada do
canário e dos metadados de execução dos coletores. Fonte atrasada, incompleta ou
divergente não deve sustentar uma causa operacional sem ressalva.

### 7.7 Contradição (`X`)

&emsp;Representa a força das evidências contrárias observadas. Dado ausente não
contribui para `X`. Uma contradição forte pode descartar o candidato mesmo que a
proximidade temporal seja alta.

## 8. Score, cobertura e confiança

### 8.1 Score

&emsp;Quando todas as features estiverem disponíveis, uma combinação heurística
inicial pode ser:

```text
score = 100 × (
    0,25A +
    0,20T +
    0,20C +
    0,15E +
    0,15I +
    0,05Q
) - 30X
```

&emsp;Os pesos são uma configuração inicial para discussão com especialistas. O
score não é uma probabilidade. Um score igual a 80 não significa 80% de chance
de a causa estar correta.

&emsp;Na execução geral, o score-base deve ser normalizado apenas pelos pesos das
features disponíveis:

```text
             soma(w_i × f_i), para features disponíveis
score-base = -------------------------------------------- × 100
             soma(w_i), para features disponíveis

score = limitar(score-base - 30X, mínimo=0, máximo=100)
```

&emsp;Features `not_applicable` são retiradas do cálculo e da cobertura. Quando uma
feature aplicável estiver indisponível, sua ausência reduz cobertura e
confiança, mas não deve ser convertida silenciosamente em valor zero.

### 8.2 Cobertura

```text
            soma dos pesos das evidências disponíveis
cobertura = ------------------------------------------
            soma dos pesos das evidências aplicáveis
```

### 8.3 Confiança

&emsp;A confiança considera score, cobertura, qualidade e força das contradições.
Um ponto de partida configurável é:

| Confiança | Condição inicial |
|---|---|
| Alta | `score >= 80`, `coverage >= 0,80`, `Q >= 0,70` e sem contradição forte. |
| Média | `score >= 60`, `coverage >= 0,60` e sem contradição determinante. |
| Baixa | Demais resultados avaliáveis. |

## 9. Padrões de correlação por família

### 9.1 Possível regressão após deploy

| Elemento | Definição |
|---|---|
| Causa candidata | Evento `app.deploy`. |
| Efeito | Anomalia em aplicação, API, borda ou experiência relacionada. |
| Relação temporal | Deploy anterior ao efeito e dentro da janela configurada. |
| Relação semântica | Alvo do deploy igual ou relacionado à entidade afetada. |
| Evidências favoráveis | Erro ou latência surgindo depois do deploy, queda de Apdex, downstreams afetados. |
| Contradições | Problema anterior ao deploy, alvo sem relação ou causa externa mais específica. |

&emsp;O evento `autoscale.run` não representa necessariamente escala provocada por
carga. Ele não deve ser interpretado automaticamente como causa de saturação.

### 9.2 Possível falha interna de backend ou API

| Fonte | Features relevantes |
|---|---|
| New Relic | `error_rate_pct`, tempo de resposta, throughput e queda de Apdex. |
| Apollo | taxa de erro, RPM e percentis de latência por operação ou campo. |
| Prometheus | CPU, réplicas, circuit breaker, erros HTTP, rede e Redis. |
| RPaaS | taxa de 5xx e percentis de latência. |

&emsp;A assinatura ganha força quando os sinais se propagam de um componente
upstream para seus dependentes. A raiz candidata deve ser o ponto mais a
montante compatível com a ordem temporal observada.

### 9.3 Possível falha de playback ou autorização

&emsp;A correlação pode combinar:

- aumento de 4xx nos vhosts conhecidos de playback;
- atribuição `playback_api` na classificação de erro;
- categoria semântica de acesso;
- crescimento de `startup_errors`;
- falha em operação relacionada à resolução do vídeo.

&emsp;Taxa alta de 4xx fora do catálogo de playback pode ser comportamento
estrutural e não deve, isoladamente, gerar hipótese.

### 9.4 Possível degradação de CDN

&emsp;A assinatura mais forte combina erro de CDN e degradação de QoE no mesmo
canal:

```text
cdn_live_errors.err_rate aumenta
    + mesmo sinal/canal
jointime, stalls ou bufferratio aumentam
```

&emsp;A importância do canal ou PoP participa do impacto. Uma entidade de alto
volume deve ter prioridade maior que uma entidade de baixo volume.

### 9.5 Possível falha de origem ou encoding

&emsp;A correlação utiliza erro de origem, categoria semântica de origem e piora de
QoE no mesmo canal. Se a origem degrada antes da CDN e do usuário, ela é uma
causa mais específica que a hipótese genérica de entrega.

### 9.6 Possível falha regional, ISP ou last-mile

&emsp;A assinatura procura concentração em estado e operadora:

```text
taxa de erro elevada em uma UF + ISP
    + volume mínimo
    + demais operadoras próximas do baseline
    + ausência de degradação global equivalente
```

&emsp;A atribuição `edge_isp` reforça essa família. O volume de sessões deve ser
considerado para evitar lift elevado produzido por amostra pequena.

### 9.7 Possível ataque ou bloqueio de WAF

&emsp;A hipótese relaciona aumento de requisições bloqueadas no Cloud Armor com
anomalias posteriores ou simultâneas na aplicação protegida. Pode explicar
crescimento de tráfego e CPU sem regressão interna.

### 9.8 Possível regressão de player ou dispositivo

&emsp;A assinatura procura erro, queda de sessões ou piora de QoE concentrada em
um player ou modelo, enquanto os demais segmentos permanecem próximos do
baseline. É necessário volume mínimo por segmento.

### 9.9 Possível degradação de QoE sem erro explícito

&emsp;Taxa de erro normal não descarta degradação. A hipótese pode ser sustentada
por aumento de:

- tempo para início (`jointime`);
- proporção de buffering;
- stalls;
- latência percebida;
- frames perdidos.

### 9.10 Pico esperado por evento ao vivo

&emsp;A janela de evento ao vivo funciona como contexto, não como causa automática
de incidente.

| Comportamento | Interpretação |
|---|---|
| Audiência sobe e QoE permanece normal | Pico esperado; reduzir peso de hipóteses baseadas apenas em volume. |
| Audiência sobe e erros/QoE pioram | Manter hipóteses de falha e aumentar impacto. |
| Evento existe, mas canal não é compatível | Não utilizar como explicação do recorte. |

### 9.11 Possível falha ou atraso de fonte

&emsp;Quando o canário ou os metadados indicarem atraso, ausência ou divergência,
o desaparecimento do sinal não deve ser interpretado como incidente de produção.
O padrão correto é uma hipótese de qualidade de dados.

## 10. Processo lógico da correlação

&emsp;Para cada execução concluída do detector:

1. recuperar o `run_id`, `sim_now`, baseline e anomalias produzidas;
2. descartar qualquer registro que não estivesse disponível em `sim_now`;
3. agrupar anomalias temporalmente compatíveis;
4. preservar `source + entity + metric` ao interpretar cada sinal;
5. selecionar famílias de hipótese compatíveis com as métricas observadas;
6. buscar causas e contextos dentro da janela temporal da família;
7. validar relacionamento semântico entre as entidades;
8. calcular `A`, `T`, `C`, `E`, `I`, `Q` e `X`;
9. registrar evidências favoráveis, contrárias e indisponíveis;
10. calcular score, cobertura e confiança;
11. classificar o candidato;
12. ordenar hipóteses para investigação humana.

### 10.1 Pseudocódigo

```text
para cada anomalia do run:
    validar qualidade e disponibilidade da fonte
    encontrar regras compatíveis com source + entity + metric

    para cada regra:
        buscar contexto disponível dentro da janela da regra
        validar relação temporal
        validar relação semântica
        coletar corroborações e contradições
        calcular features aplicáveis
        calcular score, cobertura e confiança
        registrar resultado e evidências

ordenar resultados por prioridade de investigação
```

## 11. Exemplo: deploy e aumento de erros

### 11.1 Linha temporal

```text
19:58 — deploy no serviço de playback
20:00 — início do bucket analítico
20:04 — taxa de erros aumenta
20:05 — RPaaS registra aumento de 5xx
20:07 — latência interna aumenta
20:15 — detector conclui a análise do bucket
```

### 11.2 Evidências

| Feature | Valor ilustrativo | Explicação |
|---|---:|---|
| `A` | 0,92 | O erro está muito acima do baseline. |
| `T` | 0,76 | O deploy ocorreu seis minutos antes do início do efeito. |
| `C` | 0,85 | New Relic, RPaaS e sinal interno corroboram. |
| `E` | 0,90 | A degradação está concentrada no fluxo de playback. |
| `I` | 0,70 | O serviço possui volume relevante no período. |
| `Q` | 0,95 | As fontes utilizadas estão atualizadas e completas. |
| `X` | 0,00 | Nenhuma contradição determinante foi encontrada. |

### 11.3 Resultado

```text
Título: Possível regressão após deploy no serviço de playback
Score: 84
Cobertura: 100%
Confiança: alta
Estado: generated
```

&emsp;Esse resultado não confirma o deploy como causa. Ele indica que, entre as
alternativas avaliadas, essa explicação possui evidências fortes e deve ser
investigada primeiro.

## 12. Estados do resultado

| Estado | Significado |
|---|---|
| `candidate` | A assinatura inicial da regra foi encontrada. |
| `generated` | Existem evidências mínimas para apresentar a hipótese. |
| `insufficient_evidence` | Faltam dados necessários para avaliar a causa. |
| `discarded` | Evidências observadas contradizem a hipótese. |
| `confirmed` | Uma pessoa confirmou a hipótese. |
| `partially_confirmed` | Parte da causa ou do escopo foi confirmada. |
| `rejected` | Uma pessoa rejeitou a hipótese. |

## 13. Proteções contra falsos positivos

### 13.1 RPaaS amostrado

&emsp;Como os logs são amostrados, a correlação deve priorizar taxas, como
`5xx / requests_total`, em vez de contagens absolutas. Buckets de baixo volume
não devem sustentar proporções elevadas.

### 13.2 4xx estrutural

&emsp;Taxa elevada de 4xx é normal em alguns vhosts. A hipótese de playback só
deve usar 4xx nos vhosts e fluxos configurados como relevantes.

### 13.3 Zeros das fontes CDN

&emsp;Zero em fontes CDN pode significar que o sinal não passou pelos gates de
materialidade, não necessariamente ausência comprovada de erro. Esses zeros não
devem funcionar como contradição forte sem contexto.

### 13.4 Fontes atrasadas

&emsp;Dados NPAW/Youbora possuem atraso estrutural e não devem aparecer
retroativamente em uma hipótese online. Quando ficarem disponíveis, podem
produzir uma revisão posterior, preservando a execução original.

### 13.5 Fonte parada

&emsp;Antes de interpretar queda ou desaparecimento, a correlação deve consultar o
canário e os metadados do coletor. Coletor parado é problema de dados, não prova
de incidente na produção.

### 13.6 Categorias desconhecidas

&emsp;Valores como `"(desconhecido)"` ou `"?"` representam informação ausente. Não
devem originar uma hipótese sobre um segmento chamado “desconhecido”.

### 13.7 Evento ao vivo

&emsp;A existência de jogo ou programa de grande audiência contextualiza o volume,
mas não elimina incidentes simultâneos. O contexto só reduz falsos positivos
quando o crescimento é proporcional e a experiência permanece saudável.

### 13.8 Ground truth circular

&emsp;Rótulos derivados do próprio detector não devem ser usados como verdade
independente para avaliar a mesma lógica. Janelas de incidente e correspondências
devem ser usadas na avaliação, sem participar do score online.

### 13.9 Timestamp do ticket

&emsp;O horário de abertura de um ticket não é necessariamente o início do
incidente. Avaliações de lead time devem considerar essa imprecisão.

