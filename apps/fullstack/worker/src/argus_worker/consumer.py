"""Laco de consumo: SQS -> validacao -> PostgreSQL.

Uma classe base com o ciclo do SQS (que e identico nos dois workers) e duas
subclasses com o que muda: o que e uma mensagem valida e onde ela e gravada.

Garantias, iguais as da v2 e pelos mesmos motivos:

  - At-least-once na entrega (SQS) + escrita idempotente = efeito de
    exactly-once. No merge worker a idempotencia vem da regra do `_lsn` maior
    (SQL, 010_merge_e_etl.sql); no event worker, do id derivado do conteudo
    somado ao ON CONFLICT DO NOTHING.
  - Mensagem so e apagada da fila depois que TUDO nela foi gravado ou desviado
    para a DLQ. Falha de escrita segura o delete, o SQS devolve a mensagem e o
    redrive tenta de novo.
  - Payload que nunca vai funcionar (JSON quebrado, envelope invalido, tamanho
    absurdo) vai direto para a DLQ com o motivo anexado, em vez de queimar as 5
    tentativas do redrive para chegar no mesmo lugar.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import psycopg
from botocore.exceptions import ClientError
from pydantic import ValidationError

from .changes import parse_change
from .config import Config
from .keys import build_row
from .models import parse_event
from .repository import ChangeTooLarge, check_size

log = logging.getLogger(__name__)


class BaseConsumer(ABC):
    """Ciclo do SQS, comum aos dois workers."""

    def __init__(
        self, *, config: Config, sqs_client, metrics, heartbeat, shutdown
    ) -> None:
        """Inicializa o consumidor.

        Args:
            config (Config): Configuracao do worker.
            sqs_client: Cliente boto3 para SQS.
            metrics (argus_common.Metrics): Coletor de metricas.
            heartbeat (argus_common.Heartbeat): Marcador de vida.
            shutdown (argus_common.ShutdownSignal): Sinalizador de encerramento.
        """
        self._config = config
        self._sqs = sqs_client
        self._metrics = metrics
        self._heartbeat = heartbeat
        self._shutdown = shutdown

    # ----------------------------------------------------------------- #
    # O que cada worker define
    # ----------------------------------------------------------------- #

    @abstractmethod
    def _parse(self, raw: dict[str, Any]) -> Any:
        """Valida um item cru e devolve a forma pronta para gravar.

        Args:
            raw (dict[str, Any]): Item cru vindo da fila.

        Returns:
            Any: Item validado.
        """

    @abstractmethod
    def _persist(self, itens: list[Any]) -> int:
        """Grava os itens validados.

        Args:
            itens (list[Any]): Itens ja validados.

        Returns:
            int: Quantos foram efetivamente gravados.
        """

    @property
    @abstractmethod
    def _chave_lista(self) -> str:
        """Nome do campo que envelopa a lista no corpo do POST.

        Returns:
            str: `changes` ou `events`.
        """

    # ----------------------------------------------------------------- #
    # Ciclo de vida
    # ----------------------------------------------------------------- #

    def run(self) -> None:
        """Consome a fila ate receber um sinal de parada.

        Nenhuma excecao de ciclo derruba o worker. Como as mensagens so sao
        apagadas depois da gravacao, uma falha aqui apenas deixa o visibility
        timeout expirar e o SQS reentregar -- o que a idempotencia da escrita
        torna seguro.
        """
        log.info(
            "worker iniciado",
            extra={
                "modo": self._config.modo,
                "queue_url": self._config.queue_url,
                "batch_size": self._config.batch_size,
            },
        )
        while self._shutdown.running:
            try:
                self.run_once()
            except psycopg.Error:
                # Banco fora do ar, failover, pool esgotado. Nao apagamos nada,
                # entao as mensagens voltam a ficar visiveis sozinhas.
                log.error("erro de banco no ciclo, seguindo", exc_info=True)
                self._metrics.count("CycleErrors")
                self._shutdown.sleep(2.0)
            except ClientError:
                log.error("erro de AWS no ciclo, seguindo", exc_info=True)
                self._metrics.count("CycleErrors")
                self._shutdown.sleep(1.0)
            except Exception:
                log.exception("erro inesperado no ciclo, seguindo")
                self._metrics.count("CycleErrors")
                self._shutdown.sleep(1.0)
            finally:
                self._metrics.flush()
        log.info("worker encerrado")

    def run_once(self) -> int:
        """Processa um lote.

        Returns:
            int: Quantos itens foram gravados.
        """
        espera_iniciou = time.monotonic()
        mensagens = self._receive()
        # O cronometro de CycleLatency comeca AQUI, depois do receive. O long
        # polling bloqueia ate 20s esperando mensagem, e incluir essa espera
        # ociosa faria a metrica reportar "13s de latencia" quando o
        # processamento real levou 400ms -- numero que assusta a toa no painel.
        iniciou = time.monotonic()
        self._metrics.duration_ms("PollWait", (iniciou - espera_iniciou) * 1000)
        self._heartbeat.touch()

        if not mensagens:
            return 0

        self._metrics.count("MessagesReceived", len(mensagens))

        itens: list[Any] = []
        # De qual mensagem SQS veio cada item, alinhado por indice. So serve para
        # a quarentena: sem isso, um item recusado pelo banco iria para a DLQ sem
        # dizer de que mensagem saiu, e ninguem conseguiria rastrear a origem.
        origens: list[str] = []
        resolvidas: list[dict[str, Any]] = []
        pendentes: list[dict[str, Any]] = []

        for mensagem in mensagens:
            desta, fatal = self._process_message(mensagem)
            if fatal:
                # Nao conseguimos nem desviar para a DLQ: deixa a mensagem
                # voltar para a fila em vez de perder o dado.
                continue
            if desta:
                itens.extend(desta)
                origens.extend([mensagem["MessageId"]] * len(desta))
                pendentes.append(mensagem)
            else:
                # Tudo que tinha nessa mensagem foi para a DLQ: ja resolvida.
                resolvidas.append(mensagem)

        gravados = 0
        if itens:
            try:
                gravados = self._persist(itens)
            except psycopg.Error as exc:
                if not _registro_recusado(exc):
                    # Banco fora do ar, pool esgotado, failover. As mensagens
                    # ficam na fila inteiras -- nao ha gravacao parcial a
                    # compensar, append e MERGE estao na mesma transacao.
                    log.error(
                        "falha ao gravar o lote, mensagens ficam na fila", exc_info=True
                    )
                    self._metrics.count("WriteFailed", len(itens))
                    self._delete(resolvidas)
                    raise
                # Um registro do lote violou uma restricao. Devolver o lote
                # inteiro para a fila faria a reentrega repetir a mesma falha
                # para sempre: o veneno paralisaria TODA a ingestao de mudancas,
                # e nao so o registro ruim. Ja aconteceu -- um unico change event
                # malformado travou o pipeline e derrubou o worker.
                log.warning(
                    "o banco recusou algum registro do lote, isolando um a um",
                    exc_info=True,
                )
                gravados = self._persist_isolando(itens, origens)
            resolvidas.extend(pendentes)

        if gravados:
            self._metrics.count("ItemsWritten", gravados)
        duplicados = len(itens) - gravados
        if duplicados > 0:
            # Taxa de reentrega do SQS: util para saber se o visibility timeout
            # esta curto demais para o tempo de processamento.
            self._metrics.count("ItemsDeduplicated", duplicados)

        self._delete(resolvidas)
        self._metrics.duration_ms("CycleLatency", (time.monotonic() - iniciou) * 1000)
        return gravados

    # ----------------------------------------------------------------- #
    # Etapas
    # ----------------------------------------------------------------- #

    def _receive(self) -> list[dict[str, Any]]:
        """Recebe um lote de mensagens da fila.

        Returns:
            list[dict[str, Any]]: Mensagens retornadas pelo SQS.
        """
        resposta = self._sqs.receive_message(
            QueueUrl=self._config.queue_url,
            MaxNumberOfMessages=self._config.batch_size,
            WaitTimeSeconds=self._config.wait_time_seconds,
            VisibilityTimeout=self._config.visibility_timeout_seconds,
            MessageAttributeNames=["All"],
            AttributeNames=["ApproximateReceiveCount", "SentTimestamp"],
        )
        return resposta.get("Messages", [])

    def _process_message(self, mensagem: dict[str, Any]) -> tuple[list[Any], bool]:
        """Valida o conteudo de uma mensagem.

        Args:
            mensagem (dict[str, Any]): Mensagem crua do SQS.

        Returns:
            tuple[list[Any], bool]: Itens validados e se houve falha fatal
                (nao conseguimos nem quarentenar).
        """
        message_id = mensagem["MessageId"]

        try:
            crus = _extract(mensagem.get("Body", ""), self._chave_lista)
        except ValueError as exc:
            ok = self._quarantine(mensagem.get("Body", ""), str(exc), message_id)
            return [], not ok

        self._metrics.count("ItemsReceived", len(crus))

        itens: list[Any] = []
        for cru in crus:
            try:
                itens.append(self._parse(cru))
            except (ValidationError, ValueError, TypeError, ChangeTooLarge) as exc:
                if self._quarantine(cru, f"validacao: {exc}", message_id):
                    self._metrics.count("ItemsQuarantined")
                    continue
                return [], True
        return itens, False

    def _persist_isolando(self, itens: list[Any], origens: list[str]) -> int:
        """Grava um a um, mandando para a DLQ o que o banco recusar.

        So e chamado depois que o lote inteiro falhou por violacao de restricao.
        E caro -- uma transacao por item -- e de proposito: o caso comum e o lote
        passar inteiro, e este caminho existe para que UM registro ruim custe uma
        passada lenta em vez de paralisar a fila.

        Args:
            itens (list[Any]): Itens validados do lote.
            origens (list[str]): Id da mensagem SQS de cada item, por indice.

        Returns:
            int: Quantos foram gravados.
        """
        gravados = 0
        for item, message_id in zip(itens, origens, strict=True):
            try:
                gravados += self._persist([item])
            except psycopg.Error as exc:
                if not _registro_recusado(exc):
                    # Parou de ser problema do dado e virou problema do banco no
                    # meio da varredura: para aqui e deixa o resto na fila.
                    raise
                self._quarantine(_serializavel(item), f"banco recusou: {exc}", message_id)
                self._metrics.count("ItemsQuarantined")
        return gravados

    def _quarantine(self, payload: Any, motivo: str, message_id: str) -> bool:
        """Manda o payload para a DLQ com o motivo anexado.

        Args:
            payload (Any): Dado original que falhou.
            motivo (str): Descricao da falha.
            message_id (str): Id da mensagem SQS de origem.

        Returns:
            bool: False se nem a DLQ funcionou -- ai a mensagem volta para a
                fila em vez de o dado ser perdido.
        """
        corpo = (
            payload
            if isinstance(payload, str)
            else json.dumps(payload, ensure_ascii=False, default=str)
        )
        try:
            self._sqs.send_message(
                QueueUrl=self._config.dlq_url,
                MessageBody=corpo,
                MessageAttributes={
                    "FailureReason": {"DataType": "String", "StringValue": motivo[:250]},
                    "SourceMessageId": {"DataType": "String", "StringValue": message_id},
                },
            )
        except ClientError:
            log.error(
                "falha ao enviar para a DLQ, mensagem volta para a fila",
                extra={"message_id": message_id, "reason": motivo},
                exc_info=True,
            )
            return False

        log.warning(
            "item desviado para a DLQ",
            extra={"message_id": message_id, "reason": motivo},
        )
        return True

    def _delete(self, mensagens: list[dict[str, Any]]) -> None:
        """Apaga em lotes as mensagens ja processadas.

        Args:
            mensagens (list[dict[str, Any]]): Mensagens a apagar.
        """
        if not mensagens:
            return
        # DeleteMessageBatch aceita 10 por chamada -- o mesmo teto do receive,
        # entao na pratica e sempre uma chamada so.
        for inicio in range(0, len(mensagens), 10):
            bloco = mensagens[inicio : inicio + 10]
            resposta = self._sqs.delete_message_batch(
                QueueUrl=self._config.queue_url,
                Entries=[
                    {"Id": str(i), "ReceiptHandle": m["ReceiptHandle"]}
                    for i, m in enumerate(bloco)
                ],
            )
            falhas = resposta.get("Failed", [])
            if falhas:
                # Nao e perda de dado: sem o delete, o SQS reentrega e a escrita
                # idempotente absorve a repeticao.
                log.warning(
                    "falha ao apagar mensagens da fila",
                    extra={"failed": len(falhas)},
                )
                self._metrics.count("DeleteFailed", len(falhas))
            self._metrics.count("MessagesDeleted", len(bloco) - len(falhas))


class ChangeConsumer(BaseConsumer):
    """Merge worker: change events -> bronze.change_log -> MERGE na corrente."""

    _chave_lista = "changes"
    METRICS_INTERVAL_SECONDS = 60.0

    def __init__(self, *, repository, **kwargs) -> None:
        """Inicializa o merge worker.

        Args:
            repository (ChangeRepository): Repositorio do log e do MERGE.
            **kwargs: Repassados a BaseConsumer.
        """
        super().__init__(**kwargs)
        self._repo = repository
        self._ultimo_lag = 0.0

    def run_once(self) -> int:
        """Processa um lote e mantem as metricas vivas mesmo com fila vazia.

        LagSimSeconds tinha `treat_missing_data = breaching` no alarme, mas era
        emitida apenas dentro de `_persist`. Uma fila legitimamente ociosa
        portanto alarmava como pipeline quebrado. A cadencia evita pagar as
        consultas de observabilidade a cada long poll de 20 segundos.

        Returns:
            int: Quantos changes foram gravados.
        """
        gravados = super().run_once()
        self._emit_lag_if_due()
        return gravados

    def _parse(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Valida um change event.

        Args:
            raw (dict[str, Any]): Change event cru.

        Returns:
            dict[str, Any]: Change event validado.
        """
        change = parse_change(raw)
        check_size(change)
        return change

    def _persist(self, itens: list[dict[str, Any]]) -> int:
        """Anexa ao log e aplica o MERGE.

        Args:
            itens (list[dict[str, Any]]): Change events validados.

        Returns:
            int: Quantos entraram no log.
        """
        no_log, tocadas = self._repo.append_and_merge(itens)
        self._metrics.count("ChangesMerged", tocadas)
        return no_log

    def _emit_lag_if_due(self) -> None:
        """Emite as metricas no maximo uma vez por minuto."""
        agora = time.monotonic()
        if agora - self._ultimo_lag < self.METRICS_INTERVAL_SECONDS:
            return
        self._ultimo_lag = agora
        self._emit_lag()

    def _emit_lag(self) -> None:
        """Emite lag_sim e o heartbeat por fonte.

        Sao as duas metricas que o alarme de §5.3 do plano consome. Rodam com
        cadencia fixa e nao a cada item: sao duas agregacoes sobre o change_log,
        e paga-las por change event faria o custo crescer com o volume.
        """
        try:
            lag = self._repo.lag_sim_seconds()
            if lag is not None:
                self._metrics.duration_ms("LagSimSeconds", lag)
            self._metrics.count("SourcesSilent", self._repo.sources_silent())
        except psycopg.Error:
            # Metrica nao pode derrubar ingestao. O alarme de lag_sim trata
            # ausencia como `breaching`, entao o silencio aqui ja alarma sozinho.
            log.warning("nao consegui medir o lag do pipeline", exc_info=True)


class EventConsumer(BaseConsumer):
    """Event worker: grain de sessao -> bronze.event."""

    _chave_lista = "events"

    def __init__(self, *, repository, **kwargs) -> None:
        """Inicializa o event worker.

        Args:
            repository (EventRepository): Repositorio de bronze.event.
            **kwargs: Repassados a BaseConsumer.
        """
        super().__init__(**kwargs)
        self._repo = repository

    def _parse(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Valida um evento de sessao e monta a linha.

        Args:
            raw (dict[str, Any]): Evento cru.

        Returns:
            dict[str, Any]: Linha pronta para bronze.event.
        """
        evento, conhecido = parse_event(raw)

        if not conhecido:
            # Tipo novo e gravado, nao descartado (RF03): o parque de TVs
            # atualiza devagar e schema estrito viraria perda de dado em massa.
            self._metrics.count("EventsUnknownType")
            log.info(
                "tipo de evento desconhecido, gravado como generico",
                extra={"event_name": evento.event_name},
            )

        if any(
            getattr(evento, nome, None) is None
            for nome in self._config.recommended_fields
        ):
            self._metrics.count("EventsIncomplete")

        return build_row(
            evento,
            ingested_at=datetime.now(UTC),
            max_clock_skew_days=self._config.max_clock_skew_days,
        )

    def _persist(self, itens: list[dict[str, Any]]) -> int:
        """Grava as linhas em bronze.event.

        Args:
            itens (list[dict[str, Any]]): Linhas montadas.

        Returns:
            int: Quantas foram inseridas.
        """
        return self._repo.put_many(itens)


# --------------------------------------------------------------------------- #
# Parsing do corpo da mensagem
# --------------------------------------------------------------------------- #


def _registro_recusado(exc: psycopg.Error) -> bool:
    """Distingue "este registro esta errado" de "o banco esta indisponivel".

    A diferenca decide o destino da mensagem. Erro de infraestrutura pede
    reentrega -- o mesmo dado vai passar quando o banco voltar. Erro de restricao
    NAO: o mesmo dado vai falhar todas as vezes, e reentregar de graca e o que
    transforma um registro ruim numa fila parada.

    `IntegrityError` cobre NOT NULL, unique e foreign key; `DataError`, valor
    fora de dominio e conversao impossivel. `ProgrammingError` fica de FORA de
    proposito: erro de sintaxe e defeito NOSSO, e mandar o dado do usuario para a
    DLQ por causa dele esconderia o bug atras de uma pilha de itens
    quarentenados.

    Args:
        exc (psycopg.Error): Erro levantado pela gravacao.

    Returns:
        bool: True se o problema esta no registro.
    """
    return isinstance(exc, psycopg.errors.IntegrityError | psycopg.errors.DataError)


def _serializavel(item: Any) -> Any:
    """Devolve o item numa forma que o `json.dumps` da quarentena aceite.

    Args:
        item (Any): Item validado (modelo pydantic ou dicionario).

    Returns:
        Any: Dicionario, quando o item for um modelo.
    """
    dump = getattr(item, "model_dump", None)
    return dump(mode="json") if callable(dump) else item


def _extract(body: str, chave: str) -> list[dict[str, Any]]:
    """Aceita as tres formas que a API pode entregar.

    O API Gateway repassa o corpo do POST cru para o SQS, entao o formato e o
    que o cliente mandou: um item, uma lista de itens, ou um envelope
    {"<chave>": [...]}.

    Args:
        body (str): Corpo da mensagem vindo do SQS.
        chave (str): Nome do campo que envelopa a lista (`changes` ou `events`).

    Returns:
        list[dict[str, Any]]: Itens extraidos.

    Raises:
        ValueError: Se o corpo for vazio, malformado ou nao contiver itens.
    """
    if not body or not body.strip():
        raise ValueError("corpo da mensagem vazio")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalido: {exc}") from exc

    if isinstance(parsed, list):
        itens = parsed
    elif isinstance(parsed, dict):
        itens = parsed[chave] if isinstance(parsed.get(chave), list) else [parsed]
    else:
        raise ValueError(f"esperava objeto ou lista, recebi {type(parsed).__name__}")

    if not itens:
        raise ValueError("nenhum item no corpo da mensagem")
    return itens
