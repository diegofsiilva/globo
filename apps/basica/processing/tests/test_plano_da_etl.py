"""O caminho de leitura da ETL incremental tem que ser indexado.

Este arquivo nao mede tempo. Medir tempo em teste produz um portao instavel --
uma maquina carregada reprova uma consulta correta, e ninguem confia mais no
resultado. O que ele verifica e o PLANO: se o PostgreSQL alcanca as linhas por
indice ou varrendo a tabela.

A diferenca importa porque muda a forma do custo, e nao so o valor: uma
varredura custa proporcional ao tamanho da tabela, um indice custa proporcional
ao que se pede. A ETL le um lote fixo a cada ciclo; se o custo acompanhar a
tabela, o ciclo desacelera para sempre conforme a bronze cresce -- foi
exatamente o que aconteceu na implantacao, onde o ciclo passou a levar ~16 min
para um lote de 50.000 linhas.

Ver `db/migrations/030_indice_lsn_em_evento.sql`.
"""

from __future__ import annotations

# Linhas inseridas antes de olhar o plano. Com a tabela vazia o planejador
# escolhe varredura mesmo havendo indice -- e a decisao certa para uma tabela
# de zero pagina, e nao diria nada sobre o caso que interessa. Este volume e o
# suficiente para a escolha passar a ser informativa, sem deixar o teste lento.
LINHAS = 100_000

# Consulta pedida bem no fim da faixa: e assim que a ETL le, sempre a partir do
# marcador, que caminha para a frente.
CORTE = 90_000


def _povoar(db) -> None:
    """Grava linhas em `bronze.event` com `_lsn` DESCORRELACIONADO de `ts`.

    Linhas consecutivas de `_lsn` caem em meses diferentes, e portanto em
    particoes diferentes. Nao e artificio de teste: e o caso real. O `_lsn` sai
    de uma sequencia global, na ordem em que o dado chega; o `ts` e o instante
    em que o evento ocorreu no aparelho. Reprocessamento, dispositivo com
    relogio errado e carga historica separam os dois a vontade.

    E dai vem a razao de existir do indice: como `_lsn` nao acompanha `ts`, uma
    faixa de `_lsn` toca TODAS as particoes, e particionar por `ts` nao poda
    nada. Sem indice, so resta varrer a tabela inteira.

    Sao NOVE meses para oito particoes mensais: o nono cai na particao DEFAULT,
    que existe para o evento fora da faixa prevista -- aparelho com relogio
    errado, que este sistema aceita e marca em vez de descartar. Incluir a
    default importa para o teste: uma particao vazia e varrida de qualquer
    forma, porque varrer zero pagina e mais barato que abrir um indice, e a
    assercao nao distinguiria isso de uma varredura de verdade.
    """
    with db.connection() as conn:
        conn.execute(
            """
            INSERT INTO bronze.event (
              event_id, ts, event_name, session_id, device_id, payload,
              _lsn, _captured_at)
            SELECT 'evt-plano-' || i,
                   timestamptz '2026-05-05 00:00:00+00'
                     + ((i %% 9) * interval '1 month')
                     + ((i %% 27) * interval '1 hour'),
                   'request', 's-' || i, 'd-' || (i %% 1000), '{}'::jsonb,
                   i, now()
              FROM generate_series(1, %s) AS i
            """,
            (LINHAS,),
        )
        # Sem estatistica atualizada o planejador decide no escuro, e o plano
        # observado diria mais sobre o ANALYZE ausente do que sobre o indice.
        conn.execute("ANALYZE bronze.event")


def _plano(db, consulta: str, parametros: tuple) -> str:
    """Devolve o plano de execucao como texto."""
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute("EXPLAIN (COSTS OFF) " + consulta, parametros)
        return "\n".join(linha[0] for linha in cur.fetchall())


def test_a_fronteira_do_lote_e_alcancada_por_indice(db):
    """`etl.proxima_faixa_lsn` decide o lote de cada ciclo -- roda sempre.

    Esta e a consulta que abre todo ciclo da ETL. Se ela varrer a tabela, nao
    existe tamanho de lote que salve o ciclo: o custo ja foi pago antes de uma
    linha ser processada.
    """
    _povoar(db)

    plano = _plano(
        db,
        "SELECT _lsn FROM bronze.event WHERE _lsn > %s ORDER BY _lsn LIMIT 1000",
        (CORTE,),
    )

    assert "Seq Scan" not in plano, (
        "a fronteira do lote esta varrendo bronze.event; falta indice em _lsn:\n" + plano
    )
    assert "Index" in plano


def test_a_promocao_para_silver_e_alcancada_por_indice(db):
    """`silver.build_session_event` le a faixa de `_lsn` -- o outro ponto quente.

    Mesma coluna, mesma tabela, mesmo ciclo: sao duas varreduras por ciclo
    quando o indice falta, e nao uma.
    """
    _povoar(db)

    plano = _plano(
        db,
        "SELECT event_id FROM bronze.event WHERE _lsn > %s AND _lsn <= %s",
        (CORTE, CORTE + 1000),
    )

    assert "Seq Scan" not in plano, (
        "a promocao para silver esta varrendo bronze.event:\n" + plano
    )
    assert "Index" in plano


def test_o_indice_existe_em_todas_as_particoes(db):
    """Asserção estrutural, que nao depende da escolha do planejador.

    Indice criado no pai particionado desce para as particoes. Se uma particao
    nova nascer sem ele -- por DDL manual, por exemplo --, o plano continuaria
    bom nas outras e a regressao passaria despercebida ate a particao encher.
    """
    with db.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE i.indexrelid IS NOT NULL),
                   count(*)
              FROM pg_class parent
              JOIN pg_inherits h        ON h.inhparent = parent.oid
              JOIN pg_class particao    ON particao.oid = h.inhrelid
              LEFT JOIN pg_index i      ON i.indrelid = particao.oid
                   AND i.indexrelid IN (
                     SELECT indexrelid FROM pg_index
                      WHERE indrelid = particao.oid
                        AND pg_get_indexdef(indexrelid) LIKE '%%(_lsn)'
                   )
             WHERE parent.relname = 'event'
               AND parent.relnamespace = 'bronze'::regnamespace
            """
        )
        com_indice, total = cur.fetchone()

    assert total > 0, "bronze.event deveria estar particionada"
    assert com_indice == total, (
        f"{total - com_indice} de {total} particoes de bronze.event sem indice em _lsn"
    )
