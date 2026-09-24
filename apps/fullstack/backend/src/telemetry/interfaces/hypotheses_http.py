"""Rotas publicas de consulta e feedback de hipoteses."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from flask import Blueprint, current_app, jsonify, request

from telemetry.domain.exceptions import (
    RefinementUnavailableError,
    ResourceNotFoundError,
    ValidationError,
)

hypotheses_api = Blueprint("hypotheses", __name__, url_prefix="/api/v1")

FAMILIES = frozenset(
    {
        "deploy_regression",
        "backend_internal",
        "playback_authorization",
        "cdn_degradation",
        "origin_encoding",
        "regional_or_isp",
        "waf_block",
        "player_or_device",
        "qoe_without_error",
        "expected_live_peak",
        "source_data_delay",
    }
)


def repository() -> Any:
    """Obtém o repositório de hipóteses registrado na aplicação.

    Returns:
        Any: A instância montada em `create_app`, ou o dublê injetado no teste.
    """
    return current_app.extensions["hypothesis_repository"]


def _int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    """Lê e valida um parâmetro inteiro da query string.

    Args:
        name (str): Nome do parâmetro.
        default (int): Valor quando o parâmetro não vem.
        minimum (int): Menor valor aceito.
        maximum (int): Maior valor aceito.

    Returns:
        int: O valor validado.

    Raises:
        ValidationError: Se não for inteiro ou estiver fora da faixa. Recusar é
            deliberado: silenciosamente prender ao limite devolveria uma página
            de tamanho diferente do pedido, sem nada indicando isso.
    """
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValidationError(f"{name} precisa ser inteiro", field=name) from error
    if not minimum <= value <= maximum:
        raise ValidationError(f"{name} precisa estar entre {minimum} e {maximum}", field=name)
    return value


def _datetime(name: str) -> datetime | None:
    """Lê e valida um instante ISO-8601 da query string.

    Args:
        name (str): Nome do parâmetro.

    Returns:
        datetime | None: O instante, ou `None` quando o parâmetro não vem.

    Raises:
        ValidationError: Se o formato for inválido ou o instante vier SEM fuso.
            Exigir o fuso é essencial num sistema com relógio virtual: um
            instante ingênuo seria interpretado como UTC e deslocaria a janela
            em três horas sem nenhum erro visível.
    """
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValidationError(f"{name} precisa ser ISO-8601", field=name) from error
    if value.tzinfo is None:
        raise ValidationError(f"{name} precisa incluir timezone", field=name)
    return value


def _json_value(value: Any) -> Any:
    """Converte `datetime` em texto ISO-8601, recursivamente.

    O `jsonify` do Flask serializa `datetime` no formato HTTP (RFC 822), que o
    `Date` do JavaScript lê de forma inconsistente entre navegadores. Toda data
    desta API sai em ISO-8601.

    Args:
        value (Any): Valor vindo do banco, possivelmente aninhado.

    Returns:
        Any: A mesma estrutura, com as datas já em texto.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


@hypotheses_api.get("/hypothesis-runs")
def hypothesis_runs():
    """Execuções concluídas do motor de hipóteses."""
    limit = _int("limit", default=50, minimum=1, maximum=200)
    before = request.args.get("before_run_id")
    if before is not None and not before.isdigit():
        raise ValidationError("before_run_id precisa ser inteiro", field="before_run_id")
    rows = repository().runs(limit=limit, before_run_id=int(before) if before else None)
    return jsonify({"items": _json_value(rows), "count": len(rows)})


@hypotheses_api.get("/hypotheses")
def hypotheses():
    """Página keyset de hipóteses geradas, com filtros cumulativos.

    Os valores aceitos em `family`, `kind`, `confidence` e `review_status` são
    validados contra conjuntos fechados. Um valor fora do conjunto vira 422 e
    não uma lista vazia -- lista vazia é indistinguível de "não há hipótese
    nesta família", e o operador leria um erro de digitação como um resultado.
    """
    run_id = request.args.get("run_id")
    if run_id is not None and not run_id.isdigit():
        raise ValidationError("run_id precisa ser inteiro", field="run_id")
    filters = {
        "family": (request.args.get("family") or None, FAMILIES),
        "kind": (
            request.args.get("kind") or None,
            {"operational", "context", "data_quality"},
        ),
        "confidence": (
            request.args.get("confidence") or None,
            {"high", "medium", "low"},
        ),
        "review_status": (
            request.args.get("review_status") or None,
            {"unreviewed", "confirmed", "partially_confirmed", "rejected"},
        ),
    }
    for name, (value, allowed) in filters.items():
        if value is not None and value not in allowed:
            raise ValidationError(f"{name} invalido", field=name)
    since = _datetime("from")
    until = _datetime("to")
    if since is not None and until is not None and since > until:
        raise ValidationError("from precisa ser anterior ou igual a to", field="from")
    try:
        page = repository().list(
            family=filters["family"][0],
            kind=filters["kind"][0],
            confidence=filters["confidence"][0],
            review_status=filters["review_status"][0],
            source=request.args.get("source") or None,
            entity=request.args.get("entity") or None,
            run_id=int(run_id) if run_id else None,
            since=since,
            until=until,
            cursor=request.args.get("cursor") or None,
            limit=_int("limit", default=50, minimum=1, maximum=200),
        )
    except ValueError as error:
        raise ValidationError(str(error), field="cursor") from error
    return jsonify(_json_value({**page, "count": len(page["items"])}))


@hypotheses_api.get("/hypotheses/<int:hypothesis_id>")
def hypothesis_detail(hypothesis_id: int):
    """Uma hipótese com toda a sua evidência.

    Args:
        hypothesis_id (int): Identificador da hipótese.
    """
    item = repository().detail(hypothesis_id)
    if item is None:
        raise ResourceNotFoundError("hipotese indisponivel")
    return jsonify(_json_value(item))


@hypotheses_api.post("/hypotheses/<int:hypothesis_id>/refinement")
def hypothesis_refinement(hypothesis_id: int):
    """Refina a hipotese sem permitir que o modelo acrescente fontes.

    Args:
        hypothesis_id (int): Identificador da hipotese gerada.
    """
    if not request.is_json:
        raise ValidationError("Content-Type precisa ser application/json")
    payload = request.get_json()
    if not isinstance(payload, dict):
        raise ValidationError("corpo precisa ser um objeto JSON")
    unexpected = set(payload) - {"question"}
    if unexpected:
        raise ValidationError("campo nao permitido", field=sorted(unexpected)[0])
    question = payload.get("question")
    if question is not None:
        if not isinstance(question, str) or not question.strip() or len(question) > 500:
            raise ValidationError(
                "question precisa ser texto entre 1 e 500 caracteres", field="question"
            )
        question = question.strip()
    item = repository().detail(hypothesis_id)
    if item is None:
        raise ResourceNotFoundError("hipotese indisponivel")
    refiner = current_app.extensions.get("hypothesis_refiner")
    if refiner is None:
        raise RefinementUnavailableError("refinamento por Ollama nao configurado")
    return jsonify(_json_value(refiner.refine(item, question=question)))


@hypotheses_api.post("/hypotheses/<int:hypothesis_id>/feedback")
def hypothesis_feedback(hypothesis_id: int):
    """Registra o veredito do operador sobre uma hipótese.

    A única escrita desta API. Idempotente por `idempotency_key`: reenviar o
    mesmo par chave/payload devolve 200 com o registro já gravado, e só a
    primeira gravação devolve 201. É o que permite ao dashboard reenviar depois
    de um timeout sem duplicar a avaliação.

    `reviewer_verified` sai sempre `false` e isso é honesto, não um campo por
    preencher: o token autentica o SERVIÇO, não a pessoa, então a API não tem
    como afirmar quem revisou.

    Args:
        hypothesis_id (int): Hipótese avaliada.
    """
    if not request.is_json:
        raise ValidationError("Content-Type precisa ser application/json")
    payload = request.get_json()
    if not isinstance(payload, dict):
        raise ValidationError("corpo precisa ser um objeto JSON")
    verdict = payload.get("verdict")
    if verdict not in {"confirmed", "partially_confirmed", "rejected"}:
        raise ValidationError("verdict invalido", field="verdict")
    raw_key = payload.get("idempotency_key")
    try:
        idempotency_key = UUID(str(raw_key))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError(
            "idempotency_key precisa ser UUID", field="idempotency_key"
        ) from error
    note = payload.get("note")
    reviewer_ref = payload.get("reviewer_ref")
    if note is not None and (not isinstance(note, str) or len(note) > 2000):
        raise ValidationError("note precisa ter no máximo 2000 caracteres", field="note")
    if reviewer_ref is not None and (not isinstance(reviewer_ref, str) or len(reviewer_ref) > 128):
        raise ValidationError(
            "reviewer_ref precisa ter no máximo 128 caracteres", field="reviewer_ref"
        )
    result = repository().submit_feedback(
        hypothesis_id=hypothesis_id,
        verdict=verdict,
        note=note,
        reviewer_ref=reviewer_ref,
        idempotency_key=idempotency_key,
        request_id=request.headers.get("X-Request-Id") or request.headers.get("X-Amzn-Trace-Id"),
    )
    if result is None:
        raise ResourceNotFoundError("hipotese indisponivel")
    status = 201 if result["created"] else 200
    return jsonify(
        {
            "feedback_id": result["feedback_id"],
            "created": result["created"],
            "reviewer_verified": False,
        }
    ), status
