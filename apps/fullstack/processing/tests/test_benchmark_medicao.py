"""Confere estatísticas e leitura do pico residente usadas no relatório."""

import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    return (
        importlib.import_module("benchmarks.medicao.executar"),
        importlib.import_module("benchmarks.medicao.sistema"),
    )


def test_p95_usa_nearest_rank_e_mediana_usa_dois_centrais(modules):
    executar, _ = modules
    samples = [i * 1_000_000 for i in range(20, 0, -1)]
    result = executar.resumo(samples)
    assert result == {"median_ms": 10.5, "p95_ms": 19.0, "min_ms": 1.0, "max_ms": 20.0}
    assert samples[0] == 20_000_000


def test_memoria_residente_e_afinidade_disponiveis(modules):
    _, sistema = modules
    if os.name != "nt" and not Path("/proc/self/status").exists():
        pytest.skip("Leitura nativa disponível em Windows/Linux")
    assert sistema.pico_rss(os.getpid()) > 0
    assert 0 <= sistema.cpu_disponivel() < os.cpu_count()
