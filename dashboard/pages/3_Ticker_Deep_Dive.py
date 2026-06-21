"""
Page 3 — Ticker Deep Dive
Full bull/bear case for any ticker:
  - All relevant signals scored + scored
  - Confluence score with conviction level
  - Federal contract award velocity (USASpending.gov)
  - SEC Form 4 insider transaction overlay
  - Narrative bull/bear case builder
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from utils.config import SIGNALS, TICKERS, CATEGORIES, CURATED_FUNDS, THIRTEENF_CUSIP_TO_TICKER
from utils.fetchers import (
    fetch_price, fetch_signal_series, is_synthetic,
    fetch_federal_contracts, fetch_insider_trades, fetch_live_quote,
    fetch_insider_transactions_detail, fetch_short_interest, fetch_13f_holdings,
)
from utils.analysis import (
    score_signal, compute_confluence, compute_quick_correlation,
    score_insider_activity, score_short_interest, score_13f_positioning,
    compute_quick_correlation_stats, compute_correlation,
    score_contract_velocity, build_narrative,
)
from utils.ticker_score import compute_full_ticker_score, resolve_ticker_meta
from utils.header import render_header, render_sidebar_base, go_to_ticker, ticker_chips, ticker_label, render_synthetic_data_banner
from utils.audit_ui import render_evidence_expander
from utils.lead_time_research import (
    build_insider_intensity_series, build_short_interest_change_series,
    lag_scan_with_validation, get_sector_peers, pooled_lag_scan_across_sector,
    compute_signal_reliability_score,
)
from utils.lead_time_ui import render_validated_lag_scan

st.set_page_config(page_title="Ticker Deep Dive — UA", layout="wide")
render_header("Ticker Deep Dive")
render_sidebar_base()

# Note: signal/price date ranges (START/END/PRICE_START) now live inside
# utils/ticker_score.compute_full_ticker_score() -- that's the single place
# both this page and the alert engine fetch from, so they can't drift apart.
STATUS_COLOR = {"bullish": "#1B5E20", "bearish": "#7B1010", "neutral": "#8B7355", "no_data": "#9E9E8E"}
STATUS_EMOJI = {"bullish": "▲", "bearish": "▼", "neutral": "●", "no_data": "○"}

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("# Ticker Deep Dive")
st.caption("Full multi-signal bull/bear analysis for any stock. Unique: federal contracts + insider trades + signal convergence.")

with st.expander("How this page works — start here"):
    st.markdown("""
    Enter any ticker to get a comprehensive investment brief built from multiple independent data sources:

    1. **Signal Confluence Score** — How many of the niche alternative data signals are pointing
       bullish or bearish for this specific ticker

    2. **Bull & Bear Case** — Plain-language investment thesis based on current signal readings,
       not analyst opinions

    3. **Federal Contract Awards** — DoE, DoD, and other agency contract awards to this company
       from USASpending.gov. A spike in contract awards is 6-12 months of revenue visibility
       *before* it shows up in earnings

    4. **Insider Transactions** — SEC Form 4 filings showing when executives and directors buy or
       sell. C-suite buying during bullish macro signals = highest conviction

    5. **Signal Detail Table** — Every signal's current reading vs. history, with z-scores and percentiles

    **Important:** This is a research starting point, not a buy/sell signal. Do your own due diligence.
    """)

st.divider()

# ── Ticker Selection ──────────────────────────────────────────────────────────
# If navigating from the Stock Screener, pre-populate the ticker
_default_ticker = st.session_state.get("selected_ticker", "CCJ")

col_top1, col_top2, col_top3 = st.columns([2, 1, 2])

with col_top1:
    ticker_input = st.text_input(
        "Enter any ticker symbol (universe or custom):",
        value=_default_ticker,
        max_chars=10,
        key="ticker_dive",
        help="Type any NYSE/NASDAQ/OTC ticker. For tickers outside our universe, signals are mapped by sector.",
    ).upper().strip()

with col_top2:
    st.markdown("**Quick picks by theme:**")
    theme_options = {
        "Nuclear":   ["CCJ", "LEU", "UEC", "CEG", "VST"],
        "AI Infra":  ["FCX", "WMB", "PWR", "VRT", "NVDA"],
        "Macro":     ["SPY", "UNP", "ODFL", "XLI", "XLE"],
        "Quantum":   ["IONQ", "RGTI", "QBTS", "IBM"],
    }
    theme_sel = st.selectbox("Theme:", list(theme_options.keys()), key="theme_sel")

with col_top3:
    st.markdown("&nbsp;")
    for t in theme_options[theme_sel]:
        if st.button(ticker_label(t), key=f"quick_{t}", use_container_width=True):
            st.session_state.selected_ticker = t
            st.rerun()

# Company name + relevant signals lookup — shared with the alert engine via
# utils/ticker_score.resolve_ticker_meta() so the two never diverge.
tkr_meta, company_name_hint, _auto_sig_ids = resolve_ticker_meta(ticker_input)

if ticker_input not in TICKERS:
    st.info(
        f"**{ticker_input}** is not in our tracked universe. "
        "Running analysis with sector-mapped macro signals. "
        "Add it to `utils/config.py` for custom signal configuration."
    )

st.markdown(f"### Analyzing: **{ticker_input}** — {company_name_hint}")

relevant_sig_ids = _auto_sig_ids

# Also let user add/remove signals
with st.expander("Customize which signals to include"):
    all_sig_options = {sid: f"{cfg['name']} (PCS {cfg['pcs']}/10)" for sid, cfg in SIGNALS.items()}
    selected_sig_ids = st.multiselect(
        "Signals to include in analysis:",
        list(all_sig_options.keys()),
        default=relevant_sig_ids,
        format_func=lambda x: all_sig_options[x],
        key="sig_multisel",
    )
    if selected_sig_ids:
        relevant_sig_ids = selected_sig_ids

# ── Full Score Computation ──────────────────────────────────────────────────────
# compute_full_ticker_score() is the SAME function the alert engine calls to
# evaluate watched tickers in the background -- extracted from this page on
# 2026-06-21 specifically so the score shown here and the score an alert
# fires on can never silently diverge into two different numbers for the
# same ticker (see utils/ticker_score.py's module docstring).
with st.spinner(f"Loading signal data for {ticker_input}…"):
    _full = compute_full_ticker_score(ticker_input, signal_ids=relevant_sig_ids)

signal_scores  = _full["signal_scores"]
signal_data    = _full["signal_data"]
price_series   = _full["price_series"]
corr_info      = _full["corr_info"]
confluence     = _full["confluence"]
_mom_score     = _full["momentum_score"]
_contract_vel  = _full["contract_velocity"]
_has_contract_signal = _full["has_contract_signal"]
_insider_score = _full["insider_score"]
_has_insider_signal = _full["has_insider_signal"]
_insider_tx_early = _full["insider_tx"]
_short_interest_score = _full["short_interest_score"]
_has_short_interest_signal = _full["has_short_interest_signal"]
_si_df = _full["short_interest_df"]
_thirteenf_score = _full["thirteenf_score"]
_has_13f_signal = _full["has_13f_signal"]
_fund_rows_13f = _full["thirteenf_fund_rows"]

render_synthetic_data_banner(
    sum(1 for s in signal_data.values() if is_synthetic(s)),
    len(signal_data),
)

# ── Confluence Score Banner ────────────────────────────────────────────────────
score_val  = confluence["overall_score"]
conviction = confluence["conviction"]
case       = confluence["case"]

score_color = "#1B5E20" if case == "BULL" else ("#7B1010" if case == "BEAR" else "#8B7355")

c_gauge, c_case, c_counts = st.columns([1, 2, 2])

with c_gauge:
    st.markdown(f"""
    <div style="background:#F0EBE1;border-radius:8px;padding:20px;text-align:center;
                border:2px solid {score_color};font-family:Georgia,serif;">
        <div style="font-size:0.72rem;color:#9E9E8E;letter-spacing:0.08em;">CONFLUENCE SCORE</div>
        <div style="font-size:3.5rem;font-weight:800;color:{score_color};line-height:1.1;">
            {score_val:.0f}
        </div>
        <div style="font-size:0.72rem;color:#9E9E8E;">out of 100</div>
    </div>
    """, unsafe_allow_html=True)

with c_case:
    st.markdown(f"""
    <div style="background:#F0EBE1;border-radius:8px;padding:20px;border-left:4px solid {score_color};
                border-top:1px solid #D4C9B0;border-right:1px solid #D4C9B0;border-bottom:1px solid #D4C9B0;
                font-family:Georgia,serif;">
        <div style="font-size:0.72rem;color:#9E9E8E;letter-spacing:0.08em;">SIGNAL CASE</div>
        <div style="font-size:2.2rem;font-weight:800;color:{score_color};">{case}</div>
        <div style="font-size:0.95rem;color:#1A1612;">Conviction: <b>{conviction}</b></div>
        <div style="font-size:0.80rem;color:#6B6560;margin-top:6px;">
            Based on {len(relevant_sig_ids)} independent signals + price momentum{" + federal contract award velocity" if _has_contract_signal else ""}{" + insider buy/sell activity" if _has_insider_signal else ""}{" + short interest trend" if _has_short_interest_signal else ""}{" + 13F institutional positioning" if _has_13f_signal else ""}
        </div>
    </div>
    """, unsafe_allow_html=True)

with c_counts:
    st.markdown(f"""
    <div style="background:#F0EBE1;border-radius:8px;padding:20px;
                border:1px solid #D4C9B0;font-family:Georgia,serif;">
        <div style="font-size:0.72rem;color:#9E9E8E;letter-spacing:0.08em;margin-bottom:10px;">SIGNAL BREAKDOWN</div>
        <div style="display:flex;gap:16px;align-items:center;">
            <div style="text-align:center;">
                <div style="font-size:2rem;font-weight:700;color:#1B5E20;">{confluence['bull_count']}</div>
                <div style="font-size:0.75rem;color:#6B6560;">▲ Bullish</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:2rem;font-weight:700;color:#7B1010;">{confluence['bear_count']}</div>
                <div style="font-size:0.75rem;color:#6B6560;">▼ Bearish</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:2rem;font-weight:700;color:#8B7355;">{confluence['neutral_count']}</div>
                <div style="font-size:0.75rem;color:#6B6560;">● Neutral</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with st.expander("What does the Confluence Score mean?"):
    st.markdown(f"""
    The **Confluence Score** (0–100) combines {len(relevant_sig_ids)} independent alternative data
    signals and weights them by their Predictive Confidence Score (PCS).

    - **Score >65** = Multiple independent signals currently reading bullish for {ticker_input}
    - **Score 35–65** = Mixed signals — no clear directional read right now
    - **Score <35** = Multiple signals currently reading bearish

    **Conviction level = "{conviction}"** means {
        "most signals are pointing the same direction — high agreement." if "High" in conviction
        else "signals are mixed — lower directional agreement." if conviction == "Low / Mixed"
        else "a majority of signals agree."
    }

    **What this score is:** a read of how many independent signals currently agree, weighted by
    each one's backtested correlation with {ticker_input}'s own price history. One bullish signal
    might be noise; several independent ones agreeing simultaneously is a stronger *description*
    of the current data.

    **What this score is not, yet:** a validated predictor of forward returns. A walk-forward
    backtest of this exact scoring function (real production code, tested against 6 tickers
    spanning the Power Supercycle thesis, pooled across ~19 monthly checkpoints) found no
    statistically significant relationship between the score and 1/2/3-month forward returns.
    Two of the six tickers tested showed a significant *negative* relationship in isolation —
    high readings coincided with a cyclical top rather than leading one — before pooling washed
    that out to noise. Treat conviction as agreement among signals today, not a guarantee about
    tomorrow. Full methodology and numbers: About → Methodology.
    """)

st.divider()

# ── Price Chart ───────────────────────────────────────────────────────────────
_PERIOD_OPTS = ["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "2Y", "ALL"]
_PERIOD_DAYS = {"1D": 2, "5D": 7, "1M": 35, "3M": 100, "6M": 190, "YTD": None, "1Y": 370, "2Y": 730, "ALL": 0}

price_period = st.radio(
    "Price chart period",
    _PERIOD_OPTS,
    index=6,          # default 1Y
    horizontal=True,
    label_visibility="collapsed",
    key="dive_price_period",
)
st.markdown(f"### {ticker_input} Price — {price_period}")

if not price_series.empty:
    # Trim to the selected period
    pd_days = _PERIOD_DAYS[price_period]
    if pd_days is None:   # YTD
        _yr_start = pd.Timestamp(datetime.now().year, 1, 1, tz=price_series.index.tz
                                  if price_series.index.tz else None)
        price_view = price_series[price_series.index >= _yr_start]
    elif pd_days == 0:    # ALL
        price_view = price_series
    else:
        price_view = price_series.iloc[-min(pd_days, len(price_series)):]

    if price_view.empty:
        price_view = price_series

    use_candle = len(price_view) > 5 and price_period not in ("1D", "5D")
    if use_candle:
        fig_price = go.Figure(go.Candlestick(
            x=price_view.index,
            open=price_view.values * 0.998,
            high=price_view.values * 1.005,
            low=price_view.values * 0.995,
            close=price_view.values,
            name=ticker_input,
            increasing_line_color="#1B5E20",
            decreasing_line_color="#7B1010",
        ))
    else:
        fig_price = go.Figure(go.Scatter(
            x=price_view.index, y=price_view.values,
            mode="lines", line=dict(color="#B8860B", width=2.5),
            fill="tozeroy", fillcolor="rgba(184,134,11,0.08)",
            name=ticker_input,
        ))

    # Add 50-day and 200-day MAs (from full series, trimmed to view window).
    # Dotted, distinct colors — so they read as overlays/context, while the
    # actual price line (solid, gold, drawn first above) stays the visual anchor.
    if len(price_series) >= 50 and price_period not in ("1D", "5D"):
        ma50 = price_series.rolling(50).mean()
        ma50_view = ma50[ma50.index >= price_view.index[0]]
        fig_price.add_trace(go.Scatter(
            x=ma50_view.index, y=ma50_view.values, name="50-day MA",
            line=dict(color="#1C2B4A", width=2, dash="dot"),
        ))
    if len(price_series) >= 200 and price_period in ("1Y", "2Y", "YTD", "ALL"):
        ma200 = price_series.rolling(200).mean()
        ma200_view = ma200[ma200.index >= price_view.index[0]]
        fig_price.add_trace(go.Scatter(
            x=ma200_view.index, y=ma200_view.values, name="200-day MA",
            line=dict(color="#7B1010", width=2, dash="dot"),
        ))

    fig_price.update_layout(
        height=360, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
        font=dict(size=13, color="#1A1612"),
        xaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560", size=11), rangeslider_visible=False),
        yaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560", size=11), title="Price (USD)"),
        legend=dict(font=dict(color="#1A1612"), bgcolor="rgba(250,247,240,0.9)"),
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig_price, use_container_width=True)

    # Price stats
    if len(price_series) > 50:
        current_p  = float(price_series.iloc[-1])
        high_52w   = float(price_series.tail(252).max())
        low_52w    = float(price_series.tail(252).min())
        pct_from_high = (current_p - high_52w) / high_52w * 100
        pct_from_low  = (current_p - low_52w)  / low_52w  * 100
        ytd_base   = price_series.resample("YE").first()
        ret_ytd    = (current_p / ytd_base.iloc[-1] - 1) * 100 if (len(price_series) > 50 and not ytd_base.empty) else float("nan")

        p1, p2, p3, p4 = st.columns(4)

        @st.fragment(run_every="60s")
        def _render_live_price(ticker: str, fallback_price: float) -> None:
            """
            Auto-refreshes every 60s independent of the rest of the page —
            only this fragment re-runs on the timer, not the full script, so
            the expensive historical chart/signal fetches above don't re-fire
            every minute. Falls back to the last historical close (from the
            already-fetched daily series) if the live quote is unavailable
            (after hours, network hiccup, etc.) rather than showing nothing.
            """
            q = fetch_live_quote(ticker)
            if q["price"] is not None:
                delta = f"{q['pct_change']:+.2f}%" if q["pct_change"] is not None else None
                st.metric("Current Price", f"${q['price']:.2f}", delta=delta)
                st.caption("LIVE · updates every 60s")
            else:
                st.metric("Current Price", f"${fallback_price:.2f}")
                st.caption("Last close (live quote unavailable)")

        with p1:
            _render_live_price(ticker_input, current_p)

        p2.metric("52-Week High",  f"${high_52w:.2f}", delta=f"{pct_from_high:+.1f}%")
        p3.metric("52-Week Low",   f"${low_52w:.2f}",  delta=f"{pct_from_low:+.1f}%")
        p4.metric("YTD Return",    f"{ret_ytd:+.1f}%")

st.divider()

# ── Forward Prediction Model ───────────────────────────────────────────────────
from utils.analysis import predict_ticker_forward  # noqa: E402 (deferred import keeps page fast)

st.markdown('<div class="section-header">SIGNAL-BASED PREDICTION MODEL</div>', unsafe_allow_html=True)
st.caption(
    "Probability estimates derived from macro signal confluence + price momentum. "
    "NOT financial advice. For research & education only."
)

pred = predict_ticker_forward(
    confluence_score=score_val,
    # Trim to a recent ~2-year window so volatility reflects the current regime,
    # not diluted by a much longer price_series now used for the "ALL" chart period.
    price_series=price_series.tail(550) if len(price_series) > 550 else price_series,
    signal_scores=signal_scores,
)

regime      = pred["regime"]
strength    = pred["regime_strength"]
reg_color   = "#1B5E20" if regime == "BULL" else ("#7B1010" if regime == "BEAR" else "#8B7355")
h30         = pred["horizons"][0]   # 30-day horizon

# ── Probability bar ───────────────────────────────────────────────────────────
bull_w = pred["final_bull"]
bear_w = pred["final_bear"]
neut_w = pred["final_neutral"]

st.markdown(f"""
<div style="margin-bottom:8px;">
    <div style="font-size:0.72rem;color:#9E9E8E;letter-spacing:0.06em;margin-bottom:4px;">
        DIRECTIONAL PROBABILITY (30-DAY HORIZON)
    </div>
    <div style="display:flex;border-radius:6px;overflow:hidden;height:32px;">
        <div style="width:{bull_w:.0f}%;background:#1B5E20;display:flex;align-items:center;
                    justify-content:center;color:white;font-size:0.80rem;font-weight:700;">
            ▲ {bull_w:.0f}%
        </div>
        <div style="width:{neut_w:.0f}%;background:#8B7355;display:flex;align-items:center;
                    justify-content:center;color:white;font-size:0.80rem;font-weight:700;">
            ● {neut_w:.0f}%
        </div>
        <div style="width:{bear_w:.0f}%;background:#7B1010;display:flex;align-items:center;
                    justify-content:center;color:white;font-size:0.80rem;font-weight:700;">
            ▼ {bear_w:.0f}%
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Horizon cards ─────────────────────────────────────────────────────────────
hor_cols = st.columns(3)
for hcol, h in zip(hor_cols, pred["horizons"]):
    h_color = "#1B5E20" if h["bull_pct"] > 60 else ("#7B1010" if h["bear_pct"] > 60 else "#8B7355")
    with hcol:
        st.markdown(f"""
        <div style="background:#F0EBE1;border-radius:8px;padding:14px 16px;text-align:center;
                    border-top:3px solid {h_color};border:1px solid #D4C9B0;font-family:Georgia,serif;">
            <div style="font-size:0.68rem;color:#9E9E8E;letter-spacing:0.06em;">{h['label']} FORECAST</div>
            <div style="font-size:1.8rem;font-weight:800;color:{h_color};margin:4px 0;">
                {h['bull_pct']:.0f}%
            </div>
            <div style="font-size:0.72rem;color:#6B6560;font-weight:600;">Bull Probability</div>
            <div style="font-size:0.72rem;color:#8B7355;margin-top:6px;">
                Price range<br>
                <b>${h['price_low']:.2f} — ${h['price_high']:.2f}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("")

# ── Key signals driving prediction + plain English ────────────────────────────
pred_c1, pred_c2 = st.columns([3, 2])

with pred_c1:
    _plain = pred['plain_english'].replace("\\$", "$")
    st.markdown(f"""
    <div style="background:#F0EBE1;border-radius:6px;padding:14px 16px;border:1px solid #D4C9B0;
                font-family:Georgia,serif;font-size:0.83rem;color:#2A2520;line-height:1.6;">
        <div style="font-size:0.72rem;color:#9E9E8E;letter-spacing:0.06em;margin-bottom:6px;">
            PLAIN-ENGLISH SUMMARY
        </div>
        {_plain}
    </div>
    """, unsafe_allow_html=True)

with pred_c2:
    st.markdown(f"""
    <div style="background:#F0EBE1;border-radius:6px;padding:14px 16px;border:1px solid #D4C9B0;
                font-family:Georgia,serif;">
        <div style="font-size:0.72rem;color:#9E9E8E;letter-spacing:0.06em;margin-bottom:8px;">
            MOMENTUM SNAPSHOT
        </div>
        <table style="width:100%;font-size:0.80rem;color:#1A1612;">
            <tr><td style="color:#8B7355;">1-Month</td>
                <td style="text-align:right;font-weight:700;color:{'#1B5E20' if pred['momentum_1m']>0 else '#7B1010'};">
                    {pred['momentum_1m']:+.1f}%</td></tr>
            <tr><td style="color:#8B7355;">3-Month</td>
                <td style="text-align:right;font-weight:700;color:{'#1B5E20' if pred['momentum_3m']>0 else '#7B1010'};">
                    {pred['momentum_3m']:+.1f}%</td></tr>
            <tr><td style="color:#8B7355;">6-Month</td>
                <td style="text-align:right;font-weight:700;color:{'#1B5E20' if pred['momentum_6m']>0 else '#7B1010'};">
                    {pred['momentum_6m']:+.1f}%</td></tr>
            <tr><td style="color:#8B7355;">1-Year</td>
                <td style="text-align:right;font-weight:700;color:{'#1B5E20' if pred['momentum_1y']>0 else '#7B1010'};">
                    {pred['momentum_1y']:+.1f}%</td></tr>
            <tr><td style="color:#8B7355;padding-top:6px;">Ann. Volatility</td>
                <td style="text-align:right;font-weight:700;color:#8B7355;padding-top:6px;">
                    {pred['annual_vol_pct']:.1f}%</td></tr>
        </table>
    </div>
    """, unsafe_allow_html=True)

st.caption(
    "Prediction probabilities are derived from alternative data signals and price momentum — "
    "they are NOT guarantees or financial advice. Past signal accuracy does not predict future performance. "
    "Always do your own due diligence before making investment decisions."
)

st.divider()

# ── Bull & Bear Case ──────────────────────────────────────────────────────────
st.markdown("### Bull Case vs. Bear Case")

with st.expander("How are these cases generated?"):
    st.markdown(f"""
    The bull and bear cases are built automatically from the current readings of each signal,
    compared against their 52-week historical baselines.

    **Each bullet point corresponds to one signal** that is currently flashing bullish or bearish.
    The text describes:
    - What the signal is currently showing
    - How far it deviates from its historical average
    - The causal mechanism linking it to {ticker_input}
    - The historical lead time (how many weeks ahead it predicts)

    This is not an analyst opinion — it's a systematic translation of data into narrative.
    """)

narrative = build_narrative(ticker_input, signal_scores, SIGNALS)
bull_pts   = narrative["bull_points"]
bear_pts   = narrative["bear_points"]

bull_col, bear_col = st.columns(2)

with bull_col:
    st.markdown(f"""
    <div style="background:#EBF5EC;border-radius:6px;padding:16px;
                border-left:4px solid #1B5E20;border-top:1px solid #A8C09A;
                border-right:1px solid #A8C09A;border-bottom:1px solid #A8C09A;
                min-height:200px;font-family:Georgia,serif;">
        <div style="color:#1B5E20;font-size:0.95rem;font-weight:700;margin-bottom:12px;letter-spacing:0.02em;">
            BULL CASE — {confluence['bull_count']} signals
        </div>
    """, unsafe_allow_html=True)
    if bull_pts:
        for pt in bull_pts:
            st.markdown(f"▲ {pt}")
    else:
        st.markdown("*No bullish signals currently flashing for this ticker.*")
    st.markdown("</div>", unsafe_allow_html=True)

with bear_col:
    st.markdown(f"""
    <div style="background:#FAF0F0;border-radius:6px;padding:16px;
                border-left:4px solid #7B1010;border-top:1px solid #E8A8A8;
                border-right:1px solid #E8A8A8;border-bottom:1px solid #E8A8A8;
                min-height:200px;font-family:Georgia,serif;">
        <div style="color:#7B1010;font-size:0.95rem;font-weight:700;margin-bottom:12px;letter-spacing:0.02em;">
            BEAR CASE — {confluence['bear_count']} signals
        </div>
    """, unsafe_allow_html=True)
    if bear_pts:
        for pt in bear_pts:
            st.markdown(f"▼ {pt}")
    else:
        st.markdown("*No bearish signals currently flashing for this ticker.*")
    st.markdown("</div>", unsafe_allow_html=True)

st.divider()

# ── Signal Detail Table ───────────────────────────────────────────────────────
st.markdown("### Signal Detail Table")
st.caption("Every signal scored and contextualized. Click on any row to see its sparkline chart.")

with st.expander("Understanding the table columns"):
    st.markdown("""
    | Column | Explanation |
    |---|---|
    | **Status** | 🟢 Bullish / 🔴 Bearish / 🟡 Neutral based on current reading vs. 52-week history |
    | **Score** | 0–100 scale. 50 = average. >65 = bullish. <35 = bearish |
    | **Z-Score** | Standard deviations from 52-week mean. ±1.5σ = notable. ±2σ = significant |
    | **Percentile** | Where current reading sits in its own history. 80th+ = elevated. 20th- = depressed |
    | **Dev %** | % deviation from 52-week average |
    | **4w Trend** | Whether the signal is improving (↑) or worsening (↓) vs. 4 weeks ago |
    | **Lead** | Typical weeks this signal leads the price of related stocks |
    | **PCS** | Predictive Confidence Score 1–10. Higher = more validated signal |
    """)

def _score_reason(sig_id: str, cfg: dict, sv: dict, ticker: str) -> str:
    """Generate a plain-English explanation of why this signal has its current score."""
    status  = sv.get("status", "neutral")
    score   = sv.get("score", 50)
    z       = sv.get("z_score", 0)
    pct     = sv.get("percentile", 50)
    dev     = sv.get("deviation_pct", 0)
    trend   = sv.get("trend_4w_pct", 0)
    lag     = cfg.get("lag_weeks", 0)
    inv     = cfg.get("inverse", False)
    name    = cfg.get("name", sig_id)

    direction_word = "above" if dev > 0 else "below"
    pct_context    = (
        "near all-time highs" if pct > 90 else
        "elevated" if pct > 70 else
        "near historical average" if 40 <= pct <= 60 else
        "below average" if pct < 40 else
        "near multi-year lows"
    )

    if status == "no_data":
        return "No data available — add a FRED API key in Setup to enable this signal."

    # Build the reason
    if abs(z) < 0.5:
        reading_desc = f"currently near its 1-year average ({dev:+.1f}% deviation)"
    elif abs(z) < 1.5:
        reading_desc = f"running {abs(dev):.1f}% {direction_word} its 1-year average (z={z:+.1f})"
    else:
        reading_desc = f"at {pct:.0f}th percentile — significantly {direction_word} average (z={z:+.1f})"

    # Interpret direction for inverse vs. direct signals
    if inv:
        if dev > 0:
            effect = f"bearish for {ticker} — higher {name.split('(')[0].strip()} increases headwinds"
        elif dev < 0:
            effect = f"bullish for {ticker} — lower {name.split('(')[0].strip()} removes headwinds"
        else:
            effect = "neutral — at its historical midpoint"
    else:
        if dev > 0:
            effect = f"bullish for {ticker} — higher readings historically precede price appreciation"
        elif dev < 0:
            effect = f"bearish for {ticker} — below-average readings historically precede weakness"
        else:
            effect = "neutral — at its historical midpoint"

    trend_desc = ""
    if abs(trend) > 2:
        trend_dir = "improving" if (trend > 0 and not inv) or (trend < 0 and inv) else "deteriorating"
        trend_desc = f" Momentum is {trend_dir} ({trend:+.1f}% over 4 weeks)."

    lead_desc = f" If the signal persists, expect the effect to show in {ticker} price in ~{lag} weeks." if lag > 0 else ""

    return f"{name} is {reading_desc}, {pct_context}. This is {effect}.{trend_desc}{lead_desc}"


table_rows = []
table_reasons: dict[str, str] = {}

for sig_id in relevant_sig_ids:
    cfg = SIGNALS.get(sig_id)
    sv  = signal_scores.get(sig_id, {})
    ci  = corr_info.get(sig_id, {"r": 0.0, "weight": 0.5, "p_value": 1.0, "significant": False, "n": 0})
    if not cfg:
        continue

    status  = sv.get("status", "neutral")
    score   = sv.get("score", 50)
    z       = sv.get("z_score", 0)
    pct     = sv.get("percentile", 50)
    dev     = sv.get("deviation_pct", 0)
    trend   = sv.get("trend_4w_pct", 0)
    trend_a = "↑" if trend > 1 else ("↓" if trend < -1 else "→")
    r_val   = ci["r"]
    p_val   = ci.get("p_value", 1.0)
    is_sig  = ci.get("significant", False)
    n_obs   = ci.get("n", 0)
    # Weighted impact = how much this signal moves the confluence score
    impact  = abs(r_val) * abs(score - 50)

    reason = _score_reason(sig_id, cfg, sv, ticker_input)
    table_reasons[cfg["name"]] = reason

    table_rows.append({
        "Signal":       cfg["name"],
        "Status":       STATUS_EMOJI.get(status, "●") + " " + status.capitalize(),
        "Score":        round(score, 1),
        "Corr (r)":     round(r_val, 2),
        "P-Value":      round(p_val, 3),
        "Significant":  "Yes" if is_sig else "No",
        "N":            n_obs,
        "Impact":       round(impact, 1),
        "Z-Score":      round(z, 2),
        "Percentile":   round(pct, 1),
        "Dev %":        round(dev, 2),
        "4w Trend":     f"{trend_a} {trend:+.1f}%",
        "Lead (wk)":    cfg["lag_weeks"],
        "PCS":          cfg["pcs"],
        "Category":     CATEGORIES.get(cfg["category"], {}).get("name", cfg["category"]),
    })

if table_rows:
    # Sort by weighted impact first (which signals actually move this ticker's score)
    table_df_all = pd.DataFrame(table_rows).sort_values("Impact", ascending=False)

    # ── Statistical significance filter ───────────────────────────────────────
    # Only signals with p < 0.05 against THIS ticker's price are "real" drivers.
    # Guarantee at least 3 shown signals: if fewer than 3 clear the bar, promote
    # the strongest non-significant ones (by |r|) so there's always something to
    # analyze — but they stay clearly labeled as not significant in their own row.
    sig_mask   = table_df_all["Significant"] == "Yes"
    sig_df     = table_df_all[sig_mask].copy()
    nonsig_df  = table_df_all[~sig_mask].sort_values("Corr (r)", key=lambda s: s.abs(), ascending=False).copy()

    n_promote = max(0, 3 - len(sig_df))
    promoted_df = nonsig_df.head(n_promote).copy()
    nonsig_df   = nonsig_df.iloc[n_promote:]

    table_df = pd.concat([sig_df, promoted_df]).sort_values("Impact", ascending=False)

    # Show top signal drivers callout
    top3 = table_df.head(3)
    driver_html = ""
    for _, dr in top3.iterrows():
        r_fmt = f"{dr['Corr (r)']:+.2f}"
        r_color = "#1B5E20" if dr['Corr (r)'] > 0 else "#7B1010"
        driver_html += f"""
        <div style="flex:1;background:#F0EBE1;border-radius:6px;padding:12px;
                    border:1px solid #D4C9B0;border-top:3px solid {r_color};font-family:Georgia,serif;">
            <div style="font-size:0.70rem;color:#8B7355;text-transform:uppercase;letter-spacing:0.05em;
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{dr['Signal'][:30]}</div>
            <div style="font-size:1.4rem;font-weight:700;color:{r_color};margin:4px 0;">{r_fmt}</div>
            <div style="font-size:0.75rem;color:#6B6560;">r with {ticker_input} price</div>
            <div style="font-size:0.75rem;color:#1A1612;margin-top:4px;">Score: <b>{dr['Score']:.0f}</b> &nbsp; {dr['Status']}</div>
        </div>"""

    st.markdown(f"""
    <div style="margin-bottom:12px;">
        <div style="font-size:0.72rem;color:#8B7355;text-transform:uppercase;
                    letter-spacing:0.07em;margin-bottom:8px;">
            TOP SIGNAL DRIVERS FOR {ticker_input} — by historical price correlation
        </div>
        <div style="display:flex;gap:10px;">{driver_html}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"##### Statistically Significant Signals for {ticker_input} (p < 0.05)")
    st.dataframe(
        table_df.drop(columns=["N"]),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score":  st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%.0f"
            ),
            "Impact": st.column_config.ProgressColumn(
                "Impact", min_value=0, max_value=50, format="%.1f",
                help="Score deviation × correlation — how much this signal moves the confluence for this ticker"
            ),
            "Corr (r)": st.column_config.NumberColumn(
                "Corr (r)", format="%.2f",
                help="Pearson correlation between signal and ticker price returns at the signal's lead time. ±1 = perfect; 0 = no relationship."
            ),
            "P-Value": st.column_config.NumberColumn(
                "P-Value", format="%.3f",
                help="Probability this correlation is due to chance. < 0.05 = statistically significant."
            ),
            "Significant": st.column_config.TextColumn(
                "Sig?", help="Yes = passes the p<0.05 significance test for this specific ticker."
            ),
            "Z-Score": st.column_config.NumberColumn("Z-Score", format="%.2f"),
        },
    )
    if len(promoted_df) > 0:
        st.caption(
            f"Only {len(sig_df)} signal(s) cleared the p<0.05 bar for {ticker_input} — "
            f"{len(promoted_df)} additional non-significant signal(s) with the strongest |r| are shown above "
            f"(marked \"No\" in Sig?) to keep at least 3 signals in view. Treat those with extra caution."
        )
    else:
        st.caption(
            f"All {len(sig_df)} signals shown passed the p<0.05 significance test against {ticker_input}'s price. "
            f"Sorted by Impact = |correlation| × |signal deviation|."
        )

    # ── Per-signal reasoning cards ─────────────────────────────────────────────
    st.markdown("")
    st.markdown("#### Why these scores?")
    st.caption("Detailed reasoning for every signal's current bullish/bearish/neutral reading.")

    # Build name→sig_id lookup so we can get relevant_tickers per signal
    _name_to_sid = {SIGNALS[sid]["name"]: sid for sid in SIGNALS}

    for row_i, row in enumerate(table_df.itertuples(index=False)):
        sig_name   = row.Signal
        sig_status = row.Status
        sig_score  = row.Score
        reason_txt = table_reasons.get(sig_name, "")
        corr_r     = getattr(row, "Corr (r)", 0)
        impact_val = row.Impact

        s_key = sig_status.split(" ")[-1].lower() if " " in sig_status else sig_status.lower()
        card_color = "#1B5E20" if "bullish" in s_key else ("#7B1010" if "bearish" in s_key else "#8B7355")
        bg_color   = "#F0F7F0" if "bullish" in s_key else ("#FDF0F0" if "bearish" in s_key else "#F7F5F0")
        sym        = "▲" if "bullish" in s_key else ("▼" if "bearish" in s_key else "●")

        corr_note = (
            f"&nbsp; | &nbsp; r = {corr_r:+.2f} with {ticker_input} "
            f"(impact: {impact_val:.1f})"
        ) if corr_r != 0 else ""

        st.markdown(f"""
        <div style="background:{bg_color};border-radius:6px;padding:12px 16px;margin-bottom:4px;
                    border-left:4px solid {card_color};border:1px solid rgba(0,0,0,0.08);
                    font-family:Georgia,serif;">
            <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:4px;">
                <span style="color:{card_color};font-weight:700;font-size:0.88rem;">{sym} {sig_name}</span>
                <span style="font-size:0.75rem;color:{card_color};font-weight:600;">{sig_status}</span>
                <span style="font-size:0.75rem;color:#8B7355;">Score: {sig_score:.0f}/100{corr_note}</span>
            </div>
            <div style="font-size:0.82rem;color:#2A2520;line-height:1.55;">{reason_txt}</div>
        </div>
        """, unsafe_allow_html=True)

        # Related tickers for this signal (excluding the current one being analyzed)
        sid_key = _name_to_sid.get(sig_name)
        if sid_key:
            related = [t for t in SIGNALS[sid_key].get("relevant_tickers", [])
                       if t != ticker_input][:5]
            if related:
                st.caption("Also relevant to this signal:")
                ticker_chips(related, key_prefix=f"dive_rel_{row_i}_{sid_key}")
        st.markdown("")   # small gap between cards

    # ── Not statistically significant — shown transparently, not hidden ───────
    if len(nonsig_df) > 0:
        with st.expander(
            f"Not Statistically Significant for {ticker_input} ({len(nonsig_df)} signals excluded above)"
        ):
            st.caption(
                f"These signals are tracked in the Unstructured Alpha library and may be statistically "
                f"significant for OTHER tickers, but their historical correlation with {ticker_input}'s "
                f"price specifically did not clear the p<0.05 bar. They are excluded from the confluence "
                f"score and driver table above so they don't dilute the analysis with noise."
            )
            nonsig_display = nonsig_df[["Signal", "Corr (r)", "P-Value", "N", "Category"]].rename(
                columns={"N": "Observations"}
            )
            st.dataframe(
                nonsig_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Corr (r)": st.column_config.NumberColumn("Corr (r)", format="%.2f"),
                    "P-Value":  st.column_config.NumberColumn("P-Value", format="%.3f"),
                },
            )

    # ── Deep Correlation Scan — Lead Time Optimizer ────────────────────────────
    st.divider()
    st.markdown('<div class="section-header">DEEP CORRELATION SCAN — LEAD TIME OPTIMIZER</div>', unsafe_allow_html=True)
    st.caption(f"Pick one signal above to test in depth against {ticker_input}: the optimal lead time, "
               f"whether the relationship is stable over time, and a visual overlay.")

    with st.expander("How this works"):
        st.markdown("""
        **The core idea:** alternative data signals don't move stocks instantly — there's a delay
        between when a signal changes and when the market prices it in. This tool finds that delay.

        **Lead Time Optimizer:** tests every lag from 0 to 16 weeks and shows which one produces the
        strongest correlation. If the bar at lag=6 weeks is tallest, the signal is most useful as a
        6-week leading indicator for this specific ticker.

        **Rolling 26-week correlation:** a relationship that was strong 2 years ago but has since
        collapsed means something changed — a regime shift, or the market already pricing it in.
        A stable, consistently nonzero rolling correlation is a much higher-confidence signal than
        a single overall r value.

        **r > 0.3 with p < 0.05** is generally considered a useful signal; r > 0.5 is strong.
        """)

    deep_sig_options = {sid: SIGNALS[sid]["name"] for sid in relevant_sig_ids if sid in SIGNALS}
    if _has_insider_signal:
        deep_sig_options["_insider_activity"] = "Insider Activity — validated lead-time scan"
    if _has_short_interest_signal:
        deep_sig_options["_short_interest"] = "Short Interest — validated lead-time scan"

    is_alt_data_scan = False
    if deep_sig_options:
        dc1, dc2 = st.columns([2, 1])
        with dc1:
            deep_sig_id = st.selectbox(
                "Signal to deep-scan:",
                list(deep_sig_options.keys()),
                format_func=lambda x: deep_sig_options[x],
                key="deep_scan_sig",
            )
        is_alt_data_scan = deep_sig_id in ("_insider_activity", "_short_interest")

        if is_alt_data_scan:
            with dc2:
                st.caption(
                    "Reuses the lag-scan above, but adds an out-of-sample check, a "
                    "multiple-comparisons correction, and cross-ticker pooling — alt-data "
                    "signals like this are sparser and easier to overfit by accident than "
                    "the macro signals above, so they get more rigor, not less."
                )
        else:
            deep_cfg = SIGNALS.get(deep_sig_id, {})
            with dc2:
                deep_lag = st.slider(
                    "Manual lag (weeks):", 0, 16, deep_cfg.get("lag_weeks", 0), key="deep_scan_lag"
                )

    if deep_sig_options and is_alt_data_scan:
        _alt_label = deep_sig_options[deep_sig_id]
        if st.button(f"Run validated lead-time scan: {_alt_label}", key="run_alt_lag_scan"):
            with st.spinner(
                "Fetching extended history and running the validated scan "
                "(slower than the instant macro-signal scan above) …"
            ):
                if deep_sig_id == "_insider_activity":
                    _ext_df = fetch_insider_transactions_detail(ticker_input, days=730, max_filings=150)
                    _alt_series = build_insider_intensity_series(_ext_df)
                else:
                    _ext_df = fetch_short_interest(ticker_input, years=2.0)
                    _alt_series = build_short_interest_change_series(_ext_df)

                if _alt_series.empty or price_series.empty:
                    _alt_result = {"error": "Insufficient data for this ticker", "n": 0}
                    _alt_reliability = compute_signal_reliability_score(_alt_result)
                    _alt_pooled = None
                else:
                    _alt_result = lag_scan_with_validation(_alt_series, price_series, scan_max_lag=16)

                    _peer_tickers = get_sector_peers(ticker_input, max_peers=4)
                    _alt_pooled = None
                    if _peer_tickers and not _alt_result.get("error"):
                        _peer_end = pd.Timestamp.now().strftime("%Y-%m-%d")
                        _peer_start = (pd.Timestamp.now() - pd.Timedelta(days=900)).strftime("%Y-%m-%d")
                        _peer_signals, _peer_prices = {}, {}
                        for _peer in _peer_tickers:
                            try:
                                if deep_sig_id == "_insider_activity":
                                    _peer_raw = fetch_insider_transactions_detail(_peer, days=730, max_filings=150)
                                    _peer_sig = build_insider_intensity_series(_peer_raw)
                                else:
                                    _peer_raw = fetch_short_interest(_peer, years=2.0)
                                    _peer_sig = build_short_interest_change_series(_peer_raw)
                                _peer_price = fetch_price(_peer, _peer_start, _peer_end)
                                if not _peer_sig.empty and not _peer_price.empty:
                                    _peer_signals[_peer] = _peer_sig
                                    _peer_prices[_peer] = _peer_price
                            except Exception:
                                continue
                        if _peer_signals:
                            _alt_pooled = pooled_lag_scan_across_sector(_peer_signals, _peer_prices, scan_max_lag=16)

                    _alt_reliability = compute_signal_reliability_score(_alt_result, _alt_pooled)

                st.session_state["_alt_lag_result"] = _alt_result
                st.session_state["_alt_lag_reliability"] = _alt_reliability
                st.session_state["_alt_lag_pooled"] = _alt_pooled
                st.session_state["_alt_lag_signal_id"] = deep_sig_id

        if (
            "_alt_lag_result" in st.session_state
            and st.session_state.get("_alt_lag_signal_id") == deep_sig_id
        ):
            render_validated_lag_scan(
                st.session_state["_alt_lag_result"],
                st.session_state["_alt_lag_reliability"],
                st.session_state.get("_alt_lag_pooled"),
            )

    elif deep_sig_options:
        # Reuse data already fetched earlier on this page — no extra network calls.
        deep_sig_data = signal_data.get(deep_sig_id, pd.Series(dtype=float))
        if not deep_sig_data.empty and not price_series.empty:
            deep_corr = compute_correlation(deep_sig_data, price_series, lag_weeks=deep_lag)
        else:
            deep_corr = {"error": "Insufficient overlapping data", "n": 0, "lag_scan": {}}

        if "error" in deep_corr:
            st.info(f"Not enough overlapping data to deep-scan {deep_cfg.get('name', deep_sig_id)} against {ticker_input}.")
        else:
            dr      = deep_corr.get("pearson_r", 0)
            dr2     = deep_corr.get("r_squared", 0)
            dpval   = deep_corr.get("p_value", 1)
            dsig    = deep_corr.get("significant", False)
            dn      = deep_corr.get("n", 0)
            dbest_lag = deep_corr.get("best_lag", deep_lag)
            dbest_r   = deep_corr.get("best_r", dr)
            dsig_str  = "Statistically significant (p<0.05)" if dsig else "Not statistically significant (p≥0.05)"

            dm1, dm2, dm3, dm4 = st.columns(4)
            dm1.metric("Pearson r", f"{dr:+.3f}", delta=f"at lag={deep_lag}w")
            dm2.metric("R² (explained variance)", f"{dr2:.3f}")
            dm3.metric("p-value", f"{dpval:.4f}", delta=dsig_str)
            dm4.metric("Observations", dn)

            if dbest_lag != deep_lag:
                st.info(f"Stronger correlation found at lag={dbest_lag} weeks (r={dbest_r:+.3f}). Adjust the slider above to use it.")

            # Lag-scan bar chart
            lag_scan = deep_corr.get("lag_scan", {})
            if lag_scan:
                lags, corrs = list(lag_scan.keys()), list(lag_scan.values())
                bar_colors = ["#1B5E20" if c > 0 else "#7B1010" for c in corrs]
                if deep_lag < len(bar_colors):
                    bar_colors[deep_lag] = "#B8860B"
                fig_lag = go.Figure(go.Bar(
                    x=[f"{l}w" for l in lags], y=corrs, marker_color=bar_colors,
                    text=[f"{c:+.3f}" for c in corrs], textposition="outside",
                    textfont=dict(size=9, color="#1A1612"),
                    hovertemplate="Lag %{x}: r = %{y:.4f}<extra></extra>",
                ))
                fig_lag.add_hline(y=0, line_color="#9E9E8E")
                fig_lag.update_layout(
                    height=260, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
                    xaxis=dict(showgrid=False, tickfont=dict(color="#6B6560"), title="Lag (weeks)"),
                    yaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560"), title="Pearson r"),
                    margin=dict(l=0, r=0, t=10, b=0),
                )
                st.plotly_chart(fig_lag, use_container_width=True)

            # Rolling 26-week correlation
            rolling = deep_corr.get("rolling_corr", pd.Series(dtype=float))
            if not rolling.empty and rolling.dropna().shape[0] > 5:
                fig_roll = go.Figure(go.Scatter(
                    x=rolling.dropna().index, y=rolling.dropna().values, mode="lines",
                    fill="tozeroy", line=dict(color="#1C2B4A", width=2),
                    fillcolor="rgba(28,43,74,0.12)",
                    hovertemplate="%{x}: r=%{y:.3f}<extra></extra>",
                ))
                fig_roll.add_hline(y=0, line_color="#9E9E8E")
                fig_roll.update_layout(
                    title=dict(text="Rolling 26-Week Correlation — is the relationship stable?", font=dict(size=12, color="#1C2B4A")),
                    height=220, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
                    xaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560")),
                    yaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560"),
                               title="26w rolling r", range=[-1, 1]),
                    margin=dict(l=0, r=0, t=30, b=0),
                )
                st.plotly_chart(fig_roll, use_container_width=True)

            # Signal + price overlay
            aligned = deep_corr.get("aligned", pd.DataFrame())
            if not aligned.empty:
                sig_norm = aligned["signal"] / aligned["signal"].iloc[0] * 100
                prc_norm = aligned["price"]  / aligned["price"].iloc[0]  * 100
                fig_ov = make_subplots(specs=[[{"secondary_y": True}]])
                fig_ov.add_trace(go.Scatter(
                    x=sig_norm.index, y=sig_norm.values,
                    name=f"{deep_cfg.get('name','')[:28]} (lag={deep_lag}w)",
                    line=dict(color="#1C2B4A", width=2),
                ), secondary_y=False)
                fig_ov.add_trace(go.Scatter(
                    x=prc_norm.index, y=prc_norm.values, name=f"{ticker_input} Price",
                    line=dict(color="#B8860B", width=2),
                ), secondary_y=True)
                fig_ov.update_layout(
                    height=320, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
                    legend=dict(font=dict(color="#1A1612"), bgcolor="rgba(250,247,240,0.9)"),
                    hovermode="x unified",
                    xaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560")),
                    margin=dict(l=0, r=0, t=20, b=0),
                )
                fig_ov.update_yaxes(title_text="Signal (normalized to 100)", secondary_y=False,
                                     gridcolor="#E8E0CE", tickfont=dict(color="#6B6560"), title_font=dict(color="#1C2B4A"))
                fig_ov.update_yaxes(title_text=f"{ticker_input} Price (normalized to 100)", secondary_y=True,
                                     gridcolor="rgba(0,0,0,0)", tickfont=dict(color="#6B6560"), title_font=dict(color="#B8860B"))
                st.plotly_chart(fig_ov, use_container_width=True)

st.divider()

# ── Federal Contract Awards ───────────────────────────────────────────────────
st.markdown("### Federal Contract Awards (USASpending.gov)")

with st.expander("Why federal contracts matter for investors"):
    st.markdown("""
    The US government awards contracts to companies for defense, energy, infrastructure, and more —
    all visible on the public website **USASpending.gov**.

    **Why this is a leading indicator:**
    - Contract awards precede revenue recognition by 6-24 months
    - DoE contracts to nuclear companies signal government commitment to specific technologies
    - DoD contracts signal long-term demand visibility that analysts rarely model in advance

    **This signal is almost entirely ignored by retail finance platforms.**
    Quiver Quantitative has a government contract tracker, but doesn't link it to our macro signals.

    We track award *velocity* — whether the pace of contracts is accelerating or decelerating —
    which is more predictive than the absolute dollar amount.
    """)

company_search = st.text_input(
    "Search company name (for USASpending.gov lookup):",
    value=company_name_hint,
    # BUG FIX: this key used to be a fixed "company_search" string. Streamlit
    # widgets ignore the `value=` argument on reruns once session_state
    # already has an entry for that key -- so after switching tickers (e.g.
    # CCJ -> GOOGL), this box kept showing "Cameco Corporation" and, worse,
    # the fetch below kept searching for Cameco's contracts while analyzing
    # Alphabet. Keying it per-ticker makes each ticker get its own
    # remembered search text, correctly defaulting to the fresh company
    # name when the ticker actually changes. Caught via live verification
    # while testing the 13F feature, not by the test suite (AppTest doesn't
    # simulate a user switching tickers mid-session the way this bug needs).
    key=f"company_search_{ticker_input}",
)

if company_search:
    with st.spinner(f"Fetching federal contract data for '{company_search}'…"):
        contracts_df = fetch_federal_contracts(company_search, years=2)
        vel_score    = score_contract_velocity(contracts_df)

    if not contracts_df.empty:
        vel_status = vel_score.get("status", "neutral")
        vel_color  = STATUS_COLOR.get(vel_status, "#FF9800")

        cv1, cv2, cv3 = st.columns(3)
        cv1.metric("Recent 6-month awards",  f"${vel_score['recent_total']:,.0f}")
        cv2.metric("Prior 6-month awards",   f"${vel_score['prior_total']:,.0f}")
        cv3.metric("Award velocity change",  f"{vel_score['pct_change']:+.1f}%",
                   delta="Bullish" if vel_status == "bullish" else ("Bearish" if vel_status == "bearish" else "Neutral"))

        # Contract timeline chart
        contracts_df_chart = contracts_df.dropna(subset=["date", "amount"]).copy()
        if not contracts_df_chart.empty:
            monthly_awards = contracts_df_chart.set_index("date")["amount"].resample("ME").sum().reset_index()
            monthly_awards.columns = ["date", "amount"]

            fig_c = go.Figure(go.Bar(
                x=monthly_awards["date"],
                y=monthly_awards["amount"],
                name="Monthly Award Volume",
                marker_color=vel_color,
                hovertemplate="%{x|%b %Y}: $%{y:,.0f}<extra></extra>",
            ))
            # 6-month rolling average
            ma6 = monthly_awards["amount"].rolling(3).mean()
            fig_c.add_trace(go.Scatter(
                x=monthly_awards["date"], y=ma6,
                name="3-month avg", mode="lines",
                line=dict(color="#1C2B4A", width=2.5),
            ))
            fig_c.update_layout(
                title="Monthly Federal Contract Awards",
                height=250, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
                xaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560")),
                yaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560"),
                           title="Award Amount (USD)"),
                legend=dict(font=dict(color="#1A1612"), bgcolor="rgba(250,247,240,0.9)"),
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig_c, use_container_width=True)

        # Contract table
        display_cols = [c for c in ["date", "agency", "amount", "description"] if c in contracts_df.columns]
        if display_cols:
            st.dataframe(
                contracts_df[display_cols].head(15).assign(
                    date=lambda x: x["date"].dt.strftime("%Y-%m-%d") if "date" in x.columns else x.get("date",""),
                    amount=lambda x: x["amount"].apply(lambda v: f"${v:,.0f}" if pd.notnull(v) else "—") if "amount" in x.columns else x.get("amount",""),
                ),
                use_container_width=True, hide_index=True,
            )
    else:
        st.info(f"No federal contract data found for '{company_search}'. Try a broader company name (e.g., 'Cameco' vs 'CCJ').")

st.divider()

# ── Insider Transactions ──────────────────────────────────────────────────────
st.markdown("### Insider Transactions (SEC Form 4)")

with st.expander("Why insider trades matter and how to interpret them"):
    st.markdown(f"""
    **SEC Form 4** is a legal filing that corporate insiders (executives, directors, and large shareholders)
    must submit within 2 business days of buying or selling company stock.

    **Why it matters:**
    - Insiders know the business better than anyone
    - C-suite buying = they believe the stock is undervalued
    - C-suite selling = could be personal liquidity, but worth monitoring — most insider Form 4
      activity is routine RSU vesting or option exercises, not a real buy/sell decision, which is
      why the table below only counts genuine open-market purchases and sales.

    **How the score below is built:** weighted on insider COUNT and clustering, not dollar amount —
    a $1M purchase is massive for a small-cap and trivial for a mega-cap, and this product has no
    reliable market-cap context to normalize that fairly. Multiple independent insiders buying in
    the same window (without anyone selling) is scored more bullish than one large purchase by one
    person, consistent with the academic finance literature on insider trading (Lakonishok & Lee
    2001; Seyhun), which finds clustered insider buying more predictive than transaction size alone.

    **Honesty check:** this specific signal — real Form 4 transaction detail, scored on clustering —
    has not yet been independently backtested against forward returns the way the Confluence Score
    itself was (see About → Methodology for that backtest). Treat it as a real, methodologically
    grounded read, not yet a proven one for this exact implementation.

    **Data source:** SEC EDGAR (free public database). Filings appear within 48 hours of the transaction.
    """)

# Real, parsed open-market transactions (P/S only) — reuses the same cached
# fetch already done above for the Confluence Score blend, no extra cost.
st.markdown("**Open-Market Buy/Sell Activity (last 180 days)**")
if _has_insider_signal:
    ins_color = "#1B5E20" if _insider_score["status"] == "bullish" else ("#7B1010" if _insider_score["status"] == "bearish" else "#8B7355")
    i1, i2, i3, i4 = st.columns(4)
    i1.metric("Insider Score", f"{_insider_score['score']:.0f}/100")
    i2.metric("Distinct Buyers", _insider_score["distinct_buyers"])
    i3.metric("Distinct Sellers", _insider_score["distinct_sellers"])
    i4.metric("Net Value", f"${_insider_score['net_value']:,.0f}")
    if _insider_score["cluster_bonus_applied"]:
        st.markdown(f'<span style="color:{ins_color};font-weight:700;">Cluster pattern detected</span> — 3+ insiders moved the same direction with no one going the other way.', unsafe_allow_html=True)

    tx_display = _insider_tx_early[["date", "insider", "role", "code", "shares", "price", "value"]].copy()
    tx_display["date"] = tx_display["date"].dt.strftime("%Y-%m-%d")
    tx_display["code"] = tx_display["code"].map({"P": "Purchase", "S": "Sale"})
    tx_display["price"] = tx_display["price"].map(lambda v: f"${v:,.2f}")
    tx_display["value"] = tx_display["value"].map(lambda v: f"${v:,.0f}")
    st.dataframe(tx_display, use_container_width=True, hide_index=True)
    render_evidence_expander(_insider_score.get("evidence", []))
else:
    st.info(f"No genuine open-market purchases or sales (transaction code P/S) found for {ticker_input} in the last 180 days — most Form 4 activity in this window, if any, was grants, vesting, or option exercises, not a buy/sell decision.")

with st.spinner(f"Fetching insider filing history for {ticker_input}…"):
    insider_df = fetch_insider_trades(ticker_input, days=180)

with st.expander("All Form 4 filings (including grants/vesting, not just buy/sell)"):
    if not insider_df.empty:
        display_insider = insider_df[
            [c for c in ["date", "filer", "form", "entity"] if c in insider_df.columns]
        ].head(10).copy()
        if "date" in display_insider.columns:
            display_insider["date"] = display_insider["date"].dt.strftime("%Y-%m-%d")

        st.dataframe(display_insider, use_container_width=True, hide_index=True)
        st.caption(f"Showing {min(10, len(insider_df))} most recent Form 4 filings from SEC EDGAR. [View all on SEC EDGAR →](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker_input}&type=4&dateb=&owner=include&count=40)")
    else:
        st.info(f"No recent Form 4 filings found for {ticker_input} in EDGAR search. This may indicate low insider activity or the EDGAR search returned no results. [Search manually →](https://efts.sec.gov/LATEST/search-index?q={ticker_input}&forms=4)")

st.divider()

# ── Short Interest ──────────────────────────────────────────────────────────────
st.markdown("### Short Interest (FINRA, Exchange-Listed)")

with st.expander("How short interest works and what this score means"):
    st.markdown("""
    **FINRA short interest** is collected from broker-dealers twice a month (settlement near the
    15th and the last business day of each month) and published with roughly a 2-3 week lag — the
    slowest-moving signal on this page, similar in cadence to 13F filings.

    **INVERSE signal:** rising short interest = more bearish positioning being built = lower score.
    Falling short interest = bears covering = higher score.

    **What this does NOT model:** short-squeeze dynamics. Very high short interest combined with a
    bullish price catalyst can produce a sharp upward squeeze as shorts are forced to cover — that
    is a real pattern, but modeling it reliably requires combining this with price action in a way
    this product doesn't yet do. A high "days to cover" figure below is worth noticing on its own
    merits, even though the score itself doesn't try to predict squeeze timing.

    **Data source:** FINRA's free public API (`consolidatedShortInterest`) — exchange-listed
    securities, not just OTC, verified directly against real data before this was built.
    """)

if _has_short_interest_signal:
    si_color = "#1B5E20" if _short_interest_score["status"] == "bullish" else ("#7B1010" if _short_interest_score["status"] == "bearish" else "#8B7355")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Short Interest Score", f"{_short_interest_score['score']:.0f}/100")
    s2.metric("Current Short Shares", f"{_short_interest_score['short_shares']:,}")
    s3.metric("Latest Period Change", f"{_short_interest_score['latest_change_pct']:+.1f}%")
    s4.metric("Days to Cover", f"{_short_interest_score['days_to_cover']:.1f}")

    si_display = _si_df.tail(10).copy()
    si_display["date"] = si_display["date"].dt.strftime("%Y-%m-%d")
    si_display["change_pct"] = si_display["change_pct"].map(lambda v: f"{v:+.1f}%" if pd.notna(v) else "—")
    si_display["short_shares"] = si_display["short_shares"].map(lambda v: f"{v:,.0f}" if pd.notna(v) else "—")
    st.dataframe(
        si_display.rename(columns={"short_shares": "short_shares", "change_pct": "period_change",
                                     "days_to_cover": "days_to_cover", "avg_daily_volume": "avg_daily_volume"}),
        use_container_width=True, hide_index=True,
    )
    render_evidence_expander(_short_interest_score.get("evidence", []))
else:
    st.info(f"No FINRA short interest history found for {ticker_input} in the last 18 months — this can happen for very new listings or tickers FINRA's symbol matching doesn't recognize exactly as entered.")

st.divider()

# ── 13F Institutional Positioning ────────────────────────────────────────────
st.markdown("### 13F Institutional Positioning")

with st.expander("What is a 13F filing, and why is this section limited to a few funds?"):
    _curated_funds_list_str = ", ".join(f"{_f['name']} ({_f['style'].lower()})" for _f in CURATED_FUNDS)
    st.markdown(f"""
    **A 13F is a quarterly disclosure the SEC requires** from any institutional investment manager
    overseeing more than $100 million in U.S. equities — hedge funds, mutual funds, pension funds,
    and similar. It lists every U.S.-listed stock (and certain options) the manager held at quarter-end.
    It's public, free, and is how the public learns what funds like Berkshire Hathaway are buying or
    selling — but with a real lag: managers have **45 days after quarter-end** to file, so a 13F is
    always showing a snapshot that's at least 1.5–4.5 months old by the time it's public. This is the
    slowest-moving signal on this page, in the same category as short interest but even more so.

    **Why only a handful of funds, not "every fund that holds this stock":** 13F filings report
    holdings by abbreviated company name and CUSIP — there is no ticker symbol field anywhere in a
    13F. There's no free, reliable, automatic way to turn a CUSIP into a ticker symbol. Rather than
    algorithmically fuzzy-match company names (which risks confidently mismatching two similarly-named
    companies, or missing a real holding because of an abbreviation), this product hand-verifies a
    small, well-known set of funds' actual filings against its own ticker list, fund by fund, position
    by position. That trades breadth for being right.

    **Curated funds currently tracked:** {_curated_funds_list_str}. These were chosen because their
    filings are small and concentrated enough to fully read and verify by hand, not because they're
    "the best" funds to follow.

    **A note on Put and Call options:** some 13F lines aren't plain stock ownership — they're options.
    A Call position is a bullish bet; a Put position is a bearish one (or a hedge). This product reads
    that field and scores Puts as bearish, not as if the fund simply owns the stock.
    """)

if _has_13f_signal:
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("13F Score", f"{_thirteenf_score['score']:.0f}/100")
    f2.metric("Funds Long", _thirteenf_score["funds_long"])
    f3.metric("Funds Short", _thirteenf_score["funds_short"])
    f4.metric("New Positions", _thirteenf_score["new_positions"])

    _fund_display_rows = []
    for _row in _fund_rows_13f:
        _direction_label = "Long" if _row["latest_shares"] > 0 else "Short (Put)"
        _trend = "—"
        if _row["prior_shares"]:
            _chg = (abs(_row["latest_shares"]) - abs(_row["prior_shares"])) / abs(_row["prior_shares"]) * 100
            _trend = f"{_chg:+.1f}% vs. prior quarter"
        elif _row["latest_shares"] != 0:
            _trend = "New position this quarter"
        _fund_display_rows.append({
            "Fund": _row["fund"], "Style": _row["style"], "Position": _direction_label,
            "Shares": f"{abs(_row['latest_shares']):,.0f}",
            "As of": _row["latest_period"].strftime("%Y-%m-%d") if pd.notna(_row["latest_period"]) else "—",
            "Trend": _trend,
        })
    st.dataframe(pd.DataFrame(_fund_display_rows), use_container_width=True, hide_index=True)
    st.caption("Source: SEC EDGAR Form 13F-HR, fetched live from each fund's actual filing. \"As of\" is the real reporting period, not the filing date — those can be ~45 days apart.")
    render_evidence_expander(_thirteenf_score.get("evidence", []))
else:
    _curated_fund_names_str = ", ".join(_f["name"] for _f in CURATED_FUNDS)
    st.info(f"None of the curated funds ({_curated_fund_names_str}) currently hold {ticker_input} in their most recent 13F filing. This reflects only those {len(CURATED_FUNDS)} funds, not the full universe of institutional holders — for broader 13F coverage, check a dedicated 13F aggregator like WhaleWisdom.")

st.divider()

# ── Export ────────────────────────────────────────────────────────────────────
st.markdown("### Export Analysis")

if table_rows:
    export_data = {
        "ticker": ticker_input,
        "company": company_name_hint,
        "confluence_score": score_val,
        "conviction": conviction,
        "case": case,
        "bull_signals": confluence["bull_count"],
        "bear_signals": confluence["bear_count"],
        "generated_at": datetime.now().isoformat(),
    }

    exp_df = pd.DataFrame(table_rows)
    csv_b  = exp_df.to_csv(index=False).encode()
    st.download_button(
        f"⬇️ Download {ticker_input} Signal Analysis (CSV)",
        csv_b,
        file_name=f"UA_{ticker_input}_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
