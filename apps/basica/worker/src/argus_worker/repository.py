"""Escrita em lote no DynamoDB.

Usa BatchWriteItem (25 itens por chamada, limite do servico) com retry dos
UnprocessedItems. Nao usa ConditionExpression: como a chave deriva do hash do
conteudo (ver keys.build_event_id), reentrega grava o mesmo item por cima e o
resultado e identico. Fica mais barato -- condicional gastaria WCU em falha.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from .config import DYNAMO_MAX_BATCH

log = logging.getLogger(__name__)

_SERIALIZER = TypeSerializer()

# Limite de tamanho de item do DynamoDB. Deixamos folga para o overhead dos
# nomes de atributo, que contam no total.
MAX_ITEM_BYTES = 380_000


class ItemTooLarge(ValueError):
    """Item acima do limite de 400 KB do DynamoDB -- retry nunca vai resolver."""


def _sanitize(value: Any) -> Any:
    """Deixa o valor no formato que o DynamoDB aceita.

    float vira Decimal (o DynamoDB não tem float), via str para não arrastar o
    resíduo binário de IEEE-754: Decimal(0.1) é 0.1000000000000000055..., já
    Decimal("0.1") é exatamente 0.1.

    Args:
        value (Any): Valor a ser sanitizado, de qualquer profundidade.

    Returns:
        Any: Valor equivalente com os floats convertidos em Decimal.
    """
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            # NaN/Infinity nao existem no DynamoDB; viram texto para nao
            # derrubar o lote inteiro por causa de um campo.
            return str(value)
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    return value


def _estimate_bytes(item: dict[str, Any]) -> int:
    """Estima o tamanho aproximado em bytes de um item para o DynamoDB.

    Args:
        item (dict[str, Any]): Dicionário com os atributos do item.

    Returns:
        int: Estimativa em bytes.
    """
    total = 0
    for key, value in item.items():
        total += len(str(key).encode("utf-8"))
        total += len(str(value).encode("utf-8"))
    return total


def serialize(item: dict[str, Any]) -> dict[str, Any]:
    """Converte um item Python no formato de mapa de AttributeValue do Boto3.

    Args:
        item (dict[str, Any]): Item bruto.

    Returns:
        dict[str, Any]: Mapa de AttributeValue serializado.
    """
    return {k: _SERIALIZER.serialize(_sanitize(v)) for k, v in item.items()}


def check_size(item: dict[str, Any]) -> None:
    """Levanta ItemTooLarge se o item nao couber no DynamoDB.

    Chamado pelo consumer ANTES de montar o lote. Um item gigante nunca vai
    passar por mais que tentemos, entao ele precisa ser desviado para a DLQ na
    entrada -- se entrasse no lote, derrubaria os outros 24 itens junto e o
    redrive repetiria a falha para sempre.

    Args:
        item (dict[str, Any]): Item a ser inspecionado.

    Raises:
        ItemTooLarge: Se o tamanho estimado exceder o limite seguro.
    """
    size = _estimate_bytes(item)
    if size > MAX_ITEM_BYTES:
        raise ItemTooLarge(
            f"item de ~{size} bytes excede o limite de {MAX_ITEM_BYTES} do DynamoDB"
        )


class EventRepository:
    """Grava eventos no DynamoDB, reportando quais itens ficaram para tras."""

    def __init__(self, client, table_name: str, max_retries: int = 5) -> None:
        """Inicializa o repositório do worker.

        Args:
            client: Cliente Boto3 para DynamoDB.
            table_name (str): Nome da tabela no DynamoDB.
            max_retries (int, optional): Número máximo de tentativas de reenvio
                para itens não processados.
        """
        self._client = client
        self._table = table_name
        self._max_retries = max_retries

    def put_many(self, items: list[dict[str, Any]]) -> set[str]:
        """Grava os itens e devolve as chaves (`pk|sk`) que NAO foram gravadas.

        Conjunto vazio significa que tudo entrou. As chaves devolvidas fazem o
        chamador segurar o delete da mensagem no SQS, para que o redrive tente
        de novo.

        Args:
            items (list[dict[str, Any]]): Lista de itens a serem gravados.

        Returns:
            set[str]: Conjunto de chaves dos itens que falharam.
        """
        failed: set[str] = set()
        for chunk in _chunks(_dedupe(items), DYNAMO_MAX_BATCH):
            failed |= self._write_chunk(chunk)
        return failed

    def _write_chunk(self, chunk: list[dict[str, Any]]) -> set[str]:
        """Escreve um lote de até 25 itens utilizando a API BatchWriteItem.

        Args:
            chunk (list[dict[str, Any]]): Lista contendo até 25 itens.

        Returns:
            set[str]: Chaves dos itens não processados no lote.
        """
        by_key: dict[str, dict[str, Any]] = {}
        requests: list[dict[str, Any]] = []

        for item in chunk:
            requests.append({"PutRequest": {"Item": serialize(item)}})
            by_key[_item_key(item)] = item

        pending = requests
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.batch_write_item(
                    RequestItems={self._table: pending}
                )
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code not in _RETRYABLE_CODES or attempt == self._max_retries:
                    log.error(
                        "batch_write_item falhou",
                        extra={"error_code": code, "attempt": attempt},
                        exc_info=True,
                    )
                    return set(by_key)
                _sleep_backoff(attempt)
                continue

            unprocessed = response.get("UnprocessedItems", {}).get(self._table, [])
            if not unprocessed:
                return set()

            if attempt == self._max_retries:
                break

            log.info(
                "reenviando itens nao processados pelo DynamoDB",
                extra={"unprocessed": len(unprocessed), "attempt": attempt},
            )
            pending = unprocessed
            _sleep_backoff(attempt)

        # Esgotou o retry: devolve as chaves que sobraram para o chamador.
        remaining = set()
        for request in pending:
            item = request.get("PutRequest", {}).get("Item", {})
            pk = item.get("pk", {}).get("S")
            sk = item.get("sk", {}).get("S")
            if pk and sk:
                remaining.add(f"{pk}|{sk}")
        return remaining or set(by_key)


_RETRYABLE_CODES = frozenset(
    {
        "ProvisionedThroughputExceededException",
        "ThrottlingException",
        "RequestLimitExceeded",
        "InternalServerError",
        "ServiceUnavailable",
    }
)


def _item_key(item: dict[str, Any]) -> str:
    """Extrai a chave identificadora no formato 'pk|sk' de um item.

    Args:
        item (dict[str, Any]): Dicionário com os atributos do item.

    Returns:
        str: String da chave combinada.
    """
    return f"{item.get('pk')}|{item.get('sk')}"


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove chaves repetidas, mantendo a ultima ocorrencia.

    O BatchWriteItem rejeita a requisicao INTEIRA se dois PutRequest tiverem a
    mesma chave -- nao e um item que falha, e o lote todo. E duplicata aqui e o
    caso esperado, nao a excecao: a chave deriva do hash do conteudo justamente
    para que a reentrega at-least-once do SQS colida de proposito. Sem esta
    deduplicacao, uma reentrega dentro do mesmo ciclo derrubaria os outros 24
    itens do lote junto.

    Manter a ultima e seguro porque chave igual significa conteudo igual: as
    duas versoes so diferem em `ingested_at`.

    Args:
        items (list[dict[str, Any]]): Lista de itens.

    Returns:
        list[dict[str, Any]]: Lista sem itens com chaves duplicadas.
    """
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        unique[_item_key(item)] = item
    return list(unique.values())


def _sleep_backoff(attempt: int) -> None:
    """Backoff exponencial com jitter total, para não sincronizar as tasks.

    Args:
        attempt (int): Número da tentativa atual, base do crescimento exponencial.
    """
    delay = min(2**attempt * 0.05, 2.0)
    time.sleep(random.uniform(0, delay))


def _chunks(items: list[Any], size: int) -> Iterable[list[Any]]:
    """Divide uma lista em pedaços (chunks) de tamanho fixo.

    Args:
        items (list[Any]): Lista de itens.
        size (int): Tamanho de cada sub-lote.

    Yields:
        Iterable[list[Any]]: Sub-listas com até `size` elementos.
    """
    for start in range(0, len(items), size):
        yield items[start : start + size]
