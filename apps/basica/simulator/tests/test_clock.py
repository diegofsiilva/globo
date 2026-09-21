"""Regressoes do ciclo de vida do relogio virtual."""

from __future__ import annotations

import datetime as dt

from argus_simulator.clock import Clock


class FakeDB:
    """Captura a chamada SQL sem fingir o comportamento do PostgreSQL."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def fetch_one(self, statement: str, params: tuple):
        self.calls.append((statement, params))
        return {"agora": params[2]}


def test_fechar_run_fecha_e_pausa_na_mesma_funcao() -> None:
    db = FakeDB()
    clock = Clock(db)

    clock.fechar_run(7, "paused")

    statement, params = db.calls[-1]
    assert "sim.close_run" in statement
    assert params == (7, "paused", None)


def test_run_concluida_congela_exatamente_em_t1() -> None:
    db = FakeDB()
    clock = Clock(db)
    t1 = dt.datetime(2026, 8, 5, 23, 59, 59, tzinfo=dt.UTC)

    clock.fechar_run(8, "done", t1)

    _, params = db.calls[-1]
    assert params == (8, "done", t1)
