"""
Tests for utils/header.py's render_global_ticker_search() -- the
persistent ticker search box added to every page's header (2026-06-22).

The search uses an exact-first server-side resolver so a symbol such as AMD
cannot be replaced by the fuzzy match AMDC. The form also only navigates on
submission, preventing a persisted field value from redirecting every rerun.
"""


def test_picking_a_ticker_navigates_to_ticker_deep_dive(app_test):
    at = app_test("pages/home_page.py")
    field = next((s for s in at.text_input if s.key == "global_ticker_search"), None)
    submit = next((b for b in at.button if b.key == "global_ticker_submit"), None)
    assert field is not None, "Global ticker search field not found in header"
    assert submit is not None, "Global ticker search submit button not found in header"

    field.set_value("CCJ")
    submit.click().run()
    assert not at.exception, (
        "Picking a ticker raised: " + "\n".join(str(e) for e in at.exception)
    )
    assert at.session_state["_test_switch_page"] == "pages/3_Ticker_Deep_Dive.py"


def test_exact_custom_entry_is_normalized_before_navigation():
    from utils.header import _normalize_global_ticker_pick, _resolve_global_ticker_query

    assert _normalize_global_ticker_pick(" amd ") == "AMD"
    assert _normalize_global_ticker_pick("brk.b") == "BRK.B"
    symbol_index = {
        "AMD": "AMD — Advanced Micro Devices — Core",
        "AMDC": "AMDC — Corgi AMD 2x Daily ETF",
    }
    assert _resolve_global_ticker_query("AMD", symbol_index) == ("AMD", [])
    assert _resolve_global_ticker_query("Advanced Micro Devices", symbol_index) == ("AMD", [])


def test_rerunning_after_a_pick_does_not_navigate_again(app_test):
    """
    The actual regression this test guards against: after landing on
    Ticker Deep Dive from a pick, any further rerun of ANY page (the
    header renders on all of them) must NOT keep firing switch_page()
    just because the search field still contains the same ticker.
    """
    at = app_test("pages/home_page.py")
    field = next((s for s in at.text_input if s.key == "global_ticker_search"), None)
    submit = next((b for b in at.button if b.key == "global_ticker_submit"), None)
    field.set_value("CCJ")
    submit.click().run()
    assert not at.exception
    at.session_state["_test_switch_page"] = None

    # Re-run again without submitting the form -- if the loop guard
    # were broken, this would either raise or bounce between pages.
    at.run()
    assert not at.exception, (
        "Rerunning after a pick (no new selection) raised: "
        + "\n".join(str(e) for e in at.exception)
    )
    at.run()
    assert not at.exception
    assert at.session_state["_test_switch_page"] is None


def test_picking_a_different_ticker_after_one_navigates_again(app_test):
    at = app_test("pages/home_page.py")
    field = next((s for s in at.text_input if s.key == "global_ticker_search"), None)
    submit = next((b for b in at.button if b.key == "global_ticker_submit"), None)
    field.set_value("CCJ")
    submit.click().run()
    assert at.session_state["selected_ticker"] == "CCJ"

    at.session_state["_test_switch_page"] = None
    field = next((s for s in at.text_input if s.key == "global_ticker_search"), None)
    submit = next((b for b in at.button if b.key == "global_ticker_submit"), None)
    field.set_value("NVDA")
    submit.click().run()
    assert not at.exception
    assert at.session_state["selected_ticker"] == "NVDA"
    assert at.session_state["_test_switch_page"] == "pages/3_Ticker_Deep_Dive.py"
