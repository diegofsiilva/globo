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
    direction: str
    transform: str
    materiality_absolute: float
    materiality_relative: float
    sigma_floor: float


class Catalog:
    """Catalogos validados, com identidade canonica unica."""

    def __init__(self, code_version: str = "local") -> None:
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
        return self.raw["sources.json"].get(name, self.raw["sources.json"]["default"])

    def metric(self, name: str) -> MetricPolicy | None:
        exact = self.raw["metrics.json"].get("exact", {}).get(name)
        if exact:
            return MetricPolicy(**exact)
        lower = name.lower()
        for item in self.raw["metrics.json"].get("contains", []):
            if item["token"] in lower:
                return MetricPolicy(**item["policy"])
        return None

    def normalize_entity(self, value: str) -> str:
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
        return entity.lower() in set(self.raw["playback.json"]["vhosts"])

    def rule(self, family: str) -> dict[str, Any]:
        return self.raw["rules.json"][family]
