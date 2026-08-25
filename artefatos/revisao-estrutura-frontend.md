# Revisão e refatoração estrutural do frontend Next.js

**Data:** 25/08/2026

**Escopo revisado:** `apps/basica/frontend`

**Base da revisão:** `develop` em `9dccc682be93cb88fd8679af079b2124df1678c3`

**HEAD originalmente revisado:** `3b06bc9c3ad7061f437b065f21c37fa07094b559`

**Estado refatorado observado:** `29196c089cdf4e62f6e2cb595a3f9444b3259a99`

## Objetivo e método

A revisão original usou `git diff develop...3b06bc9 -- apps/basica/frontend` e
separou os resultados em dois eixos independentes:

- **Standards:** aderência à organização do App Router, fronteiras
  Server/Client, colocalização e separação de responsabilidades;
- **Spec:** correspondência entre o que a interface aparenta entregar e os
  requisitos de `artefatos/requisitos.md`.

`docs/agents/issue-tracker.md` não existe neste repositório. Por isso,
`artefatos/requisitos.md` foi usado como especificação local. Uma revisão
futura que dependa de issues externas deverá primeiro disponibilizar essa fonte
com `/setup-matt-pocock-skills`.

Durante a execução, o estado do branch foi alterado externamente: `HEAD` passou
de `3b06bc9` para `29196c0`, e esse commit já estava também no remoto quando a
mudança foi detectada. Esta execução não criou nem desfez commits. As evidências
abaixo descrevem o conteúdo observado em `29196c0` e as verificações locais
posteriores.

## Estrutura anterior e estrutura resultante

Antes, `(pages)` era um agrupamento genérico, seis rotas tinham layouts que
apenas devolviam `children`, todas as páginas eram Client Components completas
e as fixtures estavam concentradas em `src/mocks`:

```text
src/
├── app/
│   └── (pages)/
│       ├── (dashboard)/page.tsx
│       ├── agora/{layout,page}.tsx
│       ├── comparar/{layout,page}.tsx
│       ├── explorar/{layout,page}.tsx
│       ├── hipoteses/{layout,page}.tsx
│       ├── recorte/{layout,page}.tsx
│       └── timeline/{layout,page}.tsx
├── components/
├── mocks/
└── providers/app-providers.tsx
```

Depois, `(operations)` nomeia a responsabilidade do grupo e concentra somente
a moldura compartilhada. Cada rota possui um `page.tsx` servidor para metadata
e composição e colocaliza seus detalhes privados:

```text
src/
├── app/
│   └── (operations)/
│       ├── (dashboard)/{page.tsx,_components/,dashboard.module.css}
│       ├── _components/                 # navegação e ScreenFrame do grupo
│       ├── agora/{page.tsx,_components/,_mocks/}
│       ├── comparar/{page.tsx,_components/,_mocks/}
│       ├── explorar/{page.tsx,_components/,_lib/,_mocks/}
│       ├── hipoteses/{page.tsx,_components/,_lib/,_mocks/}
│       ├── recorte/{page.tsx,_components/,_mocks/}
│       ├── timeline/{page.tsx,_components/,_mocks/}
│       └── layout.tsx
├── lib/events/                          # integração compartilhada existente
└── providers/query-provider.tsx
```

Route groups entre parênteses não participam do caminho público. As URLs
`/agora`, `/explorar`, `/comparar`, `/hipoteses`, `/timeline` e `/recorte`
permanecem; a entrada `/` agora redireciona para `/agora`.

## Standards

| # | Achado original | Evidência original | Tratamento estrutural | Resultado |
|---|---|---|---|---|
| S1 | Fronteiras Client excessivas: as sete páginas continham `"use client"`. | `app/(pages)/**/page.tsx` | Todos os `page.tsx` agora são Server Components de composição. Estado, efeitos e handlers ficaram em `_components` client privados; conteúdo estático de Timeline e Recorte permanece no servidor. | **Aprovado** |
| S2 | O React Query envolvia toda a aplicação. | `app/layout.tsx` e `providers/app-providers.tsx` | `QueryProvider` foi removido do layout raiz e envolve somente `/hipoteses`, a rota pública que ainda executa consulta client. | **Aprovado** |
| S3 | Explorar concentrava regras temporais, filtros, controles e apresentação em um único arquivo de 671 linhas. | `app/(pages)/explorar/page.tsx` | A composição client ficou em `explorar-screen.tsx`; cálculo temporal e configuração foram extraídos para `_lib`, e o detalhamento filtrável para `exploration-breakdown.tsx`. | **Aprovado** |
| S4 | Hipóteses misturava contrato, transporte HTTP e fallback mock, criando acoplamento entre produção e fixtures. | `lib/hypotheses/api.ts` | Tipos, score, seleção de fonte e adapter HTTP foram separados em `_lib`; o adapter mock ficou em `_mocks` e o HTTP não importa fixtures. | **Aprovado** |

Outras decisões coerentes com a estrutura do App Router:

- os seis layouts intermediários sem responsabilidade foram removidos;
- componentes e CSS compartilhados apenas pelo grupo operacional ficaram em
  `(operations)/_components`, não em uma pasta global genérica;
- o CSS do dashboard migrou de `globals.css` para um CSS Module local;
- `globals.css` reteve somente tokens, reset e regras globais;
- não existe mais `src/mocks` nem import de `@/mocks`.

**Resumo Standards:** 4 achados originais, 4 tratados. O principal problema —
páginas inteiras como Client Components — não permanece na estrutura final.

## Spec

Esta refatoração não implementa RF08–RF17. Ela torna explícita a procedência dos
dados para evitar que estrutura de código seja apresentada como prova de
integração funcional.

| # | Achado original | Situação após a refatoração | Resultado |
|---|---|---|---|
| P1 | Agora, Explorar, Comparar, Timeline e Recorte exibiam cenários fixos como se derivassem dos eventos coletados, afetando RF11–RF16. | As cinco rotas continuam simuladas, por decisão de escopo, mas cada fixture está em `_mocks` dentro da rota e a documentação as identifica como demonstrativas. | **Reprovado funcionalmente; procedência explicitada** |
| P2 | A rota `/` buscava no máximo 100 eventos e aplicava filtros adicionais somente nessa primeira página, tornando RF08–RF10 incompletos. | A entrada `/` agora redireciona para `/agora`; o dashboard integrado foi preservado no código, mas deixou de possuir rota pública. Paginação e filtros no backend não foram implementados. | **Reprovado** |
| P3 | Hipóteses caía silenciosamente em dados simulados quando o endpoint não estava configurado. | Não há fallback implícito. `NEXT_PUBLIC_HYPOTHESES_SOURCE=mock\|api` é obrigatório; `api` também exige `NEXT_PUBLIC_HYPOTHESES_API_URL`. Configuração ausente ou inválida interrompe o build. | **Aprovado quanto à fronteira; RF17 não verificado** |
| P4 | O dashboard integrado `/` não aparecia na navegação das seis telas operacionais. | `/` passou a redirecionar para `/agora`, alinhando a entrada à navegação. O dashboard integrado, porém, não está mais acessível por uma rota pública. | **Parcialmente aprovado** |

Classificação atual por rota:

| Rota | Fonte observada | Classificação |
|---|---|---|
| `/` | redirect para `/agora` | **Entrada**, sem consulta própria |
| `/agora` | fixture local | **Mock explícito** |
| `/explorar` | fixture local | **Mock explícito** |
| `/comparar` | fixture local | **Mock explícito** |
| `/hipoteses` | adapter selecionado por `mock\|api` | **Configurável**; RF17 não é comprovado sem endpoint e validação do parceiro |
| `/timeline` | fixture local | **Mock explícito** |
| `/recorte` | fixture local | **Mock explícito** |

**Resumo Spec:** 4 achados originais; 1 fronteira corrigida, 1 topologia
parcialmente corrigida e 2 limitações funcionais mantidas. O pior achado
continua sendo a ausência de derivação dos eventos coletados nas cinco telas de
análise simuladas.

## Configuração de Hipóteses

O contrato HTTP permanece `GET /api/v1/hypotheses`, com `from`, `to` e filtros
de escopo na query string. O Makefile fornece explicitamente o modo `mock` nos
fluxos suportados enquanto o endpoint não existe:

```dotenv
HYPOTHESES_SOURCE=mock
HYPOTHESES_API_URL=
```

No bundle, os nomes correspondentes são
`NEXT_PUBLIC_HYPOTHESES_SOURCE` e `NEXT_PUBLIC_HYPOTHESES_API_URL`. O modo
`api` nunca importa fixtures pelo adapter HTTP e falha antes de exportar o site
quando a URL está ausente.

## Evidências de verificação

Executado em `apps/basica/frontend`:

| Verificação | Resultado |
|---|---|
| `npm run lint` | **Aprovado** |
| `npx next typegen` após limpar somente `.next` | **Aprovado** |
| `npx tsc --noEmit` | **Aprovado** |
| build Webpack com `NEXT_PUBLIC_HYPOTHESES_SOURCE=mock` | **Aprovado** |
| build Webpack com `NEXT_PUBLIC_HYPOTHESES_SOURCE=api` e URL explícita | **Aprovado** |
| build sem `NEXT_PUBLIC_HYPOTHESES_SOURCE` | **Reprovado como esperado**, com mensagem exigindo `mock` ou `api` |
| build com fonte inválida | **Reprovado como esperado**, com a mesma mensagem clara |
| build `api` sem `NEXT_PUBLIC_HYPOTHESES_API_URL` | **Reprovado como esperado**, com mensagem exigindo a URL |
| busca por `"use client"` em `page.tsx` | **Aprovado**, nenhuma ocorrência |
| busca por `@/mocks` e existência de `src/mocks` | **Aprovado**, nenhuma ocorrência e diretório ausente |
| `git diff --check` no escopo | **Aprovado** |

Os dois builds válidos exportaram como conteúdo estático as sete rotas
esperadas. O `_not-found` adicional é uma rota interna gerada pelo Next.js.

## Limitações e próximos passos

- Não houve navegador controlável nesta etapa; interação, teclado, responsividade
  e equivalência visual são **não verificáveis nesta etapa**. Build e inspeção
  estática não substituem esse teste.
- Não foram usados screenshots, vídeos ou artefatos históricos como evidência
  de comportamento atual.
- Paginação completa, filtros sobre todo o conjunto e integração de RF11–RF17
  continuam fora desta refatoração. O antigo dashboard integrado permanece no
  código, mas sem rota pública após o redirecionamento de `/` para `/agora`.
- `artefatos/frontend.md` não foi editado por esta execução. Porém, o arquivo
  passou a constar no commit externo `29196c0`; portanto, a condição de manter
  toda a refatoração sem commit não corresponde mais ao estado observado do
  branch.
