"""
Page 31 — Supply Chain Signal Network
======================================
Tracks 6 signals across the full supply chain arc:

  GLOBAL PRESSURE
    ny_fed_gscpi      — NY Fed Global Supply Chain Pressure Index
                        (inverse: high pressure = bearish)

  INVENTORY CYCLE
    inventory_sales_ratio — Total Business Inventory/Sales Ratio (FRED ISRATIO)
                            (inverse: high ratio = excess inventory = bearish)

  DEMAND SIGNALS
    manufacturers_new_orders — Manufacturers' New Orders: Capital Goods
                                ex-Defense & Aircraft (FRED AMTMNO)
                                (high = rising capex demand = bullish)

  FREIGHT VOLUME
    ata_trucking       — ATA Trucking Tonnage Index (FRED TRUCKD11)
    rail_traffic       — AAR Rail Intermodal Traffic (FRED RAILFRTINTERMODAL)

  SHIPPING RATES
    shipping_index     — Breakwave Dry Bulk ETF (BDRY, via yfinance)

Regime logic:
  Score each signal 0 (bearish) or 1 (bullish) based on whether the most recent
  value is above its 12-month average (with inverse flag applied). Sum the scores.
  ≥4 bullish: BULLISH regime  |  ≤2 bullish: BEARISH regime  |  else: MIXED

DATA SOURCES
  • NY Fed GSCPI:          fetch_ny_fed_gscpi() — monthly Excel file, NY Fed website
  • ISRATIO / AMTMNO /
    TRUCKD11 /
    RAILFRTINTERMODAL:     fetch_fred() — FRED API (free key optional, works without)
  • BDRY:                  fetch_price() — yfinance (free, no key)
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.theme import inject_premium_css, PLOTLY_CONFIG
from utils.fetchers import fetch_fred, fetch_ny_fed_gscpi, fetch_price, _get_fred_key

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Supply Chain — Unstructured Alpha",
    page_icon="🔗",
    layout="wide",
)
render_header()
render_sidebar_base()
inject_premium_css()

render_page_header(
    "Supply Chain Signal Network",
    "6 signals tracking pressure, inventory cycles, and freight demand "
    "across the full supply chain.",
    icon="🔗",
)

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.block-container { padding-top: 0.5rem !important; max-width: 1200px !important; }

.sc-regime {
    border-radius: 10px; padding: 20px 28px; margin-bottom: 24px;
    font-family: Inter, sans-serif; text-align: center;
}
.sc-regime-bull  { background: #052210; color: #A8D5A2; border: 2px solid #00D566; }
.sc-regime-bear  { background: #1E0000; color: #F4A0A0; border: 2px solid #FF4444; }
.sc-regime-mixed { background: #1A1500; color: #D4C47A; border: 2px solid #F59E0B; }
.sc-regime-title { font-size: 1.5rem; font-weight: 700; letter-spacing: 0.04em; }
.sc-regime-sub   { font-size: 0.85rem; margin-top: 6px; opacity: 0.80; }

.sc-card {
    background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 8px; padding: 14px 16px; height: 100%;
}
.sc-card-title { font-family: Inter, sans-serif; font-size: 0.78rem; font-weight: 700;
    color: #A0AEC0; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px; }
.sc-card-value { font-family: Inter, sans-serif; font-size: 1.35rem; font-weight: 700;
    color: #E2E8F0; margin-bottom: 2px; }
.sc-card-trend { font-family: Inter, sans-serif; font-size: 0.78rem; }
.sc-card-bull   { color: #00D566; }
.sc-card-bear   { color: #FF4444; }
.sc-card-neutral { color: #A0AEC0; }

.sc-section {
    font-family: Inter, sans-serif; font-size: 0.68rem; font-weight: 700;
    letter-spacing: 0.14em; color: #6B7FBF; text-transform: uppercase;
    border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 4px;
    margin: 20px 0 12px 0;
}
.sc-badge {
    display: inline-block; font-size: 0.68rem; font-weight: 600;
    padding: 2px 8px; border-radius: 4px; margin-right: 6px;
}
.sc-badge-bull  { background: rgba(0,213,102,0.12); color: #00D566; border: 1px solid rgba(0,213,102,0.3); }
.sc-badge-bear  { background: rgba(255,68,68,0.12);  color: #FF4444; border: 1px solid rgba(255,68,68,0.3); }
.sc-badge-neutral { background: rgba(160,174,192,0.10); color: #A0AEC0; border: 1px solid rgba(160,174,192,0.25); }

.sc-tbl-row { display: flex; align-items: center; gap: 10px; padding: 7px 0;
    border-bottom: 1px solid rgba(255,255,255,0.05); font-family: Inter, sans-serif; }
.sc-tbl-ticker { font-size: 0.82rem; font-weight: 700; color: #E2E8F0; min-width: 52px; }
.sc-tbl-name   { font-size: 0.78rem; color: #A0AEC0; flex: 1; }
.sc-tbl-signal { font-size: 0.73rem; color: #6B7FBF; }
</style>
""", unsafe_allow_html=True)

# ── Date range ─────────────────────────────────────────────────────────────────
_TODAY = datetime.today()
_START = (_TODAY - timedelta(days=3 * 365)).strftime("%Y-%m-%d")
_END   = _TODAY.strftime("%Y-%m-%d")
_FRED_KEY = _get_fred_key()

# ── Signal definitions for this page ──────────────────────────────────────────
CHAIN_SIGNALS = [
    {
        "key":     "ny_fed_gscpi",
        "name":    "NY Fed GSCPI",
        "desc":    "Global Supply Chain Pressure Index (standard deviations from mean). "
                   "Lower = less pressure = bullish for supply chains.",
        "source":  "NY Fed",
        "source_url": "https://www.newyorkfed.org/research/policy/gscpi",
        "unit":    "Std Dev",
        "inverse": True,
        "color":   "#0D7A5F",
        "fill":    "rgba(13,122,95,0.10)",
        "freq":    "Monthly",
        "layer":   "Global Pressure",
        "fetch":   lambda: fetch_ny_fed_gscpi(_START, _END),
    },
    {
        "key":     "inventory_sales_ratio",
        "name":    "Inventory/Sales Ratio",
        "desc":    "Total Business Inventory-to-Sales Ratio (FRED ISRATIO). "
                   "Lower = lean inventories = restocking cycle ahead = bullish.",
        "source":  "FRED",
        "source_url": "https://fred.stlouisfed.org/series/ISRATIO",
        "unit":    "Months",
        "inverse": True,
        "color":   "#1A6B8A",
        "fill":    "rgba(26,107,138,0.10)",
        "freq":    "Monthly",
        "layer":   "Inventory Cycle",
        "fetch":   lambda: fetch_fred("ISRATIO", _START, _END, api_key=_FRED_KEY),
    },
    {
        "key":     "manufacturers_new_orders",
        "name":    "Manufacturers' New Orders",
        "desc":    "Capital Goods ex-Defense & Aircraft (FRED AMTMNO, $B SAAR). "
                   "Rising orders signal improving capex demand 2–3 months ahead.",
        "source":  "FRED",
        "source_url": "https://fred.stlouisfed.org/series/AMTMNO",
        "unit":    "$B SAAR",
        "inverse": False,
        "color":   "#2C6E49",
        "fill":    "rgba(44,110,73,0.10)",
        "freq":    "Monthly",
        "layer":   "Demand Orders",
        "fetch":   lambda: fetch_fred("AMTMNO", _START, _END, api_key=_FRED_KEY),
    },
    {
        "key":     "ata_trucking",
        "name":    "ATA Trucking Tonnage",
        "desc":    "ATA Trucking Tonnage Index (FRED TRUCKD11, 2015=100). "
                   "Covers ~70% of domestic freight. Leads economic data by 6–8 weeks.",
        "source":  "FRED",
        "source_url": "https://fred.stlouisfed.org/series/TRUCKD11",
        "unit":    "Index",
        "inverse": False,
        "color":   "#7C3AED",
        "fill":    "rgba(124,58,237,0.10)",
        "freq":    "Monthly",
        "layer":   "Freight Volume",
        "fetch":   lambda: fetch_fred("TRUCKD11", _START, _END, api_key=_FRED_KEY),
    },
    {
        "key":     "rail_traffic",
        "name":    "Rail Intermodal Traffic",
        "desc":    "AAR Intermodal Carloads (FRED RAILFRTINTERMODAL). "
                   "Container volumes signal import demand before official trade stats.",
        "source":  "FRED",
        "source_url": "https://fred.stlouisfed.org/series/RAILFRTINTERMODAL",
        "unit":    "K Carloads",
        "inverse": False,
        "color":   "#B45309",
        "fill":    "rgba(180,83,9,0.10)",
        "freq":    "Weekly",
        "layer":   "Freight Volume",
        "fetch":   lambda: fetch_fred("RAILFRTINTERMODAL", _START, _END, api_key=_FRED_KEY),
    },
    {
        "key":     "shipping_index",
        "name":    "Dry Bulk Shipping (BDRY)",
        "desc":    "Breakwave Dry Bulk Shipping ETF — proxy for Baltic Dry Index. "
                   "Rising rates reflect strengthening global commodity trade flows.",
        "source":  "yfinance",
        "source_url": "https://finance.yahoo.com/quote/BDRY",
        "unit":    "USD",
        "inverse": False,
        "color":   "#5D4037",
        "fill":    "rgba(93,64,55,0.10)",
        "freq":    "Daily",
        "layer":   "Shipping Rates",
        "fetch":   lambda: fetch_price("BDRY", _START, _END),
    },
]

# ── Ticker implications table ──────────────────────────────────────────────────
TICKERS = [
    ("CAT",  "Caterpillar Inc.",       ["all"],           "Equipment demand tracks new orders + freight"),
    ("DE",   "Deere & Company",        ["all"],           "Agricultural equipment — tracks full chain"),
    ("XLI",  "Industrial Select SPDR", ["all"],           "Broad industrial ETF — macro regime proxy"),
    ("JBHT", "J.B. Hunt Transport",    ["ata_trucking"],  "Pure-play trucking bellwether"),
    ("ODFL", "Old Dominion Freight",   ["ata_trucking"],  "LTL trucking — pricing power + volumes"),
    ("UPS",  "United Parcel Service",  ["ata_trucking", "rail_traffic"], "Parcel + ground freight"),
    ("FDX",  "FedEx Corporation",      ["ata_trucking", "shipping_index"], "Global freight barometer"),
    ("WHR",  "Whirlpool Corporation",  ["ny_fed_gscpi", "inventory_sales_ratio"], "Consumer durables — supply chain sensitive"),
    ("AMZN", "Amazon.com Inc.",        ["inventory_sales_ratio", "ata_trucking"], "Inventory cycle + last-mile freight"),
    ("WMT",  "Walmart Inc.",           ["inventory_sales_ratio"],    "Retail inventory cycle leader"),
    ("HON",  "Honeywell Intl.",        ["manufacturers_new_orders"], "Industrial automation + aerospace components"),
    ("ETN",  "Eaton Corporation",      ["manufacturers_new_orders"], "Power management capex play"),
    ("VALE", "Vale S.A.",              ["shipping_index"],            "Iron ore miner — shipping rate correlation"),
    ("BHP",  "BHP Group",              ["shipping_index"],            "Diversified miner — Baltic Dry proxy"),
]

# ── Fetch all signals ──────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False, max_entries=1)
def _load_all_signals(start: str, end: str, fred_key: str) -> dict[str, pd.Series]:
    """Fetch all 6 supply chain signals. Returns dict key → pd.Series."""
    results: dict[str, pd.Series] = {}
    for sig in CHAIN_SIGNALS:
        try:
            s = sig["fetch"]()
            results[sig["key"]] = s if isinstance(s, pd.Series) else pd.Series(dtype=float)
        except Exception:
            results[sig["key"]] = pd.Series(dtype=float)
    return results


with st.spinner("Loading supply chain signals…"):
    data = _load_all_signals(_START, _END, _FRED_KEY)

# ── Score each signal ──────────────────────────────────────────────────────────
def _score_signal(s: pd.Series, inverse: bool) -> tuple[str, float, float]:
    """
    Returns (status, latest_value, pct_change_vs_12m_avg).
    status: "bull" | "bear" | "neutral"
    """
    s = s.dropna()
    if len(s) < 2:
        return "neutral", float("nan"), float("nan")

    latest = float(s.iloc[-1])
    lookback = s.iloc[-min(52, len(s)):]   # up to 52 data points ≈ 1 year
    avg = float(lookback.mean())
    if avg == 0:
        return "neutral", latest, 0.0

    pct_vs_avg = (latest - avg) / abs(avg) * 100

    # Positive pct = above average (bullish for normal signals, bearish for inverse)
    raw_bull = pct_vs_avg > 0
    bull = (not inverse and raw_bull) or (inverse and not raw_bull)

    # Neutral band: within ±1% of 12m average = effectively flat
    if abs(pct_vs_avg) < 1.0:
        return "neutral", latest, pct_vs_avg
    return ("bull" if bull else "bear"), latest, pct_vs_avg


# Compute scores for all signals
signal_scores: dict[str, tuple[str, float, float]] = {}
for sig in CHAIN_SIGNALS:
    s = data.get(sig["key"], pd.Series(dtype=float))
    signal_scores[sig["key"]] = _score_signal(s, sig["inverse"])

bull_count = sum(1 for v in signal_scores.values() if v[0] == "bull")
bear_count = sum(1 for v in signal_scores.values() if v[0] == "bear")

if bull_count >= 4:
    regime = "BULLISH"
    regime_cls = "sc-regime-bull"
    regime_icon = "🟢"
    regime_sub = f"{bull_count}/6 signals indicate a healthy supply chain environment."
elif bear_count >= 4:
    regime = "BEARISH"
    regime_cls = "sc-regime-bear"
    regime_icon = "🔴"
    regime_sub = f"{bear_count}/6 signals indicate supply chain stress or contraction."
else:
    regime = "MIXED"
    regime_cls = "sc-regime-mixed"
    regime_icon = "🟡"
    regime_sub = (
        f"{bull_count} bullish, {bear_count} bearish — no clear directional alignment."
    )

# ── Regime banner ──────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="sc-regime {regime_cls}">
  <div class="sc-regime-title">{regime_icon} Supply Chain Regime: {regime}</div>
  <div class="sc-regime-sub">{regime_sub}</div>
</div>
""", unsafe_allow_html=True)

# ── Signal cards (2 rows × 3 cols) ────────────────────────────────────────────
st.markdown('<div class="sc-section">SIGNAL READINGS</div>', unsafe_allow_html=True)

cols_top = st.columns(3)
cols_bot = st.columns(3)
col_grid = cols_top + cols_bot

for i, sig in enumerate(CHAIN_SIGNALS):
    status, latest, pct = signal_scores[sig["key"]]
    s = data.get(sig["key"], pd.Series(dtype=float)).dropna()

    status_cls   = f"sc-card-{status}"
    badge_cls    = f"sc-badge-{status}"
    badge_label  = status.upper() if status != "neutral" else "NEUTRAL"
    trend_arrow  = "▲" if pct > 0 else "▼" if pct < 0 else "—"
    trend_label  = f"{trend_arrow} {abs(pct):.1f}% vs 12m avg" if not np.isnan(pct) else "—"
    latest_fmt   = f"{latest:,.2f}" if not np.isnan(latest) else "—"

    with col_grid[i]:
        # Spark chart
        fig = go.Figure()
        if len(s) >= 3:
            fig.add_trace(go.Scatter(
                x=s.index,
                y=s.values,
                mode="lines",
                line=dict(color=sig["color"], width=1.8),
                fill="tozeroy",
                fillcolor=sig["fill"],
                hovertemplate="%{y:.3f}<extra></extra>",
            ))
        fig.update_layout(
            height=80,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

        st.markdown(f"""
<div class="sc-card">
  <div class="sc-card-title">{sig["layer"]} &nbsp;·&nbsp; {sig["freq"]}</div>
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
    <span class="sc-card-value">{latest_fmt}</span>
    <span class="sc-badge {badge_cls}">{badge_label}</span>
  </div>
  <div class="sc-card-trend {status_cls}">{trend_label} &nbsp;·&nbsp; {sig["unit"]}</div>
  <div style="font-size:0.73rem;color:#718096;margin-top:6px;">{sig["name"]}</div>
</div>
""", unsafe_allow_html=True)

# ── Full signal charts ─────────────────────────────────────────────────────────
st.markdown('<div class="sc-section">SIGNAL CHARTS (3 YEARS)</div>', unsafe_allow_html=True)

tab_labels = [s["name"] for s in CHAIN_SIGNALS]
tabs = st.tabs(tab_labels)

for tab, sig in zip(tabs, CHAIN_SIGNALS):
    with tab:
        s = data.get(sig["key"], pd.Series(dtype=float)).dropna()
        status, latest, pct = signal_scores[sig["key"]]

        if len(s) < 3:
            st.info("Insufficient data for chart. Check API connectivity.")
        else:
            # 12m rolling average overlay
            freq_pts = 12 if sig["freq"] == "Monthly" else 52
            ma = s.rolling(window=min(freq_pts, len(s))).mean()

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=s.index, y=s.values,
                mode="lines",
                name=sig["name"],
                line=dict(color=sig["color"], width=2),
                fill="tozeroy",
                fillcolor=sig["color"].replace("#", "rgba(") + ",0.08)",
                hovertemplate=f"%{{x|%b %Y}}<br><b>%{{y:.3f}}</b> {sig['unit']}<extra></extra>",
            ))
            fig.add_trace(go.Scatter(
                x=ma.index, y=ma.values,
                mode="lines",
                name="12m Average",
                line=dict(color="#4A5568", width=1.2, dash="dot"),
                hovertemplate=f"%{{x|%b %Y}}<br>12m Avg: %{{y:.3f}}<extra></extra>",
            ))
            fig.update_layout(
                height=320,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(12,14,20,1)",
                font=dict(family="Inter, sans-serif", color="#A0AEC0", size=11),
                xaxis=dict(
                    gridcolor="rgba(255,255,255,0.04)",
                    tickformat="%b %Y",
                    tickfont=dict(size=10),
                ),
                yaxis=dict(
                    gridcolor="rgba(255,255,255,0.04)",
                    title=sig["unit"],
                    tickfont=dict(size=10),
                ),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=10), bgcolor="rgba(0,0,0,0)",
                ),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

        col_l, col_r = st.columns([3, 2])
        with col_l:
            st.caption(f"**{sig['name']}** · {sig['desc']}")
        with col_r:
            st.caption(
                f"Source: [{sig['source']}]({sig['source_url']}) · "
                f"Frequency: {sig['freq']} · "
                f"{'Inverse signal — higher value is bearish.' if sig['inverse'] else 'Direct signal — higher value is bullish.'}"
            )

# ── Ticker implications ────────────────────────────────────────────────────────
st.markdown('<div class="sc-section">TICKER IMPLICATIONS</div>', unsafe_allow_html=True)

st.caption(
    "Tickers most sensitive to the current supply chain regime. "
    "Signal mapping is based on documented fundamental relationships, "
    "not a backtest."
)

cols = st.columns(2)
half = len(TICKERS) // 2
for idx, (ticker, name, signals, rationale) in enumerate(TICKERS):
    col = cols[0] if idx < half else cols[1]
    with col:
        # Determine composite status for this ticker
        t_scores = []
        for sig_key in signals:
            if sig_key == "all":
                t_scores = [v[0] for v in signal_scores.values()]
                break
            if sig_key in signal_scores:
                t_scores.append(signal_scores[sig_key][0])

        bull_t = t_scores.count("bull")
        bear_t = t_scores.count("bear")
        if bull_t > bear_t:
            t_status = "bull"; t_badge = "sc-badge-bull"; t_lbl = "BULLISH"
        elif bear_t > bull_t:
            t_status = "bear"; t_badge = "sc-badge-bear"; t_lbl = "BEARISH"
        else:
            t_status = "neutral"; t_badge = "sc-badge-neutral"; t_lbl = "MIXED"

        sig_display = ", ".join(
            CHAIN_SIGNALS[[s["key"] for s in CHAIN_SIGNALS].index(k)]["name"]
            for k in ([c["key"] for c in CHAIN_SIGNALS] if signals == ["all"] else signals)
            if k in [s["key"] for s in CHAIN_SIGNALS]
        ) if signals != ["all"] else "All 6 signals"

        st.markdown(f"""
<div class="sc-tbl-row">
  <span class="sc-tbl-ticker">{ticker}</span>
  <span class="sc-tbl-name">{name}</span>
  <span class="sc-tbl-signal">{sig_display}</span>
  <span class="sc-badge {t_badge}">{t_lbl}</span>
</div>
""", unsafe_allow_html=True)

# ── How it works ───────────────────────────────────────────────────────────────
with st.expander("How the regime score is calculated", expanded=False):
    st.markdown("""
**Signal scoring (per signal)**

1. Fetch the most recent 3 years of data.
2. Compute the 12-month rolling average of the series.
3. Compare the latest value to that average:
   - **Direct signals** (trucking, rail, new orders, shipping): above average = bullish.
   - **Inverse signals** (GSCPI, inventory/sales ratio): above average = bearish.
4. Within ±1% of the 12-month average = **neutral** (no strong directional signal).

**Regime determination**

| Bullish signals | Regime |
|---|---|
| ≥ 4 of 6 | **BULLISH** — supply chain broadly constructive |
| ≤ 2 of 6 | **BEARISH** — supply chain stress or contraction |
| 3 of 6 | **MIXED** — no clear alignment |

**Limitations**

- GSCPI and ISRATIO are released monthly with 4–8 week lags; the "latest" reading reflects
  conditions from 1–2 months ago.
- Rail and trucking data also carry 3–6 week reporting lags.
- BDRY (shipping) is the only real-time daily signal.
- This page does not run a statistical backtest. Treat the regime reading as directional
  context, not a trading signal.
""")

# ── Data provenance ────────────────────────────────────────────────────────────
st.markdown('<div class="sc-section">DATA SOURCES</div>', unsafe_allow_html=True)

prov_cols = st.columns(3)
sources = [
    ("NY Fed GSCPI", "nyresearch.org", "https://www.newyorkfed.org/research/policy/gscpi",
     "Monthly Excel download. No API key required."),
    ("FRED (ISRATIO, AMTMNO, TRUCKD11, RAILFRTINTERMODAL)",
     "fred.stlouisfed.org", "https://fred.stlouisfed.org",
     "Free FRED API. Works without a key (rate-limited)."),
    ("yfinance (BDRY)", "finance.yahoo.com", "https://finance.yahoo.com/quote/BDRY",
     "Daily market data. No API key required."),
]
for i, (src, domain, url, note) in enumerate(sources):
    with prov_cols[i]:
        st.markdown(
            f"<div class='sc-card' style='padding:12px;'>"
            f"<div class='sc-card-title' style='margin-bottom:6px;'>{src}</div>"
            f"<div style='font-size:0.73rem;color:#718096;'>"
            f"<a href='{url}' target='_blank' style='color:#6B7FBF;'>{domain}</a><br>{note}"
            f"</div></div>",
            unsafe_allow_html=True,
        )
