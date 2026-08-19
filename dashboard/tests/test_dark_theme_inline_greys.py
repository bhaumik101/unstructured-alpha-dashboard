"""Two inline greys were unreadable on the dark ground, and the token test could not see them.

tests/test_theme_contrast.py compares TOKEN pairs, and every light pair clears
AA. These two are inline literals emitted by pages, so no token comparison
reaches them. axe-core against the live app did:

    #4A5280  11.5px on #0a0d12   2.60:1   Signal Dashboard cadence line
    #4A5568   9.6px on #101318   2.47:1   Sector View source captions (4 nodes)

Both are remapped to --ua-ink-mut for the dark theme, which is what the light
theme already did with the same two literals for the same reason. The token
clears AA on every dark surface (5.85 raised / 5.97 card / 6.24 page), so this
puts one muted grey in the system rather than three.

WHY THE SELECTOR HAS FOUR FORMS PER COLOUR
------------------------------------------
The remap matches the inline style STRING, so it needs every spelling the
codebase emits: `color: #X` and `color:#X`, each at the start of the attribute
and mid-attribute after a semicolon. A missing form is a silent no-op -- that
exact gap shipped once before, documented in test_theme_contrast.py.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CSS = (_ROOT / "utils" / "header.py").read_text(encoding="utf-8")

# The two axe found, with the ground each was measured against.
_FAILING = {"#4A5280": "#0a0d12", "#4A5568": "#101318"}


def _luminance(h: str) -> float:
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _dark_remap_block() -> str:
    m = re.search(
        r'html:not\(\[data-ua-theme="light"\]\) :is\((.*?)\)\s*\{([^}]*)\}',
        _CSS, re.S,
    )
    assert m, "the dark-theme inline-colour remap block is gone"
    return m.group(1) + "||" + m.group(2)


def test_the_failing_greys_are_remapped_for_dark():
    selectors, rule = _dark_remap_block().split("||")
    for hex_ in _FAILING:
        assert hex_ in selectors, f"{hex_} is not remapped for the dark theme"
    assert "var(--ua-ink-mut)" in rule, "the remap should target the muted token"
    assert "!important" in rule, (
        "these are inline styles; without !important the remap never applies"
    )


def test_each_colour_has_every_spelling_the_codebase_emits():
    selectors, _ = _dark_remap_block().split("||")
    for hex_ in _FAILING:
        forms = [
            f'[style^="color: {hex_}" i]',
            f'[style^="color:{hex_}" i]',
            f'[style*="; color: {hex_}" i]',
            f'[style*=";color:{hex_}" i]',
        ]
        missing = [f for f in forms if f not in selectors]
        assert not missing, (
            f"{hex_} is missing selector form(s), so pages emitting that "
            f"spelling keep the unreadable colour: {missing}"
        )


def test_the_replacement_token_actually_clears_aa():
    """A remap to a colour that also fails would be motion without progress."""
    m = re.search(r"--ua-ink-mut:\s*(#[0-9A-Fa-f]{6})", _CSS)
    assert m, "--ua-ink-mut is not defined"
    token = m.group(1)
    for hex_, ground in _FAILING.items():
        assert _contrast(hex_, ground) < 4.5, (
            f"{hex_} on {ground} now measures "
            f"{_contrast(hex_, ground):.2f}:1 — this test is guarding a fixed bug"
        )
        assert _contrast(token, ground) >= 4.5, (
            f"--ua-ink-mut ({token}) is {_contrast(token, ground):.2f}:1 on "
            f"{ground}, so the remap does not fix the page"
        )


def test_scrollable_regions_are_made_keyboard_reachable():
    """axe: scrollable-region-focusable. Streamlit owns that DOM, so JS is the hook."""
    js = (_ROOT / "scripts" / "inject_boot_splash.py").read_text(encoding="utf-8")
    assert "uaFocusableScrollers" in js, "the scrollable-region fix is gone"
    assert "setAttribute('tabindex','0')" in js, (
        "the fix no longer makes the scroller focusable"
    )
    body = js[js.index("function uaFocusableScrollers"):]
    body = body[: body.index("\n  }")]
    assert "scrollHeight" in body and "scrollWidth" in body, (
        "it must only tag containers that actually overflow, in either axis"
    )
    assert "querySelector('a[href],button" in body, (
        "it must skip regions that already contain something focusable, or it "
        "adds a redundant tab stop in front of working controls"
    )
    assert "uaFocusableScrollers();" in js.split("MutationObserver")[1][:200], (
        "it must re-run on mutation; Streamlit renders these containers after "
        "first paint"
    )
