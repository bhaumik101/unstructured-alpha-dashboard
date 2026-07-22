"""Unstructured Alpha's restrained dark product and chart system."""
import math as _math

import plotly.graph_objects as _go
import plotly.io as _pio

# ── Palette ───────────────────────────────────────────────────────────────────

# Backgrounds
BG_PAGE         = "#0A0D12"   # near-black page background
BG_CARD         = "#11151C"   # card surface
BG_CARD_RAISED  = "#171C25"   # hover / elevated card
BG_PLOT         = "rgba(0,0,0,0)"  # charts inherit their containing surface
BG_SIDEBAR      = "#0D1016"   # sidebar

# Typography
TEXT_PRIMARY   = "#E7EAF0"   # soft near-white, not luminous
TEXT_SECONDARY = "#A7B0BF"   # readable neutral blue-gray
TEXT_MUTED     = "#9DA7B7"   # restrained secondary copy on dark surfaces
TEXT_CAPTION   = "#8D97A8"   # subtle but accessible caption

# Brand accents
GREEN       = "#35C98B"   # restrained positive accent
GREEN_DARK  = "#27966A"   # darker green variant
GREEN_DIM   = "#001A0D"   # dimmed green for backgrounds
PURPLE      = "#8187F7"   # analytic-series accent
PURPLE_DIM  = "#1A0A3D"   # dimmed purple
CYAN        = "#55A7D8"   # secondary accent
AMBER       = "#D6A34A"   # warning/watch amber

# Signal status
BULL_GREEN  = "#35C98B"   # bullish green
BEAR_RED    = "#E06C75"   # bearish red
BEAR_DIM    = "#4D0000"   # dimmed red
NEUTRAL     = "#6B7FBF"   # neutral blue-gray

# Chart grid & borders
GRID_COLOR   = "rgba(255,255,255,0.04)"
BORDER_LIGHT = "rgba(255,255,255,0.07)"
DIVIDER      = "rgba(255,255,255,0.05)"

# Data series — vibrant on dark
SERIES_COLORS = [
    "#55A7D8",   # blue
    "#8187F7",   # indigo
    "#35C98B",   # green
    "#D6A34A",   # amber
    "#E06C75",   # red
    "#7FB7BE",   # muted cyan
    "#B58BD2",   # muted violet
    "#A8B1C2",   # neutral
]

# Heatmap colorscale (bear → neutral → bull) — dark-friendly
HEATMAP_COLORSCALE = [
    [0.00, "#6E3038"],
    [0.25, "#B75B65"],
    [0.50, "#252B35"],
    [0.75, "#2E8F68"],
    [1.00, "#3FC68E"],
]


def _register_plotly_template() -> None:
    """Give every figure a sane baseline, including figures not styled locally."""
    axis = dict(
        showgrid=True,
        gridcolor=GRID_COLOR,
        gridwidth=1,
        zeroline=False,
        showline=False,
        ticks="",
        automargin=True,
        tickfont=dict(family="Inter, sans-serif", size=10, color=TEXT_SECONDARY),
        title=dict(font=dict(family="Inter, sans-serif", size=11, color=TEXT_MUTED), standoff=10),
    )
    _pio.templates["ua_financial"] = _go.layout.Template(
        layout=_go.Layout(
            colorway=SERIES_COLORS,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter, sans-serif", size=11, color=TEXT_SECONDARY),
            title=dict(font=dict(family="Inter, sans-serif", size=14, color=TEXT_PRIMARY), x=0.01),
            xaxis=axis,
            yaxis=axis,
            margin=dict(l=12, r=12, t=36, b=12),
            hoverlabel=dict(
                bgcolor=BG_CARD_RAISED,
                bordercolor="rgba(255,255,255,0.12)",
                font=dict(family="Inter, sans-serif", size=11, color=TEXT_PRIMARY),
            ),
            legend=dict(
                orientation="h", x=0, xanchor="left", y=1.02, yanchor="bottom",
                bgcolor="rgba(0,0,0,0)", borderwidth=0,
                font=dict(family="Inter, sans-serif", size=10, color=TEXT_SECONDARY),
            ),
            modebar=dict(bgcolor="rgba(0,0,0,0)", color=TEXT_MUTED, activecolor=TEXT_PRIMARY),
        )
    )
    _pio.templates.default = "ua_financial"


_register_plotly_template()

# ── Plotly chart config ───────────────────────────────────────────────────────
# Plotly must never hijack vertical page scrolling. Range selectors and drag
# zoom remain available on the few charts where exploration is valuable.
PLOTLY_CONFIG: dict = {
    "displayModeBar": False,
    "scrollZoom": False,
    "staticPlot": False,         # keep hover tooltips
    "responsive": True,
    "doubleClick": "reset",      # double-click resets zoom
}

# Interactive charts retain drag zoom and reset-on-double-click without a
# floating toolbar obscuring data.
PLOTLY_CONFIG_INTERACTIVE: dict = {
    "displayModeBar": False,
    "displaylogo": False,
    "scrollZoom": False,
    "responsive": True,
    "doubleClick": "reset",
}

# Time-series variant — adds range selector buttons (1M/3M/6M/1Y/All) via layout,
# no toolbar visible. Use with style_timeseries_chart().
PLOTLY_CONFIG_TIMESERIES: dict = {
    "displayModeBar": False,
    "scrollZoom": False,
    "responsive": True,
    "doubleClick": "reset",
}

# ── Chart Style Helper ────────────────────────────────────────────────────────

def style_chart(
    fig,
    height: int = 350,
    title: str = "",
    *,
    hovermode: str = "x unified",
    legend: bool | None = None,
) -> object:
    """
    Apply the Unstructured Alpha dark theme to any Plotly figure.

    Usage:
        fig = go.Figure(...)
        fig = style_chart(fig, height=400, title="Signal vs. Price")
        st.plotly_chart(fig, use_container_width=True)
    """
    _axis = dict(
        showgrid=True,
        gridcolor=GRID_COLOR,
        gridwidth=1,
        # Tick labels — readable on dark plot background (#0F1118)
        tickfont=dict(color=TEXT_SECONDARY, size=10, family="Inter, sans-serif"),
        title_font=dict(color=TEXT_MUTED, size=11, family="Inter, sans-serif"),
        linecolor="rgba(255,255,255,0.07)",
        zeroline=False,
        # Axis line itself
        showline=False,
    )
    layout_updates = dict(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=BG_PLOT,
        font=dict(family="Inter, -apple-system, sans-serif", color=TEXT_SECONDARY),
        hovermode=hovermode,
        hoverlabel=dict(
            bgcolor=BG_CARD_RAISED,
            bordercolor=BORDER_LIGHT,
            font=dict(family="Inter, sans-serif", size=12, color=TEXT_PRIMARY),
            namelength=-1,
        ),
        legend=dict(
            orientation="h",
            x=0,
            xanchor="left",
            y=1.02,
            yanchor="bottom",
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            font=dict(size=11, color=TEXT_SECONDARY, family="Inter, sans-serif"),
        ),
        margin=dict(l=12, r=12, t=46 if title else 24, b=12),
        hoverdistance=48,
        uirevision="ua-chart-v2",
        xaxis=dict(
            **_axis,
            showspikes=True,
            spikecolor="rgba(255,255,255,0.15)",
            spikethickness=1,
            spikedash="dot",
        ),
        yaxis=_axis,
    )
    if title:
        layout_updates["title"] = dict(
            text=title,
            font=dict(family="Inter, -apple-system, sans-serif", size=14, color=TEXT_PRIMARY),
            x=0.01,
            xanchor="left",
        )
    if legend is not None:
        layout_updates["showlegend"] = legend
    fig.update_layout(**layout_updates)
    return fig


def style_sparkline(fig, height: int = 54, *, y_range=None) -> object:
    """A quiet, non-interactive trend line for dense cards and watchlists."""
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=2, b=2),
        showlegend=False,
        hovermode=False,
        xaxis=dict(visible=False, fixedrange=True),
        yaxis=dict(visible=False, fixedrange=True, range=y_range),
        uirevision="ua-spark-v2",
    )
    return fig


def style_distribution_chart(fig, height: int = 360, title: str = "") -> object:
    """Style box, violin, histogram, and scatter distributions without unified hover."""
    return style_chart(fig, height=height, title=title, hovermode="closest")


def style_chart_secondary(fig, height: int = 380,
                           y1_title: str = "Signal",
                           y2_title: str = "Price",
                           y1_color: str = GREEN,
                           y2_color: str = PURPLE) -> object:
    """Style a dual-axis chart (make_subplots secondary_y=True)."""
    _tick = dict(color=TEXT_SECONDARY, size=10, family="Inter, sans-serif")
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=BG_PLOT,
        font=dict(family="Inter, -apple-system, sans-serif", color=TEXT_SECONDARY),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=BG_CARD_RAISED,
            bordercolor=BORDER_LIGHT,
            font=dict(family="Inter, sans-serif", size=12, color=TEXT_PRIMARY),
            namelength=-1,
        ),
        legend=dict(
            orientation="h", x=0, xanchor="left", y=1.02, yanchor="bottom",
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            font=dict(size=11, color=TEXT_SECONDARY, family="Inter, sans-serif"),
        ),
        margin=dict(l=12, r=12, t=42, b=12),
        uirevision="ua-secondary-v2",
        xaxis=dict(
            showgrid=True,
            gridcolor=GRID_COLOR,
            tickfont=_tick,
            title_font=dict(color=TEXT_MUTED, size=11, family="Inter, sans-serif"),
            linecolor="rgba(255,255,255,0.08)",
            showline=True,
        ),
    )
    fig.update_yaxes(
        title_text=y1_title, secondary_y=False,
        gridcolor=GRID_COLOR,
        tickfont=_tick,
        title_font=dict(color=y1_color, family="Inter, sans-serif", size=11),
        linecolor="rgba(255,255,255,0.08)",
        showline=True,
    )
    fig.update_yaxes(
        title_text=y2_title, secondary_y=True,
        gridcolor="rgba(0,0,0,0)",
        tickfont=_tick,
        title_font=dict(color=y2_color, family="Inter, sans-serif", size=11),
        linecolor="rgba(255,255,255,0.08)",
        showline=True,
    )
    return fig


# ── HTML Card Templates ───────────────────────────────────────────────────────

def signal_card_html(
    icon: str,
    cat_name: str,
    pcs: int,
    name: str,
    status: str,
    score: float,
    dev: float,
    trend: float,
    lag_weeks: int,
) -> str:
    """Return an HTML card for a signal status widget — modern dark glassmorphism design."""
    STATUS_MAP = {
        "bullish":           ("#00D566", "BULLISH",  "▲", "rgba(0,213,102,0.07)",  "rgba(0,213,102,0.25)"),
        "bearish":           ("#FF4444", "BEARISH",  "▼", "rgba(255,68,68,0.07)",  "rgba(255,68,68,0.25)"),
        "neutral":           ("#6B7FBF", "NEUTRAL",  "●", "rgba(107,127,191,0.05)", "rgba(107,127,191,0.20)"),
        "insufficient_data": ("#8892AA", "NO DATA",  "○", "rgba(18,21,30,0.4)",    "rgba(255,255,255,0.08)"),
    }
    color, label, arrow, bg_tint, border_color = STATUS_MAP.get(
        status, STATUS_MAP["neutral"]
    )

    trend_arrow = "↑" if trend > 1 else ("↓" if trend < -1 else "→")
    trend_color = "#00D566" if trend > 1 else ("#FF4444" if trend < -1 else "#6B7FBF")

    # Score bar fill %
    bar_pct = min(max(score, 0), 100)

    return f"""
<div style="
    background: {bg_tint};
    border:1px solid {border_color};
    border-radius:12px;
    padding:14px 16px;
    margin-bottom:10px;
    font-family:'Inter',-apple-system,sans-serif;
    backdrop-filter:blur(8px);
    transition:all 0.2s cubic-bezier(0.4,0,0.2,1);
    position:relative;
    overflow:hidden;
">
    <div style="position:absolute;left:0;top:0;bottom:0;width:3px;background:{color};border-radius:12px 0 0 12px;"></div>
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">
        <div style="font-size:0.60rem;color:#8892AA;letter-spacing:0.10em;text-transform:uppercase;font-weight:700;">
            {icon} {cat_name} &nbsp;·&nbsp; PCS {pcs}/10
        </div>
        <div style="
            font-size:0.60rem;font-weight:700;letter-spacing:0.08em;
            color:{color};background:{'rgba(0,213,102,0.1)' if status=='bullish' else ('rgba(255,68,68,0.1)' if status=='bearish' else 'rgba(107,127,191,0.1)')};
            padding:2px 7px;border-radius:4px;
        ">{arrow} {label}</div>
    </div>
    <div style="font-weight:600;font-size:0.88rem;color:#E8EEFF;margin-bottom:10px;line-height:1.35;letter-spacing:-0.1px;">
        {name[:52]}
    </div>
    <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:12px;">
        <div>
            <div style="font-size:2.2rem;font-weight:800;color:{color};letter-spacing:-1.5px;line-height:1.0;">
                {score:.0f}
            </div>
            <div style="font-size:0.60rem;color:#8892AA;margin-top:1px;">/100</div>
        </div>
        <div style="flex:1;padding-bottom:6px;">
            <div style="height:3px;background:rgba(255,255,255,0.05);border-radius:2px;overflow:hidden;margin-bottom:8px;">
                <div style="height:100%;width:{bar_pct}%;background:{color};border-radius:2px;transition:width 0.5s ease;"></div>
            </div>
            <div style="font-size:0.72rem;color:#8892AA;line-height:1.7;">
                <div><span style="color:#8892AA;">Dev</span> &nbsp;<b style="color:#B8C0D4;">{dev:+.1f}%</b> vs 52w avg</div>
                <div><span style="color:#8892AA;">Trend</span> &nbsp;<b style="color:{trend_color};">{trend_arrow} {trend:+.1f}%</b></div>
                <div><span style="color:#8892AA;">Lead</span> &nbsp;<b style="color:#B8C0D4;">~{lag_weeks}w</b></div>
            </div>
        </div>
    </div>
</div>
"""


# ── SVG Radial Gauge ─────────────────────────────────────────────────────────

def confluence_gauge_svg(score: float, case: str = "") -> str:
    """
    Animated semicircular SVG gauge for Confluence Score (0–100).
    Zones: red 0-35 / gray 35-65 / green 65-100.
    Returns HTML string for st.markdown(..., unsafe_allow_html=True).
    """
    CX, CY, R_OUT, R_IN = 100, 80, 62, 45

    score = max(0.0, min(100.0, float(score)))
    sc = ("#00D566" if (score >= 65 or case == "BULL")
          else "#FF4444" if (score <= 35 or case == "BEAR")
          else "#6B7FBF")
    cs = case or ("BULL" if score >= 65 else ("BEAR" if score <= 35 else "NEUTRAL"))

    def _pt(a_deg, r):
        rad = _math.radians(a_deg)
        return CX + r * _math.cos(rad), CY - r * _math.sin(rad)

    def _arc(a1, a2, ro, ri, col, op=1.0):
        x1o, y1o = _pt(a1, ro); x2o, y2o = _pt(a2, ro)
        x1i, y1i = _pt(a1, ri); x2i, y2i = _pt(a2, ri)
        lg = 1 if abs(a1 - a2) > 180 else 0
        d = (f"M{x1o:.2f},{y1o:.2f} A{ro},{ro} 0 {lg},0 {x2o:.2f},{y2o:.2f} "
             f"L{x2i:.2f},{y2i:.2f} A{ri},{ri} 0 {lg},1 {x1i:.2f},{y1i:.2f}Z")
        return f'<path d="{d}" fill="{col}" opacity="{op}"/>'

    needle_ang = 180.0 - score * 1.8

    # Background zone rings
    bg = (_arc(180, 117, R_OUT, R_IN, "#FF4444", 0.22)
        + _arc(117, 63,  R_OUT, R_IN, "#8892AA", 0.14)
        + _arc(63,  0,   R_OUT, R_IN, "#00D566", 0.22))

    # Active fill up to needle
    fill = _arc(180, needle_ang, R_OUT, R_IN, sc, 0.88) if score > 0.5 else ""

    # Zone separator ticks
    def _tick(a):
        x1, y1 = _pt(a, R_IN - 1); x2, y2 = _pt(a, R_OUT + 1)
        return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="#0B0D12" stroke-width="2.5"/>')
    ticks = _tick(117) + _tick(63)

    # Animated needle: sweeps from left (score=0) to final position
    nx1, ny1 = _pt(needle_ang, R_IN + 2)
    nx2, ny2 = _pt(needle_ang, R_OUT - 1)
    rotation_start = score * 1.8
    needle = (
        f'<line x1="{nx1:.1f}" y1="{ny1:.1f}" x2="{nx2:.1f}" y2="{ny2:.1f}" '
        f'stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round">'
        f'<animateTransform attributeName="transform" type="rotate" '
        f'from="{rotation_start:.1f},{CX},{CY}" to="0,{CX},{CY}" '
        f'dur="1.0s" fill="freeze" calcMode="spline" '
        f'keyTimes="0;1" keySplines="0.25,0.46,0.45,0.94"/>'
        f'</line>'
    )

    # Center cap
    cap = (f'<circle cx="{CX}" cy="{CY}" r="6" fill="#0B0D12"/>'
           f'<circle cx="{CX}" cy="{CY}" r="3.5" fill="#E8EEFF"/>')

    # Score readout, placed BELOW the pivot rather than inside the arc.
    #
    # Vertical budget along the centre line (x=CX), top to bottom:
    #   y  -2       CONFLUENCE header  (in the viewBox's top padding)
    #   y  12       "50" axis label
    #   y  18..80   the dial itself (outer radius 62 from CY=80)
    #   y  74..86   needle pivot cap (r=6)
    #   y  87.5..113.5  score digits (font 26, baseline CY+27)
    #   y  115..123 case label       (font 8, baseline CY+41)
    #
    # The cap and the digits previously both claimed y 79..86: the white cap sat
    # on top of the number, and at scores near 0 or 100 the needle lies almost
    # horizontal through the pivot and cut straight across the digits. Anything
    # centred on CX must clear the cap's bottom edge (CY + 6), so the readout
    # moved below the pivot entirely, with ~1.5px of air on either side of it.
    # tests/test_gauge_geometry.py reconstructs these boxes and asserts they are
    # disjoint — adjust the constants there together with these.
    _SCORE_FS = 26
    score_txt = (f'<text x="{CX}" y="{CY + 27}" text-anchor="middle" '
                 f'font-family="Inter,sans-serif" font-size="{_SCORE_FS}" font-weight="900" '
                 f'fill="{sc}">{score:.0f}</text>')
    case_lbl  = (f'<text x="{CX}" y="{CY + 41}" text-anchor="middle" '
                 f'font-family="Inter,sans-serif" font-size="8" font-weight="700" '
                 f'letter-spacing="2" fill="{sc}">{cs}</text>')

    # Axis labels
    def _lbl(a, text):
        lx, ly = _pt(a, R_OUT + 10)
        return (f'<text x="{lx:.0f}" y="{ly + 4:.0f}" text-anchor="middle" '
                f'font-family="Inter,sans-serif" font-size="8" fill="#6B7FBF">{text}</text>')
    labels = _lbl(180, "0") + _lbl(90, "50") + _lbl(0, "100")

    # Sits in the viewBox's negative-y top padding. At y=10 it collided with the
    # "50" axis label, which _lbl places at the same x with a baseline of y=12.
    header = (f'<text x="{CX}" y="-2" text-anchor="middle" '
              f'font-family="Inter,sans-serif" font-size="7" font-weight="700" '
              f'letter-spacing="2.5" fill="#6B7FBF">CONFLUENCE</text>')

    return (
        '<div style="display:flex;justify-content:center;align-items:center;'
        'padding:4px 0;animation:fadeIn 0.5s ease-out;">'
        # viewBox starts at y=-12 to give the CONFLUENCE header its own band above
        # the dial, and runs 132 tall so the relocated score/case readout below the
        # pivot (baselines CY+27 and CY+41, i.e. y=107 and y=121) is not clipped.
        '<svg width="196" height="136" viewBox="0 -12 196 136" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'{bg}{fill}{ticks}{needle}{cap}{header}{score_txt}{case_lbl}{labels}'
        '</svg></div>\n'
        '<style>@keyframes fadeIn{from{opacity:0;transform:scale(0.95)}'
        'to{opacity:1;transform:scale(1)}}</style>'
    )


# ── Gradient Area Chart Helper ────────────────────────────────────────────────

def style_area_chart(fig, line_color: str = GREEN, fill_opacity: float = 0.12,
                     height: int = 350, title: str = "") -> object:
    """
    Apply dark theme to a Plotly figure AND add semi-transparent gradient area
    fill under the first trace. Call after building your go.Scatter traces.

    The fill uses tozeroy with a matching rgba color so the area recedes from
    the line — giving a Robinhood / Bloomberg Terminal look.

    Usage:
        fig = go.Figure([go.Scatter(x=dates, y=values, name="Price",
                                    line=dict(color="#00D566", width=2))])
        fig = style_area_chart(fig, line_color="#00D566")
        st.plotly_chart(fig, use_container_width=True)
    """
    import re
    # Parse hex color to rgba fill
    hex_c = line_color.lstrip("#")
    if len(hex_c) == 6:
        r_, g_, b_ = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
        fill_color = f"rgba({r_},{g_},{b_},{fill_opacity})"
    else:
        fill_color = f"rgba(0,213,102,{fill_opacity})"

    # Inject fill on the first trace
    if fig.data:
        fig.data[0].update(
            fill="tozeroy",
            fillcolor=fill_color,
            line=dict(color=line_color, width=2),
        )

    return style_chart(fig, height=height, title=title)


# ── Time-Series Chart Helper ──────────────────────────────────────────────────

def style_timeseries_chart(
    fig,
    height: int = 380,
    title: str = "",
    range_buttons: bool = True,
    rangeslider: bool = False,
    y_title: str = "",
) -> object:
    """
    Apply the UA dark theme to a time-series Plotly figure and add
    clickable range-selector buttons (1M · 3M · 6M · 1Y · All).

    Use with PLOTLY_CONFIG_TIMESERIES so the toolbar stays hidden while
    range buttons + scroll-zoom give full interactivity.

    Usage::

        fig = go.Figure([go.Scatter(x=dates, y=values, ...)])
        fig = style_timeseries_chart(fig, title="Signal History", height=380)
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG_TIMESERIES)
    """
    fig = style_chart(fig, height=height, title=title)

    _btn_style = dict(
        bgcolor="rgba(255,255,255,0.05)",
        activecolor="rgba(0,213,102,0.20)",
        bordercolor="rgba(255,255,255,0.12)",
        borderwidth=1,
        font=dict(color=TEXT_SECONDARY, size=10, family="Inter, sans-serif"),
    )

    xaxis_updates: dict = {
        "type": "date",
        "tickformat": "%b '%y",
        "nticks": 8,
        "showspikes": True,
        "spikecolor": "rgba(255,255,255,0.15)",
        "spikethickness": 1,
        "spikedash": "dot",
        "rangeslider": dict(visible=rangeslider, thickness=0.04,
                            bgcolor=BG_CARD, bordercolor=BORDER_LIGHT),
    }

    if range_buttons:
        xaxis_updates["rangeselector"] = dict(
            buttons=[
                dict(count=1,  label="1M",  step="month", stepmode="backward"),
                dict(count=3,  label="3M",  step="month", stepmode="backward"),
                dict(count=6,  label="6M",  step="month", stepmode="backward"),
                dict(count=1,  label="1Y",  step="year",  stepmode="backward"),
                dict(step="all", label="All"),
            ],
            **_btn_style,
            x=0, xanchor="left", y=1.02, yanchor="bottom",
        )

    yaxis_updates: dict = {}
    if y_title:
        yaxis_updates["title_text"] = y_title

    fig.update_layout(xaxis=xaxis_updates)
    if yaxis_updates:
        fig.update_layout(yaxis=yaxis_updates)

    return fig


# ── Disclaimer Helper ─────────────────────────────────────────────────────────

def render_disclaimer(compact: bool = False) -> str:
    """
    Return an HTML financial disclaimer block.
    Use with st.markdown(..., unsafe_allow_html=True).

    Args:
        compact: If True, returns a single-line inline disclaimer.
                 If False (default), returns the full block version.
    """
    if compact:
        return (
            '<div style="font-size:0.68rem;color:#6B7FBF;margin-top:10px;'
            'font-family:Inter,sans-serif;line-height:1.5;">'
            '&#9888; <b>Not investment advice.</b> Signal scores are generated from '
            'public data using algorithmic models. Past performance does not '
            'guarantee future results. Always do your own research.'
            '</div>'
        )
    return (
        '<div style="background:rgba(245,158,11,0.06);'
        'border:1px solid rgba(245,158,11,0.20);border-radius:8px;'
        'padding:10px 14px;margin-top:20px;font-family:Inter,sans-serif;">'
        '<div style="font-size:0.72rem;font-weight:700;color:#F59E0B;'
        'letter-spacing:0.05em;margin-bottom:4px;">&#9888; DISCLAIMER</div>'
        '<div style="font-size:0.73rem;color:#8892AA;line-height:1.6;">'
        'Unstructured Alpha signal scores are generated algorithmically from '
        'publicly available macro, insider, and alternative data. They are '
        '<b style="color:#B8C0D4;">not investment advice</b> and do not '
        'constitute a recommendation to buy or sell any security. Past signal '
        'accuracy does not guarantee future performance. Always conduct your '
        'own due diligence before making any investment decisions. Unstructured '
        'Alpha is not a registered investment advisor.'
        '</div></div>'
    )


# ── Skeleton / Shimmer Loading System ────────────────────────────────────────
# Usage pattern (in any page):
#
#   from utils.theme import inject_skeleton_css, skeleton_cards, skeleton_chart_block
#
#   inject_skeleton_css()       # once per page, injects global CSS
#
#   # Show skeleton while data loads
#   ph = st.empty()
#   ph.markdown(skeleton_cards(n=3, height=110), unsafe_allow_html=True)
#   data = expensive_load()
#   ph.empty()                  # replace with real content
#
# All skeleton elements use the `.ua-sk` class so they won't conflict with
# any Streamlit or external CSS already on the page.

_SKELETON_CSS = """
<style>
/* ── Shimmer / Skeleton ──────────────────────────────────────────────────── */
@keyframes ua_shimmer {
  0%   { background-position: -1200px 0; }
  100% { background-position:  1200px 0; }
}
.ua-sk {
  background: linear-gradient(
    90deg,
    rgba(26,30,44,0.9)   0%,
    rgba(42,48,72,0.95)  35%,
    rgba(55,62,90,0.90)  50%,
    rgba(42,48,72,0.95)  65%,
    rgba(26,30,44,0.9)  100%
  );
  background-size: 1200px 100%;
  animation: ua_shimmer 1.8s infinite linear;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.05);
}
.ua-sk-line {
  background: linear-gradient(
    90deg,
    rgba(26,30,44,0.9)  0%,
    rgba(42,48,72,0.95) 40%,
    rgba(26,30,44,0.9) 100%
  );
  background-size: 1200px 100%;
  animation: ua_shimmer 1.8s infinite linear;
  border-radius: 4px;
  height: 11px;
  margin-bottom: 8px;
}
.ua-sk-wrap {
  background: rgba(18,21,30,0.8);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 10px;
}

/* ── Fade-in animation ───────────────────────────────────────────────────── */
@keyframes ua_fadein {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0);   }
}
.ua-fade-in {
  animation: ua_fadein 0.28s ease forwards;
}

/* ── Card components ─────────────────────────────────────────────────────── */
.ua-card {
  background: #12151E;
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 12px;
  padding: 16px 20px;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
  font-family: Inter, -apple-system, sans-serif;
}
.ua-card:hover {
  border-color: rgba(124,58,237,0.35);
  box-shadow: 0 0 0 1px rgba(124,58,237,0.15), 0 4px 16px rgba(0,0,0,0.35);
}
.ua-card-green:hover {
  border-color: rgba(0,213,102,0.35);
  box-shadow: 0 0 0 1px rgba(0,213,102,0.12), 0 4px 16px rgba(0,0,0,0.35);
}
.ua-card-red:hover {
  border-color: rgba(255,68,68,0.35);
  box-shadow: 0 0 0 1px rgba(255,68,68,0.12), 0 4px 16px rgba(0,0,0,0.35);
}

/* ── Empty state ─────────────────────────────────────────────────────────── */
.ua-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  border: 1px dashed rgba(255,255,255,0.12);
  border-radius: 12px;
  padding: 28px 20px;
  text-align: center;
  color: #8892AA;
  font-size: 0.85rem;
  font-family: Inter, -apple-system, sans-serif;
  line-height: 1.6;
}
.ua-empty-icon {
  font-size: 1.6rem;
  margin-bottom: 10px;
  opacity: 0.6;
}
.ua-empty-title {
  font-size: 0.92rem;
  font-weight: 600;
  color: #B8C0D4;
  margin-bottom: 4px;
}

/* ── Metric / stat tile ──────────────────────────────────────────────────── */
.ua-metric {
  background: #12151E;
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 8px;
  padding: 12px 16px;
  font-family: Inter, -apple-system, sans-serif;
  transition: border-color 0.15s ease;
}
.ua-metric-label {
  font-size: 0.62rem;
  font-weight: 700;
  color: #8892AA;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 4px;
}
.ua-metric-value {
  font-size: 1.45rem;
  font-weight: 700;
  color: #E8EEFF;
  line-height: 1.15;
}

/* ── Status tags ─────────────────────────────────────────────────────────── */
.ua-tag {
  display: inline-block;
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 20px;
  font-family: Inter, -apple-system, sans-serif;
}
.ua-tag-bull {
  background: rgba(0,213,102,0.12);
  color: #00D566;
  border: 1px solid rgba(0,213,102,0.25);
}
.ua-tag-bear {
  background: rgba(255,68,68,0.12);
  color: #FF4444;
  border: 1px solid rgba(255,68,68,0.25);
}
.ua-tag-neutral {
  background: rgba(107,127,191,0.12);
  color: #6B7FBF;
  border: 1px solid rgba(107,127,191,0.25);
}
.ua-tag-pro {
  background: rgba(124,58,237,0.15);
  color: #A78BFA;
  border: 1px solid rgba(124,58,237,0.3);
}

/* ── Section divider ─────────────────────────────────────────────────────── */
.ua-divider {
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255,255,255,0.07) 20%,
    rgba(255,255,255,0.07) 80%,
    transparent 100%
  );
  margin: 18px 0;
}

/* ── Streamlit element polish ────────────────────────────────────────────── */
/* Smoother button transitions */
.stButton > button {
  transition: background-color 0.15s ease, border-color 0.15s ease,
              box-shadow 0.15s ease, opacity 0.15s ease !important;
}
/* Download button same treatment */
.stDownloadButton > button {
  transition: background-color 0.15s ease, border-color 0.15s ease,
              box-shadow 0.15s ease !important;
}
/* Metric delta coloring */
[data-testid="stMetricDelta"] svg { display: none; }
/* Expander header hover */
.streamlit-expanderHeader {
  transition: color 0.15s ease !important;
}
/* Tab underline transition */
.stTabs [data-baseweb="tab"] {
  transition: color 0.15s ease !important;
}
/* Dataframe hover row highlight */
.dvn-scroller:hover td { cursor: default; }

/* ── Page content fade-in on navigation ──────────────────────────────────── */
@keyframes ua_page_in {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0);   }
}
.main .block-container,
[data-testid="stMainBlockContainer"] {
  animation: ua_page_in 0.22s ease forwards;
}

/* ── Scrollbar styling ───────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: rgba(11,13,18,0.6); }
::-webkit-scrollbar-thumb {
  background: rgba(104,113,155,0.35);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(124,58,237,0.5); }

/* ── Input / selectbox focus rings ───────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
  transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
  border-color: rgba(124,58,237,0.6) !important;
  box-shadow: 0 0 0 2px rgba(124,58,237,0.15) !important;
  outline: none !important;
}

/* ── Selectbox hover / focus ─────────────────────────────────────────────── */
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
  transition: border-color 0.15s ease !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div:hover {
  border-color: rgba(124,58,237,0.5) !important;
}

/* ── Alert / info / success / warning boxes ──────────────────────────────── */
[data-testid="stAlert"] {
  border-radius: 10px !important;
  border-width: 1px !important;
  font-family: Inter, -apple-system, sans-serif !important;
}
[data-testid="stAlert"][data-baseweb="notification"] {
  background: rgba(18,21,30,0.9) !important;
}
/* Info */
[data-testid="stAlert"].st-ae { border-color: rgba(0,200,224,0.3) !important; }
/* Success */
[data-testid="stAlert"].st-af { border-color: rgba(0,213,102,0.3) !important; }
/* Warning */
[data-testid="stAlert"].st-ag { border-color: rgba(245,158,11,0.3) !important; }
/* Error */
[data-testid="stAlert"].st-ah { border-color: rgba(255,68,68,0.3) !important; }

/* ── Sidebar nav item hover ──────────────────────────────────────────────── */
[data-testid="stSidebarNav"] a {
  transition: background-color 0.15s ease, color 0.15s ease,
              padding-left 0.15s ease !important;
  border-radius: 6px !important;
}
[data-testid="stSidebarNav"] a:hover {
  background-color: rgba(124,58,237,0.10) !important;
  padding-left: 14px !important;
}
[data-testid="stSidebarNav"] a[aria-selected="true"] {
  background-color: rgba(124,58,237,0.15) !important;
  border-left: 2px solid #7C3AED !important;
}

/* ── Plotly chart container lift on hover ────────────────────────────────── */
[data-testid="stPlotlyChart"] {
  transition: box-shadow 0.2s ease !important;
  border-radius: 10px;
}
[data-testid="stPlotlyChart"]:hover {
  box-shadow: 0 4px 20px rgba(0,0,0,0.4) !important;
}

/* ── Spinner polish ──────────────────────────────────────────────────────── */
[data-testid="stSpinner"] > div {
  border-top-color: #7C3AED !important;
}

/* ── Divider ─────────────────────────────────────────────────────────────── */
hr {
  border-color: rgba(255,255,255,0.06) !important;
  margin: 16px 0 !important;
}

/* ── Expander border ─────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
  border-color: rgba(255,255,255,0.07) !important;
  border-radius: 10px !important;
  transition: border-color 0.15s ease !important;
}
[data-testid="stExpander"]:hover {
  border-color: rgba(124,58,237,0.25) !important;
}
</style>
"""


# ── Modern UI System — Buttons, Tabs, Inputs, Metrics, Sidebar ───────────────
# Drop-in replacement for every cheap-looking default Streamlit widget.
# Inject via inject_all_css() (or inject_skeleton_css / inject_premium_css).

_MODERN_UI_CSS = """
<style>
/* ══════════════════════════════════════════════════════════════════════════
   PILL TABS  — replaces underline tabs with rounded pill containers
   ══════════════════════════════════════════════════════════════════════════ */

.stTabs [data-baseweb="tab-list"] {
  background: rgba(13,15,24,0.92) !important;
  border: 1px solid rgba(255,255,255,0.07) !important;
  border-radius: 10px !important;
  padding: 3px !important;
  gap: 2px !important;
  flex-wrap: wrap !important;
}

.stTabs [data-baseweb="tab"] {
  background: transparent !important;
  border-radius: 7px !important;
  padding: 7px 14px !important;
  font-family: Inter, -apple-system, sans-serif !important;
  font-size: 0.82rem !important;
  font-weight: 600 !important;
  color: #6B7FBF !important;
  border: 1px solid transparent !important;
  margin: 0 !important;
  min-height: auto !important;
  line-height: 1.4 !important;
  white-space: nowrap !important;
  position: relative !important;
  overflow: hidden !important;
  transition: all 0.16s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.stTabs [data-baseweb="tab"]:hover {
  color: #C8D0E4 !important;
  background: rgba(255,255,255,0.05) !important;
}

/* Active pill — green-tinted glass */
.stTabs [aria-selected="true"][data-baseweb="tab"],
.stTabs [data-baseweb="tab"][aria-selected="true"] {
  background: linear-gradient(135deg,rgba(0,213,102,0.14) 0%,rgba(0,200,224,0.07) 100%) !important;
  color: #E8EEFF !important;
  font-weight: 700 !important;
  border: 1px solid rgba(0,213,102,0.22) !important;
  box-shadow: 0 1px 6px rgba(0,0,0,0.40), inset 0 1px 0 rgba(255,255,255,0.06) !important;
}

/* Kill underline highlight + divider */
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {
  display: none !important;
  height: 0 !important;
  background: none !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   MODERN BUTTONS  — base / secondary / primary / download / form-submit
   ══════════════════════════════════════════════════════════════════════════ */

@keyframes ua_btn_ripple {
  0%   { transform: translate(-50%,-50%) scale(0); opacity: 0.30; }
  100% { transform: translate(-50%,-50%) scale(5); opacity: 0; }
}

.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button,
.stLinkButton > a {
  font-family: Inter, -apple-system, sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.83rem !important;
  letter-spacing: 0.01em !important;
  padding: 8px 20px !important;
  border-radius: 8px !important;
  min-height: 36px !important;
  cursor: pointer !important;
  position: relative !important;
  overflow: hidden !important;
  transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

/* CSS-only ripple on click */
.stButton > button::after,
.stDownloadButton > button::after {
  content: '' !important;
  position: absolute !important;
  top: 50% !important; left: 50% !important;
  width: 120px !important; height: 120px !important;
  background: rgba(255,255,255,0.14) !important;
  border-radius: 50% !important;
  pointer-events: none !important;
  opacity: 0 !important;
  transform: translate(-50%,-50%) scale(0) !important;
}
.stButton > button:active::after,
.stDownloadButton > button:active::after {
  animation: ua_btn_ripple 0.42s ease-out forwards !important;
}

/* — Secondary (default) — */
.stButton > button[data-testid="baseButton-secondary"],
.stButton > button:not([data-testid="baseButton-primary"]) {
  background: rgba(22,26,40,0.92) !important;
  border: 1px solid rgba(255,255,255,0.10) !important;
  color: #B8C0D4 !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.30),
              inset 0 1px 0 rgba(255,255,255,0.04) !important;
}
.stButton > button[data-testid="baseButton-secondary"]:hover,
.stButton > button:not([data-testid="baseButton-primary"]):hover {
  background: rgba(32,38,58,0.95) !important;
  border-color: rgba(0,213,102,0.38) !important;
  color: #E8EEFF !important;
  transform: translateY(-1px) !important;
  box-shadow: 0 4px 14px rgba(0,0,0,0.35),
              0 0 0 1px rgba(0,213,102,0.10) !important;
}
.stButton > button[data-testid="baseButton-secondary"]:active,
.stButton > button:not([data-testid="baseButton-primary"]):active {
  transform: translateY(0) scale(0.975) !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.30) !important;
}

/* — Primary — */
.stButton > button[data-testid="baseButton-primary"] {
  background: linear-gradient(135deg, #00D566 0%, #00A847 100%) !important;
  border: 1px solid rgba(0,213,102,0.38) !important;
  color: #001A0B !important;
  font-weight: 700 !important;
  box-shadow: 0 4px 16px rgba(0,213,102,0.30) !important;
}
.stButton > button[data-testid="baseButton-primary"]:hover {
  filter: brightness(1.08) !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 6px 24px rgba(0,213,102,0.42) !important;
}
.stButton > button[data-testid="baseButton-primary"]:active {
  transform: translateY(0) scale(0.975) !important;
  filter: brightness(0.96) !important;
  box-shadow: 0 2px 8px rgba(0,213,102,0.20) !important;
}

/* — Download — */
.stDownloadButton > button {
  background: rgba(0,200,224,0.09) !important;
  border: 1px solid rgba(0,200,224,0.22) !important;
  color: #00C8E0 !important;
}
.stDownloadButton > button:hover {
  background: rgba(0,200,224,0.16) !important;
  border-color: rgba(0,200,224,0.42) !important;
  transform: translateY(-1px) !important;
  box-shadow: 0 4px 14px rgba(0,200,224,0.20) !important;
}

/* — Form submit — */
.stFormSubmitButton > button {
  background: linear-gradient(135deg, #7C3AED 0%, #5B21B6 100%) !important;
  border: 1px solid rgba(124,58,237,0.38) !important;
  color: #fff !important;
  font-weight: 700 !important;
  box-shadow: 0 4px 16px rgba(124,58,237,0.28) !important;
}
.stFormSubmitButton > button:hover {
  filter: brightness(1.10) !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 6px 24px rgba(124,58,237,0.38) !important;
}

/* Sidebar buttons stay green-themed */
section[data-testid="stSidebar"] .stButton > button {
  background: rgba(0,213,102,0.09) !important;
  border: 1px solid rgba(0,213,102,0.22) !important;
  color: #00D566 !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  background: rgba(0,213,102,0.16) !important;
  border-color: rgba(0,213,102,0.42) !important;
  transform: translateY(-1px) !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   SELECTBOX + MULTI-SELECT
   ══════════════════════════════════════════════════════════════════════════ */

[data-testid="stSelectbox"] [data-baseweb="select"] > div:first-child,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div:first-child {
  background: rgba(15,17,24,0.92) !important;
  border: 1px solid rgba(255,255,255,0.10) !important;
  border-radius: 8px !important;
  transition: border-color 0.16s ease, box-shadow 0.16s ease !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div:first-child:hover,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div:first-child:hover {
  border-color: rgba(0,213,102,0.38) !important;
  box-shadow: 0 0 0 1px rgba(0,213,102,0.10) !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div:first-child:focus-within,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div:first-child:focus-within {
  border-color: rgba(0,213,102,0.55) !important;
  box-shadow: 0 0 0 2px rgba(0,213,102,0.14) !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   TEXT INPUTS / TEXTAREA / NUMBER INPUT
   ══════════════════════════════════════════════════════════════════════════ */

[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
  background: rgba(15,17,24,0.92) !important;
  border: 1px solid rgba(255,255,255,0.10) !important;
  border-radius: 8px !important;
  color: #E8EEFF !important;
  font-family: Inter, -apple-system, sans-serif !important;
  font-size: 0.85rem !important;
  transition: border-color 0.16s ease, box-shadow 0.16s ease !important;
}
[data-testid="stTextInput"] input:hover,
[data-testid="stNumberInput"] input:hover,
[data-testid="stTextArea"] textarea:hover {
  border-color: rgba(255,255,255,0.18) !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
  border-color: rgba(0,213,102,0.55) !important;
  box-shadow: 0 0 0 2px rgba(0,213,102,0.14) !important;
  outline: none !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   METRICS  — glassmorphism cards with hover lift
   ══════════════════════════════════════════════════════════════════════════ */

[data-testid="stMetric"] {
  background: rgba(18,21,30,0.88) !important;
  border: 1px solid rgba(255,255,255,0.07) !important;
  border-radius: 10px !important;
  padding: 12px 16px !important;
  transition: border-color 0.16s ease, transform 0.16s ease,
              box-shadow 0.16s ease !important;
}
[data-testid="stMetric"]:hover {
  border-color: rgba(0,213,102,0.22) !important;
  transform: translateY(-1px) !important;
  box-shadow: 0 4px 16px rgba(0,0,0,0.28) !important;
}
[data-testid="stMetricValue"] {
  font-family: Inter, -apple-system, sans-serif !important;
  font-weight: 800 !important;
  color: #E8EEFF !important;
  letter-spacing: -0.5px !important;
}
[data-testid="stMetricLabel"] {
  font-family: Inter, -apple-system, sans-serif !important;
  font-size: 0.68rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.09em !important;
  text-transform: uppercase !important;
  color: #8892AA !important;
}
[data-testid="stMetricDelta"] {
  font-size: 0.80rem !important;
  font-weight: 600 !important;
}
[data-testid="stMetricDelta"] svg { display: none !important; }

/* ══════════════════════════════════════════════════════════════════════════
   EXPANDERS
   ══════════════════════════════════════════════════════════════════════════ */

[data-testid="stExpander"] {
  background: rgba(15,17,24,0.80) !important;
  border: 1px solid rgba(255,255,255,0.07) !important;
  border-radius: 10px !important;
  overflow: hidden !important;
  transition: border-color 0.16s ease, box-shadow 0.16s ease !important;
}
[data-testid="stExpander"]:hover {
  border-color: rgba(0,213,102,0.20) !important;
  box-shadow: 0 2px 12px rgba(0,0,0,0.25) !important;
}
.streamlit-expanderHeader,
[data-testid="stExpander"] summary {
  font-family: Inter, -apple-system, sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.88rem !important;
  color: #B8C0D4 !important;
  padding: 12px 14px !important;
  transition: color 0.14s ease !important;
}
.streamlit-expanderHeader:hover,
[data-testid="stExpander"] summary:hover {
  color: #E8EEFF !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   SIDEBAR NAV LINKS  — pill items with active indicator
   ══════════════════════════════════════════════════════════════════════════ */

[data-testid="stSidebarNavLink"] {
  border-radius: 7px !important;
  margin: 1px 6px !important;
  padding: 7px 10px !important;
  transition: all 0.14s cubic-bezier(0.4, 0, 0.2, 1) !important;
}
[data-testid="stSidebarNavLink"]:hover:not([aria-selected="true"]) {
  background: rgba(255,255,255,0.05) !important;
  padding-left: 14px !important;
}
[data-testid="stSidebarNavLink"][aria-selected="true"],
[data-testid="stSidebarNavLink"][aria-current="page"] {
  background: rgba(0,213,102,0.09) !important;
  border-left: 2px solid #00D566 !important;
  padding-left: 12px !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   DATAFRAME  — rounded + bordered
   ══════════════════════════════════════════════════════════════════════════ */

[data-testid="stDataFrame"],
[data-testid="stDataFrameResizable"] {
  border: 1px solid rgba(255,255,255,0.07) !important;
  border-radius: 10px !important;
  overflow: hidden !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   CHECKBOX + RADIO
   ══════════════════════════════════════════════════════════════════════════ */

[data-testid="stCheckbox"] label,
[data-testid="stRadio"] label {
  font-family: Inter, -apple-system, sans-serif !important;
  font-size: 0.85rem !important;
  color: #B8C0D4 !important;
  transition: color 0.14s ease !important;
}
[data-testid="stCheckbox"] label:hover,
[data-testid="stRadio"] label:hover {
  color: #E8EEFF !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   SPINNER  — green brand color
   ══════════════════════════════════════════════════════════════════════════ */

[data-testid="stSpinner"] > div {
  border-color: rgba(0,213,102,0.15) rgba(0,213,102,0.15)
                rgba(0,213,102,0.15) #00D566 !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   ALERTS  — rounded + light border styling
   ══════════════════════════════════════════════════════════════════════════ */

[data-testid="stAlert"] {
  border-radius: 10px !important;
  font-family: Inter, -apple-system, sans-serif !important;
  font-size: 0.83rem !important;
  border-width: 1px !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   HR / DIVIDER
   ══════════════════════════════════════════════════════════════════════════ */

hr {
  border: none !important;
  border-top: 1px solid rgba(255,255,255,0.05) !important;
  margin: 16px 0 !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   PLOTLY CHART CONTAINER  — subtle lift on hover
   ══════════════════════════════════════════════════════════════════════════ */

[data-testid="stPlotlyChart"] {
  border-radius: 10px !important;
  transition: box-shadow 0.20s ease !important;
}
[data-testid="stPlotlyChart"]:hover {
  box-shadow: 0 6px 24px rgba(0,0,0,0.45) !important;
}

/* ══════════════════════════════════════════════════════════════════════════
   PERFORMANCE  — reduce paint/layout cost
   ══════════════════════════════════════════════════════════════════════════ */

/* Only animate elements that need it; avoid global will-change */
.stButton > button,
.stTabs [data-baseweb="tab"],
[data-testid="stMetric"],
[data-testid="stExpander"],
[data-testid="stSidebarNavLink"] {
  will-change: transform !important;
}

/* contain layout on sidebar so it never triggers full-page reflow */
section[data-testid="stSidebar"] {
  contain: layout style !important;
}

/* contain Plotly chart iframes */
[data-testid="stPlotlyChart"] iframe {
  contain: strict !important;
}

/* Page fade-in */
@keyframes ua_page_in {
  from { opacity: 0; transform: translateY(5px); }
  to   { opacity: 1; transform: translateY(0); }
}
.main .block-container,
[data-testid="stMainBlockContainer"] {
  animation: ua_page_in 0.22s ease forwards !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: rgba(0,213,102,0.20);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(0,213,102,0.42); }
</style>
"""


def inject_skeleton_css() -> None:
    """
    Inject the skeleton/shimmer CSS + modern UI overrides into the page.
    Safe to call multiple times — Streamlit deduplicates identical markdown.
    """
    import streamlit as st
    st.markdown(_SKELETON_CSS + _MODERN_UI_CSS, unsafe_allow_html=True)


def skeleton_cards(n: int = 3, height: int = 110, cols: int = 1) -> str:
    """
    Return HTML for `n` stacked shimmer card placeholders.
    Use `cols` to lay them out in a CSS grid (1–4 columns).

    Args:
        n:      number of skeleton cards
        height: card height in pixels
        cols:   number of grid columns
    """
    card = (
        f'<div class="ua-sk-wrap">'
        f'  <div class="ua-sk" style="height:{height}px;width:100%;"></div>'
        f'</div>'
    )
    grid_css = f"display:grid;grid-template-columns:repeat({cols},1fr);gap:10px;"
    return f'<div style="{grid_css}">{"".join([card] * n)}</div>'


def skeleton_chart_block(height: int = 300, title_lines: int = 1) -> str:
    """
    Return HTML for a shimmer chart placeholder (full-width).

    Args:
        height:      chart area height in pixels
        title_lines: number of fake title/label lines above the chart area
    """
    lines_html = "".join(
        f'<div class="ua-sk-line" style="width:{w}%;margin-bottom:6px;"></div>'
        for w in ([40] + [25] * (title_lines - 1))[:title_lines]
    )
    return (
        f'<div class="ua-sk-wrap">'
        f'  {lines_html}'
        f'  <div class="ua-sk" style="height:{height}px;width:100%;margin-top:8px;"></div>'
        f'</div>'
    )


def loading_splash(fact: str | None = None, height: int = 260,
                   sub: str = "Loading macro signal intelligence") -> str:
    """Branded loading panel: a filled brand hexagon, the wordmark, and a true
    macro fun fact. For use in an st.empty() placeholder before a heavy fetch:

        ph = st.empty()
        ph.markdown(loading_splash(), unsafe_allow_html=True)
        data = expensive_fetch()
        ph.empty()

    The shape is a filled hexagon in the brand green->teal->purple gradient at
    moderate opacity, so it reads as a distinct object on the #0B0D12 page rather
    than a wash. Motion is a slow, non-distracting pulse; it respects
    prefers-reduced-motion. The fact defaults to a random genuinely-true one from
    utils.macro_facts (see that module's editorial rule).
    """
    if fact is None:
        from utils.macro_facts import random_fact
        fact = random_fact()
    # escape the fact for safe HTML embedding
    import html as _html
    fact_safe = _html.escape(fact)
    return f"""
<div class="ua-load-splash" role="status" aria-label="Loading" style="height:{height}px;">
  <div class="ua-load-stage">
    <svg class="ua-load-hex" viewBox="0 0 100 100" width="128" height="128" aria-hidden="true">
      <defs>
        <linearGradient id="uaLoadGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#00D566"/>
          <stop offset="55%" stop-color="#12B5A6"/>
          <stop offset="100%" stop-color="#7C3AED"/>
        </linearGradient>
      </defs>
      <polygon points="50,4 91,27 91,73 50,96 9,73 9,27"
               fill="url(#uaLoadGrad)" opacity="0.92"/>
      <polygon points="50,4 91,27 91,73 50,96 9,73 9,27"
               fill="none" stroke="#0B0D12" stroke-width="2"/>
      <text x="50" y="60" text-anchor="middle" font-family="Inter,sans-serif"
            font-size="30" font-weight="900" fill="#0B0D12">UA</text>
    </svg>
  </div>
  <div class="ua-load-word">UNSTRUCTURED <span>ALPHA</span></div>
  <div class="ua-load-sub">{sub}</div>
  <div class="ua-load-fact">{fact_safe}</div>
</div>
<style>
.ua-load-splash{{display:flex;flex-direction:column;align-items:center;justify-content:center;
  text-align:center;gap:6px;padding:18px;font-family:'Inter',system-ui,sans-serif;}}
.ua-load-stage{{filter:drop-shadow(0 0 26px rgba(0,213,102,0.28));
  animation:ua-load-pulse 2.4s ease-in-out infinite;}}
.ua-load-word{{margin-top:10px;font-size:1.05rem;font-weight:800;letter-spacing:.05em;color:#E8EEFF;}}
.ua-load-word span{{color:#00D566;}}
.ua-load-sub{{font-size:.72rem;color:#6B7FBF;letter-spacing:.02em;}}
.ua-load-fact{{margin-top:12px;max-width:440px;font-size:.8rem;line-height:1.5;color:#9AA6C4;
  border-top:1px solid rgba(255,255,255,0.07);padding-top:12px;}}
.ua-load-fact::before{{content:"DID YOU KNOW";display:block;font-size:.58rem;font-weight:700;
  letter-spacing:.14em;color:#4F5B7A;margin-bottom:5px;}}
@keyframes ua-load-pulse{{0%,100%{{transform:scale(1);opacity:.92;}}50%{{transform:scale(1.06);opacity:1;}}}}
@media (prefers-reduced-motion: reduce){{.ua-load-stage{{animation:none;}}}}
</style>
"""


def empty_state(icon: str = "", title: str = "", body: str = "", action: str = "") -> str:
    """
    Return HTML for a tasteful, emoji-free empty-state block.

    `icon` is accepted for backwards compatibility but is NOT rendered as an
    emoji — the de-emoji pass applies here too, so it's replaced by a neutral
    monochrome mark. `action` is an optional "what to do next" line; every empty
    state should point the user somewhere rather than dead-ending them.

    Usage::

        st.markdown(empty_state(title="No alerts yet",
                                body="Set a threshold on any ticker to get started.",
                                action="Open the Watchlist to add one →"),
                    unsafe_allow_html=True)
    """
    body_html = (
        f'<div style="font-size:0.82rem;color:#8892AA;margin-top:4px;line-height:1.55;">'
        f'{body}</div>'
    ) if body else ""
    action_html = (
        f'<div style="font-size:0.8rem;color:#7C9CFF;font-weight:600;margin-top:10px;">'
        f'{action}</div>'
    ) if action else ""
    # Neutral, monochrome "nothing here yet" mark — a hollow ring with a dash.
    mark = (
        '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" '
        'xmlns="http://www.w3.org/2000/svg" style="opacity:0.55;">'
        '<circle cx="12" cy="12" r="9" stroke="#5B6478" stroke-width="1.5"/>'
        '<path d="M8 12h8" stroke="#5B6478" stroke-width="1.5" stroke-linecap="round"/></svg>'
    )
    return (
        f'<div class="ua-empty">'
        f'<div class="ua-empty-icon">{mark}</div>'
        f'<div class="ua-empty-title">{title}</div>'
        f'{body_html}'
        f'{action_html}'
        f'</div>'
    )


def source_badge(source: str, series_id: str = "", extra: str = "") -> str:
    """
    Return a compact HTML provenance badge string like:
        「 FRED · TRUCKD11 」  or  「 EIA · PET.WCESTUS1.W 」
    Suitable for embedding directly inside a card's HTML markup.
    `extra` is appended after the series_id (e.g. " · SEC EDGAR").
    """
    _SOURCE_LABELS: dict[str, tuple[str, str]] = {
        "fred":    ("FRED",      "#00C8E0"),
        "eia":     ("EIA",       "#F59E0B"),
        "sec":     ("SEC EDGAR", "#A78BFA"),
        "finra":   ("FINRA",     "#A78BFA"),
        "yfinance":("yfinance",  "#6B7FBF"),
        "google":  ("Google Trends", "#6B7FBF"),
        "fomc":    ("FOMC",      "#6B7FBF"),
    }
    label, color = _SOURCE_LABELS.get(source.lower(), (source.upper(), "#6B7FBF"))
    parts = [label]
    if series_id:
        parts.append(series_id)
    if extra:
        parts.append(extra)
    text = " · ".join(parts)
    return (
        f'<span style="display:inline-block;font-size:0.65rem;font-weight:600;'
        f'letter-spacing:0.04em;color:{color};background:rgba(255,255,255,0.04);'
        f'border:1px solid rgba(255,255,255,0.08);border-radius:4px;'
        f'padding:1px 6px;font-family:Inter,monospace;">'
        f'{text}</span>'
    )


def skeleton_stat_row(n: int = 4) -> str:
    """
    Return HTML for a row of `n` small stat-box skeletons (metric cards).
    Typically used to placeholder a row of KPI chips above a chart.
    """
    card = (
        '<div class="ua-sk-wrap" style="flex:1;min-width:0;">'
        '  <div class="ua-sk-line" style="width:60%;"></div>'
        '  <div class="ua-sk" style="height:36px;width:80%;margin-top:4px;"></div>'
        '</div>'
    )
    return (
        f'<div style="display:flex;gap:10px;margin-bottom:10px;">'
        f'{"".join([card] * n)}'
        f'</div>'
    )


# ── Premium Card Helpers ──────────────────────────────────────────────────────

def glass_card(content_html: str, accent: str = "", padding: str = "20px 22px",
               radius: str = "14px", glow: bool = False) -> str:
    """
    Return a glassmorphism card wrapping arbitrary HTML content.

    Args:
        content_html: Inner HTML to wrap.
        accent:       Optional hex accent color — adds a 3px left border + tinted bg.
        padding:      CSS padding string.
        radius:       Border radius.
        glow:         If True, adds a soft outer glow matching the accent color.
    """
    if accent:
        hex_c = accent.lstrip("#")
        r_, g_, b_ = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
        bg_tint  = f"rgba({r_},{g_},{b_},0.05)"
        border   = f"1px solid rgba({r_},{g_},{b_},0.18)"
        l_border = f"3px solid {accent}"
        shadow   = (f"box-shadow:0 0 28px rgba({r_},{g_},{b_},0.12),0 8px 32px rgba(0,0,0,0.35);"
                    if glow else "box-shadow:0 4px 20px rgba(0,0,0,0.3);")
    else:
        bg_tint  = "rgba(18,21,30,0.85)"
        border   = "1px solid rgba(255,255,255,0.07)"
        l_border = "none"
        shadow   = "box-shadow:0 4px 20px rgba(0,0,0,0.3);"

    left_border_css = (f"border-left:{l_border};" if l_border != "none" else "")
    return (
        f'<div style="background:{bg_tint};{border and "border:" + border + ";"}'
        f'{left_border_css}border-radius:{radius};padding:{padding};'
        f'font-family:Inter,-apple-system,sans-serif;{shadow}'
        f'backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);">'
        f'{content_html}'
        f'</div>'
    )


def kpi_metric(label: str, value: str, sub: str = "", color: str = "#E8EEFF",
               icon: str = "") -> str:
    """
    Return HTML for a single KPI metric tile.

    Args:
        label: Small uppercase label above the value.
        value: The big number/text displayed prominently.
        sub:   Optional sub-line below the value.
        color: Accent color for the value text.
        icon:  Optional emoji/icon prefix before the value.
    """
    icon_html = f'<span style="margin-right:4px;">{icon}</span>' if icon else ""
    sub_html = (
        f'<div style="font-size:0.72rem;color:#8892AA;margin-top:3px;'
        f'font-family:Inter,sans-serif;">{sub}</div>'
    ) if sub else ""
    return (
        f'<div style="font-family:Inter,-apple-system,sans-serif;">'
        f'<div style="font-size:0.60rem;font-weight:700;letter-spacing:0.12em;'
        f'text-transform:uppercase;color:#8892AA;margin-bottom:6px;">{label}</div>'
        f'<div style="font-size:1.85rem;font-weight:800;color:{color};'
        f'letter-spacing:-0.8px;line-height:1.1;">{icon_html}{value}</div>'
        f'{sub_html}'
        f'</div>'
    )


def section_label(text: str, color: str = "#8892AA", dot: str = "") -> str:
    """
    Return a small ALL-CAPS section label with optional colored dot prefix.
    Consistent with the UA design system's micro-typography.
    """
    dot_html = (
        f'<span style="display:inline-block;width:6px;height:6px;border-radius:50%;'
        f'background:{dot};margin-right:6px;vertical-align:middle;"></span>'
    ) if dot else ""
    return (
        f'<div style="font-size:0.60rem;font-weight:700;letter-spacing:0.14em;'
        f'text-transform:uppercase;color:{color};margin-bottom:8px;'
        f'font-family:Inter,sans-serif;">{dot_html}{text}</div>'
    )


def gradient_text(text: str, from_color: str = "#00D566",
                  to_color: str = "#00C8E0", size: str = "1rem",
                  weight: str = "800") -> str:
    """Return HTML for gradient-clipped text (Webkit-based)."""
    return (
        f'<span style="font-size:{size};font-weight:{weight};'
        f'background:linear-gradient(135deg,{from_color},{to_color});'
        f'-webkit-background-clip:text;-webkit-text-fill-color:transparent;'
        f'background-clip:text;font-family:Inter,sans-serif;">{text}</span>'
    )


def avatar_initials(name: str, bg: str = "#1A1E2C", size: int = 36) -> str:
    """
    Return an HTML circular avatar showing up to 2 initials of `name`.
    Used in testimonials and user profile chips.
    """
    parts   = name.strip().split()
    letters = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()
    return (
        f'<span style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:{size}px;height:{size}px;border-radius:50%;background:{bg};'
        f'border:1px solid rgba(255,255,255,0.10);font-size:{max(size//3,10)}px;'
        f'font-weight:700;color:#C8D0E4;font-family:Inter,sans-serif;'
        f'flex-shrink:0;">{letters}</span>'
    )


# ── Animated Counter CSS ──────────────────────────────────────────────────────
_COUNTER_CSS = """
<style>
/* ── Animated count-up for KPI strips ──────────────────────────────────────── */
@keyframes ua_count_up {
  from { opacity: 0; transform: translateY(8px) scale(0.96); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
.ua-kpi-animate {
  animation: ua_count_up 0.45s cubic-bezier(0.34,1.56,0.64,1) both;
}
.ua-kpi-animate:nth-child(1) { animation-delay: 0.00s; }
.ua-kpi-animate:nth-child(2) { animation-delay: 0.07s; }
.ua-kpi-animate:nth-child(3) { animation-delay: 0.14s; }
.ua-kpi-animate:nth-child(4) { animation-delay: 0.21s; }

/* ── Gradient border card (animated) ────────────────────────────────────────── */
@keyframes ua_border_spin {
  0%   { background-position: 0% 50%;   }
  50%  { background-position: 100% 50%; }
  100% { background-position: 0% 50%;   }
}
.ua-gradient-border {
  position: relative;
  border-radius: 14px;
  padding: 1px;
  background: linear-gradient(135deg, #00D566, #00C8E0, #7C3AED, #00D566);
  background-size: 300% 300%;
  animation: ua_border_spin 4s linear infinite;
}
.ua-gradient-border > div {
  background: #12151E;
  border-radius: 13px;
  padding: 20px 22px;
}

/* ── Pulse dot (live indicator) ──────────────────────────────────────────────── */
@keyframes ua_pulse {
  0%, 100% { opacity: 1;   transform: scale(1); }
  50%       { opacity: 0.5; transform: scale(1.3); }
}
.ua-pulse-dot {
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #00D566;
  animation: ua_pulse 1.8s ease-in-out infinite;
  vertical-align: middle;
  margin-right: 5px;
}
.ua-pulse-dot.bear { background: #FF4444; }

/* ── Feature spotlight card ───────────────────────────────────────────────── */
.ua-spotlight {
  background: rgba(18,21,30,0.85);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 14px;
  padding: 24px 20px 20px;
  font-family: Inter, -apple-system, sans-serif;
  transition: border-color 0.22s ease, box-shadow 0.22s ease, transform 0.22s ease;
  position: relative;
  overflow: hidden;
}
.ua-spotlight::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--ua-spotlight-accent, linear-gradient(90deg, #00D566, #00C8E0));
  border-radius: 14px 14px 0 0;
}
.ua-spotlight:hover {
  border-color: rgba(255,255,255,0.15);
  box-shadow: 0 8px 32px rgba(0,0,0,0.45);
  transform: translateY(-3px);
}
.ua-spotlight-icon {
  font-size: 2rem;
  margin-bottom: 12px;
  display: block;
}
.ua-spotlight-tag {
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.ua-spotlight-title {
  font-size: 0.96rem;
  font-weight: 700;
  color: #E8EEFF;
  margin-bottom: 10px;
  line-height: 1.35;
  letter-spacing: -0.15px;
}
.ua-spotlight-body {
  font-size: 0.80rem;
  color: #B8C0D4;
  line-height: 1.65;
  margin-bottom: 14px;
}
.ua-spotlight-proof {
  font-size: 0.70rem;
  font-weight: 600;
  padding: 4px 0;
  border-top: 1px solid rgba(255,255,255,0.06);
}

/* ── Testimonial card ─────────────────────────────────────────────────────── */
.ua-testi {
  background: #12151E;
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 12px;
  padding: 20px;
  font-family: Inter, -apple-system, sans-serif;
  transition: border-color 0.18s ease;
}
.ua-testi:hover { border-color: rgba(255,255,255,0.14); }
.ua-testi-stars { color: #F59E0B; font-size: 0.82rem; letter-spacing: 2px; margin-bottom: 10px; }
.ua-testi-quote { font-size: 0.85rem; color: #B8C0D4; line-height: 1.65; font-style: italic; margin-bottom: 14px; }
.ua-testi-footer { display: flex; align-items: center; gap: 10px; }
.ua-testi-name   { font-size: 0.78rem; font-weight: 700; color: #E8EEFF; }
.ua-testi-role   { font-size: 0.70rem; color: #6B7FBF; }

/* ── Step card ────────────────────────────────────────────────────────────── */
.ua-step {
  background: rgba(18,21,30,0.85);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 12px;
  padding: 20px 18px;
  font-family: Inter, -apple-system, sans-serif;
  transition: border-color 0.2s ease, transform 0.2s ease;
  position: relative;
  overflow: hidden;
}
.ua-step::after {
  content: '';
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 3px;
  background: var(--ua-step-accent, #00D566);
  border-radius: 0 0 12px 12px;
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.3s ease;
}
.ua-step:hover::after { transform: scaleX(1); }
.ua-step:hover { transform: translateY(-2px); border-color: rgba(255,255,255,0.13); }
.ua-step-num {
  font-size: 2.2rem;
  font-weight: 900;
  line-height: 1;
  margin-bottom: 8px;
  letter-spacing: -1px;
}
.ua-step-title { font-size: 0.88rem; font-weight: 700; color: #E8EEFF; margin-bottom: 6px; }
.ua-step-body  { font-size: 0.76rem; color: #B8C0D4; line-height: 1.6; }

/* ── Pro upgrade banner ──────────────────────────────────────────────────── */
.ua-pro-banner {
  background: linear-gradient(135deg, rgba(124,58,237,0.12) 0%, rgba(0,200,224,0.06) 100%);
  border: 1px solid rgba(124,58,237,0.28);
  border-radius: 16px;
  padding: 26px 32px;
  font-family: Inter, -apple-system, sans-serif;
  position: relative;
  overflow: hidden;
}
.ua-pro-banner::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(124,58,237,0.6), rgba(0,200,224,0.4), transparent);
}

/* ── Guarantee badge ─────────────────────────────────────────────────────── */
.ua-guarantee {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(0,213,102,0.06);
  border: 1px solid rgba(0,213,102,0.22);
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 0.75rem;
  color: #00D566;
  font-family: Inter, sans-serif;
  font-weight: 600;
}

/* ── Pricing card featured shimmer ──────────────────────────────────────── */
@keyframes ua_card_shine {
  0%   { transform: translateX(-100%) rotate(25deg); }
  100% { transform: translateX(300%) rotate(25deg);  }
}
.ua-card-shine::after {
  content: '';
  position: absolute;
  top: -50%; left: -50%;
  width: 30%; height: 200%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.04), transparent);
  animation: ua_card_shine 3.5s ease-in-out infinite;
  pointer-events: none;
}
</style>
"""


def inject_premium_css() -> None:
    """
    Inject premium animation + component CSS + modern UI overrides.
    Safe to call multiple times (Streamlit deduplicates identical markdown).
    Covers: animated KPI counters, gradient border cards, testimonial cards,
    spotlight feature cards, step cards, Pro banner, guarantee badge,
    pulse dot, avatar initials, plus pill tabs, modern buttons, metrics, etc.
    """
    import streamlit as st
    st.markdown(_COUNTER_CSS + _MODERN_UI_CSS, unsafe_allow_html=True)


def inject_all_css() -> None:
    """
    Convenience function — inject ALL CSS in a single call:
    skeleton/shimmer + premium animations + modern UI overrides.

    Safe to call multiple times (Streamlit deduplicates identical markdown
    injections within a session).

    Usage::

        from utils.theme import inject_all_css
        inject_all_css()  # once near the top of any page
    """
    import streamlit as st
    st.markdown(_SKELETON_CSS + _COUNTER_CSS + _MODERN_UI_CSS, unsafe_allow_html=True)


# ── Polish helpers ────────────────────────────────────────────────────────────

def render_signal_legend() -> str:
    """
    Compact horizontal legend explaining Confluence Score ranges (Bull / Neutral / Bear).
    Designed to sit above signal card grids.
    """
    try:
        from utils.config import SIGNAL_COUNT as _SC
    except Exception:
        _SC = 47
    return (
        '<div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;'
        'padding:8px 14px;background:rgba(255,255,255,0.03);border-radius:8px;'
        'border:1px solid rgba(255,255,255,0.06);font-family:Inter,sans-serif;'
        'margin-bottom:12px;">'
        '<span style="font-size:0.7rem;font-weight:600;color:#4A5280;'
        'letter-spacing:0.07em;text-transform:uppercase;">Score key</span>'
        '<span style="font-size:0.78rem;color:#00D566;display:flex;align-items:center;gap:5px;">'
        '<span style="width:8px;height:8px;border-radius:50%;background:#00D566;'
        'display:inline-block;flex-shrink:0;"></span>65–100 Bullish</span>'
        '<span style="font-size:0.78rem;color:#F59E0B;display:flex;align-items:center;gap:5px;">'
        '<span style="width:8px;height:8px;border-radius:50%;background:#F59E0B;'
        'display:inline-block;flex-shrink:0;"></span>36–64 Neutral</span>'
        '<span style="font-size:0.78rem;color:#FF4D6A;display:flex;align-items:center;gap:5px;">'
        '<span style="width:8px;height:8px;border-radius:50%;background:#FF4D6A;'
        'display:inline-block;flex-shrink:0;"></span>0–35 Bearish</span>'
        '<span style="margin-left:auto;font-size:0.72rem;color:#4A5280;">'
        f'Composite of {_SC} macro signals · 0–100 scale</span>'
        '</div>'
    )


def render_data_freshness(
    source: str = "FRED / EIA / SEC EDGAR",
    cadence: str = "Updated every ~2 hours",
    note: str = "",
) -> str:
    """
    Compact provenance + freshness line for display below section headers or charts.
    Returns an HTML string — pass to st.markdown(..., unsafe_allow_html=True).
    """
    note_html = (
        f'<span style="color:#4A5280;"> · {note}</span>'
        if note else ""
    )
    return (
        f'<div style="display:flex;align-items:center;gap:6px;margin:4px 0 10px;'
        f'font-family:Inter,sans-serif;">'
        f'<span style="width:6px;height:6px;border-radius:50%;background:#00D566;'
        f'display:inline-block;flex-shrink:0;"></span>'
        f'<span style="font-size:0.72rem;color:#4A5280;">'
        f'<span style="color:#8892AA;font-weight:600;">{cadence}</span>'
        f' · Sources: {source}{note_html}</span>'
        f'</div>'
    )


def render_educational_callout(
    title: str,
    body: str,
    icon: str = "",
    accent: str = "#00C8E0",
) -> str:
    """
    Educational info callout card — explains what a metric or signal means.
    Non-intrusive; uses a left border accent rather than a full background fill.
    Returns an HTML string.
    """
    hex_c = accent.lstrip("#")
    r_, g_, b_ = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    return (
        f'<div style="border-left:3px solid {accent};'
        f'background:rgba({r_},{g_},{b_},0.05);'
        f'border-radius:0 8px 8px 0;padding:10px 14px;margin:10px 0;'
        f'font-family:Inter,sans-serif;">'
        f'<div style="display:flex;align-items:flex-start;gap:8px;">'
        f'<div>'
        f'<div style="font-size:0.8rem;font-weight:700;color:#C8D0E4;'
        f'margin-bottom:3px;">{title}</div>'
        f'<div style="font-size:0.78rem;color:#8892AA;line-height:1.55;">{body}</div>'
        f'</div></div></div>'
    )


def render_pro_cta(
    feature_name: str = "this analysis",
    description: str = "Get deeper macro context and expanded signal breakdowns.",
    compact: bool = False,
) -> str:
    """
    Clean, non-pushy Pro upgrade CTA block.
    Set compact=True for an inline pill; False for a card.
    Returns an HTML string.
    """
    if compact:
        return (
            '<div style="display:inline-flex;align-items:center;gap:8px;'
            'background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.20);'
            'border-radius:8px;padding:6px 12px;font-family:Inter,sans-serif;">'
            '<span style="font-size:0.68rem;color:#A78BFA;font-weight:700;'
            'letter-spacing:0.06em;">PRO</span>'
            f'<span style="font-size:0.8rem;color:#8892AA;">{feature_name}</span>'
            '<a href="/upgrade-to-pro" style="font-size:0.78rem;color:#7C3AED;font-weight:600;'
            'text-decoration:none;margin-left:4px;white-space:nowrap;">Unlock →</a>'
            '</div>'
        )
    return (
        '<div style="background:rgba(124,58,237,0.07);'
        'border:1px solid rgba(124,58,237,0.18);border-radius:10px;'
        'padding:14px 18px;margin:12px 0;font-family:Inter,sans-serif;'
        'display:flex;align-items:flex-start;gap:12px;">'
        '<div style="flex:1;min-width:0;">'
        '<div style="font-size:0.82rem;font-weight:700;color:#A78BFA;margin-bottom:3px;">'
        f'Pro — {feature_name}</div>'
        f'<div style="font-size:0.78rem;color:#8892AA;line-height:1.5;">{description}</div>'
        '<div style="font-size:0.68rem;color:#6B7280;margin-top:5px;">7-day free trial · cancel anytime</div>'
        '</div>'
        '<a href="/upgrade-to-pro" style="font-size:0.8rem;color:#fff;font-weight:700;'
        'text-decoration:none;white-space:nowrap;padding:8px 16px;'
        'background:linear-gradient(135deg,#7C3AED,#6D28D9);'
        'border-radius:7px;align-self:center;">Get Pro →</a>'
        '</div>'
    )


def render_platform_note() -> str:
    """
    One-line informational note clarifying the platform's purpose.
    Designed to sit below the hero section on the home page.
    Returns an HTML string — call st.markdown(..., unsafe_allow_html=True).
    """
    return (
        '<div style="text-align:center;padding:8px 16px;'
        'font-family:Inter,sans-serif;font-size:0.75rem;color:#4A5280;">'
        'Unstructured Alpha aggregates publicly available macro data for informational '
        'purposes only. Nothing here constitutes investment advice. '
        'All signals reflect statistical patterns in historical data, not predictions.'
        '</div>'
    )


# ── Animated stat counter (JavaScript count-up) ───────────────────────────────

def animated_stat_counter(
    stats: list[tuple[str, float, str, str]],
    height: int = 90,
    cols: int = 4,
    duration_ms: int = 1200,
) -> None:
    """
    Render a row of KPI tiles with JavaScript count-up animation using
    st.components.v1.html(). Each number counts up from 0 to its target
    over `duration_ms` milliseconds with an easing curve.

    Args:
        stats: list of (label, value, prefix, suffix) tuples.
               e.g. [("Signals", 43, "", ""), ("Bull", 62.0, "", "%")]
        height:      iframe height in pixels (auto-sized to fit the tiles)
        cols:        number of columns in the grid (1–6)
        duration_ms: count-up animation duration in milliseconds

    Usage::

        from utils.theme import animated_stat_counter
        animated_stat_counter([
            ("Signals Tracked", 43, "", ""),
            ("Bullish Score",   72, "", "%"),
            ("Active Alerts",    5, "", ""),
            ("Days Live",       90, "", ""),
        ])
    """
    import streamlit.components.v1 as components
    import json

    items_js = json.dumps([
        {"label": s[0], "target": float(s[1]),
         "prefix": s[2], "suffix": s[3],
         "decimals": 1 if (s[1] != int(s[1])) else 0}
        for s in stats
    ])

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#0b0d12; font-family:Inter,-apple-system,sans-serif; }}
  .grid {{
    display: grid;
    grid-template-columns: repeat({cols}, 1fr);
    gap: 10px;
    padding: 4px 0;
  }}
  .tile {{
    background: #12151e;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    padding: 14px 16px;
    transition: border-color 0.18s;
  }}
  .tile:hover {{ border-color: rgba(124,58,237,0.35); }}
  .label {{
    font-size: 0.60rem;
    font-weight: 700;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    color: #8892aa;
    margin-bottom: 6px;
  }}
  .value {{
    font-size: 1.55rem;
    font-weight: 800;
    color: #e8eeff;
    letter-spacing: -0.5px;
    line-height: 1.1;
  }}
</style>
</head>
<body>
<div class="grid" id="grid"></div>
<script>
var stats = {items_js};
var grid  = document.getElementById('grid');

stats.forEach(function(s, i) {{
  var tile = document.createElement('div');
  tile.className = 'tile';
  var lbl = document.createElement('div');
  lbl.className = 'label';
  lbl.textContent = s.label;
  var val = document.createElement('div');
  val.className = 'value';
  val.textContent = s.prefix + '0' + s.suffix;
  tile.appendChild(lbl);
  tile.appendChild(val);
  grid.appendChild(tile);

  // stagger start
  setTimeout(function() {{
    var start = null;
    function step(ts) {{
      if (!start) start = ts;
      var progress = Math.min((ts - start) / {duration_ms}, 1);
      // ease-out cubic
      var ease = 1 - Math.pow(1 - progress, 3);
      var cur = s.target * ease;
      val.textContent = s.prefix + cur.toFixed(s.decimals) + s.suffix;
      if (progress < 1) requestAnimationFrame(step);
    }}
    requestAnimationFrame(step);
  }}, i * 80);
}});
</script>
</body>
</html>
"""
    components.html(html, height=height, scrolling=False)


# ── Live data badge helpers ───────────────────────────────────────────────────

def live_badge(text: str = "LIVE", color: str = "#00D566") -> str:
    """
    Compact animated pulse badge to indicate live/real-time data.
    Returns HTML string — use inside st.markdown(unsafe_allow_html=True)
    or embed inside larger HTML blocks.

    Usage::

        st.markdown("Market data " + live_badge(), unsafe_allow_html=True)
    """
    hex_c = color.lstrip("#")
    r_, g_, b_ = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'background:rgba({r_},{g_},{b_},0.10);'
        f'border:1px solid rgba({r_},{g_},{b_},0.30);'
        f'border-radius:20px;padding:2px 8px;font-size:0.65rem;'
        f'font-weight:700;color:{color};letter-spacing:0.06em;'
        f'font-family:Inter,sans-serif;vertical-align:middle;">'
        f'<span class="ua-pulse-dot" style="background:{color};'
        f'width:6px;height:6px;border-radius:50%;display:inline-block;'
        f'animation:ua_pulse 1.8s ease-in-out infinite;flex-shrink:0;"></span>'
        f'{text}</span>'
    )


def regime_pill(regime: str, score: float | None = None) -> str:
    """
    Styled macro-regime pill — BULL / BEAR / NEUTRAL with color coding.
    Optionally shows a score in parentheses.

    Args:
        regime: "BULL", "BEAR", or "NEUTRAL" (case-insensitive)
        score:  Optional float score to append, e.g. 72.4

    Returns HTML string.

    Usage::

        st.markdown(regime_pill("BULL", 74), unsafe_allow_html=True)
    """
    r = regime.upper().strip()
    if r in ("BULL", "BULLISH"):
        color, bg = "#00D566", "rgba(0,213,102,0.10)"
        label = "● BULL"
    elif r in ("BEAR", "BEARISH"):
        color, bg = "#FF4444", "rgba(255,68,68,0.10)"
        label = "● BEAR"
    else:
        color, bg = "#F59E0B", "rgba(245,158,11,0.10)"
        label = "● NEUTRAL"

    score_html = (
        f' <span style="opacity:0.75;font-weight:600;">({score:.0f})</span>'
        if score is not None else ""
    )
    return (
        f'<span style="display:inline-flex;align-items:center;gap:0;'
        f'background:{bg};border:1px solid {color}33;border-radius:20px;'
        f'padding:3px 10px;font-size:0.70rem;font-weight:700;color:{color};'
        f'letter-spacing:0.06em;font-family:Inter,sans-serif;">'
        f'{label}{score_html}</span>'
    )


def signal_confidence_badge(level: str, compact: bool = False) -> str:
    """
    Render a small inline HTML badge showing signal confidence level.

    Args:
        level:   "High" | "Medium" | "Low"
        compact: if True, show icon only (no text label) — for tight card layouts

    Returns an HTML string. Inline-safe (no block elements).

    Usage::
        st.markdown(signal_confidence_badge("High"), unsafe_allow_html=True)
    """
    _cfg = {
        "High":   {"icon": "◆", "color": "#00D566", "bg": "rgba(0,213,102,0.10)",
                   "border": "rgba(0,213,102,0.28)", "label": "High confidence"},
        "Medium": {"icon": "◇", "color": "#F59E0B", "bg": "rgba(245,158,11,0.10)",
                   "border": "rgba(245,158,11,0.28)", "label": "Med confidence"},
        "Low":    {"icon": "○", "color": "#6B7FBF", "bg": "rgba(107,127,191,0.10)",
                   "border": "rgba(107,127,191,0.25)", "label": "Low confidence"},
    }
    c = _cfg.get(level, _cfg["Low"])
    text = c["icon"] if compact else f'{c["icon"]} {c["label"]}'
    return (
        f'<span title="Signal confidence: {level}" '
        f'style="display:inline-block;font-size:0.62rem;font-weight:700;'
        f'letter-spacing:0.04em;color:{c["color"]};background:{c["bg"]};'
        f'border:1px solid {c["border"]};border-radius:4px;padding:1px 6px;'
        f'font-family:Inter,sans-serif;white-space:nowrap;">'
        f'{text}</span>'
    )


def chart_insight_caption(text: str, icon: str = "", muted: bool = False) -> str:
    """
    Render a styled insight caption intended to appear directly below a Plotly chart.

    Provides the user with a plain-English take on what the chart is showing —
    the "so what" layer that raw data alone doesn't communicate.

    Args:
        text:  The caption text (one or two sentences max).
        icon:  Deprecated; retained for backwards-compatible call sites.
        muted: If True, use a more subdued style (for secondary charts).

    Returns an HTML string.

    Usage::
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(chart_insight_caption("HY spreads are narrowing — risk appetite is
                    improving across credit markets."), unsafe_allow_html=True)
    """
    color   = "#8892AA" if muted else "#B8C0D4"
    bg      = "rgba(18,21,30,0.0)" if muted else "rgba(18,21,30,0.55)"
    border  = "rgba(255,255,255,0.04)" if muted else "rgba(255,255,255,0.07)"
    return (
        f'<div style="background:{bg};border:1px solid {border};border-radius:8px;'
        f'padding:9px 14px;margin-top:-4px;margin-bottom:12px;'
        f'font-family:Inter,sans-serif;display:flex;align-items:flex-start;gap:8px;">'
        f'<span style="font-size:0.78rem;color:{color};line-height:1.55;">{text}</span>'
        f'</div>'
    )


def progress_ring(pct: float, size: int = 48, stroke: int = 4,
                  color: str = "#00D566", label: str = "") -> str:
    """
    SVG circular progress ring — compact visual for a 0–100 percentage.
    Animates from 0 to `pct` on load.

    Args:
        pct:    value 0–100
        size:   diameter in pixels
        stroke: ring stroke width
        color:  stroke color (hex)
        label:  text rendered in the center

    Returns HTML string.

    Usage::

        st.markdown(progress_ring(72, label="72%"), unsafe_allow_html=True)
    """
    pct = max(0.0, min(100.0, float(pct)))
    r       = (size - stroke * 2) / 2
    cx = cy = size / 2
    circ    = 2 * _math.pi * r
    dash    = circ * pct / 100
    gap     = circ - dash
    # Start at top (rotate -90°)
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
        f'style="display:inline-block;vertical-align:middle;">'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
        f'stroke="rgba(255,255,255,0.06)" stroke-width="{stroke}"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" '
        f'stroke-dasharray="{dash:.2f} {gap:.2f}" '
        f'stroke-linecap="round" '
        f'transform="rotate(-90 {cx} {cy})">'
        f'<animate attributeName="stroke-dasharray" '
        f'from="0 {circ:.2f}" to="{dash:.2f} {gap:.2f}" '
        f'dur="0.9s" fill="freeze" calcMode="spline" '
        f'keyTimes="0;1" keySplines="0.25,0.46,0.45,0.94"/>'
        f'</circle>'
        + (f'<text x="{cx}" y="{cy+4}" text-anchor="middle" '
           f'font-family="Inter,sans-serif" font-size="{max(size//5, 8)}" '
           f'font-weight="700" fill="{color}">{label}</text>' if label else "")
        + f'</svg>'
    )
