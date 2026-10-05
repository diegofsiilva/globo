"""Contrato OpenAPI da API de arquivos, separado da API de leitura."""

from .parser import MAX_BYTES, REQUIRED

JOB = {
    "type": "object",
    "required": ["id", "status", "total", "inserted", "duplicates", "rejected", "errors"],
    "properties": {
        "id": {"type": "string", "format": "uuid"},
        "filename": {"type": "string"},
        "status": {
            "type": "string",
            "enum": [
                "na_fila",
                "processando",
                "concluido",
                "concluido_com_rejeicoes",
                "rejeitado",
                "falhou",
            ],
        },
        **{
            key: {"type": "integer"}
            for key in ["total", "inserted", "duplicates", "rejected", "attempts"]
        },
        "errors": {
            "type": "array",
            "maxItems": 100,
            "items": {
                "type": "object",
                "properties": {
                    "linha": {"type": "integer"},
                    "campo": {"type": "string"},
                    "mensagem": {"type": "string"},
                },
            },
        },
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
    },
}


def responses(success):
    """Documenta sucesso e falhas comuns sem embutir credenciais."""
    return {
        str(success): {
            "description": "Job persistido ou resultado atual",
            "content": {
                "application/json": {
                    "schema": {"type": "object", "properties": {"job": JOB}}
                }
            },
        },
        **{
            str(code): {"description": desc}
            for code, desc in [
                (401, "Token de ingestão inválido"),
                (404, "Job ausente"),
                (409, "Job não pode ser retomado"),
                (413, "Upload excede limite"),
                (422, "Arquivo ou mapeamento inválido"),
                (503, "Indisponível"),
            ]
        },
    }


SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "Argus — ingestão de arquivos", "version": "1.0.0"},
    "security": [{"ingestBearer": []}],
    "components": {
        "securitySchemes": {
            "ingestBearer": {
                "type": "http",
                "scheme": "bearer",
                "description": "Token de ingestão",
            }
        }
    },
    "paths": {
        "/ingestion/live": {
            "get": {
                "security": [],
                "responses": {"200": {"description": "Processo ativo"}},
            }
        },
        "/ingestion/health": {
            "get": {
                "security": [],
                "responses": {
                    "200": {"description": "Banco acessível"},
                    "503": {"description": "Banco indisponível"},
                },
            }
        },
        "/ingestion/v1/session": {
            "get": {
                "responses": {
                    "200": {"description": "Token válido"},
                    "401": {"description": "Token inválido"},
                }
            }
        },
        "/ingestion/openapi.json": {
            "get": {"responses": {"200": {"description": "Este contrato"}}}
        },
        "/ingestion/v1/files": {
            "post": {
                "description": f"Até {MAX_BYTES} bytes; upload idempotente.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "type": "object",
                                "required": ["file", "mapping"],
                                "properties": {
                                    "file": {"type": "string", "format": "binary"},
                                    "mapping": {
                                        "type": "string",
                                        "description": "JSON destino→coluna: "
                                        + ", ".join(sorted(REQUIRED)),
                                    },
                                    "delimiter": {
                                        "type": "string",
                                        "enum": [",", ";", "\t", "|"],
                                    },
                                },
                            }
                        }
                    },
                },
                "responses": responses(202),
            }
        },
        **{
            path: {
                "parameters": [
                    {
                        "name": "job_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }
                ],
                method: {"responses": responses(code)},
            }
            for path, method, code in [
                ("/ingestion/v1/jobs/{job_id}", "get", 200),
                ("/ingestion/v1/jobs/{job_id}/retry", "post", 202),
            ]
        },
    },
}
