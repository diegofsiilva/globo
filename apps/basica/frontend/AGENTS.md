<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# AGENTS.md — dashboard

Next.js 16 (App Router) com export estático servido por S3. React 19, Tailwind
CSS v4 CSS-first, TanStack Query e primitivas shadcn/ui sobre Radix. O contrato
HTTP que a interface consome está em `rotas-frontend.md`; a organização em
detalhe, no `README.md` deste diretório.

## Regras

1. **A URL da API nunca é escrita no código.** Ela entra no bundle em tempo de
   build por `NEXT_PUBLIC_API_URL`, e o build falha de propósito sem ela — um
   bundle apontando para o próprio domínio devolveria o HTML da página no lugar
   do JSON, e o erro só apareceria no navegador do usuário. Suba sempre por
   `make -C .. frontend-dev` ou `frontend-build`, que injetam a variável.
2. **Cor fixa em `*.styles.ts` é bug** — não responde ao tema. Existe um único
   vocabulário de tokens, o canônico do bloco `@theme` em `app/globals.css`
   (`--foreground`, `--muted-foreground`, `--border`, `--surface`, `--primary`,
   `--destructive`, `--warning`…). Aliases globais e forks por tela foram
   removidos; não reintroduza. As exceções são o `meta[theme-color]` em
   `theme-toggle.tsx` e os gaps responsivos `--explore-section-gap` /
   `--explore-block-gap`, que são espaçamento.
3. **Tipografia tem seis degraus**, tokens `--text-*` no `globals.css`:
   `text-micro` (12px), `text-label` (13px), `text-body` (14px), `text-section`
   (16px, h2), `text-subhead` (20px) e `text-display` (28px). Não invente
   tamanho fora da escala.
4. **Código de rota fica junto da rota**, em `_components`, `_lib` e `_mocks`.
   Só contrato ou adapter consumido por mais de uma fronteira sobe para
   `src/lib`. Cada `page.tsx` é Server Component de composição e metadata.
5. **Dados de fixture ficam em `_mocks/`**, explicitamente separados do que veio
   da API. Não misture mock no caminho de dados real.
6. **`QueryProvider` envolve só a página que consulta no cliente**, não a árvore
   inteira.
7. **O conjunto shadcn é fechado**: `button`, `badge`, `select`, `toggle-group`,
   `sheet`, `separator`, `input`, `tooltip`, `table`, `skeleton` e `alert`.
   Radix dá comportamento e semântica; cores, radius e estados vêm dos tokens
   Argus, sem o tema visual padrão do shadcn. Componha as telas com `cn()` de
   `src/lib/utils.ts` em vez de adicionar primitiva nova.
8. **Export estático.** Nada de rota de API, middleware, ISR ou
   `dynamic = "force-dynamic"` — o build tem que continuar gerando `out/`.

## Rotas

`/` redireciona para `/agora`. As demais URLs públicas são `/explorar`,
`/comparar`, `/hipoteses`, `/timeline` e `/recorte`. O route group
`(operations)` não participa da URL; ele carrega a moldura e a navegação.

## Trabalhar nisso

```bash
make -C .. frontend-install    # npm ci
make -C .. frontend-dev        # :3000, contra a API publicada
make -C .. frontend-build      # gera out/
make -C .. test-frontend       # Vitest: contratos HTTP e componentes
make -C .. test-frontend-e2e   # Playwright: Flask + PostgreSQL argus_test
npm run lint                   # eslint
```

O teste E2E exige o PostgreSQL local (`make -C .. db-local`) e o Chromium do
Playwright (`npx playwright install chromium`). A fixture determinística fica em
`tests/e2e/fixture.sql`, usa somente `argus_test` e executa Hipóteses em modo
`api`; o Vitest simula apenas a fronteira HTTP. Fonte Archivo para interface,
IBM Plex Mono para horário, métrica e rótulo técnico. O tema inicial segue o
sistema e a escolha persiste em `argus-theme` via `next-themes`.
