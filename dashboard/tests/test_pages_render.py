"""
Every routed page must render with zero exceptions, with no API keys
configured (the worst case: every signal is explicitly unavailable,
every price fetch may fail). This is the single most important regression
test in this suite — it is the automated version of the manual "ast.parse +
AppTest across all pages" check that's been run by hand after every change
so far in this project. A bad series ID, a missing dict key in a fallback
path, or a KeyError in a chart builder should fail HERE, not get caught
days later by a user screenshot.
"""

import pytest

from tests.conftest import ROUTED_PAGES


@pytest.mark.parametrize("page_path", ROUTED_PAGES)
def test_page_renders_without_exception(app_test, page_path):
    at = app_test(page_path)
    assert not at.exception, (
        f"{page_path} raised: " + "\n".join(str(e) for e in at.exception)
    )


def test_about_page_backtest_button_runs_without_exception(app_test, monkeypatch):
    """
    Exercises the "Run Live Backtest" button click on the About page, not
    just the page's initial render — this is the only way to actually
    execute compute_backtested_pcs() / _backtest_all_signals(), since that
    code path is gated behind a button and never runs on a plain page load.
    """
    import utils.validation_status as validation_status

    monkeypatch.setattr(validation_status, "validate_all_macro_signals", lambda: {})
    at = app_test("pages/8_About.py")
    section = next((r for r in at.radio if r.key == "about_section_rail"), None)
    assert section is not None, "About section rail not found"
    section.set_value("Validation Evidence").run()
    btn = next((b for b in at.button if b.key == "run_pcs_backtest"), None)
    assert btn is not None, "Run Live Backtest button not found on About page"
    btn.click().run()
    assert not at.exception, (
        "Backtest button raised: " + "\n".join(str(e) for e in at.exception)
    )


def test_model_validation_page_shows_all_five_categories_with_no_overclaim(app_test):
    """
    Confirms the actual rendered page -- not just utils/validation_status.py
    in isolation (see tests/test_validation_status_unit.py for that) -- shows
    all 5 differentiator/composite categories, and specifically that the two
    NOT-validated composites (Confluence, Supercycle) never render with a
    bare "Validated" label that a skimming user could mistake for an
    endorsement.
    """
    at = app_test("pages/11_Model_Validation.py")
    assert not at.exception, (
        "Model Validation page raised: " + "\n".join(str(e) for e in at.exception)
    )
    all_text = " ".join(md.value for md in at.markdown)
    all_text += " " + " ".join(element.proto.body for element in at.get("html"))
    for expected in (
        "Confluence Score",
        "Power Supercycle Score",
        "Insider Activity",
        "Short Interest",
        "13F Institutional Positioning",
    ):
        assert expected in all_text, f"Expected category not found on page: {expected!r}"
    assert "NOT validated" in all_text


def test_model_validation_page_universal_validation_button_runs_without_exception(app_test, monkeypatch):
    """
    Exercises the universal lag-validation button -- the one that calls
    validate_all_macro_signals() (utils/validation_status.py), the
    2026-06-22 rollout of the out-of-sample/Bonferroni-corrected
    methodology to every macro signal, not just insider/short-interest.
    """
    import utils.validation_status as validation_status

    monkeypatch.setattr(validation_status, "validate_all_macro_signals", lambda: {})
    at = app_test("pages/11_Model_Validation.py")
    btn = next((b for b in at.button if b.key == "run_validated_lag_scan_all_signals"), None)
    assert btn is not None, "Run Universal Lag Validation button not found on Model Validation page"
    btn.click().run()
    assert not at.exception, (
        "Universal lag validation button raised: " + "\n".join(str(e) for e in at.exception)
    )


def test_anonymous_visitor_sees_real_home_page_content():
    """
    Every test above uses the app_test fixture, which injects a fake
    logged-in user into session_state BEFORE the first .run() -- meaning
    none of them ever exercise a genuinely anonymous visit. Per explicit
    user request, this app no longer requires an account to browse most of
    it: app.py's non-blocking try_restore_session() (utils/auth_ui.py)
    must let the default Home page render its real content for someone
    with no session_state user at all, not show a login gate or stop the
    script. This also exercises the CookieManager() instantiated at the
    top of every run -- AppTest has no real browser attached, so
    cookies.ready() is always False here, which is exactly the case this
    test confirms doesn't block anything anymore.

    What this does NOT confirm: whether a real "remember me" cookie
    round-trip works; that requires a live browser (see tests/conftest.py's
    module docstring).
    """
    from streamlit.testing.v1 import AppTest
    from tests.conftest import DASHBOARD_ROOT

    at = AppTest.from_file(str(DASHBOARD_ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception, (
        "Anonymous Home page visit raised: " + "\n".join(str(e) for e in at.exception)
    )
    # Not just "didn't crash" -- confirm REAL page content rendered, not a
    # blank page or a login form silently swallowing everything below it.
    all_text = (
        " ".join(md.value for md in at.markdown)
        + " ".join(t.value for t in at.title)
        + " ".join(button.label for button in at.button)
    )
    assert "Continue your research" in all_text and "Signal Dashboard" in all_text, (
        "Expected real Home page content for an anonymous visitor, got: " + all_text[:500]
    )


def test_watchlist_anonymous_visitor_sees_sign_in_prompt_not_watchlist_data():
    """
    Watchlist is the one page that still requires an account (per explicit
    user request -- every other page is now browsable by anyone). Loading
    it with NO session_state user must NOT show the actual watchlist
    add/list UI -- which would mean either leaking the watchlist-
    management interface to someone never authenticated, or crashing on
    st.session_state["user"]["id"] with no "user" key present at all.

    What this does NOT confirm: require_login()'s actual "Sign in to use
    your watchlist" copy rendering -- under AppTest, cookies.ready() is
    always False (no real browser attached), so require_login() calls
    st.stop() immediately after that check, BEFORE the sign-in form ever
    renders. That's the correct, intended behavior in a real browser
    (where the cookie component does become ready) but means this test
    can only confirm "nothing leaked and nothing crashed," not "the
    sign-in form itself looks right" -- same category of live-browser-only
    blind spot as the remember-me cookie round-trip (see tests/conftest.py).
    """
    from streamlit.testing.v1 import AppTest
    from tests.conftest import DASHBOARD_ROOT

    at = AppTest.from_file(str(DASHBOARD_ROOT / "app.py"), default_timeout=60)
    at.run()
    at.switch_page("pages/10_Watchlist.py")
    at.run()

    assert not at.exception, (
        "Anonymous Watchlist visit raised: " + "\n".join(str(e) for e in at.exception)
    )

    # The real watchlist-management UI must NOT render -- specifically, no
    # "Add a ticker to watch" input, which only require_login() actually
    # returning a real user would ever reach.
    watch_labels = [ti.label for ti in at.text_input if ti.label]
    assert not any("Add a ticker to watch" in label for label in watch_labels), (
        "Watchlist add-ticker input leaked to an anonymous visitor"
    )
