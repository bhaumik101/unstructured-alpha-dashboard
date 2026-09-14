"""
Tests for utils/header.py's render_global_ticker_search() -- the
persistent ticker search box added to every page's header (2026-06-22).

The search uses an exact-first server-side resolver so a symbol such as AMD
cannot be replaced by the fuzzy match AMDC. The form also only navigates on
submission, preventing a persisted field value from redirecting every rerun.
"""

import pytest

import utils.header as _header

_needs_header_search = pytest.mark.skipif(
    not _header.SHOW_MARKET_CHROME,
    reason="header ticker search is off since the 2026-09-14 redesign (SHOW_MARKET_CHROME)",
)


def test_global_ticker_search_left_the_header_but_is_kept_behind_the_flag():
    """The 2026-09-14 redesign leads with the portfolio exposure report, so the
    ticker-first search no longer renders on every page. It is gated by
    SHOW_MARKET_CHROME rather than deleted; the resolver below is unchanged."""
    from pathlib import Path

    import utils.header as header

    src = (Path(__file__).resolve().parents[1] / "utils" / "header.py").read_text(encoding="utf-8")
    body = src.split("def render_header(", 1)[1].split("\ndef ", 1)[0]
    assert header.SHOW_MARKET_CHROME is False
    assert "if SHOW_MARKET_CHROME:\n        render_global_ticker_search()" in body
    assert callable(header.render_global_ticker_search)


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


@_needs_header_search
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


@_needs_header_search
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


@_needs_header_search
def test_resubmitting_same_ticker_still_navigates(app_test):
    at = app_test("pages/home_page.py")
    field = next(s for s in at.text_input if s.key == "global_ticker_search")
    submit = next(b for b in at.button if b.key == "global_ticker_submit")
    field.set_value("CCJ")
    submit.click().run()
    assert at.session_state["_test_switch_page"] == "pages/3_Ticker_Deep_Dive.py"

    at.session_state["_test_switch_page"] = None
    field = next(s for s in at.text_input if s.key == "global_ticker_search")
    submit = next(b for b in at.button if b.key == "global_ticker_submit")
    field.set_value("CCJ")
    submit.click().run()

    assert not at.exception
    assert at.session_state["_test_switch_page"] == "pages/3_Ticker_Deep_Dive.py"


def test_search_action_uses_a_descriptive_non_wrapping_label():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "utils" / "header.py").read_text()

    assert '"Analyze ticker"' in source
    # The selector gained `.stFormSubmitButton` in #197's follow-up: keyed off
    # the .st-key- class alone it tied `.stFormSubmitButton > button` on
    # specificity and lost on source order. What the rule RESOLVES to is
    # covered by test_button_cascade's `label_ticker_submit` state; this only
    # checks the block is still here and still asks for no wrapping.
    assert ".st-key-global_ticker_submit .stFormSubmitButton > button p" in source
    assert "word-break: keep-all" in source
