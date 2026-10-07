"""Checagem numerica das observacoes citadas em uma hipotese.

O validador confere que os `fact_ids` foram consultados. Esta checagem confere
uma afirmacao limitada da observacao: se ela diz que uma serie sobe, cai ou
fica estavel a partir do `effect_start`, os pontos citados precisam mostrar
isso. Tambem recusa adjetivos de magnitude ("significativamente", "pico")
quando a variacao citada e pequena. A leitura causal em `reading` continua
reservada a revisao humana.

Ela so decide quando consegue: a evidencia precisa citar fatos de UMA serie,
com pontos citados antes e depois do efeito, e a observacao precisa ter uma
direcao clara. Qualquer outro caso fica `indeterminado` -- nunca contradito.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from argus_agente.leitor import CaseReader, _instant

# Limiar de variacao relativa para considerar que a serie mudou de fato.
LIMIAR_MUDANCA = 0.10
# Um adjetivo de magnitude exige uma variacao relativa desse tamanho.
LIMIAR_MAGNITUDE = 0.50

_ALTA = ("aument", "sobe", "subi", "cresc", "eleva", "pico", "dispar")
_QUEDA = ("cai", "queda", "diminu", "reduz", "desce", "declin")
_ESTAVEL = (
    "estabil",
    "estavel",
    "constante",
    "sem mudanca",
    "nao muda",
    "permanece",
    "mantem",
)
_MAGNITUDE = ("significativ", "acentu", "forte", "muito", "pico", "dispar", "expressiv")
# Palavras que negam a direcao seguinte. "nao apresenta quedas" afirma estabilidade,
# nao uma queda; sem isso a checagem contradizia uma observacao correta.
_NEGACOES = frozenset(
    ("nao", "sem", "nenhum", "nenhuma", "nunca", "inexistente", "sequer")
)


def _normalizar(texto: str) -> str:
    """Minusculas e sem acento, para casar palavras raiz de forma tolerante."""
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _afirma_direcao(tokens: list[str], raizes: tuple[str, ...]) -> bool:
    """Se alguma raiz aparece em um token que nao esta negado logo antes.

    So olha as tres palavras anteriores: "nao apresenta quedas" e "sem aumento"
    negam a direcao, enquanto "o volume cai" a afirma.
    """
    for i, token in enumerate(tokens):
        casou = any(raiz in token for raiz in raizes)
        if casou and not (_NEGACOES & set(tokens[max(0, i - 3) : i])):
            return True
    return False


def direcao_do_texto(texto: str) -> str | None:
    """Extrai a direcao afirmada: alta, queda, estavel, ou None se ambigua/ausente.

    Alta e queda consideram a negacao; estavel e detectada pela expressao inteira,
    porque as suas proprias formas ("sem mudanca", "nao muda") usam negacao.
    """
    limpo = _normalizar(texto)
    tokens = limpo.split()
    achados = set()
    if _afirma_direcao(tokens, _ALTA):
        achados.add("alta")
    if _afirma_direcao(tokens, _QUEDA):
        achados.add("queda")
    if any(p in limpo for p in _ESTAVEL):
        achados.add("estavel")
    return achados.pop() if len(achados) == 1 else None


def magnitude_do_texto(texto: str) -> bool:
    """Se o texto usa adjetivo que promete mudanca grande."""
    limpo = _normalizar(texto)
    return any(p in limpo for p in _MAGNITUDE)


@dataclass(frozen=True, slots=True)
class Medicao:
    """Resultado da leitura de uma serie em volta do efeito."""

    serie: str
    antes: float
    depois: float
    variacao: float
    direcao_medida: str


def _chave(fato: dict[str, Any]) -> tuple[Any, ...]:
    """Identifica a serie a que um fato pertence."""
    return (
        fato["source"],
        fato["entity"],
        fato["metric"],
        fato.get("dimension_type"),
        fato.get("dimension_value"),
    )


def _fact_id(fato: dict[str, Any]) -> str:
    """Mesmo identificador que o leitor expoe em `fact_id`."""
    return f"{fato['fact_key']}:{fato['version_lsn']}"


def medir_serie(
    fatos_citados: list[dict[str, Any]], chave: tuple[Any, ...], efeito: str
) -> Medicao | None:
    """Mede somente os pontos citados antes e depois do efeito."""
    try:
        instante = _instant(efeito)
    except ValueError:
        return None
    pontos = sorted(
        (
            f
            for f in fatos_citados
            if f["kind"] == "metric" and f["value"] is not None and _chave(f) == chave
        ),
        key=lambda f: f["event_start"],
    )
    antes = [f["value"] for f in pontos if _instant(f["event_start"]) < instante]
    depois = [f["value"] for f in pontos if _instant(f["event_start"]) >= instante]
    if not antes or not depois:
        return None
    media_antes = sum(antes) / len(antes)
    media_depois = sum(depois) / len(depois)
    base = max(abs(media_antes), 1e-9)
    variacao = (media_depois - media_antes) / base
    if variacao >= LIMIAR_MUDANCA:
        direcao = "alta"
    elif variacao <= -LIMIAR_MUDANCA:
        direcao = "queda"
    else:
        direcao = "estavel"
    return Medicao(
        serie=f"{chave[0]}/{chave[2]}",
        antes=round(media_antes, 4),
        depois=round(media_depois, 4),
        variacao=round(variacao, 4),
        direcao_medida=direcao,
    )


def checar_evidencias(
    hipotese: dict[str, Any], leitor: CaseReader
) -> tuple[list[str], list[dict[str, Any]]]:
    """Confere cada evidencia contra a serie real.

    Returns:
        tuple[list[str], list[dict]]: problemas que contradizem o texto, e o
            registro de cada checagem (inclusive as indeterminadas) para revisao.
    """
    problemas: list[str] = []
    checagens: list[dict[str, Any]] = []
    efeito = hipotese.get("effect_start")
    por_id = {_fact_id(f): f for f in leitor.facts}
    for lado in ("evidence_for", "evidence_against"):
        for evidencia in hipotese.get(lado, []):
            texto = evidencia["observation"]
            registro: dict[str, Any] = {
                "lado": lado,
                "observation": texto,
                "status": "indeterminado",
                "reading": evidencia["reading"],
                "interpretacao": "revisao_humana",
            }
            # Um fact_id que o leitor nao conhece torna a checagem indeterminada: nao
            # da para saber a qual serie ele pertence, entao nao se contradiz ninguem.
            desconhecidos = [i for i in evidencia["fact_ids"] if i not in por_id]
            chaves = {_chave(por_id[i]) for i in evidencia["fact_ids"] if i in por_id}
            direcao = direcao_do_texto(texto)
            if not efeito or desconhecidos or len(chaves) != 1 or direcao is None:
                checagens.append(registro)
                continue
            medicao = medir_serie(
                [por_id[i] for i in evidencia["fact_ids"]], next(iter(chaves)), efeito
            )
            if medicao is None:
                checagens.append(registro)
                continue
            registro.update(
                serie=medicao.serie,
                antes=medicao.antes,
                depois=medicao.depois,
                variacao=medicao.variacao,
                direcao_afirmada=direcao,
                direcao_medida=medicao.direcao_medida,
            )
            if direcao != medicao.direcao_medida:
                registro["status"] = "contradito"
                problemas.append(
                    f"checagem numerica: '{texto}' afirma {direcao}, mas {medicao.serie} "
                    f"foi de {medicao.antes} para {medicao.depois} "
                    f"({medicao.variacao:+.0%}), que e {medicao.direcao_medida}"
                )
            elif magnitude_do_texto(texto) and abs(medicao.variacao) < LIMIAR_MAGNITUDE:
                registro["status"] = "exagero"
                problemas.append(
                    f"checagem numerica: '{texto}' usa adjetivo de magnitude "
                    f"(ex.: 'significativo'), mas {medicao.serie} variou "
                    f"{medicao.variacao:+.0%} (de {medicao.antes} para "
                    f"{medicao.depois}); tire o adjetivo e descreva a variacao pelo "
                    f"tamanho real -- adjetivo de magnitude so vale a partir de "
                    f"{LIMIAR_MAGNITUDE:.0%}"
                )
            else:
                registro["status"] = "coerente_com_citacoes"
            checagens.append(registro)
    return problemas, checagens
