"""The main page as a dashboard: headline numbers, the most exposed stocks on
record, and what the forces did -- all read from what is already stored.

The rule that keeps it fast: opening the page never measures anything. The
panels read the stock library and the report cache; a panel with nothing
stored says so rather than showing something that looks like data.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_exposure import _report  # noqa: E402
from utils import dashboard_ui as dash  # noqa: E402
from utils import stock_library as lib  # noqa: E402


@pytest.fixture
def store(monkeypatch, tmp_path):
    from utils import db

    engine = create_engine(f"sqlite:///{tmp_path / 'home.db'}")
    db.metadata.create_all(engine, tables=[db.stock_measurements, db.stock_exposures,
                                           db.report_cache])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    return engine


@pytest.fixture
def no_measuring(monkeypatch):
    from utils import report_ui as ui

    def boom(*_a, **_k):
        raise AssertionError("the main page measured something on open")

    monkeypatch.setattr(ui, "get_report", boom)


@pytest.fixture(scope="module")
def xom():
    r = _report(holdings=[{"ticker": "XOM", "weight_pct": 100}])
    assert r["status"] == "ok"
    return r


def _page(monkeypatch, state=None):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from tests.conftest import DASHBOARD_ROOT

    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    at = AppTest.from_file(str(DASHBOARD_ROOT / "pages/60_Exposure_Report.py"), default_timeout=120)
    for k, v in (state or {}).items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    return at


def _text(at) -> str:
    return " ".join(m.value for m in at.markdown)


def test_a_first_visit_gets_the_dashboard_without_measuring_anything(
        monkeypatch, store, no_measuring, xom):
    from utils import exposure as ex

    lib.record(xom, "Exxon Mobil")
    text = _text(_page(monkeypatch))
    assert 'class="udb-tiles"' in text
    assert "Stocks on record" in text and '<div class="udb-v">1</div>' in text
    assert f'<div class="udb-v">{len(ex.FACTORS)}</div>' in text, "counted from the engine, not typed"
    assert "Most exposed stocks on record" in text


def test_an_empty_library_and_cache_say_so_plainly(monkeypatch, store, no_measuring):
    text = _text(_page(monkeypatch))
    assert '<div class="udb-v">0</div>' in text
    assert "No stock on record has a reading on interest rates that held up yet" in text
    assert "Shown once any report has been measured" in text


def test_the_forces_panel_reads_the_newest_cached_report(monkeypatch, store, no_measuring):
    from utils import report_cache

    assert report_cache.put((("VTI", 100.0),), 15, _report())
    text = _text(_page(monkeypatch))
    assert "Shown once any report has been measured" not in text
    assert "Interest rates" in text and "<svg" in text
    assert "this portfolio" not in text, "there is no portfolio on the dashboard yet"


def test_someone_changing_their_holdings_gets_the_editor_not_the_dashboard(
        monkeypatch, store, no_measuring):
    at = _page(monkeypatch, state={
        "uar_holdings": [{"ticker": "VTI", "weight_pct": 100}], "uar_editing": True})
    assert 'class="udb-tiles"' not in _text(at)


def test_a_signed_in_visitor_sees_their_saved_portfolios(monkeypatch, store, no_measuring):
    from utils import portfolio_workspace as pw

    monkeypatch.setattr(pw, "list_portfolios", lambda uid: [{"id": 1}, {"id": 2}, {"id": 3}])
    monkeypatch.setattr(pw, "get_default_holdings", lambda uid: [])
    at = _page(monkeypatch, state={"user": {"id": 7, "email": "a@example.com"},
                                   "_tier_7": "free", "_sync_done_7": True})
    text = _text(at)
    assert "Your saved portfolios" in text and '<div class="udb-v">3</div>' in text
    assert 'href="/portfolios"' in text


# ── the ranked panel ────────────────────────────────────────────────────────

def test_the_ranked_panel_links_each_stock_to_its_own_page(store, xom):
    lib.record(xom, "Exxon Mobil")
    oil = xom["portfolio"]["readings"]["oil"]
    assert oil["evidence"] in lib.STANDS_UP, "fixture: XOM's oil exposure is built in"
    html = dash.ranked_panel_html("oil", lib.ranked("oil"), lib.count())
    assert 'href="/stock?t=XOM"' in html and "Exxon Mobil" in html
    assert "Among the 1 stock on record" in html
    assert "it is not a forecast" in html


def test_newest_prefers_the_latest_fresh_report(store):
    from utils import report_cache

    a = copy.deepcopy(_report()); a["marker"] = "first"
    b = copy.deepcopy(_report()); b["marker"] = "second"
    report_cache.put((("AAA", 100.0),), 15, a)
    report_cache.put((("BBB", 100.0),), 15, b)
    assert report_cache.newest()["marker"] == "second"
