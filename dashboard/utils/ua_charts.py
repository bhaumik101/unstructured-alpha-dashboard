"""Dependency-free inline-SVG chart engine for Unstructured Alpha.

Why hand-rolled SVG rather than Plotly/Chart.js: Streamlit already injects HTML,
this needs zero external CDN (a blocked CDN was rendering charts blank), the
output is tiny, and — critically — the colors are CSS custom properties, so a
single chart string re-themes automatically when the light/dark theme flips. The
generators below are a straight port of the verified v4 redesign prototype.

Usage:
    import streamlit as st
    from utils import ua_charts
    st.markdown(ua_charts.CHART_CSS, unsafe_allow_html=True)   # once per page
    st.markdown(ua_charts.line_chart(values, x_labels), unsafe_allow_html=True)

Every function returns a self-contained ``<svg class="ua-chart">…</svg>`` string.
Colors reference theme variables (``var(--royal-2)`` etc.); the page's theme CSS
defines them, so charts inherit light/dark automatically.
"""

from __future__ import annotations

from html import escape as _esc

# CSS for the chart primitives. Inject once per page (the global theme also
# defines the --royal/--grid/--muted/... variables these classes consume).
CHART_CSS = """
<style>
.ua-chart{width:100%;height:auto;display:block;font-family:Inter,system-ui,sans-serif}
.ua-chart .axis{stroke:var(--ua-line-2,#333);stroke-width:1}
.ua-chart .grid{stroke:var(--ua-grid,rgba(128,128,128,.12));stroke-width:1}
.ua-chart .tick{fill:var(--ua-muted,#8A90A6);font-size:11px}
.ua-chart .tick.cat{fill:var(--ua-text,#EAEEF7);font-weight:600}
.ua-chart .atitle{fill:var(--ua-faint,#646A88);font-size:11px;font-weight:600}
.ua-chart .refline{stroke:var(--ua-faint,#646A88);stroke-width:1;stroke-dasharray:5 5}
.ua-chart .area{fill:var(--ua-royal-2,#8B7BF7);opacity:.16}
.ua-chart .cline{fill:none;stroke:var(--ua-royal-2,#8B7BF7);stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}
.ua-chart .dot{fill:var(--ua-royal-2,#8B7BF7)}
.ua-chart .vlabel{fill:var(--ua-text,#EAEEF7);font-size:11px;font-weight:600}
</style>
"""


def _fmt(v: float) -> str:
    """Trim trailing .0 so axis ticks read 24 not 24.0, but keep 0.24."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return f"{v:g}"


def line_chart(values, x_labels, y_min=0.0, y_max=100.0, y_ticks=None,
               ref=None, y_title="", W=560, H=280) -> str:
    """A line chart with a filled area, axes, gridlines, and an optional
    horizontal reference line (e.g. the neutral-50 level).

    values    : list of numbers (the series).
    x_labels  : list of {"i": index, "label": str} tick marks on the x-axis,
                or a list of strings the same length as values (one per point,
                downsampled to ~6 ticks automatically).
    y_ticks   : explicit list of y values to label; defaults to 5 even steps.
    ref       : y-value for a dashed reference line, or None.
    """
    values = [float(v) for v in values]
    n = max(1, len(values))
    pl, pr, pt, pb = 44, 16, 16, 34
    x0, x1, y0, y1 = pl, W - pr, H - pb, pt
    if y_ticks is None:
        step = (y_max - y_min) / 5.0
        y_ticks = [y_min + step * k for k in range(6)]

    def sx(i): return x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0)
    def sy(v): return y0 - (y0 - y1) * (v - y_min) / (y_max - y_min or 1)

    parts = [f'<svg viewBox="0 0 {W} {H}" class="ua-chart" preserveAspectRatio="xMidYMid meet">']
    for v in y_ticks:
        y = sy(v)
        parts.append(f'<line class="grid" x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}"/>')
        parts.append(f'<text class="tick" x="{x0-8}" y="{y+4:.1f}" text-anchor="end">{_esc(_fmt(v))}</text>')

    # x ticks: accept dict list or plain labels (downsample plain to ~6)
    if x_labels and isinstance(x_labels[0], dict):
        xt = x_labels
    else:
        m = len(x_labels)
        idxs = sorted(set([round(k * (m - 1) / 5) for k in range(6)])) if m > 1 else [0]
        xt = [{"i": i, "label": x_labels[i]} for i in idxs]
    for t in xt:
        parts.append(f'<text class="tick" x="{sx(t["i"]):.1f}" y="{y0+20}" text-anchor="middle">{_esc(str(t["label"]))}</text>')

    if y_title:
        cy = H / 2
        parts.append(f'<text class="atitle" x="14" y="{cy}" text-anchor="middle" transform="rotate(-90 14 {cy})">{_esc(y_title)}</text>')
    parts.append(f'<line class="axis" x1="{x0}" y1="{y1}" x2="{x0}" y2="{y0}"/>')
    parts.append(f'<line class="axis" x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}"/>')
    if ref is not None:
        yr = sy(ref)
        parts.append(f'<line class="refline" x1="{x0}" y1="{yr:.1f}" x2="{x1}" y2="{yr:.1f}"/>')

    d = "M" + " L".join(f"{sx(i):.1f},{sy(values[i]):.1f}" for i in range(n))
    area = d + f" L{sx(n-1):.1f},{y0} L{sx(0):.1f},{y0} Z"
    parts.append(f'<path class="area" d="{area}"/>')
    parts.append(f'<path class="cline" d="{d}"/>')
    parts.append(f'<circle class="dot" cx="{sx(n-1):.1f}" cy="{sy(values[-1]):.1f}" r="4"/>')
    parts.append("</svg>")
    return "".join(parts)


def bar_h(cats, vals, max_v=None, colors=None, unit="", W=560, H=250) -> str:
    """Horizontal bar chart with a value axis, category labels, gridlines, and
    per-bar value labels. `colors` is a list of CSS colors (one per bar) or a
    single color string; defaults to the royal accent."""
    vals = [float(v) for v in vals]
    n = len(cats)
    if max_v is None:
        max_v = max(vals) * 1.15 if vals else 1
    if colors is None:
        colors = ["var(--ua-royal-2,#8B7BF7)"] * n
    elif isinstance(colors, str):
        colors = [colors] * n
    pl, pr, pt, pb = 118, 44, 14, 34
    x0, x1, y0, y1 = pl, W - pr, H - pb, pt
    band = (y0 - y1) / max(1, n)
    bh = min(34, band * 0.56)

    def sx(v): return x0 + (x1 - x0) * v / (max_v or 1)

    parts = [f'<svg viewBox="0 0 {W} {H}" class="ua-chart" preserveAspectRatio="xMidYMid meet">']
    for k in range(5):
        v = max_v * k / 4.0
        x = sx(v)
        parts.append(f'<line class="grid" x1="{x:.1f}" y1="{y1}" x2="{x:.1f}" y2="{y0}"/>')
        lab = _fmt(round(v, 2)) + ("%" if unit == "%" else "")
        parts.append(f'<text class="tick" x="{x:.1f}" y="{y0+18}" text-anchor="middle">{_esc(lab)}</text>')
    parts.append(f'<line class="axis" x1="{x0}" y1="{y1}" x2="{x0}" y2="{y0}"/>')
    for i, c in enumerate(cats):
        cy = y1 + band * i + band / 2
        parts.append(f'<text class="tick cat" x="{x0-12}" y="{cy+4:.1f}" text-anchor="end">{_esc(str(c))}</text>')
        w = max(2.0, sx(vals[i]) - x0)
        parts.append(f'<rect x="{x0}" y="{cy-bh/2:.1f}" width="{w:.1f}" height="{bh:.1f}" rx="6" fill="{colors[i]}"/>')
        vlab = _fmt(vals[i]) + ("%" if unit == "%" else "")
        parts.append(f'<text class="vlabel" x="{sx(vals[i])+8:.1f}" y="{cy+4:.1f}">{_esc(vlab)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def bar_v(cats, vals, max_v=None, color=None, y_title="", x_title="", W=560, H=250) -> str:
    """Vertical bar chart / histogram with a labelled y-axis, x category axis,
    gridlines, and axis titles."""
    vals = [float(v) for v in vals]
    n = len(cats)
    if max_v is None:
        max_v = max(vals) * 1.12 if vals else 1
    if color is None:
        color = "var(--ua-royal,#6470F5)"
    pl, pr, pt, pb = 40, 14, 16, 40
    x0, x1, y0, y1 = pl, W - pr, H - pb, pt
    band = (x1 - x0) / max(1, n)
    bw = band * 0.62

    def sy(v): return y0 - (y0 - y1) * v / (max_v or 1)

    parts = [f'<svg viewBox="0 0 {W} {H}" class="ua-chart" preserveAspectRatio="xMidYMid meet">']
    for k in range(5):
        v = max_v * k / 4.0
        y = sy(v)
        parts.append(f'<line class="grid" x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}"/>')
        parts.append(f'<text class="tick" x="{x0-8}" y="{y+4:.1f}" text-anchor="end">{_esc(_fmt(round(v)))}</text>')
    parts.append(f'<line class="axis" x1="{x0}" y1="{y1}" x2="{x0}" y2="{y0}"/>')
    parts.append(f'<line class="axis" x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}"/>')
    if y_title:
        cy = H / 2
        parts.append(f'<text class="atitle" x="12" y="{cy}" text-anchor="middle" transform="rotate(-90 12 {cy})">{_esc(y_title)}</text>')
    if x_title:
        parts.append(f'<text class="atitle" x="{(x0+x1)/2:.1f}" y="{H-4}" text-anchor="middle">{_esc(x_title)}</text>')
    for i, c in enumerate(cats):
        cx = x0 + band * i + band / 2
        h = max(2.0, y0 - sy(vals[i]))
        parts.append(f'<rect x="{cx-bw/2:.1f}" y="{sy(vals[i]):.1f}" width="{bw:.1f}" height="{h:.1f}" rx="5" fill="{color}"/>')
        parts.append(f'<text class="tick" x="{cx:.1f}" y="{y0+18}" text-anchor="middle">{_esc(str(c))}</text>')
    parts.append("</svg>")
    return "".join(parts)
