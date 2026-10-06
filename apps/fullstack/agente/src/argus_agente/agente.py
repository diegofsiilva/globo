"""O ciclo de investigacao.

Uma unica funcao publica, `investigar`, com uma assinatura pequena: recebe o
caso, o leitor do recorte e o modelo, e devolve o registro do que aconteceu.
Tudo o que o piloto precisa trocar depois (outro modelo, outro leitor, outro
orcamento) entra por parametro.

O ciclo nunca termina por decisao exclusiva do modelo: ou ele conclui, ou
desiste, ou uma guarda o interrompe. Toda saida possivel vira um `desfecho` do
catalogo de `contrato.DESFECHOS`, inclusive as que nao produzem hipotese.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from collections.abc import Callable
from typing import Any

from argus_agente.checagem import checar_evidencias
from argus_agente.contrato import (
    DESFECHO_ERRO,
    DESFECHO_HIPOTESE,
    DESFECHO_INSUFICIENTE,
    DESFECHO_INVALIDA,
    DESFECHO_TETO,
    Caso,
    ConsultaRegistrada,
    RegistroDoCaso,
)
from argus_agente.ferramentas import (
    FerramentaIndisponivel,
    Ferramentas,
    despachar,
    fact_ids_de,
)
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
    validar_desistencia_contra_consultas,
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
        ferramentas (Ferramentas): Leitor do recorte.
        modelo (Any): Objeto com `passo(mensagens)` e `identidade`.
        orcamento (Orcamento | None): Tetos do caso; o padrao e o definido em `Orcamento`.
        relogio (Callable[[], float]): Tempo monotonico, injetavel nos testes.
        agora (Callable[[], dt.datetime]): Relogio de parede para o carimbo do
            registro. E o tempo real da execucao, nunca o `sim_now` do recorte.

    Returns:
        RegistroDoCaso: Desfecho, hipotese, consultas, passos e consumo.
    """
    orcamento = orcamento or Orcamento()
    guardas = Guardas(orcamento, relogio=relogio)
    abertura = mensagem_de_abertura(caso, guardas)
    registro = RegistroDoCaso(
        case_id=caso.case_id,
        criado_em=agora().isoformat(),
        recorte=caso.recorte.para_json(),
        modelo=dict(modelo.identidade),
        prompt_version=PROMPT_VERSION,
        entrada=abertura,
    )
    registro.metricas["orcamento"] = {
        "max_chamadas": orcamento.max_chamadas,
        "max_itens_por_resposta": orcamento.max_itens_por_resposta,
        "max_segundos": orcamento.max_segundos,
        "max_passos_invalidos": orcamento.max_passos_invalidos,
        "max_invalidas_iguais": orcamento.max_invalidas_iguais,
    }

    mensagens: list[dict[str, str]] = [
        {"role": "system", "content": SISTEMA},
        {"role": "user", "content": abertura},
    ]
    fact_ids_vistos: set[str] = set()

    try:
        while True:
            guardas.antes_do_passo()
            try:
                bruto = modelo.passo(mensagens)
            except ModeloIndisponivel as erro:
                registro.concluir(DESFECHO_ERRO, motivo=str(erro))
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
                if isinstance(passo, Conclusao) and hasattr(ferramentas, "facts"):
                    # O texto da evidencia precisa bater com a serie real. Contradicao
                    # vira pedido de correcao, como qualquer outra violacao.
                    problemas_numericos, passo.checagens = checar_evidencias(
                        passo.hipotese, ferramentas
                    )
                    if problemas_numericos:
                        raise PassoInvalido(problemas_numericos)
                if isinstance(passo, Desistencia):
                    validar_desistencia_contra_consultas(
                        passo.lacunas, registro.consultas
                    )
            except PassoInvalido as erro:
                _registrar_passo(
                    registro,
                    guardas,
                    str(bruto.get("action")),
                    "",
                    erro.problemas,
                    bruto,
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
                _registrar_passo(
                    registro, guardas, "consultar", passo.rationale, [], bruto
                )
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
                _registrar_passo(
                    registro, guardas, "desistir", passo.rationale, [], bruto
                )
                registro.concluir(DESFECHO_INSUFICIENTE)
                registro.lacunas = passo.lacunas
                break

            assert isinstance(passo, Conclusao)
            _registrar_passo(registro, guardas, "concluir", passo.rationale, [], bruto)
            registro.concluir(DESFECHO_HIPOTESE)
            registro.hipotese = passo.hipotese
            registro.lacunas = passo.hipotese["gaps"]
            registro.contestada = passo.contestada
            registro.hipotese["checagens"] = passo.checagens
            registro.validacao = {"aprovado": True, "avisos": passo.avisos}
            break
    except TetoAtingido as teto:
        if teto.motivo == "respostas_invalidas":
            registro.concluir(DESFECHO_INVALIDA, motivo=teto.motivo)
        else:
            registro.concluir(DESFECHO_TETO, motivo=teto.motivo)

    if not registro.validacao:
        registro.validacao = {"aprovado": registro.util, "avisos": []}
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
        ferramentas (Ferramentas): Leitor do recorte.
        consulta (Consulta): Ferramenta e argumentos ja normalizados.
        fact_ids_vistos (set[str]): Conjunto citavel, atualizado aqui.

    Returns:
        str: Mensagem de resultado ou de erro para o modelo.
    """
    inicio = time.monotonic()
    ordem = len(registro.consultas) + 1
    argumentos = dict(consulta.argumentos)
    # O teto de itens e do executor, nao do modelo: quando ele nao pede um
    # `limit`, o orcamento do caso decide.
    argumentos.setdefault("limit", guardas.orcamento.max_itens_por_resposta)
    try:
        envelope = despachar(ferramentas, consulta.ferramenta, argumentos)
    except (FerramentaIndisponivel, ValueError, TypeError, KeyError) as erro:
        detalhe = f"{type(erro).__name__}: {erro}"[:200]
        registro.consultas.append(
            ConsultaRegistrada(
                ordem=ordem,
                ferramenta=consulta.ferramenta,
                argumentos=argumentos,
                retornadas=0,
                fact_ids=(),
                duracao_ms=int((time.monotonic() - inicio) * 1000),
                erro=detalhe,
            ).para_json()
        )
        mensagem = mensagem_de_erro_de_ferramenta(consulta.ferramenta, detalhe, guardas)
        # Depois de registrar o erro e montar a resposta ao modelo, conta a falha:
        # se for a mesma chamada invalida de novo, a guarda encerra o caso. `limit`
        # e `cursor` ficam de fora da assinatura -- variar a paginacao nao muda a
        # consulta que falhou.
        chave = {k: v for k, v in argumentos.items() if k not in ("limit", "cursor")}
        assinatura = f"{consulta.ferramenta}:{json.dumps(chave, sort_keys=True)}"
        guardas.registrar_chamada_invalida(assinatura)
        return mensagem

    citaveis = fact_ids_de(envelope)
    fact_ids_vistos.update(citaveis)
    registro.consultas.append(
        ConsultaRegistrada(
            ordem=ordem,
            ferramenta=consulta.ferramenta,
            argumentos=argumentos,
            retornadas=int(envelope.get("returned", 0)),
            fact_ids=tuple(citaveis),
            duracao_ms=int((time.monotonic() - inicio) * 1000),
            tem_mais=bool(envelope.get("has_more")),
            limitacoes=tuple(envelope.get("limitations", ())),
        ).para_json()
    )
    guardas.registrar_itens(int(envelope.get("returned", 0)))
    return mensagem_de_resultado(consulta.ferramenta, argumentos, envelope, guardas)


def _registrar_passo(
    registro: RegistroDoCaso,
    guardas: Guardas,
    acao: str,
    rationale: str,
    problemas: list[str],
    bruto: Any = None,
) -> None:
    """Guarda a decisao declarada no passo, valida ou nao.

    A saida bruta do modelo e gravada junto, truncada. Sem ela, uma rejeicao
    so mostra o motivo do validador, e nao o que o modelo de fato escreveu.
    """
    registro.passos.append(
        {
            "ordem": guardas.passos,
            "acao": acao,
            "rationale": rationale,
            "problemas": problemas,
            "segundos": round(guardas.decorrido, 3),
            "saida_bruta": (
                json.dumps(bruto, ensure_ascii=False) if bruto is not None else None
            ),
        }
    )
