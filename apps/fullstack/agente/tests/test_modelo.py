"""O cliente precisa insistir quando o servidor compartilhado nao responde."""

from __future__ import annotations

import json

import pytest

from argus_agente.modelo import ClienteOllama, ModeloIndisponivel, ler_objeto


class _Transporte:
    """Devolve as respostas de um roteiro, levantando o que for excecao."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = 0

    def __call__(self, request, *, timeout):
        item = self.respostas[self.chamadas]
        self.chamadas += 1
        if isinstance(item, Exception):
            raise item
        return _Resposta(item)


class _Resposta:
    def __init__(self, corpo: bytes) -> None:
        self.corpo = corpo

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, quantidade: int) -> bytes:
        return self.corpo[:quantidade]


def _envelope(conteudo: str) -> bytes:
    return json.dumps({"message": {"content": conteudo}}).encode()


def _cliente(transporte):
    return ClienteOllama(
        "http://x:11434",
        "m",
        timeout_seconds=1,
        opener=transporte,
        espera=lambda _s: None,
    )


def test_timeout_na_primeira_tentativa_e_refeito():
    transporte = _Transporte(
        [TimeoutError("fila do servidor"), _envelope('{"action": "desistir"}')]
    )
    passo = _cliente(transporte).passo([])
    assert transporte.chamadas == 2
    assert passo["action"] == "desistir"


def test_servidor_fora_do_ar_falha_depois_das_tentativas():
    transporte = _Transporte([TimeoutError("fila"), TimeoutError("fila")])
    with pytest.raises(ModeloIndisponivel, match="2 tentativa"):
        _cliente(transporte).passo([])
    assert transporte.chamadas == 2


def test_cerca_de_codigo_nao_invalida_um_passo_bem_formado():
    assert ler_objeto('```json\n{"action": "desistir"}\n```')["action"] == "desistir"
