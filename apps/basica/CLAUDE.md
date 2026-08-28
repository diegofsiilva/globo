@AGENTS.md

## Específico do Claude Code

- Cada subdiretório com regras próprias tem `AGENTS.md` + um `CLAUDE.md` de uma
  linha que o importa. Eles carregam sob demanda, quando você lê arquivos ali
  dentro — se for mexer em `backend/`, leia `backend/AGENTS.md` antes de editar.
- `.claude/` e `.codex/` estão no `.gitignore`, então **regras em
  `.claude/rules/` não chegam ao time**. Conhecimento que todos precisam vai
  para o `AGENTS.md` da área.
- Use plan mode antes de mexer em `db/migrations/`, `infra/` ou em qualquer
  coisa que rode `terraform apply`: são as áreas onde um erro custa uma sessão
  inteira do Learner Lab.
- Não rode `terraform apply`, `make deploy`, `make load`, `make push` nem
  `make tf-destroy` sem o usuário pedir explicitamente. Todos mexem em
  infraestrutura viva; `tf-destroy` apaga o banco com as 33 tabelas carregadas.
- `frontend/AGENTS.md` começa com um bloco delimitado por
  `BEGIN:nextjs-agent-rules`, escrito pelo `next dev`. Não apague: ele é
  recriado a cada execução e some do diff só se for commitado junto.
