# Frontend do Argus

Dashboard estático em Next.js App Router. As URLs públicas são `/`, `/agora`,
`/explorar`, `/comparar`, `/hipoteses`, `/timeline` e `/recorte`.

## Organização

```text
src/
├── app/
│   ├── (operations)/
│   │   ├── (dashboard)/
│   │   ├── _components/        # moldura e navegação deste grupo
│   │   ├── agora/
│   │   ├── comparar/
│   │   ├── explorar/
│   │   ├── hipoteses/
│   │   ├── recorte/
│   │   └── timeline/
│   ├── globals.css             # tokens, reset e estilos globais
│   └── layout.tsx              # documento HTML raiz
├── lib/                        # contratos e adapters compartilhados
└── providers/                  # providers usados por ilhas específicas
```

O route group `(operations)` não participa da URL. Cada `page.tsx` é um
Server Component de composição e metadata. Código específico de uma rota fica
próximo dela em `_components`, `_lib` e `_mocks`; somente contratos ou adapters
consumidos por mais de uma fronteira ficam em `src/lib`.

O `QueryProvider` envolve apenas as páginas que executam consultas no cliente.
As telas demonstrativas mantêm suas fixtures em `_mocks`, deixando explícito
que esses dados não vieram da API de eventos.

## Configuração

O build exige uma fonte explícita para Hipóteses:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_HYPOTHESES_SOURCE=mock
NEXT_PUBLIC_HYPOTHESES_API_URL=
```

- `mock`: usa o adapter e as fixtures locais de `/hipoteses`.
- `api`: exige `NEXT_PUBLIC_HYPOTHESES_API_URL` e preserva o contrato HTTP
  `GET /api/v1/hypotheses`.

Os alvos `make -C apps/basica frontend-dev` e `frontend-build` convertem
`HYPOTHESES_SOURCE` e `HYPOTHESES_API_URL` nas variáveis públicas acima. O
fluxo gerado por `make -C apps/basica env` usa `mock` enquanto não houver um
endpoint do motor de hipóteses.

## Desenvolvimento e validação

```bash
cd apps/basica/frontend
npm ci
NEXT_PUBLIC_API_URL=http://localhost:8000 \
  NEXT_PUBLIC_HYPOTHESES_SOURCE=mock npm run dev

npm run lint
npx next typegen
npx tsc --noEmit
NEXT_PUBLIC_API_URL=http://localhost:8000 \
  NEXT_PUBLIC_HYPOTHESES_SOURCE=mock npm run build -- --webpack
```

O projeto usa `output: "export"` e `trailingSlash: true`, produzindo o site
estático em `out/` no formato esperado pelo website do S3.
