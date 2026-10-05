"""O ciclo de investigacao -- Dia 3 (passo unico) e Dia 4 (ciclo com tetos).

Uma unica funcao publica, `investigar`, com a assinatura pequena prevista no
Dia 1: recebe o caso, as ferramentas e o modelo, e devolve o registro do que
aconteceu. Tudo o que o piloto precisa trocar depois -- outro modelo, outro
adaptador de dados, outro orcamento -- entra por parametro.

O ciclo nunca termina por decisao exclusiva do modelo: ou ele conclui, ou
desiste, ou uma guarda o interrompe. Toda saida possivel vira um `desfecho`
gravado, inclusive as que nao produzem hipotese.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from collections.abc import Callable
from typing import Any

from argus_agente.contrato import Caso, RegistroDoCaso
from argus_agente.ferramentas import ArgumentoInvalido, Ferramentas
from argus_agente.limites import Guardas, Orcamento, TetoAtingido
from argus_agente.modelo import ModeloIndisponivel, RespostaIlegivel
from argus_agente.prompt import (
    PROMPT_VERSION,
    SISTEMA,
    mensagem_de_abertura,
    mensagem_de_correcao,
    mensagem_de_erro_de_ferramenta,
    mensagem_de_resultado,
)
from argus_agente.validador import (
    Conclusao,
    Consulta,
    Desistencia,
    PassoInvalido,
    interpretar,
)


def investigar(
    caso: Caso,
    ferramentas: Ferramentas,
    modelo: Any,
    *,
    orcamento: Orcamento | None = None,
    relogio: Callable[[], float] = time.monotonic,
    agora: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
) -> RegistroDoCaso:
    """Investiga um caso e devolve o registro completo da execucao.

    Args:
        caso (Caso): Recorte e inventario da investigacao.
        ferramentas (Ferramentas): Adaptador de consulta ao recorte.
        modelo (Any): Objeto com `passo(mensagens)` e `identidade`.
        orcamento (Orcamento | None): Tetos do caso; o padrao e o do Dia 1.
        relogio (Callable[[], float]): Tempo monotonico, injetavel nos testes.
        agora (Callable[[], dt.datetime]): Relogio de parede para o carimbo do
            registro. E o tempo real da execucao, nunca o `sim_now` do recorte.

    Returns:
        RegistroDoCaso: Desfecho, hipotese, consultas, passos e consumo.
    """
    orcamento = orcamento or Orcamento()
    guardas = Guardas(orcamento, relogio=relogio)
    registro = RegistroDoCaso(
        case_id=caso.case_id,
        criado_em=agora().isoformat(),
        recorte={
            "checkpoint_id": caso.recorte.checkpoint_id,
            "sim_now": caso.recorte.sim_now.isoformat(),
            "input_lsn": caso.recorte.input_lsn,
            "janela_inicio": caso.recorte.janela_inicio.isoformat(),
            "janela_fim": caso.recorte.janela_fim.isoformat(),
            "digest": caso.recorte.digest,
        },
        modelo=dict(modelo.identidade),
        prompt_version=PROMPT_VERSION,
    )
    registro.metricas["orcamento"] = {
        "max_chamadas": orcamento.max_chamadas,
        "max_linhas_por_resposta": orcamento.max_linhas_por_resposta,
        "max_linhas_totais": orcamento.max_linhas_totais,
        "max_segundos": orcamento.max_segundos,
        "max_passos_invalidos": orcamento.max_passos_invalidos,
    }

    mensagens: list[dict[str, str]] = [
        {"role": "system", "content": SISTEMA},
        {"role": "user", "content": mensagem_de_abertura(caso, guardas)},
    ]
    fact_ids_vistos: set[str] = set()

    try:
        while True:
            guardas.antes_do_passo()
            try:
                bruto = modelo.passo(mensagens)
            except ModeloIndisponivel as erro:
                registro.desfecho = "erro_de_execucao"
                registro.motivo = str(erro)
                break
            except RespostaIlegivel as erro:
                _registrar_passo(registro, guardas, "ilegivel", "", [erro.detalhe])
                registro.metricas.setdefault("respostas_ilegiveis", []).append(erro.bruto)
                guardas.registrar_passo_invalido()
                mensagens.append(
                    {
                        "role": "user",
                        "content": mensagem_de_correcao([erro.detalhe], guardas),
                    }
                )
                continue

            mensagens.append(
                {"role": "assistant", "content": json.dumps(bruto, ensure_ascii=False)}
            )
            try:
                passo = interpretar(bruto, fact_ids_vistos=fact_ids_vistos)
            except PassoInvalido as erro:
                _registrar_passo(
                    registro, guardas, str(bruto.get("action")), "", erro.problemas
                )
                guardas.registrar_passo_invalido()
                mensagens.append(
                    {
                        "role": "user",
                        "content": mensagem_de_correcao(erro.problemas, guardas),
                    }
                )
                continue

            if isinstance(passo, Consulta):
                _registrar_passo(registro, guardas, "consultar", passo.rationale, [])
                guardas.antes_da_chamada()
                mensagens.append(
                    {
                        "role": "user",
                        "content": _executar(
                            registro, guardas, ferramentas, passo, fact_ids_vistos
                        ),
                    }
                )
                continue

            if isinstance(passo, Desistencia):
                _registrar_passo(registro, guardas, "desistir", passo.rationale, [])
                registro.desfecho = "evidencia_insuficiente"
                registro.lacunas = passo.lacunas
                break

            assert isinstance(passo, Conclusao)
            _registrar_passo(registro, guardas, "concluir", passo.rationale, [])
            registro.desfecho = "hipotese"
            registro.hipotese = passo.hipotese
            registro.lacunas = passo.hipotese["gaps"]
            registro.contestada = passo.contestada
            registro.validacao = {"aprovado": True, "avisos": passo.avisos}
            break
    except TetoAtingido as teto:
        if teto.motivo == "respostas_invalidas":
            registro.desfecho = "resposta_invalida"
        else:
            registro.desfecho = "teto_atingido"
        registro.motivo = teto.motivo

    if not registro.validacao:
        registro.validacao = {"aprovado": registro.desfecho == "hipotese", "avisos": []}
    registro.metricas["consumo"] = guardas.consumo
    registro.metricas["fatos_vistos"] = len(fact_ids_vistos)
    return registro


def _executar(
    registro: RegistroDoCaso,
    guardas: Guardas,
    ferramentas: Ferramentas,
    consulta: Consulta,
    fact_ids_vistos: set[str],
) -> str:
    """Chama a ferramenta pedida, registra a consulta e monta a resposta.

    Um erro de ferramenta nao derruba o caso: ele consome uma chamada, entra no
    rastro e volta ao modelo como dado. Investigacao real tambem esbarra em
    consulta que nao existe, e e isso que o piloto quer observar.

    Args:
        registro (RegistroDoCaso): Registro em construcao.
        guardas (Guardas): Contadores do caso.
        ferramentas (Ferramentas): Adaptador de consulta.
        consulta (Consulta): Ferramenta e argumentos ja validados.
        fact_ids_vistos (set[str]): Conjunto citavel, atualizado aqui.

    Returns:
        str: Mensagem de resultado ou de erro para o modelo.

    Raises:
        TetoAtingido: Quando as linhas lidas estouram o total permitido.
    """
    limite = guardas.orcamento.max_linhas_por_resposta
    inicio = time.monotonic()
    ordem = len(registro.consultas) + 1
    argumentos = dict(consulta.argumentos)
    try:
        if consulta.ferramenta == "inventario":
            itens = ferramentas.inventario(source=argumentos.get("source"))
            resposta = _inventario_como_resposta(itens, limite)
        elif consulta.ferramenta == "serie":
            resposta = ferramentas.serie(limite=limite, **argumentos)
        else:
            resposta = ferramentas.contexto(limite=limite, **argumentos)
    except (ArgumentoInvalido, TypeError, ValueError, KeyError) as erro:
        detalhe = f"{type(erro).__name__}: {erro}"[:200]
        registro.consultas.append(
            {
                "ordem": ordem,
                "ferramenta": consulta.ferramenta,
                "argumentos": _serializavel(argumentos),
                "linhas": 0,
                "fact_ids": [],
                "duracao_ms": int((time.monotonic() - inicio) * 1000),
                "erro": detalhe,
            }
        )
        return mensagem_de_erro_de_ferramenta(consulta.ferramenta, detalhe, guardas)

    # O inventario descreve series, nao observa nada: suas linhas nao podem
    # virar evidencia citavel, ou o modelo sustentaria uma causa na existencia
    # da metrica em vez de no valor dela.
    citaveis = [linha for linha in resposta.linhas if linha.kind != "inventario"]
    for linha in citaveis:
        fact_ids_vistos.add(linha.fact_id)
        fact_ids_vistos.update(linha.fact_ids)
    registro.consultas.append(
        {
            "ordem": ordem,
            "ferramenta": consulta.ferramenta,
            "argumentos": _serializavel(argumentos),
            "linhas": len(resposta.linhas),
            "fact_ids": sorted({linha.fact_id for linha in citaveis}),
            "duracao_ms": int((time.monotonic() - inicio) * 1000),
            "truncada": resposta.truncada,
            "vazia_porque": resposta.vazia_porque,
        }
    )
    guardas.registrar_linhas(len(resposta.linhas))
    return mensagem_de_resultado(
        consulta.ferramenta, _serializavel(argumentos), resposta, guardas
    )


def _inventario_como_resposta(itens: Any, limite: int) -> Any:
    """Embrulha o inventario no mesmo formato das outras ferramentas."""
    from argus_agente.contrato import LinhaDeFato, RespostaDeFerramenta

    linhas = tuple(
        LinhaDeFato(
            fact_id=f"inventario:{item.source}:{item.entity}:{item.metric}",
            source=item.source,
            entity=item.entity,
            metric=item.metric,
            event_start=item.primeiro_evento or dt.datetime.min,
            available_at=item.ultimo_evento or dt.datetime.min,
            value=float(item.pontos),
            dimension_type=item.dimension_type,
            kind="inventario",
        )
        for item in itens[:limite]
    )
    if not linhas:
        return RespostaDeFerramenta(linhas=(), vazia_porque="o recorte nao tem series")
    return RespostaDeFerramenta(linhas=linhas, truncada=len(itens) > limite)


def _registrar_passo(
    registro: RegistroDoCaso,
    guardas: Guardas,
    acao: str,
    rationale: str,
    problemas: list[str],
) -> None:
    """Guarda a decisao declarada no passo, valida ou nao."""
    registro.passos.append(
        {
            "ordem": guardas.passos,
            "acao": acao,
            "rationale": rationale,
            "problemas": problemas,
            "segundos": round(guardas.decorrido, 3),
        }
    )


def _serializavel(argumentos: dict[str, Any]) -> dict[str, Any]:
    """Converte instantes e tuplas para o que entra no arquivo de registro."""
    saida: dict[str, Any] = {}
    for chave, valor in argumentos.items():
        if isinstance(valor, dt.datetime):
            saida[chave] = valor.isoformat()
        elif isinstance(valor, tuple):
            saida[chave] = list(valor)
        else:
            saida[chave] = valor
    return saida
