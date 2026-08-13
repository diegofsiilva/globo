"""Reproduz eventos contra a API de ingestao.

Le os CSVs do BI (ou os JSON ja convertidos), monta o payload e faz POST no
endpoint publicado pelo Terraform. Serve para validar o fluxo fim a fim depois
do deploy e para demonstrar a ingestao sem depender de uma TV de verdade.

Uso:
    # descobre a URL pelo output do Terraform
    URL=$(terraform -chdir=infra output -raw ingest_url)

    python apps/basica/tools/replay_events.py --url "$URL" --src ~/Downloads/Events
    python apps/basica/tools/replay_events.py --url "$URL" --src worker/tests/fixtures --batch
    python apps/basica/tools/replay_events.py --url "$URL" --src ~/Downloads/Events --repeat 100 --rate 20

    # so imprime o que enviaria
    python apps/basica/tools/replay_events.py --dry-run --src ~/Downloads/Events
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from events_csv_to_json import convert_file  # noqa: E402


def load_events(src: Path) -> list[dict]:
    """Carrega eventos de uma pasta contendo arquivos .csv (export do BI) ou .json.

    Args:
        src (Path): Diretório contendo os arquivos de eventos.

    Returns:
        list[dict]: Lista de dicionários de eventos prontos para envio.

    Raises:
        SystemExit: Se a pasta for inválida ou vazia.
    """
    if not src.is_dir():
        raise SystemExit(f"erro: {src} nao e uma pasta")

    events: list[dict] = []
    for path in sorted(src.glob("*.csv")):
        events.extend(convert_file(path))
    for path in sorted(src.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        events.extend(payload if isinstance(payload, list) else [payload])

    if not events:
        raise SystemExit(f"erro: nenhum .csv ou .json em {src}")
    return events


def post(url: str, payload, timeout: float = 10.0) -> tuple[int, str]:
    """Realiza uma requisição HTTP POST para a API de ingestão.

    Args:
        url (str): Endpoint HTTP de destino.
        payload: Objeto ou lista a ser serializado em JSON.
        timeout (float, optional): Tempo limite em segundos. Padrão é 10.0.

    Returns:
        tuple[int, str]: Par contendo (código de status HTTP, resposta cortada).
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")[:200]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:200]
    except urllib.error.URLError as exc:
        return 0, str(exc.reason)


def main() -> int:
    """Ponto de entrada do utilitário de simulação e replay de eventos."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, required=True, help="pasta com os eventos")
    ap.add_argument("--url", help="URL de ingestao (obrigatoria sem --dry-run)")
    ap.add_argument(
        "--batch",
        action="store_true",
        help="manda todos os eventos num POST so, em vez de um por requisicao",
    )
    ap.add_argument(
        "--repeat", type=int, default=1, help="quantas vezes repetir o conjunto"
    )
    ap.add_argument(
        "--rate",
        type=float,
        default=0.0,
        help="limite de requisicoes por segundo (0 = sem limite)",
    )
    ap.add_argument("--dry-run", action="store_true", help="so imprime o payload")
    args = ap.parse_args()

    if not args.url and not args.dry_run:
        raise SystemExit("erro: --url e obrigatorio (ou use --dry-run)")

    events = load_events(args.src)
    print(f"{len(events)} eventos carregados de {args.src}")

    if args.dry_run:
        json.dump(events if args.batch else events[0], sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    intervalo = 1.0 / args.rate if args.rate > 0 else 0.0
    enviados = falhas = 0
    t0 = time.time()

    for volta in range(args.repeat):
        lotes = [events] if args.batch else [[e] for e in events]
        for lote in lotes:
            payload = lote if args.batch else lote[0]
            status, corpo = post(args.url, payload)

            if 200 <= status < 300:
                enviados += len(lote)
            else:
                falhas += len(lote)
                print(f"  FALHA status={status} {corpo}", file=sys.stderr)

            if intervalo:
                time.sleep(intervalo)

        if args.repeat > 1 and (volta + 1) % 10 == 0:
            print(f"  volta {volta + 1}/{args.repeat}  enviados={enviados}")

    elapsed = time.time() - t0
    print(
        f"\n{enviados} eventos aceitos, {falhas} falhas em {elapsed:.1f}s "
        f"({enviados / elapsed:.1f} ev/s)"
    )
    if enviados:
        print(
            "\nA API responde 200 assim que o evento entra na fila; a gravacao no\n"
            "DynamoDB acontece logo depois, de forma assincrona. Confira com:\n"
            "  aws dynamodb scan --table-name <tabela> --select COUNT"
        )
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
