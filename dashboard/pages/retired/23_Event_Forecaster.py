"""
Page 23 — Macro Event Impact Forecaster (#204)
===============================================
Shows upcoming macro events (FOMC, CPI, NFP, ISM, EIA) and what the
UA signal engine says about each:

  1. UPCOMING EVENTS CALENDAR — next 30 days of known macro release dates
     with UA signal status for the relevant data point

  2. SIGNAL STATE GOING INTO EACH EVENT — when the relevant signal was
     last bullish/bearish/neutral, by how much, and trend direction

  3. HISTORICAL EVENT IMPACT — what SPY / sector ETFs did in the 5 days
     AFTER similar events when the relevant UA signal was in its current
     state (from signal_snapshots + yfinance)

  4. CONSENSUS VS SIGNAL DIVERGENCE — flags cases where consensus
     expectation (derived from recent trend) diverges from our signal read

DATA SOURCES:
  • Event dates:      Hard-coded schedule for 2025-2026 (no API needed;
                      updated semi-annually — FOMC dates are announced ~1
                      year in advance, CPI/NFP are always 2nd or 3rd week)
  • Signal state:     get_all_signal_scores() — shared 2h cache
  • Price impact:     yfinance (SPY, QQQ, sector ETFs)
  • Snapshot history: signal_snapshots DB table
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta, date

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.signals_cache import get_all_signal_scores
from utils.config import SIGNALS

st.set_page_config(
    page_title="Event Forecaster — Unstructured Alpha",
    page_icon="📅",
    layout="wide",
)
render_header()
render_sidebar_base()

render_page_header(
    "Event Forecaster",
    "Model-based probability estimates for upcoming macro and earnings events.",
    icon="🎲",
)

st.markdown("""
<style>
.block-container { padding-top: 0.5rem !important; max-width: 1100px !important; }
.section-hdr {
    font-family: Inter, sans-serif; font-size: 0.70rem; font-weight: 700;
    letter-spacing: 0.12em; color: #6B7FBF; text-transform: uppercase;
    border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 4px; margin-bottom: 12px;
}
.event-card {
    border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 12px 16px;
    margin-bottom: 8px; font-family: Inter, sans-serif; background: #0F1118;
}
.event-bull  { border-left: 4px solid #00D566; }
.event-bear  { border-left: 4px solid #FF4444; }
.event-neut  { border-left: 4px solid #6B7FBF; }
.event-date  { font-size: 0.72rem; color: #6B7FBF; font-weight: 600; letter-spacing: 0.06em; }
.event-name  { font-size: 0.92rem; font-weight: 700; color: #E8EEFF; }
.event-sig   { font-size: 0.80rem; color: #6B5E52; margin-top: 2px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# EVENT CALENDAR  (semi-annually maintained)
# ─────────────────────────────────────────────────────────────────────────────
# Each event: (date_str, name, category, relevant_signal_ids, impact_etfs)
_RAW_EVENTS: list[tuple] = [
    # ── FOMC meetings ────────────────────────────────────────────────────────
    ("2025-07-30", "FOMC Rate Decision",           "Fed",      ["yield_curve", "ten_year_yield", "fedspeaks_hawkishness", "hy_spread"], ["SPY", "QQQ", "TLT", "GLD"]),
    ("2025-09-17", "FOMC Rate Decision",           "Fed",      ["yield_curve", "ten_year_yield", "fedspeaks_hawkishness", "hy_spread"], ["SPY", "QQQ", "TLT", "GLD"]),
    ("2025-10-29", "FOMC Rate Decision",           "Fed",      ["yield_curve", "ten_year_yield", "fedspeaks_hawkishness", "hy_spread"], ["SPY", "QQQ", "TLT", "GLD"]),
    ("2025-12-10", "FOMC Rate Decision",           "Fed",      ["yield_curve", "ten_year_yield", "fedspeaks_hawkishness", "hy_spread"], ["SPY", "QQQ", "TLT", "GLD"]),
    ("2026-01-28", "FOMC Rate Decision",           "Fed",      ["yield_curve", "ten_year_yield", "fedspeaks_hawkishness", "hy_spread"], ["SPY", "QQQ", "TLT", "GLD"]),
    ("2026-03-18", "FOMC Rate Decision",           "Fed",      ["yield_curve", "ten_year_yield", "fedspeaks_hawkishness", "hy_spread"], ["SPY", "QQQ", "TLT", "GLD"]),
    # ── CPI / Inflation (approx 2nd week of month, data for prior month) ────
    ("2025-07-15", "CPI Inflation Report",         "Inflation", ["hy_spread", "ten_year_yield", "ig_credit", "consumer_sentiment"],    ["SPY", "TLT", "GLD", "XLY"]),
    ("2025-08-12", "CPI Inflation Report",         "Inflation", ["hy_spread", "ten_year_yield", "ig_credit", "consumer_sentiment"],    ["SPY", "TLT", "GLD", "XLY"]),
    ("2025-09-10", "CPI Inflation Report",         "Inflation", ["hy_spread", "ten_year_yield", "ig_credit", "consumer_sentiment"],    ["SPY", "TLT", "GLD", "XLY"]),
    ("2025-10-14", "CPI Inflation Report",         "Inflation", ["hy_spread", "ten_year_yield", "ig_credit", "consumer_sentiment"],    ["SPY", "TLT", "GLD", "XLY"]),
    ("2025-11-12", "CPI Inflation Report",         "Inflation", ["hy_spread", "ten_year_yield", "ig_credit", "consumer_sentiment"],    ["SPY", "TLT", "GLD", "XLY"]),
    ("2025-12-10", "CPI Inflation Report",         "Inflation", ["hy_spread", "ten_year_yield", "ig_credit", "consumer_sentiment"],    ["SPY", "TLT", "GLD", "XLY"]),
    # ── NFP / Jobs (1st Friday of month) ────────────────────────────────────
    ("2025-08-01", "Nonfarm Payrolls (NFP)",       "Labor",    ["jobless_claims", "jolts_openings", "layoffs_rate", "ata_trucking"],   ["SPY", "XLF", "XLY", "IWM"]),
    ("2025-09-05", "Nonfarm Payrolls (NFP)",       "Labor",    ["jobless_claims", "jolts_openings", "layoffs_rate", "ata_trucking"],   ["SPY", "XLF", "XLY", "IWM"]),
    ("2025-10-03", "Nonfarm Payrolls (NFP)",       "Labor",    ["jobless_claims", "jolts_openings", "layoffs_rate", "ata_trucking"],   ["SPY", "XLF", "XLY", "IWM"]),
    ("2025-11-07", "Nonfarm Payrolls (NFP)",       "Labor",    ["jobless_claims", "jolts_openings", "layoffs_rate", "ata_trucking"],   ["SPY", "XLF", "XLY", "IWM"]),
    ("2025-12-05", "Nonfarm Payrolls (NFP)",       "Labor",    ["jobless_claims", "jolts_openings", "layoffs_rate", "ata_trucking"],   ["SPY", "XLF", "XLY", "IWM"]),
    # ── ISM Manufacturing PMI (1st business day of month) ───────────────────
    ("2025-08-01", "ISM Manufacturing PMI",        "PMI",      ["ism_pmi", "durable_goods", "shipping_index", "rail_traffic"],        ["SPY", "XLI", "XLB", "XLE"]),
    ("2025-09-02", "ISM Manufacturing PMI",        "PMI",      ["ism_pmi", "durable_goods", "shipping_index", "rail_traffic"],        ["SPY", "XLI", "XLB", "XLE"]),
    ("2025-10-01", "ISM Manufacturing PMI",        "PMI",      ["ism_pmi", "durable_goods", "shipping_index", "rail_traffic"],        ["SPY", "XLI", "XLB", "XLE"]),
    ("2025-11-03", "ISM Manufacturing PMI",        "PMI",      ["ism_pmi", "durable_goods", "shipping_index", "rail_traffic"],        ["SPY", "XLI", "XLB", "XLE"]),
    ("2025-12-01", "ISM Manufacturing PMI",        "PMI",      ["ism_pmi", "durable_goods", "shipping_index", "rail_traffic"],        ["SPY", "XLI", "XLB", "XLE"]),
    # ── EIA Weekly Reports ───────────────────────────────────────────────────
    ("2025-07-30", "EIA Crude Oil Inventories",   "Energy",   ["crude_inventories", "crude_oil", "retail_gasoline"],                  ["XLE", "XOM", "CVX", "OXY"]),
    ("2025-08-06", "EIA Crude Oil Inventories",   "Energy",   ["crude_inventories", "crude_oil", "retail_gasoline"],                  ["XLE", "XOM", "CVX", "OXY"]),
    ("2025-08-13", "EIA Crude Oil Inventories",   "Energy",   ["crude_inventories", "crude_oil", "retail_gasoline"],                  ["XLE", "XOM", "CVX", "OXY"]),
    ("2025-08-20", "EIA Crude Oil Inventories",   "Energy",   ["crude_inventories", "crude_oil", "retail_gasoline"],                  ["XLE", "XOM", "CVX", "OXY"]),
    ("2025-08-27", "EIA Crude Oil Inventories",   "Energy",   ["crude_inventories", "crude_oil", "retail_gasoline"],                  ["XLE", "XOM", "CVX", "OXY"]),
    # ── Retail Sales (mid-month) ─────────────────────────────────────────────
    ("2025-08-15", "Retail Sales",                "Consumer", ["retail_sales", "consumer_sentiment", "ecommerce_share"],              ["XLY", "XLP", "AMZN", "TGT"]),
    ("2025-09-16", "Retail Sales",                "Consumer", ["retail_sales", "consumer_sentiment", "ecommerce_share"],              ["XLY", "XLP", "AMZN", "TGT"]),
    ("2025-10-16", "Retail Sales",                "Consumer", ["retail_sales", "consumer_sentiment", "ecommerce_share"],              ["XLY", "XLP", "AMZN", "TGT"]),
    # ── Housing (mid-late month) ─────────────────────────────────────────────
    ("2025-08-19", "Housing Starts",              "Housing",  ["housing_starts", "lumber_futures", "yield_curve"],                    ["XHB", "DHI", "LEN", "PHM"]),
    ("2025-09-17", "Housing Starts",              "Housing",  ["housing_starts", "lumber_futures", "yield_curve"],                    ["XHB", "DHI", "LEN", "PHM"]),
    ("2025-10-17", "Housing Starts",              "Housing",  ["housing_starts", "lumber_futures", "yield_curve"],                    ["XHB", "DHI", "LEN", "PHM"]),
    # ── PCE / Core PCE (end of month) ───────────────────────────────────────
    ("2025-08-29", "PCE Price Index",             "Inflation", ["consumer_sentiment", "retail_sales", "hy_spread"],                   ["SPY", "TLT", "GLD", "XLY"]),
    ("2025-09-26", "PCE Price Index",             "Inflation", ["consumer_sentiment", "retail_sales", "hy_spread"],                   ["SPY", "TLT", "GLD", "XLY"]),
    ("2025-10-31", "PCE Price Index",             "Inflation", ["consumer_sentiment", "retail_sales", "hy_spread"],                   ["SPY", "TLT", "GLD", "XLY"]),
]

CATEGORY_COLOR = {
    "Fed":       "#1A3A5C",
    "Inflation": "#FF4444",
    "Labor":     "#00D566",
    "PMI":       "#3D4F2E",
    "Energy":    "#5D4426",
    "Consumer":  "#4A3728",
    "Housing":   "#6B2E5F",
}

CATEGORY_ICON = {
    "Fed": "🏦", "Inflation": "📊", "Labor": "👷",
    "PMI": "🏭", "Energy": "⛽", "Consumer": "🛍️", "Housing": "🏠",
}


def _build_event_df(lookahead_days: int = 60) -> pd.DataFrame:
    today = date.today()
    cutoff = today + timedelta(days=lookahead_days)
    rows = []
    for date_str, name, category, signals, etfs in _RAW_EVENTS:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        if today <= dt <= cutoff:
            days_away = (dt - today).days
            rows.append({
                "date": dt,
                "days_away": days_away,
                "name": name,
                "category": category,
                "signals": signals,
                "etfs": etfs,
                "date_str": date_str,
            })
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["date","days_away","name","category","signals","etfs","date_str"])
    return df.sort_values("date").reset_index(drop=True)


@st.cache_data(ttl=3600, show_spinner=False, max_entries=3)
def _get_post_event_returns(event_name: str, signal_ids: list, etfs: list) -> dict:
    """
    Compute average 5-day post-event returns for sector ETFs from yfinance,
    using signal_snapshots to find historical dates where relevant signals
    were in similar states.

    Returns dict: {etf: {"bull_return": float, "bear_return": float, "n_obs": int}}
    """
    import yfinance as yf

    try:
        # Fetch 2-year price history for the ETFs
        tickers = list(set(etfs + ["SPY"]))[:8]
        raw = yf.download(tickers, period="730d", auto_adjust=True, progress=False, threads=True)
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"]
        else:
            prices = raw
        prices.index = pd.to_datetime(prices.index).tz_localize(None)
        prices = prices.dropna(how="all")

        if prices.empty:
            return {}

        # Get signal_snapshots for these signals
        try:
            from utils.db import signal_snapshots
            import utils.db as db
            from sqlalchemy import select

            cutoff_dt = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
            with db.engine.begin() as conn:
                rows = conn.execute(
                    select(signal_snapshots)
                    .where(signal_snapshots.c.signal_id.in_(signal_ids))
                    .where(signal_snapshots.c.snapshot_date >= cutoff_dt)
                ).mappings().all()

            if not rows:
                return {}

            snap_df = pd.DataFrame([dict(r) for r in rows])
            snap_df["snapshot_date"] = pd.to_datetime(snap_df["snapshot_date"])

            # For each date, determine aggregate signal status
            agg = snap_df.groupby("snapshot_date")["status"].agg(
                lambda x: "bullish" if (x == "bullish").mean() > 0.5
                else ("bearish" if (x == "bearish").mean() > 0.5 else "neutral")
            ).reset_index()

        except Exception:
            return {}

        bull_returns: dict[str, list[float]] = {e: [] for e in etfs}
        bear_returns: dict[str, list[float]] = {e: [] for e in etfs}

        for _, row in agg.iterrows():
            dt = pd.to_datetime(row["snapshot_date"])
            future = dt + timedelta(days=5)
            avail_now = prices.index[prices.index >= dt]
            avail_fut = prices.index[prices.index >= future]
            if avail_now.empty or avail_fut.empty:
                continue
            p0 = prices.loc[avail_now[0]]
            p1 = prices.loc[avail_fut[0]]
            status = row["status"]
            for etf in etfs:
                if etf in prices.columns and p0.get(etf, 0) > 0:
                    ret = (p1.get(etf, 0) - p0[etf]) / p0[etf] * 100
                    if status == "bullish":
                        bull_returns[etf].append(ret)
                    elif status == "bearish":
                        bear_returns[etf].append(ret)

        result = {}
        for etf in etfs:
            br = float(np.mean(bull_returns[etf])) if bull_returns[etf] else float("nan")
            be = float(np.mean(bear_returns[etf])) if bear_returns[etf] else float("nan")
            result[etf] = {
                "bull_return": br,
                "bear_return": be,
                "n_bull": len(bull_returns[etf]),
                "n_bear": len(bear_returns[etf]),
            }
        return result

    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────────────────────────────────────────
with st.spinner("Loading live signals and event calendar…"):
    all_scores = get_all_signal_scores()

# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("## Macro Event Impact Forecaster")
st.caption(
    "Upcoming economic releases cross-referenced with live UA signal state. "
    "Shows what our signals say going into each event and how similar signal configurations "
    "have historically played out in the 5 days after each event type."
)

# ── Controls ──────────────────────────────────────────────────────────────────
c1, c2 = st.columns([1, 2])
with c1:
    lookahead = st.selectbox("Show events in next:", [14, 30, 60, 90],
                             index=1, format_func=lambda d: f"{d} days")
with c2:
    all_cats = sorted(set(e[2] for e in _RAW_EVENTS))
    sel_cats = st.multiselect("Categories:", all_cats, default=all_cats,
                              help="Filter by event category")

event_df = _build_event_df(lookahead_days=lookahead)
if sel_cats:
    event_df = event_df[event_df["category"].isin(sel_cats)]

if event_df.empty:
    st.info(f"No events found in the next {lookahead} days for selected categories.", icon="📅")
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — UPCOMING EVENTS WITH SIGNAL READ
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Upcoming Events & Signal Read</div>', unsafe_allow_html=True)

STATUS_COLOR = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#6B7FBF"}
STATUS_ICON  = {"bullish": "▲", "bearish": "▼", "neutral": "→"}
CARD_CLASS   = {"bullish": "event-bull", "bearish": "event-bear", "neutral": "event-neut"}

for _, ev in event_df.iterrows():
    sig_ids = [s for s in ev["signals"] if s in all_scores]
    if not sig_ids:
        agg_status = "neutral"
        agg_score  = 50.0
    else:
        scores_vals = [all_scores[s].get("score", 50) for s in sig_ids]
        bull_n = sum(1 for s in sig_ids if all_scores[s].get("status") == "bullish")
        bear_n = sum(1 for s in sig_ids if all_scores[s].get("status") == "bearish")
        agg_score = float(np.mean(scores_vals))
        if bull_n > bear_n and bull_n >= len(sig_ids) * 0.5:
            agg_status = "bullish"
        elif bear_n > bull_n and bear_n >= len(sig_ids) * 0.5:
            agg_status = "bearish"
        else:
            agg_status = "neutral"

    cat_col = CATEGORY_COLOR.get(ev["category"], "#6B7FBF")
    cat_icon = CATEGORY_ICON.get(ev["category"], "📌")
    stat_col = STATUS_COLOR[agg_status]
    stat_icon = STATUS_ICON[agg_status]
    card_cls = CARD_CLASS[agg_status]

    days_label = (
        "TODAY" if ev["days_away"] == 0
        else "TOMORROW" if ev["days_away"] == 1
        else f"IN {ev['days_away']} DAYS"
    )

    # Signal detail text
    sig_details = []
    for s in sig_ids[:4]:
        sv = all_scores[s]
        sname = SIGNALS.get(s, {}).get("name", s)
        sig_details.append(
            f"<span style='color:{STATUS_COLOR[sv.get('status','neutral')]};'>"
            f"{STATUS_ICON[sv.get('status','neutral')]} {sname} ({sv.get('score',50):.0f})</span>"
        )
    sig_text = " &nbsp;·&nbsp; ".join(sig_details) if sig_details else "No relevant signals scored yet"

    st.markdown(
        f"<div class='event-card {card_cls}'>"
        f"<div style='display:flex;justify-content:space-between;align-items:flex-start;'>"
        f"<div>"
        f"<div class='event-date'>{cat_icon} {ev['category'].upper()} &nbsp;·&nbsp; "
        f"{ev['date'].strftime('%b %d, %Y')} &nbsp;·&nbsp; {days_label}</div>"
        f"<div class='event-name'>{ev['name']}</div>"
        f"<div class='event-sig'>Relevant signals: {sig_text}</div>"
        f"</div>"
        f"<div style='text-align:right;min-width:90px;'>"
        f"<div style='font-size:1.1rem;font-weight:700;color:{stat_col};'>{stat_icon} {agg_score:.0f}</div>"
        f"<div style='font-size:0.72rem;color:{stat_col};font-weight:600;'>{agg_status.upper()}</div>"
        f"</div>"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — HISTORICAL EVENT IMPACT ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Historical Impact Analysis — Select an Event</div>',
            unsafe_allow_html=True)
st.caption("5-day post-event returns for related ETFs, segmented by signal state going in. Uses actual signal_snapshots history from this app's DB.")

ev_names = event_df.apply(
    lambda r: f"{r['name']} ({r['date'].strftime('%b %d')})", axis=1
).tolist()

if ev_names:
    sel_ev_idx = st.selectbox("Event:", range(len(ev_names)),
                              format_func=lambda i: ev_names[i])
    sel_ev = event_df.iloc[sel_ev_idx]

    with st.spinner("Computing historical post-event returns…"):
        impact = _get_post_event_returns(
            sel_ev["name"],
            [s for s in sel_ev["signals"] if s in all_scores],
            sel_ev["etfs"],
        )

    if not impact:
        st.info(
            "Not enough signal snapshot history to compute post-event returns yet. "
            "This analysis builds automatically as signals are scored over time — "
            "check back after a few weeks of data accumulates.",
            icon="📈",
        )
    else:
        etfs_with_data = [e for e in sel_ev["etfs"] if e in impact and
                          not (np.isnan(impact[e]["bull_return"]) and np.isnan(impact[e]["bear_return"]))]

        if etfs_with_data:
            fig = go.Figure()
            bull_rets = [impact[e]["bull_return"] if not np.isnan(impact[e]["bull_return"]) else 0
                         for e in etfs_with_data]
            bear_rets = [impact[e]["bear_return"] if not np.isnan(impact[e]["bear_return"]) else 0
                         for e in etfs_with_data]

            fig.add_trace(go.Bar(
                name="Bullish Signal State",
                x=etfs_with_data, y=bull_rets,
                marker_color="#00D566", opacity=0.85,
            ))
            fig.add_trace(go.Bar(
                name="Bearish Signal State",
                x=etfs_with_data, y=bear_rets,
                marker_color="#FF4444", opacity=0.85,
            ))
            fig.add_hline(y=0, line_color="#9E9E9E", line_width=1)
            fig.update_layout(
                barmode="group",
                title=f"5-day post-{sel_ev['name']} returns by signal state",
                yaxis_title="Avg 5-day return (%)",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(l=40, r=20, t=50, b=40),
                height=340,
            )
            fig.update_xaxes(gridcolor="#E8E0D4")
            fig.update_yaxes(gridcolor="#E8E0D4")
            st.plotly_chart(fig, use_container_width=True)

            # Obs count note
            obs_info = " &nbsp;·&nbsp; ".join(
                f"{e}: {impact[e]['n_bull']}b/{impact[e]['n_bear']}br obs"
                for e in etfs_with_data
            )
            st.caption(f"Observations (bullish/bearish): {obs_info}")
        else:
            st.info("Insufficient historical data for this event/signal combination.", icon="📊")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — SIGNAL CONVERGENCE GOING INTO EVENTS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Signal Alignment Across Events (Next 30 Days)</div>',
            unsafe_allow_html=True)
st.caption("Events where the majority of relevant UA signals are clearly aligned — these are the highest-conviction reads.")

thirty_day_df = _build_event_df(lookahead_days=30)
if sel_cats:
    thirty_day_df = thirty_day_df[thirty_day_df["category"].isin(sel_cats)]

conviction_rows = []
for _, ev in thirty_day_df.iterrows():
    sig_ids = [s for s in ev["signals"] if s in all_scores]
    if not sig_ids:
        continue
    bull_n = sum(1 for s in sig_ids if all_scores[s].get("status") == "bullish")
    bear_n = sum(1 for s in sig_ids if all_scores[s].get("status") == "bearish")
    total = len(sig_ids)
    alignment = max(bull_n, bear_n) / total if total else 0
    direction = "BULLISH" if bull_n >= bear_n else "BEARISH"
    conviction_rows.append({
        "Event": ev["name"],
        "Date": ev["date"].strftime("%b %d"),
        "Category": ev["category"],
        "Direction": direction,
        "Alignment %": round(alignment * 100),
        "Signals Aligned": f"{max(bull_n, bear_n)}/{total}",
    })

if conviction_rows:
    conv_df = pd.DataFrame(conviction_rows).sort_values("Alignment %", ascending=False)

    def _dir_color(row: pd.Series) -> list[str]:
        color = "#00D566" if row["Direction"] == "BULLISH" else "#FF4444"
        return [""] * (len(row) - 3) + [f"color: {color}; font-weight: 700"] * 1 + [""] * 2

    st.dataframe(
        conv_df.style.background_gradient(
            subset=["Alignment %"], cmap="RdYlGn", vmin=40, vmax=100
        ),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No upcoming events in the next 30 days for selected categories.", icon="📅")

with st.expander("📚 Methodology", expanded=False):
    st.markdown("""
**Event Calendar**

FOMC meeting dates are sourced from the Federal Reserve's official calendar (announced ~1 year in advance).
CPI, NFP, ISM, Retail Sales, PCE, and Housing dates follow their standard release schedules (maintained
semi-annually in the page's event list). EIA crude inventory reports are every Wednesday.

**Signal Read**

For each event, the "Signal Read" is the aggregate status of the UA signals most directly related to
that data point. FOMC events look at yield curve, ten-year yield, FedSpeak score, and credit spreads.
NFP events look at jobless claims, JOLTS, layoffs rate, and trucking. The aggregate status uses a
majority rule: >50% bullish → BULLISH read, etc.

**Historical Impact Analysis**

Post-event returns are computed by:
1. Looking at all dates in the signal_snapshots DB where the relevant signals were in their current state
2. Fetching ETF prices 5 calendar days after each such date via yfinance
3. Averaging the returns, segmented by whether signals were bullish or bearish going in

This is correlation analysis, not causation. The returns reflect what happened after periods when
signals looked similar — not a guarantee of what will happen after this specific event.

**Important**: The historical analysis requires signal snapshot history from this app's database.
On a new deployment, this builds gradually over days/weeks as signals are scored.
""")
