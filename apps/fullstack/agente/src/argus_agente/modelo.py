"""Acesso ao modelo -- Ollama por HTTP ou por SSH, e um dublê de roteiro.

O transporte repete o desenho que ja existe no backend
(`telemetry/infrastructure/ollama.py`): quando o Ollama nao e alcancavel
diretamente, um `curl` roda dentro do servidor por SSH. A copia e deliberada --
o piloto precisa permanecer uma execucao separada, sem importar o pacote da API
de leitura e sem herdar o ciclo de vida dela.

`ModeloDeRoteiro` existe para que o ciclo do agente possa ser exercitado sem
rede: os testes e a execucao de demonstracao usam um roteiro fixo de passos.
"""

from __future__ import annotations

import json
import re
import shlex
import threading
from collections.abc import Callable, Iterable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from argus_agente.contrato import ESQUEMA_PASSO

MAX_RESPONSE_BYTES = 256 * 1024


class ModeloIndisponivel(RuntimeError):
    """O modelo nao respondeu: rede, SSH, timeout ou erro HTTP."""


class RespostaIlegivel(ValueError):
    """O modelo respondeu, mas o conteudo nao e um objeto JSON."""

    def __init__(self, detalhe: str, bruto: str = "") -> None:
        """Guarda um trecho do texto recebido para o registro do caso.

        Args:
            detalhe (str): Motivo curto da falha de leitura.
            bruto (str): Inicio da resposta, truncado, so para auditoria.
        """
        super().__init__(detalhe)
        self.detalhe = detalhe
        self.bruto = bruto[:500]


class ClienteOllama:
    """Pede um passo da investigacao ao modelo, com saida estruturada."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_seconds: float = 90.0,
        opener: Callable[..., Any] = urlopen,
        temperatura: float = 0.0,
    ) -> None:
        """Configura o adaptador.

        Args:
            base_url (str): URL HTTP do Ollama.
            model (str): Modelo ja instalado no servidor.
            timeout_seconds (float): Limite de cada chamada.
            opener (Callable[..., Any]): Transporte injetavel.
            temperatura (float): Zero por padrao, para que reexecucoes do mesmo
                caso variem o menos possivel.

        Raises:
            ValueError: Se URL, modelo ou timeout forem invalidos.
        """
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_URL precisa usar http ou https")
        if not model.strip():
            raise ValueError("OLLAMA_MODEL e obrigatorio no piloto")
        if timeout_seconds <= 0:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS precisa ser positivo")
        self.endpoint = f"{base_url.rstrip('/')}/api/chat"
        self.model = model.strip()
        self.timeout_seconds = timeout_seconds
        self.opener = opener
        self.temperatura = temperatura

    @property
    def identidade(self) -> dict[str, Any]:
        """Descricao do modelo gravada no registro do caso."""
        return {
            "provedor": "ollama",
            "model": self.model,
            "temperatura": self.temperatura,
            "timeout_segundos": self.timeout_seconds,
        }

    def passo(self, mensagens: Iterable[dict[str, str]]) -> dict[str, Any]:
        """Pede a proxima decisao do agente.

        Args:
            mensagens (Iterable[dict[str, str]]): Historico no formato do Ollama.

        Returns:
            dict[str, Any]: Objeto JSON com a acao escolhida.

        Raises:
            ModeloIndisponivel: Quando a chamada falha ou estoura o limite.
            RespostaIlegivel: Quando o conteudo devolvido nao e um objeto JSON.
        """
        payload = {
            "model": self.model,
            "stream": False,
            "format": ESQUEMA_PASSO,
            "options": {"temperature": self.temperatura},
            "messages": list(mensagens),
        }
        request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as resposta:
                bruto = resposta.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as erro:
            raise ModeloIndisponivel(f"Ollama indisponivel: {erro}") from erro
        if len(bruto) > MAX_RESPONSE_BYTES:
            raise ModeloIndisponivel("resposta do Ollama excedeu o limite")
        try:
            envelope = json.loads(bruto)
            conteudo = envelope["message"]["content"]
        except (json.JSONDecodeError, KeyError, TypeError) as erro:
            raise ModeloIndisponivel("Ollama devolveu um envelope invalido") from erro
        return ler_objeto(conteudo)


class ModeloDeRoteiro:
    """Dublê que devolve passos previamente escritos, na ordem.

    Nao imita o modelo: serve para exercitar o ciclo, os tetos e o validador de
    forma deterministica, inclusive sem rede.
    """

    def __init__(self, passos: Iterable[Any], *, nome: str = "roteiro") -> None:
        """Guarda o roteiro.

        Args:
            passos (Iterable[Any]): Dicionarios de passo, textos crus ou
                excecoes a levantar -- texto cru e excecao permitem reproduzir
                resposta invalida e indisponibilidade.
            nome (str): Identificacao gravada no registro.
        """
        self.passos = list(passos)
        self.nome = nome
        self.chamadas = 0

    @property
    def identidade(self) -> dict[str, Any]:
        """Descricao do dublê gravada no registro do caso."""
        return {"provedor": "roteiro", "model": self.nome, "temperatura": 0.0}

    def passo(self, mensagens: Iterable[dict[str, str]]) -> dict[str, Any]:
        """Devolve o proximo passo do roteiro.

        Args:
            mensagens (Iterable[dict[str, str]]): Ignorado pelo dublê.

        Returns:
            dict[str, Any]: Passo seguinte.

        Raises:
            ModeloIndisponivel: Quando o roteiro acaba ou pede indisponibilidade.
            RespostaIlegivel: Quando o roteiro traz um texto que nao e JSON.
        """
        list(mensagens)
        if self.chamadas >= len(self.passos):
            raise ModeloIndisponivel("roteiro esgotado")
        item = self.passos[self.chamadas]
        self.chamadas += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            return ler_objeto(item)
        return dict(item)


def ler_objeto(conteudo: Any) -> dict[str, Any]:
    """Extrai um objeto JSON do conteudo devolvido pelo modelo.

    `format` restringe a geracao, mas nem todo servidor honra o campo, e
    modelos as vezes embrulham o JSON em cercas de codigo. Tentar extrair o
    objeto e barato e evita descartar um passo valido por ruido de formatacao;
    o que nao for objeto JSON vira `RespostaIlegivel` e segue para o validador.

    Args:
        conteudo (Any): Texto devolvido pelo modelo.

    Returns:
        dict[str, Any]: Objeto JSON lido.

    Raises:
        RespostaIlegivel: Quando nao ha objeto JSON legivel no conteudo.
    """
    if isinstance(conteudo, dict):
        return conteudo
    if not isinstance(conteudo, str) or not conteudo.strip():
        raise RespostaIlegivel("o modelo devolveu conteudo vazio", str(conteudo))
    texto = conteudo.strip()
    cerca = re.match(r"^```(?:json)?\s*(.*?)\s*```$", texto, re.DOTALL)
    if cerca:
        texto = cerca.group(1).strip()
    try:
        lido = json.loads(texto)
    except json.JSONDecodeError:
        inicio, fim = texto.find("{"), texto.rfind("}")
        if inicio == -1 or fim <= inicio:
            raise RespostaIlegivel("resposta sem objeto JSON", texto) from None
        try:
            lido = json.loads(texto[inicio : fim + 1])
        except json.JSONDecodeError as erro:
            raise RespostaIlegivel(f"JSON malformado: {erro.msg}", texto) from erro
    if not isinstance(lido, dict):
        raise RespostaIlegivel("a resposta nao e um objeto JSON", texto)
    return lido


class AberturaSSH:
    """Executa a chamada HTTP com `curl` dentro do servidor, por SSH."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        remote_host: str = "127.0.0.1",
        remote_port: int = 11434,
    ) -> None:
        """Guarda as credenciais, que so podem vir do `.env` local.

        Args:
            host (str): Host SSH.
            port (int): Porta SSH.
            username (str): Usuario SSH.
            password (str): Senha lida do `.env`, nunca do repositorio.
            remote_host (str): Host do Ollama visto de dentro do servidor.
            remote_port (int): Porta do Ollama vista de dentro do servidor.

        Raises:
            ValueError: Quando uma credencial obrigatoria falta ou e invalida.
        """
        if not host or not username or not password:
            raise ValueError(
                "OLLAMA_SSH_HOST, OLLAMA_SSH_USER e OLLAMA_SSH_PASSWORD sao obrigatorios"
            )
        if not re.fullmatch(r"[A-Za-z0-9.-]+", remote_host):
            raise ValueError("OLLAMA_REMOTE_HOST invalido")
        if not 1 <= remote_port <= 65535:
            raise ValueError("OLLAMA_REMOTE_PORT invalida")
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.remote_host = remote_host
        self.remote_port = remote_port
        self._cliente: Any = None
        self._trava = threading.Lock()

    def __call__(self, request: Request, *, timeout: float) -> _RespostaSSH:
        """Roda a requisicao no servidor e devolve a resposta em memoria.

        Args:
            request (Request): Requisicao montada pelo cliente.
            timeout (float): Limite total da chamada.

        Returns:
            _RespostaSSH: Resposta com a pequena interface de `urlopen`.

        Raises:
            OSError: Quando a sessao SSH ou o `curl` remoto falham.
        """
        import paramiko

        try:
            cliente = self._conectado(timeout)
            url = f"http://{self.remote_host}:{self.remote_port}{request.selector}"
            comando = (
                "curl --fail --silent --show-error "
                f"--max-time {max(1, int(timeout))} "
                f"-X {shlex.quote(request.get_method())} "
                "-H 'Content-Type: application/json' "
                f"{'--data-binary @- ' if request.data is not None else ''}"
                f"{shlex.quote(url)}"
            )
            stdin, stdout, stderr = cliente.exec_command(comando, timeout=timeout)
            if request.data is not None:
                stdin.channel.sendall(request.data)
            stdin.channel.shutdown_write()
            payload = stdout.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                stdout.channel.close()
                raise OSError("resposta do Ollama excedeu o limite")
            status = stdout.channel.recv_exit_status()
            detalhe = stderr.read(4096).decode(errors="replace").strip()
            if status != 0:
                raise OSError(detalhe or f"curl remoto terminou com status {status}")
            return _RespostaSSH(payload)
        except (paramiko.SSHException, OSError) as erro:
            raise OSError(f"falha na conexao SSH com o Ollama: {erro}") from erro

    def _conectado(self, timeout: float) -> Any:
        """Abre a sessao SSH uma vez e a reaproveita entre os passos."""
        import paramiko

        with self._trava:
            transporte = self._cliente.get_transport() if self._cliente else None
            if transporte and transporte.is_active():
                return self._cliente
            cliente = paramiko.SSHClient()
            cliente.load_system_host_keys()
            # O parceiro forneceu host, usuario e senha, sem fingerprint.
            cliente.set_missing_host_key_policy(paramiko.WarningPolicy())
            cliente.connect(
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=timeout,
                auth_timeout=timeout,
                banner_timeout=timeout,
                look_for_keys=False,
                allow_agent=False,
            )
            self._cliente = cliente
            return cliente


class _RespostaSSH:
    """Resposta em memoria compativel com a interface usada pelo cliente."""

    def __init__(self, payload: bytes) -> None:
        """Guarda os bytes lidos do servidor."""
        self.payload = payload

    def __enter__(self) -> _RespostaSSH:
        """Permite o uso com `with`."""
        return self

    def __exit__(self, *_args: Any) -> None:
        """Nao ha recurso a liberar."""
        return None

    def read(self, quantidade: int) -> bytes:
        """Le no maximo a quantidade pedida.

        Args:
            quantidade (int): Limite de bytes.

        Returns:
            bytes: Trecho da resposta.
        """
        return self.payload[:quantidade]
