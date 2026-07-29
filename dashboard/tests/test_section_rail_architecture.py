"""Architecture guards for focused, lazy-loading product pages."""

import ast
from pathlib import Path


PAGES = Path(__file__).resolve().parents[1] / "pages"

LAZY_SECTION_PAGES = (
    "1_Signal_Dashboard.py",
    "2_Today_Digest.py",
    "3_Ticker_Deep_Dive.py",
    "4_Power_Supercycle.py",
    "5_Market_Overview.py",
    "6_Stock_Screener.py",
    "8_About.py",
    "10_Watchlist.py",
    "27_Factor_Exposure.py",
    "30_Track_Record_Live.py",
    "35_Signal_Strategy.py",
    "37_Legal.py",
    "39_How_Signals_Work.py",
    "40_Stock_Recommender.py",
    "41_Alternative_Data.py",
    "42_Sector_View.py",
    "43_Events_Forecasts.py",
    "44_Portfolio_Suite.py",
    "45_Options_Flow.py",
    "46_Thesis_Journal.py",
    "50_Investor_Checkup.py",
)


DENSE_SECTION_STATE = {
    "10_Watchlist.py": "_watchlist_section",
    "27_Factor_Exposure.py": "_factor_section",
    "35_Signal_Strategy.py": "_strategy_section",
    "40_Stock_Recommender.py": "_recommender_section",
    "45_Options_Flow.py": "_options_section",
}


def test_major_product_pages_use_shared_section_rail():
    for page_name in LAZY_SECTION_PAGES:
        source = (PAGES / page_name).read_text(encoding="utf-8")
        assert "sections=(" in source, f"{page_name} does not declare its section rail"
        assert "section_key=" in source, f"{page_name} does not have stable section state"


def test_major_product_pages_do_not_use_eager_tabs():
    for page_name in LAZY_SECTION_PAGES:
        source = (PAGES / page_name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        eager_tabs = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "tabs"
        ]
        assert not eager_tabs, f"{page_name} eagerly executes hidden tab content"


def test_shared_helper_exposes_section_rail_outside_hidden_sidebar():
    header_source = (PAGES.parent / "utils" / "header.py").read_text(encoding="utf-8")
    assert "Only this section loads." in header_source
    assert "selected_section = st.radio(" in header_source
    assert 'with st.container(key="ua_page_section_rail")' in header_source
    assert ".st-key-ua_page_section_rail" in header_source
    assert "position: absolute;" in header_source
    assert "div:has(> .st-key-ua_page_section_rail)" in header_source
    assert 'position: sticky;' in header_source
    assert "The menu stays visible while you scroll." in header_source
    assert "padding-left:" in header_source
    assert 'st.query_params.get("section")' in header_source
    assert 'st.query_params["section"] = requested_slug' in header_source
    assert "on_change=_sync_section_query" in header_source

    helper_source = header_source[header_source.index("def render_sidebar_base("):]
    assert "with st.sidebar:" not in helper_source
    assert "sidebar_logout" not in helper_source


def test_section_rail_deep_link_selects_requested_section(app_test):
    from streamlit.testing.v1 import AppTest

    page = PAGES / "8_About.py"
    app = AppTest.from_file(str(page), default_timeout=120)
    app.session_state["user"] = {"id": 1, "email": "test@example.com"}
    app.session_state["_tier_1"] = "pro"
    app.session_state["_sync_done_1"] = True
    app.query_params["section"] = "validation-evidence"
    app.query_params["theme"] = "light"
    app.query_params["ticker"] = "MSFT"
    app.run()

    rail = next(control for control in app.radio if control.key == "about_section_rail")
    assert rail.value == "Validation Evidence"
    assert app.query_params["theme"] == ["light"]
    assert app.query_params["ticker"] == ["MSFT"]
    assert not app.exception


def test_section_rail_selection_updates_url_without_dropping_context(app_test):
    app = app_test("pages/8_About.py")
    app.query_params["theme"] = "dark"
    app.query_params["ticker"] = "NVDA"
    app.run()

    rail = next(control for control in app.radio if control.key == "about_section_rail")
    rail.set_value("Validation Evidence").run()
    assert app.query_params["section"] == ["validation-evidence"]
    assert app.query_params["theme"] == ["dark"]
    assert app.query_params["ticker"] == ["NVDA"]

    rail = next(control for control in app.radio if control.key == "about_section_rail")
    rail.set_value("Overview").run()
    assert "section" not in app.query_params
    assert app.query_params["theme"] == ["dark"]
    assert app.query_params["ticker"] == ["NVDA"]


def test_visible_header_and_footer_own_removed_sidebar_actions():
    header_source = (PAGES.parent / "utils" / "header.py").read_text(encoding="utf-8")
    assert 'key="topright_logout"' in header_source
    assert 'href="/ai-research-assistant"' in header_source
    assert "Switch to light theme" in header_source
    assert "Important Disclaimer" in header_source


def test_dense_pages_conditionally_execute_selected_sections():
    for page_name, state_name in DENSE_SECTION_STATE.items():
        source = (PAGES / page_name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        routed_sections = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and state_name in ast.unparse(node.test)
        ]
        assert len(routed_sections) >= 4, f"{page_name} does not lazily route its dense sections"
