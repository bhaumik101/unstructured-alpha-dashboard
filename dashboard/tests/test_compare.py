"""Comparing two portfolios: current against proposed.

The question an adviser brings to a review is rarely "what is this exposed
to" on its own; it is "what does moving from this to that do". These tests pin
what makes the answer honest — the same method on both sides, no difference
invented out of two noisy readings — and what makes it usable: the trade list,
and a link that reopens the same comparison.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_exposure import _BANNED, HOLDINGS, _report  # noqa: E402
from utils import report_ui as ui  # noqa: E402


@pytest.fixture(scope="module")
def report():
    r = _report()
    assert r["status"] == "ok"
    return r


def _visible(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def test_the_comparison_names_both_sides_and_every_force(report):
    html = ui.comparison_html(report, report, "Current", "Proposed")
    assert "Current" in html and "Proposed" in html
    for reading in report["portfolio"]["readings"].values():
        assert reading["label"] in html


def test_a_difference_is_not_invented_out_of_two_noisy_readings():
    noisy = lambda impact: {"portfolio": {"readings": {"oil": {  # noqa: E731
        "label": "Oil and energy", "impact": impact, "evidence": "indistinct"}}},
        "top_exposures": []}
    html = ui.comparison_html(noisy(0.4), noisy(-0.9), "A", "B")
    assert "no measurable link either way" in html
    assert "1.3" not in html


def test_nothing_in_the_comparison_advises_or_forecasts(report):
    text = re.sub(r"(?:is|are) not a forecast", "", _visible(
        ui.comparison_html(report, report, "Current", "Proposed")))
    assert not _BANNED.search(text), _BANNED.search(text).group(0)


def test_the_what_if_and_the_comparison_share_one_rule():
    """The try-a-holding card and the comparison page must never disagree on
    when a difference is real, so they are built from the same rows."""
    source = (_ROOT / "utils" / "report_ui.py").read_text(encoding="utf-8")
    for fn in ("def candidate_delta_html", "def comparison_html"):
        block = source[source.index(fn):]
        block = block[: block.index("\ndef ", 10)]
        assert "_comparison_rows(" in block, fn


def test_a_portfolio_can_be_named_anything_without_breaking_the_page():
    html = ui.comparison_html({"portfolio": {"readings": {}}}, {"portfolio": {"readings": {}}},
                              "<script>x</script>", "B")
    assert "<script>" not in html


# ── the trade list ──────────────────────────────────────────────────────────

def test_the_trade_list_shows_what_was_added_removed_and_resized():
    a = (("VTI", 60.0), ("BND", 40.0))
    b = (("VTI", 40.0), ("BND", 30.0), ("GLD", 30.0))
    html = ui.holdings_diff_html(a, b, "Current", "Proposed")
    assert "GLD" in html and "added" in html
    assert "−20.0 pts" in html and "−10.0 pts" in html
    # largest change first
    assert html.index("GLD") < html.index("VTI") < html.index("BND")


def test_a_removed_holding_is_named_as_removed():
    html = ui.holdings_diff_html((("VTI", 50.0), ("XOM", 50.0)), (("VTI", 100.0),), "A", "B")
    assert "XOM" in html and "removed" in html


def test_identical_holdings_say_so_rather_than_drawing_an_empty_table():
    same = (("VTI", 60.0), ("BND", 40.0))
    assert "the same things" in ui.holdings_diff_html(same, same, "A", "B")


# ── the page ────────────────────────────────────────────────────────────────

@pytest.fixture
def synthetic_engine(monkeypatch):
    from datetime import date

    from tests.test_exposure import _daily_world
    from utils import exposure as ex

    def fake_live(holdings, max_holdings=ex.MAX_HOLDINGS):
        pf, sf = _daily_world()
        return ex.build_exposure_report(holdings, pf, sf, end=date(2026, 9, 11),
                                        max_holdings=max_holdings)

    monkeypatch.setattr(ex, "build_live_report", fake_live)
    ui._cached_ok_report.clear()
    yield
    ui._cached_ok_report.clear()


def _page(monkeypatch, query=None, state=None):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from tests.conftest import DASHBOARD_ROOT

    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    at = AppTest.from_file(str(DASHBOARD_ROOT / "pages/66_Compare.py"), default_timeout=120)
    for k, v in (query or {}).items():
        at.query_params[k] = v
    for k, v in (state or {}).items():
        at.session_state[k] = v
    at.run()
    return at


def _text(at) -> str:
    return " ".join([m.value for m in at.markdown] + [c.value for c in at.caption]
                    + [w.value for w in at.warning] + [e.value for e in at.error])


def test_a_shared_link_opens_straight_into_its_comparison(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, query={"a": "TLT:50,VTI:50", "b": "TLT:40,XOM:30,VTI:30"})
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    text = _text(at)
    assert "What separates them" in text and "The trade between them" in text
    assert "XOM" in text


def test_comparing_a_portfolio_with_itself_is_explained(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, query={"a": "TLT:50,VTI:50", "b": "VTI:50,TLT:50"})
    assert not at.exception
    assert "the same portfolio" in _text(at)


def test_the_report_portfolio_is_offered_as_side_a(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, state={"uar_holdings": HOLDINGS, "uar_name": "Client IRA"})
    assert not at.exception
    assert at.radio(key="cmp_src_A").value == "The portfolio on the report"


def test_the_page_is_in_the_nav_and_wears_the_theme():
    from utils.app_theme import is_product_page

    assert is_product_page("/app/pages/66_Compare.py")
    header = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")
    assert 'href="/compare"' in header
    assert 'url_path="compare"' in (_ROOT / "app.py").read_text(encoding="utf-8")


def test_the_open_dropdown_is_themed_where_it_actually_renders():
    """The open list of a select box is a BaseWeb portal outside .stApp — the
    same trap as the sign-in panel. A .stApp-scoped rule never reaches it:
    measured, it rendered #0b0d12 with #e8eeff text on the light page."""
    from utils.app_theme import PRODUCT_CSS

    rules = [line for line in PRODUCT_CSS.splitlines() if "stSelectboxVirtualDropdown" in line]
    assert rules
    assert not any(".stApp" in line for line in rules), rules
    assert '[data-baseweb="select"] > div' in PRODUCT_CSS


# ── benchmarks ──────────────────────────────────────────────────────────────

def test_benchmarks_are_real_mixes_and_not_the_market_itself():
    """The S&P 500's own readings are zero by construction (every reading is
    beyond the market), so it is not offered; each benchmark is a mix that
    adds to 100."""
    from utils import exposure as ex

    assert ex.DEFAULT_BENCHMARK in ex.BENCHMARK_PORTFOLIOS
    for name, rows in ex.BENCHMARK_PORTFOLIOS.items():
        assert sum(r["weight_pct"] for r in rows) == 100, name
        assert [r["ticker"] for r in rows] != [ex.MARKET_TICKER], name


def test_a_benchmark_can_be_chosen_as_a_side(monkeypatch, synthetic_engine):
    from utils import exposure as ex

    at = _page(monkeypatch, state={"uar_holdings": HOLDINGS, "uar_name": "Client IRA"})
    at.radio(key="cmp_src_B").set_value("A benchmark").run()
    at.button(key="cmp_go").click().run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    _rows_a, _name_a, rows_b, name_b = at.session_state["cmp_pending"]
    assert name_b == ex.DEFAULT_BENCHMARK
    assert rows_b == ex.BENCHMARK_PORTFOLIOS[ex.DEFAULT_BENCHMARK]


def test_the_report_opens_straight_into_a_benchmark_comparison(monkeypatch, synthetic_engine):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from tests.conftest import DASHBOARD_ROOT
    from utils import exposure as ex

    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    monkeypatch.setattr(st, "switch_page",
                        lambda p, *a, **k: st.session_state.__setitem__("_test_switch_page", p))
    at = AppTest.from_file(str(DASHBOARD_ROOT / "pages/60_Exposure_Report.py"), default_timeout=120)
    at.session_state["uar_holdings"] = HOLDINGS
    at.session_state["uar_name"] = "Client IRA"
    at.run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    at.button(key="uar_to_benchmark").click().run()
    rows_a, name_a, rows_b, name_b = at.session_state["cmp_pending"]
    assert name_a == "Client IRA"
    assert sorted(r["ticker"] for r in rows_a) == sorted(h["ticker"] for h in HOLDINGS)
    assert (rows_b, name_b) == (ex.BENCHMARK_PORTFOLIOS[ex.DEFAULT_BENCHMARK], ex.DEFAULT_BENCHMARK)
    assert at.session_state["_test_switch_page"].endswith("66_Compare.py")
