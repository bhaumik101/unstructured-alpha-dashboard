"""
Tests for the Home page's call-to-action buttons.

Added 2026-06-22 alongside the secondary "My Watchlist" / "Signal
Research Center" CTA row -- before this, those two pages (2 of the
app's 9 routed pages) had no discoverable link from Home at all. This
file confirms every CTA button exists with
their expected keys and that clicking each one actually navigates,
rather than just trusting the button labels visually look right.
"""

import pytest

_CTA_TARGETS = {
    "cta_signals":   "pages/1_Signal_Dashboard.py",
    "cta_dive":      "pages/3_Ticker_Deep_Dive.py",
    "cta_market":    "pages/5_Market_Overview.py",
    "cta_watchlist": "pages/10_Watchlist.py",
    "cta_validation": "pages/51_Signal_Research.py",
    # 2026-09-08: exposure became the front door. Added here rather than
    # replacing anything — this file exists because two pages once had no route
    # from Home, and repositioning must not recreate that.
    "cta_portfolio": "pages/44_Portfolio_Suite.py",
    "cta_factor":    "pages/27_Factor_Exposure.py",
}


def test_all_cta_buttons_present(app_test):
    at = app_test("pages/home_page.py")
    assert not at.exception
    present_keys = {b.key for b in at.button}
    for key in _CTA_TARGETS:
        assert key in present_keys, f"Expected CTA button key {key!r} not found on Home page"


def test_home_defaults_to_compact_dashboard_and_keeps_discover_available(app_test):
    at = app_test("pages/home_page.py")

    assert at.session_state["home_section_rail"] == "Dashboard"
    page_sections = next(
        radio for radio in at.radio if radio.key == "home_section_rail"
    )
    assert list(page_sections.options) == ["Dashboard", "Discover"]
    assert any(button.key == "dashboard_brief" for button in at.button)
    # The long product-tour CTA is rendered only after a visitor explicitly
    # chooses Discover, so it cannot inflate the default Home payload.
    assert not any(button.key == "cta_pro_mid" for button in at.button)
    phases = [
        row["phase"] for row in at.session_state["_ua_home_perf_last"]["phases"]
    ]
    assert "live_signal_scores_skipped" in phases
    assert "top_ticker_ranking_skipped" in phases
    assert "command_center" not in phases


@pytest.mark.parametrize("key,target_page", _CTA_TARGETS.items())
def test_cta_button_navigates_to_expected_page(app_test, key, target_page):
    at = app_test("pages/home_page.py")
    btn = next((b for b in at.button if b.key == key), None)
    assert btn is not None, f"CTA button {key!r} not found"
    btn.click().run()
    assert not at.exception, (
        f"Clicking {key!r} raised: " + "\n".join(str(e) for e in at.exception)
    )
    assert at.session_state["_test_switch_page"] == target_page


def test_exposure_leads_and_the_unvalidated_score_does_not(app_test):
    """Positioning, asserted rather than trusted to stay.

    The Confluence Score is backtested and NOT validated. Leading the home page
    with it puts the product's least defensible claim in front of every
    visitor, which is what an external reviewer reacted to. Portfolio exposure
    is measured, so it leads.
    """
    source = __import__("pathlib").Path("pages/home_page.py").read_text(encoding="utf-8")
    portfolio = source.index('key="cta_portfolio"')
    deep_dive = source.index('key="cta_dive"')
    assert portfolio < deep_dive, (
        "portfolio exposure must appear before Ticker Deep Dive in the CTA grid"
    )
    assert 'type="primary"' in source[portfolio - 200:portfolio], (
        "the measured feature should be the primary call to action"
    )


def test_the_home_page_says_the_score_is_not_validated(app_test):
    source = __import__("pathlib").Path("pages/home_page.py").read_text(encoding="utf-8")
    assert "not** validated" in source or "not validated" in source, (
        "the home page routes visitors to the score; it should say what the "
        "score has and has not been shown to do"
    )
