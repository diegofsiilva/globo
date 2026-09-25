"""TI-05 -- integracao entre os componentes IMPLANTADOS na AWS.

Este e o unico teste da suite que sai da maquina. Os outros quatro testes de
integracao do projeto (TI-01 a TI-04) exercitam as camadas localmente, com
PostgreSQL de verdade e SQS dublado, porque e isso que os torna repetiveis. Em
troca, eles nao alcancam quatro costuras que existem SO na nuvem:

  1. a integracao direta API Gateway -> SQS, sem Lambda no caminho;
  2. o Lambda authorizer, que valida o Bearer antes de qualquer integracao;
  3. a separacao de audiencia entre os dois tokens (leitura e ingestao);
  4. o pipeline assincrono completo: fila -> worker no Fargate -> RDS -> ETL ->
     API de leitura em Lambda.

Componentes atravessados, de ponta a ponta:

    POST /v1/events (API Gateway HTTP)
        -> Lambda authorizer (Bearer de INGESTAO)
            -> integracao direta SQS `argus-events`
                -> event-worker (ECS Fargate)
                    -> RDS PostgreSQL (`bronze.event`)
                        -> ETL bronze->silver (ciclo de 60 s)
                            -> `silver.session_event`
                                -> GET /api/v1/events (Lambda Flask)
                                    -> Lambda authorizer (Bearer de LEITURA)

PRE-CONDICAO: a pilha implantada e um Learner Lab, cuja sessao expira. O teste
LE endpoints e tokens do ambiente e e PULADO quando faltam -- a mesma regra dos
testes que dependem de banco local: sem a dependencia, pula; nao quebra. Com
isso `make test-backend` continua verde numa maquina sem lab.
O alvo `make test-implantacao` define TI05_REQUIRED=1 e falha quando faltam
esses dados, para que um gate de entrega nao confunda teste pulado com aprovado.

    make -C apps/fullstack env     # escreve .env a partir dos outputs do Terraform
    set -a && . apps/fullstack/.env && set +a
    cd apps/fullstack/backend && uv run pytest tests/integration/test_implantacao.py -v

SEGREDO NENHUM ENTRA AQUI. Endpoint e token vem do ambiente, nunca do codigo, e
nao aparecem em mensagem de assercao -- ver `_falha_sem_vazar`. O que for
impresso na evidencia tem de poder ser versionado.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta

import pytest

# Tempo maximo de espera pelo evento na API de leitura. O ETL bronze->silver
# roda a cada 60 s por padrao (`ETL_BRONZE_SILVER_INTERVAL_SECONDS`), e antes
# dele ha o poll do SQS e a gravacao do worker. Cinco minutos cobrem um ciclo
# perdido sem deixar o teste pendurado se o pipeline estiver parado.
ESPERA_MAXIMA_S = int(os.getenv("TI05_TIMEOUT_SECONDS", "300"))

# Intervalo entre consultas durante a espera.
INTERVALO_S = 10

# Token com a FORMA certa e valor errado: 64 hexadecimais que nao correspondem
# a nenhum SHA-256 registrado. Distingue "recusado por formato" de "recusado
# por nao estar autorizado" -- e o segundo que este teste quer ver.
TOKEN_INVALIDO = "f" * 64


def _ambiente() -> dict[str, str]:
    """Le endpoints e tokens do ambiente, ou pula a suite.

    Returns:
        dict[str, str]: `ingest_url`, `read_url` (sem barra final) e os dois
            tokens.
    """
    valores = {
        "ingest_url": os.getenv("ARGUS_INGEST_URL", "").strip().rstrip("/"),
        "read_url": os.getenv("ARGUS_API_URL", "").strip().rstrip("/"),
        "ingest_token": os.getenv("ARGUS_INGEST_TOKEN", "").strip(),
        "read_token": os.getenv("ARGUS_READ_TOKEN", "").strip(),
    }
    faltando = sorted(nome for nome, valor in valores.items() if not valor)
    if faltando:
        mensagem = (
            "pilha implantada indisponivel: faltam "
            + ", ".join(faltando)
            + " (rode `make -C apps/fullstack env` e carregue o .env)"
        )
        if os.getenv("TI05_REQUIRED") == "1":
            pytest.fail(mensagem)
        pytest.skip(mensagem)
    return valores


def _falha_sem_vazar(motivo: str) -> str:
    """Mensagem de falha garantidamente livre de endpoint e token.

    Assercao que falha imprime a mensagem na saida do pytest, e essa saida vai
    para a evidencia versionada. Qualquer texto que descreva a requisicao passa
    por aqui.

    Args:
        motivo (str): Descricao do que falhou, sem valor sensivel.

    Returns:
        str: A propria mensagem, para uso em `assert ..., _falha_sem_vazar(...)`.
    """
    return motivo


def _requisitar(
    url: str, *, token: str | None = None, corpo: object | None = None
) -> tuple[int, dict]:
    """Faz a requisicao e devolve status e corpo, sem levantar em erro HTTP.

    `urllib` levanta `HTTPError` em 4xx/5xx, mas aqui o status de recusa e
    justamente o resultado sob teste -- nao um acidente.

    Args:
        url (str): URL completa.
        token (str | None): Valor do `Authorization: Bearer`, se houver.
        corpo (object | None): Objeto a serializar como JSON; ausente = GET.

    Returns:
        tuple[int, dict]: Status HTTP e corpo decodificado (vazio se nao for
            JSON).
    """
    dados = None if corpo is None else json.dumps(corpo).encode()
    requisicao = urllib.request.Request(url, data=dados, method="GET" if dados is None else "POST")
    if dados is not None:
        requisicao.add_header("Content-Type", "application/json")
    if token:
        requisicao.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(requisicao, timeout=30) as resposta:
            return resposta.status, _decodificar(resposta.read())
    except urllib.error.HTTPError as erro:
        return erro.code, _decodificar(erro.read())


def _decodificar(bruto: bytes) -> dict:
    try:
        carregado = json.loads(bruto or b"{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return carregado if isinstance(carregado, dict) else {"_lista": carregado}


@pytest.fixture(scope="module")
def implantacao() -> dict[str, str]:
    """Endpoints e tokens da pilha implantada, ou pula o modulo."""
    return _ambiente()


@pytest.fixture(scope="module")
def sim_now(implantacao) -> datetime:
    """Instante VIRTUAL da pilha implantada.

    O "agora" do Argus nao e o do relogio de parede: o simulador replica uma
    janela de julho de 2026. A API de leitura so mostra linha com
    `available_at <= sim.now()`, e no grao de sessao `available_at` e o proprio
    `ts` do evento. Carimbar o evento com a hora da maquina o tornaria invisivel
    -- o teste falharia sem que nada estivesse errado no sistema.
    """
    status, corpo = _requisitar(
        f"{implantacao['read_url']}/api/v1/clock", token=implantacao["read_token"]
    )
    assert status == 200, _falha_sem_vazar(f"GET /api/v1/clock respondeu {status}")
    return datetime.fromisoformat(corpo["sim_now"])


def test_ti05_o_authorizer_na_borda_recusa_quem_nao_esta_autorizado(implantacao):
    """TI-05.1 -- RNF09 na fronteira da nuvem, e nao na tela.

    Entrada: quatro requisicoes a mesma rota de leitura -- sem token, com token
    de forma valida e valor desconhecido, com o token da audiencia ERRADA (o de
    ingestao, que nao serve para ler) e com o token correto.

    Resultado esperado: as tres primeiras sao recusadas pelo Lambda authorizer
    com 401 ou 403, ANTES de alcancar a Lambda da aplicacao; a quarta responde
    200. Nenhum teste local pode afirmar isso: o authorizer so existe na borda
    do API Gateway, e o Flask local roda sem ele.
    """
    rota = f"{implantacao['read_url']}/api/v1/clock"

    sem_token, _ = _requisitar(rota)
    assert sem_token in (401, 403), _falha_sem_vazar(
        f"requisicao sem token devolveu {sem_token}, e nao 401/403"
    )

    desconhecido, _ = _requisitar(rota, token=TOKEN_INVALIDO)
    assert desconhecido in (401, 403), _falha_sem_vazar(
        f"token desconhecido devolveu {desconhecido}, e nao 401/403"
    )

    # Audiencia trocada: o token de ingestao nao pode abrir a API de leitura.
    audiencia_errada, _ = _requisitar(rota, token=implantacao["ingest_token"])
    assert audiencia_errada in (401, 403), _falha_sem_vazar(
        f"token de ingestao abriu a API de leitura com {audiencia_errada}"
    )

    autorizado, corpo = _requisitar(rota, token=implantacao["read_token"])
    assert autorizado == 200, _falha_sem_vazar(f"token de leitura correto devolveu {autorizado}")
    assert "sim_now" in corpo


def test_ti05_evento_postado_na_borda_aparece_na_api_de_leitura(implantacao, sim_now):
    """TI-05.2 -- o pipeline assincrono completo, na infraestrutura real.

    Entrada: um evento `error` unico (sessao `ti05-<uuid>`), carimbado um minuto
    ATRAS do instante virtual para que fique imediatamente disponivel, enviado
    por `POST /v1/events` com o token de ingestao.

    Resultado esperado: a borda aceita (2xx) e o evento aparece em
    `GET /api/v1/events?session_id=...` dentro do prazo, com `event_name` e
    `device_id` preservados. A espera e necessaria e faz parte do contrato: a
    ingestao e assincrona de proposito -- a borda enfileira e responde, e quem
    grava e o worker.
    """
    sessao = f"ti05-{uuid.uuid4()}"
    evento = {
        "timestamp": (sim_now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        "event_name": "error",
        "session_id": sessao,
        "device_id": f"device-{sessao}",
        "app_bucket": "S3",
        "app_env": "production",
        "app_version": "2026.3.0",
        "device_os": "NetRange",
        "error_name": "Teste de integracao TI-05",
        "route_path": "vod",
    }

    aceito, _ = _requisitar(
        implantacao["ingest_url"], token=implantacao["ingest_token"], corpo=evento
    )
    assert 200 <= aceito < 300, _falha_sem_vazar(
        f"a borda de ingestao recusou o evento com {aceito}"
    )

    consulta = f"{implantacao['read_url']}/api/v1/events?session_id={sessao}&limit=10"
    limite = time.monotonic() + ESPERA_MAXIMA_S
    itens: list[dict] = []
    tentativas = 0

    while time.monotonic() < limite:
        tentativas += 1
        status, corpo = _requisitar(consulta, token=implantacao["read_token"])
        assert status == 200, _falha_sem_vazar(
            f"GET /api/v1/events respondeu {status} na tentativa {tentativas}"
        )
        itens = corpo.get("items", [])
        if itens:
            break
        time.sleep(INTERVALO_S)

    assert itens, _falha_sem_vazar(
        f"o evento nao apareceu na leitura em {ESPERA_MAXIMA_S}s"
        f" ({tentativas} tentativas) -- fila, worker ou ETL podem estar parados"
    )

    item = itens[0]
    assert item["session_id"] == sessao
    assert item["event_name"] == "error"
    assert item["device_id"] == f"device-{sessao}"
    # RNF10 vale na nuvem tambem: o evento foi enviado sem `user_id`, e a
    # resposta nao pode inventar um.
    assert "user_id" not in item
