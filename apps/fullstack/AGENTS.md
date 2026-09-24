# AGENTS.md — Argus

Sistema distribuído de telemetria para diagnóstico de degradação de streaming.
Inteli T15 · 2026-2A · parceiro Grupo Globo. Todo o código do projeto vive neste
diretório: quatro serviços Python, um dashboard Next.js e o Terraform.

Este arquivo é o contrato para agentes de código. Vários subdiretórios têm o seu
próprio `AGENTS.md` com regras mais específicas — **o mais próximo do arquivo
editado vence**. Contexto de negócio, UX e requisitos fica em `../../artefatos/`;
o `../../README.md` é a documentação para humanos.

## Regras invioláveis

1. **Não crie arquivo novo na raiz do repositório.** A estrutura versionada é fixa:
   `README.md`, `.gitignore`, `apps/`, `artefatos/`, `assets/`, `slides/`.
2. **Comandos saem do `Makefile`, não de scripts novos.** Rode
   `make -C apps/fullstack` para listar os alvos. Se já existe alvo para o que você
   quer fazer, use-o em vez de reproduzir os passos à mão.
3. **Nenhum segredo entra no repositório.** URL de API, id de conta AWS,
   endpoint de RDS e senha nunca vão para código, teste, doc ou mensagem de
   commit. Os valores saem de `terraform output` e vivem em `.env`, que é
   gitignored; `.env.example` mostra apenas as chaves.

   As três APIs exigem `Authorization: Bearer` desde a adequação do RNF09. Os dois
   tokens saem de `make auth-rotate`, que os imprime uma única vez; a AWS guarda
   apenas o SHA-256 de cada um. Token não entra em código, teste, doc, commit,
   print, vídeo nem no bundle do dashboard — no navegador ele vive só em
   `sessionStorage`, colado pelo operador na tela de acesso.
4. **A AWS é um AWS Academy Learner Lab.** Todo comando `aws` leva
   `--profile g4`; o Terraform não aceita `--profile` e lê `AWS_PROFILE` /
   `AWS_REGION`. O id da conta do lab muda a cada sessão nova: confira com
   `aws sts get-caller-identity --profile g4` e atualize `existing_role_arn` no
   `terraform.tfvars` **antes** de qualquer `plan` ou `apply`.
5. **Migration aplicada é imutável.** `tools/migrate.py` guarda o checksum e
   aborta quando o arquivo muda. Alteração de schema = novo arquivo
   `NNN_nome.sql`. `016_gold_checkpoint.sql` e `017_analysis_coordination.sql`
   são baseline congelado.
6. **Leitura só através das views `v_*`.** O usuário `argus_reader` tem `SELECT`
   apenas nas views, e toda view filtra `available_at <= sim.now()`. Uma consulta
   escrita contra tabela base falha por permissão negada — isso é a barreira que
   impede vazamento de futuro, não um descuido de `GRANT`.
7. **Os testes rodam contra um PostgreSQL de verdade** (`make -C apps/fullstack
   db-local`, porta 55432). Não troque o banco por dublê: a parte difícil deste
   sistema é o SQL. Sem o banco no ar, os testes que dependem dele são *pulados*,
   não quebrados. Dublê de SQS (`moto`) continua sendo o esperado.
8. **Nunca commite em `main`.** Fluxo: branch de tema → `develop` → `main`.
9. **Não toque em `../../argus_dump.sql` nem em `../../data/parquet/`.** São 4 GB
   de dado cedido pelo parceiro, não redistribuível, e o Parquet derivado dele.

## Antes de entregar

```bash
make -C apps/fullstack check    # lint + testes + terraform validate
```

Quando só uma área mudou, o alvo específico basta: `test-backend`,
`test-worker`, `test-simulator`, `test-processing`, `lint`. `tf-validate` exige
`make -C apps/fullstack tf-init` uma vez. O frontend valida com
`cd apps/fullstack/frontend && npm run lint` e `npm run build`.

## Mapa

| Caminho | O que é |
|---|---|
| `db/migrations` | O schema inteiro, em `.sql` numerado e aplicado em ordem |
| `backend` | API de leitura: Flask sobre Lambda, arquitetura hexagonal |
| `worker` | Workers de ingestão (`event` e `merge`): SQS → bronze |
| `processing` | ETL incremental, detector e motor das 11 famílias de hipótese |
| `simulator` | Relógio virtual `sim.now()` e reemissão das mudanças |
| `loader` | Carga inicial das 33 tabelas, Parquet → PostgreSQL |
| `common` | Conexão, observabilidade e ciclo de vida compartilhados |
| `frontend` | Dashboard Next.js, export estático servido por S3 |
| `infra` | Terraform de toda a infraestrutura AWS |
| `tools` | `migrate.py`, `gen_ddl.py`, `etl_dump.py`, `replay_events.py` |

## Como o dado anda

Dois fluxos de ingestão independentes desembocam no mesmo banco, e um fluxo de
leitura sai dele:

```
App de TV  ──> API Gateway ──> SQS ──> ECS (event worker) ─┐
Simulador  ──> API Gateway ──> SQS ──> ECS (merge worker) ─┴─> RDS PostgreSQL
                                                                    │
                                          Dashboard <── Lambda <────┘
```

Dentro do banco, quatro camadas de dado: `bronze` (log append-only + tabela
corrente), `silver` (sinais, sessões, versões imutáveis por LSN), `gold`
(features, qualidade, hipóteses, evidências) e `detect` (runs, claims, cursor,
baseline). Mais `sim` (o relógio) e `etl` (as funções de transformação).

**O relógio virtual é o conceito central.** O dataset é um dump do passado; o
sistema tem um presente próprio, `sim.now()`. Toda linha carrega `available_at`
— o instante em que a informação ficaria disponível na vida real, contando a
latência da fonte (a NPAW entrega com 28 h de atraso; o Prometheus, com 1 min).
Qualquer código que precise saber "que horas são" pergunta a `sim.now()`, nunca
ao relógio do processo.

## Convenções de código

- **Python 3.12**, ambientes montados por `uv` a partir do `pyproject.toml` de
  cada app. Não crie `requirements.txt` nem ative venv à mão; use `uv run`.
- **`ruff`** faz lint e formatação. A `line-length` varia por app (100 no
  backend, 90 no worker) — respeite o `pyproject.toml` local, não uniformize.
- **Docstrings PEP 257 em Python e JSDoc em JavaScript/TypeScript.** Todo módulo
  tem cabeçalho descritivo e toda função documenta parâmetros, retorno e
  comportamento.

  **A regra é verificada, não confiada.** `ruff` com o conjunto `D` (convenção
  Google) em todos os apps Python, e `jsdoc/require-jsdoc` no ESLint do
  frontend — os dois entram no `make check`. Ficam de fora, por decisão
  explícita nos respectivos arquivos de configuração: `tests/**`, os fixtures em
  `_mocks/` e as primitivas shadcn em `components/ui/`. Nesses lugares o nome do
  teste ou do componente já é a descrição, e exigir um bloco produziria linhas
  que repetem o identificador.

  Num código tipado, o que falta na documentação é o **porquê** — não repita o
  que a assinatura já diz.
- **Comentário explica o porquê, não o quê.** O padrão do repositório é comentar
  a decisão não óbvia (por que a porta é 55432, por que `boto3` saiu do backend)
  e deixar o resto falar por si. Não remova esses comentários ao refatorar.
- **Idioma:** código, comentários, docstrings, documentação e mensagens de
  commit em **português**. Identificadores de domínio já em inglês
  (`change_log`, `feature_bucket`, `available_at`) ficam como estão.
- **Commits:** Conventional Commits em português, no imperativo
  (`feat: integra tela Timeline com rota /timeline`).

## Guias por área

Leia o `AGENTS.md` do diretório antes de mexer nele: `db/`, `backend/`,
`worker/`, `processing/`, `infra/`, `frontend/`.

Referência mais funda, quando o guia da área não bastar:
`../../README.md` (visão geral e passo a passo de deploy),
`../../artefatos/plano-argus-v3.md` (decisões de arquitetura),
`../../artefatos/mvp-inicial.md` (o que está no ar e relatório de testes),
`../../artefatos/requisitos.md` (RF/RNF, usados nas tabelas de rota).
