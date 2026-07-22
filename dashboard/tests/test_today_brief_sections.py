"""The personalized default must stay cheap; the full market view loads lazily."""

from streamlit.testing.v1 import AppTest

from tests.conftest import DASHBOARD_ROOT


def _brief_app(section=None):
    at = AppTest.from_file(
        str(DASHBOARD_ROOT / "pages/2_Today_Digest.py"), default_timeout=120
    )
    at.session_state["user"] = {"id": 987654, "email": "brief@example.com"}
    if section:
        at.session_state["brief_section_rail"] = section
    return at.run()


def test_my_priorities_does_not_trigger_full_signal_sweep(monkeypatch):
    calls = []

    def fake_signal_scores(*_args, **_kwargs):
        calls.append("loaded")
        return {}

    monkeypatch.setattr("utils.signals_cache.get_all_signal_scores", fake_signal_scores)
    monkeypatch.setattr("utils.header._render_live_ticker_strip", lambda: None)
    monkeypatch.setattr("streamlit.page_link", lambda *_args, **_kwargs: None)
    at = _brief_app()

    assert not at.exception
    assert calls == []
    rail = next((radio for radio in at.radio if radio.key == "brief_section_rail"), None)
    assert rail is not None
    assert rail.value == "My Priorities"


def test_market_intelligence_loads_signal_stack_on_demand(monkeypatch):
    calls = []

    def fake_signal_scores(*_args, **_kwargs):
        calls.append("loaded")
        return {}

    monkeypatch.setattr("utils.signals_cache.get_all_signal_scores", fake_signal_scores)
    monkeypatch.setattr("utils.header._render_live_ticker_strip", lambda: None)
    monkeypatch.setattr("streamlit.page_link", lambda *_args, **_kwargs: None)
    at = _brief_app("Market Intelligence")

    assert not at.exception
    assert calls, "The full signal stack should load only after this section is selected."
