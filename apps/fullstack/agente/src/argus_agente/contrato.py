"""Contratos de entrada e saida do piloto -- a entrega do Dia 2.

Tres contratos convivem aqui, e a separacao entre eles e deliberada:

1.  `ESQUEMA_PASSO` e o unico formato que o MODELO pode produzir. Ele cobre um
    passo da investigacao: consultar uma ferramenta, concluir com uma hipotese
    ou desistir por falta de evidencia. E o schema entregue ao Ollama no campo
    `format`, e e revalidado em Python porque `format` restringe a geracao, nao
    garante semantica.
2.  As dataclasses `Caso`, `ItemInventario` e `LinhaDeFato` descrevem o que o
    EXECUTOR entrega ao modelo. Nada aqui carrega anomalia, score ou hipotese do
    motor deterministico (artefatos/arquitetura-agente-hipoteses-ia.md, 4.3).
3.  `RegistroDoCaso` e o envelope que o EXECUTOR escreve. O historico de
    consultas mora nele, e nao na resposta do modelo: um historico narrado pelo
    proprio modelo nao serve de rastro.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "1.0.0"

FERRAMENTAS = ("inventario", "serie", "contexto")
ACOES = ("consultar", "concluir", "desistir")

# Por que a lacuna existe. Separar "o dado nao existe" de "o dado ainda nao
# chegou" e o que impede o piloto de tratar atraso de fonte como ausencia --
# NPAW chega com ate 28 h de atraso causal.
MOTIVOS_DE_LACUNA = (
    "sem_dado",
    "ainda_indisponivel",
    "fora_do_catalogo",
    "limite_de_ferramenta",
)

# Como o caso terminou. So os dois primeiros produzem material para a revisao
# humana; os tres ultimos sao limitacao do piloto e entram no lote como tal.
DESFECHOS = (
    "hipotese",
    "evidencia_insuficiente",
    "teto_atingido",
    "resposta_invalida",
    "erro_de_execucao",
)

_TEXTO_CURTO = {"type": "string", "maxLength": 300}

_EVIDENCIA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fact_ids", "observation", "reading"],
    "properties": {
        "fact_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {"type": "string", "maxLength": 120},
        },
        "observation": _TEXTO_CURTO,
        "reading": _TEXTO_CURTO,
    },
}

_LACUNA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["missing", "reason"],
    "properties": {
        "missing": _TEXTO_CURTO,
        "reason": {"enum": list(MOTIVOS_DE_LACUNA)},
    },
}

ESQUEMA_HIPOTESE = {
    "type": "object",
    "additionalProperties": False,
    "required": ["statement", "scope", "evidence_for", "evidence_against", "gaps"],
    "properties": {
        "statement": {"type": "string", "maxLength": 400},
        "scope": {
            "type": "object",
            "additionalProperties": False,
            "required": ["entity"],
            "properties": {
                "entity": {"type": "string", "maxLength": 128},
                "dimension_type": {"type": "string", "maxLength": 64},
                "dimension_value": {"type": "string", "maxLength": 128},
            },
        },
        "effect_start": {"type": "string", "maxLength": 32},
        "effect_end": {"type": "string", "maxLength": 32},
        # minItems=1: uma hipotese sem nenhuma evidencia a favor nao e hipotese,
        # e `desistir` ja existe para esse caso.
        "evidence_for": {
            "type": "array",
            "minItems": 1,
            "maxItems": 6,
            "items": _EVIDENCIA,
        },
        "evidence_against": {"type": "array", "maxItems": 6, "items": _EVIDENCIA},
        "gaps": {"type": "array", "maxItems": 6, "items": _LACUNA},
    },
}

_ARGUMENTOS = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "source": {"type": "string", "maxLength": 64},
        "entity": {"type": "string", "maxLength": 128},
        "metric": {"type": "string", "maxLength": 128},
        "dimension_type": {"type": "string", "maxLength": 64},
        "dimension_value": {"type": "string", "maxLength": 128},
        "inicio": {"type": "string", "maxLength": 32},
        "fim": {"type": "string", "maxLength": 32},
        "agregacao": {"enum": ["bruto", "media_por_bucket"]},
        "tipos": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string", "maxLength": 64},
        },
    },
}

ESQUEMA_PASSO = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "rationale"],
    "properties": {
        "action": {"enum": list(ACOES)},
        "rationale": {"type": "string", "maxLength": 600},
        "tool": {"enum": list(FERRAMENTAS)},
        "arguments": _ARGUMENTOS,
        "answer": ESQUEMA_HIPOTESE,
        "gaps": {"type": "array", "maxItems": 6, "items": _LACUNA},
    },
}


@dataclass(frozen=True, slots=True)
class ItemInventario:
    """Uma serie disponivel no recorte, com cobertura e sem juizo de valor.

    O inventario e a unica visao global que o agente recebe. Ele diz o que
    existe e onde faltam pontos, nunca o que esta anormal: marcar uma serie
    como suspeita devolveria ao executor a escolha que o piloto quer medir.
    """

    source: str
    entity: str
    metric: str
    dimension_type: str | None
    unidade: str | None
    pontos: int
    primeiro_evento: dt.datetime | None
    ultimo_evento: dt.datetime | None
    # Buckets sem ponto dentro da janela. Lacuna declarada e o que separa
    # "nao ha dado" de "o agente nao perguntou".
    buckets_vazios: int
    atraso_tipico_segundos: int | None


@dataclass(frozen=True, slots=True)
class Recorte:
    """Identidade imutavel do conjunto de fatos visivel em uma investigacao.

    `digest` e o resumo do conjunto selecionado. Duas execucoes com o mesmo
    digest viram os mesmos fatos -- e so com ele a comparacao com o motor
    deterministico, no Dia 6, fala do mesmo material.
    """

    checkpoint_id: str
    sim_now: dt.datetime
    input_lsn: int
    janela_inicio: dt.datetime
    janela_fim: dt.datetime
    digest: str


@dataclass(frozen=True, slots=True)
class Caso:
    """Um recorte mais o inventario entregue ao agente no inicio do ciclo."""

    case_id: str
    recorte: Recorte
    inventario: tuple[ItemInventario, ...]
    # Series que existem para esta janela mas ainda nao estao disponiveis, com
    # o instante em que estarao. Declarar o atraso e o que permite ao agente
    # registrar `ainda_indisponivel` em vez de tratar ausencia como normalidade
    # (artefatos/hipoteses.md, RT03). Expoe existencia e horario, nunca valor.
    lacunas_de_cobertura: tuple[dict[str, Any], ...] = ()
    # Texto curto que situa o investigador (ex.: "janela de 3 h em um dia util").
    # Nao pode conter anomalia, causa nem rotulo de incidente.
    nota_de_escopo: str = ""


@dataclass(frozen=True, slots=True)
class LinhaDeFato:
    """Uma linha devolvida por uma ferramenta, sempre rastreavel a um fato.

    `fact_id` e `"{fact_key}:{version_lsn}"`. Quando a ferramenta agrega, ela
    devolve em `fact_ids` todos os fatos que contribuiram -- sem isso a
    evidencia citada pelo modelo nao poderia ser conferida.
    """

    fact_id: str
    source: str
    entity: str
    metric: str
    event_start: dt.datetime
    available_at: dt.datetime
    value: float | None
    dimension_type: str | None = None
    dimension_value: str | None = None
    sample_size: int | None = None
    kind: str = "metric"
    fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RespostaDeFerramenta:
    """Resultado de uma chamada de ferramenta, com as razoes de truncamento."""

    linhas: tuple[LinhaDeFato, ...]
    truncada: bool = False
    # Preenchido quando a consulta e valida mas nao existe dado para ela.
    vazia_porque: str | None = None


@dataclass(frozen=True, slots=True)
class ConsultaRegistrada:
    """Uma chamada de ferramenta como ela entra no rastro do caso."""

    ordem: int
    ferramenta: str
    argumentos: dict[str, Any]
    linhas: int
    fact_ids: tuple[str, ...]
    duracao_ms: int
    truncada: bool = False
    erro: str | None = None


@dataclass(slots=True)
class RegistroDoCaso:
    """O que o piloto grava por caso investigado.

    Guarda o suficiente para reexecutar e para conferir: identidade do recorte,
    modelo e versao do prompt, toda consulta feita, o raciocinio declarado em
    cada passo, a hipotese, o veredito do validador e os numeros de consumo.
    """

    case_id: str
    schema_version: str = SCHEMA_VERSION
    criado_em: str = ""
    recorte: dict[str, Any] = field(default_factory=dict)
    modelo: dict[str, Any] = field(default_factory=dict)
    prompt_version: str = ""
    desfecho: str = "erro_de_execucao"
    hipotese: dict[str, Any] | None = None
    lacunas: list[dict[str, Any]] = field(default_factory=list)
    consultas: list[dict[str, Any]] = field(default_factory=list)
    passos: list[dict[str, Any]] = field(default_factory=list)
    validacao: dict[str, Any] = field(default_factory=dict)
    metricas: dict[str, Any] = field(default_factory=dict)
    # Hipotese entregue apesar de o proprio modelo ter registrado evidencia
    # contraria. Nao invalida o resultado; muda como a revisao o le.
    contestada: bool = False
    motivo: str | None = None

    def para_json(self) -> dict[str, Any]:
        """Converte o registro em um dicionario serializavel.

        Returns:
            dict[str, Any]: Copia do registro pronta para `json.dump`.
        """
        return asdict(self)
