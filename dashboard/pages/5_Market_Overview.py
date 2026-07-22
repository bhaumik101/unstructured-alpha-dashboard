"""
Page 5 — Market Overview
Bloomberg-style snapshot with selectable time periods: 1D / 5D / 1M / 3M / 6M / YTD / 1Y.

Layout: split into 2 sections via the shared sidebar section rail --
"Markets" (indices, sector performance, rates, commodities, the
performance chart, signal snapshot -- everything driven by the period
selector) and "Macro Indicators" (growth, labor, consumer/inflation,
yield curve, key releases -- period-independent reference data, migrated
from the retired standalone Macro Monitor page). This boundary already
existed in the code before this split -- the two halves share zero
helper functions or constants (verified directly, not assumed), so this
was a low-risk mechanical move, same reasoning and tooling as the
Ticker Deep Dive restructuring on the same day (see that page's
docstring for why lazy Python branching was chosen over st.tabs()).

Note: _render_live_index_quote (an st.fragment) lives inside the
"Markets" branch -- AppTest does not exercise fragment bodies at all
(see tests/conftest.py's documented blind spot), so this split doesn't
change what is or isn't covered by the automated suite for that fragment;
it still needs a live-browser check, the same as before this change.
"""

from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from utils.header import render_header, render_sidebar_base, render_page_header, render_footer
from utils.fetchers import fetch_live_quote
from utils.theme import source_badge, inject_premium_css, inject_skeleton_css, section_label, PLOTLY_CONFIG, PLOTLY_CONFIG_INTERACTIVE, style_timeseries_chart

st.set_page_config(page_title="Market Overview — UA", layout="wide")
render_header("Market Overview")
_overview_section = render_sidebar_base(
    page_title="Market Overview",
    sections=("Markets", "Macro Indicators"),
    section_key="overview_section",
)
inject_premium_css()
inject_skeleton_css()

render_page_header(
    "Market Overview",
    "Live snapshot of equities, rates, commodities, and macro regime indicators.",
    icon="",
)

st.divider()

section = _overview_section or "Markets"

if section == "Markets":
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
    st.markdown(section_label("MAJOR INDICES", color="#55A7D8", dot="#55A7D8"), unsafe_allow_html=True)

    INDICES = {
        "S&P 500":          "SPY",
        "Nasdaq 100":       "QQQ",
        "Dow Jones":        "DIA",
        "Russell 2000":     "IWM",
        "Volatility (VIX)": "^VIX",
    }

    with st.spinner("Loading market data…"):
        idx_data = get_batch_quotes(list(INDICES.values()))

    @st.fragment(run_every="60s")
    def _render_live_index_quote(ticker: str) -> None:
        """
        Auto-refreshes every 60s, independent of the rest of the page — only
        this small fragment re-runs on the timer, not the full script, so the
        period-aware historical fetch + sparkline above (get_batch_quotes,
        cached 15 min) doesn't re-fire every minute just to keep a live price
        ticking. Same fetch_live_quote() used on Ticker Deep Dive. Silently
        renders nothing if the live quote isn't available, since the stat card
        above already shows the period-based last price as a fallback.
        """
        q = fetch_live_quote(ticker)
        if q["price"] is not None:
            delta_str = f"{q['pct_change']:+.2f}%" if q["pct_change"] is not None else ""
            color = "#00D566" if (q["pct_change"] or 0) > 0 else ("#FF4444" if (q["pct_change"] or 0) < 0 else "#6B7FBF")
            st.markdown(
                f'<div style="font-size:0.72rem;color:#9E9E8E;margin-top:2px;">'
                f'LIVE: <span style="color:{color};font-weight:700;">{q["price"]:,.2f} {delta_str}</span>'
                f' &middot; updates every 60s</div>',
                unsafe_allow_html=True,
            )


    idx_cols = st.columns(len(INDICES))
    for col, (name, ticker) in zip(idx_cols, INDICES.items()):
        q = idx_data.get(ticker, {})
        if q:
            chg_pct = get_return(q, period_sel)
            color = "#00D566" if (chg_pct or 0) > 0 else ("#FF4444" if (chg_pct or 0) < 0 else "#6B7FBF")
            # For 1D show absolute change; otherwise just show % change
            if period_sel == "1D":
                chg_abs_str = f"{q['chg_1d']:+.2f}"
            else:
                chg_abs_str = f"{period_label(period_sel)}"
            col.markdown(stat_card(name, f"{q['last']:,.2f}", chg_abs_str, chg_pct), unsafe_allow_html=True)
            with col:
                _render_live_index_quote(ticker)
            if "series" in q and len(q["series"]) >= 3:
                col.plotly_chart(
                    mini_sparkline(q["series"], color, period_sel),
                    use_container_width=True,
                    config=PLOTLY_CONFIG,
                    theme=None,
                )
        else:
            col.markdown(
                f'<div class="stat-box"><div class="stat-label">{name}</div>'
                f'<div class="stat-value">—</div><div class="stat-change flat">No data</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("")

    # ── Section 2: Sector Performance ─────────────────────────────────────────────
    st.markdown(section_label(f"SECTOR PERFORMANCE — {period_label(period_sel)}", color="#8187F7", dot="#8187F7"), unsafe_allow_html=True)

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
        colors.append("#00D566" if chg > 0 else "#FF4444")
        texts.append(f"{chg:+.2f}%")

    fig_sectors = go.Figure(go.Bar(
        x=changes, y=names, orientation="h",
        marker_color=colors,
        text=texts, textposition="outside",
        textfont=dict(color="#E8EEFF", size=11),
        hovertemplate="%{y}: %{x:+.2f}%<extra></extra>",
    ))
    fig_sectors.update_layout(
        height=320, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", zeroline=True, zerolinecolor="rgba(255,255,255,0.12)",
                   zerolinewidth=1.5, ticksuffix="%", tickfont=dict(color="#8892AA")),
        yaxis=dict(tickfont=dict(color="#E8EEFF")),
        margin=dict(l=0, r=60, t=10, b=0),
    )
    st.plotly_chart(fig_sectors, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
    st.markdown(f"&nbsp; {source_badge('yfinance', 'Sector ETF returns')}", unsafe_allow_html=True)

    # ── Section 3: Rates & Fixed Income + Commodities ─────────────────────────────
    st.divider()
    left_col, right_col = st.columns(2)

    with left_col:
        st.html(section_label("Rates & Fixed Income", color="#F59E0B", dot="#F59E0B"))

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
                    period_sel: st.column_config.TextColumn(period_sel, width="small"),
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
            sc = "#00D566" if spread > 0 else "#FF4444"
            sl = "Normal (positive)" if spread > 0 else "Inverted (recession signal)"
            st.html(f"""
            <div class="ua-spotlight ua-kpi-animate" style="--ua-spotlight-accent:{sc};margin-top:10px;padding:14px 18px;">
                <div style="font-size:0.60rem;font-weight:700;color:#8892AA;text-transform:uppercase;letter-spacing:0.10em;margin-bottom:4px;">10Y–3M Yield Curve Spread</div>
                <div style="font-size:2.0rem;font-weight:900;color:{sc};text-shadow:0 0 24px {sc}45;">{spread:+.2f}%</div>
                <div style="font-size:0.78rem;color:#8892AA;margin-top:2px;">{sl}</div>
            </div>""")

    with right_col:
        st.html(section_label("Commodities & Currencies", color="#00D566", dot="#00D566"))

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
                    period_sel: st.column_config.TextColumn(period_sel, width="small"),
                },
            )
        else:
            st.info("Commodity data unavailable.")

    # ── Section 4: Performance Chart ──────────────────────────────────────────────
    st.divider()
    st.html(section_label(f"Performance Chart — {period_label(period_sel)}", color="#7C3AED", dot="#7C3AED"))

    PERF_TICKERS = {"S&P 500": "SPY", "Nasdaq 100": "QQQ", "Russell 2000": "IWM", "Gold": "GLD"}
    PERF_COLORS  = ["#7C3AED", "#F59E0B", "#00D566", "#FF4444"]

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
        fig_perf.add_hline(y=0, line=dict(color="#6B7FBF", width=1, dash="dot"))
        fig_perf.update_layout(
            legend=dict(font=dict(color="#E8EEFF", size=11), bgcolor="rgba(18,21,30,0.90)",
                        orientation="h", yanchor="bottom", y=1.02),
        )
        fig_perf.update_yaxes(ticksuffix="%", title_text=f"Return ({period_label(period_sel)})")
        fig_perf = style_timeseries_chart(fig_perf, height=300, y_title=f"Return ({period_label(period_sel)})")
        st.plotly_chart(fig_perf, use_container_width=True, config=PLOTLY_CONFIG_INTERACTIVE, theme=None)
        st.markdown(f"&nbsp; {source_badge('yfinance', 'Daily OHLCV')}", unsafe_allow_html=True)
    else:
        st.info("Performance chart unavailable — yfinance data not loading.")

    # ── Section 5: Signal Snapshot ─────────────────────────────────────────────────
    st.divider()
    st.html(section_label("Signal Snapshot", color="#00D566", dot="#00D566"))
    st.caption("Key market signals computed from live yfinance data. Full alternative data analysis on Signal Dashboard.")

    STATUS_COLOR = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#6B7FBF", "no_data": "#9E9E8E"}
    STATUS_SYM   = {"bullish": "▲", "bearish": "▼", "neutral": "●", "no_data": "—"}

    def signal_card(label: str, status: str, detail: str, context: str = "") -> str:
        color = STATUS_COLOR.get(status, "#6B7FBF")
        sym   = STATUS_SYM.get(status, "●")
        ctx_html = (f'<div style="font-size:0.66rem;color:#8892AA;margin-top:4px;line-height:1.4;">{context}</div>'
                    if context else "")
        return (
            f'<div class="ua-spotlight ua-kpi-animate" style="--ua-spotlight-accent:{color};'
            f'text-align:center;padding:16px 10px 14px;">'
            f'<div style="font-size:0.60rem;font-weight:700;color:#8892AA;text-transform:uppercase;'
            f'letter-spacing:0.10em;line-height:1.4;margin-bottom:6px;">{label}</div>'
            f'<div style="font-size:1.6rem;font-weight:900;color:{color};'
            f'text-shadow:0 0 20px {color}40;margin-bottom:2px;">{sym}</div>'
            f'<div style="font-size:0.78rem;font-weight:700;color:{color};margin-bottom:4px;">{status.replace("_"," ").capitalize()}</div>'
            f'<div style="font-size:0.76rem;color:#B8C0D4;font-weight:600;">{detail}</div>'
            f'{ctx_html}'
            f'</div>'
        )

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
        bc     = "#00D566" if pct >= 60 else ("#FF4444" if pct <= 30 else "#6B7FBF")
        blabel = "Risk-On Environment" if pct >= 60 else ("Risk-Off Environment" if pct <= 30 else "Mixed Signals")
        st.html(f"""
        <div class="ua-spotlight" style="--ua-spotlight-accent:{bc};margin-top:14px;padding:12px 18px;display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
            <span style="font-size:0.60rem;font-weight:700;color:#8892AA;text-transform:uppercase;letter-spacing:0.10em;">Market Breadth</span>
            <span style="font-size:0.90rem;font-weight:800;color:{bc};text-shadow:0 0 16px {bc}40;">{blabel}</span>
            <span style="font-size:0.78rem;color:#8892AA;margin-left:4px;">
                <span style="color:#00D566;">▲ {bull_n}</span> · <span style="color:#6B7FBF;">● {neut_n}</span> · <span style="color:#FF4444;">▼ {bear_n}</span>
            </span>
        </div>""")

    st.caption(
        f"Signals from live yfinance data · Period shown: {period_label(period_sel)} · "
        f"Last updated: {datetime.now().strftime('%H:%M')} · "
        "Add a FRED API key in Setup for full alternative data signals."
    )


elif section == "Macro Indicators":
    # ─────────────────────────────────────────────────────────────────────────────
    # MACRO DATA — migrated from the standalone Macro Monitor page (now retired;
    # this content didn't need its own page when Market Overview already covers
    # markets — keeping macro context here instead of forcing a second page click)
    # ─────────────────────────────────────────────────────────────────────────────
    from utils.fetchers import fetch_fred, is_unavailable, _get_fred_key
    from utils.header import render_data_unavailable_banner

    MACRO_END   = datetime.now().strftime("%Y-%m-%d")
    MACRO_START = (datetime.now() - timedelta(days=3 * 365)).strftime("%Y-%m-%d")


    def _light_chart(fig: go.Figure, height: int = 280, title: str = "") -> go.Figure:
        fig.update_layout(
            height=height,
            title=dict(text=title, font=dict(color="#7C3AED", size=13, family="Inter, sans-serif"), x=0),
            paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
            xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(color="#8892AA")),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(color="#8892AA")),
            legend=dict(font=dict(color="#E8EEFF", size=10), bgcolor="rgba(18,21,30,0.90)"),
            margin=dict(l=0, r=0, t=36, b=0),
        )
        return fig


    def _status_chip(value: float, thresholds: tuple, labels: tuple, inverse: bool = False) -> str:
        lo, hi = thresholds
        if inverse:
            status = "bull" if value < lo else ("bear" if value > hi else "neutral")
        else:
            status = "bull" if value > hi else ("bear" if value < lo else "neutral")
        colors = {"bull": "#00D566", "bear": "#FF4444", "neutral": "#6B7FBF"}
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
    render_data_unavailable_banner(
        sum(1 for s in _macro_fetched.values() if is_unavailable(s)),
        len(_macro_fetched),
    )

    st.markdown(section_label("GROWTH INDICATORS", color="#D6A34A", dot="#D6A34A"), unsafe_allow_html=True)
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
                x=ata.index, y=ata.values, mode="lines", line=dict(color="#7C3AED", width=1.8),
                fill="tozeroy", fillcolor="rgba(28,43,74,0.09)",
            ))
            st.plotly_chart(_light_chart(fig, 200, "ATA Trucking Index"), use_container_width=True, config=PLOTLY_CONFIG, theme=None)
            st.markdown(f"Latest: **{last_v:,.1f}** &nbsp; 4-week change: {chg:+.1f}% &nbsp; {chip} &nbsp; {source_badge('fred','TRUCKD11')}", unsafe_allow_html=True)
        else:
            st.info("Trucking data unavailable. Add FRED API key.")

    with g2:
        ism = _macro_fetched["GACDFSA066MSFRBPHI"]
        if not ism.empty:
            last_v = float(ism.iloc[-1])
            chip   = _status_chip(last_v, (47, 53), ("Expanding (>50)", "Contracting (<50)", "Near 50"))
            fig = go.Figure(go.Scatter(x=ism.index, y=ism.values, mode="lines", line=dict(color="#F59E0B", width=1.8)))
            fig.add_hline(y=50, line=dict(color="#6B7FBF", dash="dot", width=1.5))
            st.plotly_chart(_light_chart(fig, 200, "ISM Manufacturing PMI"), use_container_width=True, config=PLOTLY_CONFIG, theme=None)
            st.markdown(f"Latest: **{last_v:.1f}** &nbsp; {chip} &nbsp; {source_badge('fred','GACDFSA066MSFRBPHI','Philly Fed')}", unsafe_allow_html=True)
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
                                    marker_color=["#00D566" if v > 0 else "#FF4444" for v in dgo.values]))
            st.plotly_chart(_light_chart(fig, 200, "Durable Goods Orders (MoM %)"), use_container_width=True, config=PLOTLY_CONFIG, theme=None)
            st.markdown(f"Latest: **{last_v:+.2f}%** &nbsp; {chip} &nbsp; {source_badge('fred','DGORDER')}", unsafe_allow_html=True)
        else:
            st.info("Durable Goods unavailable. Add FRED API key.")

    st.markdown(section_label("LABOR MARKET", color="#55A7D8", dot="#55A7D8"), unsafe_allow_html=True)

    l1, l2, l3 = st.columns(3)

    with l1:
        ic = _macro_fetched["IC4WSA"]
        if not ic.empty:
            last_v = float(ic.iloc[-1])
            chip   = _status_chip(last_v, (220000, 280000), ("Healthy (<220K)", "Elevated (>280K)", "Normal"), inverse=True)
            fig = go.Figure(go.Scatter(x=ic.index, y=ic.values, mode="lines", line=dict(color="#FF4444", width=1.8)))
            st.plotly_chart(_light_chart(fig, 200, "Initial Jobless Claims (4-Week Avg)"), use_container_width=True, config=PLOTLY_CONFIG, theme=None)
            st.markdown(f"Latest: **{last_v:,.0f}** claims &nbsp; {chip} &nbsp; {source_badge('fred','IC4WSA')}", unsafe_allow_html=True)
        else:
            st.info("Jobless claims unavailable. Add FRED API key.")

    with l2:
        jolts_ld = _macro_fetched["JTSLDR"]
        if not jolts_ld.empty:
            last_v = float(jolts_ld.iloc[-1])
            chip   = _status_chip(last_v, (1.0, 2.5), ("High demand (>2.5)", "Low demand (<1.0)", "Normal"))
            fig = go.Figure(go.Scatter(x=jolts_ld.index, y=jolts_ld.values, mode="lines", line=dict(color="#00D566", width=1.8)))
            st.plotly_chart(_light_chart(fig, 200, "JOLTS — Layoffs & Discharges Rate"), use_container_width=True, config=PLOTLY_CONFIG, theme=None)
            st.markdown(f"Latest: **{last_v:.2f}%** &nbsp; {chip} &nbsp; {source_badge('fred','JTSLDR')}", unsafe_allow_html=True)
        else:
            st.info("JOLTS data unavailable. Add FRED API key.")

    with l3:
        rail = _macro_fetched["RAILFRTINTERMODAL"]
        if not rail.empty:
            last_v = float(rail.iloc[-1])
            mean_v = float(rail.mean())
            chip   = _status_chip(last_v - mean_v, (-5000, 5000), ("Above avg", "Below avg", "Near avg"))
            fig = go.Figure(go.Scatter(x=rail.index, y=rail.values, mode="lines", line=dict(color="#7C3AED", width=1.8)))
            fig.add_hline(y=mean_v, line=dict(color="#F59E0B", dash="dot", width=1))
            st.plotly_chart(_light_chart(fig, 200, "Rail Intermodal Traffic"), use_container_width=True, config=PLOTLY_CONFIG, theme=None)
            st.markdown(f"Latest: **{last_v:,.0f}** units &nbsp; {chip} &nbsp; {source_badge('fred','RAILFRTINTERMODAL')}", unsafe_allow_html=True)
        else:
            st.info("Rail freight data unavailable. Add FRED API key.")

    st.html(section_label("Consumer & Inflation", color="#FF4444", dot="#FF4444"))

    c1, c2, c3 = st.columns(3)

    with c1:
        umcs = _macro_fetched["UMCSENT"]
        if not umcs.empty:
            last_v = float(umcs.iloc[-1])
            mean_v = float(umcs.mean())
            chip   = _status_chip(last_v - mean_v, (-5, 5), ("Above avg", "Below avg", "Near avg"))
            fig = go.Figure(go.Scatter(x=umcs.index, y=umcs.values, mode="lines", line=dict(color="#F59E0B", width=1.8)))
            fig.add_hline(y=mean_v, line=dict(color="#7C3AED", dash="dot", width=1))
            st.plotly_chart(_light_chart(fig, 200, "U. Michigan Consumer Sentiment"), use_container_width=True, config=PLOTLY_CONFIG, theme=None)
            st.markdown(f"Latest: **{last_v:.1f}** &nbsp; {chip} &nbsp; {source_badge('fred','UMCSENT')}", unsafe_allow_html=True)
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
                                    marker_color=["#00D566" if v > 0 else "#FF4444" for v in rsxfs.values]))
            st.plotly_chart(_light_chart(fig, 200, "Retail Sales ex-Autos (MoM %)"), use_container_width=True, config=PLOTLY_CONFIG, theme=None)
            st.markdown(f"Latest: **{last_v:+.2f}%** &nbsp; {chip} &nbsp; {source_badge('fred','RSXFS')}", unsafe_allow_html=True)
        else:
            st.info("Retail sales unavailable.")

    with c3:
        cpi_food = _macro_fetched["CPIUFDSL"]
        if not cpi_food.empty:
            last_v = float(cpi_food.iloc[-1])
            yoy = ((last_v / float(cpi_food.iloc[-13])) - 1) * 100 if len(cpi_food) > 13 else float("nan")
            chip = _status_chip(yoy if not pd.isna(yoy) else 0, (2, 5), ("Stable (<2%)", "High (>5%)", "Moderate"), inverse=True)
            fig = go.Figure(go.Scatter(x=cpi_food.index, y=cpi_food.values, mode="lines", line=dict(color="#FF4444", width=1.8)))
            st.plotly_chart(_light_chart(fig, 200, "CPI — Food at Home (Index Level)"), use_container_width=True, config=PLOTLY_CONFIG, theme=None)
            st.markdown(f"Index: **{last_v:.1f}** &nbsp; YoY: **{yoy:+.1f}%** &nbsp; {chip} &nbsp; {source_badge('fred','CPIUFDSL')}", unsafe_allow_html=True)
        else:
            st.info("CPI food data unavailable.")

    st.html(section_label("Official Yield Curve (FRED)", color="#7C3AED", dot="#7C3AED"))
    st.caption("FRED's own 10Y-2Y series — complements the live 10Y-3M spread computed from yfinance above.")

    yc = _macro_fetched["T10Y2Y"]
    if not yc.empty:
        fig_yc = go.Figure(go.Scatter(
            x=yc.index, y=yc.values, name="10Y–2Y Spread",
            line=dict(color="#7C3AED", width=2), fill="tozeroy", fillcolor="rgba(28,43,74,0.09)",
        ))
        for i in range(1, len(yc)):
            if yc.iloc[i] < 0:
                fig_yc.add_vrect(x0=yc.index[i - 1], x1=yc.index[i], fillcolor="rgba(123,16,16,0.09)", line_width=0)
        fig_yc.add_hline(y=0, line=dict(color="#FF4444", width=1.5))
        st.plotly_chart(_light_chart(fig_yc, 240, "10Y–2Y Treasury Yield Curve Spread"), use_container_width=True, config=PLOTLY_CONFIG, theme=None)
        last_spread = float(yc.iloc[-1])
        st.markdown(
            f"Current spread: **{last_spread:+.2f}%** &nbsp; "
            + ("Curve is **inverted** — historical recession signal." if last_spread < 0 else "Curve is **positive** — normal.")
            + f" &nbsp; {source_badge('fred','T10Y2Y')}",
            unsafe_allow_html=True,
        )
    else:
        st.info("Yield curve data unavailable. Add FRED API key.")

    # ── Economic Calendar ─────────────────────────────────────────────────────────
    st.markdown(section_label("KEY ECONOMIC RELEASES — SCHEDULE", color="#D6A34A", dot="#D6A34A"), unsafe_allow_html=True)
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
        freq_color = {"Monthly": "#7C3AED", "Weekly": "#F59E0B", "Daily": "#00D566"}.get(freq, "#6B7FBF")
        cal_rows += f"""
        <tr>
            <td><span style="color:{freq_color};font-weight:700;font-size:0.78rem;">{freq}</span></td>
            <td style="color:#8892AA;font-size:0.82rem;">{timing}</td>
            <td style="font-weight:600;color:#E8EEFF;">{release}</td>
            <td style="color:#6B7FBF;font-size:0.80rem;">{source}</td>
        </tr>
        """

    # st.html (not st.markdown): the leading-indented <table> was being parsed as
    # a markdown code block and dumped as raw text near the bottom of Macro Indicators.
    st.html(f"""
    <table class="ua-data-table">
    <thead><tr><th>Frequency</th><th>Timing</th><th>Release</th><th>Source</th></tr></thead>
    <tbody>{cal_rows}</tbody>
    </table>
    """)

render_footer()
