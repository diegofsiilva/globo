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

