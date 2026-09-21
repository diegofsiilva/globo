"""Escrita no PostgreSQL: change events no log e eventos de sessao na bronze.

Substitui o repositorio de DynamoDB da v2. A mudanca nao e so de destino: a
estrategia de idempotencia mudou de lugar.

  v2  chave derivada do hash do conteudo -> reentrega grava o mesmo item por
      cima, e o efeito e exactly-once.
  v3  `lsn` monotonico + a regra "so sobrescreve se o lsn for maior", aplicada
      por `bronze.merge_do_log` dentro do banco. A reentrega e absorvida do
      mesmo jeito, mas agora a regra vale tambem para o REPLAY e para o loader,
      que nao passam por este codigo.

A regra mora no SQL (010_merge_e_etl.sql) de proposito: e a unica forma de os
tres caminhos de escrita nao divergirem.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

log = logging.getLogger(__name__)

# Teto de tamanho de um change event. Nao ha limite de linha no PostgreSQL como
# havia no DynamoDB (400 KB), mas um payload absurdo ainda e sinal de defeito na
# origem, e aceita-lo faria o TOAST engolir a tabela em silencio.
MAX_CHANGE_BYTES = 4_000_000


class ChangeTooLarge(ValueError):
    """Change event grande demais -- retry nunca vai resolver."""


def check_size(change: dict[str, Any]) -> None:
    """Levanta ChangeTooLarge se o change event for absurdo.

    Chamado pelo consumer ANTES de montar o lote: um payload gigante nunca vai
    passar por mais que se tente, entao precisa ser desviado para a DLQ na
    entrada. Se entrasse no lote, derrubaria os outros junto e o redrive
    repetiria a falha para sempre.

    Args:
        change (dict[str, Any]): Change event ja validado.

    Raises:
        ChangeTooLarge: Se o tamanho serializado exceder o limite.
    """
    tamanho = len(json.dumps(change, default=str).encode("utf-8"))
    if tamanho > MAX_CHANGE_BYTES:
        raise ChangeTooLarge(
            f"change event de ~{tamanho} bytes excede o limite de {MAX_CHANGE_BYTES}"
        )


class ChangeRepository:
    """Anexa change events ao log e dispara o MERGE na bronze corrente."""

    def __init__(self, db) -> None:
        """Inicializa o repositorio.

        Args:
            db (argus_common.Database): Pool de conexao com o banco.
        """
        self._db = db

    def append_and_merge(self, changes: list[dict[str, Any]]) -> tuple[int, int]:
        """Grava o lote no log e aplica o MERGE, numa transacao so.

        Log e MERGE na MESMA transacao de proposito. Se o commit acontecesse
        entre os dois, uma queda no meio deixaria o log a frente da bronze
        corrente -- estado que so seria percebido quando alguem reparasse que
        uma tabela parou de atualizar. Como estao juntos, ou os dois acontecem
        ou nenhum, e o SQS reentrega o lote inteiro.

        Args:
            changes (list[dict[str, Any]]): Change events validados.

        Returns:
            tuple[int, int]: Quantos entraram no log e quantas linhas o MERGE
                tocou na bronze corrente.
        """
        if not changes:
            return 0, 0

        with self._db.connection() as conn, conn.cursor() as cur:
            # RETURNING lsn e o que fecha a faixa a aplicar. Sem ele, o MERGE
            # teria que varrer o log inteiro a cada lote -- que fica mais caro a
            # cada mensagem processada, exatamente o tipo de degradacao que so
            # aparece depois de horas rodando.
            cur.executemany(
                """
                INSERT INTO bronze.change_log
                  (source_table, op, pk, before, after, captured_at, run_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING lsn
                """,
                [
                    (
                        c["source_table"],
                        c["op"],
                        Jsonb(c["pk"]),
                        Jsonb(c["before"]) if c.get("before") is not None else None,
                        Jsonb(c["after"]) if c.get("after") is not None else None,
                        c["captured_at"],
                        c.get("run_id"),
                    )
                    for c in changes
                ],
                returning=True,
            )

            lsns: list[int] = []
            while True:
                linha = cur.fetchone()
                if linha is not None:
                    lsns.append(linha[0])
                if not cur.nextset():
                    break

            if not lsns:
                return 0, 0

            tocadas = 0
            for tabela in sorted({c["source_table"] for c in changes}):
                cur.execute(
                    "SELECT bronze.merge_do_log(%s, %s, %s)",
                    (tabela, min(lsns), max(lsns)),
                )
                resultado = cur.fetchone()
                tocadas += resultado[0] if resultado else 0

            return len(lsns), tocadas

    def lag_sim_seconds(self) -> float | None:
        """Mede quanto tempo VIRTUAL o pipeline esta atras da origem.

        E a metrica que so faz sentido neste sistema. Compara `sim.now()` com o
        `captured_at` mais recente ja aplicado: se o simulador esta em
        20:07 virtual e a ultima mudanca aplicada foi observada as 19:52, o
        pipeline esta 15 minutos virtuais atrasado.

        Medir em tempo de parede nao serviria -- com speed = 60, o mesmo atraso
        de rede vira 1 segundo ou 1 hora de defasagem conforme a velocidade.

        Returns:
            float | None: Segundos de tempo virtual, ou None se o log estiver
                vazio (nao ha atraso a medir num pipeline que nunca recebeu
                nada).
        """
        # Pelo `lsn` e nao por `max(captured_at)`.
        #
        # O `max()` global nao tem como usar indice: `change_log` e particionada
        # por RANGE em `lsn`, e um maximo sobre `captured_at` teria de olhar todas
        # as particoes. Medido no RDS com 68,7 M linhas: 15 s, mesmo com indice em
        # `(source_table, captured_at)` -- o PostgreSQL 16 nao faz skip scan.
        #
        # `lsn` e a chave de particionamento E a ordem de chegada, entao a linha
        # mais nova esta sempre no fim da ultima particao: uma sondagem de indice,
        # 0,25 s. E responde a MESMA pergunta -- "quao velho e o mais novo change
        # event que ingerimos" -- porque o log e append-only na ordem em que o
        # worker recebe.
        linha = self._medir(
            """
            SELECT extract(epoch FROM sim.now() - captured_at) AS lag
              FROM bronze.change_log
             ORDER BY lsn DESC
             LIMIT 1
            """
        )
        return float(linha["lag"]) if linha and linha["lag"] is not None else None

    def sources_silent(self, limite: dt.timedelta = dt.timedelta(hours=2)) -> int:
        """Conta quantas fontes pararam de mandar dado.

        Uma fonte que simplesmente para nao derruba nada: as outras continuam, o
        dashboard continua desenhando, e o buraco so aparece quando alguem for
        investigar um incidente e nao achar o dado. Por isso e metrica propria.

        Args:
            limite (timedelta): Silencio em tempo VIRTUAL a partir do qual a
                fonte conta como calada.

        Returns:
            int: Quantidade de fontes silenciosas.
        """
        # A janela de `lsn` e o que torna isto viavel: sem ela, o `GROUP BY`
        # varre as 68,7 M linhas (13 s medidos) porque nao existe skip scan. Com
        # ela, a poda de particao deixa a consulta em 0,17 s.
        #
        # LIMITACAO CONHECIDA: uma fonte calada ha mais tempo do que a janela
        # cobre some da contagem em vez de aparecer nela. Na pratica a janela
        # cobre bem mais que o `limite` de silencio (sao ~10 ticks do simulador),
        # mas com volume de ingestao muito maior essa folga encolhe. O jeito certo
        # de resolver e uma tabela de fontes esperadas -- que so faz sentido
        # quando o simulador cobrir mais que as quatro tabelas de hoje.
        linha = self._medir(
            """
            WITH teto AS (SELECT max(lsn) AS m FROM bronze.change_log)
            SELECT count(*) AS caladas FROM (
              SELECT source_table, max(captured_at) AS ultimo
                FROM bronze.change_log, teto
               WHERE lsn > teto.m - %s
               GROUP BY source_table
              HAVING max(captured_at) < sim.now() - %s
            ) q
            """,
            (self.JANELA_DE_LSN, limite),
        )
        return int(linha["caladas"]) if linha else 0

    # Quantos lsn para tras a contagem de fontes caladas enxerga.
    JANELA_DE_LSN = 50_000

    # Teto de tempo para as consultas de METRICA, e so para elas.
    #
    # As duas acima agregam sobre `bronze.change_log`, que e append-only: ela so
    # cresce. Com o indice `change_log_fonte_e_captura` (migration 012) as duas
    # respondem em milissegundos, mas o indice pode faltar num banco recem-criado
    # ou o plano pode degradar -- e ai a consulta passa a levar minutos.
    #
    # Isso ja aconteceu: sem o indice, `lag_sim_seconds` passava de 180 s sobre
    # 68,7 M linhas. Como o worker so toca o heartbeat entre ciclos, o arquivo
    # ficava velho, o healthcheck do ECS reprovava e a task era MORTA. Uma
    # metrica derrubando o servico que ela observa.
    #
    # `_emit_lag` ja captura `psycopg.Error` dizendo "metrica nao pode derrubar
    # ingestao". O teto e o que torna essa promessa verdadeira: sem ele a metrica
    # nao falhava, so demorava -- e demorar era pior do que falhar.
    TETO_DA_METRICA_MS = 5_000

    def _medir(self, sql: str, params: tuple = ()) -> dict | None:
        """Roda uma consulta de metrica com teto de tempo.

        Args:
            sql (str): Consulta.
            params (tuple): Parametros de bind.

        Returns:
            dict | None: Primeira linha, ou None.

        Raises:
            psycopg.errors.QueryCanceled: Se estourar o teto. Quem chama trata
                como metrica indisponivel, nao como falha de ingestao.
        """
        with self._db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            # SET LOCAL: vale so nesta transacao, entao nao vaza para a proxima
            # conexao que o pool devolver.
            cur.execute(f"SET LOCAL statement_timeout = {self.TETO_DA_METRICA_MS}")
            cur.execute(sql, params)
            return cur.fetchone()


class EventRepository:
    """Grava eventos de sessao em bronze.event."""

    # As colunas do envelope tipado, na ordem do INSERT. Explicitas e nao
    # derivadas do dict: o modelo Pydantic aceita campo extra (`extra="allow"`)
    # de proposito, e derivar a lista do payload faria um campo novo do app
    # virar coluna inexistente e quebrar a ingestao -- exatamente o contrario do
    # que o RF03 pede.
    COLUNAS = (
        "event_id",
        "ts",
        "event_name",
        "session_id",
        "device_id",
        "user_id",
        "app_bucket",
        "app_env",
        "app_target",
        "app_version",
        "device_manufacturer",
        "device_model",
        "device_model_year",
        "device_os",
        "device_os_version",
        "route_path",
        "route_params",
        "duration",
        "payload",
        "_lsn",
        "_captured_at",
    )

    def __init__(self, db) -> None:
        """Inicializa o repositorio.

        Args:
            db (argus_common.Database): Pool de conexao com o banco.
        """
        self._db = db

    def put_many(self, linhas: list[dict[str, Any]]) -> int:
        """Grava o lote, ignorando o que ja estiver la.

        `DO NOTHING` e nao `DO UPDATE`: a chave e (ts, event_id), e event_id
        deriva do conteudo do evento (ver keys.build_event_id). Chave igual
        significa evento igual, entao reescrever gastaria I/O para produzir a
        mesma linha. E o que da o efeito de exactly-once sobre a entrega
        at-least-once do SQS.

        Args:
            linhas (list[dict[str, Any]]): Linhas ja montadas por keys.build_row.

        Returns:
            int: Quantas linhas foram efetivamente inseridas (as duplicatas
                nao contam).
        """
        if not linhas:
            return 0

        instrucao = sql.SQL(
            "INSERT INTO bronze.event ({}) VALUES ({})"
            " ON CONFLICT (ts, event_id) DO NOTHING"
        ).format(
            sql.SQL(", ").join(sql.Identifier(c) for c in self.COLUNAS),
            sql.SQL(", ").join(sql.Placeholder() * len(self.COLUNAS)),
        )

        with self._db.connection() as conn, conn.cursor() as cur:
            # Um unico lsn para o lote inteiro: aqui ele marca "chegou nesta
            # remessa", nao ordena linha a linha. bronze.event nao passa por
            # MERGE -- o evento de sessao e imutavel, nunca sofre update.
            cur.execute("SELECT nextval('bronze.change_log_lsn_seq') AS lsn")
            lsn = cur.fetchone()[0]

            cur.executemany(
                instrucao,
                [
                    tuple(
                        Jsonb(linha[c])
                        if c in ("payload", "route_params") and linha.get(c) is not None
                        else (lsn if c == "_lsn" else linha.get(c))
                        for c in self.COLUNAS
                    )
                    for linha in linhas
                ],
            )
            return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
