"""The stock library: every single stock the engine measures, kept.

Run against a real SQLite database, not a fake engine, because what matters
here is the SQL itself: the per-week upsert, and "the newest week of every
stock", which is a join a fake would simply pretend to do.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_exposure import _report  # noqa: E402
from utils import stock_library as lib  # noqa: E402


@pytest.fixture
def library(monkeypatch, tmp_path):
    from utils import db

    engine = create_engine(f"sqlite:///{tmp_path / 'lib.db'}")
    db.metadata.create_all(engine, tables=[db.stock_measurements, db.stock_exposures])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    return engine


@pytest.fixture(scope="module")
def one_stock():
    r = _report(holdings=[{"ticker": "XOM", "weight_pct": 100}])
    assert r["status"] == "ok"
    return r


def _week(report: dict, as_of: str, scale: float = 1.0) -> dict:
    r = copy.deepcopy(report)
    r["as_of"] = as_of
    for reading in r["portfolio"]["readings"].values():
        for k in ("impact", "low", "high"):
            reading[k] *= scale
    return r


def _count(engine, table) -> int:
    with engine.begin() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar()


def test_a_one_stock_report_is_filed_with_every_measured_force(library, one_stock):
    from utils import db

    assert lib.record(one_stock, "Exxon Mobil")
    hist = lib.history("xom")
    assert len(hist) == 1 and hist[0]["name"] == "Exxon Mobil"
    assert hist[0]["as_of"] == one_stock["as_of"]
    assert set(hist[0]["exposures"]) == set(one_stock["portfolio"]["readings"])
    oil = hist[0]["exposures"]["oil"]
    assert oil["impact"] == pytest.approx(one_stock["portfolio"]["readings"]["oil"]["impact"])
    assert _count(library, db.stock_measurements) == 1


def test_a_portfolio_is_never_filed_under_one_of_its_holdings(library):
    """A portfolio's exposure is not a company's."""
    portfolio = _report()
    assert portfolio["status"] == "ok" and len(portfolio["positions"]) > 1
    assert lib.record(portfolio, "Balanced") is False
    assert lib.latest() == []


def test_viewing_the_same_week_twice_updates_rather_than_duplicates(library, one_stock):
    from utils import db

    assert lib.record(one_stock, "Exxon Mobil")
    assert lib.record(_week(one_stock, one_stock["as_of"], 2.0), "")
    assert _count(library, db.stock_measurements) == 1
    assert _count(library, db.stock_exposures) == len(one_stock["portfolio"]["readings"])
    hist = lib.history("XOM")
    assert hist[0]["name"] == "Exxon Mobil", "a later write without a name must not erase it"
    assert hist[0]["exposures"]["oil"]["impact"] == pytest.approx(
        2.0 * one_stock["portfolio"]["readings"]["oil"]["impact"])


def test_each_new_data_week_adds_to_the_history(library, one_stock):
    lib.record(_week(one_stock, "2026-09-04"), "Exxon Mobil")
    lib.record(_week(one_stock, "2026-09-11"), "Exxon Mobil")
    lib.record(_week(one_stock, "2026-09-18"), "Exxon Mobil")
    assert [h["as_of"] for h in lib.history("XOM")] == ["2026-09-18", "2026-09-11", "2026-09-04"]


def test_latest_is_the_newest_week_of_each_stock(library, one_stock):
    lib.record(_week(one_stock, "2026-09-04", 0.5), "Exxon Mobil")
    lib.record(_week(one_stock, "2026-09-18", 1.0), "Exxon Mobil")
    other = copy.deepcopy(one_stock)
    other["positions"] = [{"ticker": "CVX", "weight_pct": 100.0}]
    lib.record(_week(other, "2026-09-11"), "Chevron")
    latest = {s["ticker"]: s for s in lib.latest()}
    assert set(latest) == {"XOM", "CVX"}
    assert latest["XOM"]["as_of"] == "2026-09-18"
    assert latest["XOM"]["exposures"]["oil"]["impact"] == pytest.approx(
        one_stock["portfolio"]["readings"]["oil"]["impact"])


def test_a_force_that_was_not_measured_is_not_stored(library, one_stock):
    """Signal integrity: a failed series is excluded, never filled in."""
    r = copy.deepcopy(one_stock)
    del r["portfolio"]["readings"]["oil"]
    lib.record(r, "Exxon Mobil")
    assert "oil" not in lib.history("XOM")[0]["exposures"]


def test_a_failed_report_writes_nothing(library):
    assert lib.record({"status": "error", "message": "provider down"}) is False
    assert lib.latest() == []


def test_ranking_leaves_out_readings_that_could_be_noise(library, one_stock):
    lib.record(one_stock, "Exxon Mobil")
    readings = one_stock["portfolio"]["readings"]
    for key, reading in readings.items():
        ranked = lib.ranked(key)
        shown = ranked["up"] + ranked["down"]
        if reading["evidence"] in lib.STANDS_UP:
            assert [r["ticker"] for r in shown] == ["XOM"], key
            side = "up" if reading["impact"] > 0 else "down"
            assert ranked[side][0]["name"] == "Exxon Mobil"
        else:
            assert shown == [], f"{key} is indistinguishable from zero and must not rank"


def test_recording_never_raises_when_the_database_is_down(monkeypatch, one_stock):
    from utils import db

    class Down:
        def begin(self):
            raise ConnectionError("database unreachable")

    monkeypatch.setattr(db, "engine", Down())
    assert lib.record(one_stock, "Exxon Mobil") is False
    assert lib.history("XOM") == [] and lib.latest() == []
