"""
Regression test for a real production crash (2026-06-22): a browser tab
left open from before a deploy restart reconnected to the freshly
restarted server using its old session id -- a session id the new
process had NO session_state for, including "_cookies_this_run", which
utils/auth_ui.py's get_cookies() used to index directly. That turned into
a raw KeyError that crashed render_header() -> render_account_widget() ->
get_cookies() on every page for whoever's tab reconnected at the wrong
moment, confirmed live in Render's logs (the actual traceback this test
is built from).

Tests the session-state fallback logic in isolation, mocking out
CookieManager itself -- constructing the REAL browser component outside
an actual Streamlit script run context is a separate concern (and
already covered by the established "cookies.ready() is always False
under AppTest" blind spot documented in tests/conftest.py) from "does
get_cookies() crash or self-heal when its cache key is missing," which
is the actual bug fixed here.
"""

from unittest.mock import MagicMock

import pytest

from utils import auth_ui


@pytest.fixture(autouse=True)
def _fake_session_state(monkeypatch):
    """A plain dict stands in for st.session_state -- supports the same
    `in` / `[]` operations auth_ui.py's functions actually use."""
    fake_state = {}
    monkeypatch.setattr(auth_ui.st, "session_state", fake_state)
    yield fake_state


@pytest.fixture(autouse=True)
def _fake_cookie_manager(monkeypatch):
    """Replace the real CookieManager (a Streamlit custom component) with
    a plain mock -- isolates the session-state logic from component
    registration, which needs a real ScriptRunContext to behave normally."""
    monkeypatch.setattr(auth_ui, "CookieManager", lambda: MagicMock(name="CookieManager"))
    yield


def test_get_cookies_self_heals_when_cache_key_missing(_fake_session_state):
    """The exact bug: _cookies_this_run was never set for this session
    (e.g. app.py's own top-level init never ran for it). get_cookies()
    must construct one rather than raising KeyError."""
    assert auth_ui._COOKIES_SESSION_KEY not in _fake_session_state

    cookies = auth_ui.get_cookies()  # must not raise

    assert cookies is not None
    assert _fake_session_state[auth_ui._COOKIES_SESSION_KEY] is cookies


def test_get_cookies_reuses_existing_instance_without_reconstructing(_fake_session_state):
    """The normal, common case (app.py already ran init_cookies_for_this_run()
    this run) must keep returning that SAME instance, not silently swap in
    a new one on every call -- a second CookieManager() construction mid-run
    is the StreamlitDuplicateElementKey bug this whole split exists to avoid."""
    original = auth_ui.init_cookies_for_this_run()

    first_read = auth_ui.get_cookies()
    second_read = auth_ui.get_cookies()

    assert first_read is original
    assert second_read is original


def test_get_cookies_after_manual_cache_clear_constructs_fresh_instance():
    """Simulates the exact production scenario end-to-end: a normal run
    happens (cache populated), then the cache is cleared (the new-process,
    old-session-id reconnect case), and a later call must still work."""
    fake_state = {}
    import utils.auth_ui as auth_ui_module
    from unittest.mock import patch

    with patch.object(auth_ui_module, "st") as mock_st, \
         patch.object(auth_ui_module, "CookieManager", lambda: MagicMock(name="CookieManager")):
        mock_st.session_state = fake_state

        first = auth_ui_module.init_cookies_for_this_run()
        assert fake_state[auth_ui_module._COOKIES_SESSION_KEY] is first

        del fake_state[auth_ui_module._COOKIES_SESSION_KEY]  # simulate the reconnect-to-fresh-process case

        second = auth_ui_module.get_cookies()  # must not raise
        assert second is not None
