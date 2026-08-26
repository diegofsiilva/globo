"""Emissor de change events para POST /v1/changes.

Pela REDE, e nao por INSERT direto no banco. E a decisao central deste servico.

Escrever direto na bronze seria mais simples e mais rapido, e nao provaria nada:
o caminho de ingestao (API Gateway -> SQS -> merge worker -> change_log ->
MERGE) ficaria exercitado apenas no dia da apresentacao. Emitindo por HTTP, cada
tick do simulador testa o fluxo inteiro -- inclusive o que acontece quando a
fila acumula, quando o worker cai, e quando a mesma mensagem e reentregue.
"""

from __future__ import annotations

import datetime as dt
import json
import logging

import httpx

log = logging.getLogger(__name__)

# Teto de BYTES por POST, e nao de linhas.
#
# A conta original era por contagem (500 linhas) mirando o limite de 256 KB do
# SQS. Errado por dois motivos. O primeiro e que as 33 tabelas tem larguras
# muito diferentes: 500 linhas de `signal_bucket` sao alguns KB, 500 de
# `operation_metrics` passam de 300 KB.
#
# O segundo e o que realmente quebrou em producao. A integracao do API Gateway e
# `SQS-SendMessage` com `MessageBody = "$request.body"`, ou seja, o corpo inteiro
# viaja na QUERY STRING da chamada ao SQS. O limite que vale nao e o de 256 KB do
# SQS, e o de tamanho de URI -- bem menor. Lotes grandes voltavam
# `414 Request-URI Too Large`, as tres tentativas falhavam e o lote era
# DESCARTADO: perda silenciosa de mudanca.
#
# 48 KB deixa margem confortavel para o escape de percent-encoding, que pode
# quase triplicar bytes nao-ASCII (nomes de time, competicao) na URI.
TETO_DO_CORPO_BYTES = 48 * 1024

# Teto de seguranca por contagem, para o caso de linhas minusculas: um POST com
# dezenas de milhares de itens ficaria lento no worker do outro lado.
TETO_DE_ITENS = 500


def _blocos(changes: list[dict]) -> list[list[dict]]:
    """Divide os change events em lotes que cabem num POST.

    Corta por BYTES do JSON serializado, e nao por contagem: e o tamanho do corpo
    que a integracao do API Gateway limita, e as tabelas do dataset tem larguras
    que variam em uma ordem de grandeza.

    Um unico change event maior que o teto vai sozinho no seu lote, e nao e
    descartado aqui -- quem recusa (ou aceita) e a API, e a decisao de descartar
    fica num lugar so.

    Args:
        changes (list[dict]): Change events ja montados.

    Returns:
        list[list[dict]]: Lotes na ordem original.
    """
    lotes: list[list[dict]] = []
    atual: list[dict] = []
    bytes_atuais = 0

    for change in changes:
        tamanho = len(json.dumps(change, ensure_ascii=False, default=str).encode())
        estouraria = bytes_atuais + tamanho > TETO_DO_CORPO_BYTES
        if atual and (estouraria or len(atual) >= TETO_DE_ITENS):
            lotes.append(atual)
            atual, bytes_atuais = [], 0
        atual.append(change)
        bytes_atuais += tamanho

    if atual:
        lotes.append(atual)
    return lotes


class Emitter:
    """Publica change events na API de ingestao."""

    def __init__(self, url: str, *, timeout: float = 20.0, tentativas: int = 3) -> None:
        """Inicializa o emissor.

        Args:
            url (str): URL completa de POST /v1/changes.
            timeout (float): Timeout de cada requisicao, em segundos.
            tentativas (int): Tentativas por lote antes de desistir.
        """
        self._url = url
        self._tentativas = tentativas
        # Cliente reaproveitado entre ticks: reabrir a conexao TLS a cada POST
        # custaria mais handshake do que envio.
        self._client = httpx.Client(
            timeout=timeout, headers={"content-type": "application/json"}
        )

    def emitir(
        self,
        tabela: str,
        linhas: list[dict],
        pk: list[str],
        captured_at: dt.datetime,
        run_id: int,
    ) -> int:
        """Emite as linhas como change events.

        Args:
            tabela (str): Tabela de origem.
            linhas (list[dict]): Linhas ja lidas da bronze (e ja distorcidas
                pelas falhas, se alguma alcancou).
            pk (list[str]): Colunas da chave primaria.
            captured_at (datetime): Instante VIRTUAL em que a origem observou a
                mudanca. Virtual e nao de parede: e ele que o `lag_sim` compara
                com `sim.now()`, e um relogio de parede aqui tornaria a metrica
                sem sentido.
            run_id (int): Execucao do simulador que produziu estes eventos.

        Returns:
            int: Quantos change events foram aceitos.
        """
        changes = [
            {
                "source_table": tabela,
                # `u` e nao `i`: a linha ja existe na bronze (veio da carga
                # inicial). O que o simulador reemite e a OBSERVACAO dela
                # chegando de novo pelo fluxo, e a regra do `_lsn` maior
                # trata isso corretamente de qualquer forma.
                "op": "u",
                "pk": {k: linha[k] for k in pk},
                "after": linha,
                "captured_at": captured_at.isoformat(),
                "run_id": run_id,
            }
            for linha in linhas
        ]

        enviados = 0
        for bloco in _blocos(changes):
            if self._post({"changes": bloco}):
                enviados += len(bloco)
        return enviados

    def _post(self, corpo: dict) -> bool:
        """Envia um lote, com retry.

        Args:
            corpo (dict): Corpo do POST.

        Returns:
            bool: True se a API aceitou.
        """
        for tentativa in range(self._tentativas):
            try:
                resposta = self._client.post(self._url, json=corpo)
                if resposta.status_code < 300:
                    return True
                log.warning(
                    "a API recusou o lote",
                    extra={
                        "status": resposta.status_code,
                        "tentativa": tentativa,
                        "corpo": resposta.text[:200],
                    },
                )
            except httpx.HTTPError:
                log.warning(
                    "falha de rede ao emitir",
                    extra={"tentativa": tentativa},
                    exc_info=True,
                )

        # Desistir e perder este lote de proposito. O simulador reemite um dump
        # que continua inteiro no banco -- e melhor pular uma janela e seguir o
        # relogio do que travar o tempo virtual tentando reenviar. Travar faria
        # TODAS as telas pararem por causa de uma falha de rede pontual.
        log.error("lote descartado apos esgotar as tentativas")
        return False

    def close(self) -> None:
        """Fecha o cliente HTTP."""
        self._client.close()
