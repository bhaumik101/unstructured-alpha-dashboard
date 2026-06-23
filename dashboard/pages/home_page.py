"""
Home — Unstructured Alpha
Public-facing landing page. Should work for someone who has never heard
of alternative data and just Googled "hedge fund signals for retail investors."

Design goals:
  1. Immediate value signal in the first screen (live Signal Pulse)
  2. Feature grid that names every major capability clearly
  3. Plain-English explanation of what this is vs Bloomberg / stock screeners
  4. Easy CTAs to every key page
  5. No jargon without a definition
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
<div style="text-align:center;padding:32px 0 8px;font-family:Georgia,serif;">
    <div style="font-size:0.78rem;letter-spacing:0.14em;color:#B8860B;margin-bottom:10px;">
        ALTERNATIVE DATA INTELLIGENCE
    </div>
    <div style="font-size:2.3rem;font-weight:800;color:#1C2B4A;line-height:1.2;">
        Hedge Fund Signals.<br>
        <span style="color:#B8860B;">Finally Explained.</span>
    </div>
    <div style="font-size:1.05rem;color:#6B6560;margin-top:12px;max-width:600px;
                margin-left:auto;margin-right:auto;line-height:1.6;">
        Institutional-grade alternative data signals — trucking freight, uranium contracts,
        insider trades, credit spreads — scored and mapped to the stocks they move.
        No Bloomberg terminal required.
    </div>
</div>
""", unsafe_allow_html=True)

# ── Live Signal Pulse ─────────────────────────────────────────────────────────
# Most visitors land here and want something actionable immediately.
# The pulse shows the current macro read in under 3 seconds.
try:
    from utils.fetchers import fetch_signal_series
    from utils.analysis import score_signal
    from utils.config import SIGNALS as _SIGNALS_HP
    from datetime import datetime as _dt, timedelta as _td

    @st.cache_data(ttl=7200, show_spinner=False)
    def _home_signal_pulse(_v: int = 1) -> dict:
        _end   = _dt.now().strftime("%Y-%m-%d")
        _start = (_dt.now() - _td(days=730)).strftime("%Y-%m-%d")
        _bull, _bear, _neut = [], [], []
        for _sid, _cfg in _SIGNALS_HP.items():
            try:
                _s      = fetch_signal_series(_cfg, _start, _end)
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

    with st.spinner("Loading live signal pulse…"):
        _pulse = _home_signal_pulse()

    _nb, _nr, _nn = len(_pulse["bull"]), len(_pulse["bear"]), len(_pulse["neut"])
    _total_hp = _nb + _nr + _nn or 1
    _bias_color = "#1B5E20" if _nb > _nr + _nn * 0.5 else (
        "#7B1010" if _nr > _nb + _nn * 0.5 else "#8B7355")
    _bias_label = ("Bullish Leaning" if _nb > _nr + _nn * 0.5 else
                   "Bearish Leaning" if _nr > _nb + _nn * 0.5 else "Mixed Signals")

    _bull_str = (f'<b style="color:#4CAF50;">Top bull:</b> {_pulse["bull"][0][0]} '
                 f'<span style="color:#9E9E8E;">({_pulse["bull"][0][1]:.0f})</span>'
                 if _pulse["bull"] else "")
    _bear_str = (f'<b style="color:#EF5350;">Top bear:</b> {_pulse["bear"][0][0]} '
                 f'<span style="color:#9E9E8E;">({_pulse["bear"][0][1]:.0f})</span>'
                 if _pulse["bear"] else "")
    _sep_str = "&nbsp;&nbsp;·&nbsp;&nbsp;" if _pulse["bull"] and _pulse["bear"] else ""

    st.markdown(f"""
<div style="background:#1C2B4A;border-radius:10px;padding:18px 22px;margin:20px 0 8px;
            font-family:Georgia,serif;color:#FAF7F0;">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;">
        <div>
            <div style="font-size:0.65rem;letter-spacing:0.12em;color:#C9A84C;margin-bottom:4px;">
                LIVE SIGNAL PULSE — RIGHT NOW
            </div>
            <div style="font-size:1.3rem;font-weight:800;color:{_bias_color};">{_bias_label}</div>
            <div style="font-size:0.78rem;color:#D4C9B0;margin-top:3px;">
                ▲ {_nb} bullish &nbsp;·&nbsp; ▼ {_nr} bearish &nbsp;·&nbsp; ● {_nn} neutral
                &nbsp;across {_total_hp} signals
            </div>
        </div>
        <div style="font-size:0.82rem;color:#FAF7F0;text-align:right;">
            {_bull_str}{_sep_str}{_bear_str}
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

    _p1, _p2 = st.columns([4, 1])
    with _p2:
        if st.button("Full Today's Brief →", use_container_width=True, key="cta_today"):
            st.switch_page("pages/2_Today_Digest.py")
except Exception:
    pass

st.markdown("")

# ── Feature grid — 6 major features ──────────────────────────────────────────
st.markdown("""
<div style="font-size:0.70rem;text-transform:uppercase;letter-spacing:0.12em;
            color:#8B7355;text-align:center;margin-bottom:4px;">
    WHAT YOU CAN DO WITH THIS
</div>
<div style="font-size:1.5rem;font-weight:800;color:#1C2B4A;text-align:center;margin-bottom:20px;
            font-family:Georgia,serif;">
    Six Tools. One Dashboard.
</div>
""", unsafe_allow_html=True)

_FEATURE_CARD = """
<div style="background:{bg};border:1px solid #D4C9B0;border-top:4px solid {accent};
            border-radius:8px;padding:18px;font-family:Georgia,serif;min-height:190px;
            margin-bottom:4px;">
    <div style="font-size:1.5rem;margin-bottom:6px;">{icon}</div>
    <div style="font-size:0.65rem;letter-spacing:0.10em;color:{label_color};margin-bottom:4px;">
        {label}
    </div>
    <div style="font-size:0.98rem;font-weight:700;color:#1A1612;margin-bottom:6px;">{title}</div>
    <div style="font-size:0.80rem;color:#6B6560;line-height:1.5;">{body}</div>
    {badge}
</div>
"""

_NEW_BADGE = """<div style="display:inline-block;background:#B8860B;color:#FAF7F0;
    font-size:0.60rem;letter-spacing:0.08em;padding:2px 7px;border-radius:3px;
    margin-top:6px;">NEW</div>"""

_f1, _f2, _f3 = st.columns(3)

with _f1:
    st.markdown(_FEATURE_CARD.format(
        bg="#F5F8F5", accent="#1B5E20", icon="📡",
        label="SIGNALS", label_color="#1B5E20",
        title="Real-Time Signal Dashboard",
        body="Every macro signal scored right now — freight, rates, energy, housing, "
             "insider activity. Simple mode for new investors; Pro mode with z-scores and percentiles.",
        badge="",
    ), unsafe_allow_html=True)
    if st.button("Open Signal Dashboard →", use_container_width=True, key="cta_signals"):
        st.switch_page("pages/1_Signal_Dashboard.py")

with _f2:
    st.markdown(_FEATURE_CARD.format(
        bg="#F5F7FB", accent="#1C2B4A", icon="🔬",
        label="RESEARCH", label_color="#1C2B4A",
        title="Ticker Deep Dive",
        body="Type any ticker. Get a Confluence Score (0–100), 30/60/90-day probability model, "
             "earnings markers on the price chart, recent news, and a plain-English bull & bear case.",
        badge="",
    ), unsafe_allow_html=True)
    if st.button("Open Ticker Deep Dive →", use_container_width=True, key="cta_dive"):
        st.switch_page("pages/3_Ticker_Deep_Dive.py")

with _f3:
    st.markdown(_FEATURE_CARD.format(
        bg="#FFFBF2", accent="#B8860B", icon="🗺️",
        label="SECTOR ROTATION", label_color="#B8860B",
        title="Sector Rotation Signal Map",
        body="Which sectors do the signals favor right now? See all 8 equity sectors scored "
             "and ranked — Technology, Energy, Nuclear, Financials, Healthcare, and more — in one view.",
        badge=_NEW_BADGE,
    ), unsafe_allow_html=True)
    if st.button("Open Sector Map →", use_container_width=True, key="cta_sector"):
        st.switch_page("pages/12_Sector_Map.py")

_f4, _f5, _f6 = st.columns(3)

with _f4:
    st.markdown(_FEATURE_CARD.format(
        bg="#FBF8F5", accent="#8B7355", icon="📰",
        label="DAILY DIGEST", label_color="#8B7355",
        title="Today's Brief",
        body="A scannable morning briefing: top bullish signals, top bearish signals, "
             "and the macro story in plain English. Designed to read in under 2 minutes.",
        badge="",
    ), unsafe_allow_html=True)
    if st.button("Open Today's Brief →", use_container_width=True, key="cta_brief"):
        st.switch_page("pages/2_Today_Digest.py")

with _f5:
    st.markdown(_FEATURE_CARD.format(
        bg="#FBF5F5", accent="#7B1010", icon="📋",
        label="TRACK RECORD", label_color="#7B1010",
        title="Pre-Earnings Track Record",
        body="Did the signals predict the last earnings beat or miss? "
             "For any ticker, see what the Confluence Score said 7–45 days before each "
             "past earnings event vs the actual EPS result.",
        badge=_NEW_BADGE,
    ), unsafe_allow_html=True)
    if st.button("Open Track Record →", use_container_width=True, key="cta_track"):
        st.switch_page("pages/13_Track_Record.py")

with _f6:
    st.markdown(_FEATURE_CARD.format(
        bg="#F5F5FB", accent="#4A1B6B", icon="⭐",
        label="WATCHLIST", label_color="#4A1B6B",
        title="My Watchlist",
        body="Save your own tickers and get notified when signals flip bullish or bearish. "
             "Quick-add alert presets: bullish signal, bearish signal, score drastic move.",
        badge="",
    ), unsafe_allow_html=True)
    if st.button("Open My Watchlist →", use_container_width=True, key="cta_watchlist"):
        st.switch_page("pages/10_Watchlist.py")

st.divider()

# ── Sector Rotation Teaser ────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:1.15rem;font-weight:700;color:#1C2B4A;font-family:Georgia,serif;
            margin-bottom:4px;">
    🗺️ Sector Rotation Signal Map — Live Preview
</div>
<div style="font-size:0.82rem;color:#6B6560;margin-bottom:14px;">
    Which sectors does the data currently favor? Updated every 2 hours.
</div>
""", unsafe_allow_html=True)

try:
    from datetime import timedelta
    from datetime import datetime as _sm_dt
    from utils.fetchers import fetch_signal_series as _sm_fetch
    from utils.analysis import score_signal as _sm_score
    from utils.config import SIGNALS as _sm_sigs

    _SECTOR_META_HP = {
        "ai_infrastructure": ("💻 Technology & AI",  "#1C2B4A"),
        "energy":            ("⛽ Energy",            "#5D4037"),
        "nuclear":           ("⚡ Nuclear/Utilities",  "#7B1010"),
        "financials":        ("🏦 Financials",         "#B8860B"),
        "healthcare":        ("🏥 Healthcare",          "#1B5E20"),
        "consumer":          ("🛒 Consumer",           "#B34700"),
        "industrials":       ("🏭 Industrials",        "#4A1B6B"),
        "macro":             ("📊 Macro Backdrop",     "#0D4F5C"),
    }

    @st.cache_data(ttl=7200, show_spinner=False)
    def _hp_sector_scores(_v: int = 1) -> dict:
        _end   = _sm_dt.now().strftime("%Y-%m-%d")
        _start = (_sm_dt.now() - timedelta(days=730)).strftime("%Y-%m-%d")
        _buckets: dict = {}
        for _sid, _cfg in _sm_sigs.items():
            _cat = _cfg.get("category", "macro")
            if _cat not in _buckets:
                _buckets[_cat] = []
            try:
                _s = _sm_fetch(_cfg, _start, _end)
                _sc = _sm_score(_s, inverse=_cfg.get("inverse", False))
                _buckets[_cat].append(_sc.get("score", 50))
            except Exception:
                pass
        return {
            _cat: sum(_scores) / len(_scores)
            for _cat, _scores in _buckets.items()
            if _scores
        }

    with st.spinner("Loading sector scores…"):
        _hp_sectors = _hp_sector_scores()

    if _hp_sectors:
        _sorted_sectors = sorted(_hp_sectors.items(), key=lambda x: -x[1])
        _sec_cols = st.columns(min(len(_sorted_sectors), 4))
        for _si, (_cat, _avg) in enumerate(_sorted_sectors[:8]):
            _name, _color = _SECTOR_META_HP.get(_cat, (f"📊 {_cat}", "#8B7355"))
            _status = "▲" if _avg >= 60 else ("▼" if _avg <= 40 else "●")
            _sc_color = "#1B5E20" if _avg >= 60 else ("#7B1010" if _avg <= 40 else "#8B7355")
            _bg = "#EDF7ED" if _avg >= 60 else ("#FDF0F0" if _avg <= 40 else "#FAF7F0")
            with _sec_cols[_si % 4]:
                st.markdown(f"""
<div style="background:{_bg};border:1px solid #D4C9B0;border-left:3px solid {_sc_color};
            border-radius:6px;padding:10px 12px;margin-bottom:8px;font-family:Georgia,serif;">
    <div style="font-size:0.80rem;font-weight:600;color:#1A1612;">{_name}</div>
    <div style="font-size:1.3rem;font-weight:800;color:{_sc_color};">{_status} {_avg:.0f}</div>
</div>
""", unsafe_allow_html=True)

    _sm_col, _ = st.columns([1, 3])
    with _sm_col:
        if st.button("Full Sector Map →", use_container_width=True, key="cta_sector_full"):
            st.switch_page("pages/12_Sector_Map.py")
except Exception:
    st.caption("Sector preview unavailable — open the Sector Map page directly.")

st.divider()

# ── What makes this different ─────────────────────────────────────────────────
st.markdown("""
<div style="font-size:1.15rem;font-weight:700;color:#1C2B4A;font-family:Georgia,serif;
            margin-bottom:16px;">
    Why This Isn't Just Another Stock Screener
</div>
""", unsafe_allow_html=True)

_diff_a, _diff_b = st.columns(2)

with _diff_a:
    st.markdown("""
    **Traditional screeners** filter on price, P/E ratio, and volume. They tell you what *has*
    happened to a stock — not what's coming. That's rear-view-mirror investing.

    **Unstructured Alpha** uses *leading* indicators: physical economic data that moves 4–16 weeks
    *before* earnings and price follow. Examples:
    - Trucking freight falls → retail earnings weaken 6 weeks later
    - Uranium spot price rises → nuclear energy stocks follow
    - Credit spreads widen → broad market pullback precedes it by 4–8 weeks
    - Hyperscaler capex accelerates → AI infrastructure stocks outperform

    This is what hedge funds call **alternative data** — and they pay $50K–$500K/year for it.
    This tool builds it from the same free public sources.
    """)

with _diff_b:
    st.markdown("""
    **What you get that you can't get anywhere else (for free):**

    - **Sector Rotation Map** — which sectors are the signals favoring right now?
    - **Signal Lead Time** — how many weeks ahead does each indicator historically lead?
    - **Pre-Earnings Track Record** — did the score correctly predict the last 4 earnings?
    - **Confluence Score** — how many independent signals agree vs one noisy one?
    - **Honest validation** — we publish backtest results even when they're not impressive
    - **Plain-English causal logic** — why does this signal affect this stock, specifically?

    Everything is powered by free FRED, EIA, FINRA, EDGAR, and yfinance data.
    The edge isn't the data — it's knowing which signals to look for and why.
    """)

st.divider()

# ── How to use it ─────────────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:1.15rem;font-weight:700;color:#1C2B4A;font-family:Georgia,serif;
            margin-bottom:14px;">
    How to Use This in 5 Minutes
</div>
""", unsafe_allow_html=True)

_step_cols = st.columns(4)

_STEP_CARD = """
<div style="background:#FAF7F0;border:1px solid #D4C9B0;border-radius:8px;
            padding:14px;font-family:Georgia,serif;text-align:center;min-height:160px;">
    <div style="font-size:1.8rem;">{icon}</div>
    <div style="font-size:0.65rem;letter-spacing:0.10em;color:#8B7355;margin-top:4px;">STEP {n}</div>
    <div style="font-size:0.88rem;font-weight:700;color:#1A1612;margin-top:4px;">{title}</div>
    <div style="font-size:0.75rem;color:#6B6560;margin-top:6px;line-height:1.4;">{body}</div>
</div>
"""

_step_cols[0].markdown(_STEP_CARD.format(
    icon="📡", n=1, title="Check Today's Brief",
    body="See which macro signals are bullish or bearish right now. Takes 2 minutes.",
), unsafe_allow_html=True)
_step_cols[1].markdown(_STEP_CARD.format(
    icon="🗺️", n=2, title="Read the Sector Map",
    body="See which sectors the data currently favors. Find where the macro tailwinds are.",
), unsafe_allow_html=True)
_step_cols[2].markdown(_STEP_CARD.format(
    icon="🔬", n=3, title="Deep Dive a Ticker",
    body="Type any stock symbol. Get its Confluence Score, probability model, and bull/bear case.",
), unsafe_allow_html=True)
_step_cols[3].markdown(_STEP_CARD.format(
    icon="⭐", n=4, title="Build Your Watchlist",
    body="Save tickers and set alerts for when signals flip — so you don't have to check daily.",
), unsafe_allow_html=True)

st.divider()

# ── Secondary tools row ───────────────────────────────────────────────────────
_sec1, _sec2, _sec3 = st.columns(3)
with _sec1:
    if st.button("📊 Market Overview — indices, rates, commodities", use_container_width=True, key="cta_market"):
        st.switch_page("pages/5_Market_Overview.py")
with _sec2:
    if st.button("🔍 Stock Screener — rank tickers by signal strength", use_container_width=True, key="cta_screener"):
        st.switch_page("pages/6_Stock_Screener.py")
with _sec3:
    if st.button("✅ Model Validation — honest backtest results", use_container_width=True, key="cta_validation"):
        st.switch_page("pages/11_Model_Validation.py")

st.divider()

# ── Signal library quick stats ────────────────────────────────────────────────
import pandas as pd

_total_sigs = len(SIGNALS)
_by_cat: dict = {}
for _cfg in SIGNALS.values():
    _cat = _cfg.get("category", "macro")
    _by_cat[_cat] = _by_cat.get(_cat, 0) + 1

_stat_cols = st.columns(len(_by_cat) + 1)
_stat_cols[0].metric("Total Signals", _total_sigs)
for _ci, (_cat_key, _count) in enumerate(_by_cat.items(), 1):
    _cat_meta = CATEGORIES.get(_cat_key, {})
    _stat_cols[_ci].metric(_cat_meta.get("name", _cat_key), _count)

with st.expander("Browse all signals →"):
    _rows = []
    for _sig_id, _cfg in SIGNALS.items():
        _cat_meta = CATEGORIES.get(_cfg.get("category", "macro"), {})
        _rows.append({
            "Signal":    _cfg["name"],
            "Category":  _cat_meta.get("name", ""),
            "PCS":       _cfg["pcs"],
            "Lead":      f"~{_cfg['lag_weeks']}w",
            "Direction": "↓ Rising = Bearish" if _cfg.get("inverse") else "↑ Rising = Bullish",
            "Tickers":   ", ".join(_cfg["relevant_tickers"][:4]),
        })
    st.dataframe(
        pd.DataFrame(_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "PCS": st.column_config.NumberColumn(
                "PCS /10", format="%d",
                help="Predictive Confidence Score. 8+ = publication-grade research."),
            "Lead": st.column_config.TextColumn(
                "Signal Lead", help="How far ahead this signal historically leads."),
        },
    )

st.divider()

# ── FAQ ───────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:1.1rem;font-weight:700;color:#1C2B4A;font-family:Georgia,serif;
            margin-bottom:12px;">
    Common Questions
</div>
""", unsafe_allow_html=True)

_gl1, _gl2 = st.columns(2)

with _gl1:
    with st.expander("What is alternative data?"):
        st.markdown("""
        **Alternative data** is any data source that isn't a stock price or earnings report —
        things like freight volumes, uranium contracts, jobless claims, gasoline prices, and
        housing permits. Hedge funds have used this for decades. Most of it comes from free
        government sources that nobody packages for retail investors — until now.
        """)

    with st.expander("What is the Confluence Score?"):
        st.markdown("""
        The **Confluence Score** (0–100) measures how many independent signals are pointing the
        same direction for a specific stock right now.
        - **Score > 65** = Multiple bullish signals aligning
        - **Score 35–65** = Mixed signals — no clear read
        - **Score < 35** = Multiple bearish signals aligning

        One bullish signal is more likely noise than five independent ones agreeing. We
        walk-forward backtested this score and found no statistically significant relationship
        with forward returns on the tickers we tested. It's a real-time read of current data,
        not a validated forecast. Full results on the Model Validation page.
        """)

    with st.expander("What is the Sector Rotation Map?"):
        st.markdown("""
        The **Sector Map** groups all signals by the equity sector they relate to and computes
        an average Confluence Score for each sector. A high score for "Energy" means the
        energy-related alternative data signals are currently bullish on net. Use it to find
        which sectors have macro tailwinds before researching individual tickers in those sectors.
        """)

with _gl2:
    with st.expander("What is the Pre-Earnings Track Record?"):
        st.markdown("""
        The **Track Record** page shows what the Confluence Score said 7–45 days before each
        past earnings date for any ticker, and whether it correctly anticipated the EPS beat or miss.
        Score >= 60 = predicted beat · Score <= 40 = predicted miss · 40-60 = no call.

        This data accumulates organically: it grows each time a ticker is opened on Ticker Deep
        Dive. New tickers will have sparse history. Interpret small samples with caution.
        """)

    with st.expander("Is this financial advice?"):
        st.markdown("""
        **No.** This is a research and education tool. All signals are interpretations of
        publicly available data. Past signal accuracy does not predict future performance.
        Always do your own due diligence. Consult a licensed financial advisor for personalized advice.
        """)

    with st.expander("What is the PCS (Predictive Confidence Score)?"):
        st.markdown("""
        The **PCS** (1–10) rates how confident we are that a signal actually predicts stocks.
        Based on documented historical cases, causal logic, lead time quality, and data reliability.
        - **8–10**: Publication-grade research with strong causal mechanism
        - **5–7**: Solid signal with empirical support
        - **1–4**: Experimental — use with caution
        """)

st.markdown("""
<div style="text-align:center;padding:20px;font-size:0.75rem;color:#9E9E8E;font-family:Georgia,serif;">
    Unstructured Alpha — Alternative data research tool. Not financial advice.
    All data from public sources (FRED, EIA, yfinance, EDGAR, FINRA, USASpending.gov).
</div>
""", unsafe_allow_html=True)
