"""
Tests for the Home page's call-to-action buttons.

Added 2026-06-22 alongside the secondary "My Watchlist" / "Signal
Research Center" CTA row -- before this, those two pages (2 of the
app's 9 routed pages) had no discoverable link from Home at all. This
file confirms all 5 CTA buttons (3 primary + 2 secondary) exist with
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
}


def test_all_five_cta_buttons_present(app_test):
    at = app_test("pages/home_page.py")
    assert not at.exception
    present_keys = {b.key for b in at.button}
    for key in _CTA_TARGETS:
        assert key in present_keys, f"Expected CTA button key {key!r} not found on Home page"


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
