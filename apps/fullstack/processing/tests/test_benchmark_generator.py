"""Garante geração repetível e verificação sem sobrescrever referências."""

import importlib
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def generator(monkeypatch):
    # O pacote de benchmark é local e não faz parte da imagem de produção.
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    return importlib.import_module("benchmarks.gerar_fixtures")


def test_gerador_reproduz_congelados_e_reinicia_ids(generator):
    first = generator.gerar()
    assert first == generator.gerar()
    for name, document in first.items():
        assert document == json.loads(
            (generator.FIXTURES / name).read_text(encoding="utf-8")
        )
        assert document["source_files_sha256"]


def test_check_detecta_divergencia_sem_sobrescrever(tmp_path, monkeypatch, generator):
    path = tmp_path / "cargas_v1.json"
    path.write_text('{"divergente": true}\n', encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["gerar_fixtures", "--check", "--output-dir", str(tmp_path)]
    )
    with pytest.raises(SystemExit, match="Fixtures divergentes"):
        generator.main()
    assert path.read_text(encoding="utf-8") == '{"divergente": true}\n'
    assert list(tmp_path.iterdir()) == [path]
