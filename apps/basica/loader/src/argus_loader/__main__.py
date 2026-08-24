"""Entrypoint da carga inicial.

Roda uma vez e TERMINA -- por isso e task one-shot no ECS, e nao service (ver
infra/ecs_loader.tf). Um service o reiniciaria em laco para sempre, que e
exatamente o comportamento errado para um trabalho que acaba.

Uso:
    python -m argus_loader                      # baixa do S3 e carrega tudo
    python -m argus_loader --local data/parquet # de uma pasta local
    python -m argus_loader --tabela signal_meta --tabela live_event
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from argus_common import Database, Heartbeat, Metrics, configure_logging

from .loader import Loader, ManifestoDivergente

log = logging.getLogger(__name__)


def baixar_do_s3(bucket: str, prefixo: str, destino: Path) -> Path:
    """Baixa os Parquet e o manifesto do bucket de origem.

    Args:
        bucket (str): Nome do bucket.
        prefixo (str): Prefixo das chaves (por exemplo `parquet/`).
        destino (Path): Pasta local onde gravar.

    Returns:
        Path: A pasta de destino.

    Raises:
        RuntimeError: Se nao houver nada sob o prefixo.
    """
    import boto3

    s3 = boto3.client("s3")
    destino.mkdir(parents=True, exist_ok=True)

    baixados = 0
    paginador = s3.get_paginator("list_objects_v2")
    for pagina in paginador.paginate(Bucket=bucket, Prefix=prefixo):
        for objeto in pagina.get("Contents", []):
            chave = objeto["Key"]
            nome = Path(chave).name
            # So o que a carga usa. O dump .sql tambem mora no bucket (e a fonte
            # de verdade da proveniencia), mas sao 4 GB que o loader nao le.
            if not (nome.endswith(".parquet") or nome == "_manifest.json"):
                continue
            log.info(
                "baixando", extra={"chave": chave, "bytes": objeto.get("Size", 0)}
            )
            s3.download_file(bucket, chave, str(destino / nome))
            baixados += 1

    if not baixados:
        raise RuntimeError(
            f"nada encontrado em s3://{bucket}/{prefixo}. "
            "Rode `make origem-sync` antes da carga."
        )
    log.info("download concluido", extra={"arquivos": baixados})
    return destino


def captured_at_do_manifesto(parquet_dir: Path) -> dt.datetime:
    """Le do manifesto quando a origem gerou o dump.

    E este instante que vai para `_captured_at` e para o `captured_at` do
    change_log. Todas as 68,7 M de linhas do snapshot compartilham o mesmo
    valor, e isso e honesto: um snapshot e um retrato tirado de uma vez, nao um
    fluxo de mudancas observadas ao longo do tempo.

    Args:
        parquet_dir (Path): Pasta com o _manifest.json.

    Returns:
        datetime: Instante da geracao, em UTC.
    """
    manifesto = json.loads((parquet_dir / "_manifest.json").read_text(encoding="utf-8"))
    bruto = manifesto.get("generated_at")
    if not bruto:
        return dt.datetime.now(dt.UTC)
    momento = dt.datetime.fromisoformat(bruto)
    return momento if momento.tzinfo else momento.replace(tzinfo=dt.UTC)


def main() -> int:
    """Ponto de entrada.

    Returns:
        int: 0 em sucesso, 1 em falha.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local",
        type=Path,
        help="pasta local com os Parquet. Sem isto, baixa de ORIGEM_BUCKET.",
    )
    parser.add_argument(
        "--tabela",
        action="append",
        dest="tabelas",
        help="carrega so estas tabelas (pode repetir). Padrao: todas.",
    )
    parser.add_argument(
        "--sem-change-log",
        action="store_true",
        help=(
            "nao grava o snapshot em bronze.change_log. Economiza tempo e disco, "
            "e o preco e perder a propriedade de rebuild (decisao 4 do plano)."
        ),
    )
    args = parser.parse_args()

    service_name = os.getenv("SERVICE_NAME", "argus-loader")
    log_ = configure_logging(os.getenv("LOG_LEVEL", "INFO").upper(), service_name)
    metrics = Metrics(os.getenv("METRICS_NAMESPACE", "Argus/Ingestion"), service_name)
    heartbeat = Heartbeat(os.getenv("HEARTBEAT_PATH", "/tmp/argus-heartbeat"))

    db = None
    temporaria = None
    try:
        if args.local:
            parquet_dir = args.local
        else:
            bucket = os.getenv("ORIGEM_BUCKET")
            if not bucket:
                print(
                    "erro: sem --local, ORIGEM_BUCKET precisa estar definida.",
                    file=sys.stderr,
                )
                return 1
            temporaria = tempfile.TemporaryDirectory(prefix="argus-parquet-")
            parquet_dir = baixar_do_s3(
                bucket, os.getenv("ORIGEM_PREFIX", "parquet/"), Path(temporaria.name)
            )

        # Pool minusculo: a carga e um fluxo sequencial de COPY, e conexao extra
        # so disputaria I/O com ela.
        db = Database.from_env(min_size=1, max_size=2, application_name=service_name)

        loader = Loader(
            db,
            parquet_dir,
            captured_at=captured_at_do_manifesto(parquet_dir),
            escrever_change_log=not args.sem_change_log,
            heartbeat=heartbeat,
        )

        log_.info("carga iniciada", extra={"parquet_dir": str(parquet_dir)})
        resultado = loader.run(args.tabelas)

        for item in resultado.tabelas:
            metrics.count("RowsLoaded", item.linhas)
        metrics.flush()

        carregadas = [t for t in resultado.tabelas if not t.pulada]
        log_.info(
            "carga concluida",
            extra={
                "tabelas": len(resultado.tabelas),
                "carregadas": len(carregadas),
                "puladas": len(resultado.tabelas) - len(carregadas),
                "linhas": resultado.linhas,
            },
        )
        return 0

    except ManifestoDivergente:
        # Falha ALTA, e nao aviso: e a diferenca entre "carregou" e "carregou
        # tudo". Uma carga que perde linhas em silencio so aparece semanas
        # depois, como "o grafico esta estranho".
        log_.exception("a carga NAO confere com o manifesto")
        metrics.count("LoadMismatch")
        metrics.flush()
        return 1
    except Exception:
        log_.exception("carga abortou")
        metrics.count("LoadFailed")
        metrics.flush()
        return 1
    finally:
        if db is not None:
            db.close()
        if temporaria is not None:
            temporaria.cleanup()


if __name__ == "__main__":
    sys.exit(main())
