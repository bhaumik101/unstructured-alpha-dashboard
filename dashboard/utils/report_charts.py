# utils/report_charts.py
# Unstructured Alpha — the report's charts, as plain SVG
#
# WHY THIS EXISTS
# ---------------
# The product says it shows "which economic forces a portfolio is exposed to,
# how those exposures are changing, and why they matter". The report answered
# the first part with numbers and the second with one before-and-after
# sentence per force. How an exposure has MOVED is a shape, and a shape is
# read faster as a picture than as a paragraph.
#
# Three charts, each carrying nothing the engine did not measure:
#
#   - how each sensitivity has moved: a rolling year, re-measured monthly,
#     with its 90% range shaded. The range is not decoration. A rolling line
#     drawn without it would make a year of noise look like a trend, which is
#     exactly the misreading this product exists to prevent.
#   - what each force itself did: the published series over the same weeks, so
#     a reader sees the push as well as the response.
#   - which holdings carry an exposure: a diverging bar per holding, because
#     "BND carries most of it and VTI works slightly against it" is a picture.
#
# WHY SVG AND NOT A CHART LIBRARY. These print (advisers print), render in the
# first paint with no JavaScript, inherit the light and dark themes through CSS
# variables, and weigh a few kilobytes. The exposure map on the same page is
# already built this way.
#
# Every chart has a role="img" and an aria-label that says in words what the
# picture shows, because a chart that only exists visually is not accessible.

from __future__ import annotations

import math
from datetime import datetime
from html import escape
from typing import Dict, List, Optional, Sequence, Tuple

FACTOR_COLORS = {"rates": "#3b7ddd", "inflation": "#e0664a", "dollar": "#1a9a70",
                 "oil": "#d99018", "credit": "#7c5ce0", "growth": "#1497b0"}

# How each published series is read. Rates, inflation expectations and credit
# spreads are percentages, so their change is in percentage points; the dollar
# is an index and oil is dollars a barrel, so their change is a percent.
_UNITS = {
    "rates": ("%", "pts"), "inflation": ("%", "pts"), "credit": ("%", "pts"),
    "dollar": ("", "pct"), "oil": ("$", "pct"),
}

CHART_CSS = """<style>
.uac-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin:6px 0 16px;}
.uac-panel{background:var(--uar-surface);border:1px solid var(--uar-line);border-radius:14px;
  padding:12px 14px 8px;box-shadow:0 18px 40px -34px var(--uar-shadow);}
.uac-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;}
.uac-title{font-weight:650;color:var(--uar-ink);font-size:var(--uar-t-body);}
.uac-now{font-weight:650;color:var(--uar-ink);font-size:var(--uar-t-body);white-space:nowrap;}
.uac-sub{color:var(--uar-ink-3);font-size:var(--uar-t-meta);margin-top:2px;}
.uac-svg{width:100%;height:auto;display:block;margin-top:6px;overflow:visible;}
.uac-axis{stroke:var(--uar-line);stroke-width:1;}
.uac-zero{stroke:var(--uar-ink-3);stroke-width:1;stroke-dasharray:3 3;opacity:.55;}
.uac-tick{fill:var(--uar-ink-3);font-size:var(--uar-t-meta);}
.uac-val{fill:var(--uar-ink-2);font-size:var(--uar-t-micro);font-weight:600;}
.uac-label{fill:var(--uar-ink);font-size:var(--uar-t-meta);font-weight:650;}
.uac-spark{background:var(--uar-surface);border:1px solid var(--uar-line);border-radius:12px;
  padding:10px 12px 6px;border-top:3px solid var(--uac-hue,var(--uar-accent));}
.uac-sparkgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:10px;margin:6px 0 14px;}
.uac-big{font-size:var(--uar-t-price);font-weight:750;letter-spacing:-0.02em;color:var(--uar-ink);
  line-height:1.1;margin-top:2px;}
.uac-delta{font-size:var(--uar-t-meta);font-weight:650;}
.uac-up{color:var(--uar-pos-ink);}
/* Text, so the text-safe amber: the mark colour #c26a0a is 3.9:1 on white. */
.uac-down{color:var(--uar-neg-ink);}
@media print{.uac-panel,.uac-spark{break-inside:avoid;box-shadow:none;}}
</style>"""


# ── small helpers ───────────────────────────────────────────────────────────

def _minus(text: str) -> str:
    return text.replace("-", "−")


def _sentence_case(text: str) -> str:
    """Upper-case the first letter and touch nothing else.

    str.capitalize() lowercases the rest of the string, which printed "the
    10-year treasury yield" and "the trade-weighted u.s. dollar" on the charts.
    """
    text = str(text or "")
    return text[:1].upper() + text[1:]


def _pct(x: float, digits: int = 2) -> str:
    if x is None or not math.isfinite(x):
        return "—"
    if round(x, digits) == 0:
        return f"{0:.{digits}f}%"
    return _minus(f"{x:+.{digits}f}%")


def _date(iso: str) -> str:
    try:
        d = datetime.strptime(str(iso)[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return str(iso or "")
    return f"{d:%b} {d.year}"


def _scale(lo: float, hi: float, top: float, bottom: float):
    """Value -> y, with a little headroom so a line never sits on the frame."""
    if hi - lo < 1e-9:
        hi, lo = hi + 1.0, lo - 1.0
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad

    def y(v: float) -> float:
        return bottom - (v - lo) / (hi - lo) * (bottom - top)

    return y, lo, hi


def _path(points: Sequence[Tuple[float, float]]) -> str:
    return " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(points))


# ── 1. how each sensitivity has moved ──────────────────────────────────────

DOT_LIMIT = 40


def rolling_panel_svg(key: str, label: str, points: List[dict]) -> str:
    """One force: the rolling sensitivity, its 90% range, and zero."""
    if len(points) < 3:
        return ""
    width, height = 280, 140
    left, right, top, bottom = 34, 6, 10, 114
    hue = FACTOR_COLORS.get(key, "#3b7ddd")

    lows = [p["low"] for p in points]
    highs = [p["high"] for p in points]
    y, lo, hi = _scale(min(min(lows), 0.0), max(max(highs), 0.0), top, bottom)
    n = len(points)

    def x(i: int) -> float:
        return left + i * (width - left - right) / (n - 1)

    band_top = [(x(i), y(p["high"])) for i, p in enumerate(points)]
    band_bottom = [(x(i), y(p["low"])) for i, p in reversed(list(enumerate(points)))]
    band = _path(band_top + band_bottom) + " Z"
    line = _path([(x(i), y(p["impact"])) for i, p in enumerate(points)])

    # Points are drawn by how well the reading stood up: filled where it was
    # clear, open where tentative, and not at all where it could be noise --
    # so a stretch of the line with no dots on it reads as what it is. Past
    # DOT_LIMIT points (years of history) dots would merge into a bar, so the
    # same three states become a strip under the line instead.
    long_line = n > DOT_LIMIT
    dots = []
    for i, p in enumerate(points if not long_line else ()):
        if p["evidence"] == "clear":
            dots.append(f'<circle cx="{x(i):.1f}" cy="{y(p["impact"]):.1f}" r="2.6" fill="{hue}"/>')
        elif p["evidence"] == "tentative":
            dots.append(f'<circle cx="{x(i):.1f}" cy="{y(p["impact"]):.1f}" r="2.6" '
                        f'fill="var(--uar-surface)" stroke="{hue}" stroke-width="1.4"/>')

    strip, x_labels = "", ""
    if long_line:
        step = (width - left - right) / (n - 1)
        # One bar per run of the same label, so the strip has no seams.
        cells, i = [], 0
        while i < n:
            j, ev = i, points[i]["evidence"]
            while j + 1 < n and points[j + 1]["evidence"] == ev:
                j += 1
            if ev in ("clear", "tentative"):
                x0 = max(left, x(i) - step / 2)
                x1 = min(width - right, x(j) + step / 2)
                cells.append(f'<rect x="{x0:.1f}" y="{bottom + 3}" width="{x1 - x0:.1f}" height="4" '
                             f'fill="{hue}" fill-opacity="{"1" if ev == "clear" else "0.45"}"/>')
            i = j + 1
        strip = f'<g class="uac-strip">{"".join(cells)}</g>'
        # A label at the first point of every other year: enough to find 2020
        # or 2022 without crowding a 240px axis.
        seen, labels = set(), []
        for i, p in enumerate(points):
            yr = str(p["end"])[:4]
            if yr in seen:
                continue
            seen.add(yr)
            if i > 0 and int(yr) % 2 == 0 and x(i) < width - right - 12:
                labels.append(f'<line class="uac-axis" x1="{x(i):.1f}" y1="{bottom}" x2="{x(i):.1f}" '
                              f'y2="{bottom + 2}"/><text class="uac-tick" x="{x(i):.1f}" '
                              f'y="{height - 4}" text-anchor="middle">{yr}</text>')
        x_labels = "".join(labels)

    zero_y = y(0.0)
    first, last = points[0], points[-1]
    n_clear = sum(p["evidence"] == "clear" for p in points)
    n_tent = sum(p["evidence"] == "tentative" for p in points)
    summary = (f"{label}: over the rolling year ending {_date(first['end'])} this portfolio "
               f"moved {_pct(first['impact'])} per standard move; by {_date(last['end'])} it was "
               f"{_pct(last['impact'])}. The shaded range is the 90% uncertainty at each point. "
               f"Clear in {n_clear} of {n} rolling years, tentative in {n_tent}.")
    return (
        f'<svg class="uac-svg" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(summary)}">'
        f'<line class="uac-axis" x1="{left}" y1="{bottom}" x2="{width - right}" y2="{bottom}"/>'
        f'<path d="{band}" fill="{hue}" fill-opacity="0.16" stroke="none"/>'
        f'<line class="uac-zero" x1="{left}" y1="{zero_y:.1f}" x2="{width - right}" y2="{zero_y:.1f}"/>'
        f'<path d="{line}" fill="none" stroke="{hue}" stroke-width="2.2" stroke-linejoin="round"/>'
        + "".join(dots) + strip +
        f'<text class="uac-tick" x="{left - 4}" y="{top + 8}" text-anchor="end">{escape(_pct(hi, 1))}</text>'
        f'<text class="uac-tick" x="{left - 4}" y="{zero_y + 3:.1f}" text-anchor="end">0</text>'
        f'<text class="uac-tick" x="{left - 4}" y="{bottom}" text-anchor="end">{escape(_pct(lo, 1))}</text>'
        + (x_labels if long_line else
           f'<text class="uac-tick" x="{left}" y="{height - 4}">{escape(_date(first["end"]))}</text>'
           f'<text class="uac-tick" x="{width - right}" y="{height - 4}" text-anchor="end">'
           f'{escape(_date(last["end"]))}</text>')
        + '</svg>')


def rolling_charts_html(report: dict, order: Sequence[str]) -> str:
    """Small multiples, one per force, in the report's own order."""
    rolling = report.get("rolling") or {}
    readings = (report.get("portfolio") or {}).get("readings") or {}
    panels = []
    for key in order:
        points = rolling.get(key)
        if not points or key not in readings:
            continue
        svg = rolling_panel_svg(key, readings[key]["label"], points)
        if not svg:
            continue
        last = points[-1]
        panels.append(
            f'<div class="uac-panel"><div class="uac-head">'
            f'<span class="uac-title">{escape(readings[key]["label"])}</span>'
            f'<span class="uac-now">{escape(_pct(last["impact"]))}</span></div>'
            f'<div class="uac-sub">{escape(_sentence_case(readings[key]["shock_phrase"]))}</div>'
            f'{svg}</div>')
    if not panels:
        return ""
    weeks = (report.get("method") or {}).get("rolling_weeks", 52)
    long_line = any(len(rolling.get(k) or []) > DOT_LIMIT for k in order)
    evidence = ("The strip under each line is solid where that year&#39;s reading cleared the same "
                "evidence bar as the headline reading, faint where it was tentative, and empty "
                "where it could not be told apart from zero. The line goes back as far as every "
                "holding has prices, up to ten years; the headline reading still uses the last "
                "three." if long_line else
                "Filled dots cleared the same evidence bar as the headline reading, open dots were "
                "tentative, and stretches with no dots could not be told apart from zero.")
    return (
        '<div class="uar">'
        f'<div class="uac-grid">{"".join(panels)}</div>'
        f'<div class="uar-sub">Each point is the sensitivity measured over the {weeks} weeks ending '
        f'that week, re-measured every month. The shaded band is its 90% range: where the band '
        f'crosses the dashed zero line, that year&#39;s reading could be noise. {evidence} This '
        f'shows how the relationship has moved; it does not show where it goes next.</div></div>')


# ── 2. what each force itself did ──────────────────────────────────────────

def _level(key: str, value: float) -> str:
    unit, _kind = _UNITS.get(key, ("", "pct"))
    if unit == "%":
        return f"{value:.2f}%"
    if unit == "$":
        return f"${value:,.2f}"
    return f"{value:,.1f}"


def _change(key: str, first: float, last: float) -> Tuple[str, float]:
    _unit, kind = _UNITS.get(key, ("", "pct"))
    if kind == "pts":
        diff = last - first
        return _minus(f"{diff:+.2f} pts"), diff
    if first == 0:
        return "—", 0.0
    pct = (last / first - 1) * 100
    return _minus(f"{pct:+.1f}%"), pct


def sparkline_svg(values: Sequence[float], hue: str, label: str) -> str:
    if len(values) < 2:
        return ""
    width, height = 160, 40
    y, _lo, _hi = _scale(min(values), max(values), 3, height - 3)
    n = len(values)
    pts = [(i * (width - 2) / (n - 1) + 1, y(v)) for i, v in enumerate(values)]
    area = _path(pts) + f" L{pts[-1][0]:.1f},{height} L{pts[0][0]:.1f},{height} Z"
    return (f'<svg class="uac-svg" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{escape(label)}" preserveAspectRatio="none">'
            f'<path d="{area}" fill="{hue}" fill-opacity="0.12"/>'
            f'<path d="{_path(pts)}" fill="none" stroke="{hue}" stroke-width="1.8"/>'
            f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.6" fill="{hue}"/></svg>')


def factor_paths_html(report: dict, order: Sequence[str]) -> str:
    """A strip of small cards: each force's level now, its move, its path."""
    paths = report.get("factor_paths") or {}
    readings = (report.get("portfolio") or {}).get("readings") or {}
    cards = []
    for key in order:
        path = paths.get(key)
        if not path or key not in readings:
            continue
        hue = FACTOR_COLORS.get(key, "#3b7ddd")
        change_text, change = _change(key, path["first"], path["last"])
        direction = "uac-up" if change > 0 else "uac-down" if change < 0 else ""
        label = readings[key]["label"]
        words = (f"{label} went from {_level(key, path['first'])} to {_level(key, path['last'])} "
                 f"between {_date(path['dates'][0])} and {_date(path['dates'][-1])}.")
        cards.append(
            f'<div class="uac-spark" style="--uac-hue:{hue}">'
            f'<div class="uac-title">{escape(label)}</div>'
            f'<div class="uac-big">{escape(_level(key, path["last"]))}</div>'
            f'<div class="uac-delta {direction}">{escape(change_text)} over the window</div>'
            f'{sparkline_svg(path["values"], hue, words)}</div>')
    if not cards:
        return ""
    return (
        '<div class="uar">'
        f'<div class="uac-sparkgrid">{"".join(cards)}</div>'
        '<div class="uar-sub">The published series themselves over the same weeks — what each '
        'force did, not what this portfolio did. Weekly closing values from FRED; gaps in a '
        'series are left as gaps.</div></div>')


# ── 3. which holdings carry an exposure ────────────────────────────────────

def contribution_bars_svg(report: dict, key: str) -> str:
    """Diverging bars: each holding's contribution to one force, largest first.

    Contributions add up to the portfolio's figure, so the bars are the
    portfolio's reading broken into its pieces. Holdings pulling the other way
    are drawn on the other side of zero rather than hidden, because an offset
    is often the most useful thing on the chart.
    """
    rows = (report.get("contributions") or {}).get(key) or []
    readings = (report.get("portfolio") or {}).get("readings") or {}
    if len(rows) < 2 or key not in readings:
        return ""
    rows = rows[:12]
    hue = FACTOR_COLORS.get(key, "#3b7ddd")
    width, row_h, top = 560, 26, 8
    label_w, value_w = 70, 70
    height = top + row_h * len(rows) + 8
    span = max(abs(r["contribution"]) for r in rows) or 1.0
    mid = label_w + (width - label_w - value_w) / 2
    half = (width - label_w - value_w) / 2 - 4

    bars = []
    for i, r in enumerate(rows):
        yy = top + i * row_h
        length = abs(r["contribution"]) / span * half
        x0 = mid if r["contribution"] >= 0 else mid - length
        faint = r["evidence"] not in ("clear", "tentative")
        bars.append(
            f'<text class="uac-label" x="{label_w - 8}" y="{yy + 17}" text-anchor="end">'
            f'{escape(r["ticker"])}</text>'
            f'<rect x="{x0:.1f}" y="{yy + 5}" width="{max(length, 1.5):.1f}" height="{row_h - 10}" '
            f'rx="3" fill="{hue}" fill-opacity="{0.28 if faint else 0.9}"/>'
            f'<text class="uac-val" x="{width - 4}" y="{yy + 17}" text-anchor="end">'
            f'{escape(_pct(r["contribution"]))}</text>')
    total = readings[key]["impact"]
    summary = (f"{readings[key]['label']}: the portfolio's {_pct(total)} split by holding. "
               + "; ".join(f"{r['ticker']} {_pct(r['contribution'])}" for r in rows) + ".")
    return (
        f'<svg class="uac-svg" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(summary)}">'
        f'<line class="uac-zero" x1="{mid:.1f}" y1="{top}" x2="{mid:.1f}" y2="{height - 6}"/>'
        + "".join(bars) + '</svg>'
        '<div class="uar-sub">Each bar is the holding&#39;s weight times its own sensitivity; '
        'together they add up to the portfolio&#39;s figure. Bars on the other side of the line '
        'work against the rest. Pale bars are holdings whose own reading could not be told '
        'apart from noise.</div>')
