# AGENTS.md — API de leitura

Flask sobre Lambda, arquitetura hexagonal. Serve o dashboard. A única escrita é
o feedback idempotente de uma hipótese gerada; a ingestão não passa por aqui.
Detalhe de rotas, filtros e exemplos: `README.md` deste diretório.

## Regras

1. **Nenhuma consulta toca tabela base.** Toda leitura aponta para uma view
   `v_*`; o feedback chama a função `SECURITY DEFINER`
   `gold.submit_hypothesis_feedback`. O usuário `argus_reader` só tem `SELECT`
   nas views — SQL contra tabela base falha por permissão negada, de propósito.
2. **Rota nova exige entrada no OpenAPI.** A spec é montada em código
   (`interfaces/openapi.py`), importando as mesmas constantes que o adaptador
   usa para validar. `tests/test_openapi.py` quebra nos dois sentidos: rota sem
   documentação e documentação sem rota.
3. **A redação de dado pessoal acontece na saída** (`application/redaction.py`),
   nunca na entrada — a bronze guarda o evento como o aparelho mandou. Campo
   novo que possa carregar identificador passa pela redação antes de virar
   resposta. É o RNF10.
4. **Paginação é keyset, não `OFFSET`.** O cursor é opaco (base64) e carrega a
   posição da última linha lida. Cursor corrompido devolve **422**, nunca a
   primeira página em silêncio.
5. **`boto3` não volta.** A API não fala com serviço nenhum da AWS: lê do
   PostgreSQL e a autorização vem de `GRANT`. Cada dependência nova pesa no zip
   da Lambda.
6. **Nenhuma URL da API entra no código.** Ela sai de
   `terraform output -raw read_api_url` e vive no `.env`.

## Estrutura

```text
src/telemetry/
├── domain/          # entidades e exceções, sem dependência externa
├── ports/           # interfaces que a aplicação exige da infraestrutura
├── application/     # casos de uso, normalização, redação, sinais
├── infrastructure/  # adaptadores concretos (ver tabela abaixo)
├── interfaces/      # blueprints HTTP e a spec OpenAPI
├── app.py           # fábrica da aplicação Flask
└── config.py        # configuração vinda do ambiente
```

Três adaptadores, separados de propósito — um repositório único teria conjuntos
de métodos que nunca se cruzam:

| Adaptador | Grain |
|---|---|
| `infrastructure/postgres.py` | evento individual de sessão |
| `infrastructure/gold.py` | bucket agregado de 15 min |
| `infrastructure/hypotheses.py` | hipótese gerada |

## Trabalhar nisso

```bash
make -C .. db-local        # PostgreSQL local, uma vez
make -C .. api             # sobe em :5000 contra o banco local
make -C .. test-backend    # pytest
python run.py              # alternativa sem make; instala deps na 1ª execução
```

`ruff` com `line-length = 100`. Os testes montam as linhas com o mesmo
`argus_worker.keys.build_row` que o worker usa — é isso que impede API e worker
de divergirem em silêncio sobre o que é coluna de envelope e o que é payload.

Toda resposta de busca traz `query` (`strategy`, `scanned`, `returned`). Ao
escrever ou revisar uma consulta, mire numa `strategy` indexada
(`indice_sessao`, `indice_aparelho`, `indice_tipo_e_tempo`);
`particao_por_tempo` varre as partições da janela.
