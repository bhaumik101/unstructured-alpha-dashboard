"""Charts should not fall back to Plotly's untouched defaults.

Two measured gaps in the chart system:

  * 25 of 61 figure regions defined no hover at all, so hovering printed
    Plotly's default "(x, y)" tuple at full float precision. Eleven of those
    were Market Overview's macro charts -- dated series where a unified header
    with the date and a comma-formatted value is the obvious read.
  * 56 figures were sized with 23 different literal heights. 240, 250 and 260
    all appear; so do 300, 320 and 350. Most of that spread is not a decision.

utils.theme now carries a named height scale and a hover filler. The filler is
deliberately additive: a chart with its own hovertemplate keeps it, so this can
be applied to a shared helper without overriding hand-written hovers.
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import pytest

from utils.theme import (
    CHART_HEIGHTS,
    apply_default_hover,
    chart_height,
)


# ── the height vocabulary ────────────────────────────────────────────────────

def test_the_scale_covers_the_peaks_of_the_measured_distribution():
    """220, 280, 320 and 380 are 27 of the 56 sites between them.

    A scale that missed them would force a visual change on every chart that
    adopted it, which is how a "standardisation" turns into a redesign.
    """
    for peak in (220, 280, 320, 380):
        assert peak in CHART_HEIGHTS.values(), (
            f"{peak}px is one of the most common heights in the app but is not "
            "a tier, so adopting the scale there would move the chart"
        )


def test_tiers_are_distinct_and_ordered():
    values = list(CHART_HEIGHTS.values())
    assert len(set(values)) == len(values), f"duplicate tier heights: {values}"
    assert values == sorted(values), (
        f"tiers are not in ascending order, which makes the names misleading: {values}"
    )


def test_chart_height_falls_back_rather_than_raising():
    assert chart_height("lg") == CHART_HEIGHTS["lg"]
    assert chart_height("no-such-tier") == CHART_HEIGHTS["md"]


# ── the hover filler ─────────────────────────────────────────────────────────

def test_a_bare_figure_gets_a_unified_readable_hover():
    fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[1.23456, 2.5, 3.75]))
    apply_default_hover(fig)
    assert fig.layout.hovermode == "x unified"
    assert fig.data[0].hovertemplate == "%{y:,.2f}<extra></extra>", (
        "the default hover should print a comma-formatted value, not Plotly's "
        "raw float tuple"
    )


def test_a_hand_written_hover_is_never_overridden():
    """The filler runs inside shared helpers, so it must be additive."""
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2],
                               hovertemplate="Custom %{y}<extra></extra>"))
    apply_default_hover(fig)
    assert fig.data[0].hovertemplate == "Custom %{y}<extra></extra>"


def test_an_explicit_hoverinfo_is_respected():
    """`hoverinfo="skip"` is how a sparkline opts out; do not undo it."""
    fig = go.Figure(go.Scatter(x=[1, 2], y=[1, 2], hoverinfo="skip"))
    apply_default_hover(fig)
    assert not fig.data[0].hovertemplate


def test_value_format_is_configurable():
    fig = go.Figure(go.Scatter(x=[1], y=[1]))
    apply_default_hover(fig, value_format=".1%")
    assert fig.data[0].hovertemplate == "%{y:.1%}<extra></extra>"


def test_trace_families_without_a_hovertemplate_do_not_raise():
    """Indicator and Table have no hovertemplate; the filler must skip them."""
    fig = go.Figure(go.Indicator(mode="number", value=42))
    apply_default_hover(fig)          # must not raise
    assert fig.layout.hovermode == "x unified"


def test_none_and_non_figures_are_tolerated():
    assert apply_default_hover(None) is None
    sentinel = object()
    assert apply_default_hover(sentinel) is sentinel


# ── the page that consumes it ────────────────────────────────────────────────

def test_market_overview_macro_charts_route_through_the_filler():
    """All eleven go through one helper; the fix is only real if it is there."""
    source = (Path(__file__).resolve().parent.parent
              / "pages" / "5_Market_Overview.py").read_text(encoding="utf-8")
    helper = source[source.index("def _light_chart("):]
    helper = helper[: helper.index("\n    def ")]
    assert "apply_default_hover" in helper, (
        "_light_chart no longer applies the default hover, so this page's macro "
        "charts are back to Plotly's (x, y) tuple"
    )
