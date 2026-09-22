"""Testes unitários do módulo ``argus_simulator.faults``.

Unidades testadas:
  - Classe Falha:
      - Método Falha.alcanca: verificação de janela temporal e correspondência de alvos
      - Método Falha.aplicar: cálculo de distorção por multiplicador ou apagão (outage)
  - Função sortear: geração pseudo-aleatória determinística a partir de semente (seed)
  - Função _params: sorteio de parâmetros dentro dos intervalos por tipo de falha
"""

from __future__ import annotations

import datetime as dt
import random

from argus_simulator.faults import Falha, _params, sortear

# ── TU-SIM-01 — Falha.alcanca ──────────────────────────────────────────────


class TestFalhaAlcanca:
    """Verifica a lógica de alcance temporal e filtragem de alvos da classe Falha."""

    def setup_method(self):
        self.t_start = dt.datetime(2026, 7, 12, 10, 0, 0, tzinfo=dt.UTC)
        self.t_end = dt.datetime(2026, 7, 12, 11, 0, 0, tzinfo=dt.UTC)

    def test_deve_alcancar_quando_dentro_da_janela_e_alvo_exato(self):
        """Alcança o ponto dentro da janela quando o alvo corresponde."""
        falha = Falha(
            kind="error_spike",
            target={"source": "npaw", "entity": "live_stream", "metric": "buffer_ratio"},
            ts_start=self.t_start,
            ts_end=self.t_end,
            params={"multiplicador": 5.0},
        )
        ts_dentro = dt.datetime(2026, 7, 12, 10, 30, 0, tzinfo=dt.UTC)
        assert falha.alcanca(ts_dentro, "npaw", "live_stream", "buffer_ratio") is True

    def test_deve_alcancar_no_limite_inicial_exato(self):
        """Limite inferior inclusivo: ts == ts_start deve alcançar."""
        falha = Falha(
            kind="latency",
            target={"source": "npaw"},
            ts_start=self.t_start,
            ts_end=self.t_end,
            params={},
        )
        assert falha.alcanca(self.t_start, "npaw", "qualquer", "qualquer") is True

    def test_nao_deve_alcancar_no_limite_final_exato(self):
        """Limite superior exclusivo: ts == ts_end não deve alcançar."""
        falha = Falha(
            kind="latency",
            target={"source": "npaw"},
            ts_start=self.t_start,
            ts_end=self.t_end,
            params={},
        )
        assert falha.alcanca(self.t_end, "npaw", "qualquer", "qualquer") is False

    def test_nao_deve_alcancar_fora_da_janela_temporal(self):
        """Ponto antes ou depois do intervalo temporal da falha."""
        falha = Falha(
            kind="latency",
            target={"source": "npaw"},
            ts_start=self.t_start,
            ts_end=self.t_end,
            params={},
        )
        ts_antes = dt.datetime(2026, 7, 12, 9, 59, 59, tzinfo=dt.UTC)
        ts_depois = dt.datetime(2026, 7, 12, 11, 0, 1, tzinfo=dt.UTC)
        assert falha.alcanca(ts_antes, "npaw", "qualquer", "qualquer") is False
        assert falha.alcanca(ts_depois, "npaw", "qualquer", "qualquer") is False

    def test_deve_tratar_campos_ausentes_no_target_como_coringas(self):
        """Trata campos ausentes no alvo como coringas."""
        falha = Falha(
            kind="source_outage",
            target={"source": "prometheus"},
            ts_start=self.t_start,
            ts_end=self.t_end,
            params={},
        )
        ts = dt.datetime(2026, 7, 12, 10, 15, 0, tzinfo=dt.UTC)
        assert falha.alcanca(ts, "prometheus", "pod-1", "cpu_usage") is True
        assert falha.alcanca(ts, "prometheus", "node-9", "memory_rss") is True
        # Fonte diferente deve falhar
        assert falha.alcanca(ts, "npaw", "pod-1", "cpu_usage") is False

    def test_nao_deve_alcancar_quando_entidade_ou_metrica_divergirem(self):
        """Caso de incompatibilidade de entidade ou métrica."""
        falha = Falha(
            kind="error_spike",
            target={"source": "npaw", "entity": "vod", "metric": "error_rate"},
            ts_start=self.t_start,
            ts_end=self.t_end,
            params={},
        )
        ts = dt.datetime(2026, 7, 12, 10, 15, 0, tzinfo=dt.UTC)
        assert falha.alcanca(ts, "npaw", "live", "error_rate") is False
        assert falha.alcanca(ts, "npaw", "vod", "bitrate") is False


# ── TU-SIM-02 — Falha.aplicar ──────────────────────────────────────────────


class TestFalhaAplicar:
    """Verifica a distorção aplicada aos valores por tipo de falha."""

    def test_deve_retornar_none_quando_valor_original_for_none(self):
        """Valor nulo de entrada deve preservar None."""
        falha = Falha(
            "error_spike",
            {},
            dt.datetime.now(),
            dt.datetime.now(),
            {"multiplicador": 5.0},
        )
        assert falha.aplicar(None) is None

    def test_deve_retornar_none_para_source_outage(self):
        """Apagão de fonte ('source_outage') gera buraco de telemetria (None)."""
        falha = Falha("source_outage", {}, dt.datetime.now(), dt.datetime.now(), {})
        assert falha.aplicar(150.0) is None
        assert falha.aplicar(0.0) is None

    def test_deve_multiplicar_valor_conforme_parametro(self):
        """Aplica multiplicador escalar sobre o valor numérico."""
        falha = Falha(
            "error_spike",
            {},
            dt.datetime.now(),
            dt.datetime.now(),
            {"multiplicador": 4.5},
        )
        assert falha.aplicar(10.0) == 45.0
        assert falha.aplicar(0.0) == 0.0

    def test_deve_usar_multiplicador_1_como_padrao_quando_ausente(self):
        """Sem multiplicador nos parâmetros, o valor permanece inalterado (1.0)."""
        falha = Falha("drift", {}, dt.datetime.now(), dt.datetime.now(), {})
        assert falha.aplicar(42.0) == 42.0


# ── TU-SIM-03 — sortear e _params ──────────────────────────────────────────


class TestSortearEFalhasParams:
    """Verifica o sorteio determinístico e o gerador de parâmetros de falha."""

    def test_sortear_e_estritamente_deterministico_com_mesma_seed(self):
        """Mesma semente deve gerar a mesma quantidade e sequência idêntica de falhas."""
        t0 = dt.datetime(2026, 7, 12, 0, 0, 0, tzinfo=dt.UTC)
        t1 = dt.datetime(2026, 7, 12, 12, 0, 0, tzinfo=dt.UTC)
        fontes = ["npaw", "prometheus", "rpaas"]

        falhas_1 = sortear(seed=42, t0=t0, t1=t1, fontes=fontes, quantas=4)
        falhas_2 = sortear(seed=42, t0=t0, t1=t1, fontes=fontes, quantas=4)

        assert len(falhas_1) == 4
        assert len(falhas_2) == 4
        for f1, f2 in zip(falhas_1, falhas_2, strict=True):
            assert f1.kind == f2.kind
            assert f1.target == f2.target
            assert f1.ts_start == f2.ts_start
            assert f1.ts_end == f2.ts_end
            assert f1.params == f2.params

    def test_sortear_com_seeds_diferentes_gera_cenarios_distintos(self):
        """Sementes diferentes devem gerar sequências de falhas distintas."""
        t0 = dt.datetime(2026, 7, 12, 0, 0, 0, tzinfo=dt.UTC)
        t1 = dt.datetime(2026, 7, 12, 12, 0, 0, tzinfo=dt.UTC)
        fontes = ["npaw", "prometheus", "rpaas"]

        falhas_a = sortear(seed=101, t0=t0, t1=t1, fontes=fontes, quantas=5)
        falhas_b = sortear(seed=202, t0=t0, t1=t1, fontes=fontes, quantas=5)

        assert [f.ts_start for f in falhas_a] != [f.ts_start for f in falhas_b]

    def test_sortear_retorna_falhas_ordenadas_por_ts_start(self):
        """As falhas retornadas devem vir ordenadas cronologicamente por ts_start."""
        t0 = dt.datetime(2026, 7, 12, 0, 0, 0, tzinfo=dt.UTC)
        t1 = dt.datetime(2026, 7, 12, 23, 59, 59, tzinfo=dt.UTC)
        fontes = ["npaw", "prometheus"]

        falhas = sortear(seed=999, t0=t0, t1=t1, fontes=fontes, quantas=10)
        for i in range(len(falhas) - 1):
            assert falhas[i].ts_start <= falhas[i + 1].ts_start

    def test_sortear_com_lista_de_fontes_vazia_retorna_vazio(self):
        """Sem fontes candidatas, deve retornar lista vazia sem lançar exceção."""
        t0 = dt.datetime(2026, 7, 12, 0, 0, 0, tzinfo=dt.UTC)
        t1 = dt.datetime(2026, 7, 12, 12, 0, 0, tzinfo=dt.UTC)
        assert sortear(seed=1, t0=t0, t1=t1, fontes=[], quantas=5) == []

    def test_params_gera_multiplicadores_dentro_dos_intervalos_definidos(self):
        """Mantém os multiplicadores nas faixas definidas por tipo."""
        rng = random.Random(12345)

        # error_spike: [3.0, 12.0]
        params_spike = _params("error_spike", rng)
        assert 3.0 <= params_spike["multiplicador"] <= 12.0

        # latency: [1.15, 1.6]
        params_latency = _params("latency", rng)
        assert 1.15 <= params_latency["multiplicador"] <= 1.6

        # drift: [0.7, 0.9]
        params_drift = _params("drift", rng)
        assert 0.7 <= params_drift["multiplicador"] <= 0.9

        # source_outage: {}
        params_outage = _params("source_outage", rng)
        assert params_outage == {}
