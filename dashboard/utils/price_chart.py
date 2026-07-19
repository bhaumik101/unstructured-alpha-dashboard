"""Zoom-aware price chart.

Replaces the previous Deep Dive chart, which had four problems:

1. **The period labels were wrong.** `_PERIOD_DAYS` held calendar-day counts
   but they were applied as row counts (`price_series.iloc[-370:]`). Daily bars
   are trading days, ~252/year, so "1Y" rendered ~17.6 months, "6M" rendered
   ~9 months, and so on — every window overstated by 45-60%. Windows here are
   sliced by calendar date off the index, so the label and the axis agree.

2. **Two competing period controls.** A Streamlit radio trimmed the data and a
   Plotly `rangeselector` then re-zoomed inside that trim, so the two could
   disagree and the heading described only the first. There is now one control.

3. **The y-axis never followed the zoom.** Plotly holds the y range fixed when
   you zoom x, so zooming into a month of a multi-year chart left a flat
   squiggle across the middle. Zoom now rescales price to the visible window.

4. **The price line was splined.** `shape="spline", smoothing=0.3` invents
   values between closes and overshoots local extrema — on a price series that
   is a misstatement, not a style choice. Lines are linear.

The zoom behaviour needs a `plotly_relayout` listener, which `st.plotly_chart`
does not expose, so the chart renders as a self-contained HTML component. If
that fails for any reason the caller can fall back to a static figure; see
`render()`'s docstring.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime

from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

# ── Windows ───────────────────────────────────────────────────────────────────
# Each entry is a pandas DateOffset argument applied to the LAST date in the
# series. "YTD" and "ALL" are special-cased. These are calendar spans; the
# number of bars they yield depends on the trading calendar, which is the whole
# point — a month is a month regardless of how many sessions it contained.
PERIODS: dict[str, Any] = {
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "6M": pd.DateOffset(months=6),
    "YTD": "ytd",
    "1Y": pd.DateOffset(years=1),
    "2Y": pd.DateOffset(years=2),
    "5Y": pd.DateOffset(years=5),
    "ALL": "all",
}

DEFAULT_PERIOD = "1Y"

# Moving averages are only meaningful once the window is long enough to contain
# a reasonable fraction of their lookback, and a 200-day MA on a one-month view
# is a flat line that tells the user nothing.
MA_MIN_WINDOW_DAYS = {50: 60, 200: 240}


def window_start(last: pd.Timestamp, period: str) -> pd.Timestamp | None:
    """First date included by `period`, or None to mean "no lower bound"."""
    spec = PERIODS.get(period)
    if spec is None:
        raise KeyError(f"unknown period {period!r}; expected one of {sorted(PERIODS)}")
    if spec == "all":
        return None
    if spec == "ytd":
        return pd.Timestamp(year=last.year, month=1, day=1, tz=last.tz)
    return last - spec


def slice_period(series: pd.Series, period: str) -> pd.Series:
    """Trim `series` to `period` by calendar date.

    The bug this replaces used positional slicing, which conflates trading days
    with calendar days. Slicing on the index cannot drift.
    """
    if series.empty:
        return series
    start = window_start(series.index[-1], period)
    if start is None:
        return series
    out = series[series.index >= start]
    # A window that lands entirely inside a gap (a halted or newly listed name)
    # should degrade to the whole series rather than render an empty chart.
    return out if len(out) >= 2 else series


def window_stats(series: pd.Series) -> dict[str, float | None]:
    """Summary of the *visible* window, not of a fixed 52-week lookback.

    The old stat cards always reported 52-week high/low and YTD return no matter
    what the chart showed, so the numbers under the chart described a different
    period than the chart itself.
    """
    if series is None or len(series) == 0:
        return {"first": None, "last": None, "change": None, "change_pct": None,
                "high": None, "low": None, "n": 0}
    first = float(series.iloc[0])
    last = float(series.iloc[-1])
    change = last - first
    return {
        "first": first,
        "last": last,
        "change": change,
        "change_pct": (change / first * 100.0) if first else None,
        "high": float(series.max()),
        "low": float(series.min()),
        "n": int(len(series)),
    }


def _iso(idx: pd.Index) -> list[str]:
    return [pd.Timestamp(t).strftime("%Y-%m-%d") for t in idx]


def _clean(values: Iterable[Any]) -> list[float | None]:
    """NaN -> None so it survives JSON and plots as a gap, not as 0."""
    out: list[float | None] = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(None if f != f else f)  # NaN != NaN
    return out


@dataclass
class ChartPayload:
    """Everything the browser needs, already trimmed and JSON-safe."""

    ticker: str
    dates: list[str]
    close: list[float | None]
    ma50: list[float | None] = field(default_factory=list)
    ma200: list[float | None] = field(default_factory=list)
    score_dates: list[str] = field(default_factory=list)
    score_values: list[float | None] = field(default_factory=list)
    earnings: list[dict[str, Any]] = field(default_factory=list)
    period: str = DEFAULT_PERIOD
    currency: str = "$"

    def to_json(self) -> str:
        return json.dumps(self.__dict__, allow_nan=False)


def build_payload(
    ticker: str,
    price_series: pd.Series,
    period: str = DEFAULT_PERIOD,
    score_history: Sequence[Mapping[str, Any]] | None = None,
    earnings: Sequence[Mapping[str, Any]] | None = None,
    currency: str = "$",
) -> ChartPayload:
    """Assemble the payload for one ticker/period.

    Moving averages are computed on the FULL series then trimmed to the window,
    so the first visible MA point is a true 50/200-day average rather than an
    average of whatever happened to be in view.
    """
    view = slice_period(price_series, period)
    if view.empty:
        return ChartPayload(ticker=ticker, dates=[], close=[], period=period,
                            currency=currency)

    span_days = (view.index[-1] - view.index[0]).days or 1

    ma_series: dict[int, pd.Series] = {}
    for length, min_days in MA_MIN_WINDOW_DAYS.items():
        if len(price_series) >= length and span_days >= min_days:
            full = price_series.rolling(length).mean()
            ma_series[length] = full.reindex(view.index)

    score_dates: list[str] = []
    score_values: list[float | None] = []
    if score_history:
        pairs = []
        for row in score_history:
            try:
                ts = pd.Timestamp(row["snapshot_date"])
                pairs.append((ts, float(row["score"])))
            except (KeyError, TypeError, ValueError):
                continue
        pairs.sort()
        # Only carry score history that actually overlaps the window. Drawing a
        # week of dots on a two-year axis reads as a broken series; the old
        # chart also fell back to a flat dotted line at today's score across the
        # whole window, which invited reading a constant where none was measured.
        lo = view.index[0]
        inside = [(t, v) for t, v in pairs if t >= lo]
        if len(inside) >= 2:
            score_dates = [t.strftime("%Y-%m-%d") for t, _ in inside]
            score_values = [v for _, v in inside]

    marks: list[dict[str, Any]] = []
    lo, hi = view.index[0], view.index[-1]
    for e in earnings or []:
        try:
            ts = pd.Timestamp(e["date"])
        except (KeyError, TypeError, ValueError):
            continue
        if ts < lo or ts > hi + pd.Timedelta(days=90):
            continue
        surprise = e.get("surprise_pct")
        reported = bool(e.get("reported"))
        if not reported:
            colour, label = "#F59E0B", "Upcoming"
        elif surprise is None:
            colour, label = "#6B7FBF", "Reported"
        elif surprise >= 0:
            colour, label = "#00D566", f"Beat +{surprise:.0f}%"
        else:
            colour, label = "#FF4444", f"Miss {surprise:.0f}%"
        marks.append({"date": ts.strftime("%Y-%m-%d"), "color": colour, "label": label})

    return ChartPayload(
        ticker=ticker,
        dates=_iso(view.index),
        close=_clean(view.values),
        ma50=_clean(ma_series[50].values) if 50 in ma_series else [],
        ma200=_clean(ma_series[200].values) if 200 in ma_series else [],
        score_dates=score_dates,
        score_values=score_values,
        earnings=marks,
        period=period,
        currency=currency,
    )


# ── Browser side ──────────────────────────────────────────────────────────────

# Substituted with plain str.replace rather than str.format/f-strings/Template:
# the body is JavaScript and CSS, so it is dense with both braces and dollar
# signs, and every brace-or-dollar-aware formatter needs the whole template
# escaped. Distinctive @@TOKEN@@ markers cannot collide with valid JS.
_TEMPLATE = r"""
<div id="ua-wrap" style="font-family:Inter,system-ui,sans-serif;color:#E8EEFF;">
  <div id="ua-readout" style="display:flex;gap:26px;align-items:baseline;flex-wrap:wrap;
       padding:2px 4px 12px 4px;min-height:44px;"></div>
  <div id="ua-chart" style="width:100%;height:@@HEIGHT@@px;"></div>
  <div id="ua-fallback" style="display:none;padding:18px;border-radius:8px;
       background:rgba(255,68,68,0.08);border:1px solid rgba(255,68,68,0.25);
       font-size:0.82rem;color:#FFB4B4;">
    Chart library failed to load. The price data is unaffected — reload the page
    to try again.
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.27.0/plotly.min.js"></script>
<script>
(function () {
  var D = @@PAYLOAD@@;
  var gd = document.getElementById('ua-chart');
  var readout = document.getElementById('ua-readout');

  if (typeof Plotly === 'undefined') {
    document.getElementById('ua-fallback').style.display = 'block';
    gd.style.display = 'none';
    return;
  }
  if (!D.dates.length) {
    readout.innerHTML = '<span style="color:#8892AA;">No price history available.</span>';
    return;
  }

  var CUR = D.currency || '$';
  var GREEN = '#00D566', RED = '#FF4444', CYAN = '#00C8E0';

  // ── Readout ────────────────────────────────────────────────────────────────
  // Recomputed from the VISIBLE slice on every zoom, so the numbers above the
  // chart always describe the window the user is actually looking at.
  function visibleIdx(r0, r1) {
    var lo = 0, hi = D.dates.length - 1;
    if (r0 != null && r1 != null) {
      var a = new Date(r0).getTime(), b = new Date(r1).getTime();
      lo = -1;
      for (var i = 0; i < D.dates.length; i++) {
        var t = new Date(D.dates[i]).getTime();
        if (t >= a && lo === -1) lo = i;
        if (t <= b) hi = i;
      }
      if (lo === -1) lo = 0;
      if (hi < lo) hi = lo;
    }
    return [lo, hi];
  }

  function fmt(v, dp) { 
    if (v == null || isNaN(v)) return '—';
    return CUR + v.toFixed(dp == null ? 2 : dp);
  }

  function stat(label, value, colour) {
    return '<div><div style="font-size:0.58rem;letter-spacing:0.11em;text-transform:uppercase;'
         + 'color:#6B7A95;font-weight:700;margin-bottom:2px;">' + label + '</div>'
         + '<div style="font-size:1.02rem;font-weight:800;color:' + (colour || '#E8EEFF') + ';">'
         + value + '</div></div>';
  }

  function drawReadout(lo, hi) {
    var vals = D.close.slice(lo, hi + 1).filter(function (v) { return v != null; });
    if (!vals.length) { readout.innerHTML = ''; return; }
    var first = vals[0], last = vals[vals.length - 1];
    var chg = last - first, pct = first ? (chg / first * 100) : 0;
    var col = chg >= 0 ? GREEN : RED;
    var hiV = Math.max.apply(null, vals), loV = Math.min.apply(null, vals);
    var d0 = D.dates[lo], d1 = D.dates[hi];
    var days = Math.round((new Date(d1) - new Date(d0)) / 86400000);
    var span = days >= 365 ? (days / 365).toFixed(1) + 'y'
             : days >= 31 ? Math.round(days / 30.44) + 'mo'
             : days + 'd';

    readout.innerHTML =
        stat(D.ticker + ' · last', fmt(last))
      + stat('Change · ' + span, (chg >= 0 ? '+' : '') + fmt(chg).replace(CUR + '-', '-' + CUR)
             + '  (' + (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%)', col)
      + stat('Window high', fmt(hiV))
      + stat('Window low', fmt(loV))
      + stat('Range', d0 + ' → ' + d1)
      + stat('Bars', String(hi - lo + 1));
  }

  // ── Traces ─────────────────────────────────────────────────────────────────
  // Linear shape, not spline: a spline between daily closes draws prices that
  // never traded and can overshoot the window high/low shown in the readout.
  var traces = [{
    x: D.dates, y: D.close, name: D.ticker, type: 'scatter', mode: 'lines',
    line: { color: CYAN, width: 2.2, shape: 'linear' },
    fill: 'tonexty', fillcolor: 'rgba(0,200,224,0.07)',
    hovertemplate: '<b>' + CUR + '%{y:.2f}</b><extra>' + D.ticker + '</extra>'
  }];
  if (D.ma50.length) traces.push({
    x: D.dates, y: D.ma50, name: '50-day MA', type: 'scatter', mode: 'lines',
    line: { color: '#7C3AED', width: 1.4 }, connectgaps: false,
    hovertemplate: CUR + '%{y:.2f}<extra>50-day MA</extra>'
  });
  if (D.ma200.length) traces.push({
    x: D.dates, y: D.ma200, name: '200-day MA', type: 'scatter', mode: 'lines',
    line: { color: '#FF6B6B', width: 1.4 }, connectgaps: false,
    hovertemplate: CUR + '%{y:.2f}<extra>200-day MA</extra>'
  });
  if (D.score_dates.length) traces.push({
    x: D.score_dates, y: D.score_values, name: 'Confluence Score',
    type: 'scatter', mode: 'lines', yaxis: 'y2',
    line: { color: '#F59E0B', width: 1.6, dash: 'dot' },
    hovertemplate: '%{y:.1f}<extra>Confluence Score</extra>'
  });

  // Earnings sit as small markers pinned under the plot rather than as
  // full-height dashed lines with text at the top edge, which collided with
  // each other and with the range buttons.
  var shapes = D.earnings.map(function (e) {
    return {
      type: 'line', xref: 'x', yref: 'paper', x0: e.date, x1: e.date,
      y0: 0, y1: 0.045,
      line: { color: e.color, width: 2 }
    };
  });

  var layout = {
    height: @@HEIGHT@@,
    paper_bgcolor: '#0B0D12', plot_bgcolor: '#0F1118',
    font: { family: 'Inter, sans-serif', size: 12, color: '#E8EEFF' },
    margin: { l: 58, r: @@RIGHT_MARGIN@@, t: 8, b: 40 },
    hovermode: 'x unified',
    hoverlabel: { bgcolor: '#151925', bordercolor: 'rgba(255,255,255,0.12)',
                  font: { color: '#E8EEFF', size: 12 } },
    dragmode: 'zoom',
    shapes: shapes,
    showlegend: true,
    legend: { orientation: 'h', y: -0.16, x: 0, font: { size: 11, color: '#B8C0D4' },
              bgcolor: 'rgba(0,0,0,0)' },
    xaxis: {
      type: 'date',
      showgrid: true, gridcolor: 'rgba(255,255,255,0.045)',
      tickfont: { color: '#8892AA', size: 11 },
      showspikes: true, spikemode: 'across', spikethickness: 1,
      spikecolor: 'rgba(255,255,255,0.28)', spikedash: 'solid',
      rangeslider: { visible: false }
    },
    yaxis: {
      title: { text: 'Price', font: { color: '#6B7A95', size: 11 } },
      showgrid: true, gridcolor: 'rgba(255,255,255,0.045)',
      tickfont: { color: '#8892AA', size: 11 },
      tickprefix: CUR, fixedrange: false, zeroline: false
    },
    yaxis2: {
      title: { text: 'Confluence', font: { color: '#F59E0B', size: 10 } },
      overlaying: 'y', side: 'right', range: [0, 100],
      showgrid: false, fixedrange: true,
      tickfont: { color: '#F59E0B', size: 10 },
      tickvals: [0, 35, 65, 100], ticktext: ['0', '35', '65', '100'],
      visible: @@SCORE_AXIS@@
    }
  };

  Plotly.newPlot(gd, traces, layout, {
    displaylogo: false, responsive: true, scrollZoom: true, doubleClick: 'reset',
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
    displayModeBar: 'hover'
  });

  // ── Zoom handling ──────────────────────────────────────────────────────────
  // Plotly leaves the y range alone when x changes, which is what made a
  // one-month zoom on a two-year chart render as a flat line. On every relayout
  // we recompute the price extent over the visible bars and refit y, then
  // refresh the readout so the printed numbers match the drawn window.
  var applying = false;

  function refit(r0, r1) {
    var bounds = visibleIdx(r0, r1);
    var lo = bounds[0], hi = bounds[1];
    var series = [D.close];
    if (D.ma50.length) series.push(D.ma50);
    if (D.ma200.length) series.push(D.ma200);

    var mn = Infinity, mx = -Infinity;
    series.forEach(function (arr) {
      for (var i = lo; i <= hi; i++) {
        var v = arr[i];
        if (v == null || isNaN(v)) continue;
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
    });
    drawReadout(lo, hi);
    if (!isFinite(mn) || !isFinite(mx)) return;

    // A flat window (mn === mx) would produce a zero-height axis.
    var pad = (mx - mn) * 0.08 || Math.max(mx * 0.02, 0.01);
    applying = true;
    Plotly.relayout(gd, { 'yaxis.range': [mn - pad, mx + pad] })
      .then(function () { applying = false; })
      .catch(function () { applying = false; });
  }

  gd.on('plotly_relayout', function (ev) {
    if (applying) return;
    if (ev['yaxis.range[0]'] !== undefined && ev['xaxis.range[0]'] === undefined
        && !ev['xaxis.autorange']) {
      // User dragged the y-axis itself; respect it and only redraw the readout.
      return;
    }
    if (ev['xaxis.autorange'] || ev.autosize) { refit(null, null); return; }
    if (ev['xaxis.range[0]'] !== undefined) {
      refit(ev['xaxis.range[0]'], ev['xaxis.range[1]']);
    }
  });

  refit(null, null);
})();
</script>
"""


def render(
    payload: ChartPayload,
    height: int = 420,
    st_module: Any = None,
) -> None:
    """Render the chart into Streamlit.

    Raises nothing on data problems — an empty payload renders an inline
    "no price history" message. Callers that need a guaranteed render if the
    Plotly CDN is unreachable should catch exceptions and fall back to their own
    static figure; the component itself shows an inline notice in that case
    rather than a blank box.
    """
    if st_module is None:  # pragma: no cover - import cost only in the app
        import streamlit as st_module  # type: ignore

    html = build_html(payload, height=height)
    # +130 covers the readout row above and the horizontal legend below, which
    # live outside the plot's own height.
    st_module.components.v1.html(html, height=height + 130, scrolling=False)


def build_html(payload: ChartPayload, height: int = 420) -> str:
    """Pure string build, separated from Streamlit so it can be unit-tested."""
    has_score = bool(payload.score_dates)
    subs = {
        "@@PAYLOAD@@": payload.to_json(),
        "@@HEIGHT@@": str(int(height)),
        "@@RIGHT_MARGIN@@": "58" if has_score else "18",
        "@@SCORE_AXIS@@": "true" if has_score else "false",
    }
    html = _TEMPLATE
    for token, value in subs.items():
        html = html.replace(token, value)

    leftover = [t for t in subs if t in html]
    assert not leftover, f"unsubstituted template tokens: {leftover}"
    return html
