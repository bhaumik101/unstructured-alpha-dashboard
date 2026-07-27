"""Product-wide graph normalization and landing-theme regression guards."""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils.theme import (
    BEAR_RED,
    GREEN,
    GRID_COLOR,
    TEXT_SECONDARY,
    normalize_plotly_figure,
)


DASHBOARD = Path(__file__).resolve().parents[1]


def test_chart_normalizer_replaces_dark_only_chrome_and_neon_semantics():
    fig = go.Figure(
        go.Bar(
            x=["A", "B"],
            y=[3, 8],
            marker_color=["#00D566", "#FF4444"],
        )
    )
    fig.update_layout(
        height=287,
        paper_bgcolor="#0B0D12",
        plot_bgcolor="#0F1118",
        xaxis=dict(gridcolor="rgba(255,255,255,0.04)"),
        margin=dict(l=31, r=17, t=22, b=19),
    )

    normalize_plotly_figure(fig)

    assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert fig.layout.plot_bgcolor == "rgba(0,0,0,0)"
    assert fig.layout.xaxis.gridcolor == GRID_COLOR
    assert fig.layout.xaxis.tickfont.color == TEXT_SECONDARY
    assert fig.layout.height == 287
    assert fig.layout.margin.l == 31
    assert list(fig.data[0].y) == [3, 8]
    assert list(fig.data[0].marker.color) == [GREEN, BEAR_RED]


def test_chart_normalizer_covers_secondary_axes_polar_and_3d():
    secondary = make_subplots(specs=[[{"secondary_y": True}]])
    secondary.add_scatter(x=[1, 2], y=[3, 4], secondary_y=False)
    secondary.add_scatter(x=[1, 2], y=[8, 6], secondary_y=True)
    secondary.update_layout(
        xaxis2=dict(gridcolor="#ffffff"),
        yaxis2=dict(gridcolor="#ffffff"),
    )
    normalize_plotly_figure(secondary)
    assert secondary.layout.yaxis2.gridcolor == GRID_COLOR

    polar = go.Figure(
        go.Scatterpolar(r=[20, 60, 40], theta=["A", "B", "C"], fill="toself")
    )
    polar.update_layout(polar=dict(bgcolor="#0B0D12"))
    normalize_plotly_figure(polar)
    assert polar.layout.polar.bgcolor == "rgba(0,0,0,0)"
    assert polar.layout.polar.radialaxis.gridcolor == GRID_COLOR

    surface = go.Figure(go.Surface(z=[[1, 2], [3, 4]]))
    surface.update_layout(scene=dict(bgcolor="#0B0D12"))
    normalize_plotly_figure(surface)
    assert surface.layout.scene.bgcolor == "rgba(0,0,0,0)"
    assert surface.layout.scene.xaxis.gridcolor == GRID_COLOR


def test_every_active_plotly_page_loads_the_shared_chart_system():
    offenders = []
    for path in sorted((DASHBOARD / "pages").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "plotly_chart" in source and "utils.theme" not in source:
            offenders.append(path.name)
    assert not offenders, "Chart pages bypass shared chart system: " + ", ".join(offenders)


def test_landing_hero_uses_product_tokens_without_iframe_or_serif_counter():
    source = (DASHBOARD / "pages" / "home_page.py").read_text(encoding="utf-8")
    hero = source.split("# ── PRODUCT-ALIGNED LANDING HERO", 1)[1].split(
        "# ── LIVE SIGNAL PULSE", 1
    )[0]

    assert "components.v1" not in source
    assert "_components.html" not in source
    assert "var(--ua-bg-card)" in hero
    assert "var(--ua-hair)" in hero
    assert "var(--ua-ink)" in hero
    assert "grid-template-columns:repeat(4" in hero
    assert "@media(max-width:760px)" in hero
    assert "Fraunces" not in hero
    assert "Georgia" not in hero
