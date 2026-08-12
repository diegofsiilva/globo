"""Converte o dump MySQL do Argus (argus_dump.sql) em Parquet, uma pasta por tabela.

O dump tem ~3.9 GB / 68.8 M linhas, entao a leitura e feita em streaming: cada
linha de `VALUES` e parseada e as linhas sao despejadas em row groups de Parquet
sem nunca materializar a tabela inteira em memoria.

Uso:
    python apps/tools/etl_dump.py [--dump argus_dump.sql] [--out data/parquet]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# --------------------------------------------------------------------------- #
# Schema (DDL)
# --------------------------------------------------------------------------- #

RE_CREATE = re.compile(r"^CREATE TABLE `(\w+)` \($")
RE_COLUMN = re.compile(r"^\s+`(\w+)` ([a-z]+)(?:\(([^)]*)\))?(.*)$")
RE_KEY = re.compile(r"^\s+(PRIMARY KEY|UNIQUE KEY|KEY|CONSTRAINT)\b")

# tipo MySQL -> tipo Arrow
ARROW_TYPE = {
    "bigint": pa.int64(),
    "int": pa.int32(),
    "tinyint": pa.int8(),
    "smallint": pa.int16(),
    "double": pa.float64(),
    "float": pa.float32(),
    "decimal": pa.float64(),
    "varchar": pa.string(),
    "char": pa.string(),
    "text": pa.string(),
    "mediumtext": pa.string(),
    "longtext": pa.string(),
    "tinytext": pa.string(),
    "enum": pa.string(),
    "date": pa.string(),
    "datetime": pa.string(),
    "timestamp": pa.string(),
}

INT_TYPES = {"bigint", "int", "tinyint", "smallint"}
FLOAT_TYPES = {"double", "float", "decimal"}


def parse_schema(dump_path: Path) -> dict:
    """Le a secao DDL do dump e devolve {tabela: {coluna: tipo_mysql}}."""
    schema: dict[str, dict[str, str]] = {}
    table = None
    with dump_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.startswith("INSERT INTO"):
                break  # DDL acabou
            m = RE_CREATE.match(line)
            if m:
                table = m.group(1)
                schema[table] = {}
                continue
            if table is None:
                continue
            if line.startswith(")"):
                table = None
                continue
            if RE_KEY.match(line):
                continue
            m = RE_COLUMN.match(line)
            if m:
                schema[table][m.group(1)] = m.group(2)
    return schema


# --------------------------------------------------------------------------- #
# Parser de linhas de VALUES
# --------------------------------------------------------------------------- #

RE_INSERT = re.compile(rb"^INSERT INTO `(\w+)` \(([^)]*)\) VALUES$")

# Casa uma string entre aspas simples (com escapes \\ e \') OU uma virgula
# separadora. Deixa o motor de regex (C) pular o conteudo das strings, o que e
# muito mais rapido do que varrer caractere a caractere em Python.
RE_TOKEN = re.compile(rb"'(?:[^'\\]|\\.)*'|,")

UNESCAPE = {
    b"\\0": b"\0",
    b"\\'": b"'",
    b'\\"': b'"',
    b"\\b": b"\b",
    b"\\n": b"\n",
    b"\\r": b"\r",
    b"\\t": b"\t",
    b"\\Z": b"\x1a",
    b"\\\\": b"\\",
}
RE_ESCAPE = re.compile(rb"\\.")


def _unescape(raw: bytes) -> str:
    """Remove as aspas externas e desfaz os escapes do mysqldump.

    Args:
        raw (bytes): Bytes brutos do campo entre aspas.

    Returns:
        str: Texto decodificado e sanitizado.
    """
    body = raw[1:-1]
    if b"\\" in body:
        body = RE_ESCAPE.sub(lambda m: UNESCAPE.get(m.group(0), m.group(0)[1:]), body)
    return body.decode("utf-8", errors="replace")


def split_values(inner: bytes) -> list[bytes]:
    """Divide o miolo de `(...)` nos campos, respeitando strings entre aspas.

    Args:
        inner (bytes): Sequência de bytes entre parênteses da instrução VALUES.

    Returns:
        list[bytes]: Lista dos valores em bytes de cada coluna.
    """
    fields: list[bytes] = []
    start = 0
    for m in RE_TOKEN.finditer(inner):
        if m.group(0) == b",":
            fields.append(inner[start : m.start()])
            start = m.end()
    fields.append(inner[start:])
    return fields


def convert_field(raw: bytes, mysql_type: str):
    """Converte um campo bruto do dump para o tipo Python correspondente.

    Args:
        raw (bytes): Conteúdo em bytes do campo.
        mysql_type (str): Nome do tipo MySQL da coluna.

    Returns:
        Any: Valor convertido (int, float, str ou None).
    """
    if raw == b"NULL" or raw == b"":
        return None
    if raw[0:1] == b"'":
        text = _unescape(raw)
        # tinyint/int/double as vezes vem citado; normaliza pelo tipo da coluna
        if mysql_type in INT_TYPES:
            return int(text)
        if mysql_type in FLOAT_TYPES:
            return float(text)
        return text
    if mysql_type in INT_TYPES:
        return int(raw)
    if mysql_type in FLOAT_TYPES:
        return float(raw)
    return raw.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# Writer
# --------------------------------------------------------------------------- #

BATCH_ROWS = 500_000


class TableWriter:
    """Acumula linhas e escreve em Parquet a cada BATCH_ROWS."""

    def __init__(self, table: str, columns: list[str], types: list[str], out_dir: Path):
        """Inicializa o gravador Parquet da tabela.

        Args:
            table (str): Nome da tabela.
            columns (list[str]): Nomes das colunas.
            types (list[str]): Tipos MySQL correspondentes.
            out_dir (Path): Diretório de saída dos arquivos Parquet.
        """
        self.table = table
        self.columns = columns
        self.types = types
        self.schema = pa.schema(
            [pa.field(c, ARROW_TYPE.get(t, pa.string())) for c, t in zip(columns, types)]
        )
        self.path = out_dir / f"{table}.parquet"
        self.writer = pq.ParquetWriter(self.path, self.schema, compression="zstd")
        self.buffers: list[list] = [[] for _ in columns]
        self.buffered = 0
        self.rows = 0

    def add(self, values: list):
        """Adiciona uma linha de valores ao buffer local.

        Args:
            values (list): Lista de valores da linha.
        """
        for buf, v in zip(self.buffers, values):
            buf.append(v)
        self.buffered += 1
        self.rows += 1
        if self.buffered >= BATCH_ROWS:
            self.flush()

    def flush(self):
        """Despeja o buffer acumulado gravando um novo row group no arquivo Parquet."""
        if not self.buffered:
            return
        arrays = [
            pa.array(buf, type=field.type)
            for buf, field in zip(self.buffers, self.schema)
        ]
        self.writer.write_table(pa.Table.from_arrays(arrays, schema=self.schema))
        self.buffers = [[] for _ in self.columns]
        self.buffered = 0

    def close(self):
        """Finaliza a gravação e fecha o gravador do arquivo Parquet."""
        self.flush()
        self.writer.close()


# --------------------------------------------------------------------------- #
# Loop principal
# --------------------------------------------------------------------------- #


def run(dump_path: Path, out_dir: Path) -> dict:
    """Executa a conversão completa em streaming do arquivo .sql para Parquet.

    Args:
        dump_path (Path): Caminho para o arquivo SQL de dump.
        out_dir (Path): Diretório de destino dos arquivos Parquet.

    Returns:
        dict: Manifesto com estatísticas do processo de exportação.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/2] lendo DDL de {dump_path.name} ...", flush=True)
    schema = parse_schema(dump_path)
    print(f"      {len(schema)} tabelas no schema", flush=True)
    (out_dir / "_schema.json").write_text(json.dumps(schema, indent=2), encoding="utf-8")

    writers: dict[str, TableWriter] = {}
    current: TableWriter | None = None
    cur_types: list[str] = []
    # fast path: tabelas 100% numericas nao precisam do tokenizer de strings
    cur_all_numeric = False
    cur_converters: list = []

    total_rows = 0
    bad_rows = 0
    t0 = time.time()
    size = dump_path.stat().st_size
    read_bytes = 0

    print(f"[2/2] convertendo {size / 1e9:.2f} GB ...", flush=True)
    with dump_path.open("rb") as fh:
        for line in fh:
            read_bytes += len(line)
            if line[0:1] == b"(" and current is not None:
                # remove "(" inicial e "),"/"); " final
                inner = line[1 : line.rindex(b")")]
                if cur_all_numeric and b"'" not in inner:
                    fields = inner.split(b",")
                else:
                    fields = split_values(inner)
                if len(fields) != len(cur_converters):
                    bad_rows += 1
                    continue
                current.add(
                    [conv(f, t) for conv, f, t in zip(cur_converters, fields, cur_types)]
                )
                total_rows += 1
                if total_rows % 5_000_000 == 0:
                    pct = 100 * read_bytes / size
                    rate = total_rows / (time.time() - t0) / 1e6
                    print(
                        f"      {pct:5.1f}%  {total_rows / 1e6:6.1f} M linhas  "
                        f"({rate:.2f} M/s)",
                        flush=True,
                    )
                continue

            if line.startswith(b"INSERT INTO"):
                m = RE_INSERT.match(line.rstrip(b"\n"))
                if not m:
                    print(f"      AVISO: INSERT nao reconhecido: {line[:120]!r}")
                    current = None
                    continue
                table = m.group(1).decode()
                columns = [c.strip(b"`").decode() for c in m.group(2).split(b",")]
                cur_types = [schema.get(table, {}).get(c, "text") for c in columns]
                cur_all_numeric = all(
                    t in INT_TYPES or t in FLOAT_TYPES for t in cur_types
                )
                cur_converters = [convert_field] * len(columns)
                if table not in writers:
                    writers[table] = TableWriter(table, columns, cur_types, out_dir)
                current = writers[table]

    for w in writers.values():
        w.close()

    elapsed = time.time() - t0
    counts = {t: w.rows for t, w in sorted(writers.items())}
    empty = sorted(set(schema) - set(writers))

    print(f"\nconcluido em {elapsed / 60:.1f} min — {total_rows:,} linhas", flush=True)
    if bad_rows:
        print(f"AVISO: {bad_rows} linhas descartadas por aridade incompativel")
    if empty:
        print(f"tabelas sem dados no dump: {', '.join(empty)}")

    manifest = {
        "dump": str(dump_path),
        "dump_bytes": size,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_s": round(elapsed, 1),
        "total_rows": total_rows,
        "bad_rows": bad_rows,
        "row_counts": counts,
        "empty_tables": empty,
    }
    (out_dir / "_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    width = max(len(t) for t in counts)
    for t, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {t:<{width}}  {n:>12,}")
    return manifest


def main() -> int:
    """Função principal do utilitário de linha de comando."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", default="argus_dump.sql", type=Path)
    ap.add_argument("--out", default="data/parquet", type=Path)
    args = ap.parse_args()

    if not args.dump.exists():
        print(f"erro: {args.dump} nao encontrado", file=sys.stderr)
        return 1
    run(args.dump, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
