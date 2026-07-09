"""
Page 25 — Market Heatmap
S&P 500 sector treemap colored by Unstructured Alpha Confluence Score.
Each tile = a sector; sub-tiles = individual tickers in that sector.
Green = bullish confluence, red = bearish.

PERFORMANCE NOTE:
  Previously called compute_full_ticker_score() for ~80 tickers (320+ API
  calls, 5-10 min first load). Now uses get_all_signal_scores() — the shared
  2h cache already warm from Signal Dashboard / home page — and derives ticker
  scores from sector scores + price momentum. First load is now <5 seconds.
"""

import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
import numpy as np

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.theme import (style_chart, BG_PAGE, BG_PLOT, TEXT_PRIMARY, TEXT_SECONDARY, BORDER_LIGHT,
                         inject_skeleton_css, skeleton_chart_block, skeleton_stat_row, source_badge)
from utils.signals_cache import get_all_signal_scores

st.set_page_config(page_title="Market Heatmap — UA", layout="wide")
render_header("Market Heatmap")
render_sidebar_base()

render_page_header(
    "Market Heatmap",
    "S&P 500 sectors and stocks colored by Confluence Score — where the machine sees strength today.",
    icon="🗺️",
)

# ── Sector → Tickers mapping ──────────────────────────────────────────────────
SECTOR_TICKERS = {
    "Technology":          ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMD", "AVGO", "ORCL"],
    "Financials":          ["JPM", "BAC", "GS", "MS", "BLK", "WFC", "C", "AXP"],
    "Healthcare":          ["JNJ", "UNH", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT"],
    "Consumer Discret.":   ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW"],
    "Industrials":         ["CAT", "BA", "GE", "HON", "UPS", "RTX", "LMT", "DE"],
    "Energy":              ["XOM", "CVX", "COP", "SLB", "EOG", "PSX", "VLO", "OXY"],
    "Communication Svcs":  ["GOOGL", "META", "NFLX", "DIS", "CMCSA", "T", "VZ", "ATVI"],
    "Consumer Staples":    ["PG", "KO", "PEP", "WMT", "COST", "PM", "MO", "MDLZ"],
    "Utilities":           ["NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "XEL"],
    "Real Estate":         ["AMT", "PLD", "CCI", "EQIX", "PSA", "SPG", "O", "DLR"],
    "Materials":           ["LIN", "APD", "SHW", "FCX", "NEM", "NUE", "PKG", "CF"],
}

SECTOR_ETFS = {
    "Technology": "XLK", "Financials": "XLF", "Healthcare": "XLV",
    "Consumer Discret.": "XLY", "Industrials": "XLI", "Energy": "XLE",
    "Communication Svcs": "XLC", "Consumer Staples": "XLP", "Utilities": "XLU",
    "Real Estate": "XLRE", "Materials": "XLB",
}

# ── Signal category → GICS sector mapping ─────────────────────────────────────
# Signals from signals_cache have a "category" field. We map each signal
# category to the sectors it most directly affects, with a weight.
# Sectors with no matching signals fall back to the composite macro score.
CATEGORY_SECTOR_MAP = {
    "macro":            ["Technology", "Financials", "Consumer Discret.", "Industrials",
                         "Consumer Staples", "Real Estate", "Communication Svcs", "Materials"],
    "energy":           ["Energy", "Utilities", "Industrials", "Materials"],
    "ai_infrastructure":["Technology", "Communication Svcs", "Industrials"],
    "nuclear":          ["Utilities", "Energy", "Industrials"],
    "financials":       ["Financials", "Real Estate"],
    "healthcare":       ["Healthcare"],
    "consumer":         ["Consumer Discret.", "Consumer Staples"],
    "industrials":      ["Industrials", "Materials", "Energy"],
}


@st.cache_data(ttl=1800, max_entries=1, show_spinner=False)
def _compute_sector_scores_from_signals(_v: int = 1) -> dict[str, float]:
    """
    Derive a 0-100 sector score from the shared signal cache.
    No per-ticker API calls — uses the already-warm 2h signal cache.

    Algorithm:
      For each sector, collect all signals that map to it via
      CATEGORY_SECTOR_MAP. Average their scores. Sectors with
      zero mapped signals fall back to the overall macro composite.
    """
    all_sv = get_all_signal_scores(_v)

    # Bucket signal scores by sector
    sector_buckets: dict[str, list[float]] = {s: [] for s in SECTOR_TICKERS}

    for sig_id, sv in all_sv.items():
        if sv.get("error"):
            continue
        cat   = sv.get("category", "macro")
        score = sv.get("score", 50.0)
        for sector in CATEGORY_SECTOR_MAP.get(cat, []):
            if sector in sector_buckets:
                sector_buckets[sector].append(score)

    # Fallback: overall macro average for sectors with no direct signals
    macro_scores = [
        sv.get("score", 50.0)
        for sv in all_sv.values()
        if not sv.get("error") and sv.get("category") == "macro"
    ]
    macro_avg = float(np.mean(macro_scores)) if macro_scores else 50.0

    result = {}
    for sector, bucket in sector_buckets.items():
        result[sector] = float(np.mean(bucket)) if bucket else macro_avg

    return result


@st.cache_data(ttl=300, max_entries=1, show_spinner=False)
def _fetch_prices(tickers_tuple: tuple) -> dict:
    """
    Batch-fetch 5-day close prices for all tickers + ETFs.
    Returns {sym: {price, chg_1d, chg_5d}} — chg_5d used for momentum adjustment.
    5-min TTL; single yf.download call for all ~90 symbols.
    """
    tickers_list = list(tickers_tuple)
    data = {}
    try:
        raw = yf.download(
            tickers_list, period="5d", auto_adjust=True,
            progress=False, threads=True,
        )["Close"]
        # yfinance returns a DataFrame for multi-ticker, Series for single
        if hasattr(raw, "columns"):
            for sym in tickers_list:
                try:
                    if sym not in raw.columns:
                        continue
                    series = raw[sym].dropna()
                    if len(series) < 2:
                        continue
                    price  = float(series.iloc[-1])
                    prev1  = float(series.iloc[-2])
                    prev5  = float(series.iloc[0])
                    chg_1d = (price - prev1) / prev1 * 100 if prev1 > 0 else 0.0
                    chg_5d = (price - prev5) / prev5 * 100 if prev5 > 0 else 0.0
                    data[sym] = {"price": price, "chg": chg_1d, "chg_5d": chg_5d}
                except Exception:
                    pass
        else:
            # Single ticker edge case
            sym = tickers_list[0]
            series = raw.dropna()
            if len(series) >= 2:
                price  = float(series.iloc[-1])
                prev1  = float(series.iloc[-2])
                chg_1d = (price - prev1) / prev1 * 100 if prev1 > 0 else 0.0
                data[sym] = {"price": price, "chg": chg_1d, "chg_5d": chg_1d}
    except Exception:
        pass
    return data


def _ticker_score(sector_score: float, chg_5d: float) -> float:
    """
    Derive an individual ticker score from its sector's signal score
    plus a momentum adjustment based on 5-day price return.

    Adjustment: ±0.8 pts per 1% of 5-day return, capped at ±12 pts.
    This gives visible differentiation within a sector without requiring
    per-ticker API calls.
    """
    adj = max(-12.0, min(12.0, chg_5d * 0.8))
    return max(0.0, min(100.0, sector_score + adj))


def _score_to_color(score: float) -> str:
    """Map 0-100 score to hex color on a red→gray→green scale."""
    if score >= 75:  return "#00D566"
    if score >= 65:  return "#00A847"
    if score >= 55:  return "#34D399"
    if score >= 45:  return "#6B7FBF"
    if score >= 35:  return "#CC3333"
    if score >= 25:  return "#FF4444"
    return "#FF2222"


# ── Load data ─────────────────────────────────────────────────────────────────
inject_skeleton_css()
cache_v = st.session_state.get("cache_v", 1)

_sk_ph = st.empty()
_sk_ph.markdown(
    skeleton_stat_row(4) + skeleton_chart_block(height=560, title_lines=0),
    unsafe_allow_html=True,
)
sector_scores = _compute_sector_scores_from_signals(cache_v)

# Collect all unique tickers + ETFs for single batch price fetch
all_tickers = list({t for tickers in SECTOR_TICKERS.values() for t in tickers})
all_etfs    = list(SECTOR_ETFS.values())
all_syms    = tuple(sorted(set(all_tickers + all_etfs)))

prices = _fetch_prices(all_syms)
_sk_ph.empty()

# ── View mode ─────────────────────────────────────────────────────────────────
view_mode = st.segmented_control(
    "View",
    options=["Sectors", "Individual Stocks", "Both"],
    default="Both",
    key="heatmap_view",
)

# ── Build treemap data ────────────────────────────────────────────────────────
labels, parents, values, colors, customdata = [], [], [], [], []

labels.append("S&P 500")
parents.append("")
values.append(0)
colors.append("#12151E")
customdata.append(("", 0, 0, "", ""))

for sector, tickers in SECTOR_TICKERS.items():
    sec_score = sector_scores.get(sector, 50.0)
    sec_case  = "BULL" if sec_score >= 65 else ("BEAR" if sec_score <= 35 else "NEUTRAL")
    etf_sym   = SECTOR_ETFS.get(sector, "")
    etf_chg   = prices.get(etf_sym, {}).get("chg", 0.0)

    labels.append(sector)
    parents.append("S&P 500")
    values.append(len(tickers) * 100)
    colors.append(_score_to_color(sec_score))
    customdata.append((sector, round(sec_score, 1), round(etf_chg, 2), sec_case, etf_sym))

    if view_mode in ("Individual Stocks", "Both"):
        for sym in tickers:
            chg_5d = prices.get(sym, {}).get("chg_5d", 0.0)
            price  = prices.get(sym, {}).get("price", 0.0)
            chg_1d = prices.get(sym, {}).get("chg", 0.0)
            sc     = _ticker_score(sec_score, chg_5d)
            case   = "BULL" if sc >= 65 else ("BEAR" if sc <= 35 else "NEUTRAL")

            labels.append(sym)
            parents.append(sector)
            values.append(100)
            colors.append(_score_to_color(sc))
            customdata.append((sym, round(sc, 1), round(chg_1d, 2), case, f"${price:,.2f}" if price > 0 else "—"))

# ── Plotly treemap ────────────────────────────────────────────────────────────
fig = go.Figure(go.Treemap(
    labels=labels,
    parents=parents,
    values=values,
    marker=dict(
        colors=colors,
        line=dict(width=2, color="#0B0D12"),
    ),
    customdata=customdata,
    hovertemplate=(
        "<b>%{label}</b><br>"
        "Confluence: <b>%{customdata[1]}/100</b><br>"
        "Signal Case: %{customdata[3]}<br>"
        "Price: %{customdata[4]}<br>"
        "1-Day Δ: %{customdata[2]:+.2f}%<br>"
        "<extra></extra>"
    ),
    texttemplate=(
        "<b>%{label}</b><br>"
        "<span style='font-size:11px;'>%{customdata[1]}</span>"
    ),
    textfont=dict(family="Inter, sans-serif", size=13, color="#E8EEFF"),
    root_color="#0B0D12",
    tiling=dict(packing="squarify"),
    pathbar=dict(visible=True, thickness=20,
                 textfont=dict(family="Inter,sans-serif", size=11, color="#8892AA")),
))

fig.update_layout(
    height=620,
    paper_bgcolor=BG_PAGE,
    font=dict(family="Inter, sans-serif", color=TEXT_PRIMARY),
    margin=dict(l=0, r=0, t=8, b=0),
)

st.plotly_chart(fig, use_container_width=True,
                config={"scrollZoom": True, "doubleClick": "reset", "displayModeBar": False})
st.markdown(
    f"&nbsp; {source_badge('yfinance', 'Market cap · daily close')} "
    f"&nbsp; {source_badge('ua', 'Confluence Score · UA internal')}",
    unsafe_allow_html=True,
)

# ── Sector score table ─────────────────────────────────────────────────────────
st.markdown('<div class="section-header">SECTOR CONFLUENCE SCORES</div>', unsafe_allow_html=True)

sector_rows = []
for sector, tickers in SECTOR_TICKERS.items():
    sec_score  = sector_scores.get(sector, 50.0)
    sec_case   = "BULL" if sec_score >= 65 else ("BEAR" if sec_score <= 35 else "NEUTRAL")
    etf_sym    = SECTOR_ETFS.get(sector, "")
    etf_chg    = prices.get(etf_sym, {}).get("chg", 0.0)

    # Bull/bear counts using per-ticker derived scores
    ticker_scores = [
        _ticker_score(sec_score, prices.get(t, {}).get("chg_5d", 0.0))
        for t in tickers
    ]
    bull_ct = sum(1 for s in ticker_scores if s >= 65)
    bear_ct = sum(1 for s in ticker_scores if s <= 35)

    col     = "#00D566" if sec_case == "BULL" else ("#FF4444" if sec_case == "BEAR" else "#6B7FBF")
    arrow   = "▲" if etf_chg >= 0 else "▼"
    chg_col = "#00D566" if etf_chg >= 0 else "#FF4444"

    sector_rows.append(
        f'<tr style="border-bottom:1px solid rgba(255,255,255,0.04);">'
        f'<td style="padding:8px 12px;color:#E8EEFF;font-weight:600;">{sector}</td>'
        f'<td style="padding:8px 12px;text-align:center;">'
        f'<span style="font-size:1.1rem;font-weight:800;color:{col};">{sec_score:.0f}</span>'
        f'<span style="font-size:0.68rem;color:#6B7FBF;"> /100</span></td>'
        f'<td style="padding:8px 12px;text-align:center;color:{col};font-weight:700;">{sec_case}</td>'
        f'<td style="padding:8px 12px;text-align:center;color:{chg_col};font-weight:600;">'
        f'{arrow} {abs(etf_chg):.2f}%</td>'
        f'<td style="padding:8px 12px;text-align:center;color:#00D566;">{bull_ct}</td>'
        f'<td style="padding:8px 12px;text-align:center;color:#FF4444;">{bear_ct}</td>'
        f'</tr>'
    )

st.markdown(f"""
<table style="width:100%;border-collapse:collapse;font-family:Inter,sans-serif;font-size:0.83rem;">
  <thead>
    <tr style="border-bottom:1px solid rgba(0,213,102,0.2);">
      <th style="padding:9px 12px;text-align:left;color:#00D566;font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">Sector</th>
      <th style="padding:9px 12px;text-align:center;color:#00D566;font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">Score</th>
      <th style="padding:9px 12px;text-align:center;color:#00D566;font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">Case</th>
      <th style="padding:9px 12px;text-align:center;color:#00D566;font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">ETF 1D</th>
      <th style="padding:9px 12px;text-align:center;color:#00D566;font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">▲ Bull</th>
      <th style="padding:9px 12px;text-align:center;color:#00D566;font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;">▼ Bear</th>
    </tr>
  </thead>
  <tbody>{''.join(sector_rows)}</tbody>
</table>
""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Methodology note ──────────────────────────────────────────────────────────
st.markdown("""
<div style="background:rgba(124,58,237,0.07);border:1px solid rgba(124,58,237,0.2);
            border-radius:10px;padding:12px 16px;font-family:Inter,sans-serif;
            font-size:0.76rem;color:#8892AA;">
  <b style="color:#A78BFA;">How sector scores are computed:</b>
  Each sector score is derived from the 38 Unstructured Alpha macro signals
  most relevant to that sector's fundamentals (energy signals → Energy/Utilities;
  credit/financials signals → Financials/Real Estate; consumer signals →
  Consumer sectors; etc.). Individual ticker scores add a ±12pt price-momentum
  adjustment based on 5-day relative return.
  Prices update every 5 min · Scores update every 30 min.
  <b style="color:#F59E0B;">NOT investment advice.</b>
</div>
""", unsafe_allow_html=True)
