"""Performance guards for the dense-page section routing pass."""

import ast
from pathlib import Path


PAGES = Path(__file__).resolve().parents[1] / "pages"


def _tree_and_parents(page_name: str):
    tree = ast.parse((PAGES / page_name).read_text(encoding="utf-8"))
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return tree, parents


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _has_section_guard(node: ast.AST, parents: dict, state_name: str) -> bool:
    current = parents.get(node)
    while current is not None:
        if isinstance(current, ast.If) and state_name in ast.unparse(current.test):
            return True
        current = parents.get(current)
    return False


def test_provider_heavy_calls_are_bypassed_by_unrelated_sections():
    cases = (
        ("10_Watchlist.py", "_get_prepost_batch", "_watchlist_section"),
        ("40_Stock_Recommender.py", "_macro_rank_all", "_recommender_section"),
        ("45_Options_Flow.py", "fetch_options_chain", "_options_section"),
    )
    for page_name, function_name, state_name in cases:
        tree, parents = _tree_and_parents(page_name)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _call_name(node) == function_name
        ]
        assert calls, f"{page_name} no longer calls {function_name}"
        assert all(_has_section_guard(node, parents, state_name) for node in calls)


def test_dense_page_charts_only_render_inside_selected_sections():
    cases = (
        ("10_Watchlist.py", "_watchlist_section"),
        ("27_Factor_Exposure.py", "_factor_section"),
        ("35_Signal_Strategy.py", "_strategy_section"),
        ("40_Stock_Recommender.py", "_recommender_section"),
        ("45_Options_Flow.py", "_options_section"),
    )
    for page_name, state_name in cases:
        tree, parents = _tree_and_parents(page_name)
        charts = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _call_name(node) == "plotly_chart"
        ]
        assert charts, f"{page_name} has no chart coverage"
        assert all(_has_section_guard(node, parents, state_name) for node in charts), (
            f"{page_name} renders a chart outside its lazy section guard"
        )

