"""The single-stock page: one company's exposure, filed in the stock library.

Driven through AppTest with the measurement replaced by the fixture report and
the library pointed at a real SQLite file, so "viewing a stock stores it" is
checked end to end rather than by asserting a function was called.
"""

from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_exposure import _BANNED, _report  # noqa: E402
from utils import stock_library as lib  # noqa: E402
from utils import stock_ui as sui  # noqa: E402


@pytest.fixture(scope="module")
def xom():
    r = _report(holdings=[{"ticker": "XOM", "weight_pct": 100}])
    assert r["status"] == "ok"
    return r


@pytest.fixture
def library(monkeypatch, tmp_path):
    from utils import db

    engine = create_engine(f"sqlite:///{tmp_path / 'lib.db'}")
    db.metadata.create_all(engine, tables=[db.stock_measurements, db.stock_exposures])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    return engine


@pytest.fixture
def measured(monkeypatch, xom):
    from utils import report_ui as ui

    calls = []

    def fake(key, max_holdings):
        calls.append(key)
        r = copy.deepcopy(xom)
        r["positions"] = [{"ticker": key[0][0], "weight_pct": 100.0}]
        return r

    monkeypatch.setattr(ui, "get_report", fake)
    return calls


def _page(monkeypatch, path="pages/69_Stock.py", ticker=None, state=None):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from tests.conftest import DASHBOARD_ROOT

    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    monkeypatch.setattr(st, "switch_page",
                        lambda p, *a, **k: st.session_state.__setitem__("_test_switch_page", p))
    at = AppTest.from_file(str(DASHBOARD_ROOT / path), default_timeout=120)
    if ticker:
        at.query_params["t"] = ticker
    for k, v in (state or {}).items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    return at


def _text(at) -> str:
    return " ".join([m.value for m in at.markdown] + [c.value for c in at.caption]
                    + [b.label for b in at.button] + [e.value for e in at.error])


# ── wording ─────────────────────────────────────────────────────────────────

def test_the_engines_sentences_are_worded_for_a_company(xom):
    from utils import report_ui as ui

    text = sui.as_stock(ui.summary_text(xom))
    assert "this stock has been" in text or "this stock shows" in text
    assert "portfolio" not in text.lower()
    table = sui.as_stock(ui.exposure_table_html(xom))
    assert "this portfolio" not in table.lower()
    center = sui.as_stock(ui.exposure_map_html(xom), "XOM")
    assert '>XOM<' in center and ">one company<" in center and ">Portfolio<" not in center


# ── the page ────────────────────────────────────────────────────────────────

def test_viewing_a_stock_measures_it_once_and_files_it(monkeypatch, library, measured, xom):
    at = _page(monkeypatch, ticker="XOM")
    assert measured == [(("XOM", 100.0),)]
    text = _text(at)
    assert "Exxon Mobil" in text, "a known ticker is named"
    assert "first week of XOM on record" in text
    hist = lib.history("XOM")
    assert len(hist) == 1 and hist[0]["name"] == "Exxon Mobil"
    assert set(hist[0]["exposures"]) == set(xom["portfolio"]["readings"])


def test_a_second_week_on_record_draws_the_history(monkeypatch, library, measured, xom):
    earlier = copy.deepcopy(xom)
    earlier["as_of"] = "2026-08-28"
    lib.record(earlier, "Exxon Mobil")
    at = _page(monkeypatch, ticker="XOM")
    text = _text(at)
    assert 'class="usl-table"' in text
    assert "Aug 28, 2026" in text and "Sep 11, 2026" in text


def test_a_nonsense_ticker_is_refused_without_measuring(monkeypatch, library, measured):
    at = _page(monkeypatch, ticker="<script>")
    assert measured == []
    assert "doesn't look like a ticker" in _text(at)
    assert lib.latest() == []


def test_the_landing_state_lists_what_is_already_measured_without_measuring(
        monkeypatch, library, measured, xom):
    lib.record(xom, "Exxon Mobil")
    at = _page(monkeypatch)
    assert measured == [], "the landing state must not measure anything"
    text = _text(at)
    assert "Already measured here" in text and 'href="/stock?t=XOM"' in text
    assert "XOM · Exxon Mobil" in text


def test_nothing_on_the_page_forecasts_or_advises(monkeypatch, library, measured):
    at = _page(monkeypatch, ticker="XOM")
    # The page's own copy: not stylesheets, and not the site-wide structured
    # data the header injects (JSON inside a <script>, which says "Not a forecast.").
    body = re.sub(r"<[^>]+>", " ", " ".join(
        m.value for m in at.markdown if "<style>" not in m.value and "<script" not in m.value))
    # The disclaimer the report's table carries says so in the negative.
    body = re.sub(r"\bit is not a forecast\b", "", body)
    hit = _BANNED.search(body)
    assert not hit, f"forward-looking or advisory language: {body[max(0, hit.start() - 90):hit.end() + 20]!r}"


def test_build_a_portfolio_carries_the_stock_to_the_report(monkeypatch, library, measured):
    at = _page(monkeypatch, ticker="XOM")
    at.button(key="usl_to_report").click().run()
    assert at.session_state["uar_holdings"] == [{"ticker": "XOM", "weight_pct": 100}]
    assert [r["ticker"] for r in at.session_state["uar_draft"]] == ["XOM"]
    assert at.session_state["_test_switch_page"].endswith("60_Exposure_Report.py")


def test_the_reports_single_company_buttons_open_the_stock_page(monkeypatch, library, measured):
    at = _page(monkeypatch, path="pages/60_Exposure_Report.py")
    at.button(key="uar_one_XOM").click().run()
    assert at.session_state["ua_stock_ticker"] == "XOM"
    assert at.session_state["_test_switch_page"].endswith("69_Stock.py")


def test_the_handoff_lands_on_that_stock(monkeypatch, library, measured):
    at = _page(monkeypatch, state={"ua_stock_ticker": "CAT", "ua_stock_name_CAT": "Caterpillar"})
    assert measured == [(("CAT", 100.0),)]
    assert at.query_params["t"] == ["CAT"] or at.query_params["t"] == "CAT"
    assert lib.history("CAT")[0]["name"] == "Caterpillar"


def test_the_page_is_in_the_nav_and_wears_the_product_theme():
    from utils.app_theme import is_product_page

    header = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")
    assert '<a class="ua-tnav-item" href="/stock">Stocks</a>' in header
    assert 'url_path="stock"' in (_ROOT / "app.py").read_text(encoding="utf-8")
    assert is_product_page("pages/69_Stock.py")


def test_the_extra_nav_item_still_fits_a_1024px_screen():
    """Measured: "Stocks" overflowed the top bar by 33px at 1024px. Below
    1100px the items tighten rather than any being dropped."""
    from utils.app_theme import PRODUCT_CSS

    block = PRODUCT_CSS[PRODUCT_CSS.index("@media (max-width:1099px)"):]
    block = block[:block.index("}\n}") + 3]
    assert "ua-tnav-item" in block and "padding-left:6px!important" in block
    assert 'html:not([data-ua-theme="light"]) .ua-topnav' in block, (
        "it must carry the html[data-ua-theme] prefix to beat header.py's rules")
