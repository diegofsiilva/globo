# Front-end

&emsp; Este artefato documenta o dashboard integrado do Argus. A interface é uma aplicação Next.js exportada como site estático; em execução, ela consulta a API Flask, que lê o PostgreSQL. As evidências desta versão foram produzidas localmente com uma fixture pequena e determinística no banco `argus_test`. Portanto, os dados das capturas são sintéticos e controlados, mas atravessam o fluxo real **navegador → Flask → PostgreSQL**.

## 1. Interface integrada

&emsp; A entrada `/` redireciona para `/agora`. A navegação pública é formada por seis áreas operacionais, com cabeçalho, período, tema, escopo e navegação responsiva compartilhados.

| Rota | Objetivo | Dados consumidos |
|---|---|---|
| `/agora` | Mostrar sinais em desvio e degradações abertas | relógio simulado, facetas e sinais calculados |
| `/explorar` | Investigar volume, evolução temporal e concentração | facetas, séries temporais e agrupamentos |
| `/comparar` | Comparar a janela atual com referências históricas | séries, mudanças, janela estável e pico ao vivo anterior |
| `/hipoteses` | Ordenar possíveis causas e explicar o score | hipóteses publicadas, fatores e evidências |
| `/timeline` | Correlacionar seis fontes numa cronologia única | eventos de NPAW, New Relic, Prometheus, Apollo, deploy e incidente |
| `/recorte` | Delimitar população afetada e abrir uma sessão | cruzamento de métricas, amostra de erros e timeline da sessão |

&emsp; As seis rotas consultam o backend. A única exceção intencional é o painel **Ajustar o recorte**, em `/recorte`: seus cenários são informativos, vêm de `_mocks/scenario.ts` e não executam ações. Hipóteses preserva uma fonte mockável para desenvolvimento, porém todos os testes integrados desta rodada usaram `NEXT_PUBLIC_HYPOTHESES_SOURCE=api`.

### 1.1 Tecnologias

- Next.js 16 com App Router e export estático;
- React 19 e TypeScript;
- Tailwind CSS v4, shadcn/ui e Radix UI;
- TanStack Query para cache, refetch e estados assíncronos;
- Vitest, Testing Library e `user-event` para contratos e componentes;
- Playwright com Chromium para testes ponta a ponta e capturas.

### 1.2 Capturas integradas

&emsp; As imagens abaixo foram regeneradas em 28/08/2026 sobre o build estático conectado ao Flask e ao banco `argus_test`. O relógio da fixture está fixado em 14/07/2026 às 12:00 UTC (09:00 BRT), o que torna valores e janelas reproduzíveis.

#### Agora

<p align="center">
  <img src="./assets/captura_agora_tema_escuro.png" alt="Agora integrado no tema escuro" width="49%">
  <img src="./assets/captura_agora_tema_claro.png" alt="Agora integrado no tema claro" width="49%">
</p>

#### Explorar

<p align="center">
  <img src="./assets/captura_explorar_tema_escuro.png" alt="Explorar integrado no tema escuro" width="49%">
  <img src="./assets/captura_explorar_tema_claro.png" alt="Explorar integrado no tema claro" width="49%">
</p>

#### Comparar

<p align="center">
  <img src="./assets/captura_comparar_tema_escuro.png" alt="Comparar integrado no tema escuro" width="49%">
  <img src="./assets/captura_comparar_tema_claro.png" alt="Comparar integrado no tema claro" width="49%">
</p>

#### Hipóteses

<p align="center">
  <img src="./assets/captura_hipoteses_tema_escuro.png" alt="Hipóteses em modo API no tema escuro" width="49%">
  <img src="./assets/captura_hipoteses_tema_claro.png" alt="Hipóteses em modo API no tema claro" width="49%">
</p>

#### Timeline

<p align="center">
  <img src="./assets/captura_timeline_tema_escuro.png" alt="Timeline integrada no tema escuro" width="49%">
  <img src="./assets/captura_timeline_tema_claro.png" alt="Timeline integrada no tema claro" width="49%">
</p>

#### Recorte

<p align="center">
  <img src="./assets/captura_recorte_tema_escuro.png" alt="Recorte integrado no tema escuro" width="49%">
  <img src="./assets/captura_recorte_tema_claro.png" alt="Recorte integrado no tema claro" width="49%">
</p>

#### Viewports responsivos

<p align="center">
  <img src="./assets/captura_agora_mobile.png" alt="Agora integrado em 390 por 844 pixels" width="31%">
  <img src="./assets/captura_agora_tablet.png" alt="Agora integrado em 768 por 1024 pixels" width="49%">
</p>

## 2. Organização e contratos

```text
apps/basica/frontend/
├── src/app/(operations)/
│   ├── _components/              moldura, escopo, tema e navegação
│   ├── agora/                    sinais e facetas
│   ├── explorar/                 séries, facetas e agrupamentos
│   ├── comparar/                 referências e mudanças
│   ├── hipoteses/                fonte HTTP ou mock explícito
│   ├── timeline/                 adaptação das seis raias
│   └── recorte/                  crosstab, eventos e sessão
├── src/lib/                      contratos e utilitários compartilhados
├── tests/contracts/              Vitest: fronteiras HTTP e adaptadores
├── tests/ui/                     Testing Library: interação de componente
├── tests/e2e/                    Playwright e fixture SQL
├── playwright.config.ts
└── vitest.config.mts
```

&emsp; O valor de `NEXT_PUBLIC_API_URL` é incorporado no build. A aplicação falha cedo se a variável não for informada, evitando publicar um bundle que tente ler JSON do próprio domínio estático. `NEXT_PUBLIC_HYPOTHESES_API_URL` pode apontar para outra origem, mas nos testes integrados utiliza a mesma API Flask.

### 2.1 Fixture determinística

&emsp; O arquivo [`fixture.sql`](../apps/basica/frontend/tests/e2e/fixture.sql) limpa apenas as tabelas necessárias do banco de teste e insere:

- relógio simulado fixo;
- sinais atual e de baseline;
- séries para volume, taxa de erro e seis fontes operacionais;
- deploy, incidente e evento ao vivo;
- sessão de dispositivo legado com `session`, `video_view` e `error`;
- hipótese publicada com score, fator, evidência e qualidade de fonte.

&emsp; O dump de produção não participa da execução. O alvo E2E reaplica as migrations e a fixture a cada rodada, e nunca usa o banco `argus` para asserções.

### 2.2 Comandos

```bash
make -C apps/basica db-local
make -C apps/basica test-frontend
make -C apps/basica test-frontend-e2e
```

&emsp; O primeiro comando sobe o PostgreSQL local. `test-frontend` executa Vitest. `test-frontend-e2e` migra e semeia `argus_test`, gera o build com Hipóteses em modo `api`, inicia Flask e servidor estático temporários e executa Playwright. O Chromium é instalado uma vez com `npx playwright install chromium` no diretório do frontend.

## 3. Testes automatizados

### 3.1 Vitest e Testing Library

&emsp; Estes testes isolam somente a fronteira HTTP. Não simulam PostgreSQL nem tratam uma resposta mockada como prova de integração.

| ID | Verificação | Resultado |
|---|---|---|
| TA-01 | Janela e filtros cumulativos enviados ao agrupamento de Explorar | Aprovado |
| TA-02 | Conversão de sinal real para o contrato visual de Agora | Aprovado |
| TA-03 | Timeout HTTP classificado como falha repetível | Aprovado |
| TA-04 | Comparação com ontem preserva duração e horário | Aprovado |
| TA-05 | Referência estável é consultada no backend | Aprovado |
| TA-06 | Hipótese publicada vira relatório explicável com score e evidência | Aprovado |
| TA-07 | Resposta inválida de Hipóteses é rejeitada | Aprovado |
| TA-08 | Recorte solicita sessões e taxa de erro no mesmo crosstab | Aprovado |
| TA-09 | Timeline mantém seis fontes ordenadas e atribuídas | Aprovado |
| TA-10 | Alternância de tema é anunciada e acionável pelo botão público | Aprovado |
| TA-11 | Loading, vazio e erro têm mensagens distintas e erro permite nova tentativa | Aprovado |

### 3.2 Playwright integrado

| ID | Fluxo exercitado no Chromium | Resultado |
|---|---|---|
| E2E-01 | Redirecionamento de `/` e navegação pelas seis rotas | Aprovado |
| E2E-02 | Sinal de Agora calculado pelo Flask a partir do PostgreSQL | Aprovado |
| E2E-03 | Métricas, facetas, agrupamento e filtros cumulativos em Explorar | Aprovado |
| E2E-04 | Troca de referência e mudanças retornadas pelo backend | Aprovado |
| E2E-05 | Hipóteses em modo API, score e evidência publicada | Aprovado |
| E2E-06 | Timeline correlacionando seis fontes | Aprovado |
| E2E-07 | Amostra de erro e cronologia da sessão `session-e2e` | Aprovado |
| E2E-08 | Tema por teclado, menu móvel, navegação e ausência de overflow horizontal | Aprovado |

### 3.3 Resultado executado

| Validação | Resultado em 28/08/2026 |
|---|---|
| Vitest/Testing Library | 7 arquivos; 11 testes aprovados |
| Playwright integrado | 8 testes aprovados no Chromium |
| Capturas documentais | 1 cenário aprovado; 14 imagens regeneradas |
| Backend Flask | 143 testes aprovados contra PostgreSQL ativo |
| Build estático | 8 rotas geradas (`/`, `_not-found` e as seis áreas) |

&emsp; Durante a implementação, o E2E-07 revelou que `error_code` chegava no JSON, mas era substituído pelo texto genérico `error` na interface. O resumo de erro passou a priorizar o código recebido; a sessão integrada agora exibe e testa `PLAYER-500`.

## 4. Estados, entradas e acessibilidade

- loading, vazio, erro, timeout e dados prontos são representados pelos estados operacionais compartilhados;
- filtros usam valores de facetas reais e são serializados com `URLSearchParams`;
- filtros de fonte e métrica permanecem cumulativos na consulta de Explorar;
- períodos são calculados a partir de `/api/v1/clock`, sem aceitar uma janela invertida pela interface;
- botões, radios, selects, tabelas, dialog de sessão e navegação têm nomes acessíveis;
- existe link de salto para o conteúdo, foco visível e ativação por teclado;
- o tema persiste em `argus-theme` e não remove o estado da rota;
- em 390 px a navegação vira menu; em 768 px a composição permanece utilizável; o E2E-08 verificou ausência de overflow horizontal em 390 px.

## 5. Matriz de rastreabilidade dos requisitos funcionais

&emsp; A classificação usa somente código e testes executados. **Atendido** significa que o comportamento exigido foi observado no fluxo integrado; **Parcial** indica cobertura funcional incompleta; **Não atendido** registra ausência do comportamento.

| Req. | Classificação | Evidência executada | Justificativa |
|---|---|---|---|
| RF08 | Parcial | TA-01, E2E-03, E2E-07 | Há tipo/métrica, período, fonte, entidade e acesso a uma sessão. Faltam busca direta por `session_id`/`device_id` e filtros completos de SO/versão, app e código de erro. |
| RF09 | Atendido | TA-01, E2E-03 | Fonte e métrica foram combinadas na mesma requisição real. |
| RF10 | Atendido | E2E-03 | Os selects usam valores retornados por `/series/facets`. |
| RF11 | Atendido | TA-01, TA-08, E2E-03 | Agrupamentos por entidade, métrica, fonte, hora e dia estão conectados às séries agregadas. |
| RF12 | Atendido | TA-02, TA-08, E2E-02, E2E-03, E2E-04 | Indicadores, séries, comparação e mapa de calor foram renderizados a partir da API. |
| RF13 | Parcial | TA-02, E2E-02 | Aumentos anômalos de erro e volume são consultáveis; não há consultas dedicadas para todas as falhas de autenticação, autorização e timeout citadas no requisito. |
| RF14 | Atendido | TA-04, TA-05, E2E-04 | Período atual e referências históricas são comparados com dados do backend. |
| RF15 | Atendido | TA-02, E2E-02, E2E-04 | Sinais e mudanças relevantes aparecem com severidade, delta, baseline e destaque visual. |
| RF16 | Atendido | TA-09, E2E-06, E2E-07 | Tipo, período, ocorrências, dispositivos, fontes e cronologia de sessão apoiam a investigação. |
| RF17 | Atendido | TA-06, TA-07, E2E-05 | Hipóteses publicadas são ordenadas, pontuadas e sustentadas por fatores e evidências, sem linguagem conclusiva. |

### 5.1 Síntese RF

| Situação | Total |
|---|---:|
| Atendido | 8 |
| Parcial | 2 |
| Não atendido | 0 |

## 6. Matriz de rastreabilidade das User Stories

| História | Classificação | Evidência executada | Lacuna ou atendimento observado |
|---|---|---|---|
| US01 | Atendido | TA-09, E2E-06 | Timeline única com seis fontes, origem e horário. |
| US02 | Parcial | E2E-03, E2E-07 | Dispositivo legado e moderno aparecem, mas os quatro filtros de plataforma/fabricante/modelo/versão não estão completos nem persistem globalmente. |
| US03 | Parcial | E2E-03 | Há volume por dispositivo e componente; não existe volume esperado nem limite textual de cobertura. |
| US04 | Não atendido | — | A interface não apresenta atraso de ingestão, recebidos, descartados e deduplicados por fonte/período. |
| US05 | Atendido | TA-04, TA-05, E2E-04 | Referência selecionável, valores atuais/históricos, mudança e eventos entre janelas. |
| US06 | Parcial | E2E-07 | A cronologia individual existe e é ordenada, porém falta localizar diretamente uma sessão e a fixture não cobre `screen_view`. |
| US07 | Parcial | TA-01, TA-08, E2E-03 | Há filtro cumulativo e recorte por dispositivo com volume/taxa; falta combinar modelo e região e manter esse recorte em todo o fluxo. |
| US08 | Atendido | E2E-07 | Sessão de dispositivo legado mostra modelo, versão do app, horário, tipos e código de erro. |
| US09 | Não atendido | — | Não há registro, anexo ou encaminhamento de chamado com filtros e evidências. |

### 6.1 Síntese US

| Situação | Total |
|---|---:|
| Atendido | 3 |
| Parcial | 4 |
| Não atendido | 2 |

## 7. Evidência de integração com o backend

| Área | Endpoints principais exercitados |
|---|---|
| Compartilhado | `GET /api/v1/clock` |
| Agora | `GET /api/v1/facets`, `GET /api/v1/signals` |
| Explorar | `GET /api/v1/series/facets`, `GET /api/v1/series/breakdown`, `GET /api/v1/series/timeseries` |
| Comparar | `GET /api/v1/changes`, `GET /api/v1/series/timeseries`, `GET /api/v1/references/stable-window` |
| Hipóteses | `GET /api/v1/hypotheses` |
| Timeline | `GET /api/v1/timeline` |
| Recorte | `GET /api/v1/series/crosstab`, `GET /api/v1/events`, `GET /api/v1/sessions/{session_id}` |

&emsp; Uma resposta HTTP 200 não é tratada isoladamente como prova. Os cenários E2E também verificam conteúdo específico semeado no banco — `playback-api`, `LG webOS 3.x`, `INC-E2E-001`, score `82`, `session-e2e` e `PLAYER-500` — após atravessar os adaptadores da interface.

## 8. Limitações atuais

- faltam filtros completos e busca direta para todos os atributos de RF08;
- o recorte regional de US07 não está implementado no fluxo integrado;
- cobertura esperada e saúde da ingestão (US03 e US04) não possuem visualização completa;
- a sessão individual é aberta a partir de uma amostra, sem campo de localização direta;
- o painel de ajustes do recorte continua intencionalmente informativo e mockado;
- não existe encaminhamento de chamado com evidências (US09);
- a evidência desta rodada é local; publicação e infraestrutura externa não foram validadas.

## 9. Referências internas

- [Requisitos](./requisitos.md)
- [Entendimento de UX e User Stories](./entendimento_ux.md)
- [Documentação do backend](./backend.md)
- [Contrato de rotas do frontend](../apps/basica/frontend/rotas-frontend.md)
- [Instruções do frontend](../apps/basica/frontend/README.md)
