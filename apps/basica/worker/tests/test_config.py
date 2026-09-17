"""Testes unitários de carregamento de configuração em ``argus_worker.config``.

Unidades testadas:
  - Função _env_int: leitura resiliente de inteiros de variáveis de ambiente
  - Método Config.from_env: validação de modo ('merge' vs 'event'), seleção de prefixos de fila
    e delimitação de batch_size (clamping a SQS_MAX_MESSAGES).
"""

from __future__ import annotations

import os
import pytest

from argus_worker.config import SQS_MAX_MESSAGES, Config, _env_int


# ── TU-WRK-06 — _env_int e Config.from_env ─────────────────────────────────


class TestWorkerConfig:
    """Verifica a interpretação de variáveis de ambiente e validação do Config."""

    def test_env_int_retorna_padrao_quando_ausente_ou_vazio(self, monkeypatch):
        """Variável ausente ou em branco devolve o valor default."""
        monkeypatch.delenv("VAR_TESTE", raising=False)
        assert _env_int("VAR_TESTE", 42) == 42

        monkeypatch.setenv("VAR_TESTE", "   ")
        assert _env_int("VAR_TESTE", 99) == 99

    def test_env_int_converte_valor_valido(self, monkeypatch):
        """Variável com número inteiro válido é convertida com sucesso."""
        monkeypatch.setenv("VAR_TESTE", "123")
        assert _env_int("VAR_TESTE", 10) == 123

    def test_env_int_lanca_erro_quando_valor_invalido(self, monkeypatch):
        """Valor não numérico levanta ValueError informativo."""
        monkeypatch.setenv("VAR_TESTE", "nao_sou_numero")
        with pytest.raises(ValueError, match="VAR_TESTE precisa ser inteiro"):
            _env_int("VAR_TESTE", 10)

    def test_from_env_rejeita_modo_desconhecido(self):
        """Modo diferente de 'merge' ou 'event' deve levantar ValueError."""
        with pytest.raises(ValueError, match="modo desconhecido: 'invalido'"):
            Config.from_env("invalido")

    def test_from_env_lanca_erro_quando_faltam_variaveis_obrigatorias(self, monkeypatch):
        """Ausência de filas ou banco levanta RuntimeError listando as variáveis faltantes."""
        monkeypatch.delenv("CHANGES_QUEUE_URL", raising=False)
        monkeypatch.delenv("CHANGES_DLQ_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)

        with pytest.raises(RuntimeError, match="variaveis de ambiente obrigatorias ausentes"):
            Config.from_env("merge")

    def test_from_env_carrega_modo_merge_com_prefixo_changes(self, monkeypatch):
        """Modo 'merge' lê CHANGES_QUEUE_URL e CHANGES_DLQ_URL."""
        monkeypatch.setenv("CHANGES_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/changes")
        monkeypatch.setenv("CHANGES_DLQ_URL", "https://sqs.us-east-1.amazonaws.com/123/changes-dlq")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")

        cfg = Config.from_env("merge")
        assert cfg.modo == "merge"
        assert cfg.queue_url == "https://sqs.us-east-1.amazonaws.com/123/changes"
        assert cfg.dlq_url == "https://sqs.us-east-1.amazonaws.com/123/changes-dlq"
        assert cfg.batch_size == SQS_MAX_MESSAGES

    def test_from_env_carrega_modo_event_com_prefixo_events(self, monkeypatch):
        """Modo 'event' lê EVENTS_QUEUE_URL e EVENTS_DLQ_URL."""
        monkeypatch.setenv("EVENTS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/events")
        monkeypatch.setenv("EVENTS_DLQ_URL", "https://sqs.us-east-1.amazonaws.com/123/events-dlq")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")

        cfg = Config.from_env("event")
        assert cfg.modo == "event"
        assert cfg.queue_url == "https://sqs.us-east-1.amazonaws.com/123/events"
        assert cfg.dlq_url == "https://sqs.us-east-1.amazonaws.com/123/events-dlq"

    def test_from_env_limita_batch_size_ao_maximo_do_sqs(self, monkeypatch):
        """batch_size maior que SQS_MAX_MESSAGES (10) é limitado a 10."""
        monkeypatch.setenv("CHANGES_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/changes")
        monkeypatch.setenv("CHANGES_DLQ_URL", "https://sqs.us-east-1.amazonaws.com/123/changes-dlq")
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/db")
        monkeypatch.setenv("SQS_BATCH_SIZE", "50")  # Tenta pedir 50

        cfg = Config.from_env("merge")
        assert cfg.batch_size == SQS_MAX_MESSAGES  # Travado em 10
