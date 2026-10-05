"""Upload autenticado e consulta de jobs sem acesso pela API de leitura."""

import hashlib
import hmac
import json
import os

from argus_common import Database
from flask import Flask, g, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from .parser import MAX_BYTES, validate_mapping
from .store import FileStore


def create_app(db=None, token_hash=None):
    """Monta aplicação; produção recusa configuração sem hash de ingestão."""
    expected = token_hash or os.getenv("INGEST_TOKEN_SHA256", "")
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise RuntimeError("INGEST_TOKEN_SHA256 deve conter SHA-256 hexadecimal.")
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES + 1024**2
    origins = set(filter(None, os.getenv("INGEST_CORS_ORIGINS", "").split(",")))
    store = FileStore(db or Database.from_env(application_name="argus-file-api"))

    @app.before_request
    def authorize():
        """Token de ingestão separado; hash é também a identidade do job."""
        if request.method == "OPTIONS":
            return ("", 204) if request.headers.get("Origin") in origins else ("", 403)
        if request.path in {"/ingestion/health", "/ingestion/live"}:
            return None
        token = request.headers.get("Authorization", "")
        digest = hashlib.sha256(token.removeprefix("Bearer ").encode()).hexdigest()
        if not token.startswith("Bearer ") or not hmac.compare_digest(digest, expected):
            return jsonify(erro="Token de ingestão inválido."), 401
        g.owner = digest
        return None

    @app.after_request
    def cors(response):
        """Desenvolvimento com duas portas exige origem explicitamente permitida."""
        origin = request.headers.get("Origin")
        if origin in origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type"
            )
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers.add("Vary", "Origin")
        return response

    @app.get("/ingestion/health")
    def health():
        """Sonda sem dados sensíveis para o orquestrador."""
        healthy = store.db.healthy()
        return jsonify(ok=healthy), 200 if healthy else 503

    @app.get("/ingestion/live")
    def live():
        """Sonda de vida independente do PostgreSQL."""
        return jsonify(ok=True)

    @app.get("/ingestion/v1/session")
    def session():
        """Confirma a credencial antes de salvá-la na aba."""
        return jsonify(ok=True)

    @app.post("/ingestion/v1/files")
    def upload():
        """Persiste o arquivo e devolve 202; processamento ocorre fora do HTTP."""
        uploaded = request.files.get("file")
        if uploaded is None:
            return jsonify(erro="Selecione um arquivo."), 422
        filename = secure_filename(uploaded.filename or "")[:200]
        fmt = filename.rsplit(".", 1)[-1].lower()
        if fmt not in {"csv", "parquet"}:
            return jsonify(erro="Use um arquivo CSV ou Parquet."), 422
        try:
            mapping = json.loads(request.form.get("mapping", "null"))
            validate_mapping(mapping)
            delimiter = request.form.get("delimiter", ",")
            if fmt == "csv" and delimiter not in {",", ";", "\t", "|"}:
                raise ValueError("Separador CSV não suportado.")
            content = uploaded.stream.read(MAX_BYTES + 1)
            if not content or len(content) > MAX_BYTES:
                raise ValueError("Use um arquivo não vazio de até 50 MiB.")
            job = store.enqueue(g.owner, filename, fmt, content, mapping, delimiter)
        except (ValueError, TypeError) as error:
            message = (
                str(error)
                if not isinstance(error, json.JSONDecodeError)
                else ("O mapeamento precisa ser um objeto JSON válido.")
            )
            return jsonify(erro=message), 422
        return jsonify(job=job), 202

    @app.get("/ingestion/v1/jobs/<uuid:job_id>")
    def status(job_id):
        """Retorna resultado sem conteúdo, payload dos eventos ou credenciais."""
        job = store.get(g.owner, job_id)
        return (
            (jsonify(job=job), 200) if job else (jsonify(erro="Job não encontrado."), 404)
        )

    @app.post("/ingestion/v1/jobs/<uuid:job_id>/retry")
    def retry(job_id):
        """Reenvia apenas falhas transitórias que ainda possuem arquivo retido."""
        job = store.retry(g.owner, job_id)
        return (
            (jsonify(job=job), 202)
            if job
            else (
                jsonify(erro="Job não pode ser retomado. Selecione o arquivo novamente."),
                409,
            )
        )

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_):
        """Converte limite de transporte em JSON legível pelo dashboard."""
        return jsonify(erro="Arquivo excede o limite de upload."), 413

    @app.errorhandler(500)
    def unavailable(_):
        """Não expõe exceções nem detalhes do banco ao operador."""
        return jsonify(erro="Serviço de ingestão indisponível."), 503

    @app.get("/ingestion/openapi.json")
    def openapi():
        """Documenta a fronteira HTTP exclusiva da ingestão."""
        from .openapi import SPEC

        return jsonify(SPEC)

    app.extensions["file_store"] = store
    return app
