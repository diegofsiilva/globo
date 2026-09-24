"""Verifica o lote de CDC que exercita o detector com um controle negativo."""

from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hypothesis_batch import generate_batch, validate_batch


class HypothesisBatchTests(unittest.TestCase):
    """Cobre o contrato do lote antes de qualquer envio ao laboratório."""

    def test_incident_and_control_have_causal_baselines(self) -> None:
        """As quatro séries têm 12 amostras antigas e uma amostra atual."""
        now = dt.datetime(2026, 7, 12, 15, 37, tzinfo=dt.UTC)
        batch = generate_batch(now, "lab-hyp-example")
        changes = batch["changes"]

        self.assertEqual(len(changes), 52)
        self.assertEqual(validate_batch(batch), None)
        self.assertEqual(len({tuple(change["pk"].values()) for change in changes}), 52)
        for change in changes:
            self.assertEqual(change["source_table"], "signal_bucket")
            self.assertEqual(change["op"], "i")
            self.assertEqual(
                change["after"], {**change["pk"], "value": change["after"]["value"]}
            )
            self.assertLessEqual(
                dt.datetime.fromtimestamp(change["pk"]["bts"] / 1000, dt.UTC), now
            )

        for cohort in ("incident", "control"):
            for source in ("prometheus", "apollo"):
                series = [
                    change
                    for change in changes
                    if change["pk"]["entity"] == f"lab-hyp-example-{cohort}"
                    and change["pk"]["source"] == source
                ]
                self.assertEqual(len(series), 13)
                self.assertEqual(len({change["pk"]["bts"] for change in series}), 13)
                hours = {
                    dt.datetime.fromtimestamp(change["pk"]["bts"] / 1000, dt.UTC)
                    .astimezone(ZoneInfo("America/Sao_Paulo"))
                    .hour
                    for change in series
                }
                self.assertEqual(len(hours), 1)
                self.assertEqual(
                    series[-1]["after"]["value"], 15.0 if cohort == "incident" else 1.0
                )

    def test_rejects_duplicate_primary_key(self) -> None:
        """Um erro no gerador não pode criar duas versões da mesma amostra."""
        batch = generate_batch(
            dt.datetime(2026, 7, 12, 15, 37, tzinfo=dt.UTC), "lab-hyp-example"
        )
        batch["changes"][1]["pk"] = dict(batch["changes"][0]["pk"])
        batch["changes"][1]["after"].update(batch["changes"][1]["pk"])
        with self.assertRaisesRegex(ValueError, "duplicada"):
            validate_batch(batch)

    def test_rejects_changed_control_value(self) -> None:
        """O controle não pode acidentalmente virar outro incidente."""
        batch = generate_batch(
            dt.datetime(2026, 7, 12, 15, 37, tzinfo=dt.UTC), "lab-hyp-example"
        )
        batch["changes"][-1]["after"]["value"] = 15.0
        with self.assertRaisesRegex(ValueError, "grupo"):
            validate_batch(batch)


if __name__ == "__main__":
    unittest.main()
