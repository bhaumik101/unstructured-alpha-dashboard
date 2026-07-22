"""
Tests for the Market Overview lazy section-rail restructuring.

Context: same pattern and reasoning as
tests/test_ticker_deep_dive_sections.py -- this page was an 854-line
linear scroll across 11 distinct topics; it's now 2 sections ("Markets"
and "Macro Indicators") via a sidebar radio, chosen because st.tabs()
runs every tab's code regardless of selection, while the section rail lets
if/elif genuinely skip the unselected branch.
"""


def _all_markdown_text(at):
    return " ".join(md.value for md in at.markdown)


def test_default_load_shows_markets_not_macro_indicators(app_test):
    at = app_test("pages/5_Market_Overview.py")
    assert not at.exception, (
        "Default Market Overview load raised: " + "\n".join(str(e) for e in at.exception)
    )
    text = _all_markdown_text(at)

    assert "MAJOR INDICES" in text
    assert "SECTOR PERFORMANCE" in text
    assert "GROWTH INDICATORS" not in text
    assert "LABOR MARKET" not in text
    assert "KEY ECONOMIC RELEASES" not in text


def test_switching_to_macro_indicators_section(app_test):
    at = app_test("pages/5_Market_Overview.py")
    sc = next((s for s in at.radio if s.key == "overview_section"), None)
    assert sc is not None, "Section rail not found"

    sc.set_value("Macro Indicators").run()
    assert not at.exception, (
        "Switching to Macro Indicators raised: " + "\n".join(str(e) for e in at.exception)
    )
    text = _all_markdown_text(at)
    assert "GROWTH INDICATORS" in text
    assert "LABOR MARKET" in text
    assert "KEY ECONOMIC RELEASES" in text
    # Markets-only content must not leak into this branch
    assert "MAJOR INDICES" not in text
    assert "SECTOR PERFORMANCE" not in text
