"""Testes unitários do módulo ``telemetry.application.redaction``.

Funções testadas:
  - hash_user_id  — desidentificação de user_id via SHA-256 truncado
  - sanitize_url  — remoção de query params sensíveis
  - redact_headers — allowlist de cabeçalhos HTTP
  - redact_attributes — redação composta do bloco de atributos
"""

import hashlib

from telemetry.application.redaction import (
    MASKED,
    hash_user_id,
    redact_attributes,
    redact_headers,
    sanitize_url,
)


# ── TU-01 — hash_user_id ─────────────────────────────────────────────────


class TestHashUserId:

    def test_deve_gerar_hash_deterministico_de_32_hex(self):
        """Caso válido: user_id presente gera SHA-256 truncado em 32 chars."""
        salt = "meu-salt-secreto"
        user_id = "usuario-123"
        resultado = hash_user_id(user_id, salt)

        esperado = hashlib.sha256(f"{salt}:{user_id}".encode()).hexdigest()[:32]
        assert resultado == esperado
        assert len(resultado) == 32
        assert all(c in "0123456789abcdef" for c in resultado)

    def test_deve_retornar_none_quando_user_id_for_none(self):
        """Caso de ausência: None retorna None sem erro."""
        assert hash_user_id(None, "salt") is None

    def test_deve_retornar_none_quando_user_id_for_vazio(self):
        """Caso de ausência: string vazia retorna None."""
        assert hash_user_id("", "salt") is None

    def test_deve_retornar_none_quando_user_id_for_mascarado(self):
        """Caso de erro previsto: valor '***' (MASKED) retorna None."""
        assert hash_user_id(MASKED, "salt") is None

    def test_salts_diferentes_produzem_hashes_diferentes(self):
        """Segurança: salts distintos impedem cruzamento de hashes."""
        uid = "mesmo-usuario"
        h1 = hash_user_id(uid, "salt-a")
        h2 = hash_user_id(uid, "salt-b")
        assert h1 != h2


# ── TU-02 — sanitize_url ─────────────────────────────────────────────────


class TestSanitizeUrl:

    def test_deve_remover_token_e_preservar_parametros_seguros(self):
        """Caso válido: 'token' sai, 'page' e 'sort' ficam."""
        url = "https://api.example.com/data?page=2&token=abc123&sort=asc"
        resultado = sanitize_url(url)

        assert "token" not in resultado
        assert "page=2" in resultado
        assert "sort=asc" in resultado

    def test_deve_remover_todos_os_parametros_sensiveis(self):
        """Caso válido: access_token, authorization, user_id removidos."""
        url = "https://api.example.com/v1?access_token=xyz&authorization=bearer&user_id=42&ok=1"
        resultado = sanitize_url(url)

        assert "access_token" not in resultado
        assert "authorization" not in resultado
        assert "user_id" not in resultado
        assert "ok=1" in resultado

    def test_deve_preservar_url_sem_query(self):
        """Caso válido: URL limpa passa sem alteração."""
        url = "https://api.example.com/path/to/resource"
        assert sanitize_url(url) == url

    def test_deve_retornar_none_para_entrada_vazia(self):
        """Caso de ausência: None e '' retornam None."""
        assert sanitize_url(None) is None
        assert sanitize_url("") is None


# ── TU-03 — redact_headers ───────────────────────────────────────────────


class TestRedactHeaders:

    def test_deve_manter_apenas_headers_da_allowlist(self):
        """Caso válido: Content-Type e X-Client-Version passam; Authorization e Cookie não."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer secret-token",
            "X-Client-Version": "2.1.0",
            "Cookie": "session=abc",
        }
        resultado = redact_headers(headers)

        assert "content-type" in resultado
        assert "x-client-version" in resultado
        assert "authorization" not in resultado
        assert "cookie" not in resultado

    def test_deve_retornar_dict_vazio_quando_entrada_nao_for_dict(self):
        """Caso de erro: entradas não-dict retornam {} sem exceção."""
        assert redact_headers("string-invalida") == {}
        assert redact_headers(None) == {}
        assert redact_headers(42) == {}

    def test_deve_normalizar_chaves_para_lowercase(self):
        """Caso válido: chaves em qualquer casing são normalizadas."""
        headers = {"ACCEPT": "text/html", "X-PLATFORM-ID": "ios"}
        resultado = redact_headers(headers)

        assert "accept" in resultado
        assert "x-platform-id" in resultado
        assert "ACCEPT" not in resultado


# ── TU-04 — redact_attributes ────────────────────────────────────────────


class TestRedactAttributes:

    def test_deve_remover_campos_bloqueados_e_sanitizar_url(self):
        """Caso válido: authorization e response_headers saem; request_url é sanitizada."""
        attributes = {
            "authorization": "Bearer secret",
            "response_headers": {"set-cookie": "sid=x"},
            "request_url": "https://api.com/v1?token=abc&page=1",
            "route_path": "/home",
        }
        resultado = redact_attributes(attributes)

        assert "authorization" not in resultado
        assert "response_headers" not in resultado
        assert "token" not in resultado["request_url"]
        assert "page=1" in resultado["request_url"]
        assert resultado["route_path"] == "/home"

    def test_deve_filtrar_request_headers_pela_allowlist(self):
        """Caso válido: request_headers internos são filtrados."""
        attributes = {
            "request_headers": {
                "Content-Type": "application/json",
                "Authorization": "Bearer x",
                "X-Custom-Secret": "val",
            }
        }
        resultado = redact_attributes(attributes)

        assert "content-type" in resultado["request_headers"]
        assert "authorization" not in resultado["request_headers"]
        assert "x-custom-secret" not in resultado["request_headers"]

    def test_deve_omitir_request_headers_quando_nenhum_e_seguro(self):
        """Caso de erro previsto: nenhum header sobrevive → chave omitida."""
        attributes = {
            "request_headers": {"Authorization": "Bearer x", "Cookie": "s=1"},
            "route_path": "/ok",
        }
        resultado = redact_attributes(attributes)
        assert "request_headers" not in resultado
