"""Testes unitários da lógica do detector, da qualidade e do scoring.

Unidades testadas:
  - Funções de argus_processing.detector:
      - _transform: transformação logarítmica (log1p) para cauda longa vs identidade
      - _inverse: reversão da transformação (expm1) para unidades originais
      - _material: checagem de materialidade dupla (absoluta E relativa simultâneas)
      - _bad_direction: filtragem direcional de anomalias ('up', 'down', 'two_sided')
  - Função de argus_processing.quality:
      - _clamp: limitação matemática ao intervalo fechado [0.0, 1.0]
  - Função de argus_processing.scoring:
      - score_features: ponderação explicável de features, penalização por contradição,
        cálculo de cobertura e atribuição de níveis de confiança.
"""

from __future__ import annotations

import math

import pytest

from argus_processing.catalog import MetricPolicy
from argus_processing.detector import _bad_direction, _inverse, _material, _transform
from argus_processing.quality import _clamp
from argus_processing.scoring import score_features

# ── TU-PRC-01 — detector: _transform e _inverse ────────────────────────────


class TestDetectorTransformAndInverse:
    """Verifica as funções de transformação para o espaço do baseline e sua reversão."""

    def test_transform_aplica_log1p_quando_politica_exigir(self):
        """Métricas com política transform='log1p' comprimem valores usando math.log1p."""
        policy = MetricPolicy(
            direction="up",
            transform="log1p",
            materiality_absolute=10.0,
            materiality_relative=0.2,
            sigma_floor=0.01,
        )
        # log1p(0) == 0.0
        assert _transform(0.0, policy) == 0.0
        # log1p(9.0) == ln(10)
        assert pytest.approx(_transform(9.0, policy), rel=1e-6) == math.log1p(9.0)

    def test_transform_limita_valores_negativos_a_zero_antes_do_log1p(self):
        """Protege o log1p contra valores negativos."""
        policy = MetricPolicy(
            direction="up",
            transform="log1p",
            materiality_absolute=5.0,
            materiality_relative=0.1,
            sigma_floor=0.01,
        )
        assert _transform(-10.0, policy) == 0.0

    def test_transform_retorna_identidade_para_outras_politicas(self):
        """Mantém o valor quando a política não usa ``log1p``."""
        policy = MetricPolicy(
            direction="two_sided",
            transform="identity",
            materiality_absolute=1.0,
            materiality_relative=0.05,
            sigma_floor=0.01,
        )
        assert _transform(42.5, policy) == 42.5
        assert _transform(-5.0, policy) == -5.0

    def test_inverse_reverte_log1p_com_expm1(self):
        """_inverse usa math.expm1 para retornar à unidade nativa."""
        policy = MetricPolicy(
            direction="up",
            transform="log1p",
            materiality_absolute=1.0,
            materiality_relative=0.1,
            sigma_floor=0.01,
        )
        valor_transformado = math.log1p(50.0)
        assert pytest.approx(_inverse(valor_transformado, policy), rel=1e-6) == 50.0

    def test_roundtrip_transform_e_inverse(self):
        """Garante consistência de ida e volta: inverse(transform(x)) == x."""
        policy = MetricPolicy(
            direction="up",
            transform="log1p",
            materiality_absolute=1.0,
            materiality_relative=0.1,
            sigma_floor=0.01,
        )
        for x in [0.0, 1.5, 100.0, 5000.0]:
            assert pytest.approx(_inverse(_transform(x, policy), policy), rel=1e-6) == x


# ── TU-PRC-02 — detector: _material e _bad_direction ───────────────────────


class TestDetectorMaterialAndDirection:
    """Verifica os critérios de materialidade dupla e filtro de direção prejudicial."""

    def test_material_aprova_quando_atende_ambos_limiares(self):
        """Desvio é material se |obs - exp| >= abs E |obs - exp| / exp >= rel."""
        policy = MetricPolicy(
            direction="up",
            transform="identity",
            materiality_absolute=10.0,
            materiality_relative=0.20,  # 20%
            sigma_floor=0.01,
        )
        # exp=100, obs=125 -> delta=25 (>= 10) e rel=0.25 (>= 0.20) -> True
        assert _material(observed=125.0, expected=100.0, policy=policy) is True

    def test_material_reprova_se_falhar_no_limiar_absoluto(self):
        """Reprova quando somente o limiar relativo é atendido."""
        policy = MetricPolicy(
            direction="up",
            transform="identity",
            materiality_absolute=10.0,
            materiality_relative=0.20,
            sigma_floor=0.01,
        )
        # exp=1.0, obs=3.0 -> rel=200% (passa), mas delta=2.0 (< 10.0) -> False
        assert _material(observed=3.0, expected=1.0, policy=policy) is False

    def test_material_reprova_se_falhar_no_limiar_relativo(self):
        """Reprova quando somente o limiar absoluto é atendido."""
        policy = MetricPolicy(
            direction="up",
            transform="identity",
            materiality_absolute=10.0,
            materiality_relative=0.20,  # 20%
            sigma_floor=0.01,
        )
        # exp=1000.0, obs=1050.0 -> delta=50 (passa abs), mas rel=5% (< 20%) -> False
        assert _material(observed=1050.0, expected=1000.0, policy=policy) is False

    def test_material_com_expected_zero_nao_divide_por_zero(self):
        """Divisão protegida por max(abs(expected), 1e-12) previne ZeroDivisionError."""
        policy = MetricPolicy(
            direction="up",
            transform="identity",
            materiality_absolute=5.0,
            materiality_relative=0.5,
            sigma_floor=0.01,
        )
        # Com expected = 0.0, delta = 10.0 (>= 5.0) e rel = 10 / 1e-12 (>= 0.5) -> True
        assert _material(observed=10.0, expected=0.0, policy=policy) is True

    def test_bad_direction_up(self):
        """Métricas de direção 'up' só são anômalas quando sobem (observed > expected)."""
        policy = MetricPolicy("up", "identity", 1.0, 0.1, 0.01)
        assert _bad_direction(observed=110.0, expected=100.0, policy=policy) is True
        assert _bad_direction(observed=90.0, expected=100.0, policy=policy) is False
        assert _bad_direction(observed=100.0, expected=100.0, policy=policy) is False

    def test_bad_direction_down(self):
        """Marca métricas ``down`` apenas quando o observado cai."""
        policy = MetricPolicy("down", "identity", 1.0, 0.1, 0.01)
        assert _bad_direction(observed=80.0, expected=100.0, policy=policy) is True
        assert _bad_direction(observed=120.0, expected=100.0, policy=policy) is False
        assert _bad_direction(observed=100.0, expected=100.0, policy=policy) is False

    def test_bad_direction_two_sided(self):
        """Métricas two_sided são anômalas em qualquer desvio diferente de zero."""
        policy = MetricPolicy("two_sided", "identity", 1.0, 0.1, 0.01)
        assert _bad_direction(observed=150.0, expected=100.0, policy=policy) is True
        assert _bad_direction(observed=50.0, expected=100.0, policy=policy) is True
        assert _bad_direction(observed=100.0, expected=100.0, policy=policy) is False


# ── TU-PRC-03 — quality: _clamp ────────────────────────────────────────────


class TestQualityClamp:
    """Verifica a função matemática _clamp que confina razões ao intervalo [0, 1]."""

    def test_clamp_restringe_valores_extremos(self):
        """Valores menores que 0 viram 0.0, maiores que 1 viram 1.0."""
        assert _clamp(-0.5) == 0.0
        assert _clamp(1.5) == 1.0
        assert _clamp(0.0) == 0.0
        assert _clamp(1.0) == 1.0
        assert _clamp(0.75) == 0.75


# ── TU-PRC-04 — scoring: score_features ────────────────────────────────────


class TestScoreFeatures:
    """Verifica score, contradição, cobertura e confiança."""

    def test_score_com_todas_features_disponiveis_e_perfeitas(self):
        """Produz score 100 com todas as features perfeitas."""
        values = {
            "A": ("available", 1.0, "anomalia forte"),
            "T": ("available", 1.0, "alinhamento temporal"),
            "C": ("available", 1.0, "corroboracao"),
            "E": ("available", 1.0, "entidade afetada"),
            "I": ("available", 1.0, "impacto alto"),
            "Q": ("available", 1.0, "qualidade saudavel"),
        }
        score, coverage, confidence, features = score_features(values, contradiction=0.0)

        assert score == 100.0
        assert coverage == 1.0
        assert confidence == "high"
        # Deve conter as 6 features ponderadas mais a feature 'X' de contradição
        assert len(features) == 7
        assert features[-1].name == "X"

    def test_penalidade_de_contradicao_reduz_score(self):
        """Contradição aplica dedução de até 30 * contradição no score final."""
        values = {
            "A": ("available", 1.0, "anomalia"),
            "T": ("available", 1.0, "tempo"),
            "C": ("available", 1.0, "corroboracao"),
            "E": ("available", 1.0, "entidade"),
            "I": ("available", 1.0, "impacto"),
            "Q": ("available", 1.0, "qualidade"),
        }
        # contradiction = 0.5 -> reduz 30 * 0.5 = 15 pontos do score base (100 - 15 = 85)
        score, _, _, _ = score_features(values, contradiction=0.5)
        assert pytest.approx(score, rel=1e-5) == 85.0

    def test_confianca_media_quando_score_moderado(self):
        """Score entre 60 e 80 gera nível 'medium'."""
        values = {
            "A": ("available", 0.7, "anomalia"),
            "T": ("available", 0.7, "tempo"),
            "C": ("available", 0.7, "corroboracao"),
            "E": ("available", 0.7, "entidade"),
            "I": ("available", 0.7, "impacto"),
            "Q": ("available", 0.7, "qualidade"),
        }
        score, coverage, confidence, _ = score_features(values, contradiction=0.1)
        assert 60 <= score < 80
        assert confidence == "medium"

    def test_confianca_baixa_quando_alta_contradicao(self):
        """Contradição alta (>= 0.8) força confiança para 'low'."""
        values = {
            "A": ("available", 1.0, "anomalia"),
            "T": ("available", 1.0, "tempo"),
            "C": ("available", 1.0, "corroboracao"),
            "E": ("available", 1.0, "entidade"),
            "I": ("available", 1.0, "impacto"),
            "Q": ("available", 1.0, "qualidade"),
        }
        _, _, confidence, _ = score_features(values, contradiction=0.85)
        assert confidence == "low"
