"""
Page 24 — Thematic Basket Builder (#207)
=========================================
Build a custom equal-weight basket of tickers, score it with the UA
signal engine, and compare performance to SPY.

USE CASES:
  • Test whether your thematic thesis (e.g. "nuclear energy plays") is
    actually aligned with macro signals — or whether the excitement is
    price-leading and the signals haven't confirmed yet
  • Compare two competing baskets (e.g. "AI infrastructure" vs "AI software")
    on both signal alignment AND price performance
  • Quickly eyeball signal coverage — which signals matter for each name

FEATURES:
  1. Predefined theme templates (AI Infrastructure, Nuclear, Defense, etc.)
  2. Custom basket: type any tickers
  3. Basket-level confluence score (average of per-ticker UA scores)
  4. Per-ticker signal heatmap — which signals are bull/bear for each name
  5. Basket price chart vs SPY (normalized to 100 at start of period)
  6. Signal alignment score: % of baskets' relevant signals that are bullish
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
from datetime import datetime, timedelta

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.signals_cache import get_all_signal_scores
from utils.config import SIGNALS, TICKERS as TICKER_CFG

st.set_page_config(
    page_title="Basket Builder — Unstructured Alpha",
    page_icon="🧺",
    layout="wide",
)
render_header()
render_sidebar_base()

render_page_header(
    "Thematic Basket Builder",
    "Build and backtest thematic stock baskets aligned with macro signals.",
    icon="🧺",
)

st.markdown("""
<style>
.block-container { padding-top: 0.5rem !important; max-width: 1100px !important; }
.section-hdr {
    font-family: Inter, sans-serif; font-size: 0.70rem; font-weight: 700;
    letter-spacing: 0.12em; color: #6B7FBF; text-transform: uppercase;
    border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 4px; margin-bottom: 12px;
}
.score-pill {
    display: inline-block; padding: 3px 10px; border-radius: 12px;
    font-size: 0.78rem; font-weight: 700; font-family: Inter, sans-serif;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# PREDEFINED THEMATIC BASKETS
# ─────────────────────────────────────────────────────────────────────────────
THEMES: dict[str, list[str]] = {
    "AI Infrastructure":      ["NVDA", "AMD", "AVGO", "AMAT", "SMCI", "VRT", "EQIX", "DLR"],
    "Nuclear & Power":        ["CEG", "VST", "NEE", "CCJ", "UEC", "SMR", "OKLO", "LEU", "BWXT"],
    "Defense & Aerospace":    ["LMT", "RTX", "NOC", "GD", "LHX", "HII"],
    "Energy Transition":      ["PWR", "ETN", "ENPH", "NEE", "XYL", "ECL"],
    "Critical Minerals":      ["FCX", "SCCO", "MP", "ALB", "SQM", "CCJ", "VALE", "BHP"],
    "Mega-Cap Tech":          ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"],
    "Regional Banks":         ["JPM", "BAC", "GS", "WFC", "C", "KRE"],
    "Healthcare Innovators":  ["LLY", "NVO", "REGN", "VRTX", "ISRG", "AMGN"],
    "Homebuilders":           ["DHI", "LEN", "PHM", "TOL", "NVR"],
    "Natural Gas E&P":        ["EQT", "AR", "CTRA", "RRC", "CNX", "LNG"],
    "Consumer Staples":       ["COST", "WMT", "KR", "ACI", "SJM", "CAG"],
    "Industrial Automation":  ["CAT", "DE", "HON", "EMR", "ROK", "ABB"],
    "Custom":                 [],
}

STATUS_COLOR = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#6B7FBF"}
STATUS_ICON  = {"bullish": "▲", "bearish": "▼", "neutral": "→"}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False, max_entries=20)
def _get_price_history(tickers: tuple, period_days: int = 365) -> pd.DataFrame:
    """Fetch closing prices for a tuple of tickers, normalized to 100 at start."""
    try:
        raw = yf.download(
            list(tickers) + ["SPY"],
            period=f"{period_days}d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"]
        else:
            prices = raw
        prices = prices.dropna(how="all")
        # Normalize to 100 at first valid date
        normed = prices.div(prices.iloc[0]) * 100
        return normed
    except Exception:
        return pd.DataFrame()


def _score_basket(tickers: list, all_scores: dict) -> dict:
    """
    For each ticker, pull its relevant signals from TICKER_CFG and compute
    an aggregate score from the live signal scores.

    Returns {ticker: {"score": float, "bull": int, "bear": int, "neut": int, "status": str}}
    """
    result = {}
    for tkr in tickers:
        cfg = TICKER_CFG.get(tkr, {})
        sig_ids = cfg.get("signals", [])
        relevant = [s for s in sig_ids if s in all_scores]
        if not relevant:
            result[tkr] = {"score": 50.0, "bull": 0, "bear": 0, "neut": 0,
                           "status": "neutral", "signals": []}
            continue
        vals = [all_scores[s].get("score", 50) for s in relevant]
        bull = sum(1 for s in relevant if all_scores[s].get("status") == "bullish")
        bear = sum(1 for s in relevant if all_scores[s].get("status") == "bearish")
        neut = len(relevant) - bull - bear
        avg = float(np.mean(vals))
        status = "bullish" if avg >= 65 else ("bearish" if avg <= 35 else "neutral")
        result[tkr] = {
            "score":   avg,
            "bull":    bull,
            "bear":    bear,
            "neut":    neut,
            "status":  status,
            "signals": relevant,
        }
    return result


def _basket_aggregate(ticker_scores: dict) -> dict:
    """Roll up per-ticker scores to basket level."""
    if not ticker_scores:
        return {"score": 50.0, "status": "neutral", "bull_pct": 0.0}
    scores = [v["score"] for v in ticker_scores.values()]
    avg = float(np.mean(scores))
    bull_pct = sum(1 for v in ticker_scores.values() if v["status"] == "bullish") / len(ticker_scores)
    bear_pct = sum(1 for v in ticker_scores.values() if v["status"] == "bearish") / len(ticker_scores)
    status = "bullish" if avg >= 65 else ("bearish" if avg <= 35 else "neutral")
    return {"score": avg, "status": status, "bull_pct": bull_pct, "bear_pct": bear_pct}


# ─────────────────────────────────────────────────────────────────────────────
# LOAD LIVE SCORES
# ─────────────────────────────────────────────────────────────────────────────
with st.spinner("Loading live signal scores…"):
    all_scores = get_all_signal_scores()

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR-STYLE CONTROLS (top of page)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## Thematic Basket Builder")
st.caption(
    "Build a basket of tickers, score it against the UA signal engine, "
    "and compare performance vs. SPY. Use predefined themes or build your own."
)

ctrl1, ctrl2, ctrl3 = st.columns([2, 3, 1])

with ctrl1:
    theme_sel = st.selectbox("Theme:", list(THEMES.keys()), index=0)

with ctrl2:
    default_tickers = THEMES.get(theme_sel, [])
    if theme_sel == "Custom":
        custom_input = st.text_input(
            "Enter tickers (comma-separated):",
            placeholder="NVDA, MSFT, AAPL, ...",
        )
        basket_tickers = [t.strip().upper() for t in custom_input.split(",") if t.strip()][:20]
    else:
        basket_tickers = st.multiselect(
            "Tickers in basket:",
            options=list(TICKER_CFG.keys()),
            default=default_tickers,
            max_selections=20,
        )

with ctrl3:
    period_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365, "2Y": 730}
    period_sel = st.selectbox("Performance period:", list(period_map.keys()), index=2)
    period_days = period_map[period_sel]

if not basket_tickers:
    st.info("Select or enter at least one ticker to build a basket.", icon="🧺")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# COMPUTE
# ─────────────────────────────────────────────────────────────────────────────
ticker_scores = _score_basket(basket_tickers, all_scores)
basket_agg    = _basket_aggregate(ticker_scores)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — BASKET HEADLINE SCORE
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
agg_color = STATUS_COLOR[basket_agg["status"]]
agg_icon  = STATUS_ICON[basket_agg["status"]]

h1, h2, h3, h4 = st.columns(4)
h1.metric(
    "Basket UA Score",
    f"{basket_agg['score']:.1f}",
    f"{agg_icon} {basket_agg['status'].upper()}",
    delta_color="normal" if basket_agg["status"] != "bearish" else "inverse",
)
h2.metric("Tickers", len(basket_tickers))
h3.metric("Bullish Signal %", f"{basket_agg['bull_pct']*100:.0f}%")
h4.metric("Bearish Signal %", f"{basket_agg.get('bear_pct', 0)*100:.0f}%")

# Score bar
bar_w = int(basket_agg["score"])
bar_col = "#00D566" if basket_agg["score"] >= 65 else ("#FF4444" if basket_agg["score"] <= 35 else "#6B7FBF")
st.markdown(
    f"<div style='background:#E8E0D4;border-radius:4px;height:8px;margin:4px 0 16px 0;'>"
    f"<div style='width:{bar_w}%;background:{bar_col};height:8px;border-radius:4px;'></div>"
    f"</div>",
    unsafe_allow_html=True,
)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — PERFORMANCE CHART: BASKET VS SPY
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Basket Performance vs. S&P 500</div>', unsafe_allow_html=True)

with st.spinner("Fetching price history…"):
    prices = _get_price_history(tuple(basket_tickers), period_days=period_days)

if not prices.empty:
    # Equal-weight basket return
    basket_cols = [c for c in basket_tickers if c in prices.columns]
    if basket_cols:
        basket_line = prices[basket_cols].mean(axis=1)
        spy_line = prices["SPY"] if "SPY" in prices.columns else pd.Series(dtype=float)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=basket_line.index, y=basket_line.values,
            name=f"{theme_sel if theme_sel != 'Custom' else 'My Basket'} (equal-weight)",
            line=dict(color=agg_color, width=2.5),
        ))
        if not spy_line.empty:
            fig.add_trace(go.Scatter(
                x=spy_line.index, y=spy_line.values,
                name="SPY (benchmark)",
                line=dict(color="#9E9E9E", width=1.5, dash="dot"),
            ))
        fig.add_hline(y=100, line_color="rgba(255,255,255,0.08)", line_width=1)

        # Annotate basket return
        if len(basket_line) > 1:
            total_ret = basket_line.iloc[-1] - 100
            spy_ret = spy_line.iloc[-1] - 100 if not spy_line.empty else 0
            excess = total_ret - spy_ret
            fig.add_annotation(
                x=basket_line.index[-1], y=basket_line.iloc[-1],
                text=f"+{total_ret:.1f}%" if total_ret >= 0 else f"{total_ret:.1f}%",
                showarrow=False, xanchor="left", xshift=8,
                font=dict(size=11, color=agg_color, family="Inter, sans-serif"),
            )

        fig.update_layout(
            xaxis_title=None, yaxis_title="Normalized (100 = start of period)",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=20, t=20, b=30), height=360,
        )
        fig.update_xaxes(gridcolor="#E8E0D4", tickfont=dict(size=10))
        fig.update_yaxes(gridcolor="#E8E0D4", tickfont=dict(size=10))
        st.plotly_chart(fig, use_container_width=True)

        if len(basket_line) > 1:
            col_r1, col_r2, col_r3 = st.columns(3)
            col_r1.metric(f"Basket ({period_sel})", f"{total_ret:+.1f}%")
            col_r2.metric(f"SPY ({period_sel})", f"{spy_ret:+.1f}%" if not spy_line.empty else "—")
            col_r3.metric("Alpha vs SPY", f"{excess:+.1f}%",
                          delta_color="normal" if excess >= 0 else "inverse")

else:
    st.warning("Could not fetch price data. Check ticker symbols.", icon="⚠️")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — PER-TICKER SIGNAL BREAKDOWN
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Per-Ticker Signal Breakdown</div>', unsafe_allow_html=True)

ticker_rows = []
for tkr in basket_tickers:
    ts = ticker_scores.get(tkr, {})
    cfg = TICKER_CFG.get(tkr, {})
    name = cfg.get("name", tkr)
    ticker_rows.append({
        "Ticker": tkr,
        "Name": name[:28] + "…" if len(name) > 28 else name,
        "UA Score": round(ts.get("score", 50), 1),
        "Status": ts.get("status", "neutral").upper(),
        "Bull Signals": ts.get("bull", 0),
        "Bear Signals": ts.get("bear", 0),
        "Signals Mapped": len(ts.get("signals", [])),
    })

if ticker_rows:
    tdf = pd.DataFrame(ticker_rows)

    def _color_status(val: str) -> str:
        if val == "BULLISH":
            return "color: #00D566; font-weight: 700"
        elif val == "BEARISH":
            return "color: #FF4444; font-weight: 700"
        return "color: #6B7FBF"

    styled = tdf.style.applymap(_color_status, subset=["Status"])
    styled = styled.background_gradient(subset=["UA Score"], cmap="RdYlGn", vmin=20, vmax=80)
    st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — SIGNAL HEATMAP ACROSS BASKET
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Signal Coverage Heatmap</div>', unsafe_allow_html=True)
st.caption("Which UA signals are bullish / bearish / neutral for each ticker in the basket.")

# Build matrix: rows = signals, cols = tickers
all_basket_sigs = sorted(set(
    s for tkr in basket_tickers
    for s in ticker_scores.get(tkr, {}).get("signals", [])
))

if all_basket_sigs and basket_tickers:
    # Map status to numeric: bull=1, neut=0, bear=-1, missing=nan
    status_map = {"bullish": 1, "neutral": 0, "bearish": -1}
    matrix = np.full((len(all_basket_sigs), len(basket_tickers)), np.nan)

    for j, tkr in enumerate(basket_tickers):
        ts = ticker_scores.get(tkr, {})
        for i, sig in enumerate(all_basket_sigs):
            if sig in ts.get("signals", []) and sig in all_scores:
                matrix[i, j] = status_map.get(all_scores[sig].get("status", "neutral"), 0)

    sig_names = [SIGNALS.get(s, {}).get("name", s)[:35] for s in all_basket_sigs]

    fig_heat = go.Figure(go.Heatmap(
        z=matrix,
        x=basket_tickers,
        y=sig_names,
        colorscale=[[0.0, "#FF4444"], [0.5, "rgba(255,255,255,0.08)"], [1.0, "#00D566"]],
        zmin=-1, zmax=1,
        showscale=True,
        colorbar=dict(
            tickvals=[-1, 0, 1],
            ticktext=["Bearish", "Neutral", "Bullish"],
            len=0.6,
        ),
        hovertemplate="Signal: %{y}<br>Ticker: %{x}<br>Status: %{z}<extra></extra>",
    ))
    fig_heat.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=220, r=20, t=20, b=60),
        height=max(300, 30 * len(all_basket_sigs) + 80),
        xaxis=dict(tickfont=dict(size=10, family="Inter, sans-serif")),
        yaxis=dict(tickfont=dict(size=9, family="Inter, sans-serif"), autorange="reversed"),
    )
    st.plotly_chart(fig_heat, use_container_width=True)
else:
    st.info(
        "No signal mappings found for tickers in this basket. "
        "Tickers not in the UA universe won't have signal coverage — "
        "add them to TICKERS config for full analysis.",
        icon="ℹ️",
    )

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — THESIS VERDICT
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Thesis Verdict</div>', unsafe_allow_html=True)

bull_tickers = [t for t, v in ticker_scores.items() if v["status"] == "bullish"]
bear_tickers = [t for t, v in ticker_scores.items() if v["status"] == "bearish"]
neut_tickers = [t for t, v in ticker_scores.items() if v["status"] == "neutral"]

if basket_agg["status"] == "bullish":
    verdict_color = "#0D3B0E"
    verdict_bg = "#F0FFF0"
    verdict_border = "#00D566"
    verdict_text = (
        f"<b>Macro signals broadly support this basket.</b> "
        f"{len(bull_tickers)} of {len(basket_tickers)} tickers have bullish UA signal alignment. "
        f"The underlying macro data — across economic activity, credit, and sector-specific signals — "
        f"is currently consistent with the thesis for this theme."
    )
elif basket_agg["status"] == "bearish":
    verdict_color = "#4B0000"
    verdict_bg = "rgba(255,68,68,0.08)"
    verdict_border = "#FF4444"
    verdict_text = (
        f"<b>Macro signals are not yet supporting this basket.</b> "
        f"{len(bear_tickers)} of {len(basket_tickers)} tickers have bearish UA signal reads. "
        f"This doesn't mean the theme is wrong — it may be early — but the data as of now "
        f"is not confirming the bull case. Watch for signal improvement before adding exposure."
    )
else:
    verdict_color = "#F59E0B"
    verdict_bg = "rgba(245,158,11,0.08)"
    verdict_border = "#6B7FBF"
    verdict_text = (
        f"<b>Mixed signal picture — no clear macro edge.</b> "
        f"Signals are divided: {len(bull_tickers)} bullish, {len(bear_tickers)} bearish, "
        f"{len(neut_tickers)} neutral. In a mixed regime, "
        f"focus on individual names with the strongest signal alignment rather than "
        f"the basket as a whole."
    )

st.markdown(
    f"<div style='background:{verdict_bg};border-left:4px solid {verdict_border};"
    f"padding:14px 18px;border-radius:0 6px 6px 0;font-family:Inter,sans-serif;"
    f"font-size:0.88rem;color:{verdict_color};'>{verdict_text}</div>",
    unsafe_allow_html=True,
)

if bull_tickers:
    st.markdown(
        f"<div style='margin-top:10px;font-size:0.82rem;color:#00D566;'>"
        f"<b>Signal-supported:</b> {', '.join(bull_tickers)}</div>",
        unsafe_allow_html=True,
    )
if bear_tickers:
    st.markdown(
        f"<div style='margin-top:4px;font-size:0.82rem;color:#FF4444;'>"
        f"<b>Signal-cautioned:</b> {', '.join(bear_tickers)}</div>",
        unsafe_allow_html=True,
    )

with st.expander("📚 Methodology", expanded=False):
    st.markdown("""
**Basket Score**

Each ticker's UA score is the equal-weight average of the live scores of its mapped signals
(from `utils/config.py` → `TICKERS[tkr]["signals"]`). The basket score is the simple average
across all tickers. This is not a portfolio-weighted score — it's a signal-alignment measure.

**Signal Coverage**

Tickers not in the UA `TICKERS` config will show score 50 / neutral and 0 mapped signals.
Custom tickers entered in the text field will be fetched for price data but may lack signal
mappings if not in the config.

**Performance Chart**

Equal-weight means each ticker in the basket gets the same allocation. This is intentional:
the basket builder is a signal-analysis tool, not a portfolio optimizer. Real position sizing
would depend on conviction, liquidity, and correlation — all of which vary.

**Heatmap Key**

Green = bullish signal for that ticker/signal pair. Red = bearish. Grey = neutral.
Empty cells = the signal is not mapped to that ticker in the UA config.
""")
