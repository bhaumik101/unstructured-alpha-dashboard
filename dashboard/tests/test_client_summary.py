"""The one-page client summary: what an adviser hands a client.

These pin what makes it a summary a client can be given — every force with
its range and evidence label, the caveat in the body rather than small print,
no advice — and the two things the page must never do: measure a portfolio
for someone who cannot see the result, or print its own controls.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_exposure import _BANNED, _report  # noqa: E402
from utils import client_summary as cs  # noqa: E402

WHEN = datetime(2026, 9, 27, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def report():
    r = _report()
    assert r["status"] == "ok"
    return r


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# ── the page itself ─────────────────────────────────────────────────────────

def test_the_summary_names_the_portfolio_and_every_force(report):
    html = cs.summary_html(report, "Smith IRA", "Jane Smith", "Acme Advisers", when=WHEN)
    text = _text(html)
    assert "Smith IRA" in text and "Prepared for Jane Smith" in text and "by Acme Advisers" in text
    assert "September 27, 2026" in text
    for reading in report["portfolio"]["readings"].values():
        assert reading["label"] in text
        assert reading["evidence_label"] in text


def test_the_caveat_is_in_the_body_above_the_method(report):
    html = cs.summary_html(report, "X", when=WHEN)
    caveat = html.find("This describes the past, and it is not a forecast.")
    assert caveat != -1, "the caveat must be on the page"
    assert caveat < html.find('class="ucs-foot"'), "the caveat sits above the method, not after it"


def test_nothing_outside_the_caveat_advises_or_forecasts(report):
    html = cs.summary_html(report, "X", when=WHEN)
    body = re.sub(r'<div class="ucs-caveat">.*?</div>', "", html, flags=re.S)
    hit = _BANNED.search(_text(body))
    assert not hit, f"forward-looking or advisory language: {hit.group(0)!r}"


def test_a_weak_exposure_does_not_name_contributors(report):
    """Largest contributors to a reading that could be noise would be noise too."""
    html = cs.summary_html(report, "X", when=WHEN)
    for row in re.findall(r"<tr><td>.*?</tr>", html, flags=re.S):
        label = _text(row)
        reading = next(r for r in report["portfolio"]["readings"].values() if r["label"] in label)
        if reading["evidence"] not in ("clear", "tentative"):
            assert row.endswith("<td>—</td></tr>"), label


def test_names_typed_by_the_adviser_cannot_inject_markup(report):
    html = cs.summary_html(report, "<img src=x onerror=alert(1)>", "<b>x</b>", "<script>", when=WHEN)
    assert "<img src=x" not in html and "<script>" not in html and "<b>x</b>" not in html


def test_a_long_holdings_list_is_cut_to_one_line(report):
    many = dict(report, positions=[{"ticker": f"T{i:02d}", "weight_pct": 5.0} for i in range(20)])
    text = _text(cs.summary_html(many, "X", when=WHEN))
    assert "+6 more" in text and "T13" in text and "T14" not in text


def test_a_report_that_failed_prints_nothing():
    assert cs.summary_html({"status": "error", "message": "no data"}, "X") == ""


def test_print_hides_everything_but_the_summary():
    css = cs.SUMMARY_CSS.split("@media print", 1)[1]
    for chrome in (".ua-topnav", ".st-key-cs_controls", ".ucs-screen-only", '[data-testid="stButton"]'):
        assert chrome in css, f"{chrome} would print on the client's page"
    assert "@page" in css


# ── one sheet, not two ──────────────────────────────────────────────────────
# Measured in Chromium at Letter with 10mm margins: ~980px fits. After the app
# theme grew, the summary printed at 1,136px -- the method and caveat spilled
# onto a second sheet. Two causes, each worth ~50-60px, each pinned here.

def test_the_print_padding_override_outranks_the_theme():
    """The theme sets `.stApp .block-container{padding-top:58px!important}`.
    Both are !important, so a bare `.block-container` override loses on
    specificity and the 58px stays."""
    from utils.app_theme import PRODUCT_CSS

    assert ".stApp .block-container{" in PRODUCT_CSS and "padding-top:58px!important" in PRODUCT_CSS
    css = cs.SUMMARY_CSS.split("@media print", 1)[1]
    assert re.search(r"\.stApp \.block-container,[^{]*\{padding:0!important", css), (
        "the print override must be at least as specific as the theme's padding rule")


def test_section_titles_are_not_markdown_headings(report):
    """Streamlit wraps each markdown <h3> in its own anchor block (44px in
    print). role="heading" keeps them headings for a screen reader."""
    html = cs.summary_html(report, "Smith IRA")
    assert "<h3" not in html
    assert html.count('role="heading" aria-level="3"') == 3


# ── the print button ────────────────────────────────────────────────────────

def test_the_print_link_is_wired_to_the_print_dialog():
    """st.markdown strips <script>, so the link only works if the injected
    runtime turns it into window.print()."""
    from scripts.inject_boot_splash import _build_runtime

    # Comments out first: the one above the hook names window.print() too.
    runtime = re.sub(r"/\*.*?\*/", "", _build_runtime(), flags=re.S)
    assert re.search(r"addEventListener\('click',\s*function\(ev\)\{[^}]*"
                     r"closest\('\[data-ua-print\]'\).*?window\.print\(\)", runtime, flags=re.S), (
        "no click handler turns the print link into window.print()")
    page = (_ROOT / "pages" / "68_Summary.py").read_text(encoding="utf-8")
    assert 'data-ua-print="1"' in page


# ── the page, driven ────────────────────────────────────────────────────────

@pytest.fixture
def measured(monkeypatch, report):
    """Count measurements instead of running them."""
    from utils import report_ui as ui

    calls = []

    def fake_get_report(key, max_holdings):
        calls.append(key)
        return report

    monkeypatch.setattr(ui, "get_report", fake_get_report)
    return calls


def _page(monkeypatch, tier=None, holdings=None):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from tests.conftest import DASHBOARD_ROOT

    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    monkeypatch.setattr(st, "switch_page",
                        lambda p, *a, **k: st.session_state.__setitem__("_test_switch_page", p))
    at = AppTest.from_file(str(DASHBOARD_ROOT / "pages/68_Summary.py"), default_timeout=120)
    if tier:
        at.session_state["user"] = {"id": 7, "email": "a@example.com"}
        at.session_state["_tier_7"] = tier
        at.session_state["_sync_done_7"] = True
    if holdings:
        at.session_state["uar_holdings"] = holdings
        at.session_state["uar_name"] = "Smith IRA"
    at.run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    return at


def _page_text(at) -> str:
    return " ".join([m.value for m in at.markdown] + [b.label for b in at.button]
                    + [i.value for i in at.info])


HOLDINGS = [{"ticker": "TLT", "weight_pct": 40.0}, {"ticker": "XOM", "weight_pct": 30.0},
            {"ticker": "VTI", "weight_pct": 30.0}]


def test_a_free_account_is_shown_what_it_is_and_nothing_is_measured(monkeypatch, measured):
    at = _page(monkeypatch, tier="free", holdings=HOLDINGS)
    assert "part of Investor Pro" in _page_text(at)
    assert measured == [], "a gated visitor must not cost a measurement"
    assert 'class="ucs"' not in _page_text(at)


def test_pro_with_no_portfolio_open_is_sent_to_the_report(monkeypatch, measured):
    at = _page(monkeypatch, tier="pro")
    assert "Open a portfolio on the report first" in _page_text(at)
    assert measured == []


@pytest.mark.parametrize("tier", ["pro", "advisor"])
def test_pro_and_advisor_get_the_page_with_its_print_button(monkeypatch, measured, tier):
    from utils.billing import ADVISOR_TIER

    at = _page(monkeypatch, tier=ADVISOR_TIER if tier == "advisor" else "pro", holdings=HOLDINGS)
    text = _page_text(at)
    assert len(measured) == 1
    assert 'class="ucs"' in text and "Smith IRA" in text
    assert "Print or save as PDF" in text


def test_the_names_typed_on_the_page_reach_the_printout(monkeypatch, measured):
    at = _page(monkeypatch, tier="pro", holdings=HOLDINGS)
    at.text_input(key="cs_for").input("Jane Smith").run()
    assert "Prepared for Jane Smith" in _page_text(at)
