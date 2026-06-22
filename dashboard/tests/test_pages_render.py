"""
Every routed page must render with zero exceptions, with no API keys
configured (the worst case: every signal falls back to synthetic data,
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


def test_about_page_backtest_button_runs_without_exception(app_test):
    """
    Exercises the "Run Live Backtest" button click on the About page, not
    just the page's initial render — this is the only way to actually
    execute compute_backtested_pcs() / _backtest_all_signals(), since that
    code path is gated behind a button and never runs on a plain page load.
    """
    at = app_test("pages/8_About.py")
    btn = next((b for b in at.button if b.key == "run_pcs_backtest"), None)
    assert btn is not None, "Run Live Backtest button not found on About page"
    btn.click().run()
    assert not at.exception, (
        "Backtest button raised: " + "\n".join(str(e) for e in at.exception)
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
    all_text = " ".join(md.value for md in at.markdown) + " ".join(t.value for t in at.title)
    assert "UNSTRUCTURED" in all_text or "Hedge Fund Signals" in all_text, (
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
