"""The dependency-free SVG chart engine (utils/ua_charts).

These lock the structural contract every generator must keep: valid single-root
SVG, real axes + gridlines + ticks, the right number of plotted marks, safe HTML
escaping, and theme-variable colors (so charts re-theme with light/dark). No
browser needed — the output is a deterministic string.
"""

from __future__ import annotations

import re

from utils import ua_charts as C


def _one_svg(s: str):
    assert s.startswith("<svg") and s.rstrip().endswith("</svg>")
    assert s.count("<svg") == 1 and s.count("</svg>") == 1
    assert 'class="ua-chart"' in s


def _has_class(svg: str, name: str) -> bool:
    """True if any element carries `name` among its classes."""
    return any(
        name in attr.split()
        for attr in re.findall(r'class="([^"]*)"', svg)
    )


def test_line_chart_has_axes_grid_line_and_area():
    s = C.line_chart([10, 20, 15, 40, 64], ["a", "b", "c", "d", "e"],
                     y_min=0, y_max=80, ref=50, y_title="Score")
    _one_svg(s)
    assert 'class="axis"' in s          # x and y axis lines
    assert 'class="grid"' in s          # gridlines
    # Match the CLASS, not the whole attribute: `cline` now travels with a
    # modifier (`cline ua-chart-glow` / `cline ua-chart-line`), and an exact
    # `class="cline"` string test breaks on any additional class without the
    # element having changed.
    assert _has_class(s, "cline") and _has_class(s, "area")
    assert 'class="refline"' in s       # neutral reference line
    assert "Score" in s                 # y-axis title
    assert _has_class(s, "dot")         # current-point marker


def test_line_chart_downsamples_plain_labels_to_ticks():
    labels = [f"D-{i}" for i in range(31)]
    s = C.line_chart(list(range(31)), labels, y_min=0, y_max=31)
    # ~6 x tick labels, not 31
    ticks = re.findall(r'class="tick"[^>]*text-anchor="middle"', s)
    assert 3 <= len(ticks) <= 7


def test_bar_h_one_rect_and_value_label_per_category():
    s = C.bar_h(["Bullish", "Bearish", "Neutral"], [15, 9, 20], max_v=24,
                colors=["var(--ua-pos)", "var(--ua-neg)", "var(--ua-neutral)"])
    _one_svg(s)
    assert s.count("<rect") == 3                 # one bar per category
    assert s.count('class="vlabel"') == 3        # one value label per bar
    assert "Bullish" in s and "Neutral" in s
    assert 'class="grid"' in s and 'class="axis"' in s


def test_bar_h_percent_unit_formats_ticks_and_values():
    s = C.bar_h(["Industrial Production", "10-Year Treasury"], [4.3, 0.02],
                max_v=5, unit="%")
    assert "4.3%" in s          # value label keeps the decimal
    assert "%</text>" in s      # axis ticks carry the percent unit


def test_bar_v_has_both_axis_titles_and_a_bar_per_category():
    cats = ["0w", "4w", "8w", "52w"]
    s = C.bar_v(cats, [2, 14, 11, 1], max_v=16,
                y_title="# of signals", x_title="Lead time")
    _one_svg(s)
    assert s.count("<rect") == 4
    assert "# of signals" in s and "Lead time" in s
    for c in cats:
        assert c in s


def test_colors_use_theme_variables_so_charts_retheme():
    # Line/area/dot colors live in the CHART_CSS classes; bar colors are inline.
    # Both must reference CSS variables so a light/dark flip recolors them.
    assert "var(--ua-royal-2" in C.CHART_CSS
    assert "var(--ua-grid" in C.CHART_CSS and "var(--ua-muted" in C.CHART_CSS
    assert "var(--ua-royal" in C.bar_v(["a", "b"], [1, 2])       # default bar color
    assert "var(--ua-royal-2" in C.bar_h(["a"], [1])             # default bar color


def test_labels_are_html_escaped():
    s = C.bar_h(["<script>&x"], [3], max_v=5)
    assert "<script>" not in s.replace('<svg', '')  # category text escaped
    assert "&lt;script&gt;" in s or "&amp;" in s


def test_fmt_trims_integers_but_keeps_decimals():
    assert C._fmt(24.0) == "24"
    assert C._fmt(0.24) == "0.24"
    assert C._fmt(47) == "47"
