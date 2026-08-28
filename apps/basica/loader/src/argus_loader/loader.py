"""Carga inicial: Parquet -> COPY -> bronze corrente.

Requisitos nao negociaveis (§6 do plano), e o porque de cada um:

  COPY por batch, nunca INSERT linha a linha
      68,7 M INSERTs seriam 68,7 M round-trips. COPY manda o lote inteiro por um
      unico fluxo binario e o servidor grava sem replanejar por linha -- e a
      diferenca entre horas e minutos.

  Indices criados DEPOIS da carga de cada tabela
      Manter o btree da chave primaria atualizado durante a carga custa uma
      insercao ordenada por linha. Reconstruir o indice no fim e uma unica
      ordenacao em massa, que o PostgreSQL faz com muito mais eficiencia.

  ANALYZE no fim
      Sem estatisticas, o planner acha que prom_point tem 2.550 linhas (o chute
      padrao) em vez de 41 M, e escolhe nested loop onde deveria escolher hash
      join. A primeira consulta do dashboard viraria uma varredura completa.

  Validacao contra _manifest.json, com falha ALTA
      E a diferenca entre "carregou" e "carregou tudo". Uma carga que perde 3%
      das linhas em silencio e o tipo de erro que passa despercebido por semanas
      e so aparece como "o grafico esta estranho" perto da entrega.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow.parquet as pq
from psycopg import sql

log = logging.getLogger(__name__)

# Linhas por lote de COPY. 50 mil equilibra dois custos: lote pequeno demais
# desperdica round-trip, e lote grande demais segura memoria proporcional a
# largura da tabela (incidents tem 30 colunas de texto).
BATCH_ROWS = 50_000

# Acima disso, vale desmontar a chave primaria antes da carga e reconstrui-la
# depois. Abaixo, a reconstrucao custaria mais que o ganho.
LIMIAR_DROP_PK = 1_000_000


@dataclass
class ResultadoTabela:
    """O que aconteceu com uma tabela."""

    tabela: str
    linhas: int = 0
    esperadas: int | None = None
    segundos: float = 0.0
    pulada: bool = False

    @property
    def confere(self) -> bool:
        """Diz se a contagem bate com o manifesto.

        Returns:
            bool: True se bate, ou se nao ha contagem esperada para comparar.
        """
        return self.esperadas is None or self.linhas == self.esperadas


@dataclass
class Resultado:
    """O resultado da carga inteira."""

    tabelas: list[ResultadoTabela] = field(default_factory=list)

    @property
    def linhas(self) -> int:
        """Total de linhas carregadas.

        Returns:
            int: Soma das linhas de todas as tabelas.
        """
        return sum(t.linhas for t in self.tabelas)

    @property
    def divergentes(self) -> list[ResultadoTabela]:
        """Tabelas cuja contagem nao bate com o manifesto.

        Returns:
            list[ResultadoTabela]: Tabelas com divergencia.
        """
        return [t for t in self.tabelas if not t.confere]


class ManifestoDivergente(RuntimeError):
    """A contagem carregada nao bate com o _manifest.json."""


class Loader:
    """Carrega os Parquet nas tabelas da bronze corrente."""

    def __init__(
        self,
        db,
        parquet_dir: Path,
        *,
        captured_at,
        escrever_change_log: bool = True,
        heartbeat=None,
    ) -> None:
        """Inicializa o loader.

        Args:
            db (argus_common.Database): Pool de conexao.
            parquet_dir (Path): Pasta com os .parquet e o _manifest.json.
            captured_at (datetime): Instante em que a origem gerou o dump. Vai
                para `_captured_at` e para o `captured_at` do change_log --
                todas as linhas do snapshot compartilham o mesmo, o que e
                honesto: e um retrato, nao um fluxo.
            escrever_change_log (bool): Se grava tambem o snapshot no log com
                `op = 'r'`. Ver a nota de custo em `_copy_change_log`.
            heartbeat (argus_common.Heartbeat | None): Marcador de vida.
        """
        self._db = db
        self._dir = Path(parquet_dir)
        self._captured_at = captured_at
        self._change_log = escrever_change_log
        self._heartbeat = heartbeat

        manifesto = json.loads((self._dir / "_manifest.json").read_text(encoding="utf-8"))
        self._esperado: dict[str, int] = manifesto.get("row_counts", {})
        # `investigation_feedback` esta em empty_tables e nao em row_counts:
        # zero linhas e o valor CORRETO, nao um dado faltando.
        for vazia in manifesto.get("empty_tables", []):
            self._esperado.setdefault(vazia, 0)

    # ----------------------------------------------------------------- #
    # Orquestracao
    # ----------------------------------------------------------------- #

    def run(self, tabelas: list[str] | None = None) -> Resultado:
        """Carrega as tabelas pedidas (ou todas as que houver Parquet).

        Retomavel por tabela: uma tabela que ja tem a contagem certa e PULADA.
        E o que permite reiniciar a carga depois de a sessao do laboratorio
        cair, sem refazer os 41 M de prom_point que ja entraram.

        Args:
            tabelas (list[str] | None): Tabelas a carregar. None carrega todas.

        Returns:
            Resultado: O que aconteceu com cada tabela.

        Raises:
            ManifestoDivergente: Se alguma contagem final nao bater.
        """
        alvos = tabelas or sorted(
            p.stem for p in self._dir.glob("*.parquet") if not p.stem.startswith("_")
        )
        resultado = Resultado()

        # Da menor para a maior: se algo estiver errado no formato, o erro
        # aparece em segundos numa tabela de 20 linhas, e nao vinte minutos
        # depois no meio de prom_point.
        alvos.sort(key=lambda t: self._esperado.get(t, 0))

        for tabela in alvos:
            resultado.tabelas.append(self._carregar(tabela))

        self._analyze()
        self._conferir(resultado)
        return resultado

    def _carregar(self, tabela: str) -> ResultadoTabela:
        """Carrega uma tabela.

        Args:
            tabela (str): Nome da tabela.

        Returns:
            ResultadoTabela: O que aconteceu.
        """
        esperadas = self._esperado.get(tabela)
        item = ResultadoTabela(tabela=tabela, esperadas=esperadas)
        inicio = time.monotonic()

        atual = self._contar(tabela)
        if esperadas is not None and atual == esperadas and atual > 0:
            log.info("ja carregada, pulando", extra={"tabela": tabela, "linhas": atual})
            item.linhas, item.pulada = atual, True
            return item

        if atual > 0:
            # Carga anterior interrompida no meio. TRUNCATE e nao "continuar de
            # onde parou": Parquet nao tem cursor, e adivinhar quantas linhas ja
            # entraram por contagem daria errado justamente na tabela
            # particionada, onde a ordem de leitura nao e a de gravacao.
            log.warning(
                "carga parcial encontrada, recomecando a tabela",
                extra={"tabela": tabela, "linhas": atual, "esperadas": esperadas},
            )
            self._truncate(tabela)

        caminho = self._dir / f"{tabela}.parquet"
        if not caminho.exists():
            log.warning("sem Parquet, pulando", extra={"tabela": tabela})
            item.pulada = True
            return item

        # As colunas da chave primaria sao lidas ANTES de a chave ser
        # desmontada -- `_copy` precisa delas para montar o `pk` do change_log,
        # e ler o catalogo com a constraint ja removida devolveria lista vazia.
        # O sintoma seria um `pk: {}` em toda linha do log: o replay continuaria
        # "funcionando", colapsando a tabela inteira numa linha so.
        pk = self._pk_de(tabela)
        grande = (esperadas or 0) >= LIMIAR_DROP_PK
        pk_ddl = self._drop_pk(tabela) if grande else None
        try:
            item.linhas = self._copy(tabela, caminho, pk)
        finally:
            # `finally` e nao o caminho feliz: se o COPY falhar no meio, a tabela
            # NAO pode ficar sem chave primaria. Sem ela o MERGE do worker perde
            # a idempotencia e passa a duplicar em silencio -- um estrago bem
            # pior que o da carga interrompida.
            if pk_ddl:
                log.info("reconstruindo a chave primaria", extra={"tabela": tabela})
                self._restaurar_pk(tabela, pk_ddl)

        item.segundos = time.monotonic() - inicio
        log.info(
            "tabela carregada",
            extra={
                "tabela": tabela,
                "linhas": item.linhas,
                "esperadas": esperadas,
                "segundos": round(item.segundos, 1),
                "linhas_por_s": int(item.linhas / max(item.segundos, 0.001)),
            },
        )
        return item

    # ----------------------------------------------------------------- #
    # COPY
    # ----------------------------------------------------------------- #

    def _copy(self, tabela: str, caminho: Path, pk: list[str]) -> int:
        """Le o Parquet em lotes e despeja por COPY.

        Args:
            tabela (str): Nome da tabela.
            caminho (Path): Arquivo Parquet.
            pk (list[str]): Colunas da chave primaria, lidas antes de ela ser
                desmontada.

        Returns:
            int: Linhas gravadas.
        """
        arquivo = pq.ParquetFile(caminho)
        colunas = list(arquivo.schema_arrow.names)
        # `_extra` fica de fora: no snapshot inicial nao existe coluna
        # desconhecida por definicao -- o schema veio do proprio dump. O DEFAULT
        # '{}' da coluna resolve, e nao passa-la economiza 68,7 M de literais.
        destino = [*colunas, "_lsn", "_op", "_captured_at"]

        instrucao = sql.SQL("COPY bronze.{} ({}) FROM STDIN").format(
            sql.Identifier(tabela),
            sql.SQL(", ").join(sql.Identifier(c) for c in destino),
        )

        gravadas = 0
        with self._db.connection() as conn:
            # Uma faixa de lsn reservada de uma vez para a tabela inteira. Pedir
            # nextval por linha seriam 68,7 M round-trips ao gerador de
            # sequencia -- o mesmo erro que o COPY existe para evitar.
            lsn = self._reservar_lsn(conn, arquivo.metadata.num_rows)

            with conn.cursor().copy(instrucao) as copy:
                for lote in arquivo.iter_batches(batch_size=BATCH_ROWS):
                    # strict: as colunas de um mesmo RecordBatch tem sempre o
                    # mesmo comprimento. Se um dia nao tiverem, e melhor
                    # estourar do que gravar linha truncada em silencio.
                    colunas_do_lote = (c.to_pylist() for c in lote.columns)
                    for linha in zip(*colunas_do_lote, strict=True):
                        copy.write_row((*linha, lsn, "r", self._captured_at))
                        lsn += 1
                    gravadas += lote.num_rows
                    if self._heartbeat:
                        # A carga de prom_point passa de dez minutos num unico
                        # COPY. Sem bater aqui, o healthcheck mataria a task no
                        # meio da tabela maior -- exatamente a que nao se quer
                        # refazer.
                        self._heartbeat.touch()
                    log.debug(
                        "lote", extra={"tabela": tabela, "acumulado": gravadas}
                    )

            if self._change_log:
                self._copy_change_log(conn, tabela, arquivo, colunas, pk)

        return gravadas

    def _copy_change_log(
        self, conn, tabela: str, arquivo, colunas: list[str], pk: list[str]
    ) -> None:
        """Grava o snapshot tambem no log, com `op = 'r'`.

        Custa caro -- e aproximadamente dobrar a carga em tempo e em espaco -- e
        vale mesmo assim: e o log que sustenta a propriedade de rebuild da
        decisao 4. Sem o snapshot ali, `TRUNCATE` em silver e gold seguido de
        replay reconstruiria apenas o que chegou por CDC depois da carga, e a
        propriedade valeria so no papel.

        Quem tiver aperto de disco pode desligar com `--sem-change-log`, ciente
        de que perde exatamente isso.

        Args:
            conn: Conexao aberta, dentro da transacao da tabela.
            tabela (str): Nome da tabela.
            arquivo: Arquivo Parquet ja aberto.
            colunas (list[str]): Colunas da tabela na origem.
            pk (list[str]): Colunas da chave primaria.

        Raises:
            RuntimeError: Se a chave primaria vier vazia -- sem ela o `pk` do
                log fica `{}` em toda linha, e o replay colapsaria a tabela
                inteira num registro so.
        """
        if not pk:
            raise RuntimeError(
                f"bronze.{tabela} sem chave primaria ao montar o change_log: "
                "o replay ficaria corrompido em silencio"
            )
        instrucao = sql.SQL(
            "COPY bronze.change_log (source_table, op, pk, after, captured_at) FROM STDIN"
        )
        with conn.cursor().copy(instrucao) as copy:
            for lote in arquivo.iter_batches(batch_size=BATCH_ROWS):
                valores = [c.to_pylist() for c in lote.columns]
                for linha in zip(*valores, strict=True):
                    registro = dict(zip(colunas, linha, strict=True))
                    copy.write_row(
                        (
                            tabela,
                            "r",
                            json.dumps({k: registro[k] for k in pk}, default=str),
                            json.dumps(registro, default=str),
                            self._captured_at,
                        )
                    )
                if self._heartbeat:
                    self._heartbeat.touch()

    # ----------------------------------------------------------------- #
    # Catalogo
    # ----------------------------------------------------------------- #

    def _reservar_lsn(self, conn, quantas: int) -> int:
        """Reserva uma faixa contigua da sequencia do lsn.

        Args:
            conn: Conexao aberta.
            quantas (int): Quantos valores reservar.

        Returns:
            int: Primeiro lsn da faixa.
        """
        with conn.cursor() as cur:
            cur.execute(
                "SELECT setval('bronze.change_log_lsn_seq', "
                "  nextval('bronze.change_log_lsn_seq') + %s) AS fim",
                (max(quantas, 1),),
            )
            fim = cur.fetchone()[0]
        return fim - quantas

    def _pk_de(self, tabela: str) -> list[str]:
        """Le as colunas da chave primaria do catalogo.

        Args:
            tabela (str): Nome da tabela.

        Returns:
            list[str]: Colunas da PK, exceto as de controle.
        """
        linhas = self._db.fetch_all(
            "SELECT unnest(bronze.pk_de(%s)) AS coluna", (tabela,)
        )
        return [
            linha["coluna"] for linha in linhas if not linha["coluna"].startswith("_")
        ]

    def _drop_pk(self, tabela: str) -> str | None:
        """Remove a chave primaria e devolve o DDL para reconstrui-la.

        Args:
            tabela (str): Nome da tabela.

        Returns:
            str | None: Instrucao de recriacao, ou None se nao havia PK.
        """
        linha = self._db.fetch_one(
            """
            SELECT c.conname AS nome, pg_get_constraintdef(c.oid) AS definicao
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
             WHERE n.nspname = 'bronze' AND t.relname = %s AND c.contype = 'p'
            """,
            (tabela,),
        )
        if not linha:
            return None

        log.info("removendo a chave primaria antes da carga", extra={"tabela": tabela})
        with self._db.connection() as conn:
            conn.execute(
                sql.SQL("ALTER TABLE bronze.{} DROP CONSTRAINT {}").format(
                    sql.Identifier(tabela), sql.Identifier(linha["nome"])
                )
            )
        return sql.SQL("ALTER TABLE bronze.{} ADD CONSTRAINT {} {}").format(
            sql.Identifier(tabela),
            sql.Identifier(linha["nome"]),
            sql.SQL(linha["definicao"]),
        ).as_string(None)

    def _restaurar_pk(self, tabela: str, ddl: str) -> None:
        """Recria a chave primaria e CONFIRMA que ela ficou de pe.

        A confirmacao existe porque a falha aqui e silenciosa por natureza: uma
        tabela sem chave primaria aceita INSERT normalmente, e o problema so
        aparece muito depois, como linha duplicada que ninguem sabe de onde
        veio. Melhor abortar a carga.

        Args:
            tabela (str): Nome da tabela.
            ddl (str): Instrucao de recriacao devolvida por `_drop_pk`.

        Raises:
            RuntimeError: Se a chave nao existir depois da recriacao.
        """
        with self._db.connection() as conn:
            conn.execute(ddl)

        if not self._tem_pk(tabela):
            raise RuntimeError(
                f"bronze.{tabela} ficou SEM chave primaria depois da carga. "
                "O MERGE perderia a idempotencia; recarregue a tabela."
            )

    def _tem_pk(self, tabela: str) -> bool:
        """Diz se a tabela tem chave primaria.

        Args:
            tabela (str): Nome da tabela.

        Returns:
            bool: True se existe uma constraint de chave primaria.
        """
        linha = self._db.fetch_one(
            """
            SELECT count(*) AS n
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
              JOIN pg_namespace n ON n.oid = t.relnamespace
             WHERE n.nspname = 'bronze' AND t.relname = %s AND c.contype = 'p'
            """,
            (tabela,),
        )
        return bool(linha and linha["n"])

    def _contar(self, tabela: str) -> int:
        """Conta as linhas de uma tabela da bronze.

        Args:
            tabela (str): Nome da tabela.

        Returns:
            int: Contagem exata.
        """
        linha = self._db.fetch_one(
            sql.SQL("SELECT count(*) AS n FROM bronze.{}")
            .format(sql.Identifier(tabela))
            .as_string(None)
        )
        return int(linha["n"]) if linha else 0

    def _truncate(self, tabela: str) -> None:
        """Esvazia uma tabela da bronze.

        Args:
            tabela (str): Nome da tabela.
        """
        with self._db.connection() as conn:
            conn.execute(
                sql.SQL("TRUNCATE bronze.{}").format(sql.Identifier(tabela))
            )

    def _analyze(self) -> None:
        """Atualiza as estatisticas do planner depois da carga."""
        log.info("rodando ANALYZE nos schemas carregados")
        # autocommit ligado: ANALYZE de um banco inteiro dentro de uma transacao
        # longa seguraria um snapshot e atrapalharia o autovacuum justamente
        # quando ele mais precisa trabalhar.
        with self._db.connection() as conn:
            conn.set_autocommit(True)
            try:
                conn.execute("ANALYZE")
            finally:
                conn.set_autocommit(False)

    # ----------------------------------------------------------------- #
    # Validacao
    # ----------------------------------------------------------------- #

    def _conferir(self, resultado: Resultado) -> None:
        """Compara as contagens finais com o manifesto e falha alto se divergir.

        Args:
            resultado (Resultado): Resultado da carga.

        Raises:
            ManifestoDivergente: Se alguma contagem nao bater.
        """
        for item in resultado.tabelas:
            # Reconta no banco em vez de confiar no que o COPY reportou: o que
            # importa e o que ESTA la, nao o que se acredita ter mandado.
            item.linhas = self._contar(item.tabela)

        divergentes = resultado.divergentes
        if divergentes:
            detalhe = ", ".join(
                f"{t.tabela}: {t.linhas} != {t.esperadas}" for t in divergentes
            )
            raise ManifestoDivergente(
                f"{len(divergentes)} tabela(s) divergem do _manifest.json: {detalhe}"
            )
        log.info(
            "carga conferida contra o manifesto",
            extra={"tabelas": len(resultado.tabelas), "linhas": resultado.linhas},
        )
