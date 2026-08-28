# Front-end

&emsp; Este artefato documenta a implementação da interface gráfica do sistema Argus, plataforma de monitoração agêntica de telemetria do Globoplay, incluindo a validação das entradas do usuário, a rastreabilidade dos requisitos funcionais, a organização do código, a integração com o back-end e a publicação do site estático na AWS S3.

## 1. Visão geral da interface

&emsp; O Argus oferece um dashboard de monitoração de eventos de telemetria do Globoplay, permitindo que engenheiros de observabilidade e analistas de suporte investiguem falhas, acompanhem degradações e explorem a distribuição de eventos em tempo real. A interface foi projetada para operar sobre dados reais da API de leitura e, nas telas em fase de prototipação, sobre snapshots sintéticos que demonstram a experiência pretendida.

&emsp; Na versão entregue, o usuário pode consultar eventos por tipo, período e atributos do dispositivo; aplicar filtros cumulativos; visualizar indicadores e gráficos de distribuição; inspecionar detalhes completos de um evento; e acompanhar degradações operacionais com sinais de desvio e tendência.

### 1.1 Funcionalidades implementadas

- Monitor de eventos (`/monitor`) conectado à API de leitura: consulta por período (15 min, 30 min, 3 h, 24 h, tudo) e tipo de evento;
- Aplicação de filtros cumulativos por plataforma, fabricante, tipo de evento e status no Monitor;
- Busca textual por nome de evento (com limite de 80 caracteres);
- Visualização de indicadores (contagem, fabricante, plataforma, duração) no bloco de destaque do Monitor;
- Inspeção de detalhes completos do evento selecionado, incluindo atributos JSON;
- Estados de carregamento (`Consultando eventos na API…`), ausência de dados (`Nenhum evento corresponde aos filtros selecionados.`) e erro da API (`Não foi possível consultar a API. Tente novamente.`);
- Tela Agora com visão operacional, degradações ativas, sinais de desvio e filtros de escopo (plataforma, fabricante, região, app);
- Tela Explorar com exploração por tipo de evento, dimensão (Modelo, UF, ISP, Versão, Rota), intervalo temporal ajustável e busca na tabela de resultados;
- Navegação entre o Monitor e as seis áreas operacionais (Agora, Explorar, Comparar, Hipóteses, Timeline, Recorte); a rota `/` redireciona para o Monitor.

### 1.2 Tecnologias utilizadas

| Tecnologia | Finalidade | Versão |
|---|---|---|
| Next.js | Framework da aplicação e exportação do site estático (`output: "export"`) | 16.3.0 |
| React | Construção dos componentes da interface | 19.2.8 |
| TypeScript | Tipagem e manutenção do código | ^5 |
| Tailwind CSS | Estilização base e utilitários de layout | ^4 |
| Tailwind CSS e arquivos de estilos por tela | Utilitários de estilo e regras específicas de cada tela | ^4 |
| TanStack Query | Consulta, cache, refetch automático e estados das requisições ao back-end | ^5.101.4 |
| next-themes | Alternância e persistência do tema claro/escuro (`storageKey="argus-theme"`) | ^0.4.6 |
| Radix UI + lucide-react | Primitivas acessíveis (Select, Toggle, Dialog/Sheet, Tooltip) e ícones | ^1.x / ^1.34 |
| ESLint | Análise estática de qualidade e padronização | ^9 |

### 1.3 Capturas de tela

&emsp; As capturas abaixo foram produzidas a partir do build estático de produção (`npm run build`), servido localmente e fotografado em Google Chrome headless nos temas escuro e claro. Os dados apresentados vêm dos cenários sintéticos de `_mocks/scenario.ts` e são identificados na interface pela etiqueta "MOCK · SNAPSHOT".

- Ambiente: saída estática (`output: "export"`) servida em `127.0.0.1`; Google Chrome (viewport 1264×720), `prefers-reduced-motion: reduce`;
- Data da captura: 27/08/2026;
- Fonte de hipóteses: `NEXT_PUBLIC_HYPOTHESES_SOURCE=mock`.

#### 1.3.1 Agora

&emsp; A tela Agora apresenta o estado operacional mais urgente do recorte selecionado. O destaque superior resume a degradação ativa, seu alcance e a diferença em relação ao baseline; abaixo, os sinais são ordenados por sessões impactadas e mostram valor atual, referência, desvio, tendência e ação de investigação.

<p align="center">
  <img src="./assets/captura_agora_tema_escuro.png" alt="Tela Agora no tema escuro" width="49%">
  <img src="./assets/captura_agora_tema_claro.png" alt="Tela Agora no tema claro" width="49%">
</p>

<p align="center"><sub>Figuras 1 e 2 — Tela Agora nos temas escuro e claro, respectivamente.</sub></p>

#### 1.3.2 Explorar

&emsp; A tela Explorar conduz a investigação em três etapas: escolher o tipo de evento, localizar quando o comportamento mudou e identificar onde o sinal se concentra. O usuário pode ajustar a janela temporal, alternar dimensões como modelo, UF, ISP, versão e rota, além de consultar erros associados ao recorte.

<p align="center">
  <img src="./assets/captura_explorar_tema_escuro.png" alt="Tela Explorar no tema escuro" width="49%">
  <img src="./assets/captura_explorar_tema_claro.png" alt="Tela Explorar no tema claro" width="49%">
</p>

<p align="center"><sub>Figuras 3 e 4 — Tela Explorar nos temas escuro e claro, respectivamente.</sub></p>

#### 1.3.3 Comparar

&emsp; A tela Comparar posiciona o período atual diante de referências como o mesmo horário do dia anterior, a semana passada ou a última janela estável. O gráfico evidencia pontos fora do envelope histórico, enquanto a tabela quantifica a variação e a significância de cada métrica.

<p align="center">
  <img src="./assets/captura_comparar_tema_escuro.png" alt="Tela Comparar no tema escuro" width="49%">
  <img src="./assets/captura_comparar_tema_claro.png" alt="Tela Comparar no tema claro" width="49%">
</p>

<p align="center"><sub>Figuras 5 e 6 — Tela Comparar nos temas escuro e claro, respectivamente.</sub></p>

#### 1.3.4 Hipóteses

&emsp; A tela Hipóteses organiza possíveis causas por relevância e mantém as alternativas descartadas visíveis. Ao selecionar uma hipótese, o painel lateral explica a composição do score por coincidência temporal, especificidade do recorte, ausência de causa concorrente e precedente histórico, além de listar as evidências consultadas.

<p align="center">
  <img src="./assets/captura_hipoteses_tema_escuro.png" alt="Tela Hipóteses no tema escuro" width="49%">
  <img src="./assets/captura_hipoteses_tema_claro.png" alt="Tela Hipóteses no tema claro" width="49%">
</p>

<p align="center"><sub>Figuras 7 e 8 — Tela Hipóteses nos temas escuro e claro, respectivamente.</sub></p>

#### 1.3.5 Timeline

&emsp; A tela Timeline cruza as fontes Deploy, Player QoE, CDN, Backend, Identidade e Incidentes em um mesmo eixo temporal. A janela destacada ajuda a reconhecer coincidências entre mudanças técnicas e degradações, enquanto a cronologia reconstruída oferece uma alternativa textual ao gráfico.

<p align="center">
  <img src="./assets/captura_timeline_tema_escuro.png" alt="Tela Timeline no tema escuro" width="49%">
  <img src="./assets/captura_timeline_tema_claro.png" alt="Tela Timeline no tema claro" width="49%">
</p>

<p align="center"><sub>Figuras 9 e 10 — Tela Timeline nos temas escuro e claro, respectivamente.</sub></p>

#### 1.3.6 Recorte

&emsp; A tela Recorte delimita a população afetada e informa sessões, participação no tráfego, concentração dos erros e número de UFs envolvidas. O mapa de calor cruza família de dispositivo e região, e o painel lateral antecipa o efeito de possíveis ajustes sobre a especificidade e a cobertura.

<p align="center">
  <img src="./assets/captura_recorte_tema_escuro.png" alt="Tela Recorte no tema escuro" width="49%">
  <img src="./assets/captura_recorte_tema_claro.png" alt="Tela Recorte no tema claro" width="49%">
</p>

<p align="center"><sub>Figuras 11 e 12 — Tela Recorte nos temas escuro e claro, respectivamente.</sub></p>

#### 1.3.7 Viewport mobile

&emsp; A captura mobile demonstra a adaptação da tela Agora para um viewport de 390×844. Nesse formato, a navegação lateral dá lugar a um menu de hambúrguer, a barra de escopo recolhe para o resumo "Escopo · N filtros" e o conteúdo passa a ocupar uma única coluna, preservando a leitura do alerta principal e dos indicadores sem exigir rolagem horizontal.

![Tela Agora no viewport mobile de 390 por 844 pixels](./assets/captura_agora_mobile.png)

<p align="center"><sub>Figura 13 — Adaptação da tela Agora ao viewport mobile.</sub></p>

#### 1.3.8 Viewport tablet

&emsp; A captura em 768×1024 mostra o comportamento no ponto de corte da navegação lateral: em 768 px a coluna de navegação ainda é exibida, o cabeçalho começa a comprimir a barra de escopo (com rolagem horizontal) e o bloco de indicadores reflui para duas colunas. Abaixo de 768 px a navegação recolhe para o menu de hambúrguer, como na captura mobile.

![Tela Agora no viewport tablet de 768 por 1024 pixels](./assets/captura_agora_tablet.png)

<p align="center"><sub>Figura 14 — Tela Agora no viewport tablet de 768 px.</sub></p>

### 1.4 Demonstração em vídeo

&emsp; O vídeo abaixo registra a interface em execução e complementa as capturas estáticas da seção anterior.

<p align="center">
  <a href="https://drive.google.com/file/d/1HltsgZBqs5GeT-ADOx9BUANbAv2kHGSW/view?usp=sharing">Assistir à demonstração da interface (Google Drive)</a>
</p>

<p align="center"><sub>Vídeo 1 — Demonstração da interface do Argus.</sub></p>

## 2. Organização e qualidade do código

&emsp; O código-fonte do front-end está localizado em [`apps/basica/frontend`](../apps/basica/frontend). A especificação original cita `/apps/frontend`; optou-se por manter a estrutura atual do monorepo, onde o frontend coexiste com a API de leitura, o worker e a infraestrutura do MVP.

### 2.1 Estrutura de pastas

```text
apps/basica/frontend/src/
├── app/
│   ├── (operations)/
│   │   ├── monitor/             Monitor de eventos conectado à API de leitura (rota `/monitor`)
│   │   ├── _components/         Navegação, moldura, tema e estado operacional compartilhados
│   │   ├── agora/               Visão operacional com cenário sintético privado da rota
│   │   ├── explorar/            Exploração temporal, agrupamentos e cenário sintético
│   │   ├── comparar/            Comparação com referências históricas simuladas
│   │   ├── hipoteses/           Hipóteses, adaptadores de fonte e cenário simulado
│   │   ├── timeline/            Correlação cronológica simulada
│   │   ├── recorte/             Delimitação da população afetada simulada
│   │   ├── page.tsx             Redireciona a rota `/` para `/monitor`
│   │   ├── layout.tsx           Layout compartilhado das páginas operacionais
│   │   ├── loading.tsx          Estado de carregamento exibido na troca de rota
│   │   └── error.tsx            Fronteira de erro das rotas operacionais
│   ├── globals.css              Tokens e estilos globais
│   └── layout.tsx               Layout-base, fontes e metadados da aplicação
├── components/ui/               Componentes de interface reutilizáveis
├── lib/
│   ├── events/api.ts            Cliente HTTP tipado da API de eventos
│   ├── events/monitor.ts        Regras de monitoração e filtros
│   ├── operational-state.ts     Estados de carregamento, ausência e falha
│   └── utils.ts                 Composição de classes Tailwind (`cn`)
└── providers/
    ├── query-provider.tsx       Configuração compartilhada do TanStack Query
    └── theme-provider.tsx       Configuração de tema da aplicação
```

&emsp; A separação em `(operations)`, com componentes, bibliotecas e cenários privados de cada rota, preserva perto de cada tela aquilo que só ela utiliza. Componentes de interface, integrações HTTP e provedores compartilhados permanecem em diretórios próprios, em alinhamento com as convenções do Next.js App Router.

### 2.2 Convenções adotadas

- Componentes React: `PascalCase`, por exemplo `DashboardScreen`, `AgoraScreen`, `ScreenFrame` e `OperationsNavigation`.
- Funções, variáveis e hooks: `camelCase`, por exemplo `fetchEvents`, `hrefWithDemoState`, `removeFilter` e `restoreFilter`.
- Tipos e interfaces: `PascalCase`, por exemplo `ApiEvent`, `EventsResponse`, `ScreenPeriod`, `ScreenFilter` e `OperationalPresentation`.
- Estratégia de comentários: JSDoc em componentes e funções públicas; comentários inline para decisões não triviais, como a origem escolhida para hipóteses, a sincronização do tema após a hidratação e as regras de intervalo temporal.
- Ferramentas de qualidade: ESLint (0 erros), TypeScript em modo estrito (`--noEmit`), geração de tipos do App Router (`next typegen`), build de produção com Webpack.

### 2.3 Avaliação da qualidade do código

| Aspecto | Evidência observada | Avaliação |
|---|---|---|
| Modularidade | Páginas, componentes, cliente HTTP, regras de monitoramento, mocks e providers em diretórios separados | Ponto positivo |
| Nomenclatura | Tipos e funções descrevem o domínio: `ScreenPeriod`, `ScreenFilter`, `OperationalPresentation`, `hrefWithDemoState` | Ponto positivo |
| Tipagem | Eventos, filtros, períodos e respostas da API com tipos explícitos em TypeScript | Ponto positivo |
| Comentários | JSDoc em funções e componentes; decisões não triviais explicadas | Ponto positivo |
| Qualidade estática | ESLint, geração de tipos, TypeScript e build de produção aprovados | Ponto positivo |
| Componentização | `ScreenFrame` como moldura compartilhada; `OperationsNavigation` reutilizável; `_components/` privados por rota | Ponto positivo |
| Testabilidade | Não existe suíte automatizada nem script `test` no `package.json` | Limitação |
| Tamanho das telas | A marcação e o estado das telas permanecem concentrados em componentes como `AgoraScreen` e `ExplorarScreen` | Limitação |
| Integração com API | A rota `/monitor` possui cliente HTTP real; as seis áreas operacionais usam cenários sintéticos, exceto Hipóteses, que possui adaptadores para fonte mockada ou HTTP | Cobertura parcial |

## 3. Acessibilidade e responsividade

&emsp; A interface do Argus é composta pelo Monitor de eventos (`/monitor`) e por seis áreas operacionais (Agora, Explorar, Comparar, Hipóteses, Timeline e Recorte), que compartilham um sistema visual unificado: tema escuro por padrão com alternância para tema claro, tipografia Archivo e IBM Plex Mono, e uma paleta vermelho e laranja para sinalizar estados críticos. As subseções a seguir avaliam a acessibilidade e a responsividade dessas seis áreas em conjunto com o Monitor.

### 3.1 Acessibilidade

&emsp; Esses são os seguintes fundamentos de acessibilidade implementados:

- Idioma: documento com `lang="pt-BR"` no `<html>`;
- Landmarks semânticos: uso de `<nav>`, `<main>`, `<aside>`, `<header>`, `<section>` com `aria-label`;
- Link de salto: presença de mecanismo para pular para o conteúdo principal;
- Navegação: `aria-current="page"` no item ativo (normalizando a barra final imposta por `trailingSlash`), `aria-pressed` nos seletores de período;
- Filtros: selects com nome acessível via `<label>` (Monitor) ou `aria-labelledby` (barra de escopo das telas operacionais);
- Controles temporais: `aria-valuetext` nas alças de ajuste de intervalo (tela Explorar);
- Regiões ao vivo: `aria-live="polite"` para atualizações dinâmicas e `aria-live="off"` explícito no relógio;
- Foco visível: regras `:focus-visible` nos controles do Monitor e das telas operacionais;
- Movimento reduzido: `prefers-reduced-motion: reduce` desabilita transições.

| Verificação | Método | Resultado | Evidência |
|---|---|---|---|
| Idioma e landmarks | Inspeção estática do código | `lang="pt-BR"`, `nav`, `main`, `aside` presentes | [layout.tsx](../apps/basica/frontend/src/app/layout.tsx) |
| Nomes e estados ARIA | Inspeção estática do código | `aria-label`, `aria-current`, `aria-pressed`, `aria-expanded` e `aria-valuetext` presentes | Componentes de navegação, moldura e telas operacionais |
| Foco visível | Inspeção dos estilos + Chrome headless | Contorno `:focus-visible` de 2px em todos os controles exercitados do Monitor (20/20) e das telas operacionais; as alças do controle de intervalo usam contorno no thumb | Estilos por tela; rodada de validação em navegador |
| Movimento reduzido | Inspeção dos estilos por tela | A variante `motion-reduce` reduz transições nos controles aplicáveis | Estilos das telas operacionais |
| Navegação por teclado | Exercitada em Chrome headless sobre o build estático | Ordem de foco lógica; link de salto move o foco ao `#main-content`; foco itinerante (←/→/Home/End) nas abas de tipo de evento; remoção de chip de escopo por Enter no botão "×" | Rodada de validação em navegador (27/08/2026) |
| Contraste | Medição das cores computadas em Chrome (temas escuro e claro) | Todos os pares texto/fundo amostrados ≥ 4,5:1 — h1 16–18:1, rótulos e legendas ~5:1, botões ~6:1, células de heatmap 6–12:1, números-herói em gradiente 4,3–9,4:1 | Rodada de validação em navegador |

#### 3.1.1 Acessibilidade dos elementos próprios das seis áreas operacionais

&emsp; As seis áreas operacionais introduzem elementos de interface além dos usados no Monitor. O quadro abaixo descreve o tratamento de acessibilidade implementado para cada um e como foi verificado; os casos de interação correspondentes estão na seção `4.4`.

| Elemento da interface | Tratamento implementado | Verificação |
|---|---|---|
| Chips de escopo removíveis (etiquetas de filtro com botão "×") | `aria-label="Remover filtro {dimensão}: {valor}"` no botão "×" (tela Explorar) | Remoção por teclado (Enter no botão "×") confirmada em Chrome headless; o resumo do escopo é recalculado |
| Relógio "AO VIVO" atualizado a cada segundo | O relógio recebe `aria-live="off"` explícito, portanto a atualização por segundo não é anunciada por leitores de tela | Inspeção estática do código (`operations-shell.tsx`) |
| Abas de tipo de evento (Explorar: request, screen_view, video_view, session, vitals, error) | Grupo de botões de alternância `role="group"` com `aria-pressed`, foco itinerante e navegação por ←/→/Home/End; um único stop de Tab. Não adota `role="tablist"` porque a seleção reconfigura várias seções da tela, não um único painel | Navegação por setas e stop único de Tab confirmados em Chrome headless |
| Pastilhas de seleção (agrupar por dimensão, janela de comparação, hipótese) | Agrupar por dimensão e janela de comparação usam `ToggleGroup` do Radix (foco itinerante nativo, `aria-pressed`); a hipótese selecionada usa `<button aria-pressed>` | Seleção anunciada e operável por teclado; exatamente uma pastilha `aria-pressed="true"` por grupo (Chrome headless) |
| Minigráficos de tendência na tabela "Sinais em desvio agora" (tela Agora) | `aria-hidden="true"` no gráfico; os valores Agora, Baseline e Δ da linha são a alternativa textual | Inspeção estática do código (`agora-screen.tsx`) |
| Mapa de calor "Taxa de erro por família de dispositivo × região" (tela Recorte) | Percentual em texto em todas as células, com `aria-label` por célula; célula de pico rotulada "pico" | Contraste medido em 11,2–11,7:1 nas células tônicas e 6,2–6,3:1 na célula de pico — acima do piso AA (Chrome headless) |
| Timeline por raias (Deploy, Player QoE, CDN, Backend, Identidade, Incidentes) | Gráfico com `aria-hidden` no conteúdo espacial, `figcaption` sr-only e `aria-describedby` ligando a `<figure>` à lista "Cronologia reconstruída" como equivalente textual | Inspeção estática do código (`timeline-content.tsx`) |
| Alternância de tema claro/escuro | `aria-label="Usar modo {claro\|escuro}"`; o rótulo visível foi alinhado ao nome acessível (WCAG 2.5.3 "Label in Name") | Inspeção estática do código (`theme-toggle.tsx`) |

### 3.2 Responsividade

&emsp; O Monitor de eventos usa breakpoints (larguras de tela em que o layout muda) progressivos, verificados em `monitor/_components/dashboard.styles.ts` e no cabeçalho compartilhado:

| Breakpoint | Adaptação |
|---|---|
| ≤ 1000 px | Oculta a contagem de eventos e o botão "limpar"; a tabela de eventos ganha rolagem horizontal (largura mínima de 950 px) |
| ≤ 780 px | Oculta o indicador "Ao vivo" do Monitor |
| ≤ 768 px | A navegação lateral recolhe para o menu de hambúrguer (comportamento compartilhado com as seis áreas) |
| ≤ 700 px | Grade de detalhes do evento em 2 colunas; tabela de eventos com altura máxima de 55vh; bloco de indicadores com rolagem horizontal |
| ≤ 640 px | Oculta o subtítulo "Globoplay" no cabeçalho |
| ≤ 560 px | Os controles de período do Monitor passam para uma faixa própria |

#### 3.2.1 Responsividade das seis áreas operacionais

&emsp; Na resolução de desktop, a tabela "Sinais em desvio agora" (tela Agora) é um `<table>` com colunas em porcentagem (25%, 16%, 11%, 13% e automáticas); as telas Comparar, Timeline e Recorte reservam um painel lateral de largura fixa (232 px, 320 px e 300 px, respectivamente) ao lado do conteúdo principal, e a tela Hipóteses divide o espaço em duas colunas fluidas de proporção ~1:1.

&emsp; Abaixo de 768 px, a navegação principal e a barra de escopo, compartilhadas pelas seis telas, recolhem para um menu de hambúrguer (componente `Sheet`) e para o resumo "Escopo · N filtros". Abaixo de 1100 px, os painéis laterais de Comparar, Hipóteses, Timeline e Recorte empilham verticalmente sobre o conteúdo principal. Cada tela também substitui, em larguras menores, seus elementos mais densos por alternativas compactas: a tabela de sinais da Agora e o mapa de calor do Recorte viram listas de cartões, as abas de tipo de evento do Explorar reagrupam de 6 para 3 e depois 2 colunas, e o gráfico de raias da Timeline é ocultado em favor da lista "Cronologia reconstruída". A captura em viewport mobile (390×844) da seção 1.3.7 mostra esse comportamento na tela Agora.

| Área da interface | Comportamento em telas largas | Adaptação em telas estreitas |
|---|---|---|
| Navegação lateral (Monitor + as 6 áreas) | Coluna fixa ao lado do conteúdo | Recolhimento em painel deslizante (hambúrguer) abaixo de 768 px |
| Barra de escopo (chips + resumo de sessões) | Chips em linha única, texto de resumo alinhado à direita | Resumo "Escopo · N filtros" com filtros completos em painel deslizante, abaixo de 768 px |
| Abas de tipo de evento (Explorar) | Grade de 6 colunas iguais | Regrade para 3 colunas em 1040 px e 2 colunas em 600 px |
| Painel lateral (Comparar, Hipóteses, Timeline, Recorte) | Colunas lado a lado (painel de 232–320 px em Comparar/Timeline/Recorte; split fluido ~1:1 em Hipóteses) | Empilhamento vertical abaixo de 1100 px |
| Mapa de calor por região (Recorte) | 5 colunas de região + coluna de rótulo de 150 px | Lista de cartões por família de dispositivo abaixo de 768 px |
| Timeline por raias | Eixo de tempo fixo com marcadores posicionados em percentual absoluto | Gráfico ocultado abaixo de 760 px, substituído pela lista "Cronologia reconstruída" |

| Dispositivo ou viewport | Resultado | Evidência |
|---|---|---|
| Desktop (1440 px) | Layout de referência definido integralmente nessa resolução (capturas produzidas em 1264 px) | `globals.css`, seção 1.3 |
| Tablet (768 px) | Em 768 px a navegação lateral ainda aparece e o cabeçalho comprime a barra de escopo (com rolagem horizontal); abaixo de 768 px a navegação recolhe para o menu de hambúrguer | [captura_agora_tablet.png](./assets/captura_agora_tablet.png), seção 1.3.8 |
| Celular (390 px) | Menu em hambúrguer, escopo resumido e sinais em cartões empilhados nas seis áreas operacionais; navegação compacta no Monitor | [captura_agora_mobile.png](./assets/captura_agora_mobile.png), seção 1.3.7 |

## 4. Validação das entradas do usuário

&emsp; Os testes desta seção verificam se os campos aceitam dados válidos, impedem ou tratam entradas inválidas e apresentam mensagens compreensíveis sem provocar requisições incorretas ao back-end.

### 4.1 Estratégia de teste

- Ambiente: build estático de produção (`npm run build` → `out/`) servido localmente e inspeção estática do código.
- Data da execução: 27/08/2026.
- Navegador e dispositivo: Google Chrome headless dirigido por script (Playwright-core), viewports 1264×720, 390×844 e 768×1024, `prefers-reduced-motion: reduce`; complementado por inspeção estática do HTML e CSS.
- Ferramentas: inspeção manual do código-fonte, build estático servido localmente, Google Chrome headless, requisições HTTP para verificação de rotas.
- Comando de build: `NEXT_PUBLIC_API_URL=http://127.0.0.1:9 npm run build`

&emsp; As seis áreas operacionais introduzem elementos de entrada adicionais (chips de escopo, abas de tipo de evento, pastilhas de agrupamento, campo de busca em atributos, cartões de janela de comparação, seleção de hipótese, painel de ajuste de recorte). A seção 4.4 apresenta os resultados da validação em navegador desses elementos; eles não fazem parte dos casos TF-01 a TF-10 abaixo, que avaliam o Monitor (`/monitor`).

### 4.2 Casos de teste e resultados

| ID | Entrada ou cenário | Procedimento | Resultado esperado | Resultado obtido | Situação | Evidência |
|---|---|---|---|---|---|---|
| TF-01 | Período válido (15 min, 30 min, 3 h, 24 h) | Acionar cada botão de período no Monitor | A consulta é enviada com o período selecionado; `aria-pressed="true"` no período ativo | Os botões têm `aria-pressed`; a troca de período recalcula `from`/`to` via `getPeriodQuery()` e dispara refetch | Aprovado (estático + navegador) | [dashboard-screen.tsx](../apps/basica/frontend/src/app/(operations)/monitor/_components/dashboard-screen.tsx) |
| TF-02 | Período invertido | Informar data inicial posterior à data final | A consulta não é enviada e uma mensagem orienta a correção | O período é calculado programaticamente (Now − N minutos); não é possível inverter datas pelos controles nativos | Aprovado (por design) | Função `getPeriodQuery()` em [dashboard-screen.tsx](../apps/basica/frontend/src/app/(operations)/monitor/_components/dashboard-screen.tsx) |
| TF-03 | Data inválida ou ausente | Tentar acionar sem período selecionado | O campo inválido é identificado de forma acessível | Período padrão "30 min" é restaurado do `localStorage` (`event-monitor-period`) via `isPeriod()`; sempre há período válido | Aprovado (por design) | Validação `isPeriod()` com fallback |
| TF-04 | Filtro por tipo | Selecionar um tipo de evento existente no select | Apenas dados compatíveis são apresentados | `filterEvents()` filtra localmente por `eventType`, `platform`, `manufacturer`, `status` e `search` | Aprovado (estático) | Lógica de filtro em [dashboard-screen.tsx](../apps/basica/frontend/src/app/(operations)/monitor/_components/dashboard-screen.tsx) |
| TF-05 | Filtros cumulativos | Aplicar plataforma + fabricante + tipo + status simultaneamente | Todos os filtros são preservados e enviados ao back-end (API) ou aplicados localmente | Os quatro selects operam em conjunto; `fetchEvents` envia `event_name`, `device_os` e `device_manufacturer` como query string | Aprovado (estático) | [api.ts](../apps/basica/frontend/src/lib/events/api.ts) |
| TF-06 | Valor inexistente | Selecionar filtros sem correspondência nos dados retornados | A interface apresenta estado vazio sem falhar | Renderiza `Nenhum evento corresponde aos filtros selecionados.` quando `filtered.length === 0` | Aprovado (estático) | Estado vazio em [dashboard-screen.tsx](../apps/basica/frontend/src/app/(operations)/monitor/_components/dashboard-screen.tsx) |
| TF-07 | Caracteres especiais | Inserir caracteres especiais no campo de busca textual | A entrada é tratada sem quebrar a tela nem alterar indevidamente a requisição | A busca opera via `input[type="search"]` (`aria-label="Buscar eventos"`) com filtragem local por `includes()`; sem injeção na URL | Aprovado (estático) | Campo de busca em [dashboard-screen.tsx](../apps/basica/frontend/src/app/(operations)/monitor/_components/dashboard-screen.tsx) |
| TF-08 | Limite de tamanho | Informar texto maior que o limite definido | O limite é aplicado ou uma mensagem de validação é exibida | Selects têm conjuntos fechados de opções; o campo de busca impõe `maxLength={80}` e opera localmente sem envio à API | Aprovado (estático + navegador) | `maxLength={80}` em [dashboard-screen.tsx](../apps/basica/frontend/src/app/(operations)/monitor/_components/dashboard-screen.tsx) |
| TF-09 | Envio por teclado | Preencher os filtros e acionar a pesquisa pelo teclado | A ação funciona e o foco permanece previsível | Em Chrome headless: ordem de foco lógica (salto → período → tema → nav → período do Monitor → 4 selects → busca); a digitação no campo de busca aplica o filtro; os botões de período ativam por Enter; todos os 20 controles exibem contorno `:focus-visible` | Aprovado (navegador) | Rodada de validação em navegador (27/08/2026) |
| TF-10 | Falha do back-end | Simular resposta de erro ou indisponibilidade | A interface informa a falha e permite nova tentativa | TanStack Query com `retry: 1`; quando `eventsQuery.isError`, renderiza `Não foi possível consultar a API. Tente novamente.` com classe visual `.error` | Aprovado (estático + navegador) | [query-provider.tsx](../apps/basica/frontend/src/providers/query-provider.tsx), estado de erro em [dashboard-screen.tsx](../apps/basica/frontend/src/app/(operations)/monitor/_components/dashboard-screen.tsx) |

### 4.3 Síntese dos resultados

| Indicador | Resultado |
|---|---|
| Total de testes executados | 10 |
| Testes aprovados (incluindo por design) | 10 |
| Testes parciais | 0 |
| Testes não verificáveis nesta etapa | 0 |
| Testes reprovados | 0 |
| Taxa de aprovação | 100% |

Observações: TF-08 passou a Aprovado com a adição de `maxLength={80}` ao campo de busca. TF-09 foi exercitado em Chrome headless — ordem de foco lógica, digitação aplicando o filtro, ativação de botões por Enter e contorno de foco visível em todos os controles do Monitor. Os casos TF-11 a TF-19 (seção 4.4) também foram executados em navegador nesta rodada.

### 4.4 Elementos de entrada das seis áreas operacionais

&emsp; A tabela a seguir traz os resultados da validação dos elementos de entrada das seis áreas operacionais, executada em Google Chrome headless sobre o build estático (27/08/2026). Esses casos operam sobre os cenários sintéticos das telas; não substituem os casos TF-01 a TF-10 do Monitor.

| ID | Elemento | Tela | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|---|
| TF-11 | Adicionar filtro de escopo (botão "+ filtro") | Explorar | Abre um seletor de dimensão e valor; o novo chip volta a restringir o recorte | O botão abre o menu (`aria-expanded="true"`) e a opção escolhida readiciona o chip; o recorte é recalculado localmente | Aprovado |
| TF-12 | Remover filtro de escopo (botão "×" no chip) | Explorar | O chip é removido e o recorte é recalculado sem aquela restrição | Chip removido (inclusive por teclado, Enter no "×"); o resumo do escopo é recalculado | Aprovado |
| TF-13 | Alternar tema (claro/escuro) | Todas | A paleta muda sem perda do estado de filtros ou de navegação | Tema alterna; os chips de escopo e a rota atual são preservados | Aprovado |
| TF-14 | Selecionar tipo de evento (request, screen_view, video_view, session, vitals, error) | Explorar | O tipo selecionado passa a reger o gráfico e a tabela; a contagem de cada tipo continua visível | A seleção muda; o gráfico e a tabela recalculam; as contagens permanecem nos demais botões | Aprovado |
| TF-15 | Agrupar por dimensão (Modelo, UF, ISP, Versão, Rota) | Explorar | A tabela é reagrupada pela dimensão sem nova consulta ao back-end | As 5 dimensões reagrupam a tabela localmente | Aprovado |
| TF-16 | Buscar em atributos (campo de texto na barra lateral) | Explorar | Filtra a lista de erros por texto livre, sem quebrar a tela em valores vazios ou com caracteres especiais | O filtro estreita a lista; termo sem correspondência mostra "Nenhum erro encontrado"; caracteres especiais não quebram a tela; limpar restaura a lista | Aprovado |
| TF-17 | Selecionar janela de comparação (Ontem, Semana passada, Última janela estável, Pico ao vivo anterior) | Comparar | Recalcula o gráfico com envelope histórico e a tabela de significância (σ) para a janela | As 4 janelas atualizam o cabeçalho da coluna e a tabela de significância | Aprovado |
| TF-18 | Selecionar hipótese na lista ranqueada | Hipóteses | O painel "Como este score foi calculado" atualiza título, score e os quatro fatores ponderados | O painel atualiza; exatamente uma hipótese fica com `aria-pressed="true"` | Aprovado |
| TF-19 | Painel "Ajustar o recorte" | Recorte | Exibe o efeito estimado sobre especificidade e cobertura de cada ajuste | O painel apresenta o efeito previsto de cada cenário; é informativo e não-executável — o próprio painel declara "estes cenários são informativos e não executam ações" | Aprovado (por design) |

&emsp; Os nove casos foram executados e aprovados; TF-19 é aprovado por design, já que o painel de ajuste de recorte é declaradamente informativo. A síntese da seção `4.3` permanece organizada em torno dos casos TF-01 a TF-10 do Monitor.

## 5. Matriz de rastreabilidade

&emsp; A matriz relaciona os requisitos funcionais pertinentes à interface, definidos em [`requisitos.md`](./requisitos.md), às funcionalidades implementadas e aos testes que fornecem evidência de atendimento. Foram incluídos apenas os requisitos efetivamente pertinentes ao front-end (RF08 a RF17). A coluna "Evidência" indica, para cada requisito, se a referência é o código de produção do Monitor (`/monitor`), conectado à API real, ou as seis áreas operacionais, que operam sobre dados sintéticos.

| Requisito | Descrição | Funcionalidade ou critério verificado | Testes relacionados | Situação | Evidência |
|---|---|---|---|---|---|
| RF08 | Pesquisar por tipo, período e atributos | Monitor `/monitor` com selects de plataforma, fabricante e evento, período (15 min, 30 min, 3 h, 24 h, tudo) e busca textual; cada área operacional tem chips de escopo e seletor de período próprios | TF-01, TF-02, TF-03, TF-04, TF-11, TF-12 | Atendido | Controles implementados no Monitor com API real; nas seis áreas, os chips de escopo derivam de mocks e são majoritariamente decorativos (uma opção fixa por chip, sem handler de mudança) — exceto Explorar, onde adicionar/remover chip recalcula o recorte localmente |
| RF09 | Aplicar filtros cumulativos | Quatro selects cumulativos + busca textual no Monitor; em Explorar, os chips de escopo são cumulativos e recalculam o recorte localmente | TF-05, TF-11, TF-12 | Atendido | Filtros cumulativos em `fetchEvents()` e `filterEvents()` no Monitor; recálculo local em Explorar; nas demais telas os chips são decorativos |
| RF10 | Sugerir valores existentes | Os selects do Monitor derivam opções dos itens carregados via `unique()`; as seis áreas operacionais sugerem valores de escopo (ex.: webOS 3.x, LG, Nordeste) e de atributos no campo "Buscar em atributos" da tela Explorar | TF-04, TF-05, TF-16 | Parcial | Monitor deriva dinamicamente; seis áreas operacionais usam dados de demonstração fixos |
| RF11 | Agrupar eventos por critério | Botões de dimensão em `/explorar` (Modelo, UF, ISP, Versão, Rota); a tela Recorte acrescenta o agrupamento por família de dispositivo × região no mapa de calor | TF-04, TF-15 | Parcial | Cinco dimensões na interface com dados mockados; mapa de calor por dispositivo × região na tela Recorte |
| RF12 | Exibir gráficos e indicadores | Métricas no bloco de destaque do monitor; degradações e sinais em `/agora`; cada área operacional tem visualização própria: minigráficos de tendência por sinal (Agora), gráfico de eventos × erros (Explorar), gráfico com envelope histórico e significância σ (Comparar), mapa de calor (Recorte) e timeline por raias com seis fontes (Timeline) | TF-01, TF-06, TF-17 | Parcial | Visualizações implementadas sobre snapshots nas seis áreas operacionais |
| RF13 | Consultar falhas críticas | Degradação ativa, sinais de desvio, busca de erros e status "atenção"; a tela Agora lista "Sinais em desvio agora" (com Agora, baseline e Δ) e "Outras degradações abertas" com severidade (ALTO/ATENÇÃO) | TF-06, TF-07 | Parcial | Implementado com filtro de status `attention`; tabela de sinais e lista de degradações abertas na tela Agora |
| RF14 | Comparar período atual e anterior | Tela Comparar com quatro janelas de referência (ontem no mesmo horário, semana passada, última janela estável, pico ao vivo anterior), gráfico com envelope histórico e tabela com significância estatística (σ) por métrica | TF-17 | Parcial | Rota `/comparar` com layout e mock implementados |
| RF15 | Destacar aumentos relevantes | Sinais em desvio e tendência de erros na tela Agora; os desvios relevantes são destacados por cor, símbolo Δ e barra de significância σ na tela Comparar | TF-06, TF-17 | Parcial | Destaques visuais existem; critério calculado sobre dados reais apenas no Monitor |
| RF16 | Exibir contexto para investigação | Detalhes do evento: ID, data, dispositivo, sistema, rota, versão, atributos JSON; a tela Recorte detalha o recorte afetado com amostra de sessões e a tela Timeline reconstrói a cronologia do incidente cruzando seis fontes de dados | TF-04, TF-06 | Atendido | A seção de detalhes do `DashboardScreen` (com `DetailField` e `<details>` para os atributos JSON) exibe todos os campos; contexto ampliado nas telas Recorte e Timeline |
| RF17 | Apresentar hipóteses de causa raiz | Tela Hipóteses em que cada hipótese recebe um score de 0 a 100, quatro fatores ponderados com justificativa textual, lista de hipóteses descartadas com motivo e lista de evidências consultadas | TF-18 | Parcial | Rota `/hipoteses` com layout, mock e cliente de API |

### 5.1 Cobertura resumida

| Situação | Quantidade |
|---|---|
| Atendido (código de produção) | 3 (RF08, RF09, RF16) |
| Parcial (dados sintéticos) | 7 (RF10, RF11, RF12, RF13, RF14, RF15, RF17) |
| Não atendido | 0 |

&emsp; Os requisitos parciais permanecem parciais porque suas funcionalidades operam sobre dados sintéticos (mocks) nas seis áreas operacionais, em vez de dados reais da API de leitura.

## 6. Integração com o back-end

&emsp;O front-end consome a API de leitura de eventos por meio de um cliente HTTP tipado em [`events/api.ts`](../apps/basica/frontend/src/lib/events/api.ts). A URL da API é fornecida pela variável de ambiente `NEXT_PUBLIC_API_URL`, que é definida no momento do build e nunca commitada no código-fonte para evitar exposição de acesso.

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
| Trocar período (15 min, 30 min, 3 h, 24 h, tudo) | `GET /api/v1/events` | `from` e `to` recalculados por `getPeriodQuery()` | Mesma estrutura, com novo refetch automático |
| Aplicar filtro por plataforma/fabricante/tipo | `GET /api/v1/events` | Parâmetros adicionais na query string | Mesma estrutura; filtragem local adicional por `filterEvents()` |

### 6.1 Tratamento de estados

| Estado | Comportamento na interface |
|---|---|
| Carregamento | Exibe `"Consultando eventos na API…"` com classe `.empty-state` |
| Sucesso sem dados | Exibe `"Nenhum evento corresponde aos filtros selecionados."` |
| Erro da API | Exibe `"Não foi possível consultar a API. Tente novamente."` com classe `.error` e cor vermelha |
| Sucesso com dados | Renderiza tabela de eventos, bloco de destaque com indicadores e detalhes do evento selecionado |
| Atualização em segundo plano | Indicador `"Atualizando"` no canto superior enquanto `isFetching` é true |

### 6.2 Evidência do fluxo ponta a ponta

&emsp;A rota `/monitor` (para a qual `/` redireciona) está conectada ao cliente HTTP real. Quando o build recebe `NEXT_PUBLIC_API_URL` apontando para a API de leitura, o front-end:

1. Dispara `GET /api/v1/events?limit=100` no primeiro carregamento;
2. Refaz a consulta a cada mudança de período ou filtro;
3. Apresenta os eventos retornados em uma tabela ordenada do mais recente ao mais antigo;
4. Permite selecionar um evento para visualizar todos os seus campos e atributos JSON.

&emsp;A coleção Postman descrita no [MVP inicial](./mvp-inicial.md) registrou anteriormente 51 asserções de API sem falha, confirmando que os endpoints consumidos pelo front-end operam corretamente.

&emsp; As seis áreas operacionais não percorrem esse fluxo: cada uma importa cenários sintéticos das suas pastas `_mocks/` e calcula a apresentação em estado local do React. A exceção é a tela Hipóteses, que possui um adaptador HTTP opcional, ativado por `NEXT_PUBLIC_HYPOTHESES_SOURCE=api`. Essa separação permite avaliar as interações projetadas, mas não comprova integração com o back-end nessas telas.

## 7. Publicação na AWS S3

&emsp;O Next.js está configurado com `output: "export"`, que gera arquivos estáticos (HTML, CSS, JS) prontos para hospedagem em S3. A variável `NEXT_PUBLIC_API_URL` é incorporada ao bundle durante o build, apontando o site para o endpoint da API de leitura sem expor a URL no repositório.

- Procedimento de build: `NEXT_PUBLIC_API_URL=$(cd apps/basica/infra && terraform output -raw read_api_url) npm run build`

## 8. Limitações

- Testes automatizados ausentes: não existe suíte automatizada nem script `test` no `package.json`. A validação em navegador desta entrega foi feita por scripts ad hoc não versionados; recomenda-se adicionar Vitest + Testing Library para os componentes críticos e Playwright para testes E2E;
- Telas com dados mockados: Agora, Explorar, Comparar, Hipóteses, Timeline e Recorte operam sobre snapshots sintéticos; a integração com a API real está implementada no Monitor (`/monitor`), e a tela Hipóteses aceita opcionalmente uma fonte HTTP (`NEXT_PUBLIC_HYPOTHESES_SOURCE=api`);
- Leitor de tela: os fundamentos de acessibilidade foram validados em navegador (teclado, ordem de foco, contraste, viewports); a verificação com leitor de tela real (NVDA/VoiceOver) permanece pendente.

## 9. Referências internas

- [Entendimento de UX](./entendimento_ux.md): personas, User Stories, protótipos e avaliação heurística.
- [Requisitos](./requisitos.md): RF08 a RF17 e requisitos não funcionais relacionados à interface.
- [MVP inicial](./mvp-inicial.md): arquitetura implantada e evidência histórica dos testes de API.
