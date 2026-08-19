"""Primary email CTAs must be real buttons, and legible in Outlook.

Outlook on Windows renders through Word, which does not support CSS gradients.
A CTA styled `background: linear-gradient(...)` therefore gets NO background
there -- the fill silently disappears and only the text colour survives.

On the dark-themed emails that was cosmetic: the button lost its shape but the
white label still sat on a dark shell at 15-19:1. On two emails it was not:

    send_trial_reminder_email   #fff on #FFFFFF body   = 1.00:1
    send_velocity_alert_email   #0B0D12 on #0f1119     = 1.03:1

Both were invisible. The first is the entire point of the trial-ending email --
the one CTA whose job is to convert a trialing user to paid.

email_button() already existed to solve exactly this (a VML roundrect gives Word
a real filled button) but nothing called it. These tests keep every primary CTA
routed through it, and keep the label readable against the fill.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = (_ROOT / "utils" / "email.py").read_text(encoding="utf-8")

# email_button()'s own defaults, applied when a call omits them.
_DEFAULT_BG = "#5B4BE8"
_DEFAULT_FG = "#FFFFFF"


def _luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _button_calls() -> list[tuple[int, str, str]]:
    """(lineno, bg, fg) for every email_button() call site."""
    out = []
    for node in ast.walk(ast.parse(_SRC)):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "email_button"):
            continue
        kw = {
            k.arg: k.value.value
            for k in node.keywords
            if isinstance(k.value, ast.Constant) and isinstance(k.value.value, str)
        }
        out.append((node.lineno, kw.get("bg", _DEFAULT_BG), kw.get("fg", _DEFAULT_FG)))
    return out


def test_no_cta_uses_a_gradient_background():
    """A gradient fill is invisible in Word, which is Outlook on Windows."""
    bad = []
    for m in re.finditer(r"<a\s+href=[^>]*?>", _SRC, re.S):
        if "linear-gradient" in m.group(0):
            bad.append(_SRC[: m.start()].count("\n") + 1)
    assert not bad, (
        "these CTAs use a gradient background, which Outlook drops entirely, "
        "leaving the label on whatever is behind it: lines "
        + ", ".join(map(str, bad))
        + "\nuse email_button(), which supplies a VML fill for Word"
    )


def test_every_button_label_is_readable_on_its_fill():
    """WCAG AA for normal text. The label is the button."""
    failures = []
    for lineno, bg, fg in _button_calls():
        ratio = _contrast(fg, bg)
        if ratio < 4.5:
            failures.append(f"line {lineno}: {fg} on {bg} = {ratio:.2f}:1")
    assert not failures, (
        "these email buttons do not meet 4.5:1:\n  " + "\n  ".join(failures)
    )


def test_the_primary_ctas_actually_route_through_email_button():
    """Guards against a CTA being hand-rolled again alongside the helper.

    Counts call sites rather than naming them, so adding an email does not
    require editing this test -- but removing the wiring wholesale fails.
    """
    calls = _button_calls()
    assert len(calls) >= 13, (
        f"only {len(calls)} email_button() call sites; the primary CTAs are "
        "expected to route through the helper so Outlook gets a real button"
    )
