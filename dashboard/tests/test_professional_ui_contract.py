"""Regression checks for the restrained, product-wide visual system."""

from __future__ import annotations

import ast
from pathlib import Path


DASHBOARD = Path(__file__).resolve().parents[1]
ACTIVE_UI_FILES = [
    DASHBOARD / "app.py",
    DASHBOARD / "utils" / "header.py",
    DASHBOARD / "utils" / "theme.py",
    *sorted((DASHBOARD / "pages").glob("*.py")),
]

# Decorative pictographs that previously appeared in navigation, tabs, calls to
# action, alerts, and analytical labels. Directional finance symbols are kept.
BANNED_DECORATIVE_GLYPHS = set(
    "🔬📉📐📊🔄💰😨🏭🛢️📋📰👁⚡📈⚖️✅📌📬📂⭐⚙🔥🗺💻⛽🏦🏥🛒🛠🌐🚀"
    "🎯🔗👥📡🔍🔓🎉🟣🏆🔒📧🧮👋🎚🖼⚗📖📄⏳⬇🔔👤❌🟢🔴⚪🟡🎭🧭💡"
    "⚠🥇🥈🥉📅🔮💼🐦♾🎁⏱🤖🗂🧺ℹ🧪★"
)


def test_active_ui_has_no_decorative_emoji() -> None:
    failures: list[str] = []
    for path in ACTIVE_UI_FILES:
        source = path.read_text(encoding="utf-8")
        found = sorted(BANNED_DECORATIVE_GLYPHS.intersection(source))
        if found:
            failures.append(f"{path.relative_to(DASHBOARD)}: {''.join(found)}")
    assert not failures, "Decorative emoji remain in active UI:\n" + "\n".join(failures)


def test_every_active_plotly_render_opts_out_of_streamlit_theme() -> None:
    failures: list[str] = []
    render_count = 0
    for path in ACTIVE_UI_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "plotly_chart"
            ):
                continue
            render_count += 1
            has_theme_none = any(
                keyword.arg == "theme"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is None
                for keyword in node.keywords
            )
            if not has_theme_none:
                failures.append(f"{path.relative_to(DASHBOARD)}:{node.lineno}")

    assert render_count > 0
    assert not failures, "Plotly renders missing theme=None: " + ", ".join(failures)


def test_plotly_interactions_remain_restrained() -> None:
    theme_source = (DASHBOARD / "utils" / "theme.py").read_text(encoding="utf-8")
    assert '"scrollZoom": False' in theme_source
    assert '"displayModeBar": True' not in theme_source
