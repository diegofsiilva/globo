"""O ciclo precisa terminar sempre, e o motivo precisa ficar gravado."""

from __future__ import annotations

import itertools

from conftest import (
    FIM_JANELA,
    INICIO,
    conclusao,
    consulta_serie,
    fact_ids_da_serie,
    iso,
)

from argus_agente.agente import investigar
from argus_agente.limites import Orcamento
from argus_agente.modelo import ModeloDeRoteiro, ModeloIndisponivel


def _relogio_parado():
    return itertools.repeat(0.0).__next__


def test_investigacao_feliz_grava_hipotese_consultas_e_digest(caso, ferramentas):
    todos = fact_ids_da_serie(ferramentas)
    modelo = ModeloDeRoteiro([consulta_serie(), conclusao(todos[:3])])
    registro = investigar(caso, ferramentas, modelo, relogio=_relogio_parado())

    assert registro.desfecho == "hipotese"
    assert registro.hipotese["statement"].startswith("Possivel")
    assert registro.consultas[0]["ferramenta"] == "consultar_serie"
    assert registro.consultas[0]["retornadas"] == 13
    assert registro.recorte["digest"] == ferramentas.digest
    assert registro.entrada
    assert registro.metricas["consumo"]["chamadas"] == 1
    assert registro.validacao["aprovado"] is True


def test_desistencia_e_um_desfecho_valido(caso, ferramentas):
    modelo = ModeloDeRoteiro(
        [
            {
                "action": "desistir",
                "rationale": "o recorte nao sustenta causa",
                "gaps": [
                    {"missing": "quebra por regiao", "reason": "ainda_indisponivel"}
                ],
            }
        ]
    )
    registro = investigar(caso, ferramentas, modelo, relogio=_relogio_parado())
    assert registro.desfecho == "evidencia_insuficiente"
    assert registro.lacunas[0]["reason"] == "ainda_indisponivel"
    assert registro.hipotese is None


def test_desistencia_nao_pode_alegar_falta_de_serie_ja_consultada(caso, ferramentas):
    todos = fact_ids_da_serie(ferramentas)
    desistir = {
        "action": "desistir",
        "rationale": "faltam dados de erro",
        "gaps": [{"missing": "dados da taxa de erros 5xx", "reason": "sem_dado"}],
    }
    modelo = ModeloDeRoteiro([consulta_serie(), desistir, conclusao(todos[:3])])
    registro = investigar(caso, ferramentas, modelo, relogio=_relogio_parado())
    assert registro.desfecho == "hipotese"
    assert any("lacuna sem_dado contradita" in p for p in registro.passos[1]["problemas"])


def test_serie_agregada_nao_resolve_lacuna_de_quebra_por_uf(caso, ferramentas):
    desistir = {
        "action": "desistir",
        "rationale": "a quebra por UF nao foi consultada",
        "gaps": [{"missing": "quebra de erros 5xx por UF", "reason": "sem_dado"}],
    }
    modelo = ModeloDeRoteiro([consulta_serie(), desistir])
    registro = investigar(caso, ferramentas, modelo, relogio=_relogio_parado())
    assert registro.desfecho == "evidencia_insuficiente"


def test_teto_de_chamadas_encerra_o_caso(caso, ferramentas):
    modelo = ModeloDeRoteiro([consulta_serie() for _ in range(10)])
    registro = investigar(
        caso,
        ferramentas,
        modelo,
        orcamento=Orcamento(max_chamadas=2),
        relogio=_relogio_parado(),
    )
    assert registro.desfecho == "teto_atingido"
    assert registro.motivo == "chamadas"
    assert len(registro.consultas) == 2


def test_teto_de_tempo_encerra_antes_de_pedir_outro_passo(caso, ferramentas):
    relogio = itertools.count(0.0, 10.0).__next__
    modelo = ModeloDeRoteiro([consulta_serie() for _ in range(10)])
    registro = investigar(
        caso, ferramentas, modelo, orcamento=Orcamento(max_segundos=25), relogio=relogio
    )
    assert registro.desfecho == "teto_atingido"
    assert registro.motivo == "tempo"


def test_resposta_malformada_ganha_uma_correcao_e_depois_encerra(caso, ferramentas):
    modelo = ModeloDeRoteiro(["isto nao e json", "tambem nao e"])
    registro = investigar(caso, ferramentas, modelo, relogio=_relogio_parado())
    assert registro.desfecho == "resposta_invalida"
    assert registro.metricas["consumo"]["passos_invalidos"] == 2


def test_correcao_aceita_a_segunda_resposta_quando_ela_e_valida(caso, ferramentas):
    todos = fact_ids_da_serie(ferramentas)
    modelo = ModeloDeRoteiro(["{{nao json", consulta_serie(), conclusao(todos[:2])])
    registro = investigar(caso, ferramentas, modelo, relogio=_relogio_parado())
    assert registro.desfecho == "hipotese"
    assert registro.passos[0]["problemas"]


def test_hipotese_que_inventa_fato_e_devolvida_ao_modelo(caso, ferramentas):
    todos = fact_ids_da_serie(ferramentas)
    modelo = ModeloDeRoteiro(
        [consulta_serie(), conclusao(["fato:inexistente"]), conclusao(todos[:2])]
    )
    registro = investigar(caso, ferramentas, modelo, relogio=_relogio_parado())
    assert registro.desfecho == "hipotese"
    assert any(
        "nenhuma ferramenta devolveu" in problema
        for passo in registro.passos
        for problema in passo["problemas"]
    )


def test_modelo_indisponivel_vira_erro_de_execucao(caso, ferramentas):
    modelo = ModeloDeRoteiro([ModeloIndisponivel("Ollama fora do ar")])
    registro = investigar(caso, ferramentas, modelo, relogio=_relogio_parado())
    assert registro.desfecho == "erro_de_execucao"
    assert "Ollama" in registro.motivo
    assert registro.validacao["aprovado"] is False


def test_erro_de_ferramenta_entra_no_rastro_e_consome_chamada(caso, ferramentas):
    todos = fact_ids_da_serie(ferramentas)
    # Serie que nao consta do inventario: o leitor recusa, e a recusa precisa
    # voltar ao modelo como dado em vez de derrubar o caso.
    ruim = consulta_serie(metric="metrica_que_nao_existe")
    modelo = ModeloDeRoteiro([ruim, consulta_serie(), conclusao(todos[:2])])
    registro = investigar(caso, ferramentas, modelo, relogio=_relogio_parado())
    assert registro.consultas[0]["erro"].startswith("ValueError")
    assert registro.metricas["consumo"]["chamadas"] == 2
    assert registro.desfecho == "hipotese"


def test_inventario_sozinho_nao_sustenta_hipotese(caso, ferramentas):
    inventario = {
        "action": "consultar",
        "rationale": "ver o que existe",
        "tool": "inventariar_fatos",
        "arguments": {},
    }
    citando_inventario = conclusao(["prometheus:playback:http_5xx_rate"])
    modelo = ModeloDeRoteiro([inventario, citando_inventario, citando_inventario])
    registro = investigar(caso, ferramentas, modelo, relogio=_relogio_parado())
    assert registro.desfecho == "resposta_invalida"


def test_contexto_do_deploy_fica_citavel(caso, ferramentas):
    pedido = {
        "action": "consultar",
        "rationale": "procurar mudanca operacional",
        "tool": "consultar_contexto",
        "arguments": {
            "entity": "playback",
            "kinds": ["context"],
            "inicio": iso(INICIO),
            "fim": iso(FIM_JANELA),
        },
    }
    deploy = ferramentas.consultar_contexto(
        entity="playback", kinds=["context"], inicio=iso(INICIO), fim=iso(FIM_JANELA)
    )["items"][0]["fact_id"]
    modelo = ModeloDeRoteiro([pedido, conclusao([deploy])])
    registro = investigar(caso, ferramentas, modelo, relogio=_relogio_parado())
    assert registro.desfecho == "hipotese"
    assert registro.consultas[0]["fact_ids"] == [deploy]
