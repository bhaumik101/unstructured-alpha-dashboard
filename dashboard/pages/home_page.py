"""
Home — Unstructured Alpha
Public-facing landing page. Psychological design goals:
  1. Live signal data IN the hero — not below it. Real data creates immediate credibility.
  2. Specificity everywhere — "40 signals, 4-16 weeks ahead" not "leading indicators."
  3. Authority by association — FRED / SEC EDGAR / FINRA = same sources Goldman uses.
  4. Loss aversion framing — "what are you missing" more powerful than "here's what you get."
  5. Anchoring — mention Bloomberg's $50K price before showing this is free.
  6. One clear primary CTA above the fold — no decision paralysis.
"""

import streamlit as st

st.set_page_config(
    page_title="Unstructured Alpha — Macro Signal Intelligence",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Unstructured Alpha — institutional-grade macro signals for every investor."},
)

import pandas as pd
from utils.header import render_header, render_sidebar_base
from utils.signals_cache import get_all_signal_scores
from utils.config import SIGNALS, CATEGORIES
from utils.narrative import generate_narrative
from utils.top_tickers import get_top_tickers
from utils.convergence import get_convergence_events, render_convergence_events

render_header("Home")
render_sidebar_base()

# ── Load live signal data (shared cache — no extra API cost) ──────────────────
def _build_home_data() -> dict:
    _all = get_all_signal_scores()
    bull, bear, neut, buckets = [], [], [], {}
    for sid, sv in _all.items():
        if sv.get("error"):
            continue
        status = sv.get("status", "neutral")
        score  = sv.get("score", 50)
        name   = sv.get("name", sid)
        cat    = sv.get("category", "macro")
        if status == "bullish":
            bull.append((name, score))
        elif status == "bearish":
            bear.append((name, score))
        else:
            neut.append((name, score))
        buckets.setdefault(cat, []).append(score)
    return {
        "bull":    sorted(bull, key=lambda x: -x[1]),
        "bear":    sorted(bear, key=lambda x:  x[1]),
        "neut":    neut,
        "sectors": {k: sum(v)/len(v) for k, v in buckets.items() if v},
    }

try:
    with st.spinner(""):
        _raw_scores = get_all_signal_scores()
        _hd = _build_home_data()
        _narrative  = generate_narrative(_raw_scores)
        _top_tkrs   = get_top_tickers(len(_raw_scores))
    _nb, _nr, _nn = len(_hd["bull"]), len(_hd["bear"]), len(_hd["neut"])
    _total = max(1, _nb + _nr + _nn)
    _bull_pct = _nb / _total
    _bear_pct = _nr / _total
    _bias_label  = _narrative["regime"]
    _bias_color  = _narrative["regime_color"]
    _bias_bg     = "#EDF7ED" if "BULL" in _bias_label else ("#FDF0F0" if "BEAR" in _bias_label else "#FAF7F0")
    _top_bull    = _hd["bull"][0][0] if _hd["bull"] else None
    _top_bear    = _hd["bear"][0][0] if _hd["bear"] else None
    _data_loaded = True
except Exception:
    _hd = {"bull": [], "bear": [], "neut": [], "sectors": {}}
    _raw_scores = {}
    _narrative  = {"regime": "LOADING…", "regime_color": "#8B7355", "summary": "",
                   "top_bull": [], "top_bear": [], "watch_note": "", "sector_bias": {},
                   "bull_count": 0, "bear_count": 0, "neut_count": 0, "total": 0}
    _top_tkrs   = {"bullish": [], "bearish": [], "by_sector": {}, "all": []}
    _nb = _nr = _nn = _total = 0
    _bull_pct = _bear_pct = 0.0
    _bias_label = "LOADING…"
    _bias_color = "#8B7355"
    _bias_bg    = "#FAF7F0"
    _top_bull = _top_bear = None
    _data_loaded = False

# ── HERO ──────────────────────────────────────────────────────────────────────
# Psychology: specificity + live data immediately = credibility. The live
# pulse IS the hero — not a badge below it.
st.markdown(f"""
<div style="text-align:center;padding:36px 0 0;font-family:Georgia,serif;">
    <div style="font-size:0.72rem;letter-spacing:0.18em;color:#B8860B;margin-bottom:14px;
                font-weight:600;">
        INSTITUTIONAL-GRADE MACRO INTELLIGENCE · FREE
    </div>
    <div style="font-size:2.6rem;font-weight:800;color:#1C2B4A;line-height:1.15;
                max-width:720px;margin:0 auto;">
        Before the market moves,<br>
        <span style="color:#B8860B;">the signals already did.</span>
    </div>
    <div style="font-size:1.0rem;color:#5C5650;margin:16px auto 0;max-width:580px;
                line-height:1.65;">
        38 macro signals — Fed policy, energy flows, credit spreads, insider buying —
        scored in real time and mapped to the stocks you actually hold.
        The same data Goldman watches. Now accessible to everyone.
    </div>
</div>
""", unsafe_allow_html=True)

# ── LIVE SIGNAL PULSE — embedded in hero, not below it ───────────────────────
# Psychology: showing REAL data immediately answers "does this actually work?"
# The live pulse is the most powerful trust signal on this page.
_bar_bull = f"{(_nb / _total * 100):.0f}%" if _total > 0 else "0%"
_bar_bear = f"{(_nr / _total * 100):.0f}%" if _total > 0 else "0%"

_top_bull_html = (
    f'<div style="font-size:0.78rem;color:#D4F0DA;margin-top:2px;">'
    f'▲ Strongest: <b style="color:#A8E6B0;">{_top_bull}</b></div>'
    if _top_bull else ""
)
_top_bear_html = (
    f'<div style="font-size:0.78rem;color:#F5C2C2;margin-top:2px;">'
    f'▼ Weakest: <b style="color:#FFAAAA;">{_top_bear}</b></div>'
    if _top_bear else ""
)

st.markdown(f"""
<div style="background:#1C2B4A;border-radius:12px;padding:22px 28px 20px;
            margin:24px auto 0;max-width:820px;font-family:Georgia,serif;">

    <div style="display:flex;justify-content:space-between;align-items:flex-start;
                flex-wrap:wrap;gap:16px;">

        <div style="flex:1;min-width:200px;">
            <div style="font-size:0.62rem;letter-spacing:0.16em;color:#C9A84C;margin-bottom:6px;
                        font-weight:600;">LIVE MACRO READ — RIGHT NOW</div>
            <div style="font-size:2.0rem;font-weight:800;color:{_bias_color};
                        letter-spacing:-0.01em;">{_bias_label}</div>
            <div style="font-size:0.80rem;color:#A0A8B8;margin-top:6px;">
                across {_total} tracked signals
            </div>
        </div>

        <div style="display:flex;gap:24px;flex-wrap:wrap;">
            <div style="text-align:center;">
                <div style="font-size:2.2rem;font-weight:800;color:#4CAF50;">{_nb}</div>
                <div style="font-size:0.68rem;color:#4CAF50;letter-spacing:0.10em;">BULLISH</div>
                {_top_bull_html}
            </div>
            <div style="text-align:center;">
                <div style="font-size:2.2rem;font-weight:800;color:#EF5350;">{_nr}</div>
                <div style="font-size:0.68rem;color:#EF5350;letter-spacing:0.10em;">BEARISH</div>
                {_top_bear_html}
            </div>
            <div style="text-align:center;">
                <div style="font-size:2.2rem;font-weight:800;color:#B8B0A0;">{_nn}</div>
                <div style="font-size:0.68rem;color:#B8B0A0;letter-spacing:0.10em;">NEUTRAL</div>
            </div>
        </div>
    </div>

    <div style="margin-top:16px;background:rgba(255,255,255,0.08);border-radius:6px;
                height:6px;overflow:hidden;display:flex;">
        <div style="width:{_bar_bull};background:#4CAF50;"></div>
        <div style="width:{_bar_bear};background:#EF5350;"></div>
        <div style="flex:1;background:#5A6070;"></div>
    </div>
    <div style="display:flex;justify-content:space-between;margin-top:4px;">
        <div style="font-size:0.66rem;color:#8A9AB8;">▲ Bullish {_bar_bull}</div>
        <div style="font-size:0.66rem;color:#8A9AB8;">Updated every 2 hours</div>
        <div style="font-size:0.66rem;color:#8A9AB8;">Bearish {_bar_bear} ▼</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Primary CTA — one action, no decision paralysis
st.markdown("<div style='text-align:center;margin:22px 0 8px;'>", unsafe_allow_html=True)
_hcol1, _hcol2, _hcol3 = st.columns([2, 1.4, 2])
with _hcol2:
    if st.button("→ See Today's Full Signal Brief", type="primary", use_container_width=True, key="hero_cta"):
        st.switch_page("pages/2_Today_Digest.py")
st.markdown("<div style='text-align:center;font-size:0.74rem;color:#9E9E8E;margin-top:6px;font-family:Georgia,serif;'>No account needed to browse signals</div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── CREDIBILITY STRIP ─────────────────────────────────────────────────────────
# Psychology: authority by association. Same sources = same data as Goldman.
st.markdown("""
<div style="border-top:1px solid #E8E0D4;border-bottom:1px solid #E8E0D4;
            padding:14px 0;margin:4px 0 28px;text-align:center;">
    <div style="font-size:0.66rem;letter-spacing:0.14em;color:#A09080;margin-bottom:10px;
                font-weight:600;">DATA SOURCED FROM THE SAME INSTITUTIONS WALL STREET USES</div>
    <div style="display:flex;justify-content:center;gap:28px;flex-wrap:wrap;align-items:center;">
        <span style="font-size:0.82rem;color:#6B6560;font-family:Georgia,serif;">
            <b style="color:#1C2B4A;">FRED</b> · Federal Reserve</span>
        <span style="color:#D4C9B0;">|</span>
        <span style="font-size:0.82rem;color:#6B6560;font-family:Georgia,serif;">
            <b style="color:#1C2B4A;">SEC EDGAR</b> · Insider Filings</span>
        <span style="color:#D4C9B0;">|</span>
        <span style="font-size:0.82rem;color:#6B6560;font-family:Georgia,serif;">
            <b style="color:#1C2B4A;">FINRA</b> · Short Interest</span>
        <span style="color:#D4C9B0;">|</span>
        <span style="font-size:0.82rem;color:#6B6560;font-family:Georgia,serif;">
            <b style="color:#1C2B4A;">EIA</b> · Energy Data</span>
        <span style="color:#D4C9B0;">|</span>
        <span style="font-size:0.82rem;color:#6B6560;font-family:Georgia,serif;">
            <b style="color:#1C2B4A;">13F Filings</b> · Institutional Positions</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ── MACHINE INTELLIGENCE SECTION ─────────────────────────────────────────────
# Narrative + top tickers: makes the site feel like it INTERPRETS data
if _data_loaded:
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    _nar = _narrative
    _nar_col1, _nar_col2 = st.columns([3, 2])

    with _nar_col1:
        _rc  = _nar["regime_color"]
        _rgb_bg = "#EDF7ED" if ("BULL" in _nar["regime"] or "ON" in _nar["regime"]) else \
                  ("#FDF0F0" if ("BEAR" in _nar["regime"] or "OFF" in _nar["regime"]) else "#FAF7F0")
        _sect_items = "".join(
            f'<span style="display:inline-block;margin:2px 4px;padding:2px 8px;border-radius:12px;'
            f'font-size:0.67rem;background:{"#EDF7ED" if v == "BULLISH" else ("#FDF0F0" if v == "BEARISH" else "#F4F0E8")};'
            f'color:{"#1B5E20" if v == "BULLISH" else ("#7B1010" if v == "BEARISH" else "#6B6055")};'
            f'font-weight:600;">{k.split("/")[0].strip()}: {v}</span>'
            for k, v in _nar["sector_bias"].items()
        )
        _watch_html = (
            f'<div style="margin-top:10px;padding:8px 12px;background:#FFF8E7;'
            f'border-left:3px solid #B8860B;border-radius:4px;font-size:0.74rem;color:#5C4A1A;">'
            f'👁 {_nar["watch_note"]}</div>'
            if _nar.get("watch_note") else ""
        )
        st.markdown(
            f'<div style="background:{_rgb_bg};border-radius:10px;padding:20px 22px;'
            f'border-left:5px solid {_rc};font-family:Georgia,serif;">'
            f'<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.12em;color:{_rc};'
            f'text-transform:uppercase;margin-bottom:6px;">MACHINE READS THE MARKET</div>'
            f'<div style="font-size:1.3rem;font-weight:800;color:#1C2B4A;margin-bottom:10px;">'
            f'{_nar["headline"]}</div>'
            f'<div style="font-size:0.82rem;color:#4A4440;line-height:1.65;margin-bottom:12px;">'
            f'{_nar["summary"]}</div>'
            f'<div style="margin-bottom:8px;">{_sect_items}</div>'
            f'{_watch_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

    with _nar_col2:
        _bull_tkrs = _top_tkrs.get("bullish", [])[:5]
        _bear_tkrs = _top_tkrs.get("bearish", [])[:3]
        if _bull_tkrs or _bear_tkrs:
            _bull_rows = "".join(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:4px 0;border-bottom:1px solid #E8E0CE;">'
                f'<span style="font-weight:700;font-size:0.82rem;color:#1A1612;">{r["ticker"]}</span>'
                f'<span style="font-size:0.74rem;color:#4A4440;flex:1;padding-left:8px;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px;">'
                f'{r["name"][:22]}</span>'
                f'<span style="font-size:0.78rem;font-weight:700;color:#1B5E20;">'
                f'▲ {r["score"]:.0f}</span>'
                f'</div>'
                for r in _bull_tkrs
            )
            _bear_rows = "".join(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:4px 0;border-bottom:1px solid #E8E0CE;">'
                f'<span style="font-weight:700;font-size:0.82rem;color:#1A1612;">{r["ticker"]}</span>'
                f'<span style="font-size:0.74rem;color:#4A4440;flex:1;padding-left:8px;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px;">'
                f'{r["name"][:22]}</span>'
                f'<span style="font-size:0.78rem;font-weight:700;color:#7B1010;">'
                f'▼ {r["score"]:.0f}</span>'
                f'</div>'
                for r in _bear_tkrs
            )
            st.markdown(
                f'<div style="background:#FAFAF7;border-radius:10px;padding:18px 20px;'
                f'border:1px solid #D4C9B0;font-family:Georgia,serif;">'
                f'<div style="font-size:0.68rem;font-weight:700;letter-spacing:0.12em;color:#B8860B;'
                f'text-transform:uppercase;margin-bottom:10px;">WHAT THE MACHINE FAVORS NOW</div>'
                f'<div style="font-size:0.7rem;color:#9E9E8E;margin-bottom:6px;">MACRO TAILWIND ▲</div>'
                f'{_bull_rows}'
                f'<div style="font-size:0.7rem;color:#9E9E8E;margin:10px 0 6px;">MACRO HEADWIND ▼</div>'
                f'{_bear_rows}'
                f'<div style="font-size:0.65rem;color:#9E9E8E;margin-top:10px;">'
                f'38 macro signals · no price charts · pure fundamentals</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ── SIGNAL CONVERGENCE EVENTS ────────────────────────────────────────────────
# The real edge: not one signal going bullish, but 3+ independent signals
# all telling the same story about the same ticker simultaneously.
_conv_events = get_convergence_events(days_back=7, min_signals=3)
if _conv_events:
    st.markdown("""
    <div style="font-size:1.1rem;font-weight:800;color:#1C2B4A;margin-bottom:6px;
                font-family:Georgia,serif;">
        ⚡ Signal Convergence Events
        <span style="font-size:0.72rem;font-weight:400;color:#8B7355;margin-left:10px;">
        3+ independent signals aligned on the same ticker in the last 7 days</span>
    </div>
    """, unsafe_allow_html=True)
    _conv_col1, _conv_col2 = st.columns(2)
    _bull_ev = [e for e in _conv_events if e["direction"] == "bullish"][:4]
    _bear_ev = [e for e in _conv_events if e["direction"] == "bearish"][:2]
    with _conv_col1:
        render_convergence_events(_bull_ev + _bear_ev[:1], max_bull=4, max_bear=1)
    with _conv_col2:
        if len(_bear_ev) > 1:
            render_convergence_events([], max_bull=0)
            render_convergence_events(_bear_ev[1:], max_bull=0, max_bear=2)
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# ── LATEST RESEARCH NOTE TEASER ──────────────────────────────────────────────
# Show a teaser card if a note exists. Zero extra cost — just a DB read.
try:
    from utils.narrative_engine import get_latest_note as _get_ln
    _latest_note = _get_ln()
    if _latest_note:
        _note_regime   = _latest_note.get("regime", "")
        _note_headline = _latest_note.get("headline", "")
        _note_date     = _latest_note.get("note_date", "")
        _note_body     = _latest_note.get("body", "")
        _note_bull_n   = _latest_note.get("bull_count") or 0
        _note_bear_n   = _latest_note.get("bear_count") or 0

        # Extract first body paragraph (skip headline line) for teaser
        _note_paras = [p.strip() for p in _note_body.split("\n\n") if p.strip()]
        _note_hl_clean = _note_headline.strip("*#").strip()
        if _note_paras and _note_paras[0].strip("*#").strip() == _note_hl_clean:
            _note_paras = _note_paras[1:]
        _note_teaser = _note_paras[0][:240] + "…" if _note_paras else ""

        # Regime chip colors
        _regime_colors = {
            "RISK-ON":            ("#1B5E20", "#E8F5E9"),
            "CAUTIOUSLY BULLISH": ("#33691E", "#F1F8E9"),
            "MIXED / TRANSITION": ("#E65100", "#FFF8E1"),
            "CAUTIOUSLY BEARISH": ("#BF360C", "#FBE9E7"),
            "RISK-OFF":           ("#7B1010", "#FFEBEE"),
        }
        _rf, _rb = _regime_colors.get(_note_regime, ("#6B5E52", "#F5F5F5"))

        # Format date
        try:
            from datetime import datetime as _dtn
            _nd = _dtn.strptime(_note_date, "%Y-%m-%d")
            _note_date_str = _nd.strftime("%B %d, %Y")
        except Exception:
            _note_date_str = _note_date

        st.markdown(
            f'<div style="background:#FAF6F0;border:1px solid #E0D5C5;border-top:3px solid #8B6914;'
            f'border-radius:8px;padding:18px 22px;margin-bottom:24px;font-family:\'Georgia\',serif;">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">'
            f'<span style="font-size:0.62rem;letter-spacing:0.14em;font-weight:700;color:#B8860B;">📰 LATEST RESEARCH NOTE</span>'
            f'<span style="font-size:0.68rem;font-weight:700;letter-spacing:0.08em;padding:2px 8px;'
            f'border-radius:3px;background:{_rb};color:{_rf};border:1px solid {_rf}33;">{_note_regime}</span>'
            f'<span style="font-size:0.70rem;color:#8B7355;margin-left:auto;">{_note_date_str}</span>'
            f'</div>'
            f'<div style="font-size:1.05rem;font-weight:700;color:#1A1612;line-height:1.3;margin-bottom:8px;">'
            f'{_note_hl_clean}</div>'
            f'<div style="font-size:0.82rem;color:#4A4440;line-height:1.65;margin-bottom:10px;">'
            f'{_note_teaser}</div>'
            f'<div style="font-size:0.70rem;color:#8B7355;">'
            f'{_note_bull_n} bullish · {_note_bear_n} bearish signals</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Read Full Note →", key="home_note_cta", use_container_width=False):
            st.switch_page("pages/18_Weekly_Brief.py")
except Exception:
    pass  # Never block the home page

# ── 3 CORE FEATURE SPOTLIGHTS ─────────────────────────────────────────────────
# Psychology: 3 = digestible. 6 = paralysis. Show the 3 things that differentiate.
st.markdown("""
<div style="font-size:1.55rem;font-weight:800;color:#1C2B4A;text-align:center;
            margin-bottom:6px;font-family:Georgia,serif;">
    Three tools that change how you invest
</div>
<div style="font-size:0.88rem;color:#6B6560;text-align:center;margin-bottom:24px;
            font-family:Georgia,serif;">
    Not a screener. Not a news aggregator. Something genuinely different.
</div>
""", unsafe_allow_html=True)

_sp1, _sp2, _sp3 = st.columns(3)

_SPOT = """
<div style="border:1px solid #D4C9B0;border-top:4px solid {accent};border-radius:10px;
            padding:22px 20px 18px;font-family:Georgia,serif;background:{bg};
            min-height:240px;">
    <div style="font-size:0.62rem;letter-spacing:0.12em;color:{label_c};margin-bottom:8px;
                font-weight:600;">{tag}</div>
    <div style="font-size:1.08rem;font-weight:800;color:#1A1612;margin-bottom:10px;
                line-height:1.25;">{title}</div>
    <div style="font-size:0.82rem;color:#5C5650;line-height:1.6;margin-bottom:14px;">{body}</div>
    <div style="font-size:0.74rem;color:{accent};font-weight:600;">{proof}</div>
</div>
"""

with _sp1:
    st.markdown(_SPOT.format(
        accent="#1B5E20", bg="#F4FAF4", label_c="#1B5E20",
        tag="DAILY INTELLIGENCE",
        title="Today's Brief — your 2-minute macro read",
        body=(
            "Every morning: which signals flipped overnight, what the macro bias is, "
            "and what it means for your holdings. Plain English. No jargon. "
            "Opt in for a 7 AM email digest."
        ),
        proof=f"→ Currently: {_bias_label} across {_total} signals",
    ), unsafe_allow_html=True)
    if st.button("Read Today's Brief →", use_container_width=True, key="cta_brief"):
        st.switch_page("pages/2_Today_Digest.py")

with _sp2:
    st.markdown(_SPOT.format(
        accent="#1C2B4A", bg="#F4F6FA", label_c="#1C2B4A",
        tag="STOCK-SPECIFIC ANALYSIS",
        title="Ticker Deep Dive — type any stock, get a macro report",
        body=(
            "Confluence Score (0–100), 30/60/90-day probability model, "
            "signal-by-signal breakdown, earnings markers, insider activity, news. "
            "Tells you <i>why</i> the macro environment is or isn't set up for this stock."
        ),
        proof="→ Tested on 80+ tickers with statistical validation",
    ), unsafe_allow_html=True)
    if st.button("Try Ticker Deep Dive →", use_container_width=True, key="cta_dive"):
        st.switch_page("pages/3_Ticker_Deep_Dive.py")

with _sp3:
    st.markdown(_SPOT.format(
        accent="#B8860B", bg="#FDFAF2", label_c="#B8860B",
        tag="SMART ALERTS",
        title="Watchlist — know the moment a signal flips",
        body=(
            "Track any ticker with custom alert thresholds. Get notified "
            "when the Confluence Score crosses your level, a signal changes direction, "
            "or a 52-week high/low is hit. Morning email to opted-in users."
        ),
        proof="→ Free · No Bloomberg terminal needed",
    ), unsafe_allow_html=True)
    if st.button("Build Your Watchlist →", use_container_width=True, key="cta_watchlist"):
        st.switch_page("pages/10_Watchlist.py")

st.markdown("<br>", unsafe_allow_html=True)

# ── THE CONTRAST / ANCHOR ─────────────────────────────────────────────────────
# Psychology: Anchoring + loss aversion. "$50K/year" makes "free" feel extraordinary.
st.markdown("""
<div style="background:#1C2B4A;border-radius:12px;padding:28px 32px;margin:8px 0 32px;
            font-family:Georgia,serif;text-align:center;">
    <div style="font-size:0.68rem;letter-spacing:0.14em;color:#C9A84C;margin-bottom:10px;
                font-weight:600;">THE EDGE ISN'T THE DATA — IT'S KNOWING WHICH SIGNALS TO WATCH</div>
    <div style="font-size:1.35rem;font-weight:800;color:#FAF7F0;max-width:640px;margin:0 auto;
                line-height:1.35;">
        Bloomberg Terminal charges <span style="color:#C9A84C;">$27,000/year</span>
        for access to this kind of macro data.<br>
        <span style="color:#A8D8B0;">We built the same analysis from free public sources.</span>
    </div>
    <div style="font-size:0.84rem;color:#A0A8B8;margin-top:12px;max-width:560px;margin-left:auto;
                margin-right:auto;line-height:1.6;">
        FRED, SEC EDGAR, FINRA, and EIA are the same primary data sources
        institutional desks rely on. The difference is we packaged it for
        investors who don't have a six-figure data budget.
    </div>
</div>
""", unsafe_allow_html=True)

# ── SECTOR ROTATION TEASER ────────────────────────────────────────────────────
# Live sector scores create another reason to explore
st.markdown("""
<div style="font-size:1.15rem;font-weight:800;color:#1C2B4A;font-family:Georgia,serif;
            margin-bottom:4px;">Sector Rotation Signal Map — live preview</div>
<div style="font-size:0.82rem;color:#6B6560;margin-bottom:16px;font-family:Georgia,serif;">
    Which sectors do the signals currently favor? Updated every 2 hours.
</div>
""", unsafe_allow_html=True)

_SECTOR_META = {
    "ai_infrastructure": ("Technology & AI",   "#1C2B4A"),
    "energy":            ("Energy",             "#5D4037"),
    "nuclear":           ("Nuclear/Utilities",  "#7B1010"),
    "financials":        ("Financials",         "#B8860B"),
    "healthcare":        ("Healthcare",         "#1B5E20"),
    "consumer":          ("Consumer",           "#B34700"),
    "industrials":       ("Industrials",        "#4A1B6B"),
    "macro":             ("Macro Backdrop",     "#0D4F5C"),
}

try:
    _sec = _hd.get("sectors", {})
    if _sec:
        _sorted = sorted(_sec.items(), key=lambda x: -x[1])
        _sc_cols = st.columns(4)
        for _i, (_cat, _avg) in enumerate(_sorted[:8]):
            _name, _col = _SECTOR_META.get(_cat, (_cat.title(), "#8B7355"))
            _arrow  = "▲" if _avg >= 60 else ("▼" if _avg <= 40 else "●")
            _sc     = "#1B5E20" if _avg >= 60 else ("#7B1010" if _avg <= 40 else "#8B7355")
            _bg     = "#EDF7ED" if _avg >= 60 else ("#FDF0F0" if _avg <= 40 else "#FAF7F0")
            with _sc_cols[_i % 4]:
                st.markdown(f"""
<div style="background:{_bg};border:1px solid #D4C9B0;border-left:3px solid {_sc};
            border-radius:7px;padding:11px 13px;margin-bottom:8px;font-family:Georgia,serif;">
    <div style="font-size:0.78rem;font-weight:700;color:#1A1612;margin-bottom:4px;">{_name}</div>
    <div style="font-size:1.4rem;font-weight:800;color:{_sc};">{_arrow} {_avg:.0f}</div>
</div>
""", unsafe_allow_html=True)
    else:
        st.caption("Sector scores loading — refresh in a moment.")

    _smc, _ = st.columns([1, 3])
    with _smc:
        if st.button("Full Sector Map →", use_container_width=True, key="cta_sector"):
            st.switch_page("pages/12_Sector_Map.py")
except Exception:
    st.caption("Sector preview unavailable. Open the Sector Map page directly.")

st.divider()

# ── WHY THIS ISN'T A SCREENER ─────────────────────────────────────────────────
# Psychology: reframe the category. "Not X, it's Y" positions differently.
_da, _db = st.columns(2)

with _da:
    st.markdown("""
<div style="font-family:Georgia,serif;">
<div style="font-size:1.1rem;font-weight:800;color:#7B1010;margin-bottom:10px;">
    What traditional screeners miss
</div>
<div style="font-size:0.84rem;color:#5C5650;line-height:1.65;">
    Stock screeners filter on price, P/E, and volume. They tell you what
    <i>has happened</i> to a stock — not what's coming. That's rear-view-mirror investing.<br><br>
    By the time a move shows up in price and volume, institutional desks have
    already positioned. The professionals were watching leading economic signals
    4 to 16 weeks earlier.
</div>
<br>
<div style="font-size:1.1rem;font-weight:800;color:#1B5E20;margin-bottom:10px;">
    What leading signals actually predict
</div>
<div style="font-size:0.84rem;color:#5C5650;line-height:1.65;">
    • Trucking freight falls → retail earnings weaken ~6 weeks later<br>
    • Uranium spot rises → nuclear energy stocks follow<br>
    • Credit spreads widen → broad market pullback precedes it 4–8 weeks<br>
    • Hyperscaler capex accelerates → AI infrastructure stocks outperform<br><br>
    This is what hedge funds call <b style="color:#1C2B4A;">alternative data</b>.
    They pay $50K–$500K/year for it. We built it from public sources.
</div>
</div>
""", unsafe_allow_html=True)

with _db:
    st.markdown("""
<div style="font-family:Georgia,serif;">
<div style="font-size:1.1rem;font-weight:800;color:#1C2B4A;margin-bottom:10px;">
    What you get that you can't get anywhere else — for free
</div>
""", unsafe_allow_html=True)

    _diffs = [
        ("Signal Lead Time",
         "Each signal comes with a measured historical lead time — how many weeks "
         "ahead it typically precedes price movement. Not guesswork."),
        ("Pre-Earnings Track Record",
         "See what the Confluence Score said 7–45 days before each past earnings event "
         "vs. the actual EPS beat or miss."),
        ("Confluence Score",
         "How many independent signals agree? One bullish signal is noise. "
         "Seven agreeing signals is a thesis."),
        ("Honest Validation",
         "We publish our backtest results even when they're not impressive. "
         "See the Model Validation page — it's one of a kind."),
        ("Plain-English Causal Logic",
         "Not just 'this signal correlates.' We explain the economic mechanism: "
         "why this indicator moves this sector, specifically."),
    ]
    for _title, _body in _diffs:
        st.markdown(f"""
<div style="border-left:3px solid #B8860B;padding:8px 14px;margin-bottom:10px;
            background:#FDFAF4;border-radius:0 6px 6px 0;">
    <div style="font-size:0.84rem;font-weight:700;color:#1C2B4A;margin-bottom:3px;">{_title}</div>
    <div style="font-size:0.78rem;color:#5C5650;line-height:1.5;">{_body}</div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── HOW TO USE IN 4 STEPS ────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:1.15rem;font-weight:800;color:#1C2B4A;font-family:Georgia,serif;
            margin-bottom:18px;">Start generating insight in under 5 minutes</div>
""", unsafe_allow_html=True)

_steps = [
    ("1", "#1B5E20", "Read Today's Brief",
     "2-minute macro morning read. Which signals are bullish. Which are bearish. What it means.",
     "pages/2_Today_Digest.py", "Open Today's Brief →", "cta_s1"),
    ("2", "#B8860B", "Check the Sector Map",
     "See which sectors the data currently favors. Find where the macro tailwinds are right now.",
     "pages/12_Sector_Map.py", "Open Sector Map →", "cta_s2"),
    ("3", "#1C2B4A", "Deep Dive a Ticker",
     "Type any stock. Get a Confluence Score, signal breakdown, earnings history, and bull/bear case.",
     "pages/3_Ticker_Deep_Dive.py", "Open Deep Dive →", "cta_s3"),
    ("4", "#7B1010", "Set Up Your Watchlist",
     "Save your stocks. Get alerted when signals flip. Optional morning email at 7 AM ET.",
     "pages/10_Watchlist.py", "Open Watchlist →", "cta_s4"),
]

_st_cols = st.columns(4)
for _col, (_n, _ac, _title, _body, _page, _btn, _key) in zip(_st_cols, _steps):
    with _col:
        st.markdown(f"""
<div style="background:#FAF7F0;border:1px solid #D4C9B0;border-top:4px solid {_ac};
            border-radius:8px;padding:16px;font-family:Georgia,serif;min-height:170px;
            margin-bottom:8px;">
    <div style="font-size:1.5rem;font-weight:800;color:{_ac};margin-bottom:6px;">{_n}</div>
    <div style="font-size:0.88rem;font-weight:700;color:#1A1612;margin-bottom:6px;">{_title}</div>
    <div style="font-size:0.77rem;color:#6B6560;line-height:1.5;">{_body}</div>
</div>
""", unsafe_allow_html=True)
        if st.button(_btn, use_container_width=True, key=_key):
            st.switch_page(_page)

st.divider()

# ── ADDITIONAL TOOLS ──────────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:0.88rem;font-weight:700;color:#1C2B4A;font-family:Georgia,serif;
            margin-bottom:10px;">More tools</div>
""", unsafe_allow_html=True)

_t1, _t2, _t3, _t4 = st.columns(4)
with _t1:
    if st.button("📡 Signal Dashboard", use_container_width=True, key="cta_signals"):
        st.switch_page("pages/1_Signal_Dashboard.py")
with _t2:
    if st.button("📊 Market Overview", use_container_width=True, key="cta_market"):
        st.switch_page("pages/5_Market_Overview.py")
with _t3:
    if st.button("🔍 Stock Screener", use_container_width=True, key="cta_screener"):
        st.switch_page("pages/6_Stock_Screener.py")
with _t4:
    if st.button("✅ Model Validation", use_container_width=True, key="cta_validation"):
        st.switch_page("pages/11_Model_Validation.py")

st.divider()

# ── FAQ — Tight. Only the questions that actually convert. ────────────────────
st.markdown("""
<div style="font-size:1.05rem;font-weight:800;color:#1C2B4A;font-family:Georgia,serif;
            margin-bottom:10px;">Common questions</div>
""", unsafe_allow_html=True)

_q1, _q2 = st.columns(2)

with _q1:
    with st.expander("What is alternative data?"):
        st.markdown(
            "Data that isn't a stock price or earnings report. Freight volumes, uranium contracts, "
            "jobless claims, credit spreads, insider buys. Hedge funds have used this for decades. "
            "Most of it comes from free government sources that nobody packaged for retail — until now."
        )
    with st.expander("What is the Confluence Score?"):
        st.markdown(
            "A 0–100 score measuring how many independent signals agree for a given stock right now. "
            "**>65** = multiple bullish signals aligning. **<35** = multiple bearish. **35–65** = mixed. "
            "One bullish signal is noise. Seven agreeing is a thesis. "
            "We walk-forward tested this — results on the Model Validation page."
        )
    with st.expander("Does this predict stock prices?"):
        st.markdown(
            "No — and we're transparent about that. The signals have shown statistical correlations "
            "in backtests, but no tool predicts with certainty. The value is pattern recognition "
            "across 40 economic indicators that historically lead price by weeks, not perfect prediction. "
            "See Model Validation for honest results."
        )

with _q2:
    with st.expander("What does it cost?"):
        st.markdown(
            "Free to browse all signals, Today's Brief, Sector Map, Signal Dashboard, and Deep Dive. "
            "A free account (email only, no card) unlocks the Watchlist, price alerts, and morning "
            "email digest. No paid tier — this isn't a subscription service."
        )
    with st.expander("Is this financial advice?"):
        st.markdown(
            "No. This is a research and education tool. All signals reflect interpretations of public "
            "economic data. Past signal correlation doesn't guarantee future accuracy. "
            "Always do your own due diligence."
        )
    with st.expander("How is this different from Yahoo Finance?"):
        st.markdown(
            "Yahoo Finance shows what has happened to a stock (price, volume, P/E). "
            "Unstructured Alpha shows what macro forces are building beneath the surface — "
            "credit spreads, freight flows, insider positioning — that historically lead "
            "price by 4–16 weeks. Different tool, different question."
        )

# ── FOOTER ───────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:24px 0 8px;font-family:Georgia,serif;">
    <div style="font-size:0.72rem;color:#A09080;letter-spacing:0.06em;">
        UNSTRUCTURED ALPHA · ALTERNATIVE DATA INTELLIGENCE<br>
        <span style="color:#C4BBAA;">
        Not financial advice. All data from public sources:
        FRED, EIA, FINRA, SEC EDGAR, USASpending.gov, Yahoo Finance.
        </span>
    </div>
</div>
""", unsafe_allow_html=True)
