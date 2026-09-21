"""Testes unitários do módulo ``telemetry.application.signals``.

Funções/classes testadas:
  - _severidade     — classificação de z-score em faixas de severidade
  - _signal_id      — geração de identificador estável para sinais
  - GenerateSignals — caso de uso de montagem de sinais (com repositório fake)
"""

from datetime import UTC, datetime

from telemetry.application.signals import (
    LIMIAR_CRITICAL,
    LIMIAR_WARNING,
    GenerateSignals,
    _severidade,
    _signal_id,
)

# ── TU-11 — _severidade ──────────────────────────────────────────────────


class TestSeveridade:
    # --- Casos válidos de classificação ---

    def test_deve_retornar_critical_para_zscore_alto(self):
        """Caso válido: |z| >= 4.0 → 'critical'."""
        assert _severidade(4.0) == "critical"
        assert _severidade(5.5) == "critical"
        assert _severidade(-4.0) == "critical"  # sinal negativo também

    def test_deve_retornar_warning_para_zscore_moderado(self):
        """Caso válido: 2.5 <= |z| < 4.0 → 'warning'."""
        assert _severidade(2.5) == "warning"
        assert _severidade(3.9) == "warning"
        assert _severidade(-3.0) == "warning"

    def test_deve_retornar_stable_para_zscore_baixo(self):
        """Caso válido: |z| < 2.5 → 'stable'."""
        assert _severidade(2.0) == "stable"
        assert _severidade(0.0) == "stable"

    # --- Casos de limite exatos (thresholds reais da implementação) ---

    def test_limites_exatos_de_severidade(self):
        """Valores-limite: transições nos thresholds reais LIMIAR_WARNING e LIMIAR_CRITICAL."""
        # Logo abaixo de warning → stable
        assert _severidade(2.49) == "stable"
        # Exatamente em warning → warning
        assert _severidade(LIMIAR_WARNING) == "warning"  # 2.5

        # Logo abaixo de critical → warning
        assert _severidade(3.99) == "warning"
        # Exatamente em critical → critical
        assert _severidade(LIMIAR_CRITICAL) == "critical"  # 4.0

        # Negativo no limiar → mesma classificação
        assert _severidade(-LIMIAR_WARNING) == "warning"
        assert _severidade(-LIMIAR_CRITICAL) == "critical"


# ── TU-12 — _signal_id ───────────────────────────────────────────────────


class TestSignalId:
    def test_deve_gerar_id_deterministico(self):
        """Caso válido: mesma tripla → mesmo ID a cada chamada."""
        id1 = _signal_id("pop-sp", "app-video", "p95_latency")
        id2 = _signal_id("pop-sp", "app-video", "p95_latency")
        assert id1 == id2

    def test_deve_gerar_ids_diferentes_para_triplas_diferentes(self):
        """Caso válido: triplas distintas → IDs distintos."""
        id1 = _signal_id("pop-sp", "app-video", "p95_latency")
        id2 = _signal_id("pop-rj", "app-video", "p95_latency")
        assert id1 != id2

    def test_deve_ter_16_caracteres_hex(self):
        """Formato: SHA-256 truncado em 16 chars hexadecimais."""
        result = _signal_id("source", "entity", "metric")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)


# ── TU-13 — GenerateSignals.execute (com repositório fake) ───────────────


class _FakeSignalsRepository:
    """Stub do SignalsRepository para isolar a lógica do caso de uso."""

    def __init__(self, linhas):
        self._linhas = linhas

    def desvios(self, desde, ate, limiar, *, escopo=None):
        return self._linhas


class TestGenerateSignals:
    @staticmethod
    def _bucket(source, entity, metric, ts, z, value=100, media=50, desvio=10):
        return {
            "source": source,
            "entity": entity,
            "metric": metric,
            "bucket_ts": ts,
            "z": z,
            "value": value,
            "media": media,
            "desvio": desvio,
        }

    def test_deve_montar_sinal_com_severidade_e_multiplicador(self):
        """Caso válido: desvio acima do limiar gera sinal com campos calculados."""
        agora = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
        antes = datetime(2026, 7, 14, 11, 0, tzinfo=UTC)

        linhas = [
            self._bucket("pop-sp", "app", "p95", antes, z=3.0, value=120, media=50, desvio=10),
            self._bucket("pop-sp", "app", "p95", agora, z=3.0, value=120, media=50, desvio=10),
        ]
        resultado = GenerateSignals(_FakeSignalsRepository(linhas)).execute(antes, agora)

        assert resultado["count"] == 1
        sinal = resultado["items"][0]
        assert sinal["severity"] == "warning"  # |3.0| >= 2.5 e < 4.0
        assert sinal["multiplier"] == 2.4  # 120 / 50
        assert sinal["consecutive_buckets_over_threshold"] == 2
        assert sinal["trend"] == [120, 120]

    def test_deve_ignorar_grupo_cujo_ultimo_bucket_esta_abaixo_do_limiar(self):
        """Caso de erro previsto: último bucket com |z| < 2.0 → sem sinal ativo."""
        agora = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
        antes = datetime(2026, 7, 14, 11, 0, tzinfo=UTC)

        linhas = [
            self._bucket("pop-sp", "app", "p95", antes, z=3.0),
            self._bucket("pop-sp", "app", "p95", agora, z=1.5),  # abaixo do limiar
        ]
        resultado = GenerateSignals(_FakeSignalsRepository(linhas)).execute(antes, agora)

        assert resultado["count"] == 0
        assert resultado["items"] == []

    def test_deve_truncar_e_ordenar_por_magnitude(self):
        """Caso válido: limite < sinais → truncated=True, ordenação por |z| desc."""
        agora = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
        antes = datetime(2026, 7, 14, 11, 0, tzinfo=UTC)

        linhas = [
            self._bucket(f"pop-{i}", "app", "metric", agora, z=3.0 + i * 0.5) for i in range(5)
        ]
        resultado = GenerateSignals(_FakeSignalsRepository(linhas)).execute(antes, agora, limite=2)

        assert resultado["count"] == 2
        assert resultado["truncated"] is True
        assert abs(resultado["items"][0]["z"]) >= abs(resultado["items"][1]["z"])

    def test_deve_calcular_threshold_value_na_unidade_da_metrica(self):
        """Caso válido: threshold_value converte o limiar z para unidade nativa."""
        agora = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
        antes = datetime(2026, 7, 14, 11, 0, tzinfo=UTC)

        # z positivo: threshold_value = media + LIMIAR_SINAL * desvio = 50 + 2.0*10 = 70
        linhas = [
            self._bucket("pop", "app", "m", agora, z=3.0, value=100, media=50, desvio=10),
        ]
        resultado = GenerateSignals(_FakeSignalsRepository(linhas)).execute(antes, agora)

        sinal = resultado["items"][0]
        assert sinal["threshold_value"] == 70.0  # 50 + 1 * 2.0 * 10
