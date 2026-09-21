"""Carregamento e hash dos catalogos versionados do motor."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MetricPolicy:
    """Como uma metrica deve ser tratada pelo detector.

    Cada metrica tem comportamento estatistico proprio. Latencia tem cauda
    longa e so importa quando SOBE; taxa de reproducao e aproximadamente
    simetrica e so importa quando DESCE. Aplicar o mesmo tratamento a todas
    produziria anomalia onde nao ha e silencio onde ha.

    `sigma_floor` e um piso para o desvio-padrao: sem ele, uma serie que ficou
    constante por horas teria desvio proximo de zero, e a menor variacao viraria
    z-score enorme.
    """

    direction: str
    transform: str
    materiality_absolute: float
    materiality_relative: float
    sigma_floor: float


class Catalog:
    """Catalogos validados, com identidade canonica unica."""

    def __init__(self, code_version: str = "local") -> None:
        """Carrega os cinco catalogos e calcula o hash do manifesto.

        O `manifest_hash` e o que amarra um resultado de analise a EXATAMENTE a
        configuracao que o produziu -- catalogos, pesos do score e parametros do
        detector. Duas execucoes com manifestos diferentes nao sao comparaveis,
        e o cursor de progresso e travado por `manifest_hash + stream_key`
        justamente por isso (AGENTS.md, regra 3).

        Args:
            code_version (str): Versao do codigo que entra no manifesto. Um
                ajuste na logica das regras muda o resultado sem mudar nenhum
                catalogo; sem isto no hash, o motor retomaria de um cursor que
                pertence a outra versao.
        """
        base = importlib.resources.files("argus_processing").joinpath("catalogs")
        self.raw: dict[str, Any] = {}
        for name in (
            "sources.json",
            "metrics.json",
            "entity_relations.json",
            "playback.json",
            "rules.json",
        ):
            self.raw[name] = json.loads(base.joinpath(name).read_text(encoding="utf-8"))

        self.manifest_payload = {
            "catalogs": self.raw,
            "code_version": code_version,
            "engine": "argus-rules-v1",
            "detector": {
                "alpha": 0.20,
                "cold_start": 12,
                "z_threshold": 3.5,
                "strength_cap_z": 6.0,
                "timezone": "America/Sao_Paulo",
            },
            "scoring": {
                "weights": {
                    "A": 0.25,
                    "T": 0.20,
                    "C": 0.20,
                    "E": 0.15,
                    "I": 0.15,
                    "Q": 0.05,
                },
                "contradiction_penalty": 30,
            },
        }
        canonical = json.dumps(
            self.manifest_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.manifest_hash = hashlib.sha256(canonical.encode()).hexdigest()

    def source(self, name: str) -> dict[str, Any]:
        """Configuracao de uma fonte, com queda para o padrao.

        Args:
            name (str): Nome da fonte.

        Returns:
            dict[str, Any]: A entrada da fonte, ou a `default` quando a fonte
                ainda nao foi catalogada -- fonte nova precisa ser avaliada com
                algum criterio, e nao ignorada em silencio.
        """
        return self.raw["sources.json"].get(name, self.raw["sources.json"]["default"])

    def metric(self, name: str) -> MetricPolicy | None:
        """Politica de uma metrica, por nome exato ou por token contido.

        A busca por token existe porque os nomes de metrica do dump variam por
        fonte (`p95_ms`, `latency_p95`, `playback_p95_ms`). Catalogar cada
        variante exigiria editar o catalogo a cada fonte nova.

        Args:
            name (str): Nome da metrica como veio da fonte.

        Returns:
            MetricPolicy | None: A politica, ou `None` quando a metrica nao e
                reconhecida -- nesse caso o detector a ignora, em vez de
                inventar uma direcao e um limiar.
        """
        exact = self.raw["metrics.json"].get("exact", {}).get(name)
        if exact:
            return MetricPolicy(**exact)
        lower = name.lower()
        for item in self.raw["metrics.json"].get("contains", []):
            if item["token"] in lower:
                return MetricPolicy(**item["policy"])
        return None

    def normalize_entity(self, value: str) -> str:
        """Reduz um nome de entidade a sua forma canonica.

        A mesma entidade aparece escrita de formas diferentes entre fontes
        (`POP-Fortaleza`, `pop_fortaleza`, `pop-fortaleza-01`). Sem
        normalizacao, a correlacao entre duas fontes nunca casaria, e o motor
        concluiria que os sintomas sao independentes.

        Args:
            value (str): Nome como veio da fonte.

        Returns:
            str: Forma canonica, em minusculas e com hifens.
        """
        normalized = value.strip().lower()
        aliases = self.raw["entity_relations.json"].get("aliases", {})
        if normalized in aliases:
            return aliases[normalized]
        for suffix in self.raw["entity_relations.json"].get("strip_suffixes", []):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break
        normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
        return aliases.get(normalized, normalized)

    def related(self, left: str, right: str) -> bool:
        """Diz se duas entidades se referem ao mesmo escopo, ou a um contido no outro.

        E o que permite correlacionar um sintoma num POP com um deploy no
        cluster que o contem. Sem a relacao de prefixo, so casariam nomes
        identicos, e a correlacao mais util -- a hierarquica -- ficaria de fora.

        Args:
            left (str): Uma entidade.
            right (str): A outra.

        Returns:
            bool: `True` quando sao a mesma entidade ou uma contem a outra.
        """
        left_n = self.normalize_entity(left)
        right_n = self.normalize_entity(right)
        if left_n == right_n:
            return True
        for relation in self.raw["entity_relations.json"].get("prefix_relations", []):
            parent = relation["parent"]
            prefix = relation["prefix"]
            if (left_n == parent and right_n.startswith(prefix)) or (
                right_n == parent and left_n.startswith(prefix)
            ):
                return True
        return False

    def playback_vhost(self, entity: str) -> bool:
        """Diz se a entidade e um vhost do caminho de reproducao.

        Args:
            entity (str): Nome da entidade.

        Returns:
            bool: `True` para vhost de playback. Distingue o que afeta o
                espectador do que e infraestrutura de apoio -- as duas coisas
                degradam, mas so a primeira e incidente para o operador.
        """
        return entity.lower() in set(self.raw["playback.json"]["vhosts"])

    def rule(self, family: str) -> dict[str, Any]:
        """Parametros de uma das 11 familias de hipotese.

        Args:
            family (str): Nome da familia.

        Returns:
            dict[str, Any]: Janelas, limiares e pesos da familia.

        Raises:
            KeyError: Se a familia nao existir no catalogo. Falhar alto e
                deliberado: uma familia sem parametro rodaria com defaults
                implicitos, e o resultado nao seria reproduzivel.
        """
        return self.raw["rules.json"][family]
