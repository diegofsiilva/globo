"""Testes unitários de regras de negócio, cursores e autenticação no backend.

Unidades testadas:
  - Funções de telemetry.application.use_cases:
      - summarize: agregação estatística de sessões de telemetria
      - shift_window_back: deslocamento temporal relativo para comparação de períodos
      - replace_window: substituição imutável dos limites de janela em EventFilters
  - Funções de telemetry.infrastructure.hypotheses:
      - _encode_cursor: codificação segura em Base64 URL-safe para paginação keyset
      - _decode_cursor: decodificação, recomposição de padding e validação estrita
  - Funções de telemetry.interfaces.auth:
      - _token_do_cabecalho: extração do Bearer token com tolerância a case e validação
      - rota_publica: catálogo de isenção de autenticação
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import pytest

from telemetry.application.use_cases import replace_window, shift_window_back, summarize
from telemetry.domain.entities import TelemetryEvent
from telemetry.infrastructure.hypotheses import _decode_cursor, _encode_cursor
from telemetry.interfaces.auth import _token_do_cabecalho, rota_publica
from telemetry.ports.event_repository import EventFilters


# ── TU-BCK-01 — summarize ──────────────────────────────────────────────────


class TestSummarize:
    """Verifica a agregação de dados de sessão e metadados de aparelho/app."""

    def test_deve_retornar_dicionario_vazio_quando_sem_eventos(self):
        """Lista vazia de eventos retorna dicionário vazio."""
        assert summarize([]) == {}

    def test_deve_resumir_sessao_com_multiplos_eventos(self):
        """Calcula contagens, erros, datas e duração corretamente."""
        t0 = datetime(2026, 8, 12, 14, 0, 0, tzinfo=UTC)
        t1 = datetime(2026, 8, 12, 14, 5, 30, tzinfo=UTC)

        e1 = TelemetryEvent(
            event_id="evt-1",
            event_name="session",
            occurred_at=t0,
            session_id="sess-100",
            device_id="dev-1",
            device_manufacturer="LG",
            device_model="webOS TV",
            device_os="webOS",
            device_os_version="6.0",
            app_target="webos",
            app_version="3.2.1",
            app_env="production",
        )
        e2 = TelemetryEvent(
            event_id="evt-2",
            event_name="request",
            occurred_at=t0 + timedelta(seconds=60),
            session_id="sess-100",
            device_id="dev-1",
        )
        e3 = TelemetryEvent(
            event_id="evt-3",
            event_name="error",
            occurred_at=t1,
            session_id="sess-100",
            device_id="dev-1",
        )

        resumo = summarize([e1, e2, e3])

        assert resumo["event_count"] == 3
        assert resumo["by_event_name"] == {"session": 1, "request": 1, "error": 1}
        assert resumo["error_count"] == 1
        assert resumo["started_at"] == t0.isoformat()
        assert resumo["ended_at"] == t1.isoformat()
        assert resumo["duration_seconds"] == 330.0  # 5 min 30s
        assert resumo["device"]["manufacturer"] == "LG"
        assert resumo["app"]["version"] == "3.2.1"


# ── TU-BCK-02 — shift_window_back e replace_window ────────────────────────


class TestWindowShift:
    """Verifica o cálculo de deslocamento de janelas para comparação histórica (RF14)."""

    def test_deve_deslocar_janela_com_span_positivo(self):
        """Janela válida: recua o intervalo pelo mesmo tamanho (span)."""
        t_from = datetime(2026, 8, 12, 10, 0, 0, tzinfo=UTC)
        t_to = datetime(2026, 8, 12, 12, 0, 0, tzinfo=UTC)  # 2 horas
        filtros = EventFilters(occurred_from=t_from, occurred_to=t_to, event_name="error")

        anterior = shift_window_back(filtros)
        assert anterior is not None
        assert anterior.occurred_from == t_from - timedelta(hours=2)  # 08:00
        assert anterior.occurred_to == t_from                        # 10:00
        assert anterior.event_name == "error"  # Preserva outros filtros

    def test_deve_retornar_none_quando_limites_ausentes(self):
        """Sem from ou to definido, retorna None."""
        assert shift_window_back(EventFilters(occurred_from=None, occurred_to=None)) is None
        assert shift_window_back(EventFilters(occurred_from=datetime.now(UTC), occurred_to=None)) is None

    def test_deve_retornar_none_quando_span_invalido(self):
        """Intervalo com to <= from (span nulo ou negativo) retorna None."""
        t = datetime(2026, 8, 12, 10, 0, 0, tzinfo=UTC)
        assert shift_window_back(EventFilters(occurred_from=t, occurred_to=t)) is None
        assert shift_window_back(EventFilters(occurred_from=t, occurred_to=t - timedelta(hours=1))) is None

    def test_replace_window_substitui_apenas_limites_temporais(self):
        """replace_window preserva todos os outros slots de EventFilters."""
        filtros = EventFilters(session_id="s1", app_target="android_tv", limit=100)
        novo_inicio = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
        novo_fim = datetime(2026, 8, 2, 0, 0, tzinfo=UTC)

        alterado = replace_window(filtros, start=novo_inicio, end=novo_fim)
        assert alterado.session_id == "s1"
        assert alterado.app_target == "android_tv"
        assert alterado.limit == 100
        assert alterado.occurred_from == novo_inicio
        assert alterado.occurred_to == novo_fim


# ── TU-BCK-03 — _encode_cursor e _decode_cursor ────────────────────────────


class TestHypothesesCursor:
    """Verifica a serialização e validação de cursores de paginação keyset."""

    def test_roundtrip_encode_e_decode_cursor(self):
        """Cursor codificado deve ser decodificado exatamente com os mesmos valores."""
        row = {
            "score": 87.5,
            "effect_start": datetime(2026, 7, 12, 18, 30, 0, tzinfo=UTC),
            "hypothesis_id": 42,
        }
        encoded = _encode_cursor(row)
        assert isinstance(encoded, str)
        # Não deve conter padding '='
        assert not encoded.endswith("=")

        score, effect_start, hyp_id = _decode_cursor(encoded)
        assert score == 87.5
        assert effect_start == row["effect_start"]
        assert hyp_id == 42

    def test_decode_cursor_rejeita_conteudo_invalido(self):
        """String que não é JSON ou Base64 válido levanta ValueError('cursor invalido')."""
        with pytest.raises(ValueError, match="cursor invalido"):
            _decode_cursor("cursor-totalmente-invalido!#@")

        with pytest.raises(ValueError, match="cursor invalido"):
            _decode_cursor("")


# ── TU-BCK-04 — auth: _token_do_cabecalho e rota_publica ───────────────────


class TestAuthHelpers:
    """Verifica utilitários de segurança e validação do cabeçalho Bearer."""

    def test_token_do_cabecalho_extrai_corretamente(self):
        """Extrai token com prefixo Bearer e é insensível a maiúsculas/minúsculas."""
        assert _token_do_cabecalho("Bearer token123") == "token123"
        assert _token_do_cabecalho("bearer token456") == "token456"
        assert _token_do_cabecalho("BEARER   token789   ") == "token789"

    def test_token_do_cabecalho_rejeita_formatos_invalidos(self):
        """Rejeita schemas diferentes de Bearer, valores vazios ou None."""
        assert _token_do_cabecalho(None) is None
        assert _token_do_cabecalho("") is None
        assert _token_do_cabecalho("Basic dXNlcjpwYXNz") is None
        assert _token_do_cabecalho("Bearer") is None
        assert _token_do_cabecalho("Bearer    ") is None

    def test_rota_publica_identifica_rotas_sem_autenticacao(self):
        """Rotas de documentação e sondas de saúde do ALB são públicas."""
        assert rota_publica("/health/live") is True
        assert rota_publica("/health/ready") is True
        assert rota_publica("/docs") is True
        assert rota_publica("/openapi.json") is True
        assert rota_publica("/favicon.ico") is True

        # Rotas de negócio e dados exigem autenticação
        assert rota_publica("/api/v1/events") is False
        assert rota_publica("/api/v1/sessions/123") is False
        assert rota_publica("/api/v1/hypotheses") is False
