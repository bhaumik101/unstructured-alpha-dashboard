"""Catch conditions that an emoji strip silently turned into "always true".

Found live on 2026-08-11 on the Signal Dashboard card:

    # Only show fatigue for Extended/Exhausted -- Fresh/Established add noise
    ... if _streak_label.startswith(("", "")) else
    ... if _streak_label.startswith("")       else ""

The literals were once "⏳"/"🔴" and "🟢". Something stripped the emoji out of
this file (the labels themselves still carry them, in utils/score_history.py,
which the emoji contract test does not scan). `"anything".startswith("")` is
True, so the first branch won every time: the badge rendered on EVERY card,
the green branch became unreachable, and "Established" -- which the comment
directly above says to hide -- shipped onto cards.

Nothing failed. The page rendered, the suite stayed green, and the only
symptom was noise on screen.

This matters more going forward, not less: the plan is to replace the
remaining category emoji with SVG, which means more edits of exactly this
shape.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCAN_DIRS = ("pages", "utils", "cron", "scripts")

# str methods where an empty-string argument makes the call a no-op or a
# tautology rather than a test.
_VACUOUS_ARG_METHODS = {"startswith", "endswith", "strip", "lstrip", "rstrip"}


def _python_files() -> list[Path]:
    files: list[Path] = []
    for d in _SCAN_DIRS:
        files.extend(p for p in (_ROOT / d).rglob("*.py") if "retired" not in p.parts)
    assert files, "scanned no files -- the layout changed"
    return files


def _empty_str_literals(node: ast.AST) -> bool:
    """True if the node is "" or a tuple/list containing ""."""
    if isinstance(node, ast.Constant):
        return node.value == ""
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return any(
            isinstance(e, ast.Constant) and e.value == "" for e in node.elts
        )
    return False


def test_no_string_test_is_satisfied_by_every_string():
    """`x.startswith("")` is True for all x -- it is not a condition."""
    offenders: list[str] = []
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - compileall is the real gate
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            if not isinstance(fn, ast.Attribute) or fn.attr not in _VACUOUS_ARG_METHODS:
                continue
            if any(_empty_str_literals(a) for a in node.args):
                offenders.append(
                    f"{path.relative_to(_ROOT).as_posix()}:{node.lineno} "
                    f".{fn.attr}() with an empty-string argument"
                )

    assert not offenders, (
        "these string tests match every string, so the branch they guard always "
        "runs (or never does). Usually the sign of a literal -- an emoji, a "
        "prefix -- having been deleted out of the condition:\n  "
        + "\n  ".join(offenders)
    )


def test_the_card_fatigue_badge_still_says_what_it_means():
    """Pin the specific case, on the words rather than the emoji.

    The general scan above would pass on `startswith(("X", "Y"))` for any X/Y,
    including wrong ones. This asserts the branch actually names the two
    statuses its comment promises.
    """
    src = (_ROOT / "pages" / "1_Signal_Dashboard.py").read_text(encoding="utf-8")
    # Assert on the CODE, not the comment: the comment named both statuses even
    # while the condition ignored them, so matching prose proves nothing.
    code = [
        ln.strip()
        for ln in src.splitlines()
        if "_show_fatigue" in ln and not ln.strip().startswith("#")
    ]
    assert code, "the fatigue badge no longer has an explicit condition"
    decl = next((ln for ln in code if ln.startswith("_show_fatigue")), "")
    assert "Extended" in decl and "Exhausted" in decl, (
        f"the fatigue condition must name both statuses its comment promises: {decl!r}"
    )
    assert "Established" not in decl and "Fresh" not in decl, (
        f"Established/Fresh are documented as noise and must stay hidden: {decl!r}"
    )
