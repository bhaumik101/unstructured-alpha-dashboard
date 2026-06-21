"""
Page 5 — Market Overview
Bloomberg-style snapshot with selectable time periods: 1D / 5D / 1M / 3M / 6M / YTD / 1Y.
"""

from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from utils.header import render_header, render_sidebar_base

st.set_page_config(page_title="Market Overview — UA", layout="wide")
render_header("Market Overview")
render_sidebar_base()

# CBOE treasury "yield index" tickers quote the yield × 10 (e.g. a 4.30% yield
# shows as 43.00). Must be divided by 10 to get the real percentage.
CBOE_YIELD_TICKERS = {"^TNX", "^TYX", "^FVX", "^IRX"}

# ── Period selector ────────────────────────────────────────────────────────────
PERIODS = ["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "ALL"]

# trading-day lookback for each period (None = YTD special case, 0 = ALL available)
PERIOD_DAYS = {"1D": 1, "5D": 5, "1M": 22, "3M": 66, "6M": 132, "YTD": None, "1Y": 252, "ALL": 0}
# chart calendar-day window for the performance line chart
PERIOD_CHART_DAYS = {"1D": 2, "5D": 7, "1M": 35, "3M": 100, "6M": 190, "YTD": None, "1Y": 370, "ALL": 0}

period_sel = st.radio(
    "Time period",
    PERIODS,
    index=2,          # default 1M
    horizontal=True,
    label_visibility="collapsed",
    key="overview_period",
)
st.markdown("---")


# ── Data fetching ──────────────────────────────────────────────────────────────
def _pct_change(close: pd.Series, period: str) -> float | None:
    """Return % change for the selected period using daily close data."""
    try:
        n = PERIOD_DAYS[period]
        last = float(close.iloc[-1])

        if n is None:           # YTD: from Jan 1 of current year
            yr_start = pd.Timestamp(datetime.now().year, 1, 1, tz=close.index.tz)
            ytd = close[close.index >= yr_start]
            if len(ytd) < 2:
                # Fall back to first available trading day of the year
                yr_start_naive = pd.Timestamp(datetime.now().year, 1, 1)
                ytd = close[close.index.normalize() >= yr_start_naive]
            if len(ytd) < 1:
                return None
            start = float(ytd.iloc[0])
        elif n == 0:            # ALL: from first available data point
            start = float(close.iloc[0])
        else:
            idx = max(0, len(close) - n - 1)
            start = float(close.iloc[idx])

        return (last - start) / start * 100 if start and start != 0 else None
    except Exception:
        return None


@st.cache_data(ttl=900, show_spinner=False)
def get_quote(ticker: str, _v: int = 5) -> dict:
    """Fetch full available daily history and pre-compute returns for all periods."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="max", interval="1d")
        if hist.empty:
            # Fallback ladder for tickers that reject "max"
            for fallback_period in ("5y", "2y", "1y", "6mo"):
                hist = t.history(period=fallback_period, interval="1d")
                if not hist.empty:
                    break
        if hist.empty:
            return {}
        close = hist["Close"].dropna()
        if len(close) < 5:
            return {}

        # CBOE yield-index tickers (^TNX, ^IRX, ^FVX, ^TYX) quote yield × 10
        if ticker in CBOE_YIELD_TICKERS:
            close = close / 10.0

        last = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else last
        if not (all(pd.notna([last, prev])) and prev != 0):
            return {}

        chg_1d_abs = last - prev

        # Pre-compute all period returns
        returns = {}
        for p in PERIODS:
            returns[p] = _pct_change(close, p)

        return {
            "last":      last,
            "chg_1d":    chg_1d_abs,
            "returns":   returns,        # dict of period -> pct_change or None
            "series":    close,
        }
    except Exception:
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def get_batch_quotes(tickers: list, _v: int = 5) -> dict:
    return {t: get_quote(t) for t in tickers}


def get_return(q: dict, period: str) -> float | None:
    """Safe accessor for a period return from a quote dict."""
    if not q:
        return None
    return q.get("returns", {}).get(period)


def period_label(period: str) -> str:
    labels = {"1D": "Today", "5D": "5-Day", "1M": "1-Month",
               "3M": "3-Month", "6M": "6-Month", "YTD": "YTD", "1Y": "1-Year"}
    return labels.get(period, period)


def stat_card(label: str, price: str, chg_abs: str, chg_pct: float | None) -> str:
    if chg_pct is None:
        cls, arrow, change_str = "flat", "●", "—"
    else:
        cls   = "pos" if chg_pct > 0 else ("neg" if chg_pct < 0 else "flat")
        arrow = "▲" if chg_pct > 0 else ("▼" if chg_pct < 0 else "●")
        change_str = f"{chg_abs}  ({chg_pct:+.2f}%)"
    return f"""
    <div class="stat-box">
        <div class="stat-label">{label}</div>
        <div class="stat-value">{price}</div>
        <div class="stat-change {cls}">{arrow} {change_str}</div>
    </div>
    """


def mini_sparkline(series: pd.Series, color: str, period: str) -> go.Figure:
    # Trim to the right window
    n = PERIOD_DAYS.get(period, 22)
    if period == "YTD":
        yr_start = pd.Timestamp(datetime.now().year, 1, 1, tz=series.index.tz)
        spark = series[series.index >= yr_start]
        if len(spark) < 2:
            spark = series.iloc[-252:]
    elif n == 0:               # ALL — full series
        spark = series
    else:
        n = n or 252
        spark = series.iloc[-max(n + 5, 5):]
    fig = go.Figure(go.Scatter(
        x=spark.index, y=spark.values,
        mode="lines", line=dict(color=color, width=1.5),
        fill="tozeroy", fillcolor="rgba(28,43,74,0.09)",
        hovertemplate="%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(
        height=55, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig


# ── Section 1: Major Indices ───────────────────────────────────────────────────
st.markdown('<div class="section-header">MAJOR INDICES</div>', unsafe_allow_html=True)

INDICES = {
    "S&P 500":          "SPY",
    "Nasdaq 100":       "QQQ",
    "Dow Jones":        "DIA",
    "Russell 2000":     "IWM",
    "Volatility (VIX)": "^VIX",
}

with st.spinner("Loading market data…"):
    idx_data = get_batch_quotes(list(INDICES.values()))

idx_cols = st.columns(len(INDICES))
for col, (name, ticker) in zip(idx_cols, INDICES.items()):
    q = idx_data.get(ticker, {})
    if q:
        chg_pct = get_return(q, period_sel)
        color = "#1B5E20" if (chg_pct or 0) > 0 else ("#7B1010" if (chg_pct or 0) < 0 else "#8B7355")
        # For 1D show absolute change; otherwise just show % change
        if period_sel == "1D":
            chg_abs_str = f"{q['chg_1d']:+.2f}"
        else:
            chg_abs_str = f"{period_label(period_sel)}"
        col.markdown(stat_card(name, f"{q['last']:,.2f}", chg_abs_str, chg_pct), unsafe_allow_html=True)
        if "series" in q and len(q["series"]) >= 3:
            col.plotly_chart(
                mini_sparkline(q["series"], color, period_sel),
                use_container_width=True,
                config={"displayModeBar": False},
            )
    else:
        col.markdown(
            f'<div class="stat-box"><div class="stat-label">{name}</div>'
            f'<div class="stat-value">—</div><div class="stat-change flat">No data</div></div>',
            unsafe_allow_html=True,
        )

st.markdown("")

# ── Section 2: Sector Performance ─────────────────────────────────────────────
st.markdown(
    f'<div class="section-header">SECTOR PERFORMANCE — {period_label(period_sel)}</div>',
    unsafe_allow_html=True,
)

SECTORS = {
    "Technology":     "XLK",
    "Energy":         "XLE",
    "Financials":     "XLF",
    "Industrials":    "XLI",
    "Materials":      "XLB",
    "Utilities":      "XLU",
    "Healthcare":     "XLV",
    "Consumer Disc.": "XLY",
    "Real Estate":    "XLRE",
    "Comm. Services": "XLC",
    "Staples":        "XLP",
}

with st.spinner("Loading sector data…"):
    sect_data = get_batch_quotes(list(SECTORS.values()))

names, changes, colors, texts = [], [], [], []
for name, ticker in SECTORS.items():
    q = sect_data.get(ticker, {})
    chg = get_return(q, period_sel) or 0.0
    names.append(name)
    changes.append(round(chg, 2))
    colors.append("#1B5E20" if chg > 0 else "#7B1010")
    texts.append(f"{chg:+.2f}%")

fig_sectors = go.Figure(go.Bar(
    x=changes, y=names, orientation="h",
    marker_color=colors,
    text=texts, textposition="outside",
    textfont=dict(color="#1A1612", size=11),
    hovertemplate="%{y}: %{x:+.2f}%<extra></extra>",
))
fig_sectors.update_layout(
    height=320, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
    xaxis=dict(showgrid=True, gridcolor="#E8E0CE", zeroline=True, zerolinecolor="#1C2B4A",
               zerolinewidth=1.5, ticksuffix="%", tickfont=dict(color="#6B6560")),
    yaxis=dict(tickfont=dict(color="#1A1612")),
    margin=dict(l=0, r=60, t=10, b=0),
)
st.plotly_chart(fig_sectors, use_container_width=True)

# ── Section 3: Rates & Fixed Income + Commodities ─────────────────────────────
st.divider()
left_col, right_col = st.columns(2)

with left_col:
    st.markdown('<div class="section-header">RATES & FIXED INCOME</div>', unsafe_allow_html=True)

    RATES = {
        "10-Year Treasury":    "^TNX",
        "3-Month T-Bill":      "^IRX",
        "TLT (Long Bond ETF)": "TLT",
        "HYG (High Yield)":    "HYG",
        "Investment Grade":    "LQD",
    }
    with st.spinner("Loading rates…"):
        rate_data = get_batch_quotes(list(RATES.values()))

    def fmt_chg(val):
        return f"{val:+.2f}%" if val is not None else "—"

    rate_rows = []
    for name, ticker in RATES.items():
        q = rate_data.get(ticker, {})
        if q:
            rate_rows.append({
                "Instrument":            name,
                "Last":                  f"{q['last']:.2f}",
                "1D":                    fmt_chg(get_return(q, "1D")),
                "5D":                    fmt_chg(get_return(q, "5D")),
                "1M":                    fmt_chg(get_return(q, "1M")),
                "3M":                    fmt_chg(get_return(q, "3M")),
                "YTD":                   fmt_chg(get_return(q, "YTD")),
                "1Y":                    fmt_chg(get_return(q, "1Y")),
            })

    if rate_rows:
        rate_df = pd.DataFrame(rate_rows)
        # Highlight the selected period column
        st.dataframe(
            rate_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                period_sel: st.column_config.TextColumn(f"▶ {period_sel}", width="small"),
            },
        )
    else:
        st.info("Rate data unavailable.")

    # Yield curve spread (live) — 10Y minus 3M, the spread the NY Fed's own
    # recession-probability model uses (more reliable than 10Y-2Y for this purpose)
    tnx = rate_data.get("^TNX", {})
    irx = rate_data.get("^IRX", {})
    if tnx and irx:
        spread = tnx["last"] - irx["last"]
        sc = "#1B5E20" if spread > 0 else "#7B1010"
        sl = "Normal (positive)" if spread > 0 else "Inverted (recession signal)"
        st.markdown(f"""
        <div style="background:#F0EBE1;border-radius:6px;padding:12px 16px;
                    border-left:4px solid {sc};border:1px solid #D4C9B0;
                    margin-top:10px;font-family:Georgia,serif;">
            <div style="font-size:0.72rem;color:#8B7355;letter-spacing:0.06em;">10Y–3M YIELD CURVE SPREAD</div>
            <div style="font-size:1.6rem;font-weight:700;color:{sc};">{spread:+.2f}%</div>
            <div style="font-size:0.82rem;color:#6B6560;">{sl}</div>
        </div>""", unsafe_allow_html=True)

with right_col:
    st.markdown('<div class="section-header">COMMODITIES & CURRENCIES</div>', unsafe_allow_html=True)

    COMMODITIES = {
        "Gold":            "GLD",
        "Silver":          "SLV",
        "WTI Crude Oil":   "USO",
        "Copper":          "CPER",
        "Natural Gas":     "UNG",
        "US Dollar Index": "DX-Y.NYB",
        "Bitcoin":         "BTC-USD",
    }
    with st.spinner("Loading commodities…"):
        comm_data = get_batch_quotes(list(COMMODITIES.values()))

    comm_rows = []
    for name, ticker in COMMODITIES.items():
        q = comm_data.get(ticker, {})
        if q:
            comm_rows.append({
                "Asset":  name,
                "Last":   f"{q['last']:.2f}",
                "1D":     fmt_chg(get_return(q, "1D")),
                "5D":     fmt_chg(get_return(q, "5D")),
                "1M":     fmt_chg(get_return(q, "1M")),
                "3M":     fmt_chg(get_return(q, "3M")),
                "YTD":    fmt_chg(get_return(q, "YTD")),
                "1Y":     fmt_chg(get_return(q, "1Y")),
            })

    if comm_rows:
        comm_df = pd.DataFrame(comm_rows)
        st.dataframe(
            comm_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                period_sel: st.column_config.TextColumn(f"▶ {period_sel}", width="small"),
            },
        )
    else:
        st.info("Commodity data unavailable.")

# ── Section 4: Performance Chart ──────────────────────────────────────────────
st.divider()
st.markdown(
    f'<div class="section-header">PERFORMANCE CHART — {period_label(period_sel)}</div>',
    unsafe_allow_html=True,
)

PERF_TICKERS = {"S&P 500": "SPY", "Nasdaq 100": "QQQ", "Russell 2000": "IWM", "Gold": "GLD"}
PERF_COLORS  = ["#1C2B4A", "#B8860B", "#1B5E20", "#7B1010"]

@st.cache_data(ttl=3600, show_spinner=False)
def get_normalized_perf(tickers: list, _v: int = 3) -> pd.DataFrame:
    frames = {}
    for t in tickers:
        try:
            hist = yf.Ticker(t).history(period="max", interval="1d")
            if hist.empty:
                for fallback_period in ("5y", "2y", "1y"):
                    hist = yf.Ticker(t).history(period=fallback_period, interval="1d")
                    if not hist.empty:
                        break
            if not hist.empty:
                close = hist["Close"].dropna()
                if len(close) > 1:
                    frames[t] = (close / close.iloc[0] - 1) * 100
        except Exception:
            pass
    return pd.DataFrame(frames) if frames else pd.DataFrame()

with st.spinner("Building chart…"):
    perf_df = get_normalized_perf(list(PERF_TICKERS.values()))

if not perf_df.empty:
    # Trim to selected period window
    chart_days = PERIOD_CHART_DAYS.get(period_sel)
    if chart_days is None:           # YTD
        yr_start = pd.Timestamp(datetime.now().year, 1, 1, tz=perf_df.index.tz)
        perf_window = perf_df[perf_df.index >= yr_start]
    elif chart_days == 0:            # ALL — full series
        perf_window = perf_df
    else:
        perf_window = perf_df.iloc[-min(chart_days, len(perf_df)):]

    # Re-normalize so the selected window starts at 0%
    if not perf_window.empty:
        perf_norm = perf_window.copy()
        for col in perf_norm.columns:
            s = perf_norm[col].dropna()
            if len(s) > 0:
                perf_norm[col] = perf_norm[col] - s.iloc[0]
    else:
        perf_norm = perf_window

    fig_perf = go.Figure()
    for (label, ticker), color in zip(PERF_TICKERS.items(), PERF_COLORS):
        if ticker in perf_norm.columns:
            s = perf_norm[ticker].dropna()
            if not s.empty:
                fig_perf.add_trace(go.Scatter(
                    x=s.index, y=s.values,
                    name=label, mode="lines",
                    line=dict(color=color, width=2),
                    hovertemplate=f"{label}: %{{y:+.1f}}%<extra></extra>",
                ))
    fig_perf.add_hline(y=0, line=dict(color="#8B7355", width=1, dash="dot"))
    fig_perf.update_layout(
        height=300, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
        xaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560")),
        yaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560"),
                   ticksuffix="%", title=f"Return ({period_label(period_sel)})"),
        legend=dict(font=dict(color="#1A1612", size=11), bgcolor="rgba(250,247,240,0.8)",
                    orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=0, r=0, t=30, b=0),
    )
    st.plotly_chart(fig_perf, use_container_width=True)
else:
    st.info("Performance chart unavailable — yfinance data not loading.")

# ── Section 5: Signal Snapshot ─────────────────────────────────────────────────
st.divider()
st.markdown('<div class="section-header">SIGNAL SNAPSHOT</div>', unsafe_allow_html=True)
st.caption("Key market signals computed from live yfinance data. Full alternative data analysis on Signal Dashboard.")

STATUS_COLOR = {"bullish": "#1B5E20", "bearish": "#7B1010", "neutral": "#8B7355", "no_data": "#9E9E8E"}
STATUS_SYM   = {"bullish": "▲", "bearish": "▼", "neutral": "●", "no_data": "—"}

def signal_card(label: str, status: str, detail: str, context: str = "") -> str:
    color = STATUS_COLOR.get(status, "#8B7355")
    sym   = STATUS_SYM.get(status, "●")
    ctx_html = (f'<div style="font-size:0.68rem;color:#6B6560;margin-top:2px;">{context}</div>'
                if context else "")
    return f"""
    <div style="background:#F0EBE1;border-radius:6px;padding:14px 10px;text-align:center;
                border:1px solid #D4C9B0;border-top:3px solid {color};font-family:Georgia,serif;">
        <div style="font-size:0.68rem;color:#8B7355;text-transform:uppercase;
                    letter-spacing:0.06em;line-height:1.3;">{label}</div>
        <div style="font-size:1.5rem;font-weight:700;color:{color};margin:6px 0 2px;">{sym}</div>
        <div style="font-size:0.82rem;font-weight:600;color:{color};">{status.replace("_"," ").capitalize()}</div>
        <div style="font-size:0.80rem;color:#4A4440;margin-top:4px;font-weight:600;">{detail}</div>
        {ctx_html}
    </div>"""

snap_signals = []

# 1. VIX
vix_q = idx_data.get("^VIX", {})
if vix_q:
    v      = vix_q["last"]
    vix_1d = get_return(vix_q, "1D") or 0
    vstatus = "bullish" if v < 15 else ("bearish" if v > 25 or (v > 20 and vix_1d > 5) else "neutral")
    snap_signals.append(("VIX — Fear Gauge", vstatus, f"{v:.2f}",
                          "< 15 = Calm  |  > 25 = Stress  |  > 40 = Crisis"))
else:
    snap_signals.append(("VIX — Fear Gauge", "no_data", "—", "Data unavailable"))

# 2. Yield Curve
tnx_q = rate_data.get("^TNX", {})
irx_q = rate_data.get("^IRX", {})
if tnx_q and irx_q:
    spread = tnx_q["last"] - irx_q["last"]
    ycs = "bullish" if spread > 0.75 else ("bearish" if spread < -0.10 else "neutral")
    snap_signals.append(("Yield Curve (10Y−3M)", ycs, f"{spread:+.2f}%",
                          f"10Y {tnx_q['last']:.2f}% − 3M {irx_q['last']:.2f}%"))
elif tnx_q:
    snap_signals.append(("Yield Curve (10Y−3M)", "no_data",
                          f"10Y: {tnx_q['last']:.2f}%", "3M data unavailable"))
else:
    snap_signals.append(("Yield Curve (10Y−3M)", "no_data", "—", "Rate data unavailable"))

# 3. HY Credit (HYG ETF)
hyg_q = rate_data.get("HYG", {})
if hyg_q:
    hyg_sel = get_return(hyg_q, period_sel) or 0
    hyg_1m  = get_return(hyg_q, "1M") or 0
    hyg_1y  = get_return(hyg_q, "1Y") or 0
    hys = "bullish" if hyg_1m > 1.5 else ("bearish" if hyg_1m < -1.5 else "neutral")
    snap_signals.append(("HY Credit (HYG ETF)", hys, f"${hyg_q['last']:.2f}",
                          f"{period_label(period_sel)}: {hyg_sel:+.1f}%  |  1Y: {hyg_1y:+.1f}%"))
else:
    snap_signals.append(("HY Credit (HYG ETF)", "no_data", "—", "Data unavailable"))

# 4. 10-Year Yield Trend
if tnx_q:
    tnx_sel = get_return(tnx_q, period_sel) or 0
    tnx_1m  = get_return(tnx_q, "1M") or 0
    tnx_1y  = get_return(tnx_q, "1Y") or 0
    ts = "bullish" if tnx_1m < -5 else ("bearish" if tnx_1m > 8 else "neutral")
    snap_signals.append(("10-Year Yield Trend", ts, f"{tnx_q['last']:.2f}%",
                          f"{period_label(period_sel)}: {tnx_sel:+.1f}%  |  1Y: {tnx_1y:+.1f}%"))
else:
    snap_signals.append(("10-Year Yield Trend", "no_data", "—", "Data unavailable"))

# 5. Risk Appetite (SPY vs GLD)
spy_q = idx_data.get("SPY", {})
gld_q = comm_data.get("GLD", {})
if spy_q and gld_q:
    spy_sel = get_return(spy_q, period_sel) or 0
    gld_sel = get_return(gld_q, period_sel) or 0
    diff    = spy_sel - gld_sel
    ras = "bullish" if diff > 3 else ("bearish" if diff < -3 else "neutral")
    snap_signals.append(("Risk Appetite (SPY/GLD)", ras, f"Diff: {diff:+.1f}%",
                          f"SPY {spy_sel:+.1f}% vs Gold {gld_sel:+.1f}% ({period_label(period_sel)})"))
else:
    snap_signals.append(("Risk Appetite (SPY/GLD)", "no_data", "—", "Data unavailable"))

snap_cols = st.columns(len(snap_signals))
for col, (label, status, detail, context) in zip(snap_cols, snap_signals):
    col.markdown(signal_card(label, status, detail, context), unsafe_allow_html=True)

# Breadth bar
bull_n = sum(1 for _, s, _, _ in snap_signals if s == "bullish")
bear_n = sum(1 for _, s, _, _ in snap_signals if s == "bearish")
neut_n = sum(1 for _, s, _, _ in snap_signals if s == "neutral")
total  = bull_n + bear_n + neut_n
if total > 0:
    pct    = bull_n / total * 100
    bc     = "#1B5E20" if pct >= 60 else ("#7B1010" if pct <= 30 else "#8B7355")
    blabel = "Risk-On Environment" if pct >= 60 else ("Risk-Off Environment" if pct <= 30 else "Mixed Signals")
    st.markdown(f"""
    <div style="margin-top:14px;padding:10px 16px;background:#F0EBE1;border-radius:6px;
                border:1px solid #D4C9B0;border-left:4px solid {bc};font-family:Georgia,serif;">
        <span style="font-size:0.72rem;color:#8B7355;text-transform:uppercase;letter-spacing:0.06em;">
            MARKET BREADTH — </span>
        <span style="font-size:0.85rem;font-weight:700;color:{bc};">{blabel}</span>
        <span style="font-size:0.80rem;color:#6B6560;margin-left:12px;">
            {bull_n} Bullish · {neut_n} Neutral · {bear_n} Bearish
        </span>
    </div>""", unsafe_allow_html=True)

st.caption(
    f"Signals from live yfinance data · Period shown: {period_label(period_sel)} · "
    f"Last updated: {datetime.now().strftime('%H:%M')} · "
    "Add a FRED API key in Setup for full alternative data signals."
)

# ─────────────────────────────────────────────────────────────────────────────
# MACRO DATA — migrated from the standalone Macro Monitor page (now retired;
# this content didn't need its own page when Market Overview already covers
# markets — keeping macro context here instead of forcing a second page click)
# ─────────────────────────────────────────────────────────────────────────────
from utils.fetchers import fetch_fred, is_synthetic, _get_fred_key
from utils.header import render_synthetic_data_banner

MACRO_END   = datetime.now().strftime("%Y-%m-%d")
MACRO_START = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y-%m-%d")


def _light_chart(fig: go.Figure, height: int = 280, title: str = "") -> go.Figure:
    fig.update_layout(
        height=height,
        title=dict(text=title, font=dict(color="#1C2B4A", size=13, family="Georgia"), x=0),
        paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
        xaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560")),
        yaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560")),
        legend=dict(font=dict(color="#1A1612", size=10), bgcolor="rgba(250,247,240,0.8)"),
        margin=dict(l=0, r=0, t=36, b=0),
    )
    return fig


def _status_chip(value: float, thresholds: tuple, labels: tuple, inverse: bool = False) -> str:
    lo, hi = thresholds
    if inverse:
        status = "bull" if value < lo else ("bear" if value > hi else "neutral")
    else:
        status = "bull" if value > hi else ("bear" if value < lo else "neutral")
    colors = {"bull": "#1B5E20", "bear": "#7B1010", "neutral": "#8B7355"}
    syms   = {"bull": "▲", "bear": "▼", "neutral": "●"}
    label  = labels[0] if status == "bull" else (labels[1] if status == "bear" else labels[2])
    c, s = colors[status], syms[status]
    return (f'<span style="background:rgba(0,0,0,0.06);color:{c};border:1px solid {c};'
            f'border-radius:4px;padding:2px 8px;font-size:0.78rem;font-weight:700;">{s} {label}</span>')


@st.cache_data(ttl=14400, show_spinner=False)
def _get_fred_cached(series_id: str, start: str, end: str, api_key: str = "") -> pd.Series:
    """
    api_key is threaded through explicitly (not read from session_state
    inside this function) so it participates in the cache key — see the
    detailed comment on fetch_fred() in utils/fetchers.py for why: this is
    a server-wide cache shared across every concurrent user, and without the
    key as part of the cache key, one user's key (or lack of one) could
    silently leak into what another user sees for the same series/range.
    """
    try:
        return fetch_fred(series_id, start, end, api_key=api_key)
    except Exception:
        return pd.Series(dtype=float)


st.divider()

_fred_key = _get_fred_key()

# NOTE: was "NAPM" — removed from FRED in 2016 (same dead series fixed in
# utils/config.py's ism_pmi signal earlier; this page had its own separate
# hardcoded copy that the earlier fix didn't touch). Replaced with the same
# Philly Fed Manufacturing Index used there, verified live against FRED.
_macro_series_ids = ["TRUCKD11", "GACDFSA066MSFRBPHI", "DGORDER", "IC4WSA", "JTSLDR", "RAILFRTINTERMODAL",
                     "UMCSENT", "RSXFS", "CPIUFDSL", "T10Y2Y"]
_macro_fetched = {sid: _get_fred_cached(sid, MACRO_START, MACRO_END, api_key=_fred_key) for sid in _macro_series_ids}
render_synthetic_data_banner(
    sum(1 for s in _macro_fetched.values() if is_synthetic(s)),
    len(_macro_fetched),
)

st.markdown('<div class="section-header">GROWTH INDICATORS</div>', unsafe_allow_html=True)
st.caption("Real published economic data — not live prices. Updates as slowly as the government releases it.")

g1, g2, g3 = st.columns(3)

with g1:
    ata = _macro_fetched["TRUCKD11"]
    if not ata.empty:
        last_v = float(ata.iloc[-1])
        prev_v = float(ata.iloc[-5]) if len(ata) > 5 else last_v
        chg    = (last_v - prev_v) / abs(prev_v) * 100 if prev_v else 0
        chip   = _status_chip(chg, (-2, 2), ("Expanding", "Contracting", "Flat"))
        fig = go.Figure(go.Scatter(
            x=ata.index, y=ata.values, mode="lines", line=dict(color="#1C2B4A", width=1.8),
            fill="tozeroy", fillcolor="rgba(28,43,74,0.09)",
        ))
        st.plotly_chart(_light_chart(fig, 200, "ATA Trucking Index"), use_container_width=True)
        st.markdown(f"Latest: **{last_v:,.1f}** &nbsp; 4-week change: {chg:+.1f}% &nbsp; {chip}", unsafe_allow_html=True)
    else:
        st.info("Trucking data unavailable. Add FRED API key.")

with g2:
    ism = _macro_fetched["GACDFSA066MSFRBPHI"]
    if not ism.empty:
        last_v = float(ism.iloc[-1])
        chip   = _status_chip(last_v, (47, 53), ("Expanding (>50)", "Contracting (<50)", "Near 50"))
        fig = go.Figure(go.Scatter(x=ism.index, y=ism.values, mode="lines", line=dict(color="#B8860B", width=1.8)))
        fig.add_hline(y=50, line=dict(color="#8B7355", dash="dot", width=1.5))
        st.plotly_chart(_light_chart(fig, 200, "ISM Manufacturing PMI"), use_container_width=True)
        st.markdown(f"Latest: **{last_v:.1f}** &nbsp; {chip}", unsafe_allow_html=True)
    else:
        st.info("ISM PMI unavailable. Add FRED API key.")

with g3:
    dgo = _macro_fetched["DGORDER"]
    if not dgo.empty:
        last_v = float(dgo.iloc[-1])
        prev_v = float(dgo.iloc[-2]) if len(dgo) > 1 else last_v
        mom    = (last_v - prev_v) / abs(prev_v) * 100 if prev_v else 0
        chip   = _status_chip(mom, (-1, 1), ("Growing", "Declining", "Flat"))
        fig = go.Figure(go.Bar(x=dgo.index, y=dgo.values,
                                marker_color=["#1B5E20" if v > 0 else "#7B1010" for v in dgo.values]))
        st.plotly_chart(_light_chart(fig, 200, "Durable Goods Orders (MoM %)"), use_container_width=True)
        st.markdown(f"Latest: **{last_v:+.2f}%** &nbsp; {chip}", unsafe_allow_html=True)
    else:
        st.info("Durable Goods unavailable. Add FRED API key.")

st.markdown('<div class="section-header">LABOR MARKET</div>', unsafe_allow_html=True)

l1, l2, l3 = st.columns(3)

with l1:
    ic = _macro_fetched["IC4WSA"]
    if not ic.empty:
        last_v = float(ic.iloc[-1])
        chip   = _status_chip(last_v, (220000, 280000), ("Healthy (<220K)", "Elevated (>280K)", "Normal"), inverse=True)
        fig = go.Figure(go.Scatter(x=ic.index, y=ic.values, mode="lines", line=dict(color="#7B1010", width=1.8)))
        st.plotly_chart(_light_chart(fig, 200, "Initial Jobless Claims (4-Week Avg)"), use_container_width=True)
        st.markdown(f"Latest: **{last_v:,.0f}** claims &nbsp; {chip}", unsafe_allow_html=True)
    else:
        st.info("Jobless claims unavailable. Add FRED API key.")

with l2:
    jolts_ld = _macro_fetched["JTSLDR"]
    if not jolts_ld.empty:
        last_v = float(jolts_ld.iloc[-1])
        chip   = _status_chip(last_v, (1.0, 2.5), ("High demand (>2.5)", "Low demand (<1.0)", "Normal"))
        fig = go.Figure(go.Scatter(x=jolts_ld.index, y=jolts_ld.values, mode="lines", line=dict(color="#1B5E20", width=1.8)))
        st.plotly_chart(_light_chart(fig, 200, "JOLTS — Layoffs & Discharges Rate"), use_container_width=True)
        st.markdown(f"Latest: **{last_v:.2f}%** &nbsp; {chip}", unsafe_allow_html=True)
    else:
        st.info("JOLTS data unavailable. Add FRED API key.")

with l3:
    rail = _macro_fetched["RAILFRTINTERMODAL"]
    if not rail.empty:
        last_v = float(rail.iloc[-1])
        mean_v = float(rail.mean())
        chip   = _status_chip(last_v - mean_v, (-5000, 5000), ("Above avg", "Below avg", "Near avg"))
        fig = go.Figure(go.Scatter(x=rail.index, y=rail.values, mode="lines", line=dict(color="#1C2B4A", width=1.8)))
        fig.add_hline(y=mean_v, line=dict(color="#B8860B", dash="dot", width=1))
        st.plotly_chart(_light_chart(fig, 200, "Rail Intermodal Traffic"), use_container_width=True)
        st.markdown(f"Latest: **{last_v:,.0f}** units &nbsp; {chip}", unsafe_allow_html=True)
    else:
        st.info("Rail freight data unavailable. Add FRED API key.")

st.markdown('<div class="section-header">CONSUMER & INFLATION</div>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)

with c1:
    umcs = _macro_fetched["UMCSENT"]
    if not umcs.empty:
        last_v = float(umcs.iloc[-1])
        mean_v = float(umcs.mean())
        chip   = _status_chip(last_v - mean_v, (-5, 5), ("Above avg", "Below avg", "Near avg"))
        fig = go.Figure(go.Scatter(x=umcs.index, y=umcs.values, mode="lines", line=dict(color="#B8860B", width=1.8)))
        fig.add_hline(y=mean_v, line=dict(color="#1C2B4A", dash="dot", width=1))
        st.plotly_chart(_light_chart(fig, 200, "U. Michigan Consumer Sentiment"), use_container_width=True)
        st.markdown(f"Latest: **{last_v:.1f}** &nbsp; {chip}", unsafe_allow_html=True)
    else:
        st.info("Consumer sentiment unavailable.")

with c2:
    rsxfs = _macro_fetched["RSXFS"]
    if not rsxfs.empty:
        last_v = float(rsxfs.iloc[-1])
        prev_v = float(rsxfs.iloc[-2]) if len(rsxfs) > 1 else last_v
        mom    = (last_v - prev_v) / abs(prev_v) * 100 if prev_v else 0
        chip   = _status_chip(mom, (-0.5, 0.5), ("Growing", "Declining", "Flat"))
        fig = go.Figure(go.Bar(x=rsxfs.index, y=rsxfs.values,
                                marker_color=["#1B5E20" if v > 0 else "#7B1010" for v in rsxfs.values]))
        st.plotly_chart(_light_chart(fig, 200, "Retail Sales ex-Autos (MoM %)"), use_container_width=True)
        st.markdown(f"Latest: **{last_v:+.2f}%** &nbsp; {chip}", unsafe_allow_html=True)
    else:
        st.info("Retail sales unavailable.")

with c3:
    cpi_food = _macro_fetched["CPIUFDSL"]
    if not cpi_food.empty:
        last_v = float(cpi_food.iloc[-1])
        yoy = ((last_v / float(cpi_food.iloc[-13])) - 1) * 100 if len(cpi_food) > 13 else float("nan")
        chip = _status_chip(yoy if not pd.isna(yoy) else 0, (2, 5), ("Stable (<2%)", "High (>5%)", "Moderate"), inverse=True)
        fig = go.Figure(go.Scatter(x=cpi_food.index, y=cpi_food.values, mode="lines", line=dict(color="#7B1010", width=1.8)))
        st.plotly_chart(_light_chart(fig, 200, "CPI — Food at Home (Index Level)"), use_container_width=True)
        st.markdown(f"Index: **{last_v:.1f}** &nbsp; YoY: **{yoy:+.1f}%** &nbsp; {chip}", unsafe_allow_html=True)
    else:
        st.info("CPI food data unavailable.")

st.markdown('<div class="section-header">OFFICIAL YIELD CURVE (FRED)</div>', unsafe_allow_html=True)
st.caption("FRED's own 10Y-2Y series — complements the live 10Y-3M spread computed from yfinance above.")

yc = _macro_fetched["T10Y2Y"]
if not yc.empty:
    fig_yc = go.Figure(go.Scatter(
        x=yc.index, y=yc.values, name="10Y–2Y Spread",
        line=dict(color="#1C2B4A", width=2), fill="tozeroy", fillcolor="rgba(28,43,74,0.09)",
    ))
    for i in range(1, len(yc)):
        if yc.iloc[i] < 0:
            fig_yc.add_vrect(x0=yc.index[i - 1], x1=yc.index[i], fillcolor="rgba(123,16,16,0.09)", line_width=0)
    fig_yc.add_hline(y=0, line=dict(color="#7B1010", width=1.5))
    st.plotly_chart(_light_chart(fig_yc, 240, "10Y–2Y Treasury Yield Curve Spread"), use_container_width=True)
    last_spread = float(yc.iloc[-1])
    st.markdown(
        f"Current spread: **{last_spread:+.2f}%** &nbsp; "
        + ("Curve is **inverted** — historical recession signal." if last_spread < 0 else "Curve is **positive** — normal.")
    )
else:
    st.info("Yield curve data unavailable. Add FRED API key.")

# ── Economic Calendar ─────────────────────────────────────────────────────────
st.markdown('<div class="section-header">KEY ECONOMIC RELEASES — SCHEDULE</div>', unsafe_allow_html=True)
st.caption("Approximate release schedule for the major data points tracked by this dashboard.")

CALENDAR = [
    ("Monthly", "1st business day", "ISM Manufacturing PMI", "NAPM via FRED"),
    ("Weekly",  "Every Thursday",   "Initial Jobless Claims", "FRED IC4WSA"),
    ("Monthly", "~15th",            "Retail Sales",          "FRED RSXFS"),
    ("Monthly", "~17th",            "Industrial Production", "FRED INDPRO"),
    ("Monthly", "~23rd",            "Durable Goods Orders",  "FRED DGORDER"),
    ("Monthly", "Last Friday",      "Consumer Sentiment",    "UMich UMCSENT"),
    ("Monthly", "~20th",            "ATA Trucking Tonnage",  "FRED TRUCKD11"),
    ("Weekly",  "Every Friday",     "AAR Rail Traffic",      "FRED RAILFRTINTERMODAL"),
    ("Monthly", "~10th",            "CPI (all items)",       "BLS / FRED"),
    ("Weekly",  "Every Friday",     "COT Report",            "CFTC"),
    ("Monthly", "~3rd week",        "Housing Starts",        "FRED HOUST"),
    ("Daily",   "Continuous",       "10Y–2Y Spread",         "FRED T10Y2Y"),
    ("Daily",   "Continuous",       "VIX / HY Spread",       "CBOE / ICE BofA"),
]

cal_rows = ""
for freq, timing, release, source in CALENDAR:
    freq_color = {"Monthly": "#1C2B4A", "Weekly": "#B8860B", "Daily": "#1B5E20"}.get(freq, "#8B7355")
    cal_rows += f"""
    <tr>
        <td><span style="color:{freq_color};font-weight:700;font-size:0.78rem;">{freq}</span></td>
        <td style="color:#6B6560;font-size:0.82rem;">{timing}</td>
        <td style="font-weight:600;color:#1A1612;">{release}</td>
        <td style="color:#8B7355;font-size:0.80rem;">{source}</td>
    </tr>
    """

st.markdown(f"""
<table class="ua-data-table">
<thead><tr><th>Frequency</th><th>Timing</th><th>Release</th><th>Source</th></tr></thead>
<tbody>{cal_rows}</tbody>
</table>
""", unsafe_allow_html=True)
