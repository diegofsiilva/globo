"""Validação completa de CSV/Parquet e adaptação ao contrato de eventos."""

import base64
import csv
import datetime as dt
import io
import math
import re

import pyarrow.parquet as pq

from ..keys import build_row
from ..models import parse_event

MAX_BYTES = 50 * 1024**2
MAX_ROWS = 100_000
MAX_COLUMNS = 64
FIELDS = {
    "timestamp",
    "event_name",
    "session_id",
    "device_id",
    "event_id",
    "user_id",
    "app_version",
    "device_model",
    "duration",
    "request_status",
    "media_ads",
    "media_drm",
}
REQUIRED = {"timestamp", "event_name", "session_id", "device_id"}


def validate_mapping(mapping):
    """Confere destinos, nomes de origem e ausência de reutilização."""
    if not isinstance(mapping, dict) or not mapping.keys() >= REQUIRED:
        raise ValueError("Mapeie os quatro campos obrigatórios do evento.")
    if not mapping.keys() <= FIELDS:
        raise ValueError("O mapeamento contém campos de destino não suportados.")
    if any(not isinstance(v, str) or not v.strip() for v in mapping.values()):
        raise ValueError("Informe nomes de coluna válidos no mapeamento.")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Uma coluna não pode ser usada em dois campos.")


def json_value(value):
    """Preserva extras binários, temporais e numéricos em JSON serializável."""
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_value(v) for v in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return str(value)


def records(content, fmt, delimiter):
    """Itera registros reais sem reduzir o arquivo à amostra do navegador."""
    if fmt == "csv":
        if delimiter not in {",", ";", "\t", "|"}:
            raise ValueError("Separador CSV não suportado.")
        csv.field_size_limit(1024**2)
        reader = csv.reader(
            io.StringIO(content.decode("utf-8-sig")), delimiter=delimiter, strict=True
        )
        header = next(reader, [])
        names = [v.strip() for v in header]
        yield names
        for row in reader:
            if not row or all(not value.strip() for value in row):
                continue
            yield dict(zip(names, row, strict=True))
    elif fmt == "parquet":
        if content[:4] != b"PAR1" or content[-4:] != b"PAR1":
            raise ValueError("Assinatura Parquet inválida.")
        parquet = pq.ParquetFile(io.BytesIO(content))
        if parquet.metadata.num_rows > MAX_ROWS:
            raise ValueError("O arquivo excede 100.000 registros.")
        if any(
            parquet.metadata.row_group(i).total_byte_size > 64 * 1024**2
            for i in range(parquet.metadata.num_row_groups)
        ):
            raise ValueError("Grupo Parquet excede 64 MiB descomprimidos.")
        yield parquet.schema_arrow.names
        for batch in parquet.iter_batches(batch_size=500):
            yield from batch.to_pylist()
    else:
        raise ValueError("Formato não suportado.")


def mapped_value(field, value):
    """Normaliza escalares sem perder identificadores nem aceitar NaN."""
    if isinstance(value, (dict, list, bytes)):
        raise ValueError("Campo de destino requer valor escalar.")
    if value is None or (isinstance(value, str) and not value.strip()):
        if field in REQUIRED:
            raise ValueError("Campo obrigatório vazio.")
        return None
    text = value.isoformat() if isinstance(value, dt.datetime) else str(value).strip()
    if field in {"media_ads", "media_drm"}:
        if text.lower() not in {"true", "false", "1", "0"}:
            raise ValueError("Booleano inválido.")
        return text.lower() in {"true", "1"}
    if field == "duration":
        number = float(text)
        if not math.isfinite(number):
            raise ValueError("Número não finito.")
        return number
    if field == "request_status":
        number = int(text)
        if not -(2**31) <= number < 2**31:
            raise ValueError("Inteiro fora do intervalo suportado.")
        return number
    if field == "timestamp":
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
            r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?",
            text,
        ):
            raise ValueError("Data deve estar em ISO 8601.")
        dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    return text


def parse_file(content, fmt, mapping, delimiter, captured_at):
    """Valida todos os registros; rejeições não expõem valores pessoais.

    Returns:
        tuple: Linhas bronze, total, rejeitados e até cem motivos sanitizados.
    """
    validate_mapping(mapping)
    source = iter(records(content, fmt, delimiter))
    names = next(source)
    if not names or len(names) > MAX_COLUMNS or len(set(names)) != len(names):
        raise ValueError("Cabeçalho inválido; use até 64 colunas únicas.")
    if any(not name.strip() for name in names) or not set(mapping.values()) <= set(names):
        raise ValueError("Cabeçalho vazio ou coluna mapeada ausente no arquivo.")
    rows, errors = [], []
    total = rejected = size = 0
    for total, record in enumerate(source, start=1):
        if total > MAX_ROWS:
            raise ValueError("O arquivo excede 100.000 registros.")
        field = "evento"
        try:
            event = {}
            for field, column in mapping.items():
                event[field] = mapped_value(field, record[column])
            extra = {
                k: json_value(v) for k, v in record.items() if k not in mapping.values()
            }
            if extra:
                event["_file_extra"] = extra
            model, _ = parse_event(event)
            row = build_row(model, ingested_at=captured_at)
            size += len(str(row).encode("utf-8"))
            if size > 64 * 1024**2:
                raise OverflowError("Eventos expandidos excedem 64 MiB.")
            rows.append(row)
        except (ValueError, TypeError, KeyError):
            rejected += 1
            if len(errors) < 100:
                errors.append(
                    {
                        "linha": total,
                        "campo": field,
                        "mensagem": "Campo obrigatório ausente ou tipo inválido.",
                    }
                )
    if not total:
        raise ValueError("O arquivo não contém registros.")
    return rows, total, rejected, errors
