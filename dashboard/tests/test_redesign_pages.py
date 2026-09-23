"""The redesigned journey, run through Streamlit's AppTest.

Network is blocked by conftest, so the live report builder is replaced with the
same engine fed synthetic data (tests/test_exposure.py). That exercises the real
page, the real presentation code and the real engine, and checks the states a
user can land in: onboarding, a finished report, an error, and saving.
"""

from __future__ import annotations

from datetime import date

import pytest

from tests.conftest import DASHBOARD_ROOT
from tests.test_exposure import HOLDINGS, _daily_world
from utils import exposure as ex
from utils import report_ui as ui

NEW_PAGES = ("pages/60_Exposure_Report.py", "pages/61_What_Changed.py", "pages/62_Alerts.py",
             "pages/63_Methodology.py", "pages/64_Research.py", "pages/65_Pricing.py")


@pytest.fixture
def synthetic_engine(monkeypatch):
    def fake_live(holdings, max_holdings=ex.MAX_HOLDINGS):
        pf, sf = _daily_world()
        return ex.build_exposure_report(holdings, pf, sf, end=date(2026, 9, 11), max_holdings=max_holdings)

    monkeypatch.setattr(ex, "build_live_report", fake_live)
    ui._cached_ok_report.clear()
    yield
    ui._cached_ok_report.clear()


def _page(monkeypatch, path, *, user=None, state=None):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    monkeypatch.setattr(st, "switch_page",
                        lambda p, *a, **k: st.session_state.__setitem__("_test_switch_page", p))
    at = AppTest.from_file(str(DASHBOARD_ROOT / path), default_timeout=120)
    if user:
        at.session_state["user"] = user
        at.session_state[f"_tier_{user['id']}"] = "free"
        at.session_state[f"_sync_done_{user['id']}"] = True
    for k, v in (state or {}).items():
        at.session_state[k] = v
    at.run()
    return at


def _text(at) -> str:
    return " ".join([m.value for m in at.markdown] + [b.label for b in at.button]
                    + [c.value for c in at.caption] + [i.value for i in at.info]
                    + [e.value for e in at.error] + [s.value for s in at.success])


@pytest.mark.parametrize("path", NEW_PAGES)
def test_every_new_page_renders_for_an_anonymous_visitor(monkeypatch, synthetic_engine, path):
    at = _page(monkeypatch, path)
    assert not at.exception, "\n".join(str(e) for e in at.exception)


def test_a_new_visitor_sees_onboarding_not_a_login_wall(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, "pages/60_Exposure_Report.py")
    text = _text(at)
    assert "Start from a sample" in text and "Measure exposure" in text
    assert "Sign in to" not in text


def test_pasting_holdings_produces_a_full_report(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, "pages/60_Exposure_Report.py")
    # Search by name is the default method now; pasting is the second tab.
    at.radio(key="uar_method").set_value("Paste a list").run()
    at.text_area(key="uar_text").set_value("TLT 40\nXOM 30\nVTI 30")
    at.button(key="uar_submit").click().run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    text = _text(at)
    assert "Exposure to economic forces" in text
    assert "clearly sensitive to" in text
    assert at.radio(key="uar_factor").options, "the per-factor detail selector is missing"


def test_choosing_a_factor_shows_the_holdings_behind_it(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, "pages/60_Exposure_Report.py",
               state={"uar_holdings": HOLDINGS, "uar_name": "Test"})
    at.radio(key="uar_factor").set_value("oil").run()
    assert not at.exception
    assert "XOM" in _text(at)


def test_an_unmeasurable_portfolio_shows_an_explained_error(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, "pages/60_Exposure_Report.py",
               state={"uar_holdings": [{"ticker": "ZZZZ", "weight_pct": 100}], "uar_name": "Test"})
    assert not at.exception
    text = _text(at)
    assert "couldn&#39;t measure this portfolio" in text or "couldn't measure this portfolio" in text
    assert "ZZZZ" in text


def test_saving_without_an_account_explains_how_rather_than_failing(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, "pages/60_Exposure_Report.py",
               state={"uar_holdings": HOLDINGS, "uar_name": "Test"})
    at.button(key="uar_save").click().run()
    assert not at.exception
    assert "Create a free account or sign in" in _text(at)


def test_what_changed_without_a_portfolio_points_to_the_report(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, "pages/61_What_Changed.py")
    assert not at.exception
    assert "No portfolio yet" in _text(at)
    at.button(key="wc_to_report").click().run()
    assert at.session_state["_test_switch_page"] == "pages/60_Exposure_Report.py"


def test_what_changed_with_a_portfolio_shows_recent_moves(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, "pages/61_What_Changed.py",
               state={"uar_holdings": HOLDINGS, "uar_name": "Test"})
    assert not at.exception
    assert "the portfolio returned" in _text(at)


def test_alerts_page_is_honest_that_alerts_do_not_exist_yet(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, "pages/62_Alerts.py")
    assert "in development" in _text(at)
    at = _page(monkeypatch, "pages/62_Alerts.py", user={"id": 7, "email": "a@b.c"})
    at.button(key="alerts_interest").click().run()
    assert not at.exception
    assert "on the list" in _text(at)


def test_pricing_marks_unbuilt_features_and_sells_no_advisor_checkout(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, "pages/65_Pricing.py")
    assert not at.exception
    text = _text(at)
    assert "IN DEVELOPMENT" in text and "Advisor pilot" in text


# ── building a portfolio by name ────────────────────────────────────────────

@pytest.fixture
def fake_search(monkeypatch):
    """The name lookup, without the network. Two funds a person would name."""
    from utils import symbol_search as sym

    rows = {
        "total stock": [{"ticker": "VTI", "name": "Vanguard Total Stock Market ETF",
                         "kind": "ETF", "exchange": "NYSEArca"}],
        "total bond": [{"ticker": "BND", "name": "Vanguard Total Bond Market ETF",
                        "kind": "ETF", "exchange": "NASDAQ"}],
    }
    monkeypatch.setattr(sym, "search_symbols",
                        lambda q, **k: (rows.get(q.lower(), []), "live" if q.lower() in rows else "none"))


def test_a_visitor_who_knows_no_tickers_can_still_build_a_portfolio(
        monkeypatch, synthetic_engine, fake_search):
    at = _page(monkeypatch, "pages/60_Exposure_Report.py")
    at.text_input(key="uar_query").set_value("total stock").run()
    at.button(key="uar_add_VTI").click().run()
    at.text_input(key="uar_query").set_value("total bond").run()
    at.button(key="uar_add_BND").click().run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)

    draft = at.session_state["uar_draft"]
    assert [r["ticker"] for r in draft] == ["VTI", "BND"]
    assert ui.draft_total(draft) == 100.0, "weights should start out split evenly"

    at.button(key="uar_submit").click().run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    assert "Exposure to economic forces" in _text(at)


def test_a_search_that_finds_nothing_says_so_instead_of_staying_blank(
        monkeypatch, synthetic_engine, fake_search):
    at = _page(monkeypatch, "pages/60_Exposure_Report.py")
    at.text_input(key="uar_query").set_value("qqzzxy").run()
    assert not at.exception
    assert "Nothing matched" in _text(at)


def test_the_same_holding_cannot_be_added_twice(monkeypatch, synthetic_engine, fake_search):
    at = _page(monkeypatch, "pages/60_Exposure_Report.py",
               state={"uar_draft": [{"ticker": "VTI", "name": "Vanguard", "weight_pct": 100.0}]})
    at.text_input(key="uar_query").set_value("total stock").run()
    at.button(key="uar_add_VTI").click().run()
    assert not at.exception
    assert "already in the list" in " ".join(w.value for w in at.warning)
    assert len(at.session_state["uar_draft"]) == 1


# ── the report survives a refresh, and a return visit ───────────────────────

def test_a_finished_report_puts_itself_in_the_address_bar(monkeypatch, synthetic_engine):
    """Without this a reload dropped the visitor back on an empty form, and the
    browser had nothing to remember the portfolio by."""
    at = _page(monkeypatch, "pages/60_Exposure_Report.py",
               state={"uar_holdings": HOLDINGS, "uar_name": "Test"})
    assert not at.exception
    param = at.query_params.get(ui.HOLDINGS_PARAM)
    if isinstance(param, list):        # AppTest hands back the raw multi-value form
        param = param[0]
    assert param, "the report is not addressable"
    assert {r["ticker"] for r in ui.parse_holdings_param(param)} == {h["ticker"] for h in HOLDINGS}
    assert at.session_state["uar_name"] == "Test", (
        "writing our own URL must not make the page treat the report as a stranger's link"
    )


def test_a_reopened_portfolio_says_where_it_came_from(monkeypatch, synthetic_engine):
    """It is the visitor's own data coming back out of their own browser. Both
    halves of that have to be said, or it reads as a silent account."""
    param = ui.holdings_param(HOLDINGS)
    at = _page(monkeypatch, "pages/60_Exposure_Report.py")
    at.query_params[ui.HOLDINGS_PARAM] = param
    at.query_params["reopened"] = "1"
    at.run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    text = _text(at)
    assert "Reopened the portfolio you measured last time" in text
    assert "this browser only" in text
    assert "/?fresh=1" in text, "there must be a way to forget it"


def test_a_shared_link_is_not_mistaken_for_your_own_portfolio(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, "pages/60_Exposure_Report.py")
    at.query_params[ui.HOLDINGS_PARAM] = ui.holdings_param(HOLDINGS)
    at.run()
    assert not at.exception
    assert at.session_state["uar_name"] == "Shared portfolio"
    assert "Reopened the portfolio" not in _text(at)


def test_the_weight_widgets_are_rebuilt_when_the_weights_are_reset():
    """AppTest cannot catch this one, so the mechanism is pinned in source.

    Deleting a widget's session_state key does not reset it if the same key is
    rendered again on the next run: the browser resends its old value and
    Streamlit restores it. There is no frontend here, so AppTest happily
    reported 50/50 while a real browser showed 100 + 50 = 150%, which the
    engine then rescaled to 67/33 — silently measuring a portfolio nobody
    asked for. The fix is a generation counter in the widget key, bumped only
    when the weights are meant to be re-split.
    """
    page = (DASHBOARD_ROOT / "pages/60_Exposure_Report.py").read_text(encoding="utf-8")
    assert 'key=f"uar_w_{gen}_{row[\'ticker\']}"' in page, (
        "the weight widget key must carry the generation counter"
    )
    assert 'st.session_state["uar_gen"] = st.session_state.get("uar_gen", 0) + 1' in page
    assert "uar_weights_touched" in page, (
        "weights someone typed must survive the next add"
    )


def test_the_reopened_line_survives_streamlits_own_reruns(monkeypatch, synthetic_engine):
    """It was popped from session state the first time it was read, so it was
    drawn on one run and gone by the time the page settled. Streamlit reruns a
    script several times during a normal load; anything a visitor is meant to
    SEE cannot be consumed on read."""
    at = _page(monkeypatch, "pages/60_Exposure_Report.py")
    at.query_params[ui.HOLDINGS_PARAM] = ui.holdings_param(HOLDINGS)
    at.query_params["reopened"] = "1"
    at.run()
    at.run()          # exactly what Streamlit does on its own
    at.run()
    assert "Reopened the portfolio you measured last time" in _text(at)


def test_measuring_something_else_drops_the_reopened_line(monkeypatch, synthetic_engine):
    at = _page(monkeypatch, "pages/60_Exposure_Report.py")
    at.query_params[ui.HOLDINGS_PARAM] = ui.holdings_param(HOLDINGS)
    at.query_params["reopened"] = "1"
    at.run()
    assert "Reopened the portfolio" in _text(at)

    at.session_state["uar_holdings"] = [{"ticker": "VTI", "weight_pct": 100}]
    at.session_state["uar_editing"] = False
    at.run()
    assert "Reopened the portfolio" not in _text(at), (
        "the line describes one portfolio; it must not follow the visitor onto another"
    )
