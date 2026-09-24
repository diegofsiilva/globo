"""Ciclo de vida do container: heartbeat e encerramento gracioso.

Os dois mecanismos existem para o mesmo fim -- que o ECS saiba a verdade sobre o
processo -- mas resolvem lados opostos: o heartbeat diz "estou vivo" quando nao
ha trabalho, e o SIGTERM garante que sair nao largue trabalho pela metade.
"""

from __future__ import annotations

import logging
import signal
import time
from pathlib import Path

log = logging.getLogger(__name__)


class Heartbeat:
    """Marca vida para o HEALTHCHECK do container."""

    def __init__(self, path: str) -> None:
        """Inicializa o heartbeat.

        Args:
            path (str): Arquivo tocado a cada batida. O healthcheck da task
                definition compara a mtime dele com o relogio.
        """
        self._path = Path(path)

    def touch(self) -> None:
        """Bate o heartbeat.

        Precisa ser chamado a CADA ciclo, inclusive quando nao ha trabalho: fila
        vazia nao pode ser confundida com processo travado. Um worker saudavel
        num domingo de madrugada seria morto em laco se o heartbeat so batesse
        quando houvesse mensagem.

        Falha de escrita nao derruba o servico -- disco cheio em /tmp e um
        problema, mas parar de ingerir dado por causa dele e um problema pior.
        """
        try:
            self._path.write_text(str(int(time.time())), encoding="utf-8")
        except OSError:
            log.warning("nao consegui escrever o heartbeat", exc_info=True)


class ShutdownSignal:
    """Encerramento gracioso: SIGTERM encerra apos o ciclo atual."""

    def __init__(self) -> None:
        """Instala os tratadores de sinal."""
        self._running = True
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._request_stop)

    def _request_stop(self, signum, _frame) -> None:
        """Marca o pedido de parada.

        Args:
            signum: Numero do sinal recebido.
            _frame: Frame de execucao (ignorado).
        """
        log.info(
            "sinal recebido, encerrando apos o ciclo atual", extra={"signal": signum}
        )
        self._running = False

    @property
    def running(self) -> bool:
        """Indica se o laco principal deve continuar.

        Returns:
            bool: False depois de SIGTERM ou SIGINT.
        """
        return self._running

    def sleep(self, seconds: float, step: float = 0.5) -> None:
        """Dorme, mas acorda cedo se o encerramento for pedido.

        `time.sleep(30)` faria o container ignorar o SIGTERM por ate 30
        segundos, e o ECS mata a forca depois de 30. O resultado seria um
        encerramento que parece gracioso no codigo e e um SIGKILL na pratica.

        Args:
            seconds (float): Quanto dormir no total.
            step (float): De quanto em quanto tempo checar o sinal.
        """
        fim = time.monotonic() + seconds
        while self._running and time.monotonic() < fim:
            time.sleep(min(step, fim - time.monotonic()))
