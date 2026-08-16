"""Motion must stay on the compositor — checked against the stylesheet that ships.

This file used to scan the polish block inside utils/header.py. That was the
wrong artifact, and it passed while the change did nothing.

build_global_css() concatenates header.py's _CSS and THEN theme.py's
_MODERN_UI_CSS. theme.py owns a complete button system — hover lift, press
ripple, variants — every declaration !important. Two !important rules of equal
specificity resolve by order, so a motion rule added in header.py can never win.
Measured on the deployed page: buttons still computed `transition-property: all`
at 0.18s after the polish layer shipped.

The signal card lost the same way for a different reason — an inline
`transition:all` in its style attribute beats any non-important stylesheet rule.

So these tests assert on the BUILT stylesheet and on last-wins, because
last-wins is what the browser actually does:

  transform / opacity  -> composited on the GPU, skips layout and paint
  everything else      -> at least a paint, often a full layout pass
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_DASHBOARD = Path(__file__).resolve().parent.parent
_LAYOUT_PROPS = re.compile(
    r"\b(width|height|top|left|right|bottom|margin|padding|font-size|inset)\b"
)
# Components the motion layer claims to own.
_OWNED = {
    "button": re.compile(r"\.stButton\s*>\s*button"),
    "signal card": re.compile(r"\.ua-signal-card"),
}


@pytest.fixture(scope="module")
def built_css() -> str:
    """The concatenated stylesheet actually served at /app/static/ua-global.css."""
    spec = importlib.util.spec_from_file_location(
        "ibs", _DASHBOARD / "scripts" / "inject_boot_splash.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    css = mod.build_global_css()
    assert len(css) > 50_000, f"built stylesheet looks truncated: {len(css)} chars"
    return css


def _strip_at_blocks(css: str) -> str:
    """Remove @media/@supports blocks, braces balanced.

    Rules inside them are CONDITIONAL and must not count as the winner. Getting
    this wrong is what made the first version of this file useless: the last
    button rule in the sheet is the reduced-motion `transition: none`, so every
    check saw `none`, declared it safe, and passed while the real unconditional
    rule underneath still said `all`.
    """
    out, i, n = [], 0, len(css)
    while i < n:
        at = css.find("@", i)
        if at == -1:
            out.append(css[i:])
            break
        head = css[at : at + 9].lower()
        if not (head.startswith("@media") or head.startswith("@supports")):
            out.append(css[i : at + 1])
            i = at + 1
            continue
        out.append(css[i:at])
        brace = css.find("{", at)
        if brace == -1:
            break
        depth, j = 1, brace + 1
        while j < n and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        i = j
    return "".join(out)


def _rules(css: str, *, unconditional_only: bool = True):
    """(selector, body) for every rule, comments stripped, in file order."""
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    if unconditional_only:
        stripped = _strip_at_blocks(stripped)
    return re.findall(r"([^{}@]+)\{([^{}]*)\}", stripped)


def test_no_owned_component_declares_transition_all(built_css):
    """`all` must not appear for these components anywhere in the sheet.

    Not "the last rule isn't `all`" — an earlier version asserted that and had
    to find an unconditional rule to compare, which fails legitimately for the
    signal card, whose motion is correctly gated behind @media (hover: hover).
    Absence of an unconditional transition is fine; `all` never is.

    Conditional rules are included deliberately: a `transition: all` inside a
    media query is still a layout-animating rule whenever that query matches.
    """
    for label, pattern in _OWNED.items():
        offenders = []
        for sel, body in _rules(built_css, unconditional_only=False):
            if not pattern.search(sel):
                continue
            m = re.search(r"(?<![-\w])transition:\s*([^;]+)", body)
            if m and re.match(r"^all\b", m.group(1).strip()):
                offenders.append(f"{sel.strip()[:60]} -> {m.group(1).strip()[:60]}")
        assert not offenders, (
            f"{label} still has `transition: all`, which animates layout "
            f"properties:\n" + "\n".join(offenders)
        )


def test_no_owned_component_animates_a_layout_property(built_css):
    for label, pattern in _OWNED.items():
        for sel, body in _rules(built_css):
            if not pattern.search(sel):
                continue
            m = re.search(r"(?<![-\w])transition:\s*([^;]+)", body)
            if not m:
                continue
            val = " ".join(m.group(1).split())
            if val.startswith("all") or val.startswith("none"):
                continue
            assert not _LAYOUT_PROPS.search(val), (
                f"{label} animates a layout property: {val[:100]}"
            )


def test_the_card_carries_no_inline_transition():
    """An inline transition beats any non-important stylesheet rule.

    This is how the card kept `all 0.18s` after the polish layer shipped, and
    it is invisible to any test that only reads CSS.
    """
    page = (_DASHBOARD / "pages" / "1_Signal_Dashboard.py").read_text(encoding="utf-8")
    bad = []
    for m in re.finditer(r'<div class="ua-signal-card"', page):
        # The opening tag is split across f-string continuation lines, so scan
        # the source from the tag to the end of its style attribute rather than
        # line by line — the inline declaration sits on its own line with
        # neither the class name nor `style=` on it.
        end = page.find('">', m.end())
        window = page[m.end() : end if end != -1 else m.end() + 1200]
        if re.search(r"(?<![-\w])transition\s*:", window):
            bad.append(" ".join(window.split())[:120])
    assert not bad, (
        "the card sets transition inline, which overrides any non-important "
        "stylesheet rule:\n" + "\n".join(bad)
    )


def test_reduced_motion_has_the_last_word_on_transforms(built_css):
    """The guard must come after the rules it suppresses.

    header.py's guard could never reach theme.py's button hover: same
    specificity, both !important, theme.py concatenated later.
    """
    from utils.theme import _MODERN_UI_CSS

    # theme.py is the LAST block concatenated, and it is where the button hover
    # transform is set with !important. So the guard has to live in this file
    # specifically — one in header.py cannot reach these rules, whatever its
    # specificity. Asserting on the built string's byte offsets proved too
    # indirect: it still passed with theme.py's guard deleted.
    assert "prefers-reduced-motion" in _MODERN_UI_CSS, (
        "theme.py has no reduced-motion guard. Its button hover transform is "
        "!important and concatenated after header.py, so header.py's guard "
        "cannot suppress it."
    )
    guard = _MODERN_UI_CSS[_MODERN_UI_CSS.index("prefers-reduced-motion") :]
    assert re.search(r"transform:\s*none\s*!important", guard), (
        "the guard must set transform: none !important — a shortened duration "
        "still moves the element, just quickly"
    )
    assert ".stButton" in guard[: guard.find("}\n}") + 3 if "}\n}" in guard else 800], (
        "the guard does not cover the buttons whose hover transform it exists for"
    )


def test_the_motion_tokens_exist_and_are_ordered(built_css):
    fast = re.search(r"--ua-dur-fast:\s*(\d+)ms", built_css)
    base = re.search(r"--ua-dur-base:\s*(\d+)ms", built_css)
    slow = re.search(r"--ua-dur-slow:\s*(\d+)ms", built_css)
    assert fast and base and slow, "the duration tokens are missing from the built CSS"
    f, b, s = int(fast.group(1)), int(base.group(1)), int(slow.group(1))
    assert f < b < s, f"durations must ascend, got {f}/{b}/{s}"
    assert s <= 400, f"{s}ms is past the point where a UI feels like it is waiting"


def test_theme_css_uses_motion_tokens_only_with_fallbacks():
    """theme.py's block can be injected WITHOUT header.py's :root.

    inject_all_css() ships _MODERN_UI_CSS on its own on some pages. header.py's
    own rules are safe — the :root definitions travel in the same string — but a
    bare var(--ua-dur-fast) in theme.py would resolve to nothing on those pages
    and drop the transition entirely.
    """
    from utils.theme import _MODERN_UI_CSS

    defines_root = "--ua-dur-fast:" in _MODERN_UI_CSS
    for m in re.finditer(r"var\(--ua-(?:dur|ease)-[\w-]+\s*(,?)", _MODERN_UI_CSS):
        assert m.group(1) == "," or defines_root, (
            f"theme.py uses {m.group(0)[:44]} with no fallback and does not "
            f"define the token itself; on a page that injects only this block "
            f"the transition dies"
        )
