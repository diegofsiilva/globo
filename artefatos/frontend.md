# Interface gráfica do sistema

## 1. Objetivo e escopo

&emsp;Este artefato documenta o estado da interface gráfica do Argus, a organização do código e os resultados obtidos na validação das entradas disponíveis ao usuário. A análise considera acessibilidade, responsividade e integração com a API de leitura, mas distingue rigorosamente código executável, dados simulados e telas que existem apenas como protótipo.

&emsp;A versão avaliada foi o commit `3edf8fc868680cb4f9bb82e5045a2fcb2c755ddc`, da branch `feat/desenvolve-telas-agora-explorar`, em 24 de agosto de 2026. O commit foi aberto em um worktree destacado e permaneceu sem alterações durante toda a avaliação.

&emsp;A especificação da entrega indica `/apps/frontend` como pasta do código-fonte. No monorepositório atual, entretanto, o frontend está em `apps/basica/frontend`, junto da API de leitura, do worker e da infraestrutura do MVP. Nenhuma cópia ou migração foi realizada nesta etapa; a necessidade de cumprir o caminho literal deve ser confirmada com o professor antes de uma mudança estrutural.

&emsp;Deploy em S3, vídeo demonstrativo, alterações no código, correções de defeitos e testes automatizados não fazem parte desta revisão.

## 2. Estado da implementação

&emsp;O Argus deve ser compreendido como um único produto, mas as telas do commit avaliado ainda se encontram em níveis distintos de implementação. A tabela abaixo evita que dados simulados ou imagens do protótipo sejam interpretados como integração concluída.

| Rota | Papel na experiência | Origem dos dados | Estado observado |
|---|---|---|---|
| `/` | Monitor de eventos, filtros e detalhes | Cliente HTTP configurado por `NEXT_PUBLIC_API_URL` | Implementada; a integração ao vivo não foi verificada nesta execução |
| `/agora` | Visão de degradações e sinais operacionais | Snapshot sintético em `src/mocks/agora.ts` | Implementada com mock |
| `/explorar` | Exploração por evento, período, dimensão e erro | Snapshot sintético em `src/mocks/explorar.ts` | Implementada com mock |
| `/comparar` | Comparação com referências históricas | Apenas protótipo de UX | Não implementada; retornou HTTP 404 |
| `/hipoteses` | Hipóteses de causa provável | Apenas protótipo de UX | Não implementada; retornou HTTP 404 |
| `/timeline` | Correlação cronológica de eventos | Apenas protótipo de UX | Não implementada; retornou HTTP 404 |
| `/recorte` | Delimitação da população afetada | Apenas protótipo de UX | Não implementada; retornou HTTP 404 |

### 2.1 Referência visual

&emsp;As Figuras 1 e 2 apresentam a intenção de design registrada anteriormente no [Entendimento de UX](./entendimento_ux.md). Elas são referências do protótipo e **não** constituem capturas da execução nem evidência dos testes deste relatório.

<div align="center">

<sub>Figura 1 - Referência de UX para a tela Agora</sub>

![Protótipo da tela Agora](./assets/prototipo_agora.png)

<sup>Fonte: material produzido pelos autores (2026). Imagem de protótipo, não evidência de teste.</sup>

</div>

<div align="center">

<sub>Figura 2 - Referência de UX para a tela Explorar</sub>

![Protótipo da tela Explorar](./assets/prototipo_explorar.png)

<sup>Fonte: material produzido pelos autores (2026). Imagem de protótipo, não evidência de teste.</sup>

</div>

## 3. Tecnologias, organização e integração

&emsp;O frontend utiliza Next.js 16.3 com App Router, React 19.2, TypeScript, TanStack Query e CSS Modules. O build usa `output: "export"`, produzindo arquivos estáticos. A composição e o estado específicos permanecem nas páginas, enquanto elementos reaproveitáveis, como navegação, métricas, filtros e linhas de evento, estão em `src/components`.

```text
apps/basica/frontend/src/
├── app/(pages)/                 páginas e composição de cada rota
│   ├── (dashboard)/page.tsx     monitor conectado ao cliente da API
│   ├── agora/page.tsx           tela operacional com snapshot sintético
│   └── explorar/page.tsx        exploração com snapshot sintético
├── components/                  elementos reutilizáveis
├── lib/events/                  cliente HTTP e regras de filtro/formatação
├── mocks/                       dados sintéticos de Agora e Explorar
└── providers/                   configuração compartilhada do React Query
```

&emsp;A rota raiz segue o fluxo abaixo. A URL não é escrita no código; ela é fornecida no build. O cliente cria a query string, a TanStack Query controla a requisição e a atualização periódica, e a interface aplica os filtros locais sobre os itens retornados.

```text
NEXT_PUBLIC_API_URL
        │
        ▼
fetchEvents() ── GET /api/v1/events ──► API de leitura
        │
        ▼
TanStack Query
        │
        ▼
filterEvents() ──► indicadores, tabela e detalhes
```

&emsp;Já `/agora` e `/explorar` não percorrem esse fluxo: ambas importam snapshots de `src/mocks` e calculam a apresentação em estado local do React. Essa separação permite avaliar as interações projetadas, mas não comprova que os mesmos resultados sejam produzidos pelo back-end.

### 3.1 Qualidade do código

| Aspecto | Evidência observada | Avaliação |
|---|---|---|
| Modularidade | Páginas, componentes, cliente HTTP, regras de monitoramento, mocks e providers estão separados | Ponto positivo |
| Nomenclatura | Tipos e funções descrevem o domínio, como `Period`, `MonitorFilters`, `filterEvents` e `getPeriodQuery` | Ponto positivo |
| Tipagem | Eventos, filtros, períodos e respostas da API possuem tipos explícitos | Ponto positivo |
| Comentários | Funções e componentes principais possuem JSDoc; decisões não triviais são explicadas junto ao código | Ponto positivo |
| Qualidade estática | ESLint, geração de tipos, TypeScript e build de produção passaram no commit avaliado | Ponto positivo |
| Testabilidade | Não existe suíte automatizada nem script `test` no `package.json` | Limitação |
| Tamanho das páginas | `agora/page.tsx` e, principalmente, `explorar/page.tsx` concentram muitas regras e marcação | Limitação |
| Coerência da navegação | Quatro links visíveis apontam para rotas não implementadas | Limitação crítica |
| Integração | A rota `/` possui cliente real; as duas telas de produto avaliadas usam mocks | Cobertura parcial |

## 4. Acessibilidade e responsividade

&emsp;A inspeção estática encontrou fundamentos de acessibilidade: documento com `lang="pt-BR"`, link de salto para o conteúdo, navegação semântica, `aria-current` na rota ativa, `aria-pressed` em seletores, nomes acessíveis nos filtros, `aria-valuetext` nas alças temporais, regiões com rótulo e atualizações com `aria-live="polite"`. Os estilos também declaram foco visível nos principais controles e removem transições quando `prefers-reduced-motion: reduce` está ativo.

&emsp;A responsividade é tratada por breakpoints entre 1080 px e 430 px, alteração da navegação para disposição horizontal e rolagem localizada em tabelas e gráficos. Contudo, a existência dessas regras no CSS não prova que o layout permaneça utilizável em cada viewport.

| Verificação | Evidência estática | Limite desta avaliação |
|---|---|---|
| Idioma e landmarks | `lang="pt-BR"`, `nav`, `main`, tabelas e link “Pular para o conteúdo” | Ordem real de leitura não exercitada |
| Nomes e estados | `aria-label`, `aria-current`, `aria-pressed`, `aria-expanded` e `aria-valuetext` | Mudanças dinâmicas não exercitadas |
| Teclado e foco | Regras `:focus-visible` e controles HTML nativos | Navegação por Tab, setas, Enter e Espaço não exercitada |
| Movimento | `prefers-reduced-motion: reduce` nas telas e navegação | Preferência não ativada em navegador |
| Responsividade | Media queries e rolagem interna planejada | Viewports não renderizados visualmente |
| Contraste | Estados críticos também usam texto e valores | Contraste calculado não medido |

## 5. Metodologia

### 5.1 Ambiente

| Item | Valor |
|---|---|
| Data e hora | 24/08/2026, 16:52 (UTC-3) |
| Commit | `3edf8fc868680cb4f9bb82e5045a2fcb2c755ddc` |
| Node.js | `v20.20.2` |
| npm | `10.8.2` |
| Next.js | `16.3.0` |
| React | `19.2.8` |
| Dados | Snapshots sintéticos versionados nas páginas Agora e Explorar |
| Navegador | Indisponível no ambiente de execução |

### 5.2 Procedimento executado

&emsp;O commit foi aberto em um worktree temporário e destacado para impedir alterações acidentais na branch. Em seguida, foram executados:

```bash
npm ci
npm run lint
./node_modules/.bin/next typegen
./node_modules/.bin/tsc --noEmit
NEXT_PUBLIC_API_URL=http://127.0.0.1:9 npm run build -- --webpack
NEXT_PUBLIC_API_URL=http://127.0.0.1:9 npm run dev -- --webpack -p 4174
```

&emsp;A URL local deliberadamente não aponta para um back-end real; seu único papel foi satisfazer a configuração obrigatória do bundle. Por isso, esta execução não é evidência de integração ponta a ponta.

&emsp;O ambiente não disponibilizou um navegador controlável. A avaliação não foi substituída por automação ou simulação de cliques, pois isso contrariaria o escopo acordado. Os cenários que dependem de interação visual foram mantidos como `Não verificável nesta etapa`. O HTML inicial foi inspecionado apenas para confirmar a presença dos controles e atributos, sem inferir que suas transições funcionam.

### 5.3 Resultados técnicos reproduzíveis

| Verificação | Resultado | Evidência |
|---|---|---|
| Instalação limpa | Aprovado — 373 pacotes, 0 vulnerabilidades reportadas | [Log de verificação estática](./assets/frontend/verificacao-estatica.txt) |
| ESLint | Aprovado — 0 erros | [Log de verificação estática](./assets/frontend/verificacao-estatica.txt) |
| Geração de tipos do App Router | Aprovado | [Log de verificação estática](./assets/frontend/verificacao-estatica.txt) |
| TypeScript sem emissão | Aprovado — 0 erros | [Log de verificação estática](./assets/frontend/verificacao-estatica.txt) |
| Build de produção com Webpack | Aprovado | [Log de verificação estática](./assets/frontend/verificacao-estatica.txt) |
| Árvore Git do worktree | Aprovado — permaneceu limpa | [Log de verificação estática](./assets/frontend/verificacao-estatica.txt) |

&emsp;A coleção Postman descrita no [MVP inicial](./mvp-inicial.md#42-resultados) registrou anteriormente 51 asserções de API sem falha. Esse dado é histórico e complementar: ele não foi reexecutado nesta etapa e não valida entradas da interface.

## 6. Resultados dos testes de entradas do usuário

&emsp;Cada caso abaixo define uma interação reproduzível e o resultado efetivamente obtido nesta execução. `Não verificável nesta etapa` significa que o controle e seu estado inicial foram localizados, mas a interação não pôde ser exercitada sem navegador. Essa classificação não equivale a aprovação.

| ID | Entrada e procedimento | Resultado esperado | Resultado observado | Situação |
|---|---|---|---|---|
| TM-AG-01 | Acionar `15 min`, `30 min`, `3 h` e `24 h` em `/agora` | Apenas o período escolhido permanece com `aria-pressed="true"` e o recorte é atualizado | O HTML inicial contém os quatro botões e marca `30 min`; a troca não foi exercitada | Não verificável nesta etapa |
| TM-AG-02 | Combinar plataforma, fabricante, região e aplicação | Todos os filtros são aplicados em conjunto e o resumo/estado da degradação responde ao recorte | Os quatro `select` e suas opções fechadas foram encontrados; as combinações não foram exercitadas | Não verificável nesta etapa |
| TM-AG-03 | Acionar `limpar` e depois restaurar o recorte principal | Filtros assumem `todos`; a restauração devolve os valores iniciais | O botão `limpar` está presente; as transições não foram exercitadas | Não verificável nesta etapa |
| TM-EX-01 | Remover filtros, reabri-los por `+ filtro` e limpar todos | Somente filtros inativos aparecem no menu, sem duplicação; `limpar` fica desabilitado quando vazio | Quatro ações de remoção, o menu fechado e o botão de limpeza foram encontrados no estado inicial | Não verificável nesta etapa |
| TM-EX-02 | Alternar os seis tipos de evento e as dimensões Modelo, UF, ISP, Versão e Rota | Cartões, gráfico, tabela, legenda e leitura rápida passam a refletir a seleção | `Erros` e `Modelo` aparecem selecionados no HTML inicial; as demais trocas não foram exercitadas | Não verificável nesta etapa |
| TM-EX-03 | Usar presets e mover as duas alças até os limites e uma contra a outra | A janela pode mover e redimensionar, nunca fica menor que 15 min nem cruza as alças; rótulos acompanham os valores | Entradas têm `min=0`, `max=288`, valores 282/288 e rótulo inicial de 30 min; limites dinâmicos não foram exercitados | Não verificável nesta etapa |
| TM-EX-04 | Buscar por fragmento, espaços, caixa diferente, caracteres especiais e termo inexistente | Busca ignora espaços externos e caixa, não quebra com caracteres especiais e informa ausência de resultado | O campo de busca e o estado vazio existem no código; digitação não foi exercitada | Não verificável nesta etapa |
| TM-EX-05 | Alternar `Ocultar guia`/`Como usar` | Conteúdo e `aria-expanded` mudam de forma coerente | O estado inicial possui guia visível e `aria-expanded="true"`; a alternância não foi exercitada | Não verificável nesta etapa |
| TM-NAV-01 | Consultar as sete rotas declaradas pela experiência | Cada destino visível abre uma página válida | `/`, `/agora` e `/explorar` retornaram 200; `/comparar`, `/hipoteses`, `/timeline` e `/recorte` retornaram 404 | Reprovado |
| TM-ACC-01 | Percorrer controles com Tab/Shift+Tab, ativar por teclado e ajustar selects/ranges com setas | Ordem lógica, foco sempre visível, ausência de armadilha e estados acessíveis atualizados | Nomes, estados ARIA e estilos de foco foram encontrados; a operação por teclado não foi exercitada | Não verificável nesta etapa |
| TM-RESP-01 | Renderizar em 1440×900, 768×1024 e 390×844 | Conteúdo legível, sem sobreposição ou corte; rolagem apenas nas regiões planejadas | Media queries foram encontradas, mas nenhum viewport pôde ser renderizado | Não verificável nesta etapa |

&emsp;O resultado agregado é **0 casos aprovados, 1 reprovado e 10 não verificáveis**. Não foram produzidas capturas da aplicação porque não houve renderização em navegador. O [log de navegação HTTP](./assets/frontend/navegacao-http.txt) é a única evidência de execução associada aos casos manuais nesta etapa.

## 7. Matriz de rastreabilidade dos requisitos funcionais

| RF | Capacidade esperada | Implementação relacionada | Testes | Evidência e cobertura | Situação |
|---|---|---|---|---|---|
| RF08 | Pesquisar por tipo, período e atributos | Monitor `/` e controles de `/explorar` | TM-EX-02, TM-EX-03, TM-EX-04 | Controles existem; Explorar usa mock e os filtros do monitor real operam sobre até 100 itens carregados | Parcial |
| RF09 | Aplicar filtros cumulativos | Filtros de `/`, `/agora` e `/explorar` | TM-AG-02, TM-EX-01 | Combinação está implementada localmente; não há evidência de persistência entre telas | Parcial |
| RF10 | Sugerir valores existentes | Selects de `/` e `/agora`; menu de `/explorar` | TM-AG-02, TM-EX-01 | A raiz deriva opções dos itens carregados; as demais telas usam listas sintéticas e não consultam `/facets` | Parcial |
| RF11 | Agrupar eventos por critério | Botões de dimensão em `/explorar` | TM-EX-02 | Cinco dimensões aparecem na interface, mas os resultados são mockados | Parcial |
| RF12 | Exibir gráficos e indicadores | Métricas de `/agora` e gráficos de `/explorar` | TM-AG-02, TM-EX-02, TM-EX-03 | Visualizações estão implementadas sobre snapshots, sem comprovação com dados do back-end | Parcial |
| RF13 | Consultar falhas críticas | Degradação ativa, sinais e busca de erros | TM-AG-02, TM-EX-02, TM-EX-04 | A experiência representa a investigação, mas não executa consulta real nas telas avaliadas | Parcial |
| RF14 | Comparar período atual e anterior | Protótipo da tela Comparar | TM-NAV-01 | A rota `/comparar` retornou 404 | Não atendido |
| RF15 | Destacar aumentos relevantes | Sinais em desvio e tendência de erros mockados | TM-AG-02, TM-EX-03 | Destaques existem, mas não derivam de critério calculado sobre dados atuais | Parcial |
| RF16 | Exibir contexto para investigação | Detalhes do monitor `/`, tabelas e resumos | TM-AG-02, TM-EX-02 | Tipo, período, quantidade e dispositivo aparecem em partes da experiência; fluxo completo não foi verificado | Parcial |
| RF17 | Apresentar hipóteses justificadas | Protótipo da tela Hipóteses | TM-NAV-01 | A rota `/hipoteses` retornou 404; o requisito já está classificado como evolução | Não atendido |

## 8. Matriz de rastreabilidade das User Stories

| US | Persona e objetivo resumido | Evidência observada | Testes relacionados | Situação |
|---|---|---|---|---|
| US01 | Rafael — consultar eventos de diferentes fontes em uma interface | A raiz lista tipos de evento recebidos da API; a correlação entre fontes permanece apenas no protótipo da Timeline | TM-NAV-01 | Parcial |
| US02 | Rafael — filtrar e comparar dispositivos modernos e legados | Agora possui plataforma/fabricante e Explorar agrupa por modelo/versão, mas ambos usam mock e não cobrem toda a comparação | TM-AG-02, TM-EX-02 | Parcial |
| US03 | Rafael — visualizar cobertura de instrumentação | Explorar mostra volumes por dimensão, sem volume esperado nem limite de cobertura | TM-EX-02 | Parcial |
| US04 | Rafael — acompanhar integridade da ingestão | Há indicação de atualização, mas faltam atraso, descartes e deduplicações por fonte/período | TM-EX-03 | Parcial |
| US05 | Rafael — comparar indicadores com referência histórica | A rota `/comparar` retornou 404 | TM-NAV-01 | Não atendido |
| US06 | Mariana — consultar a timeline de uma sessão | A raiz mostra identificador e detalhes de um evento; não há busca e sequência cronológica de uma sessão | TM-NAV-01 | Não atendido |
| US07 | Mariana — filtrar erros por modelo e região | Região aparece em Agora e modelo em Explorar, mas os estados são independentes, mockados e não persistem entre telas | TM-AG-02, TM-EX-01, TM-EX-02 | Parcial |
| US08 | Mariana — verificar eventos de dispositivo legado | Filtros e detalhes de dispositivo existem, sem classificação explícita ou fluxo completo para legado | TM-AG-02, TM-EX-02 | Parcial |

## 9. Achados e próximos passos

1. **A base técnica compila de forma limpa.** Instalação, lint, tipos e exportação estática passaram no commit avaliado.
2. **A navegação comunica mais capacidade do que está implementado.** Quatro das seis opções operacionais levam a 404.
3. **Integração e experiência rica ainda estão separadas.** A raiz possui o cliente real, enquanto Agora e Explorar apresentam o desenho do produto com snapshots.
4. **Acessibilidade e responsividade têm boas bases estáticas, mas carecem de evidência de uso.** O código contém rótulos, foco e breakpoints, porém teclado, contraste e viewports precisam ser testados em navegador.
5. **A validação de entradas permanece incompleta.** Os controles possuem conjuntos fechados e regras defensivas no código, mas nenhum cenário dinâmico pôde ser aprovado nesta execução.
6. **A próxima rodada deve começar pela repetição de TM-AG-01 a TM-RESP-01 em navegador.** Somente depois dos resultados devem ser propostas correções ou automação, mantendo a separação entre defeito observado e melhoria planejada.

## 10. Referências internas

- [Entendimento de UX](./entendimento_ux.md) — personas, User Stories, protótipos e avaliação heurística.
- [Requisitos](./requisitos.md) — RF08 a RF17 e requisitos não funcionais relacionados à interface.
- [MVP inicial](./mvp-inicial.md) — arquitetura implantada e evidência histórica dos testes de API.

