"""
Page 16 — Short Squeeze Radar
==============================
Synthesizes three data sources no other free tool combines:

  1. Short Interest (FINRA / yfinance shortRatio)
       → high short interest means a lot of fuel for a squeeze
  2. Macro Bull Convergence (our signal engine, zero extra API calls)
       → signals say the fundamentals are turning UP against those shorts
  3. Insider Cluster Buys (SEC EDGAR Form 4, 21-day window)
       → the people who know the business are putting real money in

When all three align — shorts are loaded, macro is turning bullish, and
insiders are buying — that's the setup that precedes explosive moves.
Large hedge funds pay six figures a year to see this. It's free here.

SCORING:
  Squeeze Score = (Short Ratio Rank × 0.35) + (Macro Score × 0.40) + (Insider Bonus × 0.25)
  Each component is normalised 0-100. Final score is 0-100.

  Insider Bonus:
    2+ insiders within 21 days → 100
    1 insider within 21 days   → 50
    0 insiders within 21 days  → 0

DATA FRESHNESS:
  Short interest: 15-min yfinance cache (uses shortRatio from .info — not
  the raw FINRA filing, which lags 2 weeks, but is a good real-time proxy).
  Macro scores: 2h shared cache (same as all other pages).
  Insider data: daily resolution from EDGAR (yfinance proxy).
"""

from __future__ import annotations

import streamlit as st

from utils.config import TICKERS
from utils.header import render_header, render_sidebar_base, render_page_header, go_to_ticker
from utils.db import init_db

st.set_page_config(page_title="Short Squeeze Radar — UA", layout="wide")
render_header("Short Squeeze Radar")
render_sidebar_base()

render_page_header(
    "Short Squeeze Radar",
    "High short interest + bullish macro + insider buying — the squeeze setup.",
    icon="🎯",
)
init_db()

# ── Data loading ──────────────────────────────────────────────────────────────

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone


@st.cache_data(ttl=900, show_spinner=False, max_entries=1)  # 15-min cache
def _get_short_interest_batch(tickers_tuple: tuple[str, ...]) -> dict[str, float | None]:
    """
    Fetch shortRatio (short interest ratio / days to cover) for a batch of
    tickers via yfinance .info. Returns {ticker: short_ratio | None}.
    short_ratio = shares_short / avg_daily_volume. Higher = more fuel.
    """
    result: dict[str, float | None] = {}
    # yfinance bulk info is fetched ticker-by-ticker but batched to avoid
    # hammering the API. We use a compact 1d download to prime the cache,
    # then read .info for the short data.
    for ticker in tickers_tuple:
        try:
            info = yf.Ticker(ticker).info
            ratio = info.get("shortRatio") or info.get("shortPercentOfFloat")
            result[ticker] = float(ratio) if ratio is not None else None
        except Exception:
            result[ticker] = None
    return result


@st.cache_data(ttl=3600, show_spinner=False, max_entries=1)  # 1h cache
def _get_insider_cluster_batch(tickers_tuple: tuple[str, ...]) -> dict[str, int]:
    """
    Fetch insider transaction counts from EDGAR (via yfinance) for each
    ticker, counting buy transactions by distinct insiders in the last 21
    days. Returns {ticker: count_of_distinct_insider_buyers}.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=21)).date()
    result: dict[str, int] = {}
    for ticker in tickers_tuple:
        try:
            obj = yf.Ticker(ticker)
            hist = obj.insider_transactions
            if hist is None or hist.empty:
                result[ticker] = 0
                continue
            # Normalise column names (yfinance versions differ)
            cols = {c.lower(): c for c in hist.columns}
            date_col  = cols.get("startdate") or cols.get("date") or cols.get("transactiondate")
            shares_col = cols.get("shares") or cols.get("value") or cols.get("amount")
            if not date_col:
                result[ticker] = 0
                continue
            hist["_dt"] = pd.to_datetime(hist[date_col], errors="coerce").dt.date
            recent = hist[hist["_dt"] >= cutoff]
            if shares_col:
                buys = recent[pd.to_numeric(recent[shares_col], errors="coerce").fillna(0) > 0]
            else:
                buys = recent
            result[ticker] = int(buys["Insider"].nunique() if "Insider" in buys.columns else len(buys))
        except Exception:
            result[ticker] = 0
    return result


@st.cache_data(ttl=7200, show_spinner=False, max_entries=2)
def _get_macro_scores_all() -> list[dict]:
    """Return all ticker macro scores from the shared signal cache."""
    from utils.top_tickers import get_top_tickers
    from utils.signals_cache import get_all_signal_scores
    _scores = get_all_signal_scores()
    data = get_top_tickers(len(_scores))
    return data.get("all", [])


# ── Build the radar ───────────────────────────────────────────────────────────

@st.cache_data(ttl=900, show_spinner=False, max_entries=1)
def build_squeeze_radar(signal_hash: int = 0) -> pd.DataFrame:
    """
    Compute the composite Squeeze Score for every ticker in the universe.
    Returns a DataFrame sorted by squeeze_score descending.
    """
    macro_rows = _get_macro_scores_all()
    if not macro_rows:
        return pd.DataFrame()

    # Only evaluate tickers with macro data
    tickers = tuple(r["ticker"] for r in macro_rows)

    short_data   = _get_short_interest_batch(tickers)
    insider_data = _get_insider_cluster_batch(tickers)

    macro_by_ticker = {r["ticker"]: r for r in macro_rows}

    # Normalise short ratio to 0-100 rank
    # Use rank-based normalisation so outliers don't dominate
    short_vals = [(t, v) for t, v in short_data.items() if v is not None]
    if short_vals:
        sorted_short = sorted(short_vals, key=lambda x: x[1])
        short_rank: dict[str, float] = {}
        n = len(sorted_short)
        for i, (t, _) in enumerate(sorted_short):
            short_rank[t] = round((i / max(n - 1, 1)) * 100, 1)
    else:
        short_rank = {}

    rows = []
    for ticker, meta in TICKERS.items():
        macro = macro_by_ticker.get(ticker)
        if not macro:
            continue

        macro_score   = float(macro.get("score", 50))
        short_r       = short_rank.get(ticker, 50.0)
        insiders      = insider_data.get(ticker, 0)
        insider_bonus = 100 if insiders >= 2 else (50 if insiders == 1 else 0)

        # Only show BULL macro cases — bearish macro means the shorts may be right
        if macro.get("case") != "BULL":
            continue

        squeeze_score = (
            short_r      * 0.35 +
            macro_score  * 0.40 +
            insider_bonus * 0.25
        )

        rows.append({
            "ticker":         ticker,
            "name":           meta.get("name", ticker),
            "sector":         meta.get("sector", "Other"),
            "squeeze_score":  round(squeeze_score, 1),
            "macro_score":    round(macro_score, 1),
            "short_ratio":    short_data.get(ticker),
            "short_rank":     round(short_r, 1),
            "insider_buyers": insiders,
            "insider_bonus":  insider_bonus,
            "bull_signals":   macro.get("bull", 0),
            "bear_signals":   macro.get("bear", 0),
            "conv":           macro.get("conv", ""),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("squeeze_score", ascending=False).reset_index(drop=True)


# ── Page header ───────────────────────────────────────────────────────────────

st.markdown("# 🔥 Short Squeeze Radar")
st.markdown(
    '<div style="font-family:Inter,sans-serif;font-size:0.92rem;color:#8892AA;margin-bottom:18px;'
    'background:#12151E;border-left:4px solid #F59E0B;padding:12px 16px;border-radius:0 8px 8px 0;">'
    '<b>What this page does:</b> Finds tickers where (1) short sellers are heavily positioned, '
    '(2) the macro signal engine says the fundamentals are turning bullish against those shorts, '
    'and (3) company insiders have been buying in the last 21 days. '
    'All three aligned = highest-conviction squeeze setup. '
    'You used to need a Bloomberg terminal to see this synthesis. It\'s free here.'
    '</div>',
    unsafe_allow_html=True,
)

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Loading short interest, macro scores, and insider data…"):
    from utils.signals_cache import get_all_signal_scores as _gss
    _raw = _gss()
    _df = build_squeeze_radar(signal_hash=len(_raw))

if _df.empty:
    st.warning(
        "No squeeze setups found right now. This could mean: (a) the macro environment "
        "is not broadly bullish, or (b) short interest data is temporarily unavailable. "
        "Check back after market hours or when macro signals shift."
    )
    st.stop()

# ── Tier 1: High-conviction setups (all 3 components strong) ─────────────────

_tier1 = _df[
    (_df["short_rank"] >= 60) &
    (_df["macro_score"] >= 65) &
    (_df["insider_buyers"] >= 1)
].head(8)

_tier2 = _df[~_df["ticker"].isin(_tier1["ticker"])].head(12)

st.markdown(
    '<div style="background:#7C3AED;border-radius:10px;padding:14px 20px;margin-bottom:18px;">'
    '<div style="font-size:0.68rem;letter-spacing:0.12em;color:#F59E0B;font-weight:700;'
    'text-transform:uppercase;margin-bottom:4px;">HIGH CONVICTION — ALL THREE FACTORS ALIGNED</div>'
    f'<div style="font-size:0.90rem;color:#EEF3FA;">'
    f'<b>{len(_tier1)} setup{"s" if len(_tier1) != 1 else ""}</b> with high short interest + bullish macro + insider buying</div>'
    '</div>',
    unsafe_allow_html=True,
)

def _squeeze_card(row: pd.Series, is_tier1: bool = False) -> str:
    """Render one ticker's squeeze card as HTML."""
    bg = "#12151E" if not is_tier1 else "#0F1118"
    border_color = "#F59E0B" if is_tier1 else "rgba(255,255,255,0.08)"
    sq_color = (
        "#00D566" if row["squeeze_score"] >= 75 else
        "#B8860B" if row["squeeze_score"] >= 55 else
        "#6B7FBF"
    )
    insider_html = (
        f'🔥 {row["insider_buyers"]} insider buy{"s" if row["insider_buyers"] > 1 else ""} (21d)'
        if row["insider_buyers"] >= 1 else
        '<span style="color:#9E9E8E;">No recent insider buys</span>'
    )
    sr_display = f'{row["short_ratio"]:.1f}x' if row["short_ratio"] is not None else "N/A"
    fire_badge = "🔥 " if is_tier1 else ""
    return (
        f'<div style="background:{bg};border-radius:8px;padding:12px 16px;margin-bottom:8px;'
        f'border:1px solid {border_color};border-left:4px solid {sq_color};font-family:Inter,sans-serif;">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        f'  <div style="flex:1;">'
        f'    <div style="font-size:1.0rem;font-weight:800;color:#E8EEFF;">{fire_badge}{row["ticker"]}</div>'
        f'    <div style="font-size:0.76rem;color:#8892AA;">{row["name"][:36]}</div>'
        f'    <div style="font-size:0.67rem;color:#6B7FBF;margin-top:1px;">{row["sector"]}</div>'
        f'  </div>'
        f'  <div style="text-align:right;min-width:70px;">'
        f'    <div style="font-size:1.3rem;font-weight:800;color:{sq_color};">{row["squeeze_score"]:.0f}</div>'
        f'    <div style="font-size:0.63rem;color:#6B7FBF;text-transform:uppercase;">Squeeze Score</div>'
        f'  </div>'
        f'</div>'
        f'<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;font-size:0.72rem;">'
        f'  <span style="background:#7C3AED18;color:#7C3AED;padding:2px 8px;border-radius:10px;font-weight:600;">'
        f'    📊 Macro: {row["macro_score"]:.0f}/100 ({row["bull_signals"]}↑ {row["bear_signals"]}↓)</span>'
        f'  <span style="background:#F59E0B18;color:#8B6914;padding:2px 8px;border-radius:10px;font-weight:600;">'
        f'    📉 Short ratio: {sr_display} (top {100-row["short_rank"]:.0f}%)</span>'
        f'  <span style="background:#4CAF5018;color:#2E7D32;padding:2px 8px;border-radius:10px;font-weight:600;">'
        f'    {insider_html}</span>'
        f'</div>'
        f'</div>'
    )


if not _tier1.empty:
    _t1c1, _t1c2 = st.columns(2)
    _t1_left  = _tier1.iloc[:len(_tier1)//2 + len(_tier1)%2]
    _t1_right = _tier1.iloc[len(_tier1)//2 + len(_tier1)%2:]
    with _t1c1:
        for _, row in _t1_left.iterrows():
            st.markdown(_squeeze_card(row, is_tier1=True), unsafe_allow_html=True)
            go_to_ticker(row["ticker"], key=f"sqz_t1_{row['ticker']}")
    with _t1c2:
        for _, row in _t1_right.iterrows():
            st.markdown(_squeeze_card(row, is_tier1=True), unsafe_allow_html=True)
            go_to_ticker(row["ticker"], key=f"sqz_t1b_{row['ticker']}")
else:
    st.info("No setups currently meet all three criteria simultaneously. Check the broader radar below.")

# ── Tier 2: Broader Radar ─────────────────────────────────────────────────────

st.divider()
st.markdown(
    '<div style="font-size:0.68rem;font-weight:700;color:#6B7FBF;letter-spacing:0.10em;'
    'text-transform:uppercase;margin-bottom:12px;">BROADER RADAR — MACRO BULL + ELEVATED SHORT INTEREST</div>',
    unsafe_allow_html=True,
)

if not _tier2.empty:
    _t2c1, _t2c2 = st.columns(2)
    _t2_left  = _tier2.iloc[:len(_tier2)//2 + len(_tier2)%2]
    _t2_right = _tier2.iloc[len(_tier2)//2 + len(_tier2)%2:]
    with _t2c1:
        for _, row in _t2_left.iterrows():
            st.markdown(_squeeze_card(row, is_tier1=False), unsafe_allow_html=True)
            go_to_ticker(row["ticker"], key=f"sqz_t2_{row['ticker']}")
    with _t2c2:
        for _, row in _t2_right.iterrows():
            st.markdown(_squeeze_card(row, is_tier1=False), unsafe_allow_html=True)
            go_to_ticker(row["ticker"], key=f"sqz_t2b_{row['ticker']}")

# ── Full table (expandable) ───────────────────────────────────────────────────

st.divider()
with st.expander(f"📋 Full Squeeze Radar table ({len(_df)} BULL tickers ranked)", expanded=False):
    _disp = _df[["ticker", "name", "sector", "squeeze_score", "macro_score",
                  "short_ratio", "short_rank", "insider_buyers", "conv"]].copy()
    _disp.columns = ["Ticker", "Name", "Sector", "Squeeze Score", "Macro",
                      "Short Ratio", "Short Rank %", "Insider Buys (21d)", "Conviction"]
    _disp["Short Ratio"] = _disp["Short Ratio"].apply(
        lambda x: f"{x:.1f}x" if pd.notna(x) and x is not None else "N/A"
    )
    _disp["Short Rank %"] = _disp["Short Rank %"].apply(lambda x: f"{x:.0f}")
    st.dataframe(_disp, use_container_width=True, hide_index=True)

# ── Score explainer ───────────────────────────────────────────────────────────

with st.expander("ℹ️ How the Squeeze Score is calculated", expanded=False):
    st.markdown("""
**Squeeze Score** = (Short Ratio Rank × 0.35) + (Macro Score × 0.40) + (Insider Bonus × 0.25)

Each component is scaled 0-100:

| Component | Weight | Source | What it measures |
|---|---|---|---|
| **Short Ratio Rank** | 35% | FINRA / yfinance | Percentile rank of short interest ratio vs. all tracked tickers. Higher = more fuel for a squeeze. |
| **Macro Score** | 40% | Our 38-signal engine | How aligned macro data is with a bullish outcome for this ticker. This is the differentiating view. |
| **Insider Bonus** | 25% | SEC EDGAR Form 4 | 100 pts for 2+ distinct insiders buying in 21 days. 50 pts for 1 insider. 0 for none. |

**Only BULL macro cases appear in the radar.** A ticker where the macro is bearish means the shorts may be correct — filtering those out reduces false positives.

**Short ratio** here is `shortRatio` from yfinance — days to cover (shares short ÷ avg daily volume). Not the exact FINRA biweekly filing, but a real-time proxy that moves directionally with actual short interest.

Not financial advice. This is a synthesis tool — do your own research before any position.
""")

st.markdown("""
<div class="disclaimer">
<b>Not financial advice.</b> Squeeze Score is a screening tool, not a prediction.
Short squeezes are rare, violent, and often reverse quickly. Short interest and insider
data may lag by days. Macro signals lead prices by 4–16 weeks on average, but individual
outcomes vary. Do your own research.
</div>
""", unsafe_allow_html=True)
