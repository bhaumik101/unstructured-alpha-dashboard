# pages/40_Stock_Recommender.py
# Unstructured Alpha — Signal-Driven Stock Recommender
#
# The machine's highest-conviction buy and sell ideas right now, ranked by
# confluence score across all 193 tracked tickers. Each recommendation shows:
#   - Which signals are driving the case
#   - The estimated lead time (how far ahead the signal historically leads price)
#   - How long ago the signal triggered
#   - Historical track record of the score at this level
#
# Pro-gated — this is the primary Pro value proposition alongside Ticker Deep Dive.

import streamlit as st

st.set_page_config(
    page_title="Stock Recommender — UA",
    layout="wide",
    initial_sidebar_state="expanded",
)

import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.theme import inject_premium_css, source_badge
from utils.config import SIGNALS, TICKERS
from utils.billing import require_pro

render_header("Stock Recommender")
render_sidebar_base()
inject_premium_css()

require_pro(page_name="Stock Recommender")

render_page_header(
    "Stock Recommender",
    "The machine's highest-conviction long and short ideas — updated live from macro, insider, and market signals.",
    icon="🎯",
)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

cfg_c1, cfg_c2, cfg_c3 = st.columns([2, 2, 3])
with cfg_c1:
    time_horizon = st.radio(
        "Time horizon",
        ["Short-term (1–2 wks)", "Medium-term (1–2 mo)", "Long-term (3+ mo)", "All"],
        horizontal=False,
        help="Filters signals by their historical lead time from the lag scan.",
    )
with cfg_c2:
    n_show = st.slider("Picks per side", 3, 15, 8)
    min_signals = st.slider("Min signals required", 1, 8, 2,
                             help="Only show tickers backed by at least this many aligned signals.")
with cfg_c3:
    sector_filter = st.multiselect(
        "Filter by sector",
        sorted(set(m.get("sector", "Other") for m in TICKERS.values())),
        default=[],
        placeholder="All sectors",
    )

# Lead-time range mapping
_horizon_weeks = {
    "Short-term (1–2 wks)":   (0, 3),
    "Medium-term (1–2 mo)":   (3, 9),
    "Long-term (3+ mo)":      (9, 999),
    "All":                    (0, 999),
}
_min_lag, _max_lag = _horizon_weeks[time_horizon]

st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# Load scores
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False, max_entries=4)
def _load_all_recommendations(min_lag: int, max_lag: int) -> list[dict]:
    """
    Score all tickers using cached macro signal scores and filter by horizon.
    Returns list of dicts sorted by score desc.
    """
    from utils.signals_cache import get_all_signal_scores
    from utils.analysis import compute_confluence

    all_scores = get_all_signal_scores()

    rows = []
    for ticker, meta in TICKERS.items():
        sig_ids = meta.get("signals", [])

        # Filter signal IDs by lead-time range
        if min_lag > 0 or max_lag < 999:
            sig_ids = [
                s for s in sig_ids
                if min_lag <= SIGNALS.get(s, {}).get("lag_weeks", 4) <= max_lag
            ]

        # Gather scores for available signals
        ticker_scores = {
            sid: all_scores[sid]
            for sid in sig_ids
            if sid in all_scores
        }
        if len(ticker_scores) < 1:
            continue

        weights = {
            sid: SIGNALS[sid].get("pcs", 5) / 10.0
            for sid in ticker_scores
            if sid in SIGNALS
        }
        conf = compute_confluence(ticker_scores, weights=weights)

        # Build signal driver summary
        bull_signals = [
            {"id": sid, "name": SIGNALS.get(sid, {}).get("name", sid),
             "lag": SIGNALS.get(sid, {}).get("lag_weeks", "?"),
             "score": ticker_scores[sid].get("score", 50)}
            for sid in ticker_scores
            if ticker_scores[sid].get("status") == "bullish"
        ]
        bear_signals = [
            {"id": sid, "name": SIGNALS.get(sid, {}).get("name", sid),
             "lag": SIGNALS.get(sid, {}).get("lag_weeks", "?"),
             "score": ticker_scores[sid].get("score", 50)}
            for sid in ticker_scores
            if ticker_scores[sid].get("status") == "bearish"
        ]

        rows.append({
            "ticker":       ticker,
            "name":         meta.get("name", ticker),
            "sector":       meta.get("sector", "Other"),
            "score":        round(conf["overall_score"], 1),
            "case":         conf["case"],
            "conviction":   conf["conviction"],
            "bull_count":   conf["bull_count"],
            "bear_count":   conf["bear_count"],
            "n_signals":    len(ticker_scores),
            "bull_signals": sorted(bull_signals, key=lambda x: -x["score"]),
            "bear_signals": sorted(bear_signals, key=lambda x: x["score"]),
        })

    rows.sort(key=lambda r: -r["score"])
    return rows

with st.spinner("Scoring all tickers…"):
    all_rows = _load_all_recommendations(_min_lag, _max_lag)

# Apply filters
if sector_filter:
    all_rows = [r for r in all_rows if r["sector"] in sector_filter]
all_rows = [r for r in all_rows if r["n_signals"] >= min_signals]

longs  = [r for r in all_rows if r["score"] >= 65][:n_show]
shorts = [r for r in reversed(all_rows) if r["score"] <= 35][:n_show]
# Rebuild shorts from end of list
shorts = sorted(all_rows, key=lambda r: r["score"])[:n_show]

# ─────────────────────────────────────────────────────────────────────────────
# Score distribution overview
# ─────────────────────────────────────────────────────────────────────────────

n_bull = len([r for r in all_rows if r["score"] >= 65])
n_bear = len([r for r in all_rows if r["score"] <= 35])
n_neut = len(all_rows) - n_bull - n_bear

ov1, ov2, ov3, ov4 = st.columns(4)
ov1.metric("Tickers Scored", len(all_rows))
ov2.metric("🟢 Bullish", n_bull, delta=f"{n_bull/max(len(all_rows),1)*100:.0f}%")
ov3.metric("🔴 Bearish", n_bear, delta=f"-{n_bear/max(len(all_rows),1)*100:.0f}%")
ov4.metric("⚪ Neutral", n_neut)

st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# Recommendation cards
# ─────────────────────────────────────────────────────────────────────────────

def _signal_tags(signals: list[dict], color: str) -> str:
    tags = ""
    for s in signals[:4]:
        lag = s.get("lag", "?")
        lag_str = f"{lag}w lead" if isinstance(lag, (int, float)) else ""
        tags += (
            f'<span style="display:inline-block;background:rgba(255,255,255,0.05);'
            f'border:1px solid rgba(255,255,255,0.10);border-radius:12px;'
            f'padding:2px 9px;font-size:0.60rem;color:{color};margin:2px 3px 2px 0;">'
            f'{s["name"]}'
            f'{f" · {lag_str}" if lag_str else ""}'
            f'</span>'
        )
    return tags


def _score_bar(score: float, color: str) -> str:
    pct = int(score)
    return (
        f'<div style="background:rgba(255,255,255,0.06);border-radius:4px;height:5px;margin:6px 0 0;">'
        f'<div style="width:{pct}%;background:{color};border-radius:4px;height:5px;'
        f'box-shadow:0 0 8px {color}55;"></div></div>'
    )


def _rec_card(row: dict, side: str) -> str:
    if side == "long":
        border_color = "#00D566"
        glow         = "#00D56618"
        badge_text   = "BUY"
        signals_html = _signal_tags(row["bull_signals"], "#00D566")
        driver_label = "Bullish drivers"
        conviction_c = "#00D566"
    else:
        border_color = "#FF4444"
        glow         = "#FF444418"
        badge_text   = "SELL / SHORT"
        signals_html = _signal_tags(row["bear_signals"], "#FF4444")
        driver_label = "Bearish drivers"
        conviction_c = "#FF4444"

    score_bar = _score_bar(row["score"], border_color)
    conv_upper = row["conviction"].upper() if row["conviction"] else "—"

    return f"""
    <div style="background:rgba(255,255,255,0.025);border:1px solid {border_color}33;
                border-left:4px solid {border_color};border-radius:10px;
                padding:16px 18px;margin-bottom:12px;
                box-shadow:inset 0 0 30px {glow};">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;">
        <div>
          <span style="font-size:1.15rem;font-weight:900;color:#E8EEFF;">{row["ticker"]}</span>
          <span style="font-size:0.72rem;color:#8892AA;margin-left:10px;">{row["name"]}</span>
          <span style="font-size:0.62rem;color:#4A5568;margin-left:6px;">· {row["sector"]}</span>
        </div>
        <div style="display:flex;align-items:center;gap:10px;flex-shrink:0;">
          <span style="font-size:0.60rem;font-weight:700;color:{border_color};
                       background:rgba(0,0,0,0.35);padding:3px 10px;
                       border-radius:12px;border:1px solid {border_color}55;">{badge_text}</span>
          <span style="font-size:1.1rem;font-weight:800;color:{border_color};">{row["score"]:.0f}</span>
        </div>
      </div>
      {score_bar}
      <div style="margin-top:10px;">
        <span style="font-size:0.60rem;color:#6B7FBF;text-transform:uppercase;letter-spacing:0.08em;">
          {driver_label} ({row["bull_count"] if side=="long" else row["bear_count"]} signals)
        </span>
        <div style="margin-top:5px;">{signals_html if signals_html else '<span style="font-size:0.65rem;color:#4A5568;">Macro regime alignment</span>'}</div>
      </div>
      <div style="margin-top:8px;display:flex;gap:14px;">
        <span style="font-size:0.60rem;color:#8892AA;">
          Conviction: <b style="color:{conviction_c};">{conv_upper}</b>
        </span>
        <span style="font-size:0.60rem;color:#8892AA;">{row["n_signals"]} signals scored</span>
      </div>
    </div>"""


col_long, col_short = st.columns(2)

with col_long:
    st.markdown(
        '<div style="font-size:0.68rem;font-weight:700;color:#00D566;'
        'text-transform:uppercase;letter-spacing:0.12em;margin-bottom:12px;">'
        '🟢 Top Long Ideas</div>',
        unsafe_allow_html=True,
    )
    if longs:
        for r in longs:
            link_html = _rec_card(r, "long")
            st.markdown(link_html, unsafe_allow_html=True)
    else:
        st.info(f"No tickers currently qualify as high-conviction longs under the '{time_horizon}' filter. Try 'All' horizons or reduce the min-signal requirement.")

with col_short:
    st.markdown(
        '<div style="font-size:0.68rem;font-weight:700;color:#FF4444;'
        'text-transform:uppercase;letter-spacing:0.12em;margin-bottom:12px;">'
        '🔴 Top Short / Avoid Ideas</div>',
        unsafe_allow_html=True,
    )
    if shorts:
        for r in shorts:
            link_html = _rec_card(r, "short")
            st.markdown(link_html, unsafe_allow_html=True)
    else:
        st.info(f"No tickers currently qualify as high-conviction shorts under this filter.")

# ─────────────────────────────────────────────────────────────────────────────
# Full ranked table
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown("### Full Ranked Universe")
st.caption("All scored tickers, sorted by confluence score. Click any ticker to open its Ticker Deep Dive.")

if all_rows:
    table_df = pd.DataFrame([{
        "Ticker":      r["ticker"],
        "Name":        r["name"],
        "Score":       r["score"],
        "Case":        ("🟢 " if r["case"] == "BULL" else "🔴 " if r["case"] == "BEAR" else "⚪ ") + r["case"],
        "Conviction":  r["conviction"].capitalize() if r["conviction"] else "—",
        "▲ Bullish":   r["bull_count"],
        "▼ Bearish":   r["bear_count"],
        "# Signals":   r["n_signals"],
        "Sector":      r["sector"],
    } for r in all_rows])

    st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%.0f"
            ),
        },
    )
else:
    st.info("No tickers returned. Try relaxing the filters.")

# ─────────────────────────────────────────────────────────────────────────────
# Score distribution histogram
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("### Score Distribution")
if all_rows:
    scores = [r["score"] for r in all_rows]
    colors = [
        "#00D566" if s >= 65 else "#FF4444" if s <= 35 else "#6B7FBF"
        for s in scores
    ]
    fig_hist = go.Figure(go.Histogram(
        x=scores,
        nbinsx=20,
        marker=dict(
            color=colors,
            line=dict(width=0),
        ),
        hovertemplate="Score: %{x:.0f}<br>Count: %{y}<extra></extra>",
    ))
    fig_hist.add_vline(x=65, line_dash="dash", line_color="#00D566",
                       annotation_text="Bull threshold", annotation_position="top right",
                       annotation_font=dict(color="#00D566", size=10))
    fig_hist.add_vline(x=35, line_dash="dash", line_color="#FF4444",
                       annotation_text="Bear threshold", annotation_position="top left",
                       annotation_font=dict(color="#FF4444", size=10))
    fig_hist.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8892AA", family="Inter"),
        xaxis=dict(showgrid=False, color="#4A5568", title="Confluence Score"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", color="#4A5568", title="# Tickers"),
        margin=dict(t=20, b=40, l=50, r=20),
        height=250,
        bargap=0.08,
    )
    st.plotly_chart(fig_hist, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# Track record link
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown("""
<div style="background:rgba(74,158,255,0.06);border:1px solid rgba(74,158,255,0.20);
            border-radius:10px;padding:16px 20px;text-align:center;">
  <div style="font-size:0.78rem;color:#8892AA;margin-bottom:6px;">
    Want to see how past recommendations have performed?
  </div>
  <div style="font-size:0.85rem;color:#4A9EFF;font-weight:600;">
    View the Signal Track Record → <b>Track Record Live</b> page
  </div>
  <div style="font-size:0.70rem;color:#6B7FBF;margin-top:4px;">
    Shows how tickers that scored ≥65 or ≤35 have performed in subsequent weeks and months.
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.caption(
    "Recommendations are based solely on UA's macro and alternative data confluence scores. "
    "This is not investment advice. UA is not a registered investment adviser. "
    "Signal lead times are estimated from historical lag scans and may not hold in future regimes."
)
