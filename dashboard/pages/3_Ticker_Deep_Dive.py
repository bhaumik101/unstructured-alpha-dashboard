"""
Page 3 — Ticker Deep Dive
Full bull/bear case for any ticker:
  - All relevant signals scored + scored
  - Confluence score with conviction level
  - Federal contract award velocity (USASpending.gov)
  - SEC Form 4 insider transaction overlay
  - Narrative bull/bear case builder

Layout (2026-06-22): split into 4 sections via st.segmented_control --
Overview (score, price, prediction model, bull/bear case, signal table,
export) / Insider & Short Interest / 13F & Federal Contracts / Deep
Correlation Scan -- instead of one ~1,350-line linear scroll. Chose
segmented_control over st.tabs() deliberately: a live AppTest check
confirmed st.tabs() executes every tab body on every script run
regardless of which tab is visually selected (it's a pure CSS/display
mechanism), while branching on segmented_control's return value with
if/elif genuinely skips code for unselected sections -- see
tests/test_ticker_deep_dive_sections.py.

Important nuance this restructuring does NOT change: insider/short-
interest/13F/federal-contracts data is baked into the headline
Confluence Score itself (utils/ticker_score.py blends each active one in
at a fixed 12% weight), so all of those fetches still run unconditionally
for the Overview score regardless of which section is open -- that part
of the cost is inherent to the scoring methodology, not something tab-
splitting can defer without showing an incomplete score on first load.
What IS genuinely deferred: fetch_insider_trades(), a second, separate
fetch used only for the "all Form 4 filings" detail expander (not used
in scoring), which now only fires once the Insider & Short Interest
section is actually opened.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from utils.config import SIGNALS, TICKERS, CATEGORIES, CURATED_FUNDS, THIRTEENF_CUSIP_TO_TICKER
from utils.fetchers import (
    fetch_price, fetch_signal_series, is_synthetic, fetch_volume,
    fetch_federal_contracts, fetch_insider_trades, fetch_live_quote,
    fetch_insider_transactions_detail, fetch_short_interest, fetch_13f_holdings,
    fetch_earnings_dates, fetch_ticker_news,
)
from utils.analysis import (
    score_signal, compute_confluence, compute_quick_correlation,
    score_insider_activity, score_short_interest, score_13f_positioning,
    compute_quick_correlation_stats, compute_correlation,
    score_contract_velocity, build_narrative, compute_rsi,
)
from utils.ticker_score import compute_full_ticker_score, resolve_ticker_meta
from utils.header import render_header, render_sidebar_base, go_to_ticker, ticker_chips, ticker_label, render_synthetic_data_banner
from utils.audit_ui import render_evidence_expander
from utils.lead_time_research import (
    build_insider_intensity_series, build_short_interest_change_series,
    lag_scan_with_validation, get_sector_peers, pooled_lag_scan_across_sector,
    compute_signal_reliability_score, compute_rolling_best_lag,
)
from utils.lead_time_ui import render_validated_lag_scan, render_lag_decay_chart
from utils.score_history import record_score_snapshot, get_score_history, compute_sector_percentile

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
# Read ticker from URL query param (?ticker=NVDA) or session state (from screener/watchlist).
# This makes shareable URLs work: unstructuredalpha.com/Ticker_Deep_Dive?ticker=NVDA
_url_ticker = st.query_params.get("ticker", "")
_default_ticker = _url_ticker.upper().strip() if _url_ticker else st.session_state.get("selected_ticker", "CCJ")

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
try:
    with st.spinner(f"Loading signal data for {ticker_input}…"):
        _full = compute_full_ticker_score(ticker_input, signal_ids=relevant_sig_ids)
except Exception as _score_err:
    st.error(
        f"**Could not load data for {ticker_input}.** "
        f"This usually means the ticker symbol is invalid, or a data source "
        f"(yfinance / FRED) is temporarily unavailable. "
        f"Try again in a moment, or check that '{ticker_input}' is a valid NYSE/NASDAQ symbol."
    )
    st.caption(f"Technical detail: {_score_err}")
    st.stop()

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

# Opportunistic score snapshot -- runs once per ticker view, regardless of
# which segmented_control section a visitor lands on, since the score
# itself is computed in compute_full_ticker_score() above either way (see
# utils/score_history.py's module docstring for why this is the
# foundation the Score History chart, future track-record page, and real
# alert deltas all sit on). Wrapped defensively: a DB hiccup here must
# never break the page someone is just trying to look at a score on.
try:
    record_score_snapshot(
        ticker_input, confluence["overall_score"], confluence["case"], confluence["conviction"],
    )
except Exception:
    pass

st.divider()

section = st.segmented_control(
    "View",
    ["Overview", "Deep Correlation Scan", "Insider & Short Interest", "13F & Federal Contracts", "Earnings Track Record"],
    default="Overview",
    key="dive_section",
)
section = section or "Overview"  # segmented_control returns None if deselected

if section == "Overview":
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

    # ── Share strip ───────────────────────────────────────────────────────────
    _share_c1, _share_c2, _ = st.columns([1, 1, 3])
    with _share_c1:
        if st.button("📤 Share this analysis", key="share_btn", help="Copy a link to this ticker's analysis"):
            st.session_state["_tdd_show_share"] = True
    with _share_c2:
        if st.button("⭐ Add to Watchlist", key="add_wl_btn", help="Track this ticker with alerts"):
            st.session_state["chart_ticker"] = ticker_input
            st.switch_page("pages/10_Watchlist.py")
    if st.session_state.get("_tdd_show_share"):
        _share_url = f"https://unstructuredalpha.com/Ticker_Deep_Dive?ticker={ticker_input}"
        st.code(_share_url, language=None)
        st.caption("Copy the link above and share it. The page loads directly to this ticker's analysis.")
        if st.button("✕ Dismiss", key="share_dismiss"):
            st.session_state.pop("_tdd_show_share", None)
            st.rerun()

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

    # ── Signal Shape Radar ────────────────────────────────────────────────────────
    # Spider/radar chart showing how each of the 5 independent score dimensions
    # contributes to the final Confluence Score. Unlike the single number above,
    # the radar reveals the SHAPE of the bull/bear case — e.g., "macro signals
    # strong, but insiders are selling" reads very differently from "macro + insider
    # both bullish." Inspired by Simply Wall St's Snowflake visualization.
    #
    # The 5 axes:
    #   Macro Signals      — derived from bull/bear/neutral signal count ratio
    #   Price Momentum     — 1Y/1M blended momentum score (already 0-100)
    #   Insider Activity   — from EDGAR Form 4 buy/sell clustering
    #   Institutional Flow — from 13F filings (curated hedge funds)
    #   Short Interest     — from FINRA (high = bearish, already inverted to 0-100)
    try:
        _total_sigs = max(1, confluence["bull_count"] + confluence["bear_count"] + confluence["neutral_count"])
        _macro_axis = round(min(95, max(5,
            (confluence["bull_count"] - confluence["bear_count"]) / _total_sigs * 50 + 50
        )), 1)
        _mom_axis  = round(min(95, max(5, _mom_score)), 1)

        _radar_axes   = ["Macro\nSignals", "Price\nMomentum", "Insider\nActivity", "Institutional\nFlow", "Short\nInterest"]
        _radar_vals   = [_macro_axis, _mom_axis,
                         round(_insider_score.get("score", 50), 1)        if _has_insider_signal        else 50.0,
                         round(_thirteenf_score.get("score", 50), 1)      if _has_13f_signal            else 50.0,
                         round(_short_interest_score.get("score", 50), 1) if _has_short_interest_signal else 50.0]
        _radar_has_data = [True, True, _has_insider_signal, _has_13f_signal, _has_short_interest_signal]

        # Close the polygon
        _rv_closed = _radar_vals + [_radar_vals[0]]
        _ra_closed = _radar_axes + [_radar_axes[0]]

        _fill_color = (
            "rgba(27,94,32,0.20)"  if case == "BULL" else
            "rgba(123,16,16,0.20)" if case == "BEAR" else
            "rgba(139,115,85,0.15)"
        )
        _line_color = "#1B5E20" if case == "BULL" else ("#7B1010" if case == "BEAR" else "#8B7355")

        _fig_radar = go.Figure()

        # Neutral reference ring at 50
        _fig_radar.add_trace(go.Scatterpolar(
            r=[50] * (len(_radar_axes) + 1),
            theta=_ra_closed,
            mode="lines",
            line=dict(color="#D4C9B0", width=1, dash="dot"),
            showlegend=False, hoverinfo="skip",
        ))

        # Score polygon
        _fig_radar.add_trace(go.Scatterpolar(
            r=_rv_closed,
            theta=_ra_closed,
            fill="toself",
            fillcolor=_fill_color,
            line=dict(color=_line_color, width=2.5),
            hovertemplate="%{theta}: %{r:.0f}/100<extra></extra>",
            showlegend=False,
        ))

        _fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True, range=[0, 100],
                    tickvals=[25, 50, 75],
                    tickfont=dict(size=9, color="#8B7355", family="Georgia, serif"),
                    gridcolor="#E8E0CE", linecolor="#D4C9B0",
                ),
                angularaxis=dict(
                    tickfont=dict(size=10, color="#1C2B4A", family="Georgia, serif"),
                    linecolor="#D4C9B0", gridcolor="#E8E0CE",
                ),
                bgcolor="#FAF7F0",
            ),
            height=300, margin=dict(l=30, r=30, t=20, b=20),
            paper_bgcolor="#FAF7F0", showlegend=False,
        )

        _radar_col_l, _radar_col_r = st.columns([1, 1])
        with _radar_col_l:
            st.markdown(
                f'<div style="font-family:Georgia,serif;padding:10px 0;">'
                f'<div style="font-size:0.70rem;text-transform:uppercase;letter-spacing:0.08em;'
                f'color:#8B7355;margin-bottom:8px;">SIGNAL SHAPE — {ticker_input}</div>'
                f'<div style="font-size:0.80rem;color:#6B6560;line-height:1.7;">',
                unsafe_allow_html=True,
            )
            for _i, (_aname, _aval, _has) in enumerate(zip(_radar_axes, _radar_vals, _radar_has_data)):
                _acolor = "#1B5E20" if _aval >= 60 else ("#7B1010" if _aval <= 40 else "#8B7355")
                _asym   = "▲" if _aval >= 60 else ("▼" if _aval <= 40 else "●")
                _adisp  = _aname.replace("\n", " ")
                _no_data_note = "" if _has else " <span style='color:#9E9E9E;font-size:0.70rem;'>no data yet</span>"
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:3px 0;'
                    f'border-bottom:1px solid #F0EBE1;font-family:Georgia,serif;">'
                    f'<span style="color:#1A1612;">{_adisp}{_no_data_note}</span>'
                    f'<span style="color:{_acolor};font-weight:700;">{_asym} {_aval:.0f}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                '<div style="font-size:0.68rem;color:#9E9E8E;margin-top:8px;">'
                'Dashed ring = 50 (neutral). Score > 60 = bullish, < 40 = bearish.</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        with _radar_col_r:
            st.plotly_chart(_fig_radar, use_container_width=True)
    except Exception:
        pass  # Radar chart failure must never crash the rest of the page

    # ── Auto-Explainer ────────────────────────────────────────────────────────────
    # Build a 2–3 sentence plain-English summary of what's driving the score,
    # using only the statistically significant signals (corr_info significant=True)
    # that are currently directional (not neutral). This gives any visitor an
    # immediate, concrete "why" rather than leaving them to hunt through the
    # signal table below.
    try:
        _drivers = []
        for _sid in relevant_sig_ids:
            _ss = signal_scores.get(_sid, {})
            _ci = corr_info.get(_sid, {})
            _st = _ss.get("status", "neutral")
            if _st in ("bullish", "bearish") and _ci.get("significant"):
                _drivers.append({
                    "name":    SIGNALS.get(_sid, {}).get("name", _sid),
                    "status":  _st,
                    "r":       _ci.get("r", 0.0),
                    "z":       _ss.get("z_score", 0.0),
                    "dev":     _ss.get("deviation_pct", 0.0),
                    "lag":     SIGNALS.get(_sid, {}).get("lag_weeks", 0),
                    "inverse": SIGNALS.get(_sid, {}).get("inverse", False),
                })
        _drivers.sort(key=lambda d: -abs(d["r"]))

        def _driver_phrase(d: dict) -> str:
            """Turn one driver into a short clause like 'Copper is elevated (+2.1σ)'."""
            _name = d["name"]
            _dev  = d["dev"]
            _z    = d["z"]
            _dir  = "above" if _dev > 0 else "below"
            _mag  = abs(_dev)
            _lag  = d["lag"]
            _lag_str = f" (leads stocks ~{_lag}w)" if _lag > 0 else ""
            if d["status"] == "bullish":
                return f"**{_name}** is running {_mag:.0f}% {_dir} its average{_lag_str}"
            else:
                return f"**{_name}** is running {_mag:.0f}% {_dir} its average{_lag_str}"

        if _drivers:
            _top      = _drivers[:3]
            _case_str = confluence["case"]
            _sv       = confluence["overall_score"]
            _conv     = confluence["conviction"]

            _sent1_parts = [_driver_phrase(d) for d in _top]
            if len(_sent1_parts) == 1:
                _drivers_str = _sent1_parts[0]
            elif len(_sent1_parts) == 2:
                _drivers_str = f"{_sent1_parts[0]} and {_sent1_parts[1]}"
            else:
                _drivers_str = f"{_sent1_parts[0]}, {_sent1_parts[1]}, and {_sent1_parts[2]}"

            _bull_d = [d for d in _top if d["status"] == "bullish"]
            _bear_d = [d for d in _top if d["status"] == "bearish"]

            if _case_str == "BULL":
                _tone = "bullish" if len(_bull_d) >= len(_bear_d) else "mixed-bullish"
            elif _case_str == "BEAR":
                _tone = "bearish" if len(_bear_d) >= len(_bull_d) else "mixed-bearish"
            else:
                _tone = "neutral"

            _total_drivers = len(_drivers)
            _sent2 = (
                f"{_total_drivers} statistically significant signal{'s' if _total_drivers != 1 else ''} "
                f"currently {_tone} — conviction is **{_conv}**."
            )

            _expl_color = "#1B5E20" if case == "BULL" else ("#7B1010" if case == "BEAR" else "#8B7355")
            st.markdown(
                f'<div style="background:#FAFAFA;border-left:4px solid {_expl_color};'
                f'border:1px solid #E0E0E0;border-radius:6px;padding:14px 18px;'
                f'margin:12px 0;font-family:Georgia,serif;">'
                f'<div style="font-size:0.70rem;text-transform:uppercase;letter-spacing:0.08em;'
                f'color:#8B7355;margin-bottom:6px;">WHY THIS SCORE</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.markdown(f"{ticker_input} scores **{_sv:.0f}** ({_case_str}) primarily because {_drivers_str}. {_sent2}")
    except Exception:
        pass  # Never crash the page if explainer fails

    # ── Score History ─────────────────────────────────────────────────────────────
    _score_hist = get_score_history(ticker_input, days=180)
    if len(_score_hist) >= 2:
        st.markdown("##### Score History")
        _hist_dates  = [row["snapshot_date"] for row in _score_hist]
        _hist_scores = [row["score"] for row in _score_hist]
        _fig_hist = go.Figure(go.Scatter(
            x=_hist_dates, y=_hist_scores, mode="lines+markers",
            line=dict(color="#1C2B4A", width=2.5),
            marker=dict(size=6, color="#B8860B"),
            hovertemplate="%{x}: score=%{y:.1f}<extra></extra>",
        ))
        _fig_hist.add_hline(y=65, line_dash="dot", line_color="#1B5E20", opacity=0.4)
        _fig_hist.add_hline(y=35, line_dash="dot", line_color="#7B1010", opacity=0.4)
        _fig_hist.update_layout(
            height=200, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
            xaxis=dict(showgrid=False, tickfont=dict(color="#6B6560")),
            yaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560"),
                       title="Confluence Score", range=[0, 100]),
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(_fig_hist, use_container_width=True)
        st.caption(
            f"{len(_score_hist)} recorded day(s) for {ticker_input} — built up only from actual visits to "
            "this page (this app has no scheduler to snapshot every ticker daily), so a short or gappy "
            "history reflects real traffic, not a bug."
        )
    else:
        st.caption(
            f"Score history for {ticker_input}: {len(_score_hist)} day(s) recorded so far — comes back "
            "and builds over time as this ticker gets viewed; today's view was just recorded."
        )

    # ── Sector-Relative Percentile ────────────────────────────────────────────────
    _sector_pct = compute_sector_percentile(ticker_input, score_val)
    if _sector_pct.get("error") is None:
        _pct = _sector_pct["percentile"]
        _pct_color = "#1B5E20" if _pct >= 65 else ("#7B1010" if _pct <= 35 else "#8B7355")
        st.markdown(
            f'<div style="padding:10px 16px;border-left:4px solid {_pct_color};background:#FAF7F0;margin:8px 0;">'
            f'<span style="font-weight:700;color:{_pct_color};">{ticker_input} sits at the '
            f'{_pct:.0f}th percentile among {_sector_pct["n_peers"]} sector peers</span> '
            f'<span style="color:#6B6560;">(score {score_val:.0f} vs. sector peer average '
            f'{_sector_pct["sector_avg"]:.0f})</span></div>',
            unsafe_allow_html=True,
        )
        with st.expander("Which peers, and as of when?"):
            st.caption(
                "Peer scores are each peer's MOST RECENTLY RECORDED score, not a live recomputation "
                "(see utils/score_history.py) -- two peers shown here may be from different days, "
                "since this site has no scheduler to re-score every ticker daily, only what's actually "
                "been viewed."
            )
            st.dataframe(
                pd.DataFrame(_sector_pct["peer_scores"]), use_container_width=True, hide_index=True,
            )
    else:
        st.caption(f"Sector percentile not yet available for {ticker_input}: {_sector_pct['error']}.")

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
        price_chart_box = st.container(border=True)
        with price_chart_box:
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

            # A clean, solid, Webull-style line chart -- deliberately NOT a
            # candlestick. The previous version fabricated fake open/high/low
            # values as a fixed +/-0.2%-0.5% offset from the single Close
            # price we actually have (fetch_price() only returns daily Close,
            # no real OHLC data), which at any real zoom level renders as a
            # scattered cloud of barely-visible dots, not a clean candle --
            # confirmed directly against the live site, not assumed. A
            # smooth, gap-free, solid line plotted from the same real Close
            # series is both more honest about what data this actually is
            # AND the more professional-looking choice.
            fig_price = go.Figure(go.Scatter(
                x=price_view.index, y=price_view.values,
                mode="lines", line=dict(color="#B8860B", width=2.5, shape="spline", smoothing=0.3),
                fill="tozeroy", fillcolor="rgba(184,134,11,0.08)",
                name=ticker_input,
            ))

            # 50-day and 200-day MAs (from full series, trimmed to view window).
            # Solid, thin, distinct colors -- a dashed/dotted overlay reads as
            # "less real" than the data; Webull-style charts use solid lines
            # for moving averages too, just thinner and a different color than
            # the price line itself, which is enough to tell them apart.
            if len(price_series) >= 50 and price_period not in ("1D", "5D"):
                ma50 = price_series.rolling(50).mean()
                ma50_view = ma50[ma50.index >= price_view.index[0]]
                fig_price.add_trace(go.Scatter(
                    x=ma50_view.index, y=ma50_view.values, name="50-day MA",
                    mode="lines", line=dict(color="#1C2B4A", width=1.5, shape="spline", smoothing=0.3),
                ))
            if len(price_series) >= 200 and price_period in ("1Y", "2Y", "YTD", "ALL"):
                ma200 = price_series.rolling(200).mean()
                ma200_view = ma200[ma200.index >= price_view.index[0]]
                fig_price.add_trace(go.Scatter(
                    x=ma200_view.index, y=ma200_view.values, name="200-day MA",
                    mode="lines", line=dict(color="#7B1010", width=1.5, shape="spline", smoothing=0.3),
                ))

            # ── Earnings date markers ──────────────────────────────────────
            # Vertical dashed lines on the price chart for each earnings date
            # that falls inside the current view window.
            # Color coding:
            #   Gold (#B8860B)  — upcoming / date not yet reported
            #   Green (#1B5E20) — reported and beat (surprise > 0)
            #   Red (#7B1010)   — reported and missed (surprise < 0)
            #   Grey            — reported with no surprise data
            # Wrapped in try/except: a failed fetch never breaks the chart.
            try:
                _earnings_data = fetch_earnings_dates(ticker_input)
                _view_start = price_view.index[0]
                _view_end   = price_view.index[-1]
                # Make view bounds timezone-naive for comparison
                if hasattr(_view_start, "tzinfo") and _view_start.tzinfo is not None:
                    _view_start = _view_start.tz_localize(None)
                    _view_end   = _view_end.tz_localize(None)

                for _e in _earnings_data:
                    _e_ts = pd.Timestamp(_e["date"])
                    # Include upcoming dates up to 90 days beyond chart end
                    if _e_ts < _view_start - pd.Timedelta(days=5):
                        continue
                    if _e_ts > _view_end + pd.Timedelta(days=90):
                        continue

                    if not _e["reported"]:
                        _ec = "#B8860B"        # upcoming — gold
                        _ann = "Earnings ★"
                    elif _e["surprise_pct"] is None:
                        _ec = "#8B7355"        # reported, no surprise data — tan
                        _ann = "E"
                    elif _e["surprise_pct"] >= 0:
                        _ec = "#1B5E20"        # beat — green
                        _ann = f"E +{_e['surprise_pct']:.0f}%"
                    else:
                        _ec = "#7B1010"        # miss — red
                        _ann = f"E {_e['surprise_pct']:.0f}%"

                    fig_price.add_vline(
                        x=str(_e["date"]),
                        line_dash="dash",
                        line_color=_ec,
                        line_width=1.5,
                        opacity=0.65,
                        annotation_text=_ann,
                        annotation_position="top",
                        annotation_font_size=9,
                        annotation_font_color=_ec,
                    )
            except Exception:
                pass  # Never let an earnings fetch failure break the price chart

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
                    Auto-refreshes every 60s independent of the rest of the page.
                    Shows regular session price + delta, and pre/post market price
                    when available (market_state PRE or POST), with color-coded badge.
                    """
                    q = fetch_live_quote(ticker)
                    if q["price"] is not None:
                        delta = f"{q['pct_change']:+.2f}%" if q["pct_change"] is not None else None
                        st.metric("Current Price", f"${q['price']:.2f}", delta=delta)

                        # Pre/post market display
                        _mst = q.get("market_state")
                        _pre_p   = q.get("pre_price")
                        _pre_c   = q.get("pre_change_pct")
                        _post_p  = q.get("post_price")
                        _post_c  = q.get("post_change_pct")

                        if _mst == "PRE" and _pre_p is not None:
                            _pre_color = "#1B5E20" if (_pre_c or 0) >= 0 else "#7B1010"
                            _pre_sym   = "▲" if (_pre_c or 0) >= 0 else "▼"
                            st.markdown(
                                f'<div style="background:#EEF3FA;border-radius:4px;padding:4px 10px;'
                                f'font-family:Georgia,serif;font-size:0.78rem;margin-top:2px;">'
                                f'<span style="color:#8B7355;font-weight:600;">PRE-MARKET</span> &nbsp;'
                                f'<span style="color:{_pre_color};font-weight:700;">'
                                f'${_pre_p:.2f} &nbsp;{_pre_sym} {abs(_pre_c):.2f}%</span></div>',
                                unsafe_allow_html=True,
                            )
                        elif _mst == "POST" and _post_p is not None:
                            _post_color = "#1B5E20" if (_post_c or 0) >= 0 else "#7B1010"
                            _post_sym   = "▲" if (_post_c or 0) >= 0 else "▼"
                            st.markdown(
                                f'<div style="background:#FBF8F0;border-radius:4px;padding:4px 10px;'
                                f'font-family:Georgia,serif;font-size:0.78rem;margin-top:2px;">'
                                f'<span style="color:#8B7355;font-weight:600;">AFTER-HOURS</span> &nbsp;'
                                f'<span style="color:{_post_color};font-weight:700;">'
                                f'${_post_p:.2f} &nbsp;{_post_sym} {abs(_post_c):.2f}%</span></div>',
                                unsafe_allow_html=True,
                            )
                        st.caption("LIVE · updates every 60s")
                    else:
                        st.metric("Current Price", f"${fallback_price:.2f}")
                        st.caption("Last close (live quote unavailable)")

                with p1:
                    _render_live_price(ticker_input, current_p)

                p2.metric("52-Week High",  f"${high_52w:.2f}", delta=f"{pct_from_high:+.1f}%")
                p3.metric("52-Week Low",   f"${low_52w:.2f}",  delta=f"{pct_from_low:+.1f}%")
                p4.metric("YTD Return",    f"{ret_ytd:+.1f}%")

        # ── Volume + RSI ─────────────────────────────────────────────────────────
        # Same `price_period` selector and `price_view` window as the price
        # chart above -- deliberately not a second, separate timeframe
        # control, so switching one switches all three charts together.
        _vol_end = datetime.now().strftime("%Y-%m-%d")
        _vol_start = (datetime.now() - timedelta(days=365 * 15)).strftime("%Y-%m-%d")
        volume_series = fetch_volume(ticker_input, _vol_start, _vol_end)

        vol_col, rsi_col = st.columns(2)

        # Native bordered containers (st.container(border=True)) around
        # each chart -- per explicit user request for a more professional,
        # boxed look, matching the same treatment given to the price chart
        # above and each Watchlist row.
        with vol_col, st.container(border=True):
            st.markdown("##### Volume")
            if not volume_series.empty:
                vol_view = volume_series[volume_series.index >= price_view.index[0]]
                if vol_view.empty:
                    vol_view = volume_series
                _vol_avg = volume_series.tail(50).mean() if len(volume_series) >= 50 else volume_series.mean()
                _vol_colors = ["#1B5E20" if v >= _vol_avg else "#8B7355" for v in vol_view.values]
                fig_vol = go.Figure(go.Bar(
                    x=vol_view.index, y=vol_view.values, marker_color=_vol_colors,
                    hovertemplate="%{x|%Y-%m-%d}: %{y:,.0f}<extra></extra>",
                ))
                fig_vol.add_hline(y=_vol_avg, line_dash="dot", line_color="#1C2B4A", opacity=0.5,
                                   annotation_text="50-day avg", annotation_font_size=10)
                fig_vol.update_layout(
                    height=220, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
                    xaxis=dict(showgrid=False, tickfont=dict(color="#6B6560", size=10)),
                    yaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560", size=10)),
                    margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
                )
                st.plotly_chart(fig_vol, use_container_width=True)
                st.caption(
                    f"Bars colored green when above the trailing 50-day average volume "
                    f"({_vol_avg:,.0f}), tan when below — a rough proxy for unusually active days."
                )
            else:
                st.info(f"Volume data unavailable for {ticker_input}.")

        with rsi_col, st.container(border=True):
            st.markdown("##### RSI (14-day)")
            if len(price_series.dropna()) >= 15:
                rsi_full = compute_rsi(price_series, period=14)
                rsi_view = rsi_full[rsi_full.index >= price_view.index[0]]
                if rsi_view.dropna().empty:
                    rsi_view = rsi_full
                fig_rsi = go.Figure(go.Scatter(
                    x=rsi_view.index, y=rsi_view.values, mode="lines",
                    line=dict(color="#B8860B", width=2, shape="spline", smoothing=0.3),
                    hovertemplate="%{x|%Y-%m-%d}: RSI=%{y:.1f}<extra></extra>",
                ))
                fig_rsi.add_hline(y=70, line_dash="dot", line_color="#7B1010", opacity=0.6,
                                   annotation_text="Overbought (70)", annotation_font_size=10)
                fig_rsi.add_hline(y=30, line_dash="dot", line_color="#1B5E20", opacity=0.6,
                                   annotation_text="Oversold (30)", annotation_font_size=10)
                fig_rsi.update_layout(
                    height=220, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
                    xaxis=dict(showgrid=False, tickfont=dict(color="#6B6560", size=10)),
                    yaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560", size=10),
                               range=[0, 100]),
                    margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
                )
                st.plotly_chart(fig_rsi, use_container_width=True)
                _latest_rsi = rsi_full.dropna()
                if not _latest_rsi.empty:
                    _rsi_val = _latest_rsi.iloc[-1]
                    _rsi_read = "Overbought" if _rsi_val >= 70 else ("Oversold" if _rsi_val <= 30 else "Neutral")
                    st.caption(
                        f"Latest reading: {_rsi_val:.1f} ({_rsi_read}). Wilder's standard RSI — a "
                        "momentum indicator, not a buy/sell signal on its own; extreme readings can "
                        "persist during strong trends rather than immediately reversing."
                    )
            else:
                st.info(f"Not enough price history yet to compute RSI for {ticker_input}.")

    # ── Catalysts & News ──────────────────────────────────────────────────────────
    # Earnings timeline + recent headlines — both sourced from yfinance, no extra
    # API key required. Placed here (after price/volume/RSI, before prediction
    # model) so a user reading the chart can immediately see WHAT drove recent
    # price moves before looking at the forward model's probabilities.
    st.markdown('<div class="section-header">CATALYSTS & NEWS</div>', unsafe_allow_html=True)

    _cat_col, _news_col = st.columns([1, 2])

    with _cat_col:
        st.markdown("##### Earnings")
        try:
            _earn = fetch_earnings_dates(ticker_input)   # cached — same call as price chart above
            if _earn:
                _today = datetime.now().date()
                for _e in sorted(_earn, key=lambda x: x["date"], reverse=True):
                    _days_delta = (_e["date"] - _today).days
                    if not _e["reported"]:
                        # Upcoming
                        _when = (f"in {_days_delta}d" if _days_delta > 0
                                 else "Today" if _days_delta == 0
                                 else f"{abs(_days_delta)}d ago (est.)")
                        _bg = "#FFF8E1"
                        _border = "#B8860B"
                        _badge = f'<span style="background:#B8860B;color:white;font-size:0.68rem;padding:1px 6px;border-radius:3px;font-weight:700;">UPCOMING</span>'
                        _body = f'<div style="font-size:0.78rem;color:#6B6560;margin-top:4px;">{_when}</div>'
                        if _e["eps_estimate"] is not None:
                            _body += f'<div style="font-size:0.78rem;color:#6B6560;">Est. EPS: <b>{_e["eps_estimate"]:+.2f}</b></div>'
                    else:
                        # Reported
                        _sp = _e["surprise_pct"]
                        if _sp is None:
                            _border = "#8B7355"; _bg = "#F5F0E8"
                            _badge = '<span style="font-size:0.68rem;color:#8B7355;font-weight:600;">REPORTED</span>'
                            _beat_txt = ""
                        elif _sp >= 0:
                            _border = "#1B5E20"; _bg = "#F0F8F0"
                            _badge = f'<span style="background:#1B5E20;color:white;font-size:0.68rem;padding:1px 6px;border-radius:3px;font-weight:700;">BEAT +{_sp:.1f}%</span>'
                            _beat_txt = ""
                        else:
                            _border = "#7B1010"; _bg = "#FDF0F0"
                            _badge = f'<span style="background:#7B1010;color:white;font-size:0.68rem;padding:1px 6px;border-radius:3px;font-weight:700;">MISS {_sp:.1f}%</span>'
                            _beat_txt = ""
                        _when = f"{abs(_days_delta)}d ago" if abs(_days_delta) < 365 else _e["date"].strftime("%b %d, %Y")
                        _act_str = f'<b>{_e["eps_actual"]:+.2f}</b>' if _e["eps_actual"] is not None else "—"
                        _est_str = f'{_e["eps_estimate"]:+.2f}' if _e["eps_estimate"] is not None else "—"
                        _body = (
                            f'<div style="font-size:0.78rem;color:#6B6560;margin-top:4px;">{_when}</div>'
                            f'<div style="font-size:0.78rem;color:#6B6560;">EPS: {_act_str} <span style="color:#9E9E8E;">(est {_est_str})</span></div>'
                        )

                    st.markdown(f"""
                    <div style="background:{_bg};border-left:3px solid {_border};border-radius:4px;
                                padding:8px 12px;margin-bottom:8px;font-family:Georgia,serif;">
                        <div style="font-size:0.80rem;font-weight:700;color:#1A1612;">
                            {_e["date"].strftime("%b %d, %Y")} &nbsp; {_badge}
                        </div>
                        {_body}
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.caption("No earnings date data available for this ticker.")
        except Exception as _earn_err:
            st.caption(f"Earnings data unavailable: {_earn_err}")

    with _news_col:
        st.markdown("##### Recent Headlines")
        try:
            _news_items = fetch_ticker_news(ticker_input)
            if _news_items:
                _now_utc = pd.Timestamp.now(tz="UTC")
                for _n in _news_items:
                    _title = _n["title"][:110] + "…" if len(_n["title"]) > 110 else _n["title"]
                    _pub   = _n["publisher"] or ""
                    _url   = _n["url"] or ""

                    # Relative time display
                    _pub_dt = _n["published_at"]
                    if pd.notna(_pub_dt):
                        _age = _now_utc - _pub_dt.tz_convert("UTC")
                        _hrs = int(_age.total_seconds() // 3600)
                        if _hrs < 1:
                            _time_str = "Just now"
                        elif _hrs < 24:
                            _time_str = f"{_hrs}h ago"
                        else:
                            _time_str = f"{_hrs // 24}d ago"
                    else:
                        _time_str = ""

                    _meta = " · ".join(filter(None, [_pub, _time_str]))

                    if _url:
                        _title_html = f'<a href="{_url}" target="_blank" style="color:#1C2B4A;text-decoration:none;font-weight:600;">{_title}</a>'
                    else:
                        _title_html = f'<span style="color:#1C2B4A;font-weight:600;">{_title}</span>'

                    st.markdown(f"""
                    <div style="padding:8px 0 8px 0;border-bottom:1px solid #E8E0CE;font-family:Georgia,serif;">
                        <div style="font-size:0.85rem;line-height:1.4;">{_title_html}</div>
                        <div style="font-size:0.72rem;color:#9E9E8E;margin-top:3px;">{_meta}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.caption("No recent headlines found for this ticker.")
        except Exception as _news_err:
            st.caption(f"News unavailable: {_news_err}")

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

    # ── What Would Change My Mind ─────────────────────────────────────────────────
    # Goldman-style conditional reasoning: identify the tripwires that would
    # invalidate the current bull or bear case. Built from live signal data —
    # find the weakest bullish signals (most likely to flip) and the neutral
    # signals closest to going bearish, then express them as clear conditions.
    try:
        _case = confluence.get("case", "NEUTRAL")
        _all_ticker_sigs = _full.get("signal_scores", {})

        # Weakest bulls: bullish signals with the lowest score (closest to flipping)
        _weak_bulls = sorted(
            [(sid, sv) for sid, sv in _all_ticker_sigs.items()
             if sv.get("status") == "bullish" and not sv.get("error")],
            key=lambda x: x[1].get("score", 50)
        )[:2]
        # Closest bears: neutral signals closest to going bearish (score nearest to 35)
        _near_bears = sorted(
            [(sid, sv) for sid, sv in _all_ticker_sigs.items()
             if sv.get("status") == "neutral" and not sv.get("error")
             and sv.get("score", 50) < 50],
            key=lambda x: x[1].get("score", 50)
        )[:2]
        # Mirror for bear case
        _weak_bears = sorted(
            [(sid, sv) for sid, sv in _all_ticker_sigs.items()
             if sv.get("status") == "bearish" and not sv.get("error")],
            key=lambda x: -x[1].get("score", 50)
        )[:2]
        _near_bulls = sorted(
            [(sid, sv) for sid, sv in _all_ticker_sigs.items()
             if sv.get("status") == "neutral" and not sv.get("error")
             and sv.get("score", 50) > 50],
            key=lambda x: -x[1].get("score", 50)
        )[:2]

        _tripwire_lines = []
        if _case == "BULL" or confluence.get("bull_count", 0) >= confluence.get("bear_count", 0):
            _header = "🔁 What Would Change the Bull Case"
            for sid, sv in _weak_bulls:
                nm = sv.get("name", sid)
                sc = sv.get("score", 50)
                _tripwire_lines.append(
                    f"<b>{nm}</b> is the weakest bullish signal at {sc:.0f}/100 — "
                    f"a drop below ~35 would flip it bearish and weaken this setup."
                )
            for sid, sv in _near_bears:
                nm = sv.get("name", sid)
                sc = sv.get("score", 50)
                _tripwire_lines.append(
                    f"<b>{nm}</b> is neutral at {sc:.0f}/100 and trending lower — "
                    f"watch for a break below 35, which would add a bearish headwind."
                )
        else:
            _header = "🔁 What Would Change the Bear Case"
            for sid, sv in _weak_bears:
                nm = sv.get("name", sid)
                sc = sv.get("score", 50)
                _tripwire_lines.append(
                    f"<b>{nm}</b> is the weakest bearish signal at {sc:.0f}/100 — "
                    f"a recovery above ~65 would flip it bullish and soften the headwinds."
                )
            for sid, sv in _near_bulls:
                nm = sv.get("name", sid)
                sc = sv.get("score", 50)
                _tripwire_lines.append(
                    f"<b>{nm}</b> is neutral at {sc:.0f}/100 but leaning higher — "
                    f"a break above 65 would add a meaningful tailwind for the bull case."
                )

        if _tripwire_lines:
            _items_html = "".join(
                f'<div style="display:flex;gap:10px;margin-bottom:8px;">'
                f'<span style="color:#B8860B;font-size:1.0rem;flex-shrink:0;">◈</span>'
                f'<div style="font-size:0.80rem;color:#4A4440;line-height:1.6;">{line}</div>'
                f'</div>'
                for line in _tripwire_lines
            )
            st.markdown(
                f'<div style="background:#FFF8E7;border-radius:8px;padding:16px 18px;'
                f'margin:14px 0;border-left:4px solid #B8860B;font-family:Georgia,serif;">'
                f'<div style="font-size:0.72rem;font-weight:700;color:#B8860B;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">'
                f'{_header}</div>'
                f'{_items_html}'
                f'<div style="font-size:0.65rem;color:#9E9E8E;margin-top:8px;">'
                f'Conditions based on current signal readings · thresholds are directional, not precise price targets</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    except Exception:
        pass

    # ── Playbook Mode ─────────────────────────────────────────────────────────────
    # The last N times this ticker's confluence score crossed 70+ (or dropped
    # below 35), what happened to the stock price 4, 8, 12 weeks later?
    # Turns the score history into a miniature per-ticker track record.
    with st.expander("📖 Playbook — historical setups at this score level"):
        try:
            _ph = get_score_history(ticker_input, days=365)
            if len(_ph) < 5:
                st.info("Not enough score history yet for a playbook. Come back after this ticker has been viewed a few more times over the coming weeks.")
            else:
                import yfinance as yf
                import pandas as pd
                _crossing_threshold = 70 if confluence["case"] == "BULL" else 35
                _direction          = "above" if confluence["case"] == "BULL" else "below"
                _color              = "#1B5E20" if confluence["case"] == "BULL" else "#7B1010"

                # Find dates where score crossed the threshold
                _crossings = []
                for i in range(1, len(_ph)):
                    prev_s = float(_ph[i-1]["score"] or 50)
                    curr_s = float(_ph[i]["score"]   or 50)
                    if confluence["case"] == "BULL" and prev_s < _crossing_threshold <= curr_s:
                        _crossings.append(_ph[i]["snapshot_date"])
                    elif confluence["case"] != "BULL" and prev_s > _crossing_threshold >= curr_s:
                        _crossings.append(_ph[i]["snapshot_date"])

                if not _crossings:
                    st.info(f"Score hasn't crossed {_crossing_threshold} {_direction} yet in recorded history. The playbook will populate as history accumulates.")
                else:
                    # Fetch 1 year of price history once
                    _px = yf.download(ticker_input, period="2y", auto_adjust=True, progress=False)
                    if _px.empty:
                        st.info("Price data unavailable for playbook calculations.")
                    else:
                        _px_close = _px["Close"].squeeze()
                        _playbook_rows = []
                        for dt_str in _crossings[-5:]:  # last 5 crossings max
                            try:
                                _dt = pd.Timestamp(dt_str)
                                _entry_price = float(_px_close.asof(_dt))
                                _row = {"Setup Date": dt_str, "Score at Crossing": None}
                                for snap in _ph:
                                    if snap["snapshot_date"] == dt_str:
                                        _row["Score at Crossing"] = f"{float(snap['score']):.0f}"
                                        break
                                for weeks, label in [(4, "+4w"), (8, "+8w"), (12, "+12w")]:
                                    _fwd = _dt + pd.Timedelta(weeks=weeks)
                                    if _fwd <= _px_close.index[-1]:
                                        _fwd_price = float(_px_close.asof(_fwd))
                                        _ret = (_fwd_price / _entry_price - 1) * 100
                                        _row[label] = f"{_ret:+.1f}%"
                                    else:
                                        _row[label] = "pending"
                                _playbook_rows.append(_row)
                            except Exception:
                                continue

                        if _playbook_rows:
                            st.markdown(
                                f'<div style="font-size:0.78rem;color:#4A4440;margin-bottom:10px;">'
                                f'The last <b>{len(_playbook_rows)}</b> time(s) '
                                f'<b style="color:{_color}">{ticker_input}</b> scored '
                                f'{_crossing_threshold}+ {_direction}, forward returns were:</div>',
                                unsafe_allow_html=True,
                            )
                            _pb_df = pd.DataFrame(_playbook_rows)
                            st.dataframe(_pb_df, use_container_width=True, hide_index=True)
                            st.caption("⚠️ Small sample — treat as illustrative context, not statistical proof. Score history only accumulates when this page is visited.")
                        else:
                            st.info("Could not compute forward returns for the crossing dates found.")
        except Exception as _pb_err:
            st.caption(f"Playbook unavailable: {_pb_err}")

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

elif section == "Insider & Short Interest":
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
        # Insider Cluster Badge — detect 2+ purchases within 21 days
        # (21-day window is tighter and more actionable than the 180-day scoring window)
        try:
            import pandas as pd
            _tx_buys = _insider_tx_early[_insider_tx_early.get("code", pd.Series()) == "P"].copy() \
                if hasattr(_insider_tx_early, "get") else \
                _insider_tx_early[_insider_tx_early["code"] == "P"].copy()
            if not _tx_buys.empty and "date" in _tx_buys.columns:
                from datetime import datetime, timedelta
                _cutoff_21 = pd.Timestamp.now() - pd.Timedelta(days=21)
                _recent_buys = _tx_buys[_tx_buys["date"] >= _cutoff_21]
                _n_cluster = _recent_buys["insider"].nunique() if "insider" in _recent_buys.columns \
                    else len(_recent_buys)
                if _n_cluster >= 2:
                    st.markdown(
                        f'<div style="background:#EDF7ED;border-radius:7px;padding:10px 14px;'
                        f'margin-bottom:10px;border-left:4px solid #1B5E20;font-family:Georgia,serif;">'
                        f'<span style="font-size:1.1rem;">🔥</span> '
                        f'<b style="color:#1B5E20;font-size:0.88rem;">INSIDER CLUSTER BUY</b> — '
                        f'<span style="font-size:0.82rem;color:#4A4440;">'
                        f'{_n_cluster} distinct insiders made open-market purchases in the last 21 days. '
                        f'Cluster buying (multiple independent insiders, no offsetting sales) is '
                        f'among the strongest signals in academic insider-trading research.</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        except Exception:
            pass

        if _insider_score["cluster_bonus_applied"]:
            st.markdown(f'<span style="color:{ins_color};font-weight:700;">Cluster pattern detected (180d)</span> — 3+ insiders moved the same direction with no one going the other way.', unsafe_allow_html=True)

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


elif section == "13F & Federal Contracts":
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


elif section == "Deep Correlation Scan":
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

    # Sort signals by correlation strength so the selectbox defaults to the
    # MOST correlated signal rather than whichever happened to be listed first
    # in the config. corr_info is already computed for all ~40 signals above
    # (via compute_full_ticker_score, which now evaluates the full library
    # thanks to the resolve_ticker_meta fix) -- no extra work here, just
    # reordering the keys before building the options dict.
    # Sort key: significant signals first (p<0.05), then by |r| descending
    # within each group so the strongest relationship surfaces automatically.
    _corr_ranked_sids = sorted(
        [sid for sid in relevant_sig_ids if sid in SIGNALS],
        key=lambda s: (
            0 if corr_info.get(s, {}).get("significant") else 1,
            -abs(corr_info.get(s, {}).get("r", 0.0)),
        ),
    )
    # Label significant signals with their r value so the user can see
    # correlation strength at a glance while browsing the dropdown.
    def _sig_label(sid: str) -> str:
        ci = corr_info.get(sid, {})
        name = SIGNALS[sid]["name"]
        r = ci.get("r", 0.0)
        if ci.get("significant"):
            return f"{name}  (r={r:+.2f} ✓)"
        return name

    deep_sig_options = {sid: _sig_label(sid) for sid in _corr_ranked_sids}
    if _has_insider_signal:
        deep_sig_options["_insider_activity"] = "Insider Activity — validated lead-time scan"
    if _has_short_interest_signal:
        deep_sig_options["_short_interest"] = "Short Interest — validated lead-time scan"

    is_alt_data_scan = False
    if deep_sig_options:
        dc1, dc2 = st.columns([2, 1])
        with dc1:
            deep_sig_id = st.selectbox(
                "Signal to deep-scan (sorted by correlation strength):",
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
                # Kept for the lag-decay check below -- reuses this exact
                # extended-history series rather than re-fetching it.
                st.session_state["_alt_lag_signal_series"] = _alt_series

        if (
            "_alt_lag_result" in st.session_state
            and st.session_state.get("_alt_lag_signal_id") == deep_sig_id
        ):
            render_validated_lag_scan(
                st.session_state["_alt_lag_result"],
                st.session_state["_alt_lag_reliability"],
                st.session_state.get("_alt_lag_pooled"),
            )

            st.divider()
            st.markdown("##### Is this signal's lead time stable, or is it decaying?")
            st.caption(
                "Uses the same extended fetch already pulled above for the validated scan -- no extra "
                "network calls. Honest caveat specific to alt-data signals: insider/short-interest "
                "history is capped well under what macro/FRED signals have (FINRA's API caps at 50 "
                "rows; EDGAR fetches are limited to a bounded number of filings), so this trend view "
                "has fewer, thinner windows here than it would for a longer-history macro signal -- "
                "weigh n_windows accordingly, shown below."
            )
            if st.button("Check lead-time stability over time", key="run_alt_lag_decay"):
                _alt_series_cur = st.session_state.get("_alt_lag_signal_series")
                with st.spinner("Scanning each trailing window…"):
                    if _alt_series_cur is None or _alt_series_cur.empty or price_series.empty:
                        _alt_decay_result = {"error": "Insufficient data for this ticker"}
                    else:
                        _alt_decay_result = compute_rolling_best_lag(
                            _alt_series_cur, price_series, window_weeks=52, step_weeks=8, scan_max_lag=16,
                        )
                    st.session_state["_alt_decay_result"] = _alt_decay_result
                    st.session_state["_alt_decay_sig_id"] = deep_sig_id

            if (
                "_alt_decay_result" in st.session_state
                and st.session_state.get("_alt_decay_sig_id") == deep_sig_id
            ):
                render_lag_decay_chart(st.session_state["_alt_decay_result"])

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
        st.markdown("##### Is this signal's lead time stable, or is it decaying?")
        st.caption(
            "The data above uses the page's standard 2-year window, which isn't enough history to "
            "track a trend in the lead time itself. This re-fetches a longer history (up to 10 years, "
            "where FRED/EIA actually has it) specifically to check whether the lag found above has been "
            "stable over time or is compressing/lengthening — institutional desks call this \"alpha "
            "decay.\" Exploratory, not a validated finding (see the result for exactly why)."
        )
        if st.button(f"Check lead-time stability for {deep_cfg.get('name', deep_sig_id)}", key="run_macro_lag_decay"):
            with st.spinner("Fetching extended history and scanning each trailing window…"):
                _decay_end = datetime.now().strftime("%Y-%m-%d")
                _decay_start = (datetime.now() - timedelta(days=365 * 10)).strftime("%Y-%m-%d")
                try:
                    _decay_sig = fetch_signal_series(deep_cfg, _decay_start, _decay_end)
                except Exception:
                    _decay_sig = pd.Series(dtype=float)
                try:
                    _decay_price = fetch_price(ticker_input, _decay_start, _decay_end)
                except Exception:
                    _decay_price = pd.Series(dtype=float)

                if _decay_sig.empty or _decay_price.empty:
                    _decay_result = {"error": "Insufficient extended-history data for this ticker/signal pair"}
                else:
                    _decay_result = compute_rolling_best_lag(
                        _decay_sig, _decay_price, window_weeks=104, step_weeks=13, scan_max_lag=16,
                    )
                st.session_state["_macro_decay_result"] = _decay_result
                st.session_state["_macro_decay_sig_id"] = deep_sig_id

        if (
            "_macro_decay_result" in st.session_state
            and st.session_state.get("_macro_decay_sig_id") == deep_sig_id
        ):
            render_lag_decay_chart(st.session_state["_macro_decay_result"])


elif section == "Earnings Track Record":
    # ── Earnings Track Record ─────────────────────────────────────────────────
    # Compare what the Confluence Score said in the 7–45 days before each
    # earnings event vs what actually happened (EPS beat / miss / meet).
    # Data coverage is organic: score history accumulates only when someone
    # opens this ticker on Ticker Deep Dive, so early-stage tickers may have
    # sparse history. We're honest about that here.
    st.markdown("### Pre-Earnings Signal Track Record")
    st.caption(
        f"Did the Confluence Score correctly anticipate earnings outcomes for **{ticker_input}**? "
        "Shows score snapshots recorded 7–45 days before each past earnings date vs actual EPS result. "
        "History accumulates as this ticker is viewed — sparse for tickers not yet frequently visited."
    )

    try:
        _trk_earnings = fetch_earnings_dates(ticker_input)
        _trk_history  = get_score_history(ticker_input, days=365)

        # Build a lookup: date → snapshot row
        import datetime as _datetime_mod
        _trk_snap_map: dict = {}
        for _row in _trk_history:
            try:
                _d = _datetime_mod.date.fromisoformat(_row["snapshot_date"])
                _trk_snap_map[_d] = _row
            except Exception:
                pass

        _trk_past = [e for e in _trk_earnings if e.get("reported") and e.get("eps_actual") is not None]
        _trk_upcoming = [e for e in _trk_earnings if not e.get("reported")]

        # For each past earnings, find most recent snapshot in 7–45 day pre-window
        _trk_rows = []
        for _e in _trk_past:
            _earn_d = _e["date"]
            if isinstance(_earn_d, str):
                _earn_d = _datetime_mod.date.fromisoformat(_earn_d)
            _best_snap = None
            _best_delta = None
            for _snap_d, _snap_row in _trk_snap_map.items():
                _delta = (_earn_d - _snap_d).days
                if 7 <= _delta <= 45:
                    if _best_delta is None or _delta < _best_delta:
                        _best_snap = _snap_row
                        _best_delta = _delta
            _trk_rows.append({"earnings": _e, "snap": _best_snap, "delta_days": _best_delta})

        # ── Upcoming earnings reminder ─────────────────────────────────────────
        if _trk_upcoming:
            _up = _trk_upcoming[-1]  # most recent upcoming
            _up_est = f"{_up['eps_estimate']:+.2f}" if _up.get("eps_estimate") is not None else "N/A"
            st.info(
                f"**Next earnings:** {_up['date']} — Consensus EPS estimate: **{_up_est}**  \n"
                "Current Confluence Score above may indicate signal posture heading in. "
                "This page will update after the event is reported."
            )

        # ── Track record table ────────────────────────────────────────────────
        _rows_with_data = [r for r in _trk_rows if r["snap"] is not None]
        _rows_no_data   = [r for r in _trk_rows if r["snap"] is None]

        if not _trk_past:
            st.info("No past earnings data available for this ticker.")
        elif not _rows_with_data:
            st.warning(
                "No pre-earnings score snapshots found yet. Score history accumulates "
                "each time this ticker is opened on Ticker Deep Dive. Check back after "
                "a few more views — especially in the 6 weeks before the next earnings date."
            )
        else:
            # Accuracy metrics
            _n_checked = 0
            _n_correct  = 0
            _n_neutral  = 0
            for _r in _rows_with_data:
                _score = _r["snap"]["score"]
                _surp  = _r["earnings"].get("surprise_pct")
                if _surp is None:
                    continue
                _n_checked += 1
                if _score >= 60:
                    _pred_dir = "bullish"
                elif _score <= 40:
                    _pred_dir = "bearish"
                else:
                    _pred_dir = "neutral"
                    _n_neutral += 1
                    continue
                _actual_dir = "bullish" if _surp > 0 else "bearish"
                if _pred_dir == _actual_dir:
                    _n_correct += 1

            _n_directional = _n_checked - _n_neutral
            _accuracy = (_n_correct / _n_directional * 100) if _n_directional > 0 else None

            # Summary banner
            _acc_color = "#1B5E20" if (_accuracy or 0) >= 60 else ("#7B1010" if (_accuracy or 0) < 45 else "#8B7355")
            _m1, _m2, _m3 = st.columns(3)
            _m1.metric("Earnings Events Checked", len(_rows_with_data))
            _m2.metric("Directional Calls Made", _n_directional)
            if _accuracy is not None:
                _m3.metric("Accuracy", f"{_accuracy:.0f}%",
                           delta="above coin-flip" if _accuracy >= 55 else "below coin-flip")
            else:
                _m3.metric("Accuracy", "—")

            st.caption(
                "⚠️ Small sample — interpret cautiously. Accuracy here is directional only "
                "(score ≥60 → predicts beat; ≤40 → predicts miss). Neutral scores (40–60) are excluded from accuracy."
            )
            st.markdown("")

            # Per-earnings rows
            for _r in sorted(_rows_with_data, key=lambda x: x["earnings"]["date"], reverse=True):
                _e    = _r["earnings"]
                _snap = _r["snap"]
                _earn_d = _e["date"]
                _score  = _snap["score"]
                _case   = _snap.get("case", "mixed")
                _delta  = _r["delta_days"]
                _surp   = _e.get("surprise_pct")
                _actual = _e.get("eps_actual")
                _est    = _e.get("eps_estimate")

                if _score >= 60:
                    _pred_dir = "bullish"
                    _pred_label = f"▲ Bullish ({_score:.0f})"
                    _pred_color = "#1B5E20"
                elif _score <= 40:
                    _pred_dir = "bearish"
                    _pred_label = f"▼ Bearish ({_score:.0f})"
                    _pred_color = "#7B1010"
                else:
                    _pred_dir = "neutral"
                    _pred_label = f"● Neutral ({_score:.0f})"
                    _pred_color = "#8B7355"

                if _surp is not None:
                    _actual_dir = "bullish" if _surp > 0 else ("bearish" if _surp < 0 else "neutral")
                    _outcome_label = (
                        f"✅ Beat (+{_surp:.1f}%)" if _surp > 0 else
                        f"❌ Miss ({_surp:.1f}%)" if _surp < 0 else
                        "● Met estimate"
                    )
                    _outcome_color = "#1B5E20" if _surp > 0 else ("#7B1010" if _surp < 0 else "#8B7355")
                    if _pred_dir != "neutral":
                        _matched = _pred_dir == _actual_dir
                        _match_label = "✅ Correct" if _matched else "❌ Wrong"
                        _match_color = "#1B5E20" if _matched else "#7B1010"
                    else:
                        _match_label = "— No call"
                        _match_color = "#8B7355"
                else:
                    _outcome_label = "No surprise data"
                    _outcome_color = "#9E9E8E"
                    _match_label = "—"
                    _match_color = "#9E9E8E"

                _eps_line = ""
                if _actual is not None and _est is not None:
                    _eps_line = f"EPS: **{_actual:+.2f}** actual vs **{_est:+.2f}** est"
                elif _actual is not None:
                    _eps_line = f"EPS: **{_actual:+.2f}** (no estimate available)"

                st.markdown(f"""
<div style="background:#FAF7F0;border:1px solid #D4C9B0;border-left:4px solid {_pred_color};
            border-radius:6px;padding:12px 16px;margin-bottom:8px;font-family:Georgia,serif;">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
        <div>
            <div style="font-size:0.70rem;color:#8B7355;letter-spacing:0.06em;">
                EARNINGS · {_earn_d}
            </div>
            <div style="font-size:0.85rem;color:#1A1612;margin-top:2px;">{_eps_line}</div>
        </div>
        <div style="display:flex;gap:20px;flex-wrap:wrap;">
            <div style="text-align:center;">
                <div style="font-size:0.65rem;color:#9E9E8E;letter-spacing:0.06em;">SCORE {_delta}d BEFORE</div>
                <div style="font-weight:700;color:{_pred_color};font-size:0.88rem;">{_pred_label}</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:0.65rem;color:#9E9E8E;letter-spacing:0.06em;">ACTUAL RESULT</div>
                <div style="font-weight:700;color:{_outcome_color};font-size:0.88rem;">{_outcome_label}</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:0.65rem;color:#9E9E8E;letter-spacing:0.06em;">CALL</div>
                <div style="font-weight:700;color:{_match_color};font-size:0.88rem;">{_match_label}</div>
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

        # Rows without snapshot data
        if _rows_no_data:
            with st.expander(f"{len(_rows_no_data)} earnings event(s) with no pre-earnings score snapshot"):
                for _r in _rows_no_data:
                    _e = _r["earnings"]
                    _surp = _e.get("surprise_pct")
                    _s_label = f"+{_surp:.1f}% beat" if (_surp or 0) > 0 else (f"{_surp:.1f}% miss" if _surp else "")
                    st.markdown(
                        f"- **{_e['date']}** — EPS: {_e.get('eps_actual', '?'):+.2f} "
                        f"({_s_label}) — *No score snapshot in 7–45 day pre-window*"
                    )

    except Exception as _trk_err:
        st.error(f"Could not load earnings track record: {_trk_err}")

    st.divider()
    if st.button("View full Track Record page →", key="goto_track_record_from_tdd"):
        st.switch_page("pages/13_Track_Record.py")
