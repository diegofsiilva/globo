"""Leitura e validacao da resposta do modelo.

O validador nao julga se a causa proposta e verdadeira; isso e da revisao
humana (artefatos/arquitetura-agente-hipoteses-ia.md, 4.1). Ele responde
apenas: a resposta e bem formada, cita fatos que existem no recorte, declara o
que faltou e admite o que a contradiz.

A validacao SEMANTICA dos argumentos -- janela dentro do recorte, par de
dimensao, combinacao anunciada pelo inventario -- nao mora aqui. Ela e do
leitor, que e quem conhece o recorte. Repetir essas regras neste arquivo criaria
um segundo lugar para elas divergirem, e divergencia entre validador e leitor
produz exatamente o erro mais dificil de achar: o passo aceito aqui e recusado
la. Pedido invalido consome uma chamada, entra no rastro e volta ao modelo como
dado, que e o que o desenho do Dia 1 previu.

`problemas` interrompe o passo e vira pedido de correcao. `avisos` segue junto
com o resultado, para a revisao ler a hipotese com a ressalva certa.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

from argus_agente.contrato import ACOES, FERRAMENTAS, MAX_TEXTO, MOTIVOS_DE_LACUNA

# Linguagem conclusiva em uma saida que e, por construcao, uma explicacao
# candidata. A regra espelha a RN-H11 do motor atual (artefatos/hipoteses.md):
# o piloto propoe, nao confirma.
TERMOS_CONCLUSIVOS = (
    "causa raiz",
    "causa-raiz",
    "com certeza",
    "certamente",
    "definitivamente",
    "confirmado que",
    "comprovado",
    "sem duvida",
)

# Argumentos que o leitor recebe como numero. Todo o resto chega como texto;
# listas ficam como listas de texto.
ARGUMENTOS_NUMERICOS = ("limit",)
ARGUMENTOS_EM_LISTA = ("kinds",)


class PassoInvalido(ValueError):
    """A resposta do modelo violou o contrato e precisa ser refeita."""

    def __init__(self, problemas: list[str]) -> None:
        """Guarda a lista de violacoes, que vai inteira para o modelo.

        Args:
            problemas (list[str]): Violacoes encontradas, em portugues.
        """
        super().__init__("; ".join(problemas))
        self.problemas = problemas


@dataclass(frozen=True, slots=True)
class Consulta:
    """O modelo pediu uma ferramenta."""

    ferramenta: str
    argumentos: dict[str, Any]
    rationale: str


@dataclass(slots=True)
class Conclusao:
    """O modelo entregou uma hipotese."""

    hipotese: dict[str, Any]
    rationale: str
    contestada: bool = False
    avisos: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Desistencia:
    """O modelo declarou evidencia insuficiente."""

    lacunas: list[dict[str, Any]]
    rationale: str


Passo = Consulta | Conclusao | Desistencia


def interpretar(passo: Any, *, fact_ids_vistos: set[str]) -> Passo:
    """Valida um passo do modelo e devolve a acao correspondente.

    Args:
        passo (Any): Objeto JSON devolvido pelo modelo.
        fact_ids_vistos (set[str]): Identificadores que as ferramentas ja
            entregaram nesta investigacao. Citar fora deste conjunto e
            alucinacao de referencia, nao divergencia de opiniao.

    Returns:
        Passo: Consulta, Conclusao ou Desistencia.

    Raises:
        PassoInvalido: Quando a resposta viola o contrato.
    """
    problemas: list[str] = []
    if not isinstance(passo, dict):
        raise PassoInvalido(["a resposta nao e um objeto JSON"])
    acao = passo.get("action")
    if acao not in ACOES:
        raise PassoInvalido([f"action precisa ser um de {list(ACOES)}, veio {acao!r}"])
    rationale = _texto(passo.get("rationale"), "rationale", problemas)

    if acao == "consultar":
        ferramenta, argumentos = _validar_consulta(passo, problemas)
        if problemas:
            raise PassoInvalido(problemas)
        return Consulta(ferramenta=ferramenta, argumentos=argumentos, rationale=rationale)

    if acao == "desistir":
        lacunas = _validar_lacunas(passo.get("gaps"), problemas, obrigatorio=True)
        if problemas:
            raise PassoInvalido(problemas)
        return Desistencia(lacunas=lacunas, rationale=rationale)

    hipotese, avisos = _validar_hipotese(passo.get("answer"), fact_ids_vistos, problemas)
    if problemas:
        raise PassoInvalido(problemas)
    return Conclusao(
        hipotese=hipotese,
        rationale=rationale,
        contestada=bool(hipotese["evidence_against"]),
        avisos=avisos,
    )


def _validar_consulta(
    passo: dict[str, Any], problemas: list[str]
) -> tuple[str, dict[str, Any]]:
    """Confere o nome da ferramenta e normaliza os tipos dos argumentos."""
    ferramenta = passo.get("tool")
    if ferramenta not in FERRAMENTAS:
        problemas.append(
            f"tool precisa ser um de {list(FERRAMENTAS)}, veio {ferramenta!r}"
        )
        return "", {}
    brutos = passo.get("arguments") or {}
    if not isinstance(brutos, dict):
        problemas.append("arguments precisa ser um objeto")
        return ferramenta, {}
    argumentos: dict[str, Any] = {}
    for chave, valor in brutos.items():
        if valor is None:
            continue
        if chave in ARGUMENTOS_NUMERICOS:
            if isinstance(valor, bool) or not isinstance(valor, int):
                problemas.append(f"{chave} precisa ser um numero inteiro")
                continue
            argumentos[chave] = valor
        elif chave in ARGUMENTOS_EM_LISTA:
            if not isinstance(valor, list) or not valor:
                problemas.append(f"{chave} precisa ser uma lista nao vazia")
                continue
            argumentos[chave] = [str(item)[:64] for item in valor[:5]]
        else:
            argumentos[chave] = str(valor)[:512]
    return ferramenta, argumentos


def _validar_hipotese(
    bruta: Any, fact_ids_vistos: set[str], problemas: list[str]
) -> tuple[dict[str, Any], list[str]]:
    """Confere estrutura, lastro e honestidade da hipotese."""
    avisos: list[str] = []
    if not isinstance(bruta, dict):
        problemas.append("concluir exige o objeto answer")
        return {}, avisos
    statement = _texto(bruta.get("statement"), "statement", problemas, limite=400)
    for termo in TERMOS_CONCLUSIVOS:
        if termo in statement.lower():
            problemas.append(
                f"statement afirma causa de forma conclusiva ({termo!r}); "
                "a saida do piloto e uma explicacao candidata"
            )
            break
    escopo = bruta.get("scope")
    if not isinstance(escopo, dict) or not str(escopo.get("entity", "")).strip():
        problemas.append("scope.entity e obrigatorio")
        escopo = {}
    a_favor = _validar_evidencias(
        bruta.get("evidence_for"), "evidence_for", fact_ids_vistos, problemas
    )
    if not a_favor:
        problemas.append(
            "evidence_for precisa ter ao menos uma evidencia com fatos consultados"
        )
    contra = _validar_evidencias(
        bruta.get("evidence_against"), "evidence_against", fact_ids_vistos, problemas
    )
    lacunas = _validar_lacunas(bruta.get("gaps"), problemas, obrigatorio=False)
    if not contra and not lacunas:
        problemas.append(
            "nenhuma tentativa de refutacao registrada: preencha evidence_against "
            "com o que voce verificou e nao derrubou a hipotese, ou gaps com o que "
            "nao foi possivel verificar"
        )
    repetidos = {
        fact_id
        for evidencia in a_favor
        for fact_id in evidencia["fact_ids"]
        if any(fact_id in outra["fact_ids"] for outra in contra)
    }
    if repetidos:
        avisos.append(
            f"os fatos {sorted(repetidos)} sustentam e contestam a hipotese "
            "ao mesmo tempo"
        )
    hipotese = {
        "statement": statement,
        "scope": {
            chave: str(escopo[chave])[:128]
            for chave in ("entity", "dimension_type", "dimension_value")
            if escopo.get(chave)
        },
        "evidence_for": a_favor,
        "evidence_against": contra,
        "gaps": lacunas,
    }
    for chave in ("effect_start", "effect_end"):
        instante = bruta.get(chave)
        if instante:
            lido = _instante(instante, chave, problemas)
            if lido is not None:
                hipotese[chave] = lido.isoformat()
    return hipotese, avisos


def _validar_evidencias(
    brutas: Any, campo: str, fact_ids_vistos: set[str], problemas: list[str]
) -> list[dict[str, Any]]:
    """Confere que cada evidencia cita fatos realmente entregues."""
    if brutas is None:
        return []
    if not isinstance(brutas, list):
        problemas.append(f"{campo} precisa ser uma lista")
        return []
    saida: list[dict[str, Any]] = []
    for indice, bruta in enumerate(brutas[:6]):
        rotulo = f"{campo}[{indice}]"
        if not isinstance(bruta, dict):
            problemas.append(f"{rotulo} precisa ser um objeto")
            continue
        fact_ids = bruta.get("fact_ids")
        if not isinstance(fact_ids, list) or not fact_ids:
            problemas.append(f"{rotulo}.fact_ids precisa citar ao menos um fato")
            continue
        inventados = [
            str(fact_id) for fact_id in fact_ids if str(fact_id) not in fact_ids_vistos
        ]
        if inventados:
            problemas.append(
                f"{rotulo} cita fatos que nenhuma ferramenta devolveu: {inventados[:5]}"
            )
            continue
        observacao = _texto(bruta.get("observation"), f"{rotulo}.observation", problemas)
        leitura = _texto(bruta.get("reading"), f"{rotulo}.reading", problemas)
        saida.append(
            {
                "fact_ids": list(dict.fromkeys(str(fact_id) for fact_id in fact_ids))[
                    :12
                ],
                "observation": observacao,
                "reading": leitura,
            }
        )
    return saida


def _validar_lacunas(
    brutas: Any, problemas: list[str], *, obrigatorio: bool
) -> list[dict[str, Any]]:
    """Confere as lacunas declaradas e seus motivos."""
    if brutas is None:
        brutas = []
    if not isinstance(brutas, list):
        problemas.append("gaps precisa ser uma lista")
        return []
    if obrigatorio and not brutas:
        problemas.append("desistir exige ao menos uma lacuna em gaps")
        return []
    saida: list[dict[str, Any]] = []
    for indice, bruta in enumerate(brutas[:6]):
        if not isinstance(bruta, dict):
            problemas.append(f"gaps[{indice}] precisa ser um objeto")
            continue
        motivo = bruta.get("reason")
        if motivo not in MOTIVOS_DE_LACUNA:
            problemas.append(
                f"gaps[{indice}].reason precisa ser um de {list(MOTIVOS_DE_LACUNA)}"
            )
            continue
        saida.append(
            {
                "missing": _texto(
                    bruta.get("missing"), f"gaps[{indice}].missing", problemas
                ),
                "reason": motivo,
            }
        )
    return saida


def _texto(
    valor: Any, campo: str, problemas: list[str], *, limite: int = MAX_TEXTO
) -> str:
    """Normaliza um texto curto e recusa o que vier vazio ou fora do tipo."""
    if not isinstance(valor, str) or not valor.strip():
        problemas.append(f"{campo} precisa ser um texto nao vazio")
        return ""
    limpo = re.sub(r"[\x00-\x1f\x7f]", " ", valor).strip()
    return limpo[:limite]


def _instante(valor: Any, campo: str, problemas: list[str]) -> dt.datetime | None:
    """Le um instante ISO-8601 vindo do modelo."""
    if not isinstance(valor, str):
        problemas.append(f"{campo} precisa ser um texto ISO-8601")
        return None
    try:
        return dt.datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        problemas.append(f"{campo} nao e um instante ISO-8601 valido: {valor!r}")
        return None
