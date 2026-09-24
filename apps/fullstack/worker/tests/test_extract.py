"""Testes unitários de extração e resiliência em ``argus_worker.consumer``.

Unidades testadas:
  - Função _extract: extração flexível de corpos SQS
  - Função _registro_recusado: classificação de erros para a DLQ
  - Função _serializavel: conversão de modelos para a quarentena
"""

from __future__ import annotations

import json

import psycopg
import pytest
from pydantic import BaseModel

from argus_worker.consumer import _extract, _registro_recusado, _serializavel

# ── TU-WRK-01 — _extract ───────────────────────────────────────────────────


class TestConsumerExtract:
    """Verifica os formatos aceitos e os erros de corpos SQS."""

    def test_deve_extrair_objeto_unico_e_empacotar_em_lista(self):
        """Caso 1: cliente envia um único objeto JSON {...} -> retorna [{...}]."""
        payload = {"event_name": "screen_view", "session_id": "sess-1"}
        body = json.dumps(payload)

        resultado = _extract(body, chave="events")
        assert resultado == [payload]

    def test_deve_extrair_lista_crua_diretamente(self):
        """Caso 2: cliente envia uma lista crua de objetos [{...}, {...}]."""
        itens = [
            {"event_name": "request", "session_id": "sess-1"},
            {"event_name": "request", "session_id": "sess-2"},
        ]
        body = json.dumps(itens)

        resultado = _extract(body, chave="events")
        assert resultado == itens

    def test_deve_extrair_envelope_com_chave_esperada(self):
        """Caso 3: cliente envia envelope {'events': [...]} ou {'changes': [...]}."""
        itens = [{"source_table": "signal_bucket", "op": "u"}]
        body = json.dumps({"changes": itens})

        resultado = _extract(body, chave="changes")
        assert resultado == itens

    def test_deve_extrair_envelope_com_objeto_unico_sob_a_chave(self):
        """Variação: envelope cujo valor da chave é um único objeto em vez de lista."""
        item = {"source_table": "signal_bucket", "op": "u"}
        body = json.dumps({"changes": item})

        resultado = _extract(body, chave="changes")
        assert resultado == [{"changes": item}]

    def test_deve_lancar_erro_quando_corpo_vazio_ou_espacos(self):
        """Erro previsto: corpo vazio ou apenas com espaços em branco."""
        with pytest.raises(ValueError, match="corpo da mensagem vazio"):
            _extract("", chave="events")

        with pytest.raises(ValueError, match="corpo da mensagem vazio"):
            _extract("   \n\t  ", chave="events")

    def test_deve_lancar_erro_quando_json_invalido(self):
        """Erro previsto: sintaxe JSON corrompida."""
        with pytest.raises(ValueError, match="JSON invalido"):
            _extract("{ chave_sem_fechar: ", chave="events")

    def test_deve_lancar_erro_quando_tipo_json_nao_for_objeto_nem_lista(self):
        """Erro previsto: JSON válido mas tipo primitivo (número, string, booleano)."""
        with pytest.raises(ValueError, match="esperava objeto ou lista, recebi int"):
            _extract("12345", chave="events")

        with pytest.raises(ValueError, match="esperava objeto ou lista, recebi str"):
            _extract('"uma string simples"', chave="events")

    def test_deve_lancar_erro_quando_lista_vazia(self):
        """Erro previsto: lista vazia [] ou envelope vazio {'events': []}."""
        with pytest.raises(ValueError, match="nenhum item no corpo da mensagem"):
            _extract("[]", chave="events")

        with pytest.raises(ValueError, match="nenhum item no corpo da mensagem"):
            _extract(json.dumps({"events": []}), chave="events")


# ── TU-WRK-02 — _registro_recusado ─────────────────────────────────────────


class TestRegistroRecusado:
    """Verifica a distinção entre erros que justificam DLQ e erros de infraestrutura."""

    def test_deve_recusar_erro_de_integridade(self):
        """IntegrityError (ex: NOT NULL, FK violada, chave duplicada) deve ir para DLQ."""
        exc = psycopg.errors.IntegrityError("violacao de chave estrangeira")
        assert _registro_recusado(exc) is True

    def test_deve_recusar_erro_de_dados(self):
        """Envia erros de dados para a DLQ."""
        exc = psycopg.errors.DataError("valor inteiro fora do limite aceito")
        assert _registro_recusado(exc) is True

    def test_nao_deve_recusar_erro_operacional_de_banco(self):
        """Reentrega erros operacionais de banco sem quarentena."""
        exc = psycopg.OperationalError("conexao perdida com o servidor")
        assert _registro_recusado(exc) is False

    def test_nao_deve_recusar_erro_de_programacao(self):
        """Não atribui um erro de programação ao dado recebido."""
        exc = psycopg.ProgrammingError("erro de sintaxe em instrucao SQL")
        assert _registro_recusado(exc) is False


# ── TU-WRK-03 — _serializavel ──────────────────────────────────────────────


class ExemploModelo(BaseModel):
    id: int
    nome: str


class TestSerializavel:
    """Verifica a conversão para formato serializável em JSON."""

    def test_deve_converter_modelo_pydantic_para_dicionario(self):
        """Modelos Pydantic chamam model_dump(mode='json')."""
        modelo = ExemploModelo(id=10, nome="teste")
        assert _serializavel(modelo) == {"id": 10, "nome": "teste"}

    def test_deve_preservar_dicionario_comum_intacto(self):
        """Dicionários comuns continuam inalterados."""
        d = {"chave": "valor", "numero": 123}
        assert _serializavel(d) == d
