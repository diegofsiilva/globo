# AGENTS.md — workers de ingestão

Dois consumidores de SQS que gravam na bronze. **Uma imagem só, dois pontos de
entrada** — `python -m argus_worker merge` e `python -m argus_worker event`; o
modo vem do `command` da task definition em `infra/ecs.tf`. Eles compartilham o
laço de SQS, a observabilidade e o pool de conexão, e diferem apenas no que
validam e onde gravam. Rodam em ECS Fargate ARM64.

| Worker | Fila | O que faz |
|---|---|---|
| `event` | `events` | Valida o evento de sessão e grava em `bronze.event` |
| `merge` | `changes` | Grava em `bronze.change_log` **e** faz o MERGE na tabela corrente, na mesma transação |

## Regras

1. **O log e o MERGE vão na mesma transação.** Separá-los abre a janela em que a
   corrente diverge do log, e o log é a fonte de verdade da qual a corrente pode
   ser reconstruída.
2. **A gravação é idempotente.** A mesma mensagem entregue duas vezes (o SQS
   garante *at least once*) não pode duplicar linha nem regredir a corrente para
   uma versão mais antiga.
3. **Schema estrito é perda de dado.** O parque de TVs atualiza devagar; tipo de
   evento desconhecido tem que ser aceito sem alteração de código. Não adicione
   validação que rejeite campo extra.
4. **Payload inválido vai para a DLQ com o motivo** no atributo
   `FailureReason` — nunca é descartado em silêncio. Inspeção:
   `make -C .. dlq`.
5. **`keys.build_row` é o contrato compartilhado.** O backend importa a mesma
   função nos testes. Mudar o que é coluna de envelope e o que vai para o
   payload quebra os dois lados de uma vez — é intencional.

## Estrutura

```text
src/argus_worker/
├── consumer.py     # laço do SQS: receive, processa, delete
├── changes.py      # caminho do change event (log + MERGE)
├── models.py       # validação pydantic dos envelopes
├── keys.py         # build_row: chave e envelope canônicos
├── repository.py   # acesso ao PostgreSQL
└── config.py       # configuração vinda do ambiente
```

`argus-common` (conexão, observabilidade, ciclo de vida) vem de `../common` como
dependência de path. É por isso que o build da imagem tem contexto em
`apps/fullstack/`, e não em `worker/` — dentro do container o `uv sync` não
enxergaria `../common` de outro jeito.

## Trabalhar nisso

```bash
make -C .. test-worker     # pytest (SQS falso via moto, PostgreSQL real)
make -C .. images          # constrói as quatro imagens ARM64
make -C .. replay          # reenvia os eventos de exemplo à API publicada
```

`ruff` com `line-length = 90`. As fixtures dos seis eventos do MVP estão em
`tests/fixtures/` e vêm dos CSVs do BI via `make -C .. events-json` — são
**amostras** de poucas linhas, não um dataset representativo.

Os workers não rodam localmente contra a fila real. Para exercitar o caminho
completo, use `make -C .. replay` contra a API de ingestão publicada.
