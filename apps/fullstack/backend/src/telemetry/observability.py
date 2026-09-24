"""Log estruturado em JSON e correlacao de requisicoes.

Uma linha de log por requisicao, em JSON, com o mesmo `request_id` que volta no
cabecalho da resposta e que o API Gateway ja grava no seu access log. E o que
torna o RNF11 verificavel: uma falha de consulta pode ser separada de uma falha
de ingestao ou de processamento sem depender de correlacao por horario, que num
sistema com relogio virtual nem sequer bate.

Duas regras que valem para todo campo novo:

* **Nenhum token.** O valor do `Authorization` nunca entra no log, nem
  truncado, nem em hash -- um hash de token curto e reversivel por forca bruta.
  Da autorizacao so sai a *audiencia* (`dashboard` ou `ingest`), que e o que
  interessa para auditar acesso.
* **Nenhum dado pessoal.** A query string vai para o log apenas como a lista de
  NOMES dos parametros. Os valores ficam de fora porque `session_id`,
  `device_id` e `user_id` viajam por ali, e o RNF10 vale tambem para o log --
  redigir na resposta e vazar no CloudWatch nao seria redigir.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any

from flask import Flask, g, request

# Nome canonico do cabecalho de correlacao. O API Gateway nao gera este
# cabecalho sozinho; quem o envia e o cliente (dashboard, Postman, replay) ou,
# na ausencia dele, esta propria camada.
CABECALHO_REQUEST_ID = "X-Request-Id"

# O request id entra no log, e log e um formato que se le por grep. Um valor
# vindo do cliente com quebra de linha ou aspas poderia forjar uma segunda
# entrada de log inteira; este padrao e o que fecha essa porta.
FORMATO_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

# Campos que o formatter promove do `extra` do logging para o topo do JSON.
# Qualquer outro atributo do LogRecord fica de fora de proposito: promover tudo
# despejaria o estado interno do logging no CloudWatch.
CAMPOS_PROMOVIDOS = (
    "request_id",
    "route",
    "method",
    "status",
    "latency_ms",
    "audience",
    "query_keys",
    "bytes",
)


class JsonFormatter(logging.Formatter):
    """Formata cada `LogRecord` como um objeto JSON de uma linha.

    O CloudWatch Logs Insights consegue consultar campo a campo quando a
    mensagem e um JSON valido (`fields @timestamp, status, latency_ms`). Com o
    formato texto padrao a mesma consulta viraria uma expressao regular sobre a
    mensagem, que quebra na primeira vez que alguem muda a ordem das palavras.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Serializa o registro.

        Args:
            record (logging.LogRecord): Registro produzido pelo `logging`.

        Returns:
            str: Uma linha de JSON, sem quebras internas.
        """
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for campo in CAMPOS_PROMOVIDOS:
            valor = getattr(record, campo, None)
            if valor is not None:
                payload[campo] = valor
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # `default=str` para que um datetime ou Decimal que escape num `extra`
        # vire texto em vez de derrubar o proprio log.
        return json.dumps(payload, ensure_ascii=False, default=str)


def register_observability(app: Flask) -> None:
    """Liga o log estruturado e a correlacao por `X-Request-Id` na aplicacao.

    Args:
        app (Flask): Aplicacao onde os hooks de requisicao serao registrados.
    """
    _configurar_handler(app)

    @app.before_request
    def abrir_requisicao() -> None:
        """Fixa o instante inicial e resolve o identificador de correlacao."""
        g.request_id = _resolver_request_id()
        g.audiencia = _resolver_audiencia()
        # `perf_counter` e nao `time()`: a latencia e um intervalo, e um ajuste
        # de relogio no meio da requisicao produziria uma medida negativa.
        g.iniciado_em = time.perf_counter()

    @app.after_request
    def fechar_requisicao(response):
        """Devolve o `X-Request-Id` e emite a linha de log da requisicao.

        Args:
            response: Resposta que o Flask esta prestes a enviar.

        Returns:
            A mesma resposta, com o cabecalho de correlacao acrescentado.
        """
        request_id = getattr(g, "request_id", None)
        if request_id:
            response.headers[CABECALHO_REQUEST_ID] = request_id

        iniciado_em = getattr(g, "iniciado_em", None)
        latencia_ms = (
            round((time.perf_counter() - iniciado_em) * 1000, 1)
            if iniciado_em is not None
            else None
        )

        app.logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "route": request.path,
                "method": request.method,
                "status": response.status_code,
                "latency_ms": latencia_ms,
                "audience": getattr(g, "audiencia", None),
                # Só os nomes. Ver a docstring do módulo.
                "query_keys": sorted(set(request.args.keys())) or None,
                "bytes": response.calculate_content_length(),
            },
        )
        return response


def _configurar_handler(app: Flask) -> None:
    """Troca o formatter dos logs da aplicacao pelo JSON.

    Na Lambda o runtime ja instala um handler no logger raiz; substituir o
    formatter dele e o que evita duas linhas por evento -- uma em texto, do
    handler do runtime, e outra em JSON, de um handler nosso.

    Args:
        app (Flask): Aplicacao cujo logger sera reconfigurado.
    """
    formatter = JsonFormatter()
    raiz = logging.getLogger()
    if raiz.handlers:
        for handler in raiz.handlers:
            handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        raiz.addHandler(handler)

    nivel = str(app.config.get("LOG_LEVEL", "INFO")).upper()
    raiz.setLevel(nivel)
    app.logger.setLevel(nivel)
    # Sem isto o Flask emitiria a mesma linha duas vezes: uma pelo handler
    # proprio de `app.logger` e outra pelo do logger raiz.
    app.logger.handlers.clear()
    app.logger.propagate = True


def _resolver_request_id() -> str:
    """Escolhe o identificador de correlacao desta requisicao.

    Ordem de preferencia: o `X-Request-Id` que o cliente enviou (permite seguir
    um clique do dashboard ate o log), depois o `requestId` que o API Gateway
    gerou (permite cruzar com o access log do estagio) e, por ultimo, um UUID
    novo, para quando a API roda fora da AWS.

    Returns:
        str: Identificador validado contra `FORMATO_REQUEST_ID`.
    """
    do_cliente = request.headers.get(CABECALHO_REQUEST_ID, "")
    if FORMATO_REQUEST_ID.match(do_cliente):
        return do_cliente

    contexto = _contexto_do_gateway()
    do_gateway = str(contexto.get("requestId", ""))
    if FORMATO_REQUEST_ID.match(do_gateway):
        return do_gateway

    return str(uuid.uuid4())


def _resolver_audiencia() -> str | None:
    """Le a audiencia que o Lambda authorizer anexou ao contexto da requisicao.

    O authorizer devolve `context.audience` (`dashboard` ou `ingest`). O valor
    chega aqui pelo evento do API Gateway, e nao por cabecalho, justamente para
    que um cliente nao consiga declarar a propria audiencia.

    Returns:
        str | None: A audiencia autorizada, ou `None` quando a rota e publica
            (`GET /health/live`) ou quando a API roda fora do API Gateway.
    """
    autorizador = _contexto_do_gateway().get("authorizer") or {}
    contexto = autorizador.get("lambda") or {}
    audiencia = contexto.get("audience")
    return str(audiencia) if audiencia else None


def _contexto_do_gateway() -> dict[str, Any]:
    """Devolve o `requestContext` do evento do API Gateway, quando existir.

    O `apig-wsgi` guarda o evento cru em `apig_wsgi.full_event`. Fora da Lambda
    (testes, `make api`) a chave nao existe e a funcao devolve vazio, sem que
    quem chama precise saber onde esta rodando.

    Returns:
        dict[str, Any]: O `requestContext`, ou um dicionario vazio.
    """
    evento = request.environ.get("apig_wsgi.full_event") or {}
    contexto = evento.get("requestContext")
    return contexto if isinstance(contexto, dict) else {}
