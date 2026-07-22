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


def test_sidebar_helper_documents_lazy_execution_contract():
    header_source = (PAGES.parent / "utils" / "header.py").read_text(encoding="utf-8")
    assert "Only this section is loaded." in header_source
    assert "selected_section = st.radio(" in header_source
    assert 'position: sticky;' in header_source
    assert "This menu stays available while you scroll." in header_source


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
