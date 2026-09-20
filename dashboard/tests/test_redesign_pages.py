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
