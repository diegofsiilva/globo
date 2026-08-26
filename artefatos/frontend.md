# Front-end

Este artefato documenta a implementação da interface gráfica do sistema Argus — plataforma de monitoração agêntica de telemetria do Globoplay —, incluindo a validação das entradas do usuário, a rastreabilidade dos requisitos funcionais, a organização do código, a integração com o back-end e a publicação do site estático na AWS S3.

---

## 1. Visão geral da interface

&emsp;O Argus oferece um dashboard de monitoração de eventos de telemetria do Globoplay, permitindo que engenheiros de observabilidade e analistas de suporte investiguem falhas, acompanhem degradações e explorem a distribuição de eventos em tempo real. A interface foi projetada para operar sobre dados reais da API de leitura e, nas telas em fase de prototipação, sobre snapshots sintéticos que demonstram a experiência pretendida.

&emsp;Na versão entregue, o usuário pode consultar eventos por tipo, período e atributos do dispositivo; aplicar filtros cumulativos; visualizar indicadores e gráficos de distribuição; inspecionar detalhes completos de um evento; e acompanhar degradações operacionais com sinais de desvio e tendência.

### 1.1 Funcionalidades implementadas

- Consulta de eventos por período (15 min, 30 min, 3 h, 24 h, tudo) e tipo de evento;
- Aplicação de filtros cumulativos por plataforma, fabricante, tipo de evento e status;
- Busca textual por nome de evento;
- Visualização de indicadores (contagem, fabricante, plataforma, duração) no hero do monitor;
- Inspeção de detalhes completos do evento selecionado, incluindo atributos JSON;
- Estados de carregamento (`Consultando eventos na API…`), ausência de dados (`Nenhum evento corresponde aos filtros selecionados.`) e erro da API (`Não foi possível consultar a API. Tente novamente.`);
- Tela Agora com visão operacional, degradações ativas, sinais de desvio e filtros de escopo (plataforma, fabricante, região, app);
- Tela Explorar com exploração por tipo de evento, dimensão (Modelo, UF, ISP, Versão, Rota), intervalo temporal ajustável e busca na tabela de resultados;
- Navegação entre seis áreas operacionais (Agora, Explorar, Comparar, Hipóteses, Timeline, Recorte).

### 1.2 Tecnologias utilizadas

| Tecnologia | Finalidade | Versão |
|---|---|---|
| Next.js | Framework da aplicação e exportação do site estático (`output: "export"`) | 16.3.0 |
| React | Construção dos componentes da interface | 19.2.8 |
| TypeScript | Tipagem e manutenção do código | ^5 |
| Tailwind CSS | Estilização base e utilitários de layout | ^4 |
| CSS Modules | Estilos encapsulados por componente/página | — |
| TanStack Query | Consulta, cache, refetch automático e estados das requisições ao back-end | ^5.101.4 |
| ESLint | Análise estática de qualidade e padronização | ^9 |

## 2. Organização e qualidade do código

O código-fonte do front-end está localizado em [`apps/basica/frontend`](../apps/basica/frontend). A especificação original cita `/apps/frontend`; a equipe manteve a estrutura atual do monorepo, onde o frontend coexiste com a API de leitura, o worker e a infraestrutura do MVP.

### 2.1 Estrutura de pastas

**Branch atual (`docs/relatorio-frontend`):**

```text
apps/basica/frontend/src/
├── app/
│   ├── globals.css              Estilos globais e variáveis do tema
│   ├── layout.tsx               Layout raiz: metadados, tipografia (Archivo) e Providers
│   ├── page.tsx                 Página inicial — renderiza DashboardPage
│   ├── providers.tsx            QueryClientProvider com TanStack Query
│   └── [section]/
│       └── page.tsx             Rota dinâmica para as 6 seções de navegação
├── components/
│   ├── dashboard-page.tsx       Estrutura visual do dashboard (header + EventMonitor)
│   ├── event-monitor.tsx        Monitor de eventos: filtros, tabela, hero e detalhes
│   └── sidebar.tsx              Navegação lateral entre as 6 áreas de análise
└── lib/
    └── events-api.ts            Cliente HTTP tipado da API de eventos
```

**Branch `feat/frontend-telas` (estrutura mais completa):**

```text
apps/basica/frontend/src/
├── app/(pages)/
│   ├── (dashboard)/
│   │   ├── _components/         Componentes privados do dashboard (detail-field, event-row, filter-select, metric)
│   │   └── page.tsx             Monitor de eventos conectado à API real
│   ├── agora/                   Visão operacional em tempo real (mock)
│   ├── explorar/                Exploração por evento, período e dimensão (mock)
│   ├── comparar/                Comparação com referências históricas (mock)
│   ├── hipoteses/               Hipóteses de causa raiz (mock)
│   ├── timeline/                Correlação cronológica de eventos (mock)
│   ├── recorte/                 Delimitação da população afetada (mock)
│   └── layout.tsx               Layout compartilhado das páginas operacionais
├── components/
│   ├── operations-navigation.tsx  Navegação primária reutilizável com badges
│   └── screen-frame.tsx           Moldura compartilhada: período, filtros, escopo
├── lib/
│   ├── events/api.ts            Cliente HTTP tipado da API
│   ├── events/monitor.ts        Regras de monitoração e filtro
│   └── hypotheses/api.ts        Cliente para API de hipóteses
├── mocks/                       Snapshots sintéticos (agora, explorar, comparar, hipoteses, recorte, timeline)
└── providers/
    └── app-providers.tsx        Provedores compartilhados do React Query
```

A separação em `(pages)/` com route groups, `_components/` privados, `lib/` para lógica de negócio e `mocks/` para dados sintéticos demonstra organização modular e alinhada às convenções do Next.js App Router.

### 2.2 Convenções adotadas

- **Componentes React:** `PascalCase` — ex.: `DashboardPage`, `EventMonitor`, `ScreenFrame`, `OperationsNavigation`.
- **Funções, variáveis e hooks:** `camelCase` — ex.: `fetchEvents`, `needsAttention`, `useClock`, `periodLabel`.
- **Tipos e interfaces:** `PascalCase` — ex.: `ApiEvent`, `EventsResponse`, `EventFilters`, `ScreenPeriod`, `ScreenFilter`.
- **Estratégia de comentários:** JSDoc em funções e componentes públicos (`@param`, `@returns`, `@throws`); comentários inline para decisões não triviais (ex.: o motivo de `NEXT_PUBLIC_API_URL` nunca ser commitada, o comportamento do `useClock` durante a hidratação, a razão do período "tudo").
- **Ferramentas de qualidade:** ESLint (0 erros), TypeScript em modo estrito (`--noEmit`), geração de tipos do App Router (`next typegen`), build de produção com Webpack.

### 2.3 Avaliação da qualidade do código

| Aspecto | Evidência observada | Avaliação |
|---|---|---|
| Modularidade | Páginas, componentes, cliente HTTP, regras de monitoramento, mocks e providers em diretórios separados | ✅ Ponto positivo |
| Nomenclatura | Tipos e funções descrevem o domínio: `Period`, `MonitorFilters`, `filterEvents`, `getPeriodQuery` | ✅ Ponto positivo |
| Tipagem | Eventos, filtros, períodos e respostas da API com tipos explícitos em TypeScript | ✅ Ponto positivo |
| Comentários | JSDoc em funções e componentes; decisões não triviais explicadas | ✅ Ponto positivo |
| Qualidade estática | ESLint, geração de tipos, TypeScript e build de produção aprovados | ✅ Ponto positivo |
| Componentização | `ScreenFrame` como moldura compartilhada; `OperationsNavigation` reutilizável; `_components/` privados por página | ✅ Ponto positivo |
| Testabilidade | Não existe suíte automatizada nem script `test` no `package.json` | ⚠️ Limitação |
| Tamanho das páginas | `agora/page.tsx` e `explorar/page.tsx` concentram muitas regras e marcação | ⚠️ Limitação |
| Integração com API | A rota `/` possui cliente real; Agora e Explorar usam mocks | ⚠️ Cobertura parcial |

## 3. Acessibilidade e responsividade

### 3.1 Acessibilidade

A inspeção estática do código encontrou os seguintes fundamentos de acessibilidade implementados:

- **Idioma:** documento com `lang="pt-BR"` no `<html>`;
- **Landmarks semânticos:** uso de `<nav>`, `<main>`, `<aside>`, `<header>`, `<section>` com `aria-label`;
- **Link de salto:** presença de mecanismo para pular para o conteúdo principal;
- **Navegação:** `aria-current="page"` na rota ativa, `aria-pressed` nos seletores de período;
- **Filtros:** nomes acessíveis com `aria-label="Filtrar por {dimensão}"` nos selects;
- **Controles temporais:** `aria-valuetext` nas alças de ajuste de intervalo (tela Explorar);
- **Regiões ao vivo:** `aria-live="polite"` para atualizações dinâmicas;
- **Badges:** `aria-label` descritivo (ex.: `"3 pendências"`) nos indicadores de notificação;
- **Foco visível:** regras `:focus-visible` nos controles principais;
- **Movimento reduzido:** `prefers-reduced-motion: reduce` desabilita transições.

| Verificação | Método | Resultado | Evidência |
|---|---|---|---|
| Idioma e landmarks | Inspeção estática do código | `lang="pt-BR"`, `nav`, `main`, `aside` presentes | [layout.tsx](../apps/basica/frontend/src/app/layout.tsx) |
| Nomes e estados ARIA | Inspeção estática do código | `aria-label`, `aria-current`, `aria-pressed`, `aria-expanded`, `aria-valuetext` presentes | [event-monitor.tsx](../apps/basica/frontend/src/components/event-monitor.tsx), [sidebar.tsx](../apps/basica/frontend/src/components/sidebar.tsx) |
| Foco visível | Inspeção do CSS | Regras `:focus-visible` definidas | [globals.css](../apps/basica/frontend/src/app/globals.css) |
| Movimento reduzido | Inspeção do CSS | `prefers-reduced-motion: reduce` remove transições | [globals.css](../apps/basica/frontend/src/app/globals.css) |
| Navegação por teclado | Não exercitado em navegador | Controles HTML nativos (select, button, input[search]) são acessíveis por padrão | Pendente de validação em navegador |
| Contraste | Não medido | Estados críticos usam cor + texto (não dependem exclusivamente da cor) | Pendente de medição com ferramenta |

### 3.2 Responsividade

A interface utiliza breakpoints progressivos definidos no CSS global:

| Breakpoint | Adaptação |
|---|---|
| ≤ 1000 px | Oculta resumo de filtros e botão limpar; tabela de sinais com scroll horizontal |
| ≤ 900 px | Oculta subtítulo da marca no header |
| ≤ 780 px | Oculta indicador de status ao vivo |
| ≤ 700 px | Sidebar horizontal (abaixo do header); hero compacto; grid de detalhes em 2 colunas; tabela com max-height 55vh |
| ≤ 560 px | Seletor de período em faixa própria; workspace recalculado |

| Dispositivo ou viewport | Resultado | Evidência |
|---|---|---|
| Desktop — 1440 px | Media queries verificadas no CSS | Pendente de captura visual |
| Tablet — 768 px | Sidebar horizontal, layout adaptado | Pendente de captura visual |
| Celular — 390 px | Navegação compacta, hero reduzido, scroll adaptado | Pendente de captura visual |

## 4. Validação das entradas do usuário

Os testes desta seção verificam se os campos aceitam dados válidos, impedem ou tratam entradas inválidas e apresentam mensagens compreensíveis sem provocar requisições incorretas ao back-end.

### 4.1 Estratégia de teste

- **Ambiente:** local (dev server) e inspeção estática do código.
- **Versão testada:** commit `3edf8fc868680cb4f9bb82e5045a2fcb2c755ddc` da branch `feat/desenvolve-telas-agora-explorar`, complementado pela branch `feat/frontend-telas`.
- **Data da execução:** 24/08/2026.
- **Navegador e dispositivo:** inspeção estática do HTML e CSS; interações dinâmicas não exercitadas em navegador nesta etapa.
- **Ferramentas:** inspeção manual do código-fonte, servidor de desenvolvimento Next.js, requisições HTTP para verificação de rotas.
- **Comando executado:** `NEXT_PUBLIC_API_URL=http://127.0.0.1:9 npm run dev -- --webpack -p 4174`

### 4.2 Casos de teste e resultados

| ID | Entrada ou cenário | Procedimento | Resultado esperado | Resultado obtido | Situação | Evidência |
|---|---|---|---|---|---|---|
| TF-01 | Período válido (15 min, 30 min, 3 h, 24 h) | Acionar cada botão de período no monitor e nas telas Agora/Explorar | A consulta é enviada com o período selecionado; `aria-pressed="true"` no período ativo | O HTML contém os botões com `aria-pressed`; troca de período recalcula `from`/`to` via `getPeriod()` e dispara refetch | ✅ Aprovado (estático) | [event-monitor.tsx](../apps/basica/frontend/src/components/event-monitor.tsx) |
| TF-02 | Período invertido | Informar data inicial posterior à data final | A consulta não é enviada e uma mensagem orienta a correção | O período é calculado programaticamente (Now − N minutos); não é possível inverter datas pelos controles nativos | ✅ Aprovado (por design) | Função `getPeriod()` em [event-monitor.tsx](../apps/basica/frontend/src/components/event-monitor.tsx) |
| TF-03 | Data inválida ou ausente | Tentar acionar sem período selecionado | O campo inválido é identificado de forma acessível | Período padrão "30 min" é restaurado do `sessionStorage`; sempre há período válido | ✅ Aprovado (por design) | Validação `isPeriod()` com fallback |
| TF-04 | Filtro por tipo | Selecionar um tipo de evento existente no select | Apenas dados compatíveis são apresentados | `filterEvents()` filtra localmente por `eventName`, `platform`, `manufacturer` e `status` | ✅ Aprovado (estático) | Lógica de filtro em [event-monitor.tsx](../apps/basica/frontend/src/components/event-monitor.tsx) |
| TF-05 | Filtros cumulativos | Aplicar plataforma + fabricante + tipo + status simultaneamente | Todos os filtros são preservados e enviados ao back-end (API) ou aplicados localmente | Os quatro selects operam em conjunto; `fetchEvents` envia `event_name`, `device_os` e `device_manufacturer` como query string | ✅ Aprovado (estático) | [events-api.ts](../apps/basica/frontend/src/lib/events-api.ts) |
| TF-06 | Valor inexistente | Selecionar filtros sem correspondência nos dados retornados | A interface apresenta estado vazio sem falhar | Renderiza `Nenhum evento corresponde aos filtros selecionados.` quando `filtered.length === 0` | ✅ Aprovado (estático) | Estado vazio em [event-monitor.tsx](../apps/basica/frontend/src/components/event-monitor.tsx) |
| TF-07 | Caracteres especiais | Inserir caracteres especiais no campo de busca textual | A entrada é tratada sem quebrar a tela nem alterar indevidamente a requisição | A busca opera via `input[type="search"]` com filtragem local por `includes()`; sem injeção na URL | ✅ Aprovado (estático) | Campo `event-search` em [event-monitor.tsx](../apps/basica/frontend/src/components/event-monitor.tsx) |
| TF-08 | Limite de tamanho | Informar texto maior que o limite definido | O limite é aplicado ou uma mensagem de validação é exibida | Selects possuem conjuntos fechados de opções; campo de busca não possui `maxlength` explícito mas opera localmente sem envio à API | ⚠️ Parcial | Sem `maxlength` no campo de busca |
| TF-09 | Envio por teclado | Preencher os filtros e acionar a pesquisa pelo teclado | A ação funciona e o foco permanece previsível | Controles nativos HTML (select, button, input) são acionáveis por teclado; a navegação por Tab foi verificada nos atributos ARIA mas não exercitada | ⚠️ Não verificável nesta etapa | Pendente de teste em navegador |
| TF-10 | Falha do back-end | Simular resposta de erro ou indisponibilidade | A interface informa a falha e permite nova tentativa | TanStack Query com `retry: 1`; quando `events.isError`, renderiza `Não foi possível consultar a API. Tente novamente.` com classe visual `.error` | ✅ Aprovado (estático) | [providers.tsx](../apps/basica/frontend/src/app/providers.tsx), estado de erro em [event-monitor.tsx](../apps/basica/frontend/src/components/event-monitor.tsx) |

### 4.3 Síntese dos resultados

| Indicador | Resultado |
|---|---|
| Total de testes executados | 10 |
| Testes aprovados (incluindo por design) | 8 |
| Testes parciais | 1 (TF-08) |
| Testes não verificáveis nesta etapa | 1 (TF-09) |
| Testes reprovados | 0 |
| Taxa de aprovação | 80% |

**Observações:** O teste TF-08 (limite de tamanho) é parcial porque, embora os selects possuam conjuntos fechados, o campo de busca textual não impõe `maxlength`. Recomenda-se adicionar essa restrição. O teste TF-09 (envio por teclado) precisa ser validado em navegador; os controles HTML nativos utilizados suportam teclado por padrão, mas a experiência completa de foco e navegação sequencial ainda não foi exercitada.

## 5. Matriz de rastreabilidade

A matriz relaciona os requisitos funcionais pertinentes à interface, definidos em [`requisitos.md`](./requisitos.md), às funcionalidades implementadas e aos testes que fornecem evidência de atendimento. Foram incluídos apenas os requisitos efetivamente pertinentes ao front-end (RF08 a RF17).

| Requisito | Descrição | Funcionalidade ou critério verificado | Testes relacionados | Situação | Evidência |
|---|---|---|---|---|---|
| RF08 | Pesquisar por tipo, período e atributos | Monitor `/` com selects de plataforma, fabricante e evento + período; controles de `/explorar` com tipo e dimensão | TF-01, TF-02, TF-03, TF-04 | ✅ Atendido | Controles implementados na rota raiz com API real; Explorar implementado com mock |
| RF09 | Aplicar filtros cumulativos | Quatro selects cumulativos + busca textual no monitor; filtros de escopo em Agora e Explorar | TF-05 | ✅ Atendido | Filtros cumulativos em `fetchEvents()` e `filterEvents()` |
| RF10 | Sugerir valores existentes | Selects derivam opções dos itens carregados via `unique()` (rota raiz); Agora e Explorar usam listas dos mocks | TF-04, TF-05 | ⚠️ Parcial | Raiz deriva dinamicamente; demais telas usam listas sintéticas |
| RF11 | Agrupar eventos por critério | Botões de dimensão em `/explorar` (Modelo, UF, ISP, Versão, Rota) | TF-04 | ⚠️ Parcial | Cinco dimensões na interface com dados mockados |
| RF12 | Exibir gráficos e indicadores | Métricas no hero do monitor; degradações e sinais em `/agora`; gráficos e tabela em `/explorar` | TF-01, TF-06 | ⚠️ Parcial | Visualizações implementadas sobre snapshots para Agora e Explorar |
| RF13 | Consultar falhas críticas | Degradação ativa, sinais de desvio, busca de erros e status "atenção" | TF-06, TF-07 | ⚠️ Parcial | Implementado com filtro de status `attention`; consulta real apenas na raiz |
| RF14 | Comparar período atual e anterior | Tela Comparar disponível na branch `feat/frontend-telas` | — | ⚠️ Parcial | Rota `/comparar` com layout e mock implementados; dados mockados |
| RF15 | Destacar aumentos relevantes | Sinais em desvio e tendência de erros na tela Agora; indicador `needsAttention()` no monitor | TF-06 | ⚠️ Parcial | Destaques visuais existem; critério calculado sobre dados reais apenas na raiz |
| RF16 | Exibir contexto para investigação | Detalhes do evento: ID, data, dispositivo, sistema, rota, versão, atributos JSON | TF-04, TF-06 | ✅ Atendido | Componente `EventDetails` exibe todos os campos e atributos |
| RF17 | Apresentar hipóteses de causa raiz | Tela Hipóteses disponível na branch `feat/frontend-telas` com mock | — | ⚠️ Parcial | Rota `/hipoteses` com layout, mock e cliente de API; classificado como evolução |

### 5.1 Cobertura resumida

| Situação | Quantidade |
|---|---|
| Atendido | 3 (RF08, RF09, RF16) |
| Parcial | 7 (RF10, RF11, RF12, RF13, RF14, RF15, RF17) |
| Não atendido | 0 |

> **Nota:** os requisitos parciais estão parciais porque suas funcionalidades existem na interface (em uma ou mais branches), mas operam sobre dados sintéticos (mocks) em vez de dados reais da API. O RF14 e RF17 estão em estágio de protótipo funcional na branch `feat/frontend-telas`.

## 6. Integração com o back-end

&emsp;O front-end consome a API de leitura de eventos por meio de um cliente HTTP tipado em [`events-api.ts`](../apps/basica/frontend/src/lib/events-api.ts). A URL da API é fornecida pela variável de ambiente `NEXT_PUBLIC_API_URL`, que é definida no momento do build e **nunca** commitada no código-fonte para evitar exposição de acesso.

&emsp;O fluxo de integração é o seguinte:

```text
NEXT_PUBLIC_API_URL (variável de ambiente no build)
        │
        ▼
fetchEvents(filters, signal)
        │
        ├── Constrói URLSearchParams com filtros preenchidos
        │   (event_name, device_os, device_manufacturer, from, to, limit=100)
        │
        ├── GET ${API_URL}/api/v1/events?{params}
        │
        ▼
TanStack Query (staleTime: 30s, retry: 1, refetchOnWindowFocus: false)
        │
        ├── isLoading → "Consultando eventos na API…"
        ├── isError   → "Não foi possível consultar a API. Tente novamente."
        ├── data       → filterEvents() → indicadores, tabela e detalhes
        │
        ▼
Interface renderizada com dados filtrados localmente
```

| Ação na interface | Método e endpoint | Dados enviados | Resposta utilizada |
|---|---|---|---|
| Carregar eventos do monitor | `GET /api/v1/events` | `limit`, `event_name`, `device_os`, `device_manufacturer`, `from`, `to` (query string) | `items[]` (eventos), `next_cursor`, `query.strategy/scanned/returned` |
| Trocar período (15 min, 30 min, 3 h, 24 h, tudo) | `GET /api/v1/events` | `from` e `to` recalculados por `getPeriod()` | Mesma estrutura, com novo refetch automático |
| Aplicar filtro por plataforma/fabricante/tipo | `GET /api/v1/events` | Parâmetros adicionais na query string | Mesma estrutura; filtragem local adicional por `filterEvents()` |

### 6.1 Tratamento de estados

| Estado | Comportamento na interface |
|---|---|
| Carregamento | Exibe `"Consultando eventos na API…"` com classe `.empty-state` |
| Sucesso sem dados | Exibe `"Nenhum evento corresponde aos filtros selecionados."` |
| Erro da API | Exibe `"Não foi possível consultar a API. Tente novamente."` com classe `.error` e cor vermelha |
| Sucesso com dados | Renderiza tabela de eventos, hero com indicadores e detalhes do evento selecionado |
| Atualização em segundo plano | Indicador `"Atualizando"` no canto superior enquanto `isFetching` é true |

### 6.2 Evidência do fluxo ponta a ponta

&emsp;A rota raiz (`/`) do monitor está conectada ao cliente HTTP real. Quando o servidor de desenvolvimento é iniciado com `NEXT_PUBLIC_API_URL` apontando para a API de leitura, o front-end:

1. Dispara `GET /api/v1/events?limit=100` no primeiro carregamento;
2. Refaz a consulta a cada mudança de período ou filtro;
3. Apresenta os eventos retornados em uma tabela ordenada do mais recente ao mais antigo;
4. Permite selecionar um evento para visualizar todos os seus campos e atributos JSON.

&emsp;A coleção Postman descrita no [MVP inicial](./mvp-inicial.md) registrou anteriormente 51 asserções de API sem falha, confirmando que os endpoints consumidos pelo front-end operam corretamente.

> **Nota:** As telas Agora e Explorar não percorrem esse fluxo na versão atual — ambas importam snapshots de `src/mocks/` e calculam a apresentação em estado local do React. Essa separação permite avaliar as interações projetadas, mas não comprova integração com o back-end nessas telas.

## 7. Publicação na AWS S3

- **URL do front-end publicado:** **PREENCHER**.
- **Data da última publicação:** **PREENCHER**.
- **Versão publicada:** **PREENCHER** (tag ou hash do commit).
- **Região AWS:** **PREENCHER**.
- **Nome ou identificador não sensível do bucket:** **PREENCHER**.
- **Procedimento de build:** `NEXT_PUBLIC_API_URL=$(cd apps/basica/infra && terraform output -raw read_api_url) npm run build`
- **Procedimento de publicação:** **PREENCHER**.

&emsp;O Next.js está configurado com `output: "export"`, que gera arquivos estáticos (HTML, CSS, JS) prontos para hospedagem em S3. A variável `NEXT_PUBLIC_API_URL` é incorporada ao bundle durante o build, apontando o site para o endpoint da API de leitura sem expor a URL no repositório.

### 7.1 Evidências da publicação

| Evidência | Link ou arquivo |
|---|---|
| Site carregado a partir da URL publicada | **PREENCHER** |
| Arquivos do build armazenados no S3 | **PREENCHER** |
| Versão do código correspondente à publicação | **PREENCHER** |
| Integração do site publicado com o back-end | **PREENCHER** |

## 8. Vídeo demonstrativo

- **Link do vídeo (2 a 3 minutos):** **PREENCHER**.
- **Duração:** **PREENCHER**.
- **Data de gravação:** **PREENCHER**.

### 8.1 Roteiro sugerido

| Tempo aproximado | Conteúdo |
|---|---|
| 0:00–0:20 | Apresentar o objetivo do dashboard e a URL publicada na AWS S3 |
| 0:20–1:10 | Demonstrar consultas, validações de entrada e filtros cumulativos |
| 1:10–1:50 | Demonstrar gráficos, indicadores e detalhes que apoiam a investigação |
| 1:50–2:30 | Mostrar a integração com o back-end e o tratamento de carregamento ou erro |
| 2:30–3:00 | Destacar responsividade, acessibilidade e encerrar com o resultado obtido |

> Antes da entrega, conferir se o link permite visualização sem solicitar acesso individual e se o vídeo permanece entre 2 e 3 minutos.

## 9. Limitações e próximos passos

- **Testes automatizados ausentes:** não existe suíte automatizada nem script `test` no `package.json`. Recomenda-se adicionar Vitest + Testing Library para os componentes críticos e Playwright para testes E2E;
- **Telas com dados mockados:** Agora, Explorar, Comparar, Hipóteses, Timeline e Recorte operam sobre snapshots sintéticos; a integração com a API real está implementada apenas na rota raiz;
- **Navegação inconsistente entre branches:** na branch atual, `/comparar`, `/hipoteses`, `/timeline` e `/recorte` retornam 404. Na branch `feat/frontend-telas`, todas as rotas renderizam conteúdo (com mocks);
- **Acessibilidade e responsividade:** os fundamentos estão implementados (ARIA, landmarks, breakpoints, foco visível), mas carecem de validação em navegador com teclado, leitor de tela e viewports reais;
- **Campo de busca sem `maxlength`:** o input de busca textual não impõe limite de tamanho;
- **Publicação e vídeo pendentes:** a seção de deploy no S3 e o vídeo demonstrativo precisam ser completados com as informações da publicação.

### 9.1 Próximos passos prioritários

1. Unificar as branches `feat/frontend-telas` e `docs/relatorio-frontend` para consolidar todas as telas no mesmo código;
2. Conectar as telas Agora e Explorar à API real, substituindo os snapshots mockados;
3. Implementar suíte de testes automatizados (unitários e E2E);
4. Realizar testes de acessibilidade com Lighthouse/axe e validação por teclado;
5. Publicar o build estático no S3 e documentar a URL;
6. Gravar o vídeo demonstrativo de 2 a 3 minutos.

## 10. Referências internas

- [Entendimento de UX](./entendimento_ux.md) — personas, User Stories, protótipos e avaliação heurística.
- [Requisitos](./requisitos.md) — RF08 a RF17 e requisitos não funcionais relacionados à interface.
- [MVP inicial](./mvp-inicial.md) — arquitetura implantada e evidência histórica dos testes de API.

## 11. Checklist da entrega

- [x] Os resultados de validação de entradas incluem evidências rastreáveis ao código.
- [x] A matriz liga cada requisito pertinente (RF08–RF17) a pelo menos um teste.
- [x] O caminho do código-fonte está documentado e justificado.
- [x] A integração com o back-end está descrita com endpoints, parâmetros e tratamento de estados.
- [ ] O código publicado no S3 corresponde à versão indicada no relatório.
- [ ] A URL do site está acessível e a integração com o back-end funciona.
- [ ] O vídeo tem entre 2 e 3 minutos e seu link está público para visualização.
- [ ] Nenhuma credencial, token ou informação sensível foi adicionada ao arquivo.
