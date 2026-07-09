# pages/33_Scoreboard.py
# Unstructured Alpha — Public Live Scoreboard
#
# No login required. Shows the machine's 25 most bullish + 25 most bearish
# tickers right now, scored by the 28-signal macro confluence engine.
# Updated each time the signals cache refreshes (~2-hour TTL).
#
# Acquisition surface: this page is designed to be shared. Anyone who lands
# here sees real, live signal intelligence. To understand WHY a ticker scores
# the way it does, they need to open Ticker Deep Dive — which requires an
# account. That's the natural funnel.

import streamlit as st

st.set_page_config(
    page_title="Live Scoreboard — UA",
    layout="wide",
    initial_sidebar_state="expanded",
)

from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from utils.header import render_header, render_page_header, render_sidebar_base
from utils.top_tickers import get_top_tickers
from utils.db import engine, score_snapshots
from utils.theme import inject_premium_css

render_header("Scoreboard")
render_sidebar_base()
inject_premium_css()

render_page_header(
    "Live Scoreboard",
    "The machine's top and bottom signals across the full ticker universe — refreshed every 2 hours.",
    icon="📊",
)


# ── Fetch scores ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200, show_spinner=False, max_entries=1)
def _load_all_rows() -> list[dict]:
    from utils.signals_cache import get_all_signal_scores
    signal_scores = get_all_signal_scores()
    result = get_top_tickers(signal_scores_hash=len(signal_scores))
    return result.get("all", [])


@st.cache_data(ttl=7200, show_spinner=False, max_entries=1)
def _load_7d_deltas(ticker_tuple: tuple) -> dict[str, float]:
    """
    Query score_snapshots for 7-day deltas for the given tickers.
    Returns {ticker: delta} (may be partial if some tickers have no history).
    """
    if not ticker_tuple:
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(
                    score_snapshots.c.ticker,
                    score_snapshots.c.score,
                    score_snapshots.c.snapshot_date,
                )
                .where(score_snapshots.c.ticker.in_(list(ticker_tuple)))
                .where(score_snapshots.c.snapshot_date >= cutoff)
                .order_by(score_snapshots.c.ticker, score_snapshots.c.snapshot_date)
            ).fetchall()
    except Exception:
        return {}

    # Group by ticker, take earliest vs latest within the window
    from collections import defaultdict
    by_ticker: dict[str, list] = defaultdict(list)
    for r in rows:
        by_ticker[r[0]].append((r[2], float(r[1])))  # (date, score)

    deltas: dict[str, float] = {}
    for ticker, entries in by_ticker.items():
        entries.sort()
        if len(entries) >= 2:
            deltas[ticker] = round(entries[-1][1] - entries[0][1], 1)
    return deltas


with st.spinner("Loading signal scores…"):
    all_rows = _load_all_rows()

top25    = all_rows[:25]
bottom25 = list(reversed(all_rows[-25:])) if len(all_rows) >= 25 else list(reversed(all_rows))

featured_tickers = tuple({r["ticker"] for r in top25 + bottom25})
deltas = _load_7d_deltas(featured_tickers)

refreshed_at = datetime.now(timezone.utc).strftime("%H:%M UTC")
total_scored = len(all_rows)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_pill(score: float, case: str) -> str:
    if case == "BULL":
        bg, fg = "#0D2B1A", "#00D566"
        border = "rgba(0,213,102,0.35)"
    elif case == "BEAR":
        bg, fg = "#2B0D15", "#FF4D6A"
        border = "rgba(255,77,106,0.35)"
    else:
        bg, fg = "#1A1E2B", "#F59E0B"
        border = "rgba(245,158,11,0.35)"
    return (
        f'<span style="background:{bg};color:{fg};border:1px solid {border};'
        f'border-radius:6px;padding:3px 10px;font-size:0.95rem;font-weight:800;'
        f'font-variant-numeric:tabular-nums;">{score:.0f}</span>'
    )


def _delta_badge(delta: float | None) -> str:
    if delta is None:
        return '<span style="color:#4A5280;font-size:0.75rem;">—</span>'
    color = "#00D566" if delta >= 0 else "#FF4D6A"
    arrow = "▲" if delta >= 0 else "▼"
    sign  = "+" if delta >= 0 else ""
    return (
        f'<span style="color:{color};font-size:0.78rem;font-weight:700;">'
        f'{arrow} {sign}{delta:.1f}</span>'
    )


def _case_label(case: str) -> str:
    MAP = {"BULL": ("Bullish", "#00D566"), "BEAR": ("Bearish", "#FF4D6A")}
    label, color = MAP.get(case, ("Neutral", "#F59E0B"))
    return f'<span style="color:{color};font-size:0.78rem;font-weight:600;">{label}</span>'


def _render_table(rows: list[dict], label: str, emoji: str) -> None:
    st.markdown(
        f'<div style="font-size:0.62rem;font-weight:700;color:#8892AA;'
        f'letter-spacing:0.12em;text-transform:uppercase;margin-bottom:10px;">'
        f'{emoji} {label}</div>',
        unsafe_allow_html=True,
    )
    # Header
    h_cols = st.columns([0.5, 2.8, 2.2, 1.2, 1.2, 1.4])
    with h_cols[0]: st.markdown('<span style="font-size:0.68rem;color:#4A5280;">#</span>', unsafe_allow_html=True)
    with h_cols[1]: st.markdown('<span style="font-size:0.68rem;color:#4A5280;">TICKER</span>', unsafe_allow_html=True)
    with h_cols[2]: st.markdown('<span style="font-size:0.68rem;color:#4A5280;">SECTOR</span>', unsafe_allow_html=True)
    with h_cols[3]: st.markdown('<span style="font-size:0.68rem;color:#4A5280;">SCORE</span>', unsafe_allow_html=True)
    with h_cols[4]: st.markdown('<span style="font-size:0.68rem;color:#4A5280;">7D Δ</span>', unsafe_allow_html=True)
    with h_cols[5]: st.markdown('<span style="font-size:0.68rem;color:#4A5280;"> </span>', unsafe_allow_html=True)
    st.markdown('<hr style="border:none;border-top:1px solid #1E2535;margin:4px 0 8px;">', unsafe_allow_html=True)

    for i, row in enumerate(rows, 1):
        ticker  = row["ticker"]
        delta   = deltas.get(ticker)
        cols    = st.columns([0.5, 2.8, 2.2, 1.2, 1.2, 1.4])

        with cols[0]:
            st.markdown(f'<span style="font-size:0.82rem;color:#4A5280;">{i}</span>', unsafe_allow_html=True)
        with cols[1]:
            name_short = row["name"][:26] + "…" if len(row["name"]) > 28 else row["name"]
            st.markdown(
                f'<div style="font-size:0.95rem;font-weight:700;color:#E8EEFF;">{ticker}</div>'
                f'<div style="font-size:0.72rem;color:#6B7A95;">{name_short}</div>',
                unsafe_allow_html=True,
            )
        with cols[2]:
            st.markdown(f'<span style="font-size:0.78rem;color:#8892AA;">{row.get("sector","")}</span>', unsafe_allow_html=True)
        with cols[3]:
            st.markdown(_score_pill(row["score"], row["case"]), unsafe_allow_html=True)
        with cols[4]:
            st.markdown(_delta_badge(delta), unsafe_allow_html=True)
        with cols[5]:
            if st.button("Deep Dive →", key=f"dd_{label}_{ticker}", use_container_width=True):
                st.query_params["ticker"] = ticker
                st.switch_page("pages/3_Ticker_Deep_Dive.py")

        st.markdown('<hr style="border:none;border-top:1px solid #12151E;margin:2px 0;">', unsafe_allow_html=True)


# ── Meta strip ────────────────────────────────────────────────────────────────

st.markdown(
    f'<div style="display:flex;gap:24px;align-items:center;margin-bottom:24px;'
    f'flex-wrap:wrap;">'
    f'<span style="font-size:0.75rem;color:#6B7A95;">🕐 Updated {refreshed_at}</span>'
    f'<span style="font-size:0.75rem;color:#6B7A95;">📡 {total_scored} tickers scored</span>'
    f'<span style="font-size:0.75rem;color:#6B7A95;">⚙️ 28 macro + alt-data signals</span>'
    f'<span style="font-size:0.75rem;color:#6B7A95;">0–100 scale · ≥65 Bullish · ≤35 Bearish</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Two-column layout ─────────────────────────────────────────────────────────

bull_col, bear_col = st.columns(2, gap="large")

with bull_col:
    _render_table(top25, "Top 25 — Most Bullish", "🟢")

with bear_col:
    _render_table(bottom25, "Bottom 25 — Most Bearish", "🔴")


# ── Footer note ───────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown(
    '<div style="font-size:0.72rem;color:#4A5280;text-align:center;line-height:1.8;">'
    'Scores reflect macro signal alignment only — not price momentum or fundamental valuation. '
    'Not financial advice. Click "Deep Dive →" on any ticker to see the full signal breakdown '
    '(account required). '
    '<a href="https://unstructuredalpha.com/About" style="color:#6B7A95;">Methodology →</a>'
    '</div>',
    unsafe_allow_html=True,
)
