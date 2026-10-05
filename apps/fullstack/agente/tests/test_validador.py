"""O validador recusa o que nao pode ser conferido e avisa o que e ambiguo."""

from __future__ import annotations

import pytest
from conftest import conclusao, consulta_serie

from argus_agente.validador import Conclusao, Consulta, PassoInvalido, interpretar

VISTOS = {"prometheus:http_5xx_rate:0", "prometheus:http_5xx_rate:120"}


def test_consulta_valida_vira_chamada_de_ferramenta():
    passo = interpretar(consulta_serie(), fact_ids_vistos=set())
    assert isinstance(passo, Consulta)
    assert passo.ferramenta == "consultar_serie"


def test_acao_desconhecida_e_rejeitada():
    with pytest.raises(PassoInvalido, match="action"):
        interpretar({"action": "deletar", "rationale": "x"}, fact_ids_vistos=set())


def test_limit_fora_do_tipo_e_rejeitado_antes_de_gastar_chamada():
    with pytest.raises(PassoInvalido, match="limit"):
        interpretar(consulta_serie(limit="muitos"), fact_ids_vistos=set())


def test_argumento_faltando_nao_e_julgado_aqui():
    # Combinacao incompleta e assunto do leitor, que conhece o recorte. O
    # validador so normaliza tipos; a recusa chega como erro de ferramenta.
    passo = consulta_serie()
    del passo["arguments"]["metric"]
    assert interpretar(passo, fact_ids_vistos=set()).ferramenta == "consultar_serie"


def test_hipotese_que_cita_fato_nao_entregue_e_rejeitada():
    with pytest.raises(PassoInvalido, match="nenhuma ferramenta devolveu"):
        interpretar(conclusao(["inventado:1"]), fact_ids_vistos=VISTOS)


def test_hipotese_sem_tentativa_de_refutacao_e_rejeitada():
    passo = conclusao(list(VISTOS))
    passo["answer"]["gaps"] = []
    with pytest.raises(PassoInvalido, match="refutacao"):
        interpretar(passo, fact_ids_vistos=VISTOS)


def test_linguagem_conclusiva_e_rejeitada():
    passo = conclusao(list(VISTOS))
    passo["answer"]["statement"] = "A causa raiz foi o deploy"
    with pytest.raises(PassoInvalido, match="conclusiva"):
        interpretar(passo, fact_ids_vistos=VISTOS)


def test_evidencia_contraria_marca_a_hipotese_como_contestada():
    passo = conclusao(
        ["prometheus:http_5xx_rate:0"], contra=["prometheus:http_5xx_rate:120"]
    )
    resultado = interpretar(passo, fact_ids_vistos=VISTOS)
    assert isinstance(resultado, Conclusao)
    assert resultado.contestada


def test_fato_que_apoia_e_contesta_vira_aviso_e_nao_erro():
    repetido = ["prometheus:http_5xx_rate:0"]
    resultado = interpretar(conclusao(repetido, contra=repetido), fact_ids_vistos=VISTOS)
    assert isinstance(resultado, Conclusao)
    assert resultado.avisos and "ao mesmo tempo" in resultado.avisos[0]


def test_desistir_exige_lacuna_com_motivo_do_catalogo():
    with pytest.raises(PassoInvalido, match="gaps"):
        interpretar({"action": "desistir", "rationale": "nada"}, fact_ids_vistos=set())
    with pytest.raises(PassoInvalido, match="reason"):
        interpretar(
            {
                "action": "desistir",
                "rationale": "nada",
                "gaps": [{"missing": "x", "reason": "porque sim"}],
            },
            fact_ids_vistos=set(),
        )
