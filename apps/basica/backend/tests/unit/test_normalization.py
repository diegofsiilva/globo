"""Testes unitários do módulo ``telemetry.application.normalization``.

Funções testadas:
  - parse_datetime    — parsing multi-formato com normalização UTC
  - parse_json_object — validação de JSON em atributos
  - optional_float    — conversão numérica opcional com erro tipado
  - optional_int      — conversão inteira opcional com erro tipado
  - canonicalize_keys — mapeamento de chaves CSV → canônicas
  - parse_event_id    — geração/validação de UUID
"""

from uuid import UUID

import pytest

from telemetry.application.normalization import (
    canonicalize_keys,
    optional_float,
    optional_int,
    parse_datetime,
    parse_event_id,
    parse_json_object,
)
from telemetry.domain.exceptions import ValidationError

# ── TU-05 — parse_datetime ────────────────────────────────────────────────


class TestParseDatetime:
    def test_deve_parsear_iso_8601_com_z(self):
        """Caso válido: '2026-07-13T10:30:00Z' vira datetime UTC."""
        resultado = parse_datetime("2026-07-13T10:30:00Z")
        assert resultado.tzinfo is not None
        assert resultado.year == 2026
        assert resultado.month == 7
        assert resultado.hour == 10

    def test_deve_parsear_formato_legado_americano(self):
        """Caso válido: 'July 13, 2026 14:30:00' é suportado pelo fallback."""
        resultado = parse_datetime("July 13, 2026 14:30:00")
        assert resultado.year == 2026
        assert resultado.month == 7
        assert resultado.day == 13
        assert resultado.tzinfo is not None

    def test_deve_levantar_erro_para_timestamp_nulo(self):
        """Caso de erro: None → ValidationError com menção a 'obrigatorio'."""
        with pytest.raises(ValidationError, match="obrigatorio"):
            parse_datetime(None)

    def test_deve_levantar_erro_para_formato_desconhecido(self):
        """Caso de erro: string não reconhecida → ValidationError 'invalido'."""
        with pytest.raises(ValidationError, match="invalido"):
            parse_datetime("nao-e-uma-data")

    def test_deve_parsear_formato_simples_sem_timezone(self):
        """Caso válido: '2026-07-13 14:30:00' recebe UTC por padrão."""
        resultado = parse_datetime("2026-07-13 14:30:00")
        assert resultado.year == 2026
        assert resultado.hour == 14
        assert resultado.tzinfo is not None


# ── TU-06 — parse_json_object ─────────────────────────────────────────────


class TestParseJsonObject:
    def test_deve_parsear_json_string_valido(self):
        """Caso válido: string JSON com objeto → dict."""
        resultado = parse_json_object('{"key": "value", "count": 42}', "campo")
        assert resultado == {"key": "value", "count": 42}

    def test_deve_retornar_dict_existente_inalterado(self):
        """Caso válido: dict passado diretamente é retornado por referência."""
        entrada = {"a": 1}
        assert parse_json_object(entrada, "campo") is entrada

    def test_deve_retornar_dict_vazio_para_none_ou_string_vazia(self):
        """Caso de ausência: None e '' retornam {}."""
        assert parse_json_object(None, "campo") == {}
        assert parse_json_object("", "campo") == {}

    def test_deve_levantar_erro_para_json_malformado(self):
        """Caso de erro: JSON malformado → ValidationError."""
        with pytest.raises(ValidationError, match="JSON valido"):
            parse_json_object("{invalido", "campo")

    def test_deve_levantar_erro_quando_json_nao_for_objeto(self):
        """Caso de erro: JSON válido que é lista → ValidationError."""
        with pytest.raises(ValidationError, match="objeto JSON"):
            parse_json_object("[1, 2, 3]", "campo")


# ── TU-07 — optional_float / optional_int ─────────────────────────────────


class TestOptionalConversions:
    def test_optional_float_converte_string_numerica(self):
        """Caso válido: '3.14' → 3.14."""
        assert optional_float("3.14", "campo") == pytest.approx(3.14)

    def test_optional_float_retorna_none_para_none(self):
        """Caso de ausência: None → None sem erro."""
        assert optional_float(None, "campo") is None

    def test_optional_float_rejeita_texto_nao_numerico(self):
        """Caso de erro: 'abc' → ValidationError."""
        with pytest.raises(ValidationError, match="numerico"):
            optional_float("abc", "duration_ms")

    def test_optional_int_converte_string_inteira(self):
        """Caso válido: '2024' → 2024."""
        assert optional_int("2024", "campo") == 2024

    def test_optional_int_rejeita_float_string(self):
        """Caso de erro: '3.14' não é int → ValidationError."""
        with pytest.raises(ValidationError, match="inteiro"):
            optional_int("3.14", "device_model_year")


# ── TU-08 — canonicalize_keys ─────────────────────────────────────────────


class TestCanonicalizeKeys:
    def test_deve_converter_chaves_csv_para_canonicas(self):
        """Caso válido: 'Event Name' → 'event_name', 'Device Id' → 'device_id'."""
        payload = {
            "Event Name": "request",
            "Device Id": "abc-123",
            "Duration": "1.5",
        }
        resultado = canonicalize_keys(payload)

        assert "event_name" in resultado
        assert "device_id" in resultado
        assert "duration" in resultado
        assert resultado["event_name"] == "request"

    def test_deve_preservar_chaves_ja_canonicas(self):
        """Caso válido: chaves que não estão no CSV_FIELD_MAP passam inalteradas."""
        payload = {"event_name": "vitals", "session_id": "xyz"}
        resultado = canonicalize_keys(payload)
        assert resultado == payload


# ── TU-09 — parse_event_id ────────────────────────────────────────────────


class TestParseEventId:
    def test_deve_gerar_uuid_quando_valor_ausente(self):
        """Caso válido: None → UUID v4 gerado automaticamente."""
        resultado = parse_event_id(None)
        assert isinstance(resultado, UUID)

    def test_deve_aceitar_uuid_string_valido(self):
        """Caso válido: UUID v4 em string → objeto UUID equivalente."""
        uuid_str = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        resultado = parse_event_id(uuid_str)
        assert isinstance(resultado, UUID)
        assert str(resultado) == uuid_str

    def test_deve_levantar_erro_para_uuid_invalido(self):
        """Caso de erro: string que não é UUID → ValidationError."""
        with pytest.raises(ValidationError, match="UUID"):
            parse_event_id("nao-e-uuid")
