"""Your portfolios: the page a returning visitor lands on.

Saving a portfolio used to be the end of the road — it went into a picker
inside an expander, and nothing brought anyone back to it. These tests pin the
page that does, and the one rule that keeps it fast: it never measures a
portfolio just because the page was opened.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_exposure import _BANNED, _report  # noqa: E402
from utils import report_ui as ui  # noqa: E402


@pytest.fixture(scope="module")
def report():
    r = _report()
    assert r["status"] == "ok"
    return r


# ── the card ────────────────────────────────────────────────────────────────

def test_a_card_leads_with_exposures_that_stand_up(report):
    html = ui.portfolio_card_html("Client IRA", 3, "2026-09-20T10:00:00", report)
    assert "Client IRA" in html and "3 holdings" in html and "Sep 20, 2026" in html
    readings = report["portfolio"]["readings"]
    for key in report["top_exposures"][:3]:
        assert readings[key]["label"] in html
    shown = set(report["top_exposures"][:3])
    for key, reading in readings.items():
        if key not in shown and reading["evidence"] not in ("clear", "tentative"):
            assert f'{reading["label"]} <b>' not in html, (
                "a card must not headline a reading that could be noise")


def test_a_card_draws_the_leading_exposures_drift(report):
    html = ui.portfolio_card_html("Client IRA", 3, "", report)
    assert "<svg" in html and 'role="img"' in html and "rolling year" in html


def test_an_unmeasured_portfolio_says_so_instead_of_showing_zeros():
    html = ui.portfolio_card_html("Old one", 4, "", None)
    assert "Not measured" in html and "%" not in html


def test_a_portfolio_with_nothing_clear_says_so_plainly():
    quiet = {"status": "ok", "as_of": "2026-09-18", "top_exposures": [],
             "portfolio": {"readings": {}}, "rolling": {}}
    assert "No exposure stood out from noise" in ui.portfolio_card_html("Quiet", 2, "", quiet)


def test_the_card_does_not_forecast(report):
    text = re.sub(r"<[^>]+>", " ", ui.portfolio_card_html("X", 3, "", report))
    assert not _BANNED.search(text), _BANNED.search(text).group(0)


def test_peeking_never_measures(monkeypatch):
    """Opening the page must not start ten measurements for an adviser with
    ten saved portfolios."""
    from utils import exposure as ex

    def boom(*_a, **_k):
        raise AssertionError("peek_report measured a portfolio")

    monkeypatch.setattr(ex, "build_live_report", boom)
    assert ui.peek_report((("ZZZZ", 100.0),), 15) is None


# ── the page ────────────────────────────────────────────────────────────────

@pytest.fixture
def workspace(monkeypatch, report):
    from utils import portfolio_workspace as pw

    saved = [
        {"id": 1, "user_id": 7, "name": "Client — Smith IRA", "updated_at": "2026-09-20T10:00:00"},
        {"id": 2, "user_id": 7, "name": "Client — Jones taxable", "updated_at": "2026-09-21T10:00:00"},
    ]
    holdings = {1: [{"ticker": "TLT", "weight_pct": 40.0}, {"ticker": "VTI", "weight_pct": 30.0},
                    {"ticker": "XOM", "weight_pct": 30.0}],
                2: [{"ticker": "VTI", "weight_pct": 100.0}]}
    monkeypatch.setattr(pw, "list_portfolios", lambda uid: saved if int(uid) == 7 else [])
    monkeypatch.setattr(pw, "get_holdings",
                        lambda uid, pid: holdings.get(int(pid), []) if int(uid) == 7 else [])
    # Portfolio 1 has been measured recently; portfolio 2 has not.
    measured_key = ui.prepare_holdings(holdings[1], ui.FREE_MAX_HOLDINGS)[0]
    monkeypatch.setattr(ui, "peek_report",
                        lambda key, mh: report if key == measured_key else None)
    return saved


def _page(monkeypatch, user=None):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from tests.conftest import DASHBOARD_ROOT

    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    monkeypatch.setattr(st, "switch_page",
                        lambda p, *a, **k: st.session_state.__setitem__("_test_switch_page", p))
    at = AppTest.from_file(str(DASHBOARD_ROOT / "pages/67_Portfolios.py"), default_timeout=120)
    if user:
        at.session_state["user"] = user
        at.session_state[f"_tier_{user['id']}"] = "free"
        at.session_state[f"_sync_done_{user['id']}"] = True
    at.run()
    return at


def _text(at) -> str:
    return " ".join([m.value for m in at.markdown] + [c.value for c in at.caption]
                    + [b.label for b in at.button])


def test_a_signed_out_visitor_is_told_what_the_page_is_for(monkeypatch):
    at = _page(monkeypatch)
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    assert "Sign in to see your saved portfolios" in _text(at)


def test_every_saved_portfolio_gets_a_card(monkeypatch, workspace):
    at = _page(monkeypatch, user={"id": 7, "email": "a@example.com"})
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    text = _text(at)
    assert "Client — Smith IRA" in text and "Client — Jones taxable" in text
    assert "Not measured" in text, "the unmeasured one must say so"
    assert "Measure it" in text, "and offer to measure the one that is missing"


def test_opening_a_card_carries_that_portfolio_to_the_report(monkeypatch, workspace):
    at = _page(monkeypatch, user={"id": 7, "email": "a@example.com"})
    at.button(key="pf_open_1").click().run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    assert at.session_state["uar_name"] == "Client — Smith IRA"
    assert {h["ticker"] for h in at.session_state["uar_holdings"]} == {"TLT", "VTI", "XOM"}
    assert at.session_state["_test_switch_page"].endswith("60_Exposure_Report.py")


def test_compare_from_a_card_puts_it_on_side_a(monkeypatch, workspace):
    at = _page(monkeypatch, user={"id": 7, "email": "a@example.com"})
    at.button(key="pf_cmp_2").click().run()
    assert not at.exception
    assert at.session_state["uar_name"] == "Client — Jones taxable"
    assert at.session_state["_test_switch_page"].endswith("66_Compare.py")


def test_the_page_is_reachable_from_the_account_menu():
    header = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")
    account = header.split('<span class="ua-tnav-trigger">Account ', 1)[1]
    assert 'href="/portfolios"' in account
    assert 'url_path="portfolios"' in (_ROOT / "app.py").read_text(encoding="utf-8")
