"""User-facing ticker-universe claims must come from product_metrics.

The app previously advertised 80+, 193, and 280+ tickers on different pages
while the configured universe contained exactly 280. Marketing-style numeric
claims and f-strings that call ``len(TICKERS)`` directly are both prohibited:
all UI copy must use ``SUPPORTED_TICKER_COUNT`` instead.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


PAGES = Path(__file__).resolve().parent.parent / "pages"
HARDCODED_UNIVERSE = re.compile(
    r"\b(?:[5-9]\d|[1-9]\d{2,3})\+?\s+(?:supported\s+)?tickers?\b"
    r"|\b(?:[5-9]\d|[1-9]\d{2,3})-ticker\s+(?:supported\s+)?universe\b",
    re.IGNORECASE,
)


def _ui_trees() -> list[tuple[Path, ast.AST]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in sorted(PAGES.rglob("*.py"))
    ]


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Return AST ids for documentation text that is never rendered in the UI."""
    docs: set[int] = set()
    containers = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if not isinstance(node, containers) or not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            docs.add(id(first.value))
    return docs


def test_no_ui_string_hardcodes_a_large_ticker_count():
    offenders: list[str] = []
    for path, tree in _ui_trees():
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            if HARDCODED_UNIVERSE.search(node.value):
                offenders.append(f"{path.relative_to(PAGES)}:{node.lineno}")
    assert not offenders, (
        "ticker-universe claims must use SUPPORTED_TICKER_COUNT: "
        + ", ".join(offenders)
    )


def test_no_ui_fstring_computes_len_tickers_directly():
    offenders: list[str] = []
    for path, tree in _ui_trees():
        for joined in (node for node in ast.walk(tree) if isinstance(node, ast.JoinedStr)):
            for node in ast.walk(joined):
                if not isinstance(node, ast.Call) or len(node.args) != 1:
                    continue
                if not isinstance(node.func, ast.Name) or node.func.id != "len":
                    continue
                arg = node.args[0]
                if isinstance(arg, ast.Name) and arg.id == "TICKERS":
                    offenders.append(f"{path.relative_to(PAGES)}:{node.lineno}")
    assert not offenders, (
        "UI f-strings must use SUPPORTED_TICKER_COUNT, not len(TICKERS): "
        + ", ".join(offenders)
    )
