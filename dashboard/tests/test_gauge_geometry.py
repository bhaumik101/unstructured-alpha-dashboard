"""Geometry assertions for the Confluence gauge SVG.

The gauge shipped with two overlapping-element bugs that no test could catch,
because every existing check only asserted that the SVG *string* contained the
score. Both bugs were purely positional:

  1. The needle pivot cap (circle at CY, r=6) and the score digits (baseline
     CY+20, font-size 28) both occupied roughly y 79..86. The white cap sat on
     top of the number, and near score 0 or 100 the needle lies almost
     horizontal through the pivot and cut across the digits.

  2. The "50" axis label (baseline y=12, x=CX) and the CONFLUENCE header
     (baseline y=10, x=CX) were printed on top of each other.

These tests reconstruct each element's bounding box from the emitted SVG and
assert the boxes are disjoint, so a future tweak to a radius, font size or
baseline fails here instead of on the page.
"""

from __future__ import annotations

import re

import pytest

from utils.theme import confluence_gauge_svg

# Ratio of a font's cap height to its em size. Inter's cap height is 0.727em;
# 0.75 is used as a slightly conservative (taller) estimate so the tests fail
# before a human would notice a collision, not after.
CAP_HEIGHT_RATIO = 0.75
# Descender depth below the baseline, same conservative treatment.
DESCENDER_RATIO = 0.25

SCORES = [0, 1, 12, 35, 36, 50, 64, 65, 88, 99, 100]


def _texts(svg: str):
    """Yield (x, baseline_y, font_size, content) for every <text> in the SVG."""
    for m in re.finditer(r"<text\b([^>]*)>(.*?)</text>", svg, re.S):
        attrs, content = m.group(1), m.group(2)

        def _attr(name, default=None):
            a = re.search(rf'{name}="([^"]+)"', attrs)
            return a.group(1) if a else default

        yield (
            float(_attr("x")),
            float(_attr("y")),
            float(_attr("font-size", "10")),
            content.strip(),
        )


def _circles(svg: str):
    """Yield (cx, cy, r) for every <circle> in the SVG."""
    for m in re.finditer(r"<circle\b([^>]*)/>", svg):
        attrs = m.group(1)

        def _attr(name):
            return float(re.search(rf'{name}="([^"]+)"', attrs).group(1))

        yield _attr("cx"), _attr("cy"), _attr("r")


def _vspan(baseline: float, font_size: float) -> tuple[float, float]:
    """Vertical extent (top, bottom) of a text run around its baseline."""
    return baseline - font_size * CAP_HEIGHT_RATIO, baseline + font_size * DESCENDER_RATIO


def _viewbox(svg: str) -> tuple[float, float, float, float]:
    vb = re.search(r'viewBox="([^"]+)"', svg).group(1).split()
    return tuple(float(v) for v in vb)  # type: ignore[return-value]


def _find_text(svg: str, predicate):
    return [t for t in _texts(svg) if predicate(t)]


# ── The two bugs, pinned ──────────────────────────────────────────────────────

@pytest.mark.parametrize("score", SCORES)
def test_score_digits_clear_the_needle_pivot_cap(score):
    """The number must sit entirely below the white pivot cap."""
    svg = confluence_gauge_svg(score)

    cap_bottom = max(cy + r for _, cy, r in _circles(svg))

    digits = _find_text(svg, lambda t: t[3] == f"{score:.0f}")
    assert digits, f"score readout {score:.0f} not found in gauge"
    x, baseline, fs, _ = digits[0]
    top, _bottom = _vspan(baseline, fs)

    assert top >= cap_bottom, (
        f"score {score}: digits start at y={top:.1f} but the pivot cap extends to "
        f"y={cap_bottom:.1f} — the white dot overlaps the number by "
        f"{cap_bottom - top:.1f}px"
    )


@pytest.mark.parametrize("score", SCORES)
def test_needle_never_crosses_the_score_digits(score):
    """The needle is drawn outward from the pivot, so its lowest point must
    still clear the digits. Near score 0/100 the needle is nearly horizontal at
    the pivot's height, which is how it used to slice through the number."""
    svg = confluence_gauge_svg(score)

    line = re.search(
        r'<line x1="([-\d.]+)" y1="([-\d.]+)" x2="([-\d.]+)" y2="([-\d.]+)"[^>]*'
        r'stroke="#FFFFFF"',
        svg,
    )
    assert line, "needle not found"
    needle_bottom = max(float(line.group(2)), float(line.group(4)))

    digits = _find_text(svg, lambda t: t[3] == f"{score:.0f}")[0]
    top, _ = _vspan(digits[1], digits[2])

    assert needle_bottom <= top, (
        f"score {score}: needle reaches y={needle_bottom:.1f}, digits start at "
        f"y={top:.1f} — the needle crosses the number"
    )


def test_header_and_axis_label_do_not_overlap():
    """CONFLUENCE and the "50" tick share the centre line and must not collide."""
    svg = confluence_gauge_svg(50)

    header = _find_text(svg, lambda t: t[3] == "CONFLUENCE")
    assert header, "CONFLUENCE header not found"
    mid_lbl = _find_text(svg, lambda t: t[3] == "50" and abs(t[0] - 100) < 1)
    assert mid_lbl, '"50" axis label not found on the centre line'

    h_top, h_bottom = _vspan(header[0][1], header[0][2])
    l_top, l_bottom = _vspan(mid_lbl[0][1], mid_lbl[0][2])

    assert h_bottom <= l_top or l_bottom <= h_top, (
        f"CONFLUENCE spans y {h_top:.1f}..{h_bottom:.1f} and the '50' label spans "
        f"y {l_top:.1f}..{l_bottom:.1f} — they overlap"
    )


# ── General invariants ────────────────────────────────────────────────────────

@pytest.mark.parametrize("score", SCORES)
def test_all_text_fits_inside_the_viewbox(score):
    """Relocating the readout downward is only safe if the viewBox grew too."""
    svg = confluence_gauge_svg(score)
    _vx, vy, _vw, vh = _viewbox(svg)
    v_top, v_bottom = vy, vy + vh

    for x, baseline, fs, content in _texts(svg):
        top, bottom = _vspan(baseline, fs)
        assert top >= v_top - 0.5, f"{content!r} clipped at the top ({top:.1f} < {v_top})"
        assert bottom <= v_bottom + 0.5, (
            f"{content!r} clipped at the bottom ({bottom:.1f} > {v_bottom})"
        )


@pytest.mark.parametrize("score", SCORES)
def test_no_two_centreline_elements_overlap(score):
    """Everything centred on x=CX has to be vertically disjoint.

    This is the general form of both bugs: the gauge stacks header, axis label,
    dial, cap, score and case label on one column, and nothing enforced a
    vertical budget between them.
    """
    svg = confluence_gauge_svg(score)

    boxes = []
    for x, baseline, fs, content in _texts(svg):
        if abs(x - 100) < 1:  # on the centre line
            top, bottom = _vspan(baseline, fs)
            boxes.append((top, bottom, content))
    for _cx, cy, r in _circles(svg):
        boxes.append((cy - r, cy + r, f"cap(r={r})"))

    boxes.sort()
    for (t1, b1, n1), (t2, b2, n2) in zip(boxes, boxes[1:]):
        # Concentric cap circles are allowed to overlap each other.
        if n1.startswith("cap") and n2.startswith("cap"):
            continue
        assert b1 <= t2 + 0.01, (
            f"score {score}: {n1!r} (y {t1:.1f}..{b1:.1f}) overlaps "
            f"{n2!r} (y {t2:.1f}..{b2:.1f})"
        )


@pytest.mark.parametrize("score,expected_case", [(80, "BULL"), (50, "NEUTRAL"), (10, "BEAR")])
def test_case_label_still_derived_from_score(score, expected_case):
    """Guard the behaviour while moving the pixels."""
    assert expected_case in confluence_gauge_svg(score)


def test_explicit_case_overrides_derived_case():
    assert "BULL" in confluence_gauge_svg(50, case="BULL")


@pytest.mark.parametrize("score", [-20, 0, 100, 140])
def test_score_is_clamped(score):
    svg = confluence_gauge_svg(score)
    shown = _find_text(svg, lambda t: t[3].isdigit() and t[0] == 100 and t[2] > 15)
    assert shown, "score readout not found"
    assert 0 <= float(shown[0][3]) <= 100
