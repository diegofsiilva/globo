# AGENTS.md — ETL, detector e motor de hipóteses

Backend determinístico de análise. Um serviço ECS com três threads no mesmo
processo: bronze→silver, silver→gold e o ciclo canário → detector → regras →
score. O fundamento completo está no `README.md` deste diretório.

**Não há classificador supervisionado, LLM, fila nova ou serviço contínuo
adicional — e não deve haver.** Uma hipótese é uma explicação candidata e
auditável para revisão humana, não uma causa-raiz confirmada.

## Regras

1. **Determinismo.** Mesma entrada, mesma saída. Nada de `random` sem semente,
   `datetime.now()` (use `sim.now()`) ou dependência de ordem de dicionário.
2. **Os fatos de análise saem de `bronze.change_log`, não da tabela corrente.**
   É o que conserva duas mudanças da mesma PK que cheguem entre dois ciclos do
   ETL.
3. **Fencing protege o commit.** O claim trava o cursor de
   `manifest_hash + stream_key`, e a captura é `REPEATABLE READ`. Não escreva
   resultado fora desse caminho: dois runs concorrentes sem fencing publicam
   hipóteses inconsistentes.
4. **`016` e `017` são baseline concluído e congelado** (checkpoint, claim,
   lease, heartbeat, takeover, fencing). Não altere.
5. **Regra nova entra em `rules.py` com teste em `test_familias.py`.** São 11
   famílias de hipótese; cada uma precisa de evidência explicável associada.
6. **O modo sombra é o padrão.** As views de hipótese ficam vazias até o evento
   append-only `published`; `withdrawn` volta a ocultar sem apagar histórico.

## Estrutura

```text
src/argus_processing/
├── etl.py                    # bronze→silver e silver→gold
├── catalog.py                # catálogo de fontes
├── quality.py                # canário por fonte
├── detector.py               # EWMA, baseline circadiano, anomalias
├── rules.py                  # as 11 famílias de hipótese
├── scoring.py                # score das hipóteses
├── domain.py                 # tipos do domínio de análise
├── analysis_repository.py    # persistência
├── orchestration.py          # claim, lease, heartbeat, fencing
├── pipeline.py               # composição do ciclo
└── analysisctl.py            # CLI de operação
```

## Trabalhar nisso

```bash
make -C .. db-local            # o banco é obrigatório aqui
make -C .. test-processing     # a suíte mais densa do repositório
make -C .. etl-incremental     # um ciclo manual do ETL
make -C .. etl                 # recompute completo, idempotente
```

`ruff` com `line-length = 90`. O código do repositório é a fonte de verdade — a
imagem que estiver rodando na AWS pode estar defasada.
