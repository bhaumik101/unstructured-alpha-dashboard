"""The visual system has to be able to converge, not just exist.

The product had 25 design tokens and every one of them was a colour. There was
no type scale, no spacing scale. So every surface invented its own geometry, and
the result was 107 distinct font-size literals across 1,526 uses -- with steps
like 0.68 / 0.70 / 0.72 / 0.74 / 0.75 / 0.76rem that are a third of a pixel
apart. Nobody chose between those; they accumulated. A dense field of
near-identical values that no one picked is the mechanical signature of a UI
that reads as generated rather than designed.

Adding scales does not fix that on its own -- 1,526 call sites cannot be
rewritten safely in one change, and certainly not without looking at every page.
So this file does two things:

  1. asserts the scales exist, in both themes, and stay ordered
  2. ratchets the literal count so the debt can only ever shrink

The ratchet is the part that matters. It does not demand a big-bang refactor; it
makes the next person's default the token instead of a fresh magic number, and
it turns "we should clean this up someday" into a number that cannot go up.
Lower BASELINE_* whenever you retire literals. Never raise it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

# Measured on the commit that introduced the scales. These are ceilings, not
# targets: they exist to be lowered.
BASELINE_DISTINCT_FONT_SIZES = 105
BASELINE_FONT_SIZE_OCCURRENCES = 1443
BASELINE_DISTINCT_RADII = 19

_FONT_SIZE = re.compile(r"font-size:\s*([0-9.]+)(rem|px|em)")
_RADIUS = re.compile(r"border-radius:\s*([0-9.]+)(px|rem)")

_TYPE_STEPS = [
    "--ua-text-2xs",
    "--ua-text-xs",
    "--ua-text-sm",
    "--ua-text-base",
    "--ua-text-md",
    "--ua-text-lg",
    "--ua-text-xl",
    "--ua-text-2xl",
    "--ua-text-3xl",
]
_SPACE_STEPS = [f"--ua-space-{n}" for n in range(1, 9)]


def _active_ui_files() -> list[Path]:
    """Browser-rendered UI only.

    utils/email.py is deliberately NOT migrated to tokens and stays in raw
    literals: email clients do not support CSS custom properties, so a
    var(--ua-text-sm) in an email body silently falls back to the client's
    default size. It is still counted here, because a raw literal there is
    correct rather than debt.
    """
    files = [DASHBOARD / "app.py"]
    files += sorted((DASHBOARD / "pages").glob("*.py"))
    files += sorted((DASHBOARD / "utils").glob("*.py"))
    return [f for f in files if f.exists()]


def _theme_css() -> str:
    return (DASHBOARD / "utils" / "header.py").read_text(encoding="utf-8")


def test_type_and_spacing_scales_are_defined() -> None:
    css = _theme_css()
    missing = [t for t in _TYPE_STEPS + _SPACE_STEPS if f"{t}:" not in css]
    assert not missing, f"design tokens not defined: {missing}"


def test_type_scale_steps_are_visibly_distinct() -> None:
    """Every step must be a jump you can actually see.

    A scale whose neighbours differ by 0.02rem is not a scale, it is the same
    sprawl with nicer names -- which is the exact failure being corrected.
    """
    css = _theme_css()
    sizes = []
    for token in _TYPE_STEPS:
        match = re.search(rf"{re.escape(token)}:\s*([0-9.]+)rem", css)
        assert match, f"{token} is not defined in rem"
        sizes.append(float(match.group(1)))

    assert sizes == sorted(sizes), f"type scale is not monotonic: {sizes}"
    for smaller, larger in zip(sizes, sizes[1:]):
        ratio = larger / smaller
        assert ratio >= 1.08, (
            f"steps {smaller}rem and {larger}rem differ by {ratio:.3f}x — under "
            "8% is invisible at these sizes, so it is not a real step"
        )


def test_spacing_scale_is_a_consistent_rhythm() -> None:
    css = _theme_css()
    values = []
    for token in _SPACE_STEPS:
        match = re.search(rf"{re.escape(token)}:\s*([0-9.]+)px", css)
        assert match, f"{token} is not defined in px"
        values.append(float(match.group(1)))

    assert values == sorted(values), f"spacing scale is not monotonic: {values}"
    assert all(v % 4 == 0 for v in values), (
        f"spacing must stay on the 4px grid, got {values}"
    )


def test_font_size_literals_do_not_grow() -> None:
    """Ratchet. Lower the baseline when you retire literals; never raise it."""
    distinct: set[str] = set()
    occurrences = 0
    for path in _active_ui_files():
        for match in _FONT_SIZE.finditer(path.read_text(encoding="utf-8")):
            distinct.add(match.group(1) + match.group(2))
            occurrences += 1

    assert len(distinct) <= BASELINE_DISTINCT_FONT_SIZES, (
        f"distinct font-size literals rose to {len(distinct)} (baseline "
        f"{BASELINE_DISTINCT_FONT_SIZES}). Use a --ua-text-* token instead of a "
        "new raw value."
    )
    assert occurrences <= BASELINE_FONT_SIZE_OCCURRENCES, (
        f"raw font-size uses rose to {occurrences} (baseline "
        f"{BASELINE_FONT_SIZE_OCCURRENCES}). Use a --ua-text-* token."
    )


def test_radius_literals_do_not_grow() -> None:
    distinct: set[str] = set()
    for path in _active_ui_files():
        for match in _RADIUS.finditer(path.read_text(encoding="utf-8")):
            distinct.add(match.group(1) + match.group(2))

    assert len(distinct) <= BASELINE_DISTINCT_RADII, (
        f"distinct border-radius literals rose to {len(distinct)} (baseline "
        f"{BASELINE_DISTINCT_RADII}). Use --ua-radius, --ua-radius-sm/lg/xs or "
        "--ua-radius-pill."
    )


def test_scales_are_theme_independent() -> None:
    """Geometry must not fork per theme.

    Colours legitimately differ between light and dark. Sizes and gaps do not,
    and a light-mode-only override is how the two themes drift apart into
    subtly different products.
    """
    css = _theme_css()
    light_start = css.find('html[data-ua-theme="light"]')
    assert light_start > 0, "light theme block not found"
    light_block = css[light_start : light_start + 4000]

    forked = [t for t in _TYPE_STEPS + _SPACE_STEPS if f"{t}:" in light_block]
    assert not forked, (
        f"geometry tokens redefined for light mode: {forked}. Type and spacing "
        "are theme-independent; only colour should differ."
    )
