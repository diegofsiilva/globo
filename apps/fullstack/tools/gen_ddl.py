"""Gera o DDL da bronze corrente (migration 004) a partir do dump do Argus.

Sao 33 tabelas com 250+ colunas somadas, herdadas de seis fontes diferentes.
Escrever isso a mao seria uma sessao inteira de digitacao e um erro de tipo
silencioso esperando para acontecer -- o gerador le a mesma verdade que o ETL
usou (`data/parquet/_schema.json` e `_keys.json`, ambos extraidos do DDL do
proprio dump) e nao tem como divergir dela.

Escopo: **so a migration 004**. As migrations 003 (`bronze.change_log`) e 005
(`bronze.event`) tem schema proprio e fixo, que nao deriva do dump -- elas sao
escritas a mao em `db/migrations/`, e gerar um arquivo constante a partir de um
gerador que ignora a entrada so esconderia de onde o schema veio.

Uso:
    python apps/fullstack/tools/gen_ddl.py \
        [--parquet data/parquet] \
        [--out apps/fullstack/db/migrations/004_bronze_corrente_argus.sql]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Tipos
# --------------------------------------------------------------------------- #

# MySQL -> PostgreSQL. E o mesmo exercicio que o ARROW_TYPE de etl_dump.py faz
# para o Arrow, com duas diferencas que importam:
#
#   tinyint  -> smallint  : o PostgreSQL nao tem inteiro de 1 byte. `blocked` e
#                           `enabled` viram smallint em vez de boolean porque o
#                           dump guarda 0/1 e converter aqui seria interpretar
#                           dado da origem numa camada que so deve copia-lo.
#   *text*   -> text      : o PostgreSQL nao cobra pelo tamanho declarado, entao
#                           varchar(n) so acrescentaria uma restricao que a
#                           origem pode afrouxar sem avisar.
PG_TYPE = {
    "bigint": "bigint",
    "int": "integer",
    "tinyint": "smallint",
    "smallint": "smallint",
    "double": "double precision",
    "float": "real",
    "decimal": "double precision",
    "varchar": "text",
    "char": "text",
    "text": "text",
    "mediumtext": "text",
    "longtext": "text",
    "tinytext": "text",
    "enum": "text",
    # No dump estas tres chegam como string ISO-8601, nao como tipo temporal do
    # MySQL. A conversao para timestamptz e trabalho da silver (§4.5 do plano),
    # nao da bronze -- aqui a copia e fiel.
    "date": "text",
    "datetime": "text",
    "timestamp": "text",
}

# --------------------------------------------------------------------------- #
# Particionamento
# --------------------------------------------------------------------------- #

# Tabela -> coluna de tempo usada como chave de particao.
#
# Nao existe um `ts` universal: cada tabela herdou o nome da sua fonte. Este
# mapa e a unica lista literal do gerador, e existe porque "qual coluna e o
# tempo" e uma decisao de modelagem -- inferir por nome acertaria em `ts` e
# erraria em `timestamp` (service_overview) ou `epoch_ms` (prom_point).
PARTITION_KEY = {
    "prom_point": "epoch_ms",
    "signal_point": "ts",
    "signal_bucket": "bts",
    "ca_point": "ts_ms",
    "device_hourly": "hour_ts",
    "operation_metrics": "start_ts",
}

# Folga em dias antes e depois da janela observada no Parquet. Cobre o replay do
# simulador andando alem do fim do dump sem cair na particao DEFAULT.
PADDING_DAYS = 10

MS_PER_DAY = 86_400_000

# --------------------------------------------------------------------------- #
# Comentarios de coluna
# --------------------------------------------------------------------------- #

# Armadilhas que a EDA encontrou e que nao aparecem no schema. Ficam como
# COMMENT ON COLUMN para que ninguem redescubra na analise.
COLUMN_NOTES = {
    ("rpaas_bucket", "p50_ms"): "100% nula nas 52.560 linhas do dump",
    ("rpaas_bucket", "p90_ms"): "100% nula nas 52.560 linhas do dump",
    ("rpaas_bucket", "p95_ms"): "100% nula nas 52.560 linhas do dump",
    ("rpaas_bucket", "p99_ms"): "100% nula nas 52.560 linhas do dump",
    ("rpaas_bucket", "latency_samples"): (
        "100% nula nas 52.560 linhas do dump: sem ela nao da para separar "
        "'borda lenta' de 'borda falhando'"
    ),
    ("signal_point", "tags"): (
        "JSON na maioria das fontes, mas a string literal 'live' em "
        "youbora_player_live e NULL em varias. A silver converte tolerando "
        "falha de parse"
    ),
    ("live_event", "slug"): (
        "chega sempre como 'globo' (a familia) enquanto a QoE vem por praca "
        "(globo-rj, globo-sp): o casamento e LIKE 'globo%' como agregado "
        "nacional, nunca praca especifica"
    ),
    ("live_event", "tid"): (
        "tid 994 e 995 sao feeds SIMULTANEOS com jogos diferentes, nao o mesmo "
        "canal em horarios diferentes. Agrupar por start_ts funde dois jogos"
    ),
    ("incident_label", "provenance"): (
        "7 dos 20 rotulos sao 'detector-derived', criados olhando a saida do "
        "proprio Argus. Avaliar detector contra eles mede concordancia com o "
        "baseline, nao acuracia"
    ),
    ("signal_meta", "last_run_at"): "texto ISO-8601, nao epoch_ms",
    ("cdn_entity_tier", "updated_at"): "texto ISO-8601, nao epoch_ms",
    ("investigation_feedback", "investigated_at"): "texto ISO-8601, nao epoch_ms",
    ("geo_hourly", "isp"): (
        "exclusivo com state_province na pratica: a linha traz UF ou ISP, nunca os dois"
    ),
}

TABLE_NOTES = {
    "prom_point": "tabela-fato do Prometheus: 41,2 M linhas, cadencia de 1 min",
    "signal_point": "camada canonica ponto a ponto, ja normalizada pela origem",
    "signal_bucket": "camada canonica em bucket de 15 min",
    "investigation_feedback": "vazia no dump (0 linhas), schema preservado",
    "live_event": "calendario de transmissoes ao vivo; ver gold.live_event_window",
    "incident_label": "ground truth rotulado a mao; ver a coluna provenance",
    "dashboard_artifact": "saida do Argus que ja existe em producao na Globo",
}


# --------------------------------------------------------------------------- #
# Leitura da janela de tempo
# --------------------------------------------------------------------------- #


def time_bounds(parquet_dir: Path, table: str, column: str) -> tuple[int, int]:
    """Le o minimo e o maximo da coluna de tempo pelas estatisticas do Parquet.

    Usa as estatisticas de row group, que o pyarrow le do rodape do arquivo. Ler
    a coluna inteira de `prom_point` custaria varredura de 41 M valores para
    obter dois numeros que ja estao gravados no metadado.

    Args:
        parquet_dir (Path): Pasta com os arquivos Parquet.
        table (str): Nome da tabela.
        column (str): Coluna de tempo (epoch em milissegundos).

    Returns:
        tuple[int, int]: Menor e maior valor observados.

    Raises:
        RuntimeError: Se o arquivo nao tiver estatisticas para a coluna.
    """
    import pyarrow.parquet as pq

    meta = pq.ParquetFile(parquet_dir / f"{table}.parquet").metadata
    index = meta.schema.names.index(column)

    lo: int | None = None
    hi: int | None = None
    for group in range(meta.num_row_groups):
        stats = meta.row_group(group).column(index).statistics
        if stats is None or not stats.has_min_max:
            continue
        lo = stats.min if lo is None else min(lo, stats.min)
        hi = stats.max if hi is None else max(hi, stats.max)

    if lo is None or hi is None:
        raise RuntimeError(
            f"{table}.{column} sem estatisticas no Parquet: nao da para "
            "dimensionar as particoes"
        )
    return int(lo), int(hi)


def daily_ranges(lo_ms: int, hi_ms: int) -> list[tuple[int, int, str]]:
    """Quebra a janela em faixas diarias alinhadas a meia-noite UTC.

    Args:
        lo_ms (int): Primeiro instante observado, em epoch de milissegundos.
        hi_ms (int): Ultimo instante observado, em epoch de milissegundos.

    Returns:
        list[tuple[int, int, str]]: Faixas `(inicio, fim, sufixo)`, com o fim
            exclusivo, como o `FOR VALUES FROM ... TO ...` do PostgreSQL espera.
    """
    start = (lo_ms // MS_PER_DAY - PADDING_DAYS) * MS_PER_DAY
    end = (hi_ms // MS_PER_DAY + PADDING_DAYS + 1) * MS_PER_DAY

    ranges = []
    cursor = start
    while cursor < end:
        day = dt.datetime.fromtimestamp(cursor / 1000, dt.UTC)
        ranges.append((cursor, cursor + MS_PER_DAY, day.strftime("%Y%m%d")))
        cursor += MS_PER_DAY
    return ranges


# --------------------------------------------------------------------------- #
# Geracao
# --------------------------------------------------------------------------- #


def quote(text: str) -> str:
    """Escapa um literal de texto para o SQL.

    Args:
        text (str): Texto a escapar.

    Returns:
        str: Literal pronto para interpolar, ja com as aspas.
    """
    return "'" + text.replace("'", "''") + "'"


def render_table(
    table: str,
    columns: dict[str, str],
    pk: list[str],
    parquet_dir: Path,
) -> str:
    """Monta o CREATE TABLE de uma tabela da bronze corrente.

    Args:
        table (str): Nome da tabela.
        columns (dict[str, str]): Mapa `{coluna: tipo_mysql}`.
        pk (list[str]): Colunas da chave primaria, na ordem da origem.
        parquet_dir (Path): Pasta com os Parquet, usada para dimensionar as
            particoes.

    Returns:
        str: Bloco SQL da tabela, das particoes e dos comentarios.

    Raises:
        RuntimeError: Se a chave primaria estiver vazia -- sem ela o MERGE do
            worker nao tem como ser idempotente.
    """
    if not pk:
        raise RuntimeError(f"{table} sem chave primaria no dump")

    part_key = PARTITION_KEY.get(table)

    # Numa tabela particionada a chave de particao TEM que fazer parte de toda
    # restricao de unicidade; alem disso, deixa-la na frente da PK e o que
    # permite ao planner podar particao e ainda usar o indice.
    ordered_pk = pk if part_key is None else [part_key] + [c for c in pk if c != part_key]

    width = max(max(len(c) for c in columns), len("_captured_at")) + 2
    lines = [f"  {name.ljust(width)}{PG_TYPE[kind]}," for name, kind in columns.items()]
    lines += [
        f"  {'_extra'.ljust(width)}jsonb       NOT NULL DEFAULT '{{}}',",
        f"  {'_lsn'.ljust(width)}bigint      NOT NULL,",
        f"  {'_op'.ljust(width)}char(1)     NOT NULL,",
        f"  {'_captured_at'.ljust(width)}timestamptz NOT NULL,",
        f"  PRIMARY KEY ({', '.join(ordered_pk)})",
    ]

    body = "\n".join(lines)
    suffix = f"\n) PARTITION BY RANGE ({part_key});" if part_key else "\n);"
    out = [f"CREATE TABLE bronze.{table} (\n{body}{suffix}"]

    if part_key:
        lo, hi = time_bounds(parquet_dir, table, part_key)
        ranges = daily_ranges(lo, hi)
        out.append(
            f"-- {len(ranges)} particoes diarias cobrindo "
            f"{ranges[0][2]}..{ranges[-1][2]}, mais a DEFAULT."
        )
        for start, end, label in ranges:
            out.append(
                f"CREATE TABLE bronze.{table}_p{label} PARTITION OF bronze.{table} "
                f"FOR VALUES FROM ({start}) TO ({end});"
            )
        # Sem a DEFAULT, uma linha fora da janela faz o INSERT falhar. Numa
        # bronze cuja regra e nunca recusar dado da origem, isso e o pior
        # comportamento possivel.
        out.append(
            f"CREATE TABLE bronze.{table}_default PARTITION OF bronze.{table} DEFAULT;"
        )

    note = TABLE_NOTES.get(table)
    if note:
        out.append(f"COMMENT ON TABLE bronze.{table} IS {quote(note)};")
    out.append(
        f"COMMENT ON COLUMN bronze.{table}._extra IS "
        + quote(
            "coluna nova da origem cai aqui sem DDL; vira coluna real quando estabilizar"
        )
        + ";"
    )
    for name in columns:
        note = COLUMN_NOTES.get((table, name))
        if note:
            out.append(f"COMMENT ON COLUMN bronze.{table}.{name} IS {quote(note)};")

    return "\n".join(out)


def render(schema: dict, keys: dict, parquet_dir: Path) -> str:
    """Gera o arquivo completo da migration 004.

    Args:
        schema (dict): Mapa `{tabela: {coluna: tipo_mysql}}`.
        keys (dict): Mapa `{tabela: [colunas da PK]}`.
        parquet_dir (Path): Pasta com os Parquet.

    Returns:
        str: Conteudo do arquivo SQL.
    """
    partitioned = "\n--   ".join(
        f"{t:<20s} por {PARTITION_KEY[t]}" for t in sorted(PARTITION_KEY)
    )
    header = f"""\
-- 004_bronze_corrente_argus.sql
--
-- ARQUIVO GERADO por tools/gen_ddl.py -- nao edite a mao.
-- Fonte: data/parquet/_schema.json e _keys.json, ambos extraidos do DDL de
-- argus_dump.sql por tools/etl_dump.py. Para regerar:
--
--     make gen-ddl
--
-- As {len(schema)} tabelas do Argus, copiadas com fidelidade da origem. Cada
-- uma ganha quatro colunas de controle:
--
--   _extra jsonb    escape de schema: coluna nova da Globo cai aqui, sem DDL
--   _lsn bigint     posicao no bronze.change_log que produziu esta versao
--   _op char(1)     i | u | d | r (r = linha vinda do snapshot inicial)
--   _captured_at    quando a origem observou a mudanca
--
-- A chave primaria e a identidade natural declarada no dump: e ela que torna o
-- MERGE do worker idempotente sem coluna de controle extra.
--
-- Seis tabelas sao particionadas por RANGE na coluna de tempo, em faixas
-- diarias mais uma DEFAULT. Repare que a coluna de tempo tem nome diferente em
-- cada uma: nao existe um `ts` universal neste dataset, cada tabela herdou o
-- nome da sua fonte.
--
--   {partitioned}
"""

    blocks = [header]
    for table, colunas in schema.items():
        blocks.append(render_table(table, colunas, keys.get(table, []), parquet_dir))
    return "\n\n".join(blocks) + "\n"


def main() -> int:
    """Ponto de entrada da linha de comando.

    Returns:
        int: 0 em sucesso, 1 em falha.
    """
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path, default=root / "data" / "parquet")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "db"
        / "migrations"
        / "004_bronze_corrente_argus.sql",
    )
    args = parser.parse_args()

    schema_path = args.parquet / "_schema.json"
    keys_path = args.parquet / "_keys.json"
    for path in (schema_path, keys_path):
        if not path.exists():
            print(
                f"erro: {path} nao existe. Rode tools/etl_dump.py sobre o dump primeiro.",
                file=sys.stderr,
            )
            return 1

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    keys = json.loads(keys_path.read_text(encoding="utf-8"))

    unknown = {
        kind for cols in schema.values() for kind in cols.values() if kind not in PG_TYPE
    }
    if unknown:
        print(
            f"erro: tipo MySQL sem equivalente mapeado: {sorted(unknown)}. "
            "Acrescente em PG_TYPE em vez de deixar virar text por acidente.",
            file=sys.stderr,
        )
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(schema, keys, args.parquet), encoding="utf-8")

    tables = len(schema)
    columns = sum(len(c) for c in schema.values())
    print(f"{args.out}: {tables} tabelas, {columns} colunas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
