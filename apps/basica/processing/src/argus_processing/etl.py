"""ETL incremental: chama as funcoes de banco que fazem o trabalho de verdade.

Este modulo e intencionalmente fino. A regra de cada camada, o calculo da
janela e o avanco atomico do watermark moram em SQL
(`db/migrations/010_merge_e_etl.sql`, `015_etl_incremental.sql`) -- pelo mesmo
motivo que `bronze.merge_do_log` mora la: o watermark tem que avancar no MESMO
commit que o dado, e psycopg_pool devolve uma conexao nova a cada
`db.fetch_one`, entao amarrar duas chamadas Python numa unica transacao exigiria
gerenciar a conexao aqui em cima. Uma chamada SQL por ciclo evita o problema
por construcao.
"""

from __future__ import annotations

from typing import Any

from argus_common import Database


def executar_bronze_silver(db: Database, batch_size: int) -> dict[str, Any]:
    """Roda um ciclo do worker bronze->silver.

    Args:
        db (Database): Pool de conexao.
        batch_size (int): Teto de entradas do `bronze.change_log` processadas
            nesta chamada.

    Returns:
        dict[str, Any]: Linha de `etl.executar_bronze_silver` -- `status`
            ('sucesso' | 'sem_pendencia' | 'falha'), `linhas`, `de_lsn`,
            `ate_lsn`, `erro`.
    """
    row = db.fetch_one("SELECT * FROM etl.executar_bronze_silver(%s)", (batch_size,))
    assert row is not None  # a funcao sempre devolve exatamente uma linha
    return row


def executar_silver_gold(db: Database, janela_max_segundos: int) -> dict[str, Any]:
    """Roda um ciclo do worker silver->gold.

    Args:
        db (Database): Pool de conexao.
        janela_max_segundos (int): Teto de quanto tempo virtual esta chamada
            absorve, a partir de onde o watermark parou.

    Returns:
        dict[str, Any]: Linha de `etl.executar_silver_gold` -- `status`
            ('sucesso' | 'sem_pendencia' | 'falha'), `linhas`, `de_ts`,
            `ate_ts`, `erro`.
    """
    row = db.fetch_one(
        "SELECT * FROM etl.executar_silver_gold(%s)", (janela_max_segundos,)
    )
    assert row is not None
    return row
