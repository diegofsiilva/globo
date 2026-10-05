"""Contratos de entrada e saida do piloto.

Tres contratos convivem aqui, e a separacao entre eles e deliberada:

1.  `ESQUEMA_PASSO` e o unico formato que o MODELO pode produzir. Ele cobre um
    passo da investigacao: consultar uma ferramenta, concluir com uma hipotese
    ou desistir por falta de evidencia. E o schema entregue ao Ollama no campo
    `format`, e e revalidado em Python porque `format` restringe a geracao, nao
    garante semantica.
2.  O contrato de LEITURA -- nomes das ferramentas, argumentos aceitos e
    envelope de resposta -- nao e definido aqui. Ele vive em
    `artefatos/arquitetura-agente-hipoteses-ia.md`, secao 3.4, e e implementado
    pelo `CaseReader` de `leitor.py`. Este modulo apenas repete os
    nomes e argumentos para poder validar o que o modelo pede antes de chamar.
3.  `RegistroDoCaso` e o envelope que o EXECUTOR escreve. O historico de
    consultas mora nele, e nao na resposta do modelo: um historico narrado pelo
    proprio modelo nao serve de rastro.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_VERSION = "2.0.0"

# Os nomes sao os da secao 3.4 do documento de arquitetura. Mudar um deles aqui
# sem mudar o leitor quebra o despacho em silencio.
FERRAMENTAS = ("inventariar_fatos", "consultar_serie", "consultar_contexto")
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
DESFECHO_HIPOTESE = "hipotese"
DESFECHO_INSUFICIENTE = "evidencia_insuficiente"
DESFECHO_TETO = "teto_atingido"
DESFECHO_INVALIDA = "resposta_invalida"
DESFECHO_ERRO = "erro_de_execucao"

DESFECHOS = (
    DESFECHO_HIPOTESE,
    DESFECHO_INSUFICIENTE,
    DESFECHO_TETO,
    DESFECHO_INVALIDA,
    DESFECHO_ERRO,
)

# Desfechos que entregam material para a revisao humana. O lote usa isto para
# separar "o piloto respondeu" de "o piloto nao conseguiu responder".
DESFECHOS_UTEIS = (DESFECHO_HIPOTESE, DESFECHO_INSUFICIENTE)

# Limite de texto livre. E o mesmo do schema: um validador que aceitasse mais
# do que o schema permite deixaria passar texto que o modelo nunca deveria ter
# conseguido gerar.
MAX_TEXTO = 300

_TEXTO_CURTO = {"type": "string", "maxLength": MAX_TEXTO}

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

# Uniao dos argumentos das tres ferramentas da secao 3.4. O validador recusa,
# por ferramenta, o que nao pertence a ela -- o schema so impede o modelo de
# inventar um nome de argumento novo.
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
        "kinds": {
            "type": "array",
            "maxItems": 2,
            "items": {"enum": ["metric", "context"]},
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        "cursor": {"type": "string", "maxLength": 512},
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
class Recorte:
    """Identidade imutavel do conjunto de fatos visivel em uma investigacao.

    Os valores vem do `CaseReader`, nao sao recalculados aqui. `digest` resume
    os `fact_id` e os papeis efetivamente expostos; `recorte_id` e o
    identificador opaco que as ferramentas carregam de volta em cada resposta.
    Duas execucoes com o mesmo digest viram os mesmos fatos -- e so com ele a
    comparacao com o motor deterministico fala do mesmo material.
    """

    checkpoint_id: str
    origin: str
    sim_now: dt.datetime
    input_lsn: int
    recorte_id: str
    digest: str

    def para_json(self) -> dict[str, Any]:
        """Serializa o recorte para o registro do caso.

        Returns:
            dict[str, Any]: Campos do recorte com o instante em ISO-8601.
        """
        corpo = asdict(self)
        corpo["sim_now"] = self.sim_now.isoformat()
        return corpo


@dataclass(frozen=True, slots=True)
class Caso:
    """Um recorte mais o inventario entregue ao agente no inicio do ciclo."""

    case_id: str
    recorte: Recorte
    # Envelope devolvido por `inventariar_fatos`: a unica visao global que o
    # agente recebe. Diz o que existe e onde ha nulos, nunca o que esta anormal.
    inventario: dict[str, Any]
    # Texto curto que situa o investigador (ex.: "janela de 3 h em um dia util").
    # Nao pode conter anomalia, causa nem rotulo de incidente.
    nota_de_escopo: str = ""


@dataclass(frozen=True, slots=True)
class ConsultaRegistrada:
    """Uma chamada de ferramenta como ela entra no rastro do caso."""

    ordem: int
    ferramenta: str
    argumentos: dict[str, Any]
    retornadas: int
    fact_ids: tuple[str, ...]
    duracao_ms: int
    tem_mais: bool = False
    limitacoes: tuple[str, ...] = ()
    erro: str | None = None

    def para_json(self) -> dict[str, Any]:
        """Serializa a consulta para o arquivo do caso.

        Returns:
            dict[str, Any]: Listas no lugar das tuplas, pronto para `json.dump`.
        """
        corpo = asdict(self)
        corpo["fact_ids"] = list(self.fact_ids)
        corpo["limitacoes"] = list(self.limitacoes)
        return corpo


@dataclass(slots=True)
class RegistroDoCaso:
    """O que o piloto grava por caso investigado.

    Guarda o suficiente para reexecutar e para conferir: identidade do recorte,
    modelo e versao do prompt, a entrada entregue ao modelo, toda consulta
    feita, o raciocinio declarado em cada passo, a hipotese, o veredito do
    validador e os numeros de consumo.
    """

    case_id: str
    schema_version: str = SCHEMA_VERSION
    criado_em: str = ""
    recorte: dict[str, Any] = field(default_factory=dict)
    modelo: dict[str, Any] = field(default_factory=dict)
    prompt_version: str = ""
    # Mensagem de abertura exatamente como o modelo a recebeu. Sem ela, um
    # resultado estranho nao pode ser atribuido a entrada ou ao modelo.
    entrada: str = ""
    desfecho: str = DESFECHO_ERRO
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

    def __post_init__(self) -> None:
        """Recusa um desfecho fora do catalogo.

        Raises:
            ValueError: Se `desfecho` nao for um dos `DESFECHOS`.
        """
        if self.desfecho not in DESFECHOS:
            raise ValueError(f"desfecho desconhecido: {self.desfecho!r}")

    @property
    def util(self) -> bool:
        """Se o caso produziu material para a revisao humana."""
        return self.desfecho in DESFECHOS_UTEIS

    def concluir(self, desfecho: str, *, motivo: str | None = None) -> None:
        """Fixa o desfecho do caso, recusando valor fora do catalogo.

        Args:
            desfecho (str): Um dos `DESFECHOS`.
            motivo (str | None): Detalhe curto gravado no relatorio.

        Raises:
            ValueError: Se o desfecho nao estiver no catalogo.
        """
        if desfecho not in DESFECHOS:
            raise ValueError(f"desfecho desconhecido: {desfecho!r}")
        self.desfecho = desfecho
        self.motivo = motivo

    def para_json(self) -> dict[str, Any]:
        """Converte o registro em um dicionario serializavel.

        Returns:
            dict[str, Any]: Copia do registro pronta para `json.dump`.
        """
        return asdict(self)
