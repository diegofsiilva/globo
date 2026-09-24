# Frontend do Argus

Dashboard estático em Next.js App Router. A entrada `/` redireciona para
`/agora`; as demais URLs públicas são `/explorar`, `/comparar`, `/hipoteses`,
`/timeline` e `/recorte`.

O contrato HTTP que a interface já chama e o que ela espera da API de leitura
e do motor de hipóteses está em [rotas-frontend.md](./rotas-frontend.md).

## Organização

```text
src/
├── app/
│   ├── (operations)/
│   │   ├── (dashboard)/        # entrada /, redirecionada para /agora
│   │   ├── _components/        # moldura e navegação deste grupo
│   │   ├── agora/
│   │   ├── comparar/
│   │   ├── explorar/
│   │   ├── hipoteses/
│   │   ├── recorte/
│   │   └── timeline/
│   ├── globals.css             # Tailwind, tema, animações e reset
│   └── layout.tsx              # documento HTML raiz
├── lib/                        # contratos e adapters compartilhados
├── components/ui/              # primitivas shadcn customizadas para o Argus
└── providers/                  # providers usados por ilhas específicas
```

O route group `(operations)` não participa da URL. Cada `page.tsx` é um
Server Component de composição e metadata. Código específico de uma rota fica
próximo dela em `_components`, `_lib` e `_mocks`; somente contratos ou adapters
consumidos por mais de uma fronteira ficam em `src/lib`.

O `QueryProvider` envolve apenas a página que executa consultas no cliente.
As telas demonstrativas mantêm suas fixtures em `_mocks`, deixando explícito
que esses dados não vieram da API de eventos.

## Estilos

O frontend usa Tailwind CSS v4 com configuração CSS-first em `globals.css`.
Paletas, tipografia e animações são tokens de `@theme`; os componentes usam
utilities Tailwind colocalizadas em arquivos `*.styles.ts`. `clsx` compõe os
estados condicionais sem depender de CSS Modules ou `tailwind.config`.

As primitivas acessíveis ficam em `src/components/ui` e seguem a estrutura do
shadcn/ui. O projeto mantém somente `button`, `badge`, `select`, `toggle-group`,
`sheet`, `separator`, `input`, `tooltip`, `table`, `skeleton` e `alert`. A
composição das telas continua próxima das rotas e usa `cn()` de `src/lib/utils.ts`.
Radix fornece comportamento e semântica; cores, radius, bordas e estados são
definidos pelos tokens Argus, sem o tema visual padrão do shadcn.

Archivo é a fonte da interface e IBM Plex Mono identifica horários, métricas e
rótulos técnicos. O tema inicial segue o sistema; o seletor do cabeçalho
persiste a escolha em `argus-theme` e aplica a classe no documento com
`next-themes`.

Há um único vocabulário de tokens de cor, o canônico do `@theme` (`--foreground`,
`--muted-foreground`, `--subtle-foreground`, `--border`, `--border-soft`,
`--border-strong`, `--surface`, `--surface-raised`, `--primary`, `--destructive`,
`--warning`…). Os aliases globais (`--ink`, `--muted`, `--soft`, `--line`, `--red`,
`--canvas`) e os forks por tela (`--agora-*`, `--explore-*`) foram removidos: eram
indireção sem diferença visual. Cor fixa em `*.styles.ts` é bug — não responde ao
tema. As duas exceções são o `meta[theme-color]` em `theme-toggle.tsx` e os gaps
responsivos `--explore-section-gap` / `--explore-block-gap`, que são espaçamento.

A tipografia tem seis degraus, declarados como tokens `--text-*` no `globals.css`:
`text-micro` (12px, rótulos e legendas), `text-label` (13px), `text-body` (14px),
`text-section` (16px, h2), `text-subhead` (20px, métricas de bloco) e
`text-display` (28px, h1 de tela e métricas de destaque). O h1 de toda tela usa a
constante `screenTitle` de `(operations)/_components/screen-frame.styles.ts`.
Nenhum texto abaixo de 12px — a única exceção é `[font-size:16px]` nos inputs em
telas estreitas, que existe para o iOS não dar zoom no foco.

Estilos inline ficam restritos a valores calculados em runtime, como altura e
posição de barras dos gráficos. Breakpoints, foco visível, redução de movimento
e pseudo-elementos do seletor temporal são expressos por variantes Tailwind.

## Configuração

O build usa a API de leitura para eventos e hipóteses:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_HYPOTHESES_SOURCE=api
```

- `mock`: usa o adapter e as fixtures locais de `/hipoteses`.
- `api`: usa `NEXT_PUBLIC_API_URL` e preserva o contrato HTTP autenticado
  `GET /api/v1/hypotheses`.

Os alvos `make -C apps/fullstack frontend-dev` e `frontend-build` convertem
`ARGUS_API_URL` e `HYPOTHESES_SOURCE` nas variáveis públicas acima. O fluxo
gerado por `make -C apps/fullstack env` usa a API por padrão; `mock` precisa ser
escolhido explicitamente para desenvolvimento visual.

## Desenvolvimento e validação

```bash
cd apps/fullstack/frontend
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000 \
  NEXT_PUBLIC_HYPOTHESES_SOURCE=mock npm run dev

npm run lint
npx next typegen
npx tsc --noEmit
test -z "$(find src -name '*.module.css' -print)"
NEXT_PUBLIC_API_URL=http://localhost:8000 \
  NEXT_PUBLIC_HYPOTHESES_SOURCE=mock npm run build -- --webpack
```

O projeto usa `output: "export"` e `trailingSlash: true`, produzindo o site
estático em `out/` no formato esperado pelo website do S3.
