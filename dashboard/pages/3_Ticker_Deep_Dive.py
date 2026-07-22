"""
Page 3 — Ticker Deep Dive
Full bull/bear case for any ticker:
  - All relevant signals scored + scored
  - Confluence score with conviction level
  - Federal contract award velocity (USASpending.gov)
  - SEC Form 4 insider transaction overlay
  - Narrative bull/bear case builder

Layout: split into focused sections via the shared sidebar section rail --
Overview (score, price, prediction model, bull/bear case, signal table,
export) / Insider & Short Interest / 13F & Federal Contracts / Deep
Correlation Scan -- instead of one ~1,350-line linear scroll. Chose
the section rail over st.tabs() deliberately: a live AppTest check
confirmed st.tabs() executes every tab body on every script run
regardless of which tab is visually selected (it's a pure CSS/display
mechanism), while branching on the rail's return value with
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
import time

_PAGE_STARTED_AT = time.perf_counter()

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from utils.config import SIGNALS, TICKERS, CATEGORIES, CURATED_FUNDS, THIRTEENF_CUSIP_TO_TICKER
from utils.conviction import get_conviction_context
from utils.fetchers import (
    fetch_price, fetch_signal_series, is_unavailable, fetch_volume,
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
from utils.ticker_score import resolve_ticker_meta
from utils.score_cache import (
    clear_full_score_result,
    clear_session_result,
    get_full_ticker_score,
    get_latest_compatible_full_snapshot,
    get_session_result,
    make_full_score_cache_key,
    set_session_result,
)
from utils.performance import record_timing
from utils.header import render_header, render_sidebar_base, render_page_header, render_guided_steps, go_to_ticker, ticker_chips, ticker_label, render_data_unavailable_banner, render_footer
from utils.analysis import compute_signal_confidence
from utils.theme import (
    confluence_gauge_svg, style_area_chart, style_chart,
    style_chart_secondary, style_distribution_chart,
    source_badge, inject_all_css, section_label, PLOTLY_CONFIG,
    PLOTLY_CONFIG_INTERACTIVE, render_disclaimer,
    render_educational_callout, signal_confidence_badge,
    chart_insight_caption,
)
from utils.card_generator import generate_signal_card
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
_tdd_section = render_sidebar_base(
    page_title="Ticker Deep Dive",
    sections=(
        "Overview",
        "Thesis Workspace",
        "Deep Correlation Scan",
        "Insider & Short Interest",
        "13F & Federal Contracts",
        "Earnings Track Record",
        "Earnings Sentiment",
    ),
    section_key="dive_section",
)
inject_all_css()

render_page_header(
    "Ticker Deep Dive",
    "Deep-dive analysis: signal correlations, score history, fundamentals, and catalysts.",
    icon="",
)

# Note: signal/price date ranges (START/END/PRICE_START) now live inside
# utils/ticker_score.compute_full_ticker_score() -- that's the single place
# both this page and the alert engine fetch from, so they can't drift apart.
STATUS_COLOR = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#6B7FBF", "no_data": "#8892AA"}
STATUS_EMOJI = {"bullish": "▲", "bearish": "▼", "neutral": "●", "no_data": "○"}


st.markdown("""
<div style="background:linear-gradient(135deg,rgba(124,58,237,0.08),rgba(0,200,224,0.06));
            border:1px solid rgba(124,58,237,0.22);border-radius:12px;
            padding:16px 22px;margin-bottom:16px;font-family:Inter,sans-serif;">
    <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
        <div style="flex:1;min-width:220px;">
            <div style="font-size:0.60rem;letter-spacing:0.14em;font-weight:700;color:#A78BFA;
                        margin-bottom:4px;">TICKER DEEP DIVE</div>
            <div style="font-size:0.82rem;color:#B8C0D4;line-height:1.6;">
                Type any ticker → get a <b style="color:#E8EEFF;">Confluence Score (0–100)</b> from
                43 live macro signals, a bull/bear case in plain English, insider activity, earnings
                catalysts, and signal-by-signal breakdown. Updated every 2 hours from primary sources.
            </div>
        </div>
        <div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0;">
            <span style="font-size:0.72rem;color:#00D566;background:rgba(0,213,102,0.08);
                         border:1px solid rgba(0,213,102,0.2);border-radius:6px;padding:3px 10px;">
                SEC EDGAR insider filings</span>
            <span style="font-size:0.72rem;color:#00C8E0;background:rgba(0,200,224,0.08);
                         border:1px solid rgba(0,200,224,0.2);border-radius:6px;padding:3px 10px;">
                FRED + EIA macro signals</span>
            <span style="font-size:0.72rem;color:#A78BFA;background:rgba(124,58,237,0.08);
                         border:1px solid rgba(124,58,237,0.2);border-radius:6px;padding:3px 10px;">
                FINRA short interest</span>
        </div>
    </div>
</div>
""".replace("43 live macro signals", f"{len(SIGNALS)} live macro signals"), unsafe_allow_html=True)

with st.expander("Detailed methodology — signal scoring, lead times, and validation"):
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

# ── First-visit onboarding callout ──────────────────────────────────────────
if not st.session_state.get("_tdd_onboarded"):
    render_guided_steps(
        "Turn a ticker into an evidence-backed research view",
        [
            (
                "Read the Confluence Score",
                "Use the 0–100 score as the first read: 65 or higher signals a macro tailwind, 35 or lower a headwind, and the middle range is mixed.",
            ),
            (
                "Confirm the evidence quality",
                "Review confidence and signal breadth before acting. Strong deviations with confirming momentum carry more weight than a quiet, low-confidence reading.",
            ),
            (
                "Open the supporting research",
                "Use the section rail for signal detail, historical correlations, earnings context, ownership data, and your private thesis workspace.",
            ),
        ],
        eyebrow="Ticker research workflow",
        intro="Start with the headline read, verify what supports it, then move into the evidence that matters for your decision.",
    )
    st.session_state["_tdd_onboarded"] = True

st.markdown(f"### Analyzing: **{ticker_input}** — {company_name_hint}")

# Credits the search_ticker onboarding step, which had no call site anywhere and
# so could never complete. Deduped per ticker rather than per session so that
# looking up five names records five analyses, but Streamlit's reruns while
# reading one of them do not.
try:
    from utils.instrumentation import record_once
    record_once("ticker_analyzed", dedupe_key=f"ticker_analyzed::{ticker_input}",
                ticker=ticker_input)
except Exception:
    pass

# ── One-click watchlist toggle for the ticker being viewed ────────────────────
# Viewing a ticker is exactly when someone decides to track it — so the action
# lives here rather than making them go to the Watchlist page and re-type it.
# Uses the existing alerts_db API (default alert thresholds). Fully defensive.
try:
    from utils.alerts_db import add_to_watchlist, remove_from_watchlist, is_watched
    _wl_uid = (st.session_state.get("user") or {}).get("id")
    _wl_c1, _wl_c2 = st.columns([1, 4])
    if _wl_uid:
        if is_watched(_wl_uid, ticker_input):
            if _wl_c1.button("Watching", key=f"wl_rm_{ticker_input}",
                             use_container_width=True,
                             help="Remove this ticker from your watchlist"):
                remove_from_watchlist(_wl_uid, ticker_input)
                st.toast(f"Removed {ticker_input} from your watchlist")
                st.rerun()
            _wl_c2.caption("On your watchlist — you'll get score-move and price alerts.")
        else:
            if _wl_c1.button("＋ Add to Watchlist", key=f"wl_add_{ticker_input}",
                             type="primary", use_container_width=True,
                             help="Track this ticker and get score/price alerts"):
                add_to_watchlist(_wl_uid, ticker_input)
                st.toast(f"Added {ticker_input} to your watchlist")
                st.rerun()
    else:
        _wl_c1.button("＋ Add to Watchlist", key=f"wl_add_anon_{ticker_input}",
                      disabled=True, use_container_width=True)
        _wl_c2.caption("Sign in to track this ticker and get alerts.")
except Exception:
    pass

# ── Research workflow actions ────────────────────────────────────────────────
# The Thesis Workspace used to exist only as a sidebar radio option, which was
# easy to miss and made the separate Journal page feel disconnected. Keep the
# rail for fast section switching, but expose the three natural next actions at
# the point where the user has chosen a ticker.
st.markdown(
    "**Next step:** save your reasoning, review prior decisions, or export this "
    "ticker's research. The section menu remains available in the left sidebar."
)
_workflow_thesis, _workflow_journal, _workflow_export = st.columns(3)
if _workflow_thesis.button(
    "Create or Update Thesis",
    key=f"open_thesis_workspace_{ticker_input}",
    type="primary",
    use_container_width=True,
    help="Open the private thesis form for this ticker",
):
    st.session_state["dive_section"] = "Thesis Workspace"
    st.rerun()
if _workflow_journal.button(
    "Open Thesis Journal",
    key=f"open_thesis_journal_{ticker_input}",
    use_container_width=True,
    help="Review every saved active, closed, or invalidated thesis",
):
    st.switch_page("pages/46_Thesis_Journal.py")
if _workflow_export.button(
    "Export PDF Report",
    key=f"open_pdf_export_{ticker_input}",
    use_container_width=True,
    help="Open the PDF exporter with this ticker already selected",
):
    st.session_state["export_ticker"] = ticker_input
    st.switch_page("pages/28_Export.py")
st.caption(
    "Thesis Workspace records your stance, catalysts, risks, invalidation rule, "
    "and review outcome. Thesis Journal organizes those saved decisions over time."
)

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

# ── Rate limit: distinct-ticker analyses per user (protects providers) ──────────
# Only a NEW ticker consumes a token — repeated reruns on the same ticker (widget
# interactions) don't count, so normal use is never throttled. Over the limit we
# show a calm message and stop, consistently across reruns for that ticker.
_rl_blocked, _rl_retry = False, 0
try:
    from utils.ratelimit import limit_action as _limit_action
    _rl_user = (st.session_state.get("user") or {}).get("id")
    if _rl_user:
        _rl_actor = f"u{_rl_user}"
    else:
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx as _grsc
            _ctx = _grsc()
            _rl_actor = f"s{getattr(_ctx, 'session_id', 'anon')}" if _ctx else "anon"
        except Exception:
            _rl_actor = "anon"
    if st.session_state.get("_tdd_rl_ticker") != ticker_input:
        _ok, _retry = _limit_action(_rl_actor, "ticker_analysis")
        st.session_state["_tdd_rl_ticker"] = ticker_input
        st.session_state["_tdd_rl_blocked"] = (not _ok, _retry)
    _rl_blocked, _rl_retry = st.session_state.get("_tdd_rl_blocked", (False, 0))
except Exception:
    _rl_blocked, _rl_retry = False, 0  # limiter must never break a working page
# st.stop() is OUTSIDE the try so it propagates (it raises a control exception).
if _rl_blocked:
    st.warning(
        f"You're analyzing tickers very quickly. Please wait about {_rl_retry}s "
        "before the next one — this keeps live data fresh and fast for everyone."
    )
    st.stop()

# Select the research workflow before scoring so public views never pay for
# optional SEC, FINRA, USASpending, or 13F calls they do not display.
section = _tdd_section or "Overview"
_pro_sections = {
    "Thesis Workspace",
    "Deep Correlation Scan",
    "Insider & Short Interest",
    "13F & Federal Contracts",
    "Earnings Sentiment",
}
if section in _pro_sections:
    from utils.billing import require_pro
    require_pro("Ticker Deep Dive Pro")

_include_optional_score = section in {"Insider & Short Interest", "13F & Federal Contracts"}

# ── Full Score Computation ──────────────────────────────────────────────────────
# compute_full_ticker_score() is the SAME function the alert engine calls to
# evaluate watched tickers in the background -- extracted from this page on
# 2026-06-21 specifically so the score shown here and the score an alert
# fires on can never silently diverge into two different numbers for the
# same ticker (see utils/ticker_score.py's module docstring).
_score_key = make_full_score_cache_key(ticker_input, relevant_sig_ids, _include_optional_score)
_snapshot = get_latest_compatible_full_snapshot(ticker_input, relevant_sig_ids) if _include_optional_score else None
_snapshot_slot = st.empty()
if _snapshot:
    _age_hours = _snapshot["age_seconds"] / 3600
    _freshness = "fresh" if _age_hours < 6 else "recent" if _age_hours < 24 else "stale"
    _snapshot_slot.info(
        f"**Latest complete score: {_snapshot['score']:.1f} ({_snapshot['case']})** · "
        f"calculated {_snapshot['calculated_at'][:16].replace('T', ' ')} UTC · {_freshness}. "
        "Refreshing live evidence now."
    )

_refresh_col, _refresh_help = st.columns([1, 5])
if _refresh_col.button("↻ Refresh live score", key=f"refresh_full_{ticker_input}",
                       help="Refresh only this ticker and signal configuration"):
    clear_session_result(st.session_state, _score_key)
    clear_full_score_result(ticker_input, relevant_sig_ids, include_optional=_include_optional_score)
    st.rerun()
_refresh_help.caption(
    "This view loads macro and momentum evidence only."
    if not _include_optional_score else
    "This Pro view adds contracts, insiders, short interest, and curated 13F evidence."
)

_full = get_session_result(st.session_state, _score_key)
_score_cache_status = "session_hit" if _full is not None else "miss"
try:
    if _full is None:
        _score_label = "complete evidence score" if _include_optional_score else "macro and momentum score"
        with st.status(f"Preparing {ticker_input}'s {_score_label}…", expanded=True) as _load_status:
            def _score_progress(_stage: str, _message: str) -> None:
                _load_status.update(label=_message, state="running", expanded=True)

            _score_outcome = get_full_ticker_score(
                ticker_input,
                relevant_sig_ids,
                include_optional=_include_optional_score,
                progress_callback=_score_progress,
            )
            _full = _score_outcome.result
            _score_cache_status = _score_outcome.cache_status
            set_session_result(st.session_state, _score_outcome.key, _full)
            _ready_label = "Complete score ready" if _full.get("is_complete", True) else "Provisional score ready"
            _load_status.update(label=_ready_label, state="complete", expanded=False)
except Exception as _score_err:
    if _snapshot:
        st.warning(
            "Fresh optional evidence is temporarily unavailable. The compatible complete score above "
            "has been preserved and was not replaced by a partial score."
        )
    else:
        st.error(
            f"**Could not load data for {ticker_input}.** "
            f"This usually means the ticker symbol is invalid, or a data source "
            f"(yfinance / FRED) is temporarily unavailable. "
            f"Try again in a moment, or check that '{ticker_input}' is a valid NYSE/NASDAQ symbol."
        )
    st.caption(f"Technical detail: {_score_err}")
    st.stop()

if not _full.get("is_complete", True) and _snapshot:
    st.warning(
        "Fresh optional evidence is temporarily unavailable. The last compatible complete score "
        "above remains authoritative; no partial score has replaced it."
    )
    st.stop()
if not _full.get("is_complete", True):
    st.warning(
        "**Provisional score:** one or more live sources are unavailable "
        f"({', '.join(_full.get('source_errors', []))}). This result is not stored as a complete score."
    )
_snapshot_slot.empty()
_display_score_kind = "Complete" if _full.get("is_complete", True) else "Provisional"
st.caption(
    f"{_display_score_kind} score calculated {_full.get('calculated_at', 'just now')[:16].replace('T', ' ')} UTC "
    f"· cache: {_score_cache_status.replace('_', ' ')}"
)
_page_run_count = int(st.session_state.get("_tdd_page_run_count", 0)) + 1
st.session_state["_tdd_page_run_count"] = _page_run_count
record_timing(
    "page_startup_to_score",
    ticker=ticker_input,
    duration_seconds=time.perf_counter() - _PAGE_STARTED_AT,
    success=_full.get("is_complete", True),
    cache_status=_score_cache_status,
    metadata={"rerun": _page_run_count > 1},
)

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

render_data_unavailable_banner(
    sum(1 for s in signal_data.values() if is_unavailable(s)),
    len(signal_data),
)

# Opportunistic score snapshot -- runs once per ticker view, regardless of
# which section a visitor lands on, since the score
# itself is computed in compute_full_ticker_score() above either way (see
# utils/score_history.py's module docstring for why this is the
# foundation the Score History chart, future track-record page, and real
# alert deltas all sit on). Wrapped defensively: a DB hiccup here must
# never break the page someone is just trying to look at a score on.
if _full.get("score_kind") == "full" and _full.get("is_complete", True):
    try:
        record_score_snapshot(
            ticker_input, confluence["overall_score"], confluence["case"], confluence["conviction"],
        )
    except Exception:
        pass

# Component snapshot for "Explain the Move" — the reconciling per-signal / factor
# breakdown behind today's score, upserted opportunistically like the score
# snapshot above. This is what a future A/B comparison attributes the change to.
if _full.get("score_kind") == "full" and _full.get("is_complete", True):
    try:
        from utils.score_components import build_components
        from utils.score_history import record_score_components
        record_score_components(ticker_input, build_components(_full))
    except Exception:
        pass

# ── Explain the Move: contextual attribution command ─────────────────────────
# Appears near the score whenever there's a material move AND a prior snapshot to
# compare against. Silent (nothing to explain) until this ticker has ≥2 days of
# history. Smart window auto-selects 1D vs 7D vs 30D by where the move happened.
try:
    from utils.score_history import explain_move_smart
    from utils.score_attribution import render_attribution_html
    _move = explain_move_smart(ticker_input)
    if _move.get("state") in ("ok", "insufficient_coverage") and abs(_move.get("total_change", 0.0)) >= 0.5:
        _mv_chg = _move.get("total_change", 0.0)
        _mv_lbl = (_move.get("window_label") or "recent").strip()
        with st.expander(f"Explain the {abs(_mv_chg):.0f}-point move · {_mv_lbl}", expanded=False):
            st.html(render_attribution_html(_move))
except Exception:
    pass

# ── Prediction Log: auto-log score crossings + resolve pending predictions ────
# Runs on every TDD page load. Two jobs:
#   1. Log today's score if it crossed 70+ (bull) or 35- (bear) for the first
#      time — idempotent via unique(ticker, date, event_type) constraint.
#   2. Resolve any pending predictions whose forward windows have expired.
# Both are best-effort and completely silent — never block or crash this page.
try:
    from utils.prediction_log import log_prediction, resolve_pending
    _score_val = confluence["overall_score"]
    _case_val  = confluence["case"]
    _history   = get_score_history(ticker_input, days=7)

    # Only log if the score JUST crossed — not if it's been here for weeks.
    # Proxy: previous score was on the other side of the threshold.
    _prev_score = float(_history[-2]["score"]) if len(_history) >= 2 else _score_val
    if _case_val == "BULL" and _score_val >= 70 and _prev_score < 70:
        # Fetch current price for entry logging
        try:
            import yfinance as yf
            _entry_px = float(yf.Ticker(ticker_input).info.get("currentPrice") or
                              yf.Ticker(ticker_input).info.get("regularMarketPrice") or 0) or None
        except Exception:
            _entry_px = None
        log_prediction(
            ticker=ticker_input, event_type="score_cross_bull", direction="bull",
            score=_score_val, price=_entry_px,
            signal_count=confluence.get("bull_count", 0),
            signals_triggered=confluence.get("bull_signals", []),
        )
    elif _case_val == "BEAR" and _score_val <= 35 and _prev_score > 35:
        try:
            import yfinance as yf
            _entry_px = float(yf.Ticker(ticker_input).info.get("currentPrice") or
                              yf.Ticker(ticker_input).info.get("regularMarketPrice") or 0) or None
        except Exception:
            _entry_px = None
        log_prediction(
            ticker=ticker_input, event_type="score_cross_bear", direction="bear",
            score=_score_val, price=_entry_px,
            signal_count=confluence.get("bear_count", 0),
            signals_triggered=confluence.get("bear_signals", []),
        )

    # Resolve pending predictions (cheap — skips if nothing is due)
    resolve_pending(max_resolve=10)
except Exception:
    pass

st.divider()

if section == "Overview":
    # ── Confluence Score Banner ────────────────────────────────────────────────────
    score_val  = confluence["overall_score"]
    conviction = confluence["conviction"]
    case       = confluence["case"]

    score_color = "#00D566" if case == "BULL" else ("#FF4444" if case == "BEAR" else "#6B7FBF")

    # Conviction context: signal alignment + historical forward return
    try:
        _conv_ctx = get_conviction_context(ticker_input, score_val, signal_scores)
        _conv_ctx_sentence = _conv_ctx["sentence"]
    except Exception:
        _conv_ctx_sentence = "Conviction context unavailable."

    # ── Earnings event risk ───────────────────────────────────────────────────
    # A macro score reads a backdrop that moves over weeks; an earnings print
    # moves the stock in one session for reasons these signals can't see. So the
    # score isn't wrong before a report — it's about to be outweighed. We surface
    # the date and say so plainly; we deliberately do NOT forecast the result or
    # adjust the score, which would mean quietly mixing an event model into a
    # macro one. Any lookup failure yields no badge rather than a wrong badge.
    _earn_badge, _earn_caveat = "", ""
    try:
        from utils.earnings_awareness import next_earnings, badge_html, caveat_text
        _earn = next_earnings(ticker_input)
        if _earn:
            _earn_badge = badge_html(_earn)
            _earn_caveat = caveat_text(_earn.get("days_until"))
    except Exception:
        pass

    # ── Thesis window (time-stop) ─────────────────────────────────────────────
    # A score says a case exists but not WHEN it should show up in price, or when
    # to conclude it didn't — which is how conviction quietly becomes stubbornness.
    # Every signal carries a researched lead time, so we derive an expected window
    # from the median lead of the signals actually FORMING this case (median, not
    # mean: leads run 1–52 weeks and one long-tail signal would stretch a 4-week
    # thesis to a year). Framed as a guide, never a forecast or a stop-loss.
    _horizon_badge, _horizon_note = "", ""
    try:
        from utils.time_stops import driving_signal_ids, thesis_horizon, horizon_html
        _hz = thesis_horizon(driving_signal_ids(confluence, case))
        if _hz.get("median_weeks"):
            _horizon_badge = horizon_html(_hz)
            _horizon_note = _hz.get("note", "")
    except Exception:
        pass

    # These two are interpolated INLINE (same source line as the conviction div)
    # on purpose. Streamlit renders this banner through st.markdown, and markdown
    # ends a raw-HTML block at the first blank line — after which the following
    # indented lines are parsed as a code block and the rest of the banner leaks
    # to the page as visible HTML source. A conditional on its own line emits
    # exactly that blank line whenever the condition is false, so both optional
    # fragments are pre-rendered here and appended without ever owning a line.
    _earn_caveat_html = (
        f'<div style="font-size:0.66rem;color:#F59E0B;margin-top:6px;'
        f'line-height:1.45;">{" ".join(_earn_caveat.split())}</div>'
    ) if _earn_caveat else ""
    _horizon_note_html = (
        f'<div style="font-size:0.64rem;color:#6B7FBF;margin-top:5px;'
        f'line-height:1.45;">{" ".join(_horizon_note.split())}</div>'
    ) if _horizon_note else ""

    st.markdown(f"""
    <div class="ua-gradient-border" style="margin-bottom:20px;">
      <div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;padding:18px 22px;">
        <div style="flex-shrink:0;">{confluence_gauge_svg(score_val, case)}</div>
        <div style="width:1px;height:72px;background:rgba(255,255,255,0.08);flex-shrink:0;"></div>
        <div style="flex:1;min-width:180px;">
          <div style="font-size:0.60rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:4px;">Signal Case</div>
          <div class="ua-kpi-animate" style="font-size:2.2rem;font-weight:900;color:{score_color};
               text-shadow:0 0 32px {score_color}55,0 0 8px {score_color}35;line-height:1;">{case}</div>
          <div style="font-size:0.80rem;color:#B8C0D4;margin-top:4px;">Conviction: <b style="color:{score_color};">{conviction}</b>{_earn_badge}{_horizon_badge}</div>{_earn_caveat_html}{_horizon_note_html}
          <div style="font-size:0.70rem;color:#8892AA;margin-top:6px;line-height:1.5;">
            {len(relevant_sig_ids)} signals + momentum{" + contracts" if _has_contract_signal else ""}{" + insiders" if _has_insider_signal else ""}{" + short interest" if _has_short_interest_signal else ""}{" + 13F" if _has_13f_signal else ""}
          </div>
          <div style="font-size:0.70rem;color:#6B7FBF;margin-top:8px;line-height:1.6;
                      border-top:1px solid rgba(255,255,255,0.06);padding-top:8px;">
            {_conv_ctx_sentence}
          </div>
        </div>
        <div style="width:1px;height:72px;background:rgba(255,255,255,0.08);flex-shrink:0;"></div>
        <div style="display:flex;gap:20px;align-items:center;flex-shrink:0;">
          <div class="ua-spotlight ua-kpi-animate" style="--ua-spotlight-accent:#00D566;text-align:center;padding:14px 20px;">
            <div style="font-size:2rem;font-weight:900;color:#00D566;text-shadow:0 0 24px #00D56645;">{confluence['bull_count']}</div>
            <div style="font-size:0.66rem;color:#8892AA;text-transform:uppercase;letter-spacing:0.08em;">▲ Bullish</div>
          </div>
          <div class="ua-spotlight ua-kpi-animate" style="--ua-spotlight-accent:#FF4444;text-align:center;padding:14px 20px;">
            <div style="font-size:2rem;font-weight:900;color:#FF4444;text-shadow:0 0 24px #FF444445;">{confluence['bear_count']}</div>
            <div style="font-size:0.66rem;color:#8892AA;text-transform:uppercase;letter-spacing:0.08em;">▼ Bearish</div>
          </div>
          <div class="ua-spotlight ua-kpi-animate" style="--ua-spotlight-accent:#6B7FBF;text-align:center;padding:14px 20px;">
            <div style="font-size:2rem;font-weight:900;color:#6B7FBF;">{confluence['neutral_count']}</div>
            <div style="font-size:0.66rem;color:#8892AA;text-transform:uppercase;letter-spacing:0.08em;">● Neutral</div>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Your Score — personalized by the user's risk profile ──────────────────
    # ADDITIVE by design: the canonical Confluence Score above is never changed
    # (it has to stay comparable across users, snapshots and alerts). This is a
    # second, clearly-labelled read tuned to how this user actually invests —
    # risk tolerance, time horizon, and which data they want counted.
    # Engine + tests: utils/risk_profile.py. Fully defensive; on any problem the
    # page renders exactly as before.
    try:
        from utils.risk_profile import (
            get_profile, save_profile, compute_personal_score,
            TOLERANCES, HORIZONS, EMPHASES,
            TOLERANCE_LABELS, HORIZON_LABELS, EMPHASIS_LABELS,
        )
        _rp_user = st.session_state.get("user") or {}
        _rp_uid = _rp_user.get("id")

        if "_risk_profile" not in st.session_state:
            st.session_state["_risk_profile"] = get_profile(_rp_uid)
        _prof = st.session_state["_risk_profile"]

        with st.expander("Your risk profile — personalize this score", expanded=False):
            st.caption(
                "Tune the read to how you actually invest. This produces a separate "
                "**Your Score** — the Confluence Score above stays the standard, "
                "comparable number."
            )
            _rc1, _rc2, _rc3 = st.columns(3)
            _tol = _rc1.selectbox(
                "Risk tolerance", list(TOLERANCES),
                index=list(TOLERANCES).index(_prof["tolerance"]),
                format_func=lambda t: TOLERANCE_LABELS[t], key="rp_tol",
                help="Aggressive gives price momentum and alt-data more say; conservative leans on slow macro.",
            )
            _hor = _rc2.selectbox(
                "Time horizon", list(HORIZONS),
                index=list(HORIZONS).index(_prof["horizon"]),
                format_func=lambda h: HORIZON_LABELS[h], key="rp_hor",
                help="Only counts signals that historically lead price on your timeframe.",
            )
            _emp = _rc3.selectbox(
                "Data emphasis", list(EMPHASES),
                index=list(EMPHASES).index(_prof["emphasis"]),
                format_func=lambda e: EMPHASIS_LABELS[e], key="rp_emp",
                help="Whether insider activity, 13F positioning and short interest participate.",
            )
            _new_prof = {"tolerance": _tol, "horizon": _hor, "emphasis": _emp}
            if _new_prof != _prof:
                st.session_state["_risk_profile"] = _new_prof
                _prof = _new_prof
                if _rp_uid:
                    if save_profile(_rp_uid, _new_prof):
                        st.caption("Saved to your account and applied to Your Score and alerts.")
                        # record() both logs the event and ticks the onboarding
                        # checklist. Keeping those two as separate calls is how
                        # the other three steps ended up with no call site.
                        try:
                            from utils.instrumentation import record
                            record("risk_profile_set", user_id=_rp_uid,
                                   tolerance=_new_prof.get("tolerance"),
                                   horizon=_new_prof.get("horizon"))
                        except Exception:
                            pass
                else:
                    st.caption("Sign in to save this profile to your account.")

        _ps = compute_personal_score(_full, _prof)
        if _ps.get("ok"):
            _pv, _dl = _ps["score"], _ps.get("delta", 0.0)
            _pc = "#00D566" if _pv >= 65 else ("#FF4444" if _pv <= 35 else "#6B7FBF")
            _dtxt = ("+" if _dl > 0 else "") + f"{_dl:g}"
            _dcol = "#00D566" if _dl > 0 else ("#FF4444" if _dl < 0 else "#8892AA")
            st.html(f"""
            <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap;
                        background:rgba(255,255,255,0.025);border:1px solid {_pc}33;
                        border-left:4px solid {_pc};border-radius:10px;
                        padding:14px 18px;margin:0 0 18px;">
              <div style="flex-shrink:0;text-align:center;min-width:104px;">
                <div style="font-size:0.56rem;font-weight:700;color:{_pc};
                            letter-spacing:0.10em;text-transform:uppercase;">YOUR SCORE</div>
                <div style="font-size:2rem;font-weight:900;color:{_pc};line-height:1.15;">{_pv:.0f}</div>
                <div style="font-size:0.62rem;color:{_dcol};">{_dtxt} vs standard</div>
              </div>
              <div style="width:1px;height:54px;background:rgba(255,255,255,0.08);flex-shrink:0;"></div>
              <div style="flex:1;min-width:220px;">
                <div style="font-size:0.68rem;color:#B8C2D9;line-height:1.5;">{_ps['explanation']}</div>
                <div style="margin-top:6px;font-size:0.58rem;color:#6B7FBF;">
                  {_ps['tolerance_label']} · {_ps['horizon_label']} · {_ps['emphasis_label']}
                </div>
              </div>
            </div>""")
    except Exception:
        pass

    # ── TradingView Advanced Chart — the same professional widget as the Stock
    # Chart page, embedded here so the chart lives right beside the analysis.
    try:
        from utils.tradingview import render_tradingview_chart
        st.markdown(f"#### {ticker_input} — Interactive Chart")
        render_tradingview_chart(ticker_input, chart_height=480, key=f"tdd_{ticker_input}")
    except Exception:
        pass

    # ── Confluence Score Explainer (transparency layer) ───────────────────────
    # Point 3: make the score explain itself in <10s — plain-English band, how
    # much it moved & WHY (per-signal attribution of the macro-backdrop change),
    # agreement among the statistically-relevant signals, a data-quality
    # confidence read, the factor mix, and the known limitations stated plainly.
    # See utils/score_explainer.py (unit-tested in tests/test_score_explainer.py).
    # ADDITIVE: the granular confidence/attribution cards below remain as deeper
    # detail. Fully defensive — a hiccup here must never break the score page.
    try:
        from utils.score_explainer import build_explainer, render_explainer_html
        from utils.score_history import get_signal_trends as _ua_get_signal_trends
        _expl_hist = get_score_history(ticker_input, days=30)
        try:
            _expl_trends = _ua_get_signal_trends(days_back=7)
        except Exception:
            _expl_trends = {}
        _expl_payload = build_explainer(
            _full, score_history=_expl_hist, signal_trends=_expl_trends, change_days=7,
        )
        st.html(render_explainer_html(_expl_payload))
    except Exception:
        pass

    # ── Signal Confidence Summary ─────────────────────────────────────────────
    # Aggregate across active signal scores: how many are High / Medium / Low
    # confidence? Gives users an immediate gut-check on whether the score is
    # based on strong z-score deviations or weak within-normal-range readings.
    try:
        from utils.signals_cache import get_all_signal_scores as _get_all_sc
        _all_sc = _get_all_sc()
        _rel_sc = {sid: _all_sc[sid] for sid in relevant_sig_ids if sid in _all_sc}
        _conf_counts = {"High": 0, "Medium": 0, "Low": 0}
        for _sc_sid, _sc_sv in _rel_sc.items():
            _sc_pcs = SIGNALS.get(_sc_sid, {}).get("pcs", 5)
            _sc_conf = compute_signal_confidence(_sc_sv, pcs=_sc_pcs)
            _conf_counts[_sc_conf["level"]] += 1
        _total_conf = sum(_conf_counts.values())
        if _total_conf > 0:
            _conf_caption = (
                f"Signal confidence breakdown across {_total_conf} active signals: "
                f"<b style='color:#00D566;'>◆ {_conf_counts['High']} High</b> · "
                f"<b style='color:#F59E0B;'>◇ {_conf_counts['Medium']} Medium</b> · "
                f"<b style='color:#6B7FBF;'>○ {_conf_counts['Low']} Low</b>. "
            )
            if _conf_counts["High"] >= _conf_counts["Medium"] + _conf_counts["Low"]:
                _conf_caption += "Majority of signals show strong conviction — score is well-supported."
            elif _conf_counts["Low"] > _conf_counts["High"] + _conf_counts["Medium"]:
                _conf_caption += "Most signals are within normal ranges — score reflects mild alignment, not extreme readings."
            else:
                _conf_caption += "Mixed confidence — check individual signal cards for the strongest drivers."
            st.markdown(
                chart_insight_caption(_conf_caption, icon="◆", muted=False),
                unsafe_allow_html=True,
            )
    except Exception:
        pass

    # ── Signal Attribution Breakdown ──────────────────────────────────────────
    # Shows which subsystems are driving the score (per Reddit feedback: the
    # score is a black box without this; a breakdown card builds trust).
    # Weights: each active optional signal gets 12%; remainder split 80/20
    # macro/momentum. We show the weight % alongside each subsystem's score.
    _n_opt_active = sum([_has_contract_signal, _has_insider_signal, _has_short_interest_signal, _has_13f_signal])
    _opt_slice    = 0.12
    _remaining    = 1.0 - _opt_slice * _n_opt_active
    _macro_wt     = round(_remaining * 0.80 * 100)
    _mom_wt       = round(_remaining * 0.20 * 100)

    def _score_color(s):
        return "#00D566" if s >= 60 else ("#FF4444" if s <= 40 else "#6B7FBF")

    def _attr_card(label, value_html, weight_pct, active=True):
        opacity = "1" if active else "0.35"
        return f"""
        <div style="flex:1;min-width:90px;background:rgba(255,255,255,0.03);
                    border:1px solid rgba(255,255,255,0.07);border-radius:8px;
                    padding:10px 12px;opacity:{opacity};">
          <div style="font-size:0.58rem;color:#8892AA;text-transform:uppercase;
                      letter-spacing:0.10em;margin-bottom:5px;white-space:nowrap;">{label}</div>
          <div style="font-size:0.90rem;font-weight:700;line-height:1.1;">{value_html}</div>
          <div style="font-size:0.55rem;color:#4A5568;margin-top:4px;">{weight_pct}% of score</div>
        </div>"""

    _macro_net  = confluence.get("bull_count", 0) - confluence.get("bear_count", 0)
    _mac_c      = _score_color(score_val if _macro_net >= 0 else 100 - score_val)
    _mac_label  = (f'<span style="color:#00D566;">▲{confluence["bull_count"]}</span>'
                   f' <span style="color:#FF4444;">▼{confluence["bear_count"]}</span>'
                   f' <span style="color:#6B7FBF;">●{confluence["neutral_count"]}</span>')

    _mom_c = _score_color(_mom_score)
    _mom_label = f'<span style="color:{_mom_c};">{_mom_score:.0f}/100</span>'

    _ins_label  = (f'<span style="color:{_score_color(_insider_score["score"])}">{_insider_score["score"]:.0f}/100</span>'
                   if _has_insider_signal else '<span style="color:#4A5568;">no data</span>')
    _si_label   = (f'<span style="color:{_score_color(_short_interest_score["score"])}">{_short_interest_score["score"]:.0f}/100</span>'
                   if _has_short_interest_signal else '<span style="color:#4A5568;">no data</span>')
    _tf_label   = (f'<span style="color:{_score_color(_thirteenf_score["score"])}">{_thirteenf_score["score"]:.0f}/100</span>'
                   if _has_13f_signal else '<span style="color:#4A5568;">no data</span>')
    _cv_label   = (f'<span style="color:{_score_color(_contract_vel["score"])}">{_contract_vel["score"]:.0f}/100</span>'
                   if _has_contract_signal else '<span style="color:#4A5568;">no data</span>')

    # weight_pct here is just the number — _attr_card appends the "%" itself
    # (previously this included a "%", producing the "12%%" display bug).
    _opt_wt_display = f"{round(_opt_slice * 100)}"

    st.html(f"""
    <div style="margin-bottom:14px;">
      <div style="font-size:0.60rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;
                  text-transform:uppercase;margin-bottom:8px;">Score Attribution</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        {_attr_card("Macro Signals", _mac_label, _macro_wt)}
        {_attr_card("Momentum", _mom_label, _mom_wt)}
        {_attr_card("Insiders", _ins_label, _opt_wt_display if _has_insider_signal else "—", _has_insider_signal)}
        {_attr_card("Short Int.", _si_label, _opt_wt_display if _has_short_interest_signal else "—", _has_short_interest_signal)}
        {_attr_card("13F Funds", _tf_label, _opt_wt_display if _has_13f_signal else "—", _has_13f_signal)}
        {_attr_card("Contracts", _cv_label, _opt_wt_display if _has_contract_signal else "—", _has_contract_signal)}
      </div>
    </div>
    """)

    # ── Score Velocity Banner ─────────────────────────────────────────────────
    # Shows when the score is moving at an unusual rate-of-change compared to
    # this ticker's own history — top 10% velocity triggers the banner.
    # Derived from score_snapshots so no live recompute; best-effort (try/except).
    try:
        from utils.score_history import get_score_velocity_stats as _gsvs
        _vel_stats = _gsvs(ticker_input)
        if _vel_stats and _vel_stats["percentile"] >= 85 and _vel_stats["n_windows"] >= 6:
            _vel = _vel_stats["velocity"]
            _vd  = _vel_stats["direction"]
            _vp  = _vel_stats["percentile"]
            _vc  = "#00D566" if _vd == "up" else "#FF4D6A"
            _va  = "▲" if _vd == "up" else "▼"
            _vsign = "+" if _vel >= 0 else ""
            _top_n = round(100 - _vp, 0)
            st.markdown(f"""
            <div style="background:rgba(245,158,11,0.07);border:1px solid rgba(245,158,11,0.28);
                        border-left:4px solid #F59E0B;border-radius:8px;
                        padding:10px 18px;margin-bottom:14px;
                        display:flex;align-items:center;gap:14px;">
              <span style="width:3px;height:30px;background:#8187F7;border-radius:2px;flex-shrink:0;"></span>
              <div>
                <span style="font-size:0.75rem;font-weight:700;color:#F59E0B;
                             letter-spacing:0.08em;text-transform:uppercase;">Score Velocity Alert</span>
                <span style="font-size:0.82rem;color:#8892AA;margin-left:10px;">
                  <span style="color:{_vc};font-weight:700;">{_va} {_vsign}{_vel:.1f} pts/day</span>
                  &nbsp;over last 5 sessions · faster than {_vp:.0f}% of all historical windows
                </span>
              </div>
            </div>
            """, unsafe_allow_html=True)
    except Exception:
        pass  # velocity banner is always best-effort; never block the page

    # ── AI Signal Explanation (Pro) ───────────────────────────────────────────
    # Haiku-generated 3-4 sentence plain-English explanation of WHY the score
    # is what it is, grounded in the actual signal breakdown. Pro-gated: free
    # users see a locked teaser with an upgrade nudge.
    try:
        _explain_user = st.session_state.get("user")
        _explain_tier_key = f"_tier_{_explain_user['id']}" if _explain_user else None
        if _explain_tier_key and _explain_tier_key not in st.session_state:
            from utils.billing import get_user_tier
            st.session_state[_explain_tier_key] = get_user_tier(_explain_user["id"])
        _explain_is_pro = bool(_explain_tier_key and st.session_state.get(_explain_tier_key) == "pro")

        if _explain_is_pro:
            # Build compact signal context for the prompt
            @st.cache_data(ttl=86400, show_spinner=False, max_entries=64)  # per-day: cache key is the score-state, so it only regenerates when inputs change; 24h cuts Haiku calls ~24x
            def _generate_score_explanation(
                _ticker: str,
                _score: float,
                _case: str,
                _conviction: str,
                _sig_summary: str,
            ) -> str | None:
                import os
                api_key = os.environ.get("ANTHROPIC_API_KEY", "")
                if not api_key:
                    return None
                prompt = (
                    f"Ticker: {_ticker} | Confluence Score: {_score:.0f}/100 | "
                    f"Case: {_case} | Conviction: {_conviction}\n\n"
                    f"Signal breakdown:\n{_sig_summary}\n\n"
                    "Write 3-4 sentences explaining in plain English why this ticker scores "
                    f"{_score:.0f}. Identify the 2-3 dominant drivers, note any meaningful "
                    "tensions between bullish and bearish signals, and say what would need to "
                    "change for the score to move materially. "
                    "Be specific — name the signals. No hype. No disclaimers. No markdown."
                )
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=api_key)
                    resp = client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=220,
                        system=(
                            "You are a concise, data-driven equity analyst. Write in plain prose. "
                            "Cite specific signal names and numeric scores. Never be promotional."
                        ),
                        messages=[{"role": "user", "content": prompt}],
                    )
                    return resp.content[0].text.strip()
                except Exception:
                    return None

            # Build signal summary string: top 6 by extremity, both directions
            _top_sigs = sorted(
                signal_scores.items(),
                key=lambda kv: -abs(kv[1].get("score", 50) - 50)
            )[:6]
            _sig_lines = []
            for _sid, _sv in _top_sigs:
                _sname  = SIGNALS.get(_sid, {}).get("name", _sid)
                _sscore = _sv.get("score", 50)
                _sstatus = _sv.get("status", "neutral")
                _sig_lines.append(f"  {_sname}: {_sscore:.0f}/100 ({_sstatus})")
            _sig_summary_str = "\n".join(_sig_lines)

            _explanation = _generate_score_explanation(
                ticker_input,
                score_val,
                case,
                conviction,
                _sig_summary_str,
            )

            if _explanation:
                _case_color = "#00D566" if case == "BULL" else ("#FF4D6A" if case == "BEAR" else "#F59E0B")
                st.markdown(f"""
                <div style="background:rgba(124,58,237,0.06);border:1px solid rgba(124,58,237,0.20);
                            border-left:4px solid #7C3AED;border-radius:0 10px 10px 0;
                            padding:16px 20px;margin:0 0 20px;font-family:Inter,sans-serif;">
                  <div style="font-size:0.60rem;font-weight:700;color:#7C3AED;
                              letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px;">
                    AI SIGNAL INTERPRETATION — PRO
                  </div>
                  <p style="margin:0;font-size:0.90rem;color:#D0D8F0;line-height:1.75;">
                    {_explanation}
                  </p>
                  <div style="font-size:0.68rem;color:#4A5280;margin-top:10px;">
                    Generated by Claude Haiku from live signal data · Not financial advice
                  </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            # Non-Pro: show locked preview
            st.markdown("""
            <div style="background:rgba(124,58,237,0.04);border:1px solid rgba(124,58,237,0.15);
                        border-left:4px solid rgba(124,58,237,0.4);border-radius:0 10px 10px 0;
                        padding:16px 20px;margin:0 0 20px;font-family:Inter,sans-serif;
                        position:relative;overflow:hidden;">
              <div style="font-size:0.60rem;font-weight:700;color:#7C3AED;
                          letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px;">
                AI SIGNAL INTERPRETATION — PRO
              </div>
              <p style="margin:0;font-size:0.90rem;color:#4A5280;line-height:1.75;
                        filter:blur(4px);user-select:none;">
                The dominant bullish driver is the copper/gold ratio, which has climbed 8% over
                14 days signalling risk-on rotation into cyclicals. Simultaneously, insider
                cluster activity shows two senior officers adding shares within 21 days, a pattern
                historically associated with mean outperformance. The bearish counterweight comes
                from the inverted yield curve, which has predicted earnings contractions with a
                10-week lead across 47 similar setups.
              </p>
              <div style="position:absolute;inset:0;background:linear-gradient(to bottom,
                          transparent 20%,rgba(12,14,20,0.85));display:flex;
                          align-items:flex-end;justify-content:center;padding-bottom:12px;">
                <span style="font-size:0.78rem;color:#A78BFA;font-weight:600;">
                  Upgrade to Pro to unlock AI explanations
                </span>
              </div>
            </div>
            """, unsafe_allow_html=True)
    except Exception:
        pass  # AI explanation is best-effort; never crash the page

    # ── Share strip ───────────────────────────────────────────────────────────
    # Build top-signal list for the card (up to 4 highest-confidence signals
    # in their dominant direction, formatted as "▲ Signal Name")
    _card_sigs: list[str] = []
    for _sid, _sv in sorted(
        signal_scores.items(),
        key=lambda kv: -abs(kv[1].get("score", 50) - 50)
    ):
        if len(_card_sigs) >= 4:
            break
        _s_status = _sv.get("status", "neutral")
        _s_name   = SIGNALS.get(_sid, {}).get("name", _sid)
        if _s_status == "bullish":
            _card_sigs.append(f"▲ {_s_name}")
        elif _s_status == "bearish":
            _card_sigs.append(f"▼ {_s_name}")

    _co_name = TICKERS.get(ticker_input, {}).get("name", ticker_input)

    _share_c1, _share_c2, _share_c3, _ = st.columns([1.2, 1.2, 1, 2.6])
    with _share_c1:
        # Generate PNG card on demand — cached in session_state so re-renders
        # don't regenerate; only regenerates when ticker/score changes.
        _card_cache_key = f"_card_{ticker_input}_{score_val:.0f}_{case}"
        if _card_cache_key not in st.session_state:
            st.session_state[_card_cache_key] = generate_signal_card(
                ticker=ticker_input,
                company_name=_co_name,
                score=score_val,
                case=case,
                conviction=conviction,
                bull_count=confluence["bull_count"],
                bear_count=confluence["bear_count"],
                neutral_count=confluence["neutral_count"],
                top_signals=_card_sigs,
            )
        st.download_button(
            label="Download Signal Card",
            data=st.session_state[_card_cache_key],
            file_name=f"UA_{ticker_input}_{case}_{score_val:.0f}.png",
            mime="image/png",
            key="card_dl_btn",
            help="Download a shareable PNG card to post on Twitter, Reddit, or Discord",
            use_container_width=True,
        )
    with _share_c2:
        if st.button("Share Link", key="share_btn",
                     help="Copy a direct link to this ticker's analysis",
                     use_container_width=True):
            st.session_state["_tdd_show_share"] = True
    with _share_c3:
        if st.button("Watchlist", key="add_wl_btn",
                     help="Track this ticker with score + price alerts",
                     use_container_width=True):
            st.session_state["chart_ticker"] = ticker_input
            st.switch_page("pages/10_Watchlist.py")
    if st.session_state.get("_tdd_show_share"):
        _share_url = f"https://app.unstructuredalpha.com/Ticker_Deep_Dive?ticker={ticker_input}"
        st.code(_share_url, language=None)
        st.caption("Share this link — it loads directly to this ticker's full analysis.")
        if st.button("Dismiss", key="share_dismiss"):
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
        _line_color = "#00D566" if case == "BULL" else ("#FF4444" if case == "BEAR" else "#6B7FBF")

        _fig_radar = go.Figure()

        # Neutral reference ring at 50
        _fig_radar.add_trace(go.Scatterpolar(
            r=[50] * (len(_radar_axes) + 1),
            theta=_ra_closed,
            mode="lines",
            line=dict(color="rgba(255,255,255,0.08)", width=1, dash="dot"),
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
                    tickfont=dict(size=9, color="#6B7FBF", family="Inter, sans-serif"),
                    gridcolor="rgba(255,255,255,0.05)", linecolor="rgba(255,255,255,0.08)",
                ),
                angularaxis=dict(
                    tickfont=dict(size=10, color="#7C3AED", family="Inter, sans-serif"),
                    linecolor="rgba(255,255,255,0.08)", gridcolor="rgba(255,255,255,0.05)",
                ),
                bgcolor="#0F1118",
            ),
            height=300, margin=dict(l=30, r=30, t=20, b=20),
            paper_bgcolor="#0B0D12", showlegend=False,
        )

        _radar_col_l, _radar_col_r = st.columns([1, 1])
        with _radar_col_l:
            st.markdown(
                f'<div style="font-family:Inter,sans-serif;padding:10px 0;">'
                f'<div style="font-size:0.70rem;text-transform:uppercase;letter-spacing:0.08em;'
                f'color:#6B7FBF;margin-bottom:8px;">SIGNAL SHAPE — {ticker_input}</div>'
                f'<div style="font-size:0.80rem;color:#8892AA;line-height:1.7;">',
                unsafe_allow_html=True,
            )
            for _i, (_aname, _aval, _has) in enumerate(zip(_radar_axes, _radar_vals, _radar_has_data)):
                _acolor = "#00D566" if _aval >= 60 else ("#FF4444" if _aval <= 40 else "#6B7FBF")
                _asym   = "▲" if _aval >= 60 else ("▼" if _aval <= 40 else "●")
                _adisp  = _aname.replace("\n", " ")
                _no_data_note = "" if _has else " <span style='color:#9E9E9E;font-size:0.70rem;'>no data yet</span>"
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;padding:3px 0;'
                    f'border-bottom:1px solid rgba(18,21,30,0.85);font-family:Inter,sans-serif;">'
                    f'<span style="color:#E8EEFF;">{_adisp}{_no_data_note}</span>'
                    f'<span style="color:{_acolor};font-weight:700;">{_asym} {_aval:.0f}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            st.markdown(
                '<div style="font-size:0.68rem;color:#8892AA;margin-top:8px;">'
                'Dashed ring = 50 (neutral). Score > 60 = bullish, < 40 = bearish.</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        with _radar_col_r:
            _fig_radar = style_chart(
                _fig_radar, height=300, hovermode="closest", legend=False,
            )
            st.plotly_chart(_fig_radar, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
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

            _expl_color = "#00D566" if case == "BULL" else ("#FF4444" if case == "BEAR" else "#6B7FBF")
            st.markdown(
                f'<div style="background:#12151E;border-left:4px solid {_expl_color};'
                f'border:1px solid #E0E0E0;border-radius:6px;padding:14px 18px;'
                f'margin:12px 0;font-family:Inter,sans-serif;">'
                f'<div style="font-size:0.70rem;text-transform:uppercase;letter-spacing:0.08em;'
                f'color:#6B7FBF;margin-bottom:6px;">WHY THIS SCORE</div>'
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
            line=dict(color="#7C3AED", width=2.5),
            marker=dict(size=6, color="#F59E0B"),
            hovertemplate="%{x}: score=%{y:.1f}<extra></extra>",
        ))
        _fig_hist.add_hline(y=65, line_dash="dot", line_color="#00D566", opacity=0.4)
        _fig_hist.add_hline(y=35, line_dash="dot", line_color="#FF4444", opacity=0.4)
        _fig_hist.update_layout(
            height=200, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
            xaxis=dict(showgrid=False, tickfont=dict(color="#8892AA")),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#8892AA"),
                       title="Confluence Score", range=[0, 100]),
            margin=dict(l=0, r=0, t=10, b=0),
        )
        _fig_hist = style_chart(_fig_hist, height=220, hovermode="x unified", legend=False)
        st.plotly_chart(_fig_hist, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
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
        _pct_color = "#00D566" if _pct >= 65 else ("#FF4444" if _pct <= 35 else "#6B7FBF")
        st.markdown(
            f'<div class="ua-spotlight" style="--ua-spotlight-accent:{_pct_color};padding:10px 16px;margin:8px 0;">'
            f'<span style="font-weight:700;color:{_pct_color};">{ticker_input} sits at the '
            f'{_pct:.0f}th percentile among {_sector_pct["n_peers"]} sector peers</span> '
            f'<span style="color:#8892AA;">(score {score_val:.0f} vs. sector peer average '
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

    # ── Similar Tickers in Sector ─────────────────────────────────────────────────
    # Reuses peer_scores already fetched by compute_sector_percentile() above --
    # zero extra DB hits or API calls. Up to 4 peers shown as clickable cards.
    if _sector_pct.get("error") is None and _sector_pct.get("peer_scores"):
        st.markdown(
            section_label("Similar Tickers in This Sector", color="#6B7FBF", dot="#6B7FBF"),
            unsafe_allow_html=True,
        )
        _peers_to_show = _sector_pct["peer_scores"][:4]
        _pcols = st.columns(len(_peers_to_show))
        for _pi, _peer in enumerate(_peers_to_show):
            _pt   = _peer["ticker"]
            _ps   = _peer["score"]
            _pa   = _peer["as_of"]
            _pc   = "#00D566" if _ps >= 65 else ("#FF4444" if _ps <= 35 else "#6B7FBF")
            _pn   = TICKERS.get(_pt, {}).get("name", _pt)
            with _pcols[_pi]:
                st.markdown(
                    f'<div style="background:rgba(107,127,191,0.08);border:1px solid rgba(107,127,191,0.20);'
                    f'border-radius:8px;padding:12px 14px;text-align:center;margin-bottom:6px;">'
                    f'<div style="font-size:1.05rem;font-weight:800;color:#E8EEFF;font-family:Inter,sans-serif;">{_pt}</div>'
                    f'<div style="font-size:0.72rem;color:#8892AA;margin-bottom:5px;white-space:nowrap;'
                    f'overflow:hidden;text-overflow:ellipsis;" title="{_pn}">{_pn}</div>'
                    f'<div style="font-size:1.5rem;font-weight:900;color:{_pc};line-height:1.1;">{_ps:.0f}</div>'
                    f'<div style="font-size:0.68rem;color:#6B7A95;margin-top:2px;">score · {_pa}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button(f"Explore {_pt} →", key=f"peer_nav_{_pt}", use_container_width=True):
                    st.session_state.selected_ticker = _pt
                    st.rerun()

    st.divider()

    # ── Price Chart ───────────────────────────────────────────────────────────────
    # Windows are sliced by calendar date in utils.price_chart. The previous
    # implementation kept calendar-day constants but applied them positionally
    # (`price_series.iloc[-370:]`), and daily bars are trading days, so "1Y"
    # drew ~17.6 months and "6M" drew ~9. See that module's docstring.
    from utils.price_chart import (
        DEFAULT_PERIOD,
        PERIODS,
        build_payload,
        render as render_price_chart,
        slice_period,
    )

    _period_opts = list(PERIODS)
    price_period = st.radio(
        "Price chart period",
        _period_opts,
        index=_period_opts.index(DEFAULT_PERIOD),
        horizontal=True,
        label_visibility="collapsed",
        key="dive_price_period",
    )
    st.markdown(f"### {ticker_input} Price \u2014 {price_period}")

    # Downstream volume and RSI charts align to this same window.
    price_view = slice_period(price_series, price_period) if not price_series.empty else price_series

    if not price_series.empty:
        price_chart_box = st.container(border=True)
        with price_chart_box:
            try:
                _earnings_data = fetch_earnings_dates(ticker_input)
            except Exception:
                _earnings_data = []  # a failed earnings fetch never breaks the chart

            render_price_chart(
                build_payload(
                    ticker=ticker_input,
                    price_series=price_series,
                    period=price_period,
                    score_history=_score_hist,
                    earnings=_earnings_data,
                ),
                height=400,
                st_module=st,
            )
            st.markdown(
                source_badge("yfinance", "Daily OHLCV") + "&nbsp;&nbsp;" +
                source_badge("yfinance", "Confluence Score · UA internal"),
                unsafe_allow_html=True,
            )

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
                            _pre_color = "#00D566" if (_pre_c or 0) >= 0 else "#FF4444"
                            _pre_sym   = "▲" if (_pre_c or 0) >= 0 else "▼"
                            st.markdown(
                                f'<div style="background:rgba(0,200,224,0.08);border-radius:4px;padding:4px 10px;'
                                f'font-family:Inter,sans-serif;font-size:0.78rem;margin-top:2px;">'
                                f'<span style="color:#6B7FBF;font-weight:600;">PRE-MARKET</span> &nbsp;'
                                f'<span style="color:{_pre_color};font-weight:700;">'
                                f'${_pre_p:.2f} &nbsp;{_pre_sym} {abs(_pre_c):.2f}%</span></div>',
                                unsafe_allow_html=True,
                            )
                        elif _mst == "POST" and _post_p is not None:
                            _post_color = "#00D566" if (_post_c or 0) >= 0 else "#FF4444"
                            _post_sym   = "▲" if (_post_c or 0) >= 0 else "▼"
                            st.markdown(
                                f'<div style="background:rgba(245,158,11,0.08);border-radius:4px;padding:4px 10px;'
                                f'font-family:Inter,sans-serif;font-size:0.78rem;margin-top:2px;">'
                                f'<span style="color:#6B7FBF;font-weight:600;">AFTER-HOURS</span> &nbsp;'
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

    # ── Signal → Price Overlay ─────────────────────────────────────────────────
    # Lets users pick any signal and overlay its historical series directly on
    # top of the price chart — dual-axis: price (left, USD) and signal z-score
    # (right, ±3σ). Shows the lag relationship visually so users can judge
    # whether "bullish credit spreads → price up 8 weeks later" looks real or
    # spurious in this specific ticker's history.
    #
    # Design choices:
    #   - Signal on right Y as z-score (not raw value) so any unit (basis points,
    #     barrels, index level) plots on the same −3 to +3 scale alongside price.
    #   - Correlation + p-value from corr_info (already computed above) displayed
    #     as a compact badge row — no re-fetching.
    #   - Default signal = highest |r| from relevant_sig_ids so the first thing
    #     users see is the most meaningful relationship, not an arbitrary one.
    #   - Wrapped in st.expander so it doesn't add visual weight unless the user
    #     wants it.
    with st.expander("Signal to Price Overlay", expanded=False):
        try:
            # Sort relevant signals by |correlation| descending so the first
            # option in the selectbox is the most meaningful one by default.
            _sig_corr_order = sorted(
                relevant_sig_ids,
                key=lambda sid: -abs(corr_info.get(sid, {}).get("r", 0.0)),
            )
            _sig_labels = {
                sid: f"{SIGNALS.get(sid, {}).get('name', sid)}"
                     f"  (r={corr_info.get(sid, {}).get('r', 0.0):+.2f}"
                     + (", sig" if corr_info.get(sid, {}).get("significant") else "")
                     + ")"
                for sid in _sig_corr_order
            }

            _ov_col1, _ov_col2 = st.columns([3, 1])
            with _ov_col1:
                _sel_sig_id = st.selectbox(
                    "Choose signal to overlay:",
                    options=_sig_corr_order,
                    format_func=lambda x: _sig_labels[x],
                    key="sig_overlay_sel",
                )
            with _ov_col2:
                _ov_lag = st.number_input(
                    "Lead weeks (shift signal forward):",
                    min_value=0, max_value=52, value=0,
                    key="sig_overlay_lag",
                    help="Shift the signal series N weeks forward to test if it leads price action.",
                )

            # Fetch and process signal series
            _ov_cfg = SIGNALS.get(_sel_sig_id, {})

            @st.cache_data(ttl=3600, max_entries=20, show_spinner=False)
            def _fetch_sig_for_overlay(sig_id: str, start: str, end: str):
                """Cached signal fetch for the overlay chart."""
                cfg = SIGNALS.get(sig_id, {})
                if not cfg:
                    return None
                try:
                    return fetch_signal_series(cfg, start, end)
                except Exception:
                    return None

            _ov_end   = datetime.now().strftime("%Y-%m-%d")
            _ov_start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

            with st.spinner("Loading signal data…"):
                _ov_raw = _fetch_sig_for_overlay(_sel_sig_id, _ov_start, _ov_end)

            if _ov_raw is not None and not _ov_raw.empty and not price_series.empty:
                # Normalize signal to z-score, clamped to ±3σ for readability
                _ov_mean = _ov_raw.mean()
                _ov_std  = _ov_raw.std()
                if _ov_std > 0:
                    _ov_z = ((_ov_raw - _ov_mean) / _ov_std).clip(-3, 3)
                else:
                    _ov_z = _ov_raw * 0.0  # flat if no variance

                # Align to a common daily index (signal is often weekly)
                _ov_price_clean = price_series.copy()
                if _ov_price_clean.index.tz is not None:
                    _ov_price_clean.index = _ov_price_clean.index.tz_localize(None)

                _ov_z_reindexed = _ov_z.reindex(_ov_price_clean.index, method="ffill")

                # Apply user-specified forward shift (lead time)
                if _ov_lag > 0:
                    _ov_z_shifted = _ov_z_reindexed.shift(periods=_ov_lag * 7)
                else:
                    _ov_z_shifted = _ov_z_reindexed

                # Restrict to view window (use the price_view period selected above)
                # Same calendar-date window as the price chart above; this line
                # previously took 370 rows, i.e. ~17.6 months labelled as 1Y.
                _ov_price_view = slice_period(_ov_price_clean, price_period)
                _ov_z_view     = _ov_z_shifted.reindex(_ov_price_view.index)

                # Build dual-axis overlay chart
                _ov_is_inverse = _ov_cfg.get("inverse", False)
                _sig_name      = _ov_cfg.get("name", _sel_sig_id)
                _ov_r    = corr_info.get(_sel_sig_id, {}).get("r", None)
                _ov_sig  = corr_info.get(_sel_sig_id, {}).get("significant", False)

                # Signal color: green if bullish correlation direction, red if inverse/bearish
                _ov_sig_color = "#F59E0B"  # amber default (no clear direction)
                if _ov_r is not None:
                    if (_ov_r > 0 and not _ov_is_inverse) or (_ov_r < 0 and _ov_is_inverse):
                        _ov_sig_color = "#00D566"  # aligned bullish
                    else:
                        _ov_sig_color = "#FF6B6B"  # misaligned / bearish direction

                _fig_ov = make_subplots(specs=[[{"secondary_y": True}]])

                # Price line (primary, left Y)
                _fig_ov.add_trace(go.Scatter(
                    x=_ov_price_view.index,
                    y=_ov_price_view.values,
                    name=f"{ticker_input} Price",
                    mode="lines",
                    line=dict(color="#00C8E0", width=2.5),
                    fill="tozeroy",
                    fillcolor="rgba(0,200,224,0.06)",
                    hovertemplate="$%{y:.2f}<extra>" + ticker_input + "</extra>",
                ), secondary_y=False)

                # Signal z-score line (secondary, right Y)
                _lag_note = f" (shifted +{_ov_lag}w)" if _ov_lag > 0 else ""
                _inv_note = " [inverse]" if _ov_is_inverse else ""
                _fig_ov.add_trace(go.Scatter(
                    x=_ov_z_view.index,
                    y=_ov_z_view.values,
                    name=f"{_sig_name}{_lag_note}{_inv_note}",
                    mode="lines",
                    line=dict(color=_ov_sig_color, width=2, dash="solid"),
                    opacity=0.85,
                    hovertemplate="%{y:+.2f}σ<extra>" + _sig_name + "</extra>",
                ), secondary_y=True)

                # Zero-line reference on signal axis
                _fig_ov.add_hline(
                    y=0, line_dash="dot",
                    line_color="rgba(255,255,255,0.15)",
                    line_width=1, yref="y2",
                )

                _fig_ov.update_layout(
                    height=350,
                    paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
                    font=dict(size=12, color="#E8EEFF"),
                    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                               tickfont=dict(color="#8892AA")),
                    legend=dict(font=dict(color="#E8EEFF", size=11),
                                bgcolor="rgba(18,21,30,0.85)",
                                bordercolor="rgba(255,255,255,0.07)", borderwidth=1),
                    margin=dict(l=0, r=0, t=24, b=0),
                )
                _fig_ov.update_yaxes(
                    title_text="Price (USD)",
                    secondary_y=False,
                    showgrid=True, gridcolor="rgba(255,255,255,0.04)",
                    tickfont=dict(color="#8892AA", size=10),
                    title_font=dict(color="#8892AA", size=10),
                    tickprefix="$", autorange=True,
                )
                _fig_ov.update_yaxes(
                    title_text="Signal (z-score)",
                    secondary_y=True,
                    range=[-3.5, 3.5],
                    showgrid=False,
                    tickfont=dict(color=_ov_sig_color, size=10),
                    title_font=dict(color=_ov_sig_color, size=10),
                    zeroline=False,
                    tickvals=[-3, -2, -1, 0, 1, 2, 3],
                    ticktext=["-3σ", "-2σ", "-1σ", "0", "+1σ", "+2σ", "+3σ"],
                )

                st.plotly_chart(
                    _fig_ov, use_container_width=True,
                    config=PLOTLY_CONFIG_INTERACTIVE, theme=None,
                )

                # ── Correlation stats row ────────────────────────────────────────
                _stat_col1, _stat_col2, _stat_col3, _stat_col4 = st.columns(4)
                _ov_ci = corr_info.get(_sel_sig_id, {})
                _r_val = _ov_ci.get("r", None)
                _p_val = _ov_ci.get("p", None)
                _lag_w = _ov_cfg.get("lag_weeks", 0)
                _pcs   = _ov_cfg.get("pcs", "—")

                with _stat_col1:
                    _r_disp = f"{_r_val:+.3f}" if _r_val is not None else "—"
                    _r_color = "#00D566" if (_r_val or 0) > 0.2 else ("#FF4444" if (_r_val or 0) < -0.2 else "#8892AA")
                    st.markdown(
                        f'<div style="background:#0F1118;border-radius:6px;padding:10px 14px;'
                        f'font-family:Inter,sans-serif;border:1px solid rgba(255,255,255,0.06);">'
                        f'<div style="font-size:0.65rem;color:#6B7FBF;text-transform:uppercase;'
                        f'letter-spacing:0.08em;">Correlation (r)</div>'
                        f'<div style="font-size:1.4rem;font-weight:700;color:{_r_color};">{_r_disp}</div>'
                        f'<div style="font-size:0.68rem;color:#8892AA;">with {ticker_input} price</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with _stat_col2:
                    _p_disp  = f"{_p_val:.3f}" if _p_val is not None else "—"
                    _sig_label = "Significant (p<0.05)" if _ov_sig else "Not significant"
                    _sig_color = "#00D566" if _ov_sig else "#8892AA"
                    st.markdown(
                        f'<div style="background:#0F1118;border-radius:6px;padding:10px 14px;'
                        f'font-family:Inter,sans-serif;border:1px solid rgba(255,255,255,0.06);">'
                        f'<div style="font-size:0.65rem;color:#6B7FBF;text-transform:uppercase;'
                        f'letter-spacing:0.08em;">P-value</div>'
                        f'<div style="font-size:1.4rem;font-weight:700;color:{_sig_color};">{_p_disp}</div>'
                        f'<div style="font-size:0.68rem;color:{_sig_color};">{_sig_label}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with _stat_col3:
                    _lag_disp = f"{_lag_w}w" if _lag_w else "same-period"
                    _inv_disp = " (inverse)" if _ov_is_inverse else ""
                    st.markdown(
                        f'<div style="background:#0F1118;border-radius:6px;padding:10px 14px;'
                        f'font-family:Inter,sans-serif;border:1px solid rgba(255,255,255,0.06);">'
                        f'<div style="font-size:0.65rem;color:#6B7FBF;text-transform:uppercase;'
                        f'letter-spacing:0.08em;">Configured Lag</div>'
                        f'<div style="font-size:1.4rem;font-weight:700;color:#E8EEFF;">{_lag_disp}</div>'
                        f'<div style="font-size:0.68rem;color:#8892AA;">signal leads price{_inv_disp}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with _stat_col4:
                    st.markdown(
                        f'<div style="background:#0F1118;border-radius:6px;padding:10px 14px;'
                        f'font-family:Inter,sans-serif;border:1px solid rgba(255,255,255,0.06);">'
                        f'<div style="font-size:0.65rem;color:#6B7FBF;text-transform:uppercase;'
                        f'letter-spacing:0.08em;">Predictive Score</div>'
                        f'<div style="font-size:1.4rem;font-weight:700;color:#F59E0B;">{_pcs}/10</div>'
                        f'<div style="font-size:0.68rem;color:#8892AA;">PCS (backtested weight)</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                # Source badges
                _src = _ov_cfg.get("source", "FRED")
                st.markdown(
                    source_badge(_src, f"{_sig_name} series") + "&nbsp;&nbsp;" +
                    source_badge("yfinance", f"{ticker_input} daily close"),
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Signal plotted as z-score (right axis) — how many standard deviations from "
                    "its 2-year mean. Use the lead weeks input above to visually test whether the "
                    "signal leads price action. Correlation is computed over the full 2-year window."
                )
            else:
                st.warning(f"Could not load signal data for **{_sig_name}**. Try a different signal.")

        except Exception as _ov_err:
            st.caption(f"Signal overlay unavailable: {_ov_err}")

    # Signal overlay expander closes here — back at Overview (4-space) level.
    # Reopen price_series guard so fundamentals/RSI/news sections retain their
    # original control flow (only rendered when price data is available).
    if not price_series.empty:
        # ── Financial Fundamentals Panel ──────────────────────────────────────────
        @st.cache_data(ttl=3600, max_entries=30, show_spinner=False)
        def _fetch_fundamentals(sym: str) -> dict:
            try:
                info = yf.Ticker(sym).info
                def _fmt_large(v):
                    if v is None: return "—"
                    v = float(v)
                    if v >= 1e12: return f"${v/1e12:.2f}T"
                    if v >= 1e9:  return f"${v/1e9:.2f}B"
                    if v >= 1e6:  return f"${v/1e6:.2f}M"
                    return f"${v:,.0f}"
                def _fmt_pct(v):
                    return f"{float(v)*100:.2f}%" if v is not None else "—"
                def _fmt_x(v, decimals=2):
                    return f"{float(v):.{decimals}f}x" if v is not None else "—"
                def _fmt_num(v, decimals=2):
                    return f"{float(v):.{decimals}f}" if v is not None else "—"
                return {
                    "longName":          info.get("longName") or sym,
                    "sector":            info.get("sector", "—"),
                    "industry":          info.get("industry", "—"),
                    "marketCap":         _fmt_large(info.get("marketCap")),
                    "enterpriseValue":   _fmt_large(info.get("enterpriseValue")),
                    "trailingPE":        _fmt_num(info.get("trailingPE")),
                    "forwardPE":         _fmt_num(info.get("forwardPE")),
                    "pegRatio":          _fmt_num(info.get("pegRatio")),
                    "priceToBook":       _fmt_x(info.get("priceToBook")),
                    "evToEbitda":        _fmt_x(info.get("enterpriseToEbitda")),
                    "evToRevenue":       _fmt_x(info.get("enterpriseToRevenue")),
                    "totalRevenue":      _fmt_large(info.get("totalRevenue")),
                    "grossMargins":      _fmt_pct(info.get("grossMargins")),
                    "operatingMargins":  _fmt_pct(info.get("operatingMargins")),
                    "profitMargins":     _fmt_pct(info.get("profitMargins")),
                    "revenueGrowth":     _fmt_pct(info.get("revenueGrowth")),
                    "earningsGrowth":    _fmt_pct(info.get("earningsGrowth")),
                    "returnOnEquity":    _fmt_pct(info.get("returnOnEquity")),
                    "returnOnAssets":    _fmt_pct(info.get("returnOnAssets")),
                    "debtToEquity":      _fmt_num(info.get("debtToEquity")),
                    "currentRatio":      _fmt_num(info.get("currentRatio")),
                    "freeCashflow":      _fmt_large(info.get("freeCashflow")),
                    "dividendYield":     _fmt_pct(info.get("dividendYield")),
                    "payoutRatio":       _fmt_pct(info.get("payoutRatio")),
                    "beta":              _fmt_num(info.get("beta")),
                    "sharesShort":       _fmt_large(info.get("sharesShort")),
                    "shortRatio":        _fmt_num(info.get("shortRatio")),
                    "shortPercentOfFloat": _fmt_pct(info.get("shortPercentOfFloat")),
                    "institutionsPct":   _fmt_pct(info.get("heldPercentInstitutions")),
                    "insidersPct":       _fmt_pct(info.get("heldPercentInsiders")),
                    "employees":         f"{info.get('fullTimeEmployees', 0):,}" if info.get("fullTimeEmployees") else "—",
                    "country":           info.get("country", "—"),
                    "website":           info.get("website", ""),
                    "description":       info.get("longBusinessSummary", ""),
                }
            except Exception:
                return {}

        with st.expander("Company Fundamentals and Financials", expanded=False):
            with st.spinner("Loading fundamentals…"):
                fund = _fetch_fundamentals(ticker_input)

            if not fund:
                st.warning("Could not load fundamentals for this ticker.")
            else:
                # Company header
                st.markdown(
                    f'<div style="font-family:Inter,sans-serif;margin-bottom:12px;">'
                    f'<span style="font-size:1.05rem;font-weight:700;color:#E8EEFF;">{fund["longName"]}</span>&nbsp;&nbsp;'
                    f'<span style="font-size:0.78rem;color:#8892AA;">{fund["sector"]} · {fund["industry"]}</span>'
                    f'{"&nbsp;&nbsp;<a href=" + repr(fund["website"]) + " target=_blank style=color:#7C3AED;font-size:0.78rem;>Website ↗</a>" if fund["website"] else ""}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if fund["description"]:
                    st.markdown(
                        f'<div style="font-family:Inter,sans-serif;font-size:0.82rem;color:#8892AA;'
                        f'line-height:1.65;margin-bottom:14px;border-left:2px solid rgba(124,58,237,0.3);'
                        f'padding-left:10px;">{fund["description"][:420]}{"…" if len(fund["description"]) > 420 else ""}</div>',
                        unsafe_allow_html=True,
                    )

                def _fund_table(rows):
                    """Render a 2-column label/value table."""
                    cells = "".join(
                        f'<tr style="border-bottom:1px solid rgba(255,255,255,0.04);">'
                        f'<td style="padding:5px 10px;color:#8892AA;font-size:0.78rem;">{label}</td>'
                        f'<td style="padding:5px 10px;color:#E8EEFF;font-weight:600;font-size:0.82rem;text-align:right;">{val}</td>'
                        f'</tr>'
                        for label, val in rows
                    )
                    return (
                        f'<table style="width:100%;border-collapse:collapse;font-family:Inter,sans-serif;">'
                        f'<tbody>{cells}</tbody></table>'
                    )

                fc1, fc2, fc3, fc4 = st.columns(4)
                with fc1:
                    st.markdown("**Valuation**")
                    st.html(_fund_table([
                        ("Market Cap",    fund["marketCap"]),
                        ("EV",            fund["enterpriseValue"]),
                        ("Trailing P/E",  fund["trailingPE"]),
                        ("Forward P/E",   fund["forwardPE"]),
                        ("PEG Ratio",     fund["pegRatio"]),
                        ("Price / Book",  fund["priceToBook"]),
                        ("EV / EBITDA",   fund["evToEbitda"]),
                        ("EV / Revenue",  fund["evToRevenue"]),
                    ]))
                with fc2:
                    st.markdown("**Profitability**")
                    st.html(_fund_table([
                        ("Revenue (TTM)",     fund["totalRevenue"]),
                        ("Gross Margin",      fund["grossMargins"]),
                        ("Operating Margin",  fund["operatingMargins"]),
                        ("Net Margin",        fund["profitMargins"]),
                        ("Revenue Growth",    fund["revenueGrowth"]),
                        ("Earnings Growth",   fund["earningsGrowth"]),
                        ("Return on Equity",  fund["returnOnEquity"]),
                        ("Return on Assets",  fund["returnOnAssets"]),
                    ]))
                with fc3:
                    st.markdown("**Balance Sheet & Cash**")
                    st.html(_fund_table([
                        ("Free Cash Flow",  fund["freeCashflow"]),
                        ("Debt / Equity",   fund["debtToEquity"]),
                        ("Current Ratio",   fund["currentRatio"]),
                        ("Dividend Yield",  fund["dividendYield"]),
                        ("Payout Ratio",    fund["payoutRatio"]),
                        ("Beta",            fund["beta"]),
                        ("Employees",       fund["employees"]),
                        ("Country",         fund["country"]),
                    ]))
                with fc4:
                    st.markdown("**Ownership & Short Interest**")
                    st.html(_fund_table([
                        ("Institutions %",    fund["institutionsPct"]),
                        ("Insiders %",        fund["insidersPct"]),
                        ("Short Shares",      fund["sharesShort"]),
                        ("Short Ratio",       fund["shortRatio"]),
                        ("Short % Float",     fund["shortPercentOfFloat"]),
                    ]))

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
                _vol_colors = ["#00D566" if v >= _vol_avg else "#6B7FBF" for v in vol_view.values]
                fig_vol = go.Figure(go.Bar(
                    x=vol_view.index, y=vol_view.values, marker_color=_vol_colors,
                    hovertemplate="%{x|%Y-%m-%d}: %{y:,.0f}<extra></extra>",
                ))
                fig_vol.add_hline(y=_vol_avg, line_dash="dot", line_color="#7C3AED", opacity=0.5,
                                   annotation_text="50-day avg", annotation_font_size=10)
                fig_vol.update_layout(
                    height=220, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
                    xaxis=dict(showgrid=False, tickfont=dict(color="#8892AA", size=10), fixedrange=False),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#8892AA", size=10),
                               autorange=True, fixedrange=False, tickformat=".2s"),
                    margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
                )
                st.plotly_chart(
                    fig_vol, use_container_width=True,
                    config=PLOTLY_CONFIG_INTERACTIVE, theme=None,
                )
                st.caption(
                    f"Bars colored green when above the trailing 50-day average volume "
                    f"({_vol_avg:,.0f}), tan when below — a rough proxy for unusually active days."
                )
                st.html(source_badge("yfinance", "Daily Volume"))
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
                    line=dict(color="#F59E0B", width=2, shape="spline", smoothing=0.3),
                    hovertemplate="%{x|%Y-%m-%d}: RSI=%{y:.1f}<extra></extra>",
                ))
                fig_rsi.add_hline(y=70, line_dash="dot", line_color="#FF4444", opacity=0.6,
                                   annotation_text="Overbought (70)", annotation_font_size=10)
                fig_rsi.add_hline(y=30, line_dash="dot", line_color="#00D566", opacity=0.6,
                                   annotation_text="Oversold (30)", annotation_font_size=10)
                fig_rsi.update_layout(
                    height=220, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
                    xaxis=dict(showgrid=False, tickfont=dict(color="#8892AA", size=10), fixedrange=False),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#8892AA", size=10),
                               range=[0, 100], fixedrange=True),  # RSI is 0-100 by definition
                    margin=dict(l=0, r=0, t=10, b=0), showlegend=False,
                )
                st.plotly_chart(
                    fig_rsi, use_container_width=True,
                    config=PLOTLY_CONFIG_INTERACTIVE, theme=None,
                )
                _latest_rsi = rsi_full.dropna()
                if not _latest_rsi.empty:
                    _rsi_val = _latest_rsi.iloc[-1]
                    _rsi_read = "Overbought" if _rsi_val >= 70 else ("Oversold" if _rsi_val <= 30 else "Neutral")
                    st.caption(
                        f"Latest reading: {_rsi_val:.1f} ({_rsi_read}). Wilder's standard RSI — a "
                        "momentum indicator, not a buy/sell signal on its own; extreme readings can "
                        "persist during strong trends rather than immediately reversing."
                    )
                    st.html(source_badge("yfinance", "RSI·14 · computed"))
            else:
                st.info(f"Not enough price history yet to compute RSI for {ticker_input}.")

    # ── Catalysts & News ──────────────────────────────────────────────────────────
    # Earnings timeline + recent headlines — both sourced from yfinance, no extra
    # API key required. Placed here (after price/volume/RSI, before prediction
    # model) so a user reading the chart can immediately see WHAT drove recent
    # price moves before looking at the forward model's probabilities.
    st.html(section_label("Catalysts & News", color="#F59E0B", dot="#F59E0B"))

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
                        _bg = "rgba(245,158,11,0.08)"
                        _border = "#F59E0B"
                        _badge = f'<span style="background:#F59E0B;color:white;font-size:0.68rem;padding:1px 6px;border-radius:3px;font-weight:700;">UPCOMING</span>'
                        _body = f'<div style="font-size:0.78rem;color:#8892AA;margin-top:4px;">{_when}</div>'
                        if _e["eps_estimate"] is not None:
                            _body += f'<div style="font-size:0.78rem;color:#8892AA;">Est. EPS: <b>{_e["eps_estimate"]:+.2f}</b></div>'
                    else:
                        # Reported
                        _sp = _e["surprise_pct"]
                        if _sp is None:
                            _border = "#6B7FBF"; _bg = "#F5F0E8"
                            _badge = '<span style="font-size:0.68rem;color:#6B7FBF;font-weight:600;">REPORTED</span>'
                            _beat_txt = ""
                        elif _sp >= 0:
                            _border = "#00D566"; _bg = "#F0F8F0"
                            _badge = f'<span style="background:#00D566;color:#0B0D12;font-size:0.68rem;padding:1px 6px;border-radius:3px;font-weight:700;">BEAT +{_sp:.1f}%</span>'
                            _beat_txt = ""
                        else:
                            _border = "#FF4444"; _bg = "rgba(255,68,68,0.08)"
                            _badge = f'<span style="background:#FF4444;color:#0B0D12;font-size:0.68rem;padding:1px 6px;border-radius:3px;font-weight:700;">MISS {_sp:.1f}%</span>'
                            _beat_txt = ""
                        _when = f"{abs(_days_delta)}d ago" if abs(_days_delta) < 365 else _e["date"].strftime("%b %d, %Y")
                        _act_str = f'<b>{_e["eps_actual"]:+.2f}</b>' if _e["eps_actual"] is not None else "—"
                        _est_str = f'{_e["eps_estimate"]:+.2f}' if _e["eps_estimate"] is not None else "—"
                        _body = (
                            f'<div style="font-size:0.78rem;color:#8892AA;margin-top:4px;">{_when}</div>'
                            f'<div style="font-size:0.78rem;color:#8892AA;">EPS: {_act_str} <span style="color:#8892AA;">(est {_est_str})</span></div>'
                        )

                    st.markdown(f"""
                    <div style="background:{_bg};border-left:3px solid {_border};border-radius:4px;
                                padding:8px 12px;margin-bottom:8px;font-family:Inter,sans-serif;">
                        <div style="font-size:0.80rem;font-weight:700;color:#E8EEFF;">
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
                        _title_html = f'<a href="{_url}" target="_blank" style="color:#00C8E0;text-decoration:none;font-weight:600;">{_title}</a>'
                    else:
                        _title_html = f'<span style="color:#E8EEFF;font-weight:600;">{_title}</span>'

                    st.markdown(f"""
                    <div style="padding:8px 0 8px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-family:Inter,sans-serif;">
                        <div style="font-size:0.85rem;line-height:1.4;">{_title_html}</div>
                        <div style="font-size:0.72rem;color:#8892AA;margin-top:3px;">{_meta}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.caption("No recent headlines found for this ticker.")
        except Exception as _news_err:
            st.caption(f"News unavailable: {_news_err}")

    st.divider()

    # ── Contextual Pro Upgrade Nudge ───────────────────────────────────────────────
    # Shown after the user has seen real signal value — reciprocity principle.
    # Anonymous → push to signup. Logged-in free → push to upgrade.
    # Pro users see nothing here.
    try:
        _tdd_user = st.session_state.get("user")
        _tdd_is_pro = False
        if _tdd_user:
            _tdd_tier_key = f"_tier_{_tdd_user['id']}"
            if _tdd_tier_key not in st.session_state:
                from utils.billing import get_user_tier
                st.session_state[_tdd_tier_key] = get_user_tier(_tdd_user["id"])
            _tdd_is_pro = st.session_state.get(_tdd_tier_key) == "pro"

        if not _tdd_is_pro:
            _PURPLE = "#7C3AED"
            if _tdd_user:
                # Logged-in free user → upgrade nudge
                st.markdown(f"""
                <div style="background:rgba(124,58,237,0.07);border:1px solid rgba(124,58,237,0.22);
                            border-radius:12px;padding:20px 24px;font-family:Inter,sans-serif;margin:12px 0;">
                    <div style="font-size:0.60rem;letter-spacing:0.16em;font-weight:700;
                                color:{_PURPLE};margin-bottom:10px;">UNLOCK THE FULL PICTURE — PRO</div>
                    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:16px;">
                        <div style="background:rgba(18,21,30,0.6);border-radius:8px;padding:10px 14px;
                                    border:1px solid rgba(255,255,255,0.06);">
                            <div style="font-size:0.75rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">7 AM Digest</div>
                            <div style="font-size:0.70rem;color:#8892AA;line-height:1.5;">
                                Today's top setups from all 47 signals, in your inbox before market open.
                            </div>
                        </div>
                        <div style="background:rgba(18,21,30,0.6);border-radius:8px;padding:10px 14px;
                                    border:1px solid rgba(255,255,255,0.06);">
                            <div style="font-size:0.75rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">Price and Signal Alerts</div>
                            <div style="font-size:0.70rem;color:#8892AA;line-height:1.5;">
                                Get notified the moment a signal flips for a ticker in your watchlist.
                            </div>
                        </div>
                        <div style="background:rgba(18,21,30,0.6);border-radius:8px;padding:10px 14px;
                                    border:1px solid rgba(255,255,255,0.06);">
                            <div style="font-size:0.75rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">Signal Backtester</div>
                            <div style="font-size:0.70rem;color:#8892AA;line-height:1.5;">
                                Build custom signal rules and backtest them against historical prices.
                            </div>
                        </div>
                    </div>
                    <div style="font-size:0.72rem;color:#8892AA;">
                        7-day free trial · cancel any time · from $20/mo
                    </div>
                </div>
                """, unsafe_allow_html=True)
                _gu_c1, _gu_c2, _ = st.columns([1.2, 1.2, 3])
                with _gu_c1:
                    if st.button("Start Free Trial →", type="primary", key="tdd_upgrade_cta",
                                 use_container_width=True):
                        st.switch_page("pages/29_Upgrade.py")
                with _gu_c2:
                    if st.button("Add to Watchlist", key="tdd_wl_cta2",
                                 use_container_width=True):
                        st.session_state["chart_ticker"] = ticker_input
                        st.switch_page("pages/10_Watchlist.py")
            else:
                # Anonymous user → signup nudge
                st.markdown(f"""
                <div style="background:rgba(124,58,237,0.06);border:1px solid rgba(124,58,237,0.18);
                            border-radius:12px;padding:18px 22px;font-family:Inter,sans-serif;margin:12px 0;">
                    <div style="font-size:0.60rem;letter-spacing:0.16em;font-weight:700;
                                color:{_PURPLE};margin-bottom:8px;">FREE ACCOUNT — SAVE &amp; TRACK</div>
                    <div style="font-size:0.85rem;color:#E8EEFF;font-weight:600;margin-bottom:6px;">
                        Save {ticker_input} to your watchlist and get alerts when signals flip.
                    </div>
                    <div style="font-size:0.75rem;color:#8892AA;">
                        Free accounts include watchlist tracking + signal flip alerts.
                        Pro ($20/mo) adds the 7 AM digest, email alerts, and Signal Backtester.
                    </div>
                </div>
                """, unsafe_allow_html=True)
                _au_c1, _au_c2, _ = st.columns([1.2, 1.2, 3])
                with _au_c1:
                    if st.button("Create Free Account", type="primary", key="tdd_signup_cta",
                                 use_container_width=True):
                        st.switch_page("pages/home_page.py")
                with _au_c2:
                    if st.button("See Pro features →", key="tdd_pro_peek_cta",
                                 use_container_width=True):
                        st.switch_page("pages/29_Upgrade.py")
    except Exception:
        pass  # Never let this crash the page

    st.divider()

    # ── Forward Prediction Model ───────────────────────────────────────────────────
    from utils.analysis import predict_ticker_forward  # noqa: E402 (deferred import keeps page fast)

    st.markdown(
        section_label("SIGNAL-BASED PREDICTION MODEL", color="#8187F7", dot="#8187F7"),
        unsafe_allow_html=True,
    )
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
    reg_color   = "#00D566" if regime == "BULL" else ("#FF4444" if regime == "BEAR" else "#6B7FBF")
    h30         = pred["horizons"][0]   # 30-day horizon

    # ── Probability bar ───────────────────────────────────────────────────────────
    bull_w = pred["final_bull"]
    bear_w = pred["final_bear"]
    neut_w = pred["final_neutral"]

    st.markdown(f"""
    <div style="margin-bottom:8px;">
        <div style="font-size:0.72rem;color:#8892AA;letter-spacing:0.06em;margin-bottom:4px;">
            DIRECTIONAL PROBABILITY (30-DAY HORIZON)
        </div>
        <div style="display:flex;border-radius:6px;overflow:hidden;height:32px;">
            <div style="width:{bull_w:.0f}%;background:#00D566;display:flex;align-items:center;
                        justify-content:center;color:white;font-size:0.80rem;font-weight:700;">
                ▲ {bull_w:.0f}%
            </div>
            <div style="width:{neut_w:.0f}%;background:#6B7FBF;display:flex;align-items:center;
                        justify-content:center;color:white;font-size:0.80rem;font-weight:700;">
                ● {neut_w:.0f}%
            </div>
            <div style="width:{bear_w:.0f}%;background:#FF4444;display:flex;align-items:center;
                        justify-content:center;color:white;font-size:0.80rem;font-weight:700;">
                ▼ {bear_w:.0f}%
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Horizon cards ─────────────────────────────────────────────────────────────
    hor_cols = st.columns(3)
    for hcol, h in zip(hor_cols, pred["horizons"]):
        h_color = "#00D566" if h["bull_pct"] > 60 else ("#FF4444" if h["bear_pct"] > 60 else "#6B7FBF")
        with hcol:
            st.markdown(f"""
            <div class="ua-spotlight ua-kpi-animate" style="--ua-spotlight-accent:{h_color};text-align:center;padding:18px 16px 16px;">
                <div style="font-size:0.60rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:6px;">{h['label']} Forecast</div>
                <div style="font-size:2.6rem;font-weight:900;color:{h_color};
                     text-shadow:0 0 24px {h_color}45;line-height:1;margin-bottom:4px;">
                    {h['bull_pct']:.0f}%
                </div>
                <div style="font-size:0.72rem;color:#8892AA;font-weight:600;margin-bottom:8px;">Bull Probability</div>
                <div style="font-size:0.68rem;color:#6B7FBF;border-top:1px solid rgba(255,255,255,0.06);padding-top:8px;">
                    Price range<br>
                    <b style="color:#B8C0D4;">${h['price_low']:.2f} — ${h['price_high']:.2f}</b>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("")

    # ── Key signals driving prediction + plain English ────────────────────────────
    pred_c1, pred_c2 = st.columns([3, 2])

    with pred_c1:
        _plain = pred['plain_english'].replace("\\$", "$")
        st.markdown(f"""
        <div style="background:rgba(18,21,30,0.85);border-radius:6px;padding:14px 16px;border:1px solid rgba(255,255,255,0.08);
                    font-family:Inter,sans-serif;font-size:0.83rem;color:#B8C0D4;line-height:1.6;">
            <div style="font-size:0.72rem;color:#8892AA;letter-spacing:0.06em;margin-bottom:6px;">
                PLAIN-ENGLISH SUMMARY
            </div>
            {_plain}
        </div>
        """, unsafe_allow_html=True)

    with pred_c2:
        st.markdown(f"""
        <div style="background:rgba(18,21,30,0.85);border-radius:6px;padding:14px 16px;border:1px solid rgba(255,255,255,0.08);
                    font-family:Inter,sans-serif;">
            <div style="font-size:0.72rem;color:#8892AA;letter-spacing:0.06em;margin-bottom:8px;">
                MOMENTUM SNAPSHOT
            </div>
            <table style="width:100%;font-size:0.80rem;color:#E8EEFF;">
                <tr><td style="color:#6B7FBF;">1-Month</td>
                    <td style="text-align:right;font-weight:700;color:{'#00D566' if pred['momentum_1m']>0 else '#FF4444'};">
                        {pred['momentum_1m']:+.1f}%</td></tr>
                <tr><td style="color:#6B7FBF;">3-Month</td>
                    <td style="text-align:right;font-weight:700;color:{'#00D566' if pred['momentum_3m']>0 else '#FF4444'};">
                        {pred['momentum_3m']:+.1f}%</td></tr>
                <tr><td style="color:#6B7FBF;">6-Month</td>
                    <td style="text-align:right;font-weight:700;color:{'#00D566' if pred['momentum_6m']>0 else '#FF4444'};">
                        {pred['momentum_6m']:+.1f}%</td></tr>
                <tr><td style="color:#6B7FBF;">1-Year</td>
                    <td style="text-align:right;font-weight:700;color:{'#00D566' if pred['momentum_1y']>0 else '#FF4444'};">
                        {pred['momentum_1y']:+.1f}%</td></tr>
                <tr><td style="color:#6B7FBF;padding-top:6px;">Ann. Volatility</td>
                    <td style="text-align:right;font-weight:700;color:#6B7FBF;padding-top:6px;">
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
        <div style="background:rgba(0,213,102,0.05);border-radius:6px;padding:16px;
                    border-left:4px solid #00D566;border-top:1px solid #A8C09A;
                    border-right:1px solid #A8C09A;border-bottom:1px solid #A8C09A;
                    min-height:200px;font-family:Inter,sans-serif;">
            <div style="color:#00D566;font-size:0.95rem;font-weight:700;margin-bottom:12px;letter-spacing:0.02em;">
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
        <div style="background:rgba(255,68,68,0.05);border-radius:6px;padding:16px;
                    border-left:4px solid #FF4444;border-top:1px solid #E8A8A8;
                    border-right:1px solid #E8A8A8;border-bottom:1px solid #E8A8A8;
                    min-height:200px;font-family:Inter,sans-serif;">
            <div style="color:#FF4444;font-size:0.95rem;font-weight:700;margin-bottom:12px;letter-spacing:0.02em;">
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
            _header = "What Would Change the Bull Case"
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
            _header = "What Would Change the Bear Case"
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
                f'<span style="color:#F59E0B;font-size:1.0rem;flex-shrink:0;">◈</span>'
                f'<div style="font-size:0.80rem;color:#B8C0D4;line-height:1.6;">{line}</div>'
                f'</div>'
                for line in _tripwire_lines
            )
            st.markdown(
                f'<div style="background:rgba(245,158,11,0.07);border-radius:8px;padding:16px 18px;'
                f'margin:14px 0;border-left:4px solid #F59E0B;font-family:Inter,sans-serif;">'
                f'<div style="font-size:0.72rem;font-weight:700;color:#F59E0B;'
                f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:10px;">'
                f'{_header}</div>'
                f'{_items_html}'
                f'<div style="font-size:0.65rem;color:#8892AA;margin-top:8px;">'
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
    with st.expander("Playbook — historical setups at this score level"):
        try:
            _ph = get_score_history(ticker_input, days=365)
            if len(_ph) < 5:
                st.info("Not enough score history yet for a playbook. Come back after this ticker has been viewed a few more times over the coming weeks.")
            else:
                import yfinance as yf
                import pandas as pd
                _crossing_threshold = 70 if confluence["case"] == "BULL" else 35
                _direction          = "above" if confluence["case"] == "BULL" else "below"
                _color              = "#00D566" if confluence["case"] == "BULL" else "#FF4444"

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
                                f'<div style="font-size:0.78rem;color:#B8C0D4;margin-bottom:10px;">'
                                f'The last <b>{len(_playbook_rows)}</b> time(s) '
                                f'<b style="color:{_color}">{ticker_input}</b> scored '
                                f'{_crossing_threshold}+ {_direction}, forward returns were:</div>',
                                unsafe_allow_html=True,
                            )
                            _pb_df = pd.DataFrame(_playbook_rows)
                            st.dataframe(_pb_df, use_container_width=True, hide_index=True)
                            st.caption("Small sample: treat this as illustrative context, not statistical proof. Score history only accumulates when this page is visited.")
                        else:
                            st.info("Could not compute forward returns for the crossing dates found.")
        except Exception as _pb_err:
            st.caption(f"Playbook unavailable: {_pb_err}")

    # ── Regime-Conditional Return Distributions ───────────────────────────────────
    # For each score bucket (50–60, 60–70, 70–80, 80+), show what actual
    # forward returns looked like across ALL tickers in our history when they
    # were in that score range. Context for "what does score X typically mean?"
    with st.expander("What this score level historically implies — Return Distribution"):
        try:
            _all_score_hist = []
            # Pull score history for this ticker
            _this_hist = get_score_history(ticker_input, days=365)
            if len(_this_hist) < 5:
                st.info("Not enough score history yet. Return distributions accumulate as this ticker is viewed over time.")
            else:
                import yfinance as yf

                _px_data = yf.download(ticker_input, period="2y", auto_adjust=True, progress=False)
                if _px_data.empty:
                    st.info("Price data unavailable for return distribution.")
                else:
                    _px_c = _px_data["Close"].squeeze()
                    _BUCKETS = [
                        (50, 60,  "50–60 (Neutral-leaning bull)",   "#6B7FBF"),
                        (60, 70,  "60–70 (Moderate bull)",          "#2E7D32"),
                        (70, 80,  "70–80 (Strong bull)",            "#00D566"),
                        (80, 100, "80–100 (High-conviction bull)",  "#003300"),
                        (20, 35,  "20–35 (Bear signal)",            "#FF4444"),
                        (35, 50,  "35–50 (Neutral-leaning bear)",   "#B71C1C"),
                    ]
                    _bucket_results = {}
                    for _lo, _hi, _label, _col in _BUCKETS:
                        _returns = []
                        for _snap in _this_hist:
                            _s = float(_snap["score"] or 50)
                            if _lo <= _s < _hi:
                                _dt = pd.Timestamp(_snap["snapshot_date"])
                                try:
                                    for _weeks, _lbl in [(4, "4w"), (8, "8w"), (12, "12w")]:
                                        _fwd = _dt + pd.Timedelta(weeks=_weeks)
                                        if _fwd <= _px_c.index[-1]:
                                            _ep = float(_px_c.asof(_dt))
                                            _fp = float(_px_c.asof(_fwd))
                                            if _ep > 0:
                                                _returns.append({
                                                    "weeks": _lbl,
                                                    "ret": round((_fp / _ep - 1) * 100, 2)
                                                })
                                except Exception:
                                    pass
                        if _returns:
                            _df_r = pd.DataFrame(_returns)
                            _bucket_results[_label] = {
                                "color":  _col,
                                "count":  len(_this_hist),
                                "by_week": {
                                    w: _df_r[_df_r["weeks"] == w]["ret"].tolist()
                                    for w in ["4w", "8w", "12w"]
                                },
                            }

                    if not _bucket_results:
                        st.info("No score readings in any bucket yet — more history needed.")
                    else:
                        _current_score = confluence["overall_score"]
                        # Find which bucket the current score falls in
                        _curr_bucket_label = None
                        for _lo, _hi, _label, _ in _BUCKETS:
                            if _lo <= _current_score < _hi:
                                _curr_bucket_label = _label
                                break

                        if _curr_bucket_label:
                            st.markdown(
                                f'<div style="background:#7C3AED;border-radius:6px;padding:8px 14px;'
                                f'margin-bottom:12px;font-family:Inter,sans-serif;">'
                                f'<span style="color:#C9A84C;font-size:0.70rem;text-transform:uppercase;'
                                f'letter-spacing:0.08em;">CURRENT SCORE BUCKET</span> '
                                f'<span style="color:#EEF3FA;font-weight:700;">{_curr_bucket_label}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

                        fig_dist = go.Figure()
                        _shown = 0
                        for _label, _dat in _bucket_results.items():
                            _is_curr = (_label == _curr_bucket_label)
                            for _wk in ["4w", "8w", "12w"]:
                                _vals = _dat["by_week"].get(_wk, [])
                                if not _vals:
                                    continue
                                fig_dist.add_trace(go.Box(
                                    y=_vals,
                                    name=f"{_label[:18]} {_wk}",
                                    marker_color=_dat["color"],
                                    opacity=1.0 if _is_curr else 0.45,
                                    boxmean=True,
                                    hovertemplate=(
                                        f"<b>{_label}</b><br>"
                                        f"Horizon: {_wk}<br>"
                                        f"Median: %{{median:.1f}}%<br>"
                                        f"Observations: {len(_vals)}"
                                        f"<extra></extra>"
                                    ),
                                ))
                                _shown += 1

                        if _shown > 0:
                            fig_dist.add_hline(y=0, line_dash="dot", line_color="#6B7FBF", opacity=0.5)
                            fig_dist.update_layout(
                                title=dict(
                                    text=f"{ticker_input} — Forward return distributions by score bucket",
                                    font=dict(size=14, color="#7C3AED"), x=0.5,
                                ),
                                yaxis_title="Forward Return (%)",
                                height=380,
                                paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
                                margin=dict(l=50, r=20, t=50, b=60),
                                font=dict(family="Inter, sans-serif", color="#8892AA"),
                                showlegend=True,
                                legend=dict(font=dict(size=9)),
                            )
                            fig_dist = style_distribution_chart(fig_dist, height=380)
                            st.plotly_chart(fig_dist, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
                            st.caption(
                                f"Box plot of {ticker_input}'s actual forward returns at each time horizon "
                                f"when its score was in each bucket. Current score bucket highlighted. "
                                "Small samples: interpret with caution. History grows with each visit."
                            )
        except Exception:
            pass

    st.divider()

    # ── Signal Detail Table ───────────────────────────────────────────────────────
    st.markdown("### Signal Detail Table")
    st.caption("Every signal scored and contextualized. Click on any row to see its sparkline chart.")

    with st.expander("Understanding the table columns"):
        st.markdown("""
        | Column | Explanation |
        |---|---|
        | **Status** | Bullish / Bearish / Neutral based on current reading vs. 52-week history |
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
            r_color = "#00D566" if dr['Corr (r)'] > 0 else "#FF4444"
            driver_html += f"""
            <div style="flex:1;background:rgba(18,21,30,0.85);border-radius:6px;padding:12px;
                        border:1px solid rgba(255,255,255,0.08);border-top:3px solid {r_color};font-family:Inter,sans-serif;">
                <div style="font-size:0.70rem;color:#6B7FBF;text-transform:uppercase;letter-spacing:0.05em;
                            white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{dr['Signal'][:30]}</div>
                <div style="font-size:1.4rem;font-weight:700;color:{r_color};margin:4px 0;">{r_fmt}</div>
                <div style="font-size:0.75rem;color:#8892AA;">r with {ticker_input} price</div>
                <div style="font-size:0.75rem;color:#E8EEFF;margin-top:4px;">Score: <b>{dr['Score']:.0f}</b> &nbsp; {dr['Status']}</div>
            </div>"""

        st.markdown(f"""
        <div style="margin-bottom:12px;">
            <div style="font-size:0.72rem;color:#6B7FBF;text-transform:uppercase;
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
            card_color = "#00D566" if "bullish" in s_key else ("#FF4444" if "bearish" in s_key else "#6B7FBF")
            bg_color   = "#F0F7F0" if "bullish" in s_key else ("rgba(255,68,68,0.08)" if "bearish" in s_key else "#F7F5F0")
            sym        = "▲" if "bullish" in s_key else ("▼" if "bearish" in s_key else "●")

            corr_note = (
                f"&nbsp; | &nbsp; r = {corr_r:+.2f} with {ticker_input} "
                f"(impact: {impact_val:.1f})"
            ) if corr_r != 0 else ""

            st.markdown(f"""
            <div style="background:{bg_color};border-radius:6px;padding:12px 16px;margin-bottom:4px;
                        border-left:4px solid {card_color};border:1px solid rgba(0,0,0,0.08);
                        font-family:Inter,sans-serif;">
                <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:4px;">
                    <span style="color:{card_color};font-weight:700;font-size:0.88rem;">{sym} {sig_name}</span>
                    <span style="font-size:0.75rem;color:{card_color};font-weight:600;">{sig_status}</span>
                    <span style="font-size:0.75rem;color:#6B7FBF;">Score: {sig_score:.0f}/100{corr_note}</span>
                </div>
                <div style="font-size:0.82rem;color:#B8C0D4;line-height:1.55;">{reason_txt}</div>
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

        _ecol1, _ecol2 = st.columns([2, 2])
        with _ecol1:
            st.download_button(
                f"Download {ticker_input} Signal Analysis (CSV)",
                csv_b,
                file_name=f"UA_{ticker_input}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with _ecol2:
            if st.button(
                "Export Full PDF Report",
                key="tdd_to_pdf",
                use_container_width=True,
                help="Opens the Export page pre-filled with this ticker",
            ):
                st.session_state["export_ticker"] = ticker_input
                st.switch_page("pages/28_Export.py")

elif section == "Thesis Workspace":
    st.html(section_label("THESIS WORKSPACE", color="#7C3AED", dot="#7C3AED"))
    st.caption(
        "Turn the live research into a durable decision record. Save what you believe, "
        "what could change your mind, and the timeframe in which the thesis should work."
    )

    from utils.thesis import get_thesis, save_thesis

    _thesis_user = st.session_state.get("user") or {}
    _thesis_user_id = _thesis_user.get("id")
    if not _thesis_user_id:
        st.warning("Sign in to save a private investment thesis.")
    else:
        _saved_thesis = get_thesis(_thesis_user_id, ticker_input) or {}
        _stance_options = ["Bullish", "Neutral", "Bearish"]
        _status_options = ["active", "closed", "invalidated"]
        _saved_stance = _saved_thesis.get("stance", "Neutral")
        _saved_status = _saved_thesis.get("status", "active")
        try:
            _current_price = float(price_series.dropna().iloc[-1]) if not price_series.empty else None
        except Exception:
            _current_price = None
        _entry_price = _saved_thesis.get("entry_price") or _current_price
        _entry_score = _saved_thesis.get("entry_score") or float(confluence.get("overall_score", 50))

        _summary_cols = st.columns(4)
        _summary_cols[0].metric("Current Score", f"{confluence.get('overall_score', 50):.0f}/100")
        _summary_cols[1].metric("Saved Stance", _saved_stance)
        _summary_cols[2].metric("Status", _saved_status.title())
        _summary_cols[3].metric(
            "Decision Entry",
            f"${_entry_price:,.2f}" if _entry_price else "Not recorded",
        )

        with st.form(f"thesis_form_{ticker_input}"):
            _form_cols = st.columns([1, 1, 1])
            with _form_cols[0]:
                _stance = st.selectbox(
                    "Stance",
                    _stance_options,
                    index=_stance_options.index(_saved_stance) if _saved_stance in _stance_options else 1,
                )
            with _form_cols[1]:
                _horizon = st.number_input(
                    "Expected horizon (weeks)",
                    min_value=1,
                    max_value=260,
                    value=int(_saved_thesis.get("horizon_weeks") or 12),
                )
            with _form_cols[2]:
                _status = st.selectbox(
                    "Decision status",
                    _status_options,
                    index=_status_options.index(_saved_status) if _saved_status in _status_options else 0,
                    format_func=lambda value: value.title(),
                )

            _thesis_text = st.text_area(
                "Core thesis",
                value=_saved_thesis.get("thesis", ""),
                placeholder="What do you believe the market is underestimating or overestimating?",
                height=130,
            )
            _detail_cols = st.columns(2)
            with _detail_cols[0]:
                _catalysts = st.text_area(
                    "Catalysts",
                    value=_saved_thesis.get("catalysts", ""),
                    placeholder="Events that could confirm or accelerate the thesis",
                    height=110,
                )
                _risks = st.text_area(
                    "Primary risks",
                    value=_saved_thesis.get("risks", ""),
                    placeholder="What could impair the expected outcome?",
                    height=110,
                )
            with _detail_cols[1]:
                _invalidation = st.text_area(
                    "What would change your mind?",
                    value=_saved_thesis.get("invalidation", ""),
                    placeholder="Define the evidence or threshold that invalidates this thesis",
                    height=110,
                )
                _outcome = st.text_area(
                    "Review and outcome notes",
                    value=_saved_thesis.get("outcome_notes", ""),
                    placeholder="Record what happened, what you learned, and whether the reasoning held",
                    height=110,
                )

            _save_thesis = st.form_submit_button("Save Thesis", type="primary", use_container_width=True)

        if _save_thesis:
            try:
                save_thesis(
                    user_id=_thesis_user_id,
                    ticker=ticker_input,
                    stance=_stance,
                    status=_status,
                    horizon_weeks=int(_horizon),
                    thesis=_thesis_text,
                    catalysts=_catalysts,
                    risks=_risks,
                    invalidation=_invalidation,
                    outcome_notes=_outcome,
                    entry_price=_entry_price,
                    entry_score=_entry_score,
                )
                st.success(f"{ticker_input} thesis saved to your private decision journal.")
                st.rerun()
            except ValueError as _thesis_error:
                st.error(str(_thesis_error))

elif section == "Insider & Short Interest":
    st.html(section_label("INSIDER AND SHORT INTEREST", color="#55A7D8", dot="#55A7D8"))
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
        ins_color = "#00D566" if _insider_score["status"] == "bullish" else ("#FF4444" if _insider_score["status"] == "bearish" else "#6B7FBF")
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
                        f'<div style="background:rgba(0,213,102,0.08);border-radius:7px;padding:10px 14px;'
                        f'margin-bottom:10px;border-left:4px solid #00D566;font-family:Inter,sans-serif;">'
                        f'<b style="color:#35C98B;font-size:0.88rem;letter-spacing:0.04em;">INSIDER CLUSTER BUY</b> — '
                        f'<span style="font-size:0.82rem;color:#B8C0D4;">'
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

        _tx_cols = ["date", "insider", "role", "code", "shares", "price", "value"]
        if "filed_date" in _insider_tx_early.columns:
            _tx_cols = ["date", "filed_date"] + [c for c in _tx_cols if c != "date"]
        tx_display = _insider_tx_early[[c for c in _tx_cols if c in _insider_tx_early.columns]].copy()
        tx_display["date"] = tx_display["date"].dt.strftime("%Y-%m-%d")
        if "filed_date" in tx_display.columns:
            tx_display["filed_date"] = tx_display["filed_date"].fillna("—")
        tx_display["code"] = tx_display["code"].map({"P": "Purchase", "S": "Sale"})
        tx_display["price"] = tx_display["price"].map(lambda v: f"${v:,.2f}")
        tx_display["value"] = tx_display["value"].map(lambda v: f"${v:,.0f}")
        tx_display = tx_display.rename(columns={
            "date": "Trade Date", "filed_date": "Filed (Known As Of)",
            "insider": "Insider", "role": "Role", "code": "Type",
            "shares": "Shares", "price": "Price", "value": "Value",
        })
        st.dataframe(tx_display, use_container_width=True, hide_index=True)
        st.caption("**Trade Date** = when the transaction occurred. **Filed (Known As Of)** = when SEC received the disclosure — the earliest a market participant could have acted on this. STOCK Act requires filing within 45 days of the trade; late filers are common.")
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
        si_color = "#00D566" if _short_interest_score["status"] == "bullish" else ("#FF4444" if _short_interest_score["status"] == "bearish" else "#6B7FBF")
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
    st.html(section_label("13F AND FEDERAL CONTRACTS", color="#D6A34A", dot="#D6A34A"))
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
                    line=dict(color="#7C3AED", width=2.5),
                ))
                fig_c.update_layout(
                    title="Monthly Federal Contract Awards",
                    height=250, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
                    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#8892AA")),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#8892AA"),
                               title="Award Amount (USD)"),
                    legend=dict(font=dict(color="#E8EEFF"), bgcolor="rgba(18,21,30,0.90)"),
                    margin=dict(l=0, r=0, t=30, b=0),
                )
                fig_c = style_chart(fig_c, height=270, hovermode="x unified")
                st.plotly_chart(fig_c, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

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
    st.markdown(
        section_label("DEEP CORRELATION SCAN — LEAD TIME OPTIMIZER", color="#55A7D8", dot="#55A7D8"),
        unsafe_allow_html=True,
    )
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
    # in the config. corr_info is already computed for all ~47 signals above
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
            return f"{name}  (r={r:+.2f}, significant)"
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
                bar_colors = ["#00D566" if c > 0 else "#FF4444" for c in corrs]
                if deep_lag < len(bar_colors):
                    bar_colors[deep_lag] = "#F59E0B"
                fig_lag = go.Figure(go.Bar(
                    x=[f"{l}w" for l in lags], y=corrs, marker_color=bar_colors,
                    text=[f"{c:+.3f}" for c in corrs], textposition="outside",
                    textfont=dict(size=9, color="#E8EEFF"),
                    hovertemplate="Lag %{x}: r = %{y:.4f}<extra></extra>",
                ))
                fig_lag.add_hline(y=0, line_color="#8892AA")
                fig_lag.update_layout(
                    height=260, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
                    xaxis=dict(showgrid=False, tickfont=dict(color="#8892AA"), title="Lag (weeks)"),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#8892AA"), title="Pearson r"),
                    margin=dict(l=0, r=0, t=10, b=0),
                )
                fig_lag = style_chart(fig_lag, height=280, hovermode="closest", legend=False)
                st.plotly_chart(fig_lag, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

            # Rolling 26-week correlation
            rolling = deep_corr.get("rolling_corr", pd.Series(dtype=float))
            if not rolling.empty and rolling.dropna().shape[0] > 5:
                fig_roll = go.Figure(go.Scatter(
                    x=rolling.dropna().index, y=rolling.dropna().values, mode="lines",
                    fill="tozeroy", line=dict(color="#7C3AED", width=2),
                    fillcolor="rgba(28,43,74,0.12)",
                    hovertemplate="%{x}: r=%{y:.3f}<extra></extra>",
                ))
                fig_roll.add_hline(y=0, line_color="#8892AA")
                fig_roll.update_layout(
                    title=dict(text="Rolling 26-Week Correlation — is the relationship stable?", font=dict(size=12, color="#7C3AED")),
                    height=220, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
                    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#8892AA")),
                    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#8892AA"),
                               title="26w rolling r", range=[-1, 1]),
                    margin=dict(l=0, r=0, t=30, b=0),
                )
                fig_roll = style_area_chart(fig_roll, line_color="#8187F7", height=240)
                st.plotly_chart(fig_roll, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

            # Signal + price overlay
            aligned = deep_corr.get("aligned", pd.DataFrame())
            if not aligned.empty:
                sig_norm = aligned["signal"] / aligned["signal"].iloc[0] * 100
                prc_norm = aligned["price"]  / aligned["price"].iloc[0]  * 100
                fig_ov = make_subplots(specs=[[{"secondary_y": True}]])
                fig_ov.add_trace(go.Scatter(
                    x=sig_norm.index, y=sig_norm.values,
                    name=f"{deep_cfg.get('name','')[:28]} (lag={deep_lag}w)",
                    line=dict(color="#7C3AED", width=2),
                ), secondary_y=False)
                fig_ov.add_trace(go.Scatter(
                    x=prc_norm.index, y=prc_norm.values, name=f"{ticker_input} Price",
                    line=dict(color="#F59E0B", width=2),
                ), secondary_y=True)
                fig_ov.update_layout(
                    height=320, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
                    legend=dict(font=dict(color="#E8EEFF"), bgcolor="rgba(18,21,30,0.90)"),
                    hovermode="x unified",
                    xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#8892AA")),
                    margin=dict(l=0, r=0, t=20, b=0),
                )
                fig_ov.update_yaxes(title_text="Signal (normalized to 100)", secondary_y=False,
                                     gridcolor="rgba(255,255,255,0.05)", tickfont=dict(color="#8892AA"), title_font=dict(color="#7C3AED"))
                fig_ov.update_yaxes(title_text=f"{ticker_input} Price (normalized to 100)", secondary_y=True,
                                     gridcolor="rgba(0,0,0,0)", tickfont=dict(color="#8892AA"), title_font=dict(color="#F59E0B"))
                fig_ov = style_chart_secondary(
                    fig_ov, height=340,
                    y1_title="Signal (indexed)", y2_title=f"{ticker_input} price (indexed)",
                    y1_color="#8187F7", y2_color="#D6A34A",
                )
                st.plotly_chart(fig_ov, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

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
    st.html(section_label("EARNINGS TRACK RECORD", color="#8187F7", dot="#8187F7"))
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
            _acc_color = "#00D566" if (_accuracy or 0) >= 60 else ("#FF4444" if (_accuracy or 0) < 45 else "#6B7FBF")
            _m1, _m2, _m3 = st.columns(3)
            _m1.metric("Earnings Events Checked", len(_rows_with_data))
            _m2.metric("Directional Calls Made", _n_directional)
            if _accuracy is not None:
                _m3.metric("Accuracy", f"{_accuracy:.0f}%",
                           delta="above coin-flip" if _accuracy >= 55 else "below coin-flip")
            else:
                _m3.metric("Accuracy", "—")

            st.caption(
                "Small sample: interpret cautiously. Accuracy here is directional only "
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
                    _pred_color = "#00D566"
                elif _score <= 40:
                    _pred_dir = "bearish"
                    _pred_label = f"▼ Bearish ({_score:.0f})"
                    _pred_color = "#FF4444"
                else:
                    _pred_dir = "neutral"
                    _pred_label = f"● Neutral ({_score:.0f})"
                    _pred_color = "#6B7FBF"

                if _surp is not None:
                    _actual_dir = "bullish" if _surp > 0 else ("bearish" if _surp < 0 else "neutral")
                    _outcome_label = (
                        f"Beat (+{_surp:.1f}%)" if _surp > 0 else
                        f"Miss ({_surp:.1f}%)" if _surp < 0 else
                        "● Met estimate"
                    )
                    _outcome_color = "#00D566" if _surp > 0 else ("#FF4444" if _surp < 0 else "#6B7FBF")
                    if _pred_dir != "neutral":
                        _matched = _pred_dir == _actual_dir
                        _match_label = "Correct" if _matched else "Wrong"
                        _match_color = "#00D566" if _matched else "#FF4444"
                    else:
                        _match_label = "— No call"
                        _match_color = "#6B7FBF"
                else:
                    _outcome_label = "No surprise data"
                    _outcome_color = "#8892AA"
                    _match_label = "—"
                    _match_color = "#8892AA"

                _eps_line = ""
                if _actual is not None and _est is not None:
                    _eps_line = f"EPS: **{_actual:+.2f}** actual vs **{_est:+.2f}** est"
                elif _actual is not None:
                    _eps_line = f"EPS: **{_actual:+.2f}** (no estimate available)"

                st.markdown(f"""
<div style="background:#0B0D12;border:1px solid rgba(255,255,255,0.08);border-left:4px solid {_pred_color};
            border-radius:6px;padding:12px 16px;margin-bottom:8px;font-family:Inter,sans-serif;">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
        <div>
            <div style="font-size:0.70rem;color:#6B7FBF;letter-spacing:0.06em;">
                EARNINGS · {_earn_d}
            </div>
            <div style="font-size:0.85rem;color:#E8EEFF;margin-top:2px;">{_eps_line}</div>
        </div>
        <div style="display:flex;gap:20px;flex-wrap:wrap;">
            <div style="text-align:center;">
                <div style="font-size:0.65rem;color:#8892AA;letter-spacing:0.06em;">SCORE {_delta}d BEFORE</div>
                <div style="font-weight:700;color:{_pred_color};font-size:0.88rem;">{_pred_label}</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:0.65rem;color:#8892AA;letter-spacing:0.06em;">ACTUAL RESULT</div>
                <div style="font-weight:700;color:{_outcome_color};font-size:0.88rem;">{_outcome_label}</div>
            </div>
            <div style="text-align:center;">
                <div style="font-size:0.65rem;color:#8892AA;letter-spacing:0.06em;">CALL</div>
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
        st.switch_page("pages/30_Track_Record_Live.py")

elif section == "Earnings Sentiment":
    st.html(section_label("EARNINGS SENTIMENT", color="#55A7D8", dot="#55A7D8"))
    # ── Earnings Transcript Sentiment (SEC EDGAR 8-K Item 2.02 + LM lexicon) ──
    import plotly.graph_objects as go

    from utils.fetchers import fetch_earnings_transcript_sentiment

    st.subheader(f"Earnings Sentiment — {ticker}")
    st.caption(
        "Sentiment of SEC EDGAR 8-K earnings press releases (Item 2.02) scored "
        "with the Loughran-McDonald (2011) financial lexicon."
    )

    with st.spinner("Fetching SEC EDGAR 8-K filings…"):
        _sent_df = fetch_earnings_transcript_sentiment(ticker, n_quarters=8)

    if _sent_df.empty:
        st.info(
            f"No 8-K Item 2.02 filings found for **{ticker}** on SEC EDGAR. "
            "This is normal for non-US companies, very small-caps, or tickers "
            "that report on a non-standard schedule."
        )
    else:
        # ── Bar chart ─────────────────────────────────────────────────────────
        _colors = [
            "#26a69a" if s >= 0 else "#ef5350"
            for s in _sent_df["sentiment_score"]
        ]
        _labels = [d.strftime("%b %Y") for d in _sent_df["date"]]

        _fig = go.Figure()
        _fig.add_trace(go.Bar(
            x=_labels,
            y=_sent_df["sentiment_score"],
            marker_color=_colors,
            text=[f"{s:+.2f}" for s in _sent_df["sentiment_score"]],
            textposition="outside",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Sentiment: %{y:+.3f}<br>"
                "Positive words: %{customdata[0]}<br>"
                "Negative words: %{customdata[1]}<br>"
                "Total words: %{customdata[2]}<extra></extra>"
            ),
            customdata=list(zip(
                _sent_df["positive"],
                _sent_df["negative"],
                _sent_df["total_words"],
            )),
        ))
        _fig.add_hline(y=0, line_color="rgba(255,255,255,0.25)", line_width=1)

        _fig.update_layout(
            height=380,
            margin=dict(l=20, r=20, t=30, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(
                title="Earnings Release",
                color="#aaaaaa",
                gridcolor="rgba(255,255,255,0.05)",
            ),
            yaxis=dict(
                title="Sentiment Score (−1 to +1)",
                color="#aaaaaa",
                gridcolor="rgba(255,255,255,0.08)",
                zeroline=False,
                range=[
                    min(-0.05, _sent_df["sentiment_score"].min() * 1.25),
                    max(0.05,  _sent_df["sentiment_score"].max() * 1.25),
                ],
            ),
            showlegend=False,
            font=dict(family="Inter, sans-serif", color="#cccccc"),
        )
        _fig = style_distribution_chart(_fig, height=380)
        st.plotly_chart(_fig, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

        # ── Bull / Bear scoring ───────────────────────────────────────────────
        _latest   = _sent_df["sentiment_score"].iloc[-1]
        _trailing = _sent_df["sentiment_score"].tail(4).mean()
        _trend    = _sent_df["sentiment_score"].diff().tail(3).mean()

        if _latest > 0.05 and _trailing > 0:
            _signal_label = "Bullish tone"
            _signal_color = "#26a69a"
        elif _latest < -0.05 and _trailing < 0:
            _signal_label = "Bearish tone"
            _signal_color = "#ef5350"
        else:
            _signal_label = "Neutral / Mixed"
            _signal_color = "#aaaaaa"

        _trend_label = (
            "↑ Improving" if _trend > 0.01
            else "↓ Deteriorating" if _trend < -0.01
            else "→ Stable"
        )

        _c1, _c2, _c3 = st.columns(3)
        with _c1:
            st.metric("Latest quarter", f"{_latest:+.3f}")
        with _c2:
            st.metric("Trailing 4-qtr avg", f"{_trailing:+.3f}")
        with _c3:
            st.metric("Trend (3-qtr Δ avg)", _trend_label)

        st.markdown(
            f"<div style='margin-top:4px;font-size:1.05rem;font-weight:600;"
            f"color:{_signal_color}'>{_signal_label}</div>",
            unsafe_allow_html=True,
        )

        # ── Source links ──────────────────────────────────────────────────────
        st.divider()
        with st.expander("Filing sources (SEC EDGAR 8-K)"):
            for _, _row in _sent_df.iterrows():
                st.markdown(
                    f"[{_row['date'].strftime('%Y-%m-%d')}]({_row['filing_url']}) — "
                    f"score: {_row['sentiment_score']:+.3f} | "
                    f"+{_row['positive']} / −{_row['negative']} words "
                    f"({_row['total_words']:,} total)"
                )

        # ── Methodology note ──────────────────────────────────────────────────
        st.caption(
            "**Methodology:** Loughran & McDonald (2011) financial-domain sentiment "
            "lexicon applied to the full text of Item 2.02 earnings press releases "
            "filed with the SEC on Form 8-K. Score = (positive − negative) / "
            "(positive + negative), range −1 to +1. General-purpose sentiment "
            "models (e.g. VADER) are avoided because they misclassify common "
            "financial terms such as 'liability', 'risk', and 'capital' as negative. "
            "**Source:** SEC EDGAR public HTTPS API — no API key required."
        )

st.html(render_disclaimer())
render_footer(page="ticker")
record_timing(
    "full_page_render",
    ticker=ticker_input,
    duration_seconds=time.perf_counter() - _PAGE_STARTED_AT,
    success=True,
    cache_status=_score_cache_status,
    metadata={"rerun": _page_run_count > 1},
)
