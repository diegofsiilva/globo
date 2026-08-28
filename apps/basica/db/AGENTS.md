# AGENTS.md — schema e migrations

`migrations/` contém o schema inteiro, em `.sql` numerado com três dígitos e
aplicado em ordem lexicográfica por `tools/migrate.py`. Não há Alembic nem
sqitch: o runner cabe em duzentas linhas e é deliberadamente mínimo.

## Regras

1. **Migration aplicada não se edita.** O runner grava o checksum de cada
   arquivo em `public.schema_migrations` e aborta quando ele muda. Existe
   `--forcar`, mas ele só reescreve o checksum — não reaplica nada. Mudança de
   schema = arquivo novo.
2. **Prefixo de três dígitos, sempre.** É o que faz a ordem lexicográfica
   coincidir com a ordem de dependência. `10_x.sql` sem o zero quebraria a ordem
   em silêncio.
3. **`016_gold_checkpoint.sql` e `017_analysis_coordination.sql` são baseline
   congelado.** Checkpoint, claim, lease, heartbeat, takeover e fencing estão
   concluídos ali; o resto do sistema depende desse contrato.
4. **`004_bronze_corrente_argus.sql` é gerado**, não escrito à mão. Ele sai do
   schema do dump via `make -C apps/basica gen-ddl`, que lê os Parquet.
5. **Toda view `v_*` filtra `available_at <= sim.now()`.** Uma view nova sem
   esse filtro vaza futuro para a API e para o detector. Não há teste que pegue
   isso automaticamente — é responsabilidade de quem escreve a view.
6. **`argus_reader` recebe `SELECT` só em view.** Ao criar uma view pública,
   lembre do `GRANT`; ao criar tabela, não conceda nada a ele.

## Camadas

| Schema | Guarda | Invariante |
|---|---|---|
| `bronze` | `change_log` (append-only, por trigger) + tabela corrente por origem + `event` | A corrente é o MERGE do log; dá para reconstruí-la do zero |
| `silver` | sinais, sessões, `analysis_fact_version` | Canonicaliza tempo; versões imutáveis por LSN |
| `gold` | features, qualidade, hipóteses, evidências | Produtos de leitura, com barreira de LSN |
| `detect` | runs, claims, cursor, baseline, anomalias | Coordena o detector por checkpoint |
| `sim` | relógio virtual (`sim.now()`), falhas injetadas | O "agora" de todo o sistema |
| `etl` | funções do ETL incremental | `etl.executar_bronze_silver()`, `etl.executar_silver_gold()` |

## Trabalhar nisso

```bash
make -C apps/basica db-local          # sobe o Postgres 16 e aplica tudo
make -C apps/basica migrate-status    # o que já rodou
make -C apps/basica db-psql           # psql dentro do container
make -C apps/basica etl               # recompute completo: gold.rebuild_tudo()
make -C apps/basica count             # linhas por camada
```

Depois de adicionar uma migration, rode `make -C apps/basica db-local` do zero
(o alvo recria o container) e em seguida `make -C apps/basica test`: o teste
`processing/tests/test_migrations_upgrade.py` valida a sequência.
