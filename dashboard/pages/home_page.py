"""
Home — Unstructured Alpha landing page
Simplified, retail-first design with clear CTAs and plain-English explainers.
"""

import streamlit as st

st.set_page_config(
    page_title="Unstructured Alpha — Home",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Unstructured Alpha — hedge-fund signals for everyday investors."},
)

from utils.header import render_header, render_sidebar_base
from utils.config import SIGNALS, CATEGORIES

render_header("Home")
render_sidebar_base()

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:28px 0 20px;font-family:Georgia,serif;">
    <div style="font-size:2.0rem;font-weight:800;color:#1C2B4A;line-height:1.2;">
        Hedge Fund Signals.<br>
        <span style="color:#B8860B;">Made for Everyone.</span>
    </div>
    <div style="font-size:1.0rem;color:#6B6560;margin-top:10px;max-width:560px;margin-left:auto;margin-right:auto;">
        Institutional-grade alternative data from free public sources —
        trucking freight, uranium contracts, jobless claims, rig counts, and more —
        scored and mapped to specific stocks so you know what the signals actually mean.
    </div>
</div>
""", unsafe_allow_html=True)

# ── Today's Brief preview strip ──────────────────────────────────────────────
# Show a live signal pulse summary so users land on something immediately
# actionable, not just navigation buttons. Uses the same cached
# compute_all_signal_scores() call Today's Brief uses (2h TTL), so this
# adds zero extra network cost when both pages have been visited recently.
try:
    from utils.fetchers import fetch_signal_series
    from utils.analysis import score_signal
    from utils.config import SIGNALS as _SIGNALS_HP
    import streamlit as st
    from datetime import datetime as _dt, timedelta as _td

    @st.cache_data(ttl=7200, show_spinner=False)
    def _home_signal_pulse(_v: int = 1) -> dict:
        _end = _dt.now().strftime("%Y-%m-%d")
        _start = (_dt.now() - _td(days=730)).strftime("%Y-%m-%d")
        _bull, _bear, _neut = [], [], []
        for _sid, _cfg in _SIGNALS_HP.items():
            try:
                _s = fetch_signal_series(_cfg, _start, _end)
                _scored = score_signal(_s, inverse=_cfg.get("inverse", False))
                _status = _scored.get("status", "neutral")
                _score  = _scored.get("score", 50)
                if _status == "bullish":
                    _bull.append((_cfg["name"], _score))
                elif _status == "bearish":
                    _bear.append((_cfg["name"], _score))
                else:
                    _neut.append((_cfg["name"], _score))
            except Exception:
                pass
        return {
            "bull": sorted(_bull, key=lambda x: -x[1]),
            "bear": sorted(_bear, key=lambda x:  x[1]),
            "neut": _neut,
        }

    with st.spinner("Loading signal pulse…"):
        _pulse = _home_signal_pulse()

    _nb, _nr, _nn = len(_pulse["bull"]), len(_pulse["bear"]), len(_pulse["neut"])
    _total_hp = _nb + _nr + _nn or 1
    _bias_color = "#1B5E20" if _nb > _nr + _nn * 0.5 else ("#7B1010" if _nr > _nb + _nn * 0.5 else "#8B7355")
    _bias_label = "Bullish Leaning" if _nb > _nr + _nn * 0.5 else ("Bearish Leaning" if _nr > _nb + _nn * 0.5 else "Mixed")

    st.markdown(
        f'<div style="background:#F0EBE1;border:1px solid #D4C9B0;border-left:4px solid {_bias_color};'
        f'border-radius:6px;padding:14px 18px;margin-bottom:16px;font-family:Georgia,serif;">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">'
        f'<div>'
        f'<span style="font-size:0.70rem;text-transform:uppercase;letter-spacing:0.08em;color:#8B7355;">Signal Pulse — Now</span><br>'
        f'<span style="font-size:1.05rem;font-weight:700;color:{_bias_color};">{_bias_label}</span>'
        f'<span style="font-size:0.82rem;color:#8B7355;margin-left:10px;">'
        f'▲ {_nb} bullish &nbsp; ▼ {_nr} bearish &nbsp; ● {_nn} neutral</span>'
        f'</div>'
        f'<div style="font-size:0.80rem;color:#1A1612;">'
        + (f'<b style="color:#1B5E20;">Strongest bull:</b> {_pulse["bull"][0][0]} ({_pulse["bull"][0][1]:.0f})' if _pulse["bull"] else '')
        + ('&nbsp;&nbsp;' if _pulse["bull"] and _pulse["bear"] else '')
        + (f'<b style="color:#7B1010;">Strongest bear:</b> {_pulse["bear"][0][0]} ({_pulse["bear"][0][1]:.0f})' if _pulse["bear"] else '')
        + f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    _hp1, _hp2 = st.columns([3, 1])
    with _hp2:
        if st.button("Full Today's Brief →", use_container_width=True, key="cta_today"):
            st.switch_page("pages/2_Today_Digest.py")
except Exception:
    pass  # Never crash the home page over a signal pulse preview failure

# ── 3 Big Start Buttons ───────────────────────────────────────────────────────
btn1, btn2, btn3 = st.columns(3)

with btn1:
    st.markdown("""
    <div style="background:#1C2B4A;border-radius:10px;padding:22px 18px;text-align:center;
                font-family:Georgia,serif;color:#FAF7F0;min-height:120px;">
        <div style="font-size:0.68rem;letter-spacing:0.12em;color:#C9A84C;margin-bottom:8px;">SIGNALS</div>
        <div style="font-weight:700;font-size:1.0rem;margin-bottom:6px;">Check the Signals</div>
        <div style="font-size:0.80rem;color:#C9A84C;line-height:1.4;">
            See which macro signals are flashing bullish or bearish right now.
            Simple or Pro mode.
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Open Signal Dashboard →", use_container_width=True, key="cta_signals"):
        st.switch_page("pages/1_Signal_Dashboard.py")

with btn2:
    st.markdown("""
    <div style="background:#1B5E20;border-radius:10px;padding:22px 18px;text-align:center;
                font-family:Georgia,serif;color:#FAF7F0;min-height:120px;">
        <div style="font-size:0.68rem;letter-spacing:0.12em;color:#A5D6A7;margin-bottom:8px;">TICKER</div>
        <div style="font-weight:700;font-size:1.0rem;margin-bottom:6px;">Analyze Any Ticker</div>
        <div style="font-size:0.80rem;color:#A5D6A7;line-height:1.4;">
            Full signal score + 30/60/90-day probability model
            for any stock on any exchange.
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Open Ticker Deep Dive →", use_container_width=True, key="cta_dive"):
        st.switch_page("pages/3_Ticker_Deep_Dive.py")

with btn3:
    st.markdown("""
    <div style="background:#7B1010;border-radius:10px;padding:22px 18px;text-align:center;
                font-family:Georgia,serif;color:#FAF7F0;min-height:120px;">
        <div style="font-size:0.68rem;letter-spacing:0.12em;color:#EF9A9A;margin-bottom:8px;">MARKET</div>
        <div style="font-weight:700;font-size:1.0rem;margin-bottom:6px;">Market Snapshot</div>
        <div style="font-size:0.80rem;color:#EF9A9A;line-height:1.4;">
            Indices, rates, commodities, and sector performance
            with 1D → ALL time selectors.
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Open Market Overview →", use_container_width=True, key="cta_market"):
        st.switch_page("pages/5_Market_Overview.py")

# ── Secondary row: Watchlist + Model Validation ───────────────────────────────
sec1, sec2 = st.columns(2)
with sec1:
    if st.button("⭐ My Watchlist — track your own tickers", use_container_width=True, key="cta_watchlist"):
        st.switch_page("pages/10_Watchlist.py")
with sec2:
    if st.button("How validated is each score? — Model Validation Dashboard", use_container_width=True, key="cta_validation"):
        st.switch_page("pages/11_Model_Validation.py")

st.markdown("")
st.divider()

# ── Plain-English explainers ──────────────────────────────────────────────────
exp1, exp2 = st.columns(2)

with exp1:
    st.markdown("### What is this?")
    st.markdown("""
    Hedge funds pay **$50,000–$500,000/year** for alternative data — signals from physical
    economic activity that predict stock moves before earnings reports confirm them.

    Examples:
    - Trucking freight volume drops → retail stocks fall 6 weeks later
    - Uranium spot price rises → nuclear fuel company stocks follow
    - Jobless claims spike → consumer discretionary stocks weaken

    This dashboard pulls that same data from **free government sources** and connects each signal
    to the stocks it affects — with the causal logic explained in plain English.

    *Think of it as having a friend at a hedge fund who actually explains their reasoning.*
    """)

with exp2:
    st.markdown("### How to use it")
    st.markdown("""
    **Step 1 — Check the Signal Dashboard**
    See which signals are bullish, bearish, or neutral right now.
    Use **Simple mode** if you're new; **Pro mode** for z-scores and percentiles.

    **Step 2 — Analyze a specific ticker**
    Go to **Ticker Deep Dive**, type any stock symbol. You'll get:
    - A composite signal score (0–100)
    - A 30/60/90-day probability model
    - A plain-English bull & bear case

    **Step 3 — Screen the universe**
    Use the **Stock Screener** to find tickers ranked by signal strength.
    Filter by sector, signal direction, or score range.

    **Step 4 — Go deeper**
    The **Power Supercycle** page tracks the AI → Power → Nuclear thesis specifically.
    The **Deep Correlation Scan** section on Ticker Deep Dive lets you measure the exact
    lead time for any signal/ticker pair.

    **Step 5 — Save tickers & check the receipts**
    Create a free account to build a **Watchlist** with quick-add alert presets (bullish,
    bearish, drastic moves). Curious how validated any of this actually is? The
    **Model Validation Dashboard** shows the real backtest result — or honest "not
    validated yet" status — for every score on the site, not just the ones that look good.
    """)

st.divider()

# ── Signal Library quick preview ──────────────────────────────────────────────
import pandas as pd

total_sigs = len(SIGNALS)
by_cat = {}
for cfg in SIGNALS.values():
    cat = cfg.get("category", "macro")
    by_cat[cat] = by_cat.get(cat, 0) + 1

cat_cols = st.columns(len(by_cat) + 1)
cat_cols[0].metric("Total Signals", total_sigs)
for ci, (cat_key, count) in enumerate(by_cat.items(), 1):
    cat_meta = CATEGORIES.get(cat_key, {})
    cat_cols[ci].metric(cat_meta.get('name', cat_key), count)

with st.expander("Browse all signals →"):
    rows = []
    for sig_id, cfg in SIGNALS.items():
        cat_meta = CATEGORIES.get(cfg.get("category","macro"), {})
        rows.append({
            "Signal":    cfg["name"],
            "Category":  cat_meta.get('name',''),
            "PCS":       cfg["pcs"],
            "Lead":      f"~{cfg['lag_weeks']}w",
            "Direction": "↓ Rising = Bearish" if cfg.get("inverse") else "↑ Rising = Bullish",
            "Tickers":   ", ".join(cfg["relevant_tickers"][:4]),
        })
    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "PCS": st.column_config.NumberColumn("PCS /10", format="%d", help="Predictive Confidence Score. 8+ = publication-grade research."),
            "Lead": st.column_config.TextColumn("Signal Lead", help="How far ahead this signal historically leads the market."),
        },
    )

st.divider()

# ── Quick glossary ────────────────────────────────────────────────────────────
st.markdown("### Common Questions")

gl_col1, gl_col2 = st.columns(2)

with gl_col1:
    with st.expander("What is 'alternative data'?"):
        st.markdown("""
        **Alternative data** is any data source that isn't a stock price or earnings report.
        Examples: freight volumes, uranium contracts, unemployment claims, gasoline prices, housing permits.
        Hedge funds have used this for decades. Most of it comes from free government sources that
        nobody packages for regular investors — until now.
        """)

    with st.expander("What is the Confluence Score?"):
        st.markdown("""
        The **Confluence Score** (0–100) measures how many independent signals are CURRENTLY pointing
        the same direction for a specific stock.
        - **Score > 65** = Multiple bullish signals currently aligning
        - **Score 35–65** = Mixed signals — no clear read right now
        - **Score < 35** = Multiple bearish signals currently aligning

        One bullish signal is more likely to be noise than five independent ones agreeing — but
        agreement is not the same as accuracy. We walk-forward backtested this exact score against
        6 tickers and found no statistically significant relationship with forward returns. It's a
        real-time read of what the data currently says, not a validated forecast. Full numbers on
        the About page.
        """)

    with st.expander("What is the Prediction Model?"):
        st.markdown("""
        The **Prediction Model** on the Ticker Deep Dive page estimates the probability that a
        stock is higher or lower over the next 30, 60, or 90 days — based on:
        1. Current macro signal readings (confluence score)
        2. Recent price momentum (1-month and 3-month)
        3. Historical volatility (for the price range estimate)

        It is **not** a buy/sell signal. It's a probability estimate to help you think
        about risk and timing alongside your own analysis.
        """)

with gl_col2:
    with st.expander("What is the PCS (Predictive Confidence Score)?"):
        st.markdown("""
        The **PCS** (1–10) rates how confident we are that a signal actually predicts stocks.
        Based on: documented historical cases, causal logic, lead time quality, and data reliability.
        - **8–10**: Publication-grade research, well-documented causal mechanism
        - **5–7**: Solid signal with some empirical support
        - **1–4**: Experimental — use with caution

        Signals with PCS ≥ 7 carry more weight in the confluence score calculation.
        """)

    with st.expander("What is 'signal lead time'?"):
        st.markdown("""
        If a signal has a **6-week lead time**, it means: when this signal moves, the related
        stock price historically follows in the same direction about 6 weeks later.

        Example: Lumber prices peak → homebuilder stocks peak 6–8 weeks later.
        This gives you a potential window to act before the price move happens.
        """)

    with st.expander("Is this financial advice?"):
        st.markdown("""
        **No.** This is a research and education tool. All signals are interpretations of
        publicly available data. Past signal accuracy does not predict future performance.
        Always do your own due diligence before making any investment decision.
        Consult a licensed financial advisor for personalized advice.
        """)

st.markdown("""
<div style="text-align:center;padding:20px;font-size:0.75rem;color:#9E9E8E;font-family:Georgia,serif;">
    Unstructured Alpha — Alternative data research tool. Not financial advice.
    All data from public sources (FRED, yfinance, USASpending.gov).
</div>
""", unsafe_allow_html=True)
