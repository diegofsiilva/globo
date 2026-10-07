"""Verifica o recorte temporal e as ferramentas do executor sintético."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from argus_agente.leitor import CaseReader, run_case

FIXTURES = Path(__file__).parents[1] / "fixtures" / "sinteticos"


def _load(name: str) -> dict:
    """Lê um caso sintético versionado sem depender de banco."""
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class SyntheticCaseTests(unittest.TestCase):
    """Exercita os limites que impedem vazamento e referências ambíguas."""

    def test_excludes_late_old_and_deleted_facts(self) -> None:
        """O recorte usa a versão mais recente elegível e respeita tombstones."""
        reader = CaseReader(_load("degradacao_sintetica"))
        ids = {fact["fact_key"][0]: fact["version_lsn"] for fact in reader.facts}
        self.assertEqual(ids, {"a": 18, "b": 12, "c": 15})
        self.assertEqual(len(reader.inventariar_fatos()["items"]), 2)

    def test_digest_and_output_are_reproducible(self) -> None:
        """A mesma entrada devolve digest e respostas iguais."""
        case = _load("degradacao_sintetica")
        self.assertEqual(run_case(case), run_case(case))
        self.assertEqual(run_case(case)["origin"], "synthetic")

    def test_series_keeps_null_and_context_can_be_empty(self) -> None:
        """Ausência de medida ou contexto não vira zero ou evidência favorável."""
        result = run_case(_load("evidencia_insuficiente"))
        series, context = result["responses"][1:]
        self.assertIsNone(series["items"][0]["value"])
        self.assertEqual(context["items"], [])
        self.assertIn("sem_fatos_no_recorte_consultado", context["limitations"])

    def test_pagination_binds_cursor_to_filters(self) -> None:
        """Cursor não pode mudar a série nem pular o recorte."""
        reader = CaseReader(_load("degradacao_sintetica"))
        query = {
            "source": "prometheus",
            "entity": "playback-api",
            "metric": "error_rate_pct",
            "inicio": "2026-08-20T19:00:00Z",
            "fim": "2026-08-20T20:00:00Z",
            "limit": 1,
        }
        first = reader.consultar_serie(**query)
        self.assertTrue(first["has_more"])
        second = reader.consultar_serie(**query, cursor=first["next_cursor"])
        self.assertNotEqual(first["items"], second["items"])
        with self.assertRaisesRegex(ValueError, "cursor"):
            reader.consultar_serie(
                **{**query, "inicio": "2026-08-20T19:15:00Z"},
                cursor=first["next_cursor"],
            )

    def test_rejects_future_window(self) -> None:
        """Consulta não pode avançar além do presente do checkpoint."""
        reader = CaseReader(_load("degradacao_sintetica"))
        with self.assertRaisesRegex(ValueError, "janela"):
            reader.consultar_contexto(
                entity="playback-api",
                inicio="2026-08-20T19:00:00Z",
                fim="2026-08-20T20:01:00Z",
            )

    def test_database_scope_has_distinct_recorte_id(self) -> None:
        """Cursores de um recorte sintético não passam para o recorte real."""
        case = _load("degradacao_sintetica")
        synthetic = CaseReader(case)
        case["origin"] = "database"
        database = CaseReader(case)
        self.assertEqual(synthetic.digest, database.digest)
        self.assertNotEqual(synthetic.recorte_id, database.recorte_id)


if __name__ == "__main__":
    unittest.main()
