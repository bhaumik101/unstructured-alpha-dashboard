"""
Page 12 — Sector Rotation Signal Map
A live heat map of all equity sectors ranked by their current alternative-data
signal confluence. Each sector's score is the average of its underlying signals'
individual scores — e.g., Energy's score is the mean of crude inventories,
natural gas storage, and rig count. Not a stock price tracker; a macro
signal posture tracker.

Why sectors, not tickers? Because the first question a macro investor asks is
"which sectors does the data favor right now?" — before ever looking at
individual stocks. This page answers that in one view.

Sectors are defined by the signal category taxonomy already in utils/config.py:
ai_infrastructure → Technology & AI
energy            → Energy
nuclear           → Nuclear / Utilities
financials        → Financials
healthcare        → Healthcare
consumer          → Consumer
industrials       → Industrials
macro             → Macro Backdrop (rates, credit, housing, freight, etc.)
"""

from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.config import SIGNALS, CATEGORIES
from utils.header import render_header, render_sidebar_base

st.set_page_config(page_title="Sector Map — UA", layout="wide")
render_header("Sector Map")
render_sidebar_base()

st.markdown("# Sector Rotation Signal Map")
st.caption(
    "Live read of which equity sectors the alternative-data signals currently favor. "
    "Score = average confluence of all signals in that sector category. "
    "Green ≥ 60 · Red ≤ 40 · Tan = mixed."
)

# ── Sector display metadata ───────────────────────────────────────────────────
# Maps config.py category keys → display name, icon, color, representative ETF
SECTOR_META = {
    "ai_infrastructure": {
        "name":  "Technology & AI",
        "icon":  "💻",
        "color": "#1C2B4A",
        "etf":   "XLK / SMH",
        "desc":  "Hyperscaler capex, semiconductor demand, AI infrastructure build-out",
    },
    "energy": {
        "name":  "Energy",
        "icon":  "⛽",
        "color": "#5D4037",
        "etf":   "XLE / OIH",
        "desc":  "Crude inventories, natural gas storage, rig count, EIA data",
    },
    "nuclear": {
        "name":  "Nuclear / Utilities",
        "icon":  "⚡",
        "color": "#7B1010",
        "etf":   "XLU / URA",
        "desc":  "Uranium spot price, nuclear contract awards, power demand",
    },
    "financials": {
        "name":  "Financials",
        "icon":  "🏦",
        "color": "#B8860B",
        "etf":   "XLF / KRE",
        "desc":  "Credit spreads, yield curve shape, interest rate environment",
    },
    "healthcare": {
        "name":  "Healthcare",
        "icon":  "🏥",
        "color": "#1B5E20",
        "etf":   "XLV / IBB",
        "desc":  "Healthcare utilization, biotech funding, drug pricing signals",
    },
    "consumer": {
        "name":  "Consumer",
        "icon":  "🛒",
        "color": "#B34700",
        "etf":   "XLY / XLP",
        "desc":  "Consumer confidence, retail sales, gasoline price pressure",
    },
    "industrials": {
        "name":  "Industrials",
        "icon":  "🏭",
        "color": "#4A1B6B",
        "etf":   "XLI / IYT",
        "desc":  "ISM manufacturing PMI, freight volume, railcar loadings",
    },
    "macro": {
        "name":  "Macro Backdrop",
        "icon":  "📊",
        "color": "#0D4F5C",
        "etf":   "SPY / TLT",
        "desc":  "Rates, credit, housing, freight, jobless claims — the broader economic backdrop",
    },
}

STATUS_COLOR  = {"bullish": "#1B5E20", "bearish": "#7B1010", "neutral": "#8B7355"}
STATUS_LABEL  = {"bullish": "▲ BULLISH", "bearish": "▼ BEARISH", "neutral": "● MIXED"}
STATUS_BG     = {"bullish": "#EDF7ED", "bearish": "#FDF0F0", "neutral": "#FAF7F0"}


# ── Signal scoring — grouped by category ─────────────────────────────────────
@st.cache_data(ttl=7200, show_spinner=False)
def _compute_sector_scores(_v: int = 1) -> dict:
    """
    Score every signal in SIGNALS and group results by category.
    Returns {category_key: {score, status, bull, bear, neut, top_signals, n}}

    Cache key _v exists so callers can force-bust by passing a different int
    (e.g. after a manual Refresh click) without the function signature changing.
    """
    from utils.fetchers import fetch_signal_series
    from utils.analysis import score_signal

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    buckets: dict = {}
    for sig_id, cfg in SIGNALS.items():
        cat = cfg.get("category", "macro")
        if cat not in buckets:
            buckets[cat] = {"scores": [], "bull": 0, "bear": 0, "neut": 0, "signals": []}
        try:
            s = fetch_signal_series(cfg, start, end)
            scored  = score_signal(s, inverse=cfg.get("inverse", False))
            status  = scored.get("status", "neutral")
            score   = scored.get("score", 50)
            buckets[cat]["scores"].append(score)
            buckets[cat]["signals"].append((cfg["name"], round(score, 1), status))
            if status == "bullish":
                buckets[cat]["bull"] += 1
            elif status == "bearish":
                buckets[cat]["bear"] += 1
            else:
                buckets[cat]["neut"] += 1
        except Exception:
            pass

    result = {}
    for cat, data in buckets.items():
        if not data["scores"]:
            continue
        avg = sum(data["scores"]) / len(data["scores"])
        if avg >= 60:
            overall = "bullish"
        elif avg <= 40:
            overall = "bearish"
        else:
            overall = "neutral"
        # Top signals sorted by distance from 50 (most decisive first)
        top = sorted(data["signals"], key=lambda x: -abs(x[1] - 50))[:3]
        result[cat] = {
            "score":       round(avg, 1),
            "status":      overall,
            "bull":        data["bull"],
            "bear":        data["bear"],
            "neut":        data["neut"],
            "top_signals": top,
            "n":           len(data["scores"]),
        }
    return result


# ── Refresh control ───────────────────────────────────────────────────────────
_ts = datetime.now().strftime("%I:%M %p")
_hdr_col, _ref_col = st.columns([5, 1])
with _hdr_col:
    st.caption(f"Signal scores cached up to 2 hours · last computed ~{_ts}")
with _ref_col:
    if st.button("↺ Refresh", key="sm_refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Compute scores ────────────────────────────────────────────────────────────
with st.spinner("Scoring signals across all sectors…"):
    _sector_scores = _compute_sector_scores()

if not _sector_scores:
    st.error("Could not compute sector scores — check signal data availability.")
    st.stop()

# ── Overall market posture banner ─────────────────────────────────────────────
_all_scores  = [v["score"] for v in _sector_scores.values()]
_all_avg     = sum(_all_scores) / len(_all_scores) if _all_scores else 50
_bull_sectors = sum(1 for v in _sector_scores.values() if v["status"] == "bullish")
_bear_sectors = sum(1 for v in _sector_scores.values() if v["status"] == "bearish")
_neut_sectors = sum(1 for v in _sector_scores.values() if v["status"] == "neutral")

_market_status = "bullish" if _bull_sectors > _bear_sectors + _neut_sectors * 0.5 else (
    "bearish" if _bear_sectors > _bull_sectors + _neut_sectors * 0.5 else "neutral"
)
_market_color = STATUS_COLOR[_market_status]

st.markdown(f"""
<div style="background:#1C2B4A;border-radius:10px;padding:18px 24px;margin-bottom:20px;
            font-family:Georgia,serif;color:#FAF7F0;">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
        <div>
            <div style="font-size:0.68rem;letter-spacing:0.10em;color:#C9A84C;margin-bottom:4px;">
                BROAD MARKET SIGNAL POSTURE
            </div>
            <div style="font-size:1.5rem;font-weight:800;color:{_market_color};">
                {STATUS_LABEL[_market_status]}
            </div>
            <div style="font-size:0.82rem;color:#C9A84C;margin-top:2px;">
                Avg sector score: {_all_avg:.0f} / 100
            </div>
        </div>
        <div style="display:flex;gap:24px;text-align:center;">
            <div>
                <div style="font-size:1.6rem;font-weight:800;color:#4CAF50;">{_bull_sectors}</div>
                <div style="font-size:0.70rem;color:#A5D6A7;letter-spacing:0.06em;">BULLISH</div>
            </div>
            <div>
                <div style="font-size:1.6rem;font-weight:800;color:#EF9A9A;">{_bear_sectors}</div>
                <div style="font-size:0.70rem;color:#EF9A9A;letter-spacing:0.06em;">BEARISH</div>
            </div>
            <div>
                <div style="font-size:1.6rem;font-weight:800;color:#D4C9B0;">{_neut_sectors}</div>
                <div style="font-size:0.70rem;color:#D4C9B0;letter-spacing:0.06em;">MIXED</div>
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Sector grid ───────────────────────────────────────────────────────────────
# Sort sectors: bullish first (by score desc), then neutral, then bearish
def _sort_key(cat_key: str) -> tuple:
    d = _sector_scores.get(cat_key, {})
    order = {"bullish": 0, "neutral": 1, "bearish": 2}
    return (order.get(d.get("status", "neutral"), 1), -d.get("score", 50))

_ordered_cats = sorted(
    [c for c in SECTOR_META if c in _sector_scores],
    key=_sort_key,
)

# 3-column grid
_grid_cols = st.columns(3)
for _i, _cat in enumerate(_ordered_cats):
    _d  = _sector_scores[_cat]
    _m  = SECTOR_META.get(_cat, {"name": _cat, "icon": "●", "color": "#8B7355",
                                   "etf": "", "desc": ""})
    _sc = _d["score"]
    _st = _d["status"]
    _sc_color  = STATUS_COLOR[_st]
    _card_bg   = STATUS_BG[_st]
    _bar_w_b   = _d["bull"] / _d["n"] * 100 if _d["n"] else 0
    _bar_w_n   = _d["neut"] / _d["n"] * 100 if _d["n"] else 0
    _bar_w_r   = _d["bear"] / _d["n"] * 100 if _d["n"] else 0

    # Top signals for this sector
    _top_html = ""
    for _sig_name, _sig_score, _sig_st in _d["top_signals"]:
        _sig_c = STATUS_COLOR.get(_sig_st, "#8B7355")
        _sig_sym = "▲" if _sig_st == "bullish" else ("▼" if _sig_st == "bearish" else "●")
        _top_html += (
            f'<div style="font-size:0.72rem;color:{_sig_c};margin-top:2px;">'
            f'{_sig_sym} {_sig_name} <span style="color:#9E9E8E;">({_sig_score:.0f})</span></div>'
        )

    _col = _grid_cols[_i % 3]
    with _col:
        st.markdown(f"""
        <div style="background:{_card_bg};border:1px solid #D4C9B0;border-top:4px solid {_sc_color};
                    border-radius:8px;padding:16px 18px;margin-bottom:16px;font-family:Georgia,serif;
                    min-height:220px;">
            <div style="display:flex;align-items:center;justify-content:space-between;">
                <div style="font-size:1.1rem;font-weight:700;color:#1A1612;">
                    {_m['icon']} {_m['name']}
                </div>
                <div style="font-size:1.4rem;font-weight:800;color:{_sc_color};">{_sc:.0f}</div>
            </div>
            <div style="font-size:0.72rem;color:#8B7355;margin-top:2px;margin-bottom:8px;">
                {_m['etf']} &nbsp;·&nbsp; {_d['n']} signal{'s' if _d['n'] != 1 else ''}
            </div>

            <div style="font-weight:700;color:{_sc_color};font-size:0.82rem;margin-bottom:6px;">
                {STATUS_LABEL[_st]}
            </div>

            <!-- Signal breakdown bar -->
            <div style="display:flex;border-radius:3px;overflow:hidden;height:6px;margin-bottom:8px;">
                <div style="width:{_bar_w_b:.0f}%;background:#1B5E20;"></div>
                <div style="width:{_bar_w_n:.0f}%;background:#8B7355;"></div>
                <div style="width:{_bar_w_r:.0f}%;background:#7B1010;"></div>
            </div>
            <div style="font-size:0.68rem;color:#9E9E8E;margin-bottom:8px;">
                ▲{_d['bull']} bull &nbsp; ●{_d['neut']} neutral &nbsp; ▼{_d['bear']} bear
            </div>

            <div style="border-top:1px solid #E8E0CE;padding-top:8px;">
                <div style="font-size:0.68rem;color:#9E9E8E;letter-spacing:0.06em;margin-bottom:4px;">
                    TOP MOVERS
                </div>
                {_top_html}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Button to jump to Signal Dashboard filtered view
        if st.button(f"Explore {_m['name']} signals →", key=f"sm_goto_{_cat}",
                     use_container_width=True):
            st.switch_page("pages/1_Signal_Dashboard.py")

st.divider()

# ── Rotation bar chart ────────────────────────────────────────────────────────
st.markdown("### Signal Score by Sector")
st.caption("Ranked highest to lowest. Dashed lines at 65 (bullish threshold) and 35 (bearish threshold).")

_chart_labels = []
_chart_scores = []
_chart_colors = []
for _cat in sorted(_ordered_cats, key=lambda c: -_sector_scores[c]["score"]):
    _m  = SECTOR_META.get(_cat, {"name": _cat, "icon": "●"})
    _d  = _sector_scores[_cat]
    _chart_labels.append(f"{_m['icon']} {_m['name']}")
    _chart_scores.append(_d["score"])
    _chart_colors.append(STATUS_COLOR[_d["status"]])

_fig_bar = go.Figure(go.Bar(
    x=_chart_labels,
    y=_chart_scores,
    marker_color=_chart_colors,
    text=[f"{s:.0f}" for s in _chart_scores],
    textposition="outside",
    hovertemplate="%{x}: %{y:.1f}<extra></extra>",
))
_fig_bar.add_hline(y=65, line_dash="dot", line_color="#1B5E20", opacity=0.5,
                    annotation_text="Bullish (65)", annotation_font_size=10)
_fig_bar.add_hline(y=35, line_dash="dot", line_color="#7B1010", opacity=0.5,
                    annotation_text="Bearish (35)", annotation_font_size=10)
_fig_bar.update_layout(
    height=320, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
    font=dict(family="Georgia, serif", size=12, color="#1A1612"),
    xaxis=dict(showgrid=False, tickfont=dict(color="#1A1612", size=11)),
    yaxis=dict(showgrid=True, gridcolor="#E8E0CE", range=[0, 105], title="Signal Score"),
    margin=dict(l=0, r=0, t=20, b=0),
    showlegend=False,
)
st.plotly_chart(_fig_bar, use_container_width=True)

st.divider()

# ── What this means ───────────────────────────────────────────────────────────
with st.expander("How to interpret this map"):
    st.markdown("""
    **Score** is the average of all alternative-data signals in each sector's category.
    It uses the same 0–100 Confluence Score methodology as the Ticker Deep Dive — signals
    are z-scored against their own history, then mapped to 0–100.

    **Green ≥ 60** means more signals in that sector are running above their historical average
    than below — the macro backdrop currently favors this sector.

    **Red ≤ 40** means more signals are below their historical average — macro headwinds.

    **This is NOT a stock screener.** A bullish sector signal means the data backdrop favors
    stocks in that sector over the next 4–12 weeks on average. Individual stocks can diverge
    significantly from the sector.

    **Use this alongside Ticker Deep Dive** — find which sectors the signals favor here, then
    go research specific tickers in those sectors with the full per-ticker scoring.

    *All data from public sources. Not financial advice.*
    """)

st.markdown("""
<div style="text-align:center;padding:16px;font-size:0.75rem;color:#9E9E8E;font-family:Georgia,serif;">
    Unstructured Alpha · Sector scores update every 2 hours · Not financial advice
</div>
""", unsafe_allow_html=True)
