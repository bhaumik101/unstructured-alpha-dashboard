"""Guards against blank Streamlit canvas-backed data grids."""

from pathlib import Path


HEADER = Path("utils/header.py").read_text(encoding="utf-8")

def test_dataframe_scroll_overlay_is_transparent():
    assert ".dvn-scroller { background: transparent !important; }" in HEADER
    assert ".dvn-scroller { background: var(--ua-bg-card) !important; }" not in HEADER


def test_dataframe_fix_is_theme_agnostic():
    # The rule is intentionally unscoped so it protects both dark and light mode.
    selector_index = HEADER.index(".dvn-scroller { background: transparent")
    preceding_line = HEADER[:selector_index].splitlines()[-1]
    assert 'html[data-ua-theme="light"]' not in preceding_line
