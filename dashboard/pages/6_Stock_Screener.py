"""
Page 6 — Stock Screener
Filter and rank every ticker in the Unstructured Alpha universe by confluence
score, sector, signal direction, and signal strength. Click any row to jump to
the Ticker Deep Dive, or enter any ticker symbol for a quick analysis.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from utils.config import SIGNALS, TICKERS
from utils.fetchers import fetch_live_quote, fetch_signal_series
from utils.analysis import compute_confluence, score_signal
from utils.header import render_header, render_sidebar_base, render_synthetic_data_banner
from utils.quotes import get_batch_quotes
from utils.signals_cache import get_all_signal_scores

st.set_page_config(page_title="Stock Screener — UA", layout="wide")
render_header("Stock Screener")

render_sidebar_base()

st.caption(
    "Confluence Score ranks tickers by current signal agreement, not a validated return forecast — "
    "see About → Methodology for the backtest behind that distinction."
)

END   = datetime.now().strftime("%Y-%m-%d")
START = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

STATUS_COLOR = {"bullish": "#1B5E20", "bearish": "#7B1010", "neutral": "#8B7355", "insufficient_data": "#9E9E8E"}
STATUS_SYM   = {"bullish": "▲", "bearish": "▼", "neutral": "●", "insufficient_data": "○"}


# ── Quick Analyze Any Ticker ──────────────────────────────────────────────────
st.markdown('<div class="section-header">QUICK TICKER ANALYSIS</div>', unsafe_allow_html=True)
st.caption("Analyze any publicly traded stock — not just our universe. Enter a ticker to score it against the macro signals most relevant to its sector.")

qa_col1, qa_col2 = st.columns([2, 5])
with qa_col1:
    custom_ticker = st.text_input(
        "Enter any ticker symbol",
        placeholder="e.g. TSLA, MSFT, META, BRK-B",
        key="quick_ticker",
        label_visibility="collapsed",
    ).strip().upper()

with qa_col2:
    run_quick = st.button("Analyze Ticker", type="primary", key="run_quick_btn")

if custom_ticker and run_quick:
    with st.spinner(f"Analyzing {custom_ticker}…"):
        try:
            import yfinance as yf
            t = yf.Ticker(custom_ticker)
            info = t.info or {}
            hist = t.history(period="1y")

            if hist.empty or "Close" not in hist.columns:
                st.error(f"No price data found for **{custom_ticker}**. Check the ticker symbol and try again.")
            else:
                close = hist["Close"].dropna()
                last  = float(close.iloc[-1])
                prev  = float(close.iloc[-2]) if len(close) > 1 else last
                yr_start = float(close.iloc[0])
                chg_1d   = (last - prev) / prev * 100
                chg_1y   = (last - yr_start) / yr_start * 100

                company_name = info.get("longName") or info.get("shortName") or custom_ticker
                sector_raw   = info.get("sector", "Unknown")

                # Map yfinance sector to our signal set
                SECTOR_SIGNAL_MAP = {
                    "Technology":              ["hyperscaler_capex", "semiconductor_etf", "ten_year_yield", "hy_spread", "vix"],
                    "Energy":                  ["crude_oil", "crude_inventories", "natural_gas", "gas_storage", "dollar_index"],
                    "Financial Services":      ["yield_curve", "hy_spread", "ten_year_yield", "vix", "bank_lending_standards", "credit_card_delinquency"],
                    "Healthcare":              ["jobless_claims", "consumer_sentiment", "hy_spread", "ten_year_yield", "fda_approval_velocity"],
                    "Consumer Cyclical":       ["retail_sales", "consumer_sentiment", "jobless_claims", "ata_trucking", "retail_job_openings", "ecommerce_share"],
                    "Consumer Defensive":      ["retail_sales", "food_cpi", "jobless_claims", "consumer_sentiment", "retail_job_openings"],
                    "Industrials":             ["ism_pmi", "ata_trucking", "rail_traffic", "durable_goods", "hy_spread", "construction_spending"],
                    "Basic Materials":         ["copper", "dollar_index", "ism_pmi", "crude_oil", "shipping_index"],
                    "Utilities":               ["ten_year_yield", "natural_gas", "uranium_proxy", "power_demand_growth", "vix"],
                    "Real Estate":             ["ten_year_yield", "housing_starts", "hy_spread", "vix"],
                    "Communication Services":  ["hyperscaler_capex", "jobless_claims", "ten_year_yield", "hy_spread"],
                }
                sig_ids = SECTOR_SIGNAL_MAP.get(sector_raw, ["ata_trucking", "hy_spread", "ten_year_yield", "vix", "yield_curve"])

                # Score the mapped signals
                ticker_scores = {}
                for sid in sig_ids:
                    cfg = SIGNALS.get(sid)
                    if not cfg:
                        continue
                    try:
                        s = fetch_signal_series(cfg, START, END)
                        ticker_scores[sid] = score_signal(s, inverse=cfg.get("inverse", False))
                    except Exception:
                        ticker_scores[sid] = {"score": 50, "status": "neutral"}

                conf = compute_confluence(ticker_scores)

                # Display result
                score_color = "#1B5E20" if conf["overall_score"] >= 65 else ("#7B1010" if conf["overall_score"] <= 35 else "#8B7355")
                st.markdown(f"""
                <div style="background:#F0EBE1;border-radius:8px;padding:20px 24px;border:1px solid #D4C9B0;
                            border-left:5px solid {score_color};font-family:Georgia,serif;margin:10px 0;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">
                        <div>
                            <div style="font-size:1.2rem;font-weight:700;color:#1A1612;">{company_name} ({custom_ticker})</div>
                            <div style="font-size:0.80rem;color:#8B7355;margin-top:2px;">{sector_raw} &nbsp;·&nbsp; ${last:,.2f} &nbsp;·&nbsp; 1D: {chg_1d:+.2f}% &nbsp;·&nbsp; 1Y: {chg_1y:+.1f}%</div>
                        </div>
                        <div style="text-align:center;">
                            <div style="font-size:0.70rem;color:#8B7355;text-transform:uppercase;letter-spacing:0.06em;">Confluence Score</div>
                            <div style="font-size:2.2rem;font-weight:700;color:{score_color};">{conf['overall_score']:.0f}</div>
                            <div style="font-size:0.78rem;color:{score_color};">{conf['case']} · {conf['conviction']}</div>
                        </div>
                    </div>
                    <div style="margin-top:14px;font-size:0.80rem;color:#6B6560;">
                        Based on {len(ticker_scores)} macro signals mapped to {sector_raw} sector.
                        &nbsp;·&nbsp; {conf['bull_count']} Bullish &nbsp;·&nbsp; {conf['bear_count']} Bearish &nbsp;·&nbsp;
                        {len(ticker_scores) - conf['bull_count'] - conf['bear_count']} Neutral
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if custom_ticker in TICKERS:
                    st.success(f"{custom_ticker} is in our full universe — see the full deep dive on the Ticker Deep Dive page.")
                else:
                    st.info(
                        f"{custom_ticker} is not in our tracked universe. "
                        "This quick score uses sector-mapped signals as a proxy. "
                        "For the deepest analysis, use the Ticker Deep Dive page with a custom ticker."
                    )

        except Exception as ex:
            st.error(f"Could not analyze {custom_ticker}: {ex}")

st.divider()


# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Screener Filters")

    # Text search
    search_text = st.text_input(
        "Search ticker or company", placeholder="e.g. NVDA, Goldman, Energy",
        key="scr_search",
    ).strip().lower()

    # Sector filter
    all_sectors = sorted(set(v.get("sector", "Other") for v in TICKERS.values() if v.get("sector")))
    sel_sectors = st.multiselect("Sectors", all_sectors, default=all_sectors, key="scr_sectors")

    # Bias filter
    bias_opts = ["All", "Bullish only", "Bearish only", "Neutral only"]
    bias_sel  = st.selectbox("Signal Bias", bias_opts, key="scr_bias")

    # Min PCS weight
    min_pcs = st.slider("Min signal PCS (quality filter)", 1, 10, 5, key="scr_pcs")

    # Score range
    score_min, score_max = st.slider("Confluence score range", 0, 100, (0, 100), key="scr_score")

    st.divider()
    st.caption("Scores update hourly. Add a FRED API key in Setup for live macro signals.")
    st.caption("Click any ticker row, then use the **Ticker Deep Dive** page for full signal breakdown.")


# ── Load signals once (shared cross-page cache) ───────────────────────────────
# load_all_signal_scores() has been replaced by get_all_signal_scores() from
# utils.signals_cache — same data, shared TTL=2h cache with home page, Signal
# Dashboard, Today's Brief, and Sector Map.  No local fetch loop needed.


@st.cache_data(ttl=1800, show_spinner=False)
def load_all_ticker_momentum() -> dict:
    """
    Batch-download 1-year closes for the entire universe and compute a
    price-momentum score (0-100) for each ticker.

    Blends:
      - 1-year return  (60% weight)
      - 1-month return (40% weight)
    Then maps that blended return to 0-100 via a sigmoid-like clip so that
    ±30% maps to roughly 75 / 25.
    """
    tickers_list = list(TICKERS.keys())
    momentum = {}
    try:
        raw = yf.download(
            tickers_list,
            period="1y",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        for tkr in tickers_list:
            try:
                col = closes[tkr] if tkr in closes.columns else pd.Series(dtype=float)
                col = col.dropna()
                if len(col) < 10:
                    momentum[tkr] = 50.0
                    continue
                ret_1y = (col.iloc[-1] / col.iloc[0]) - 1 if len(col) >= 200 else 0.0
                ret_1m = (col.iloc[-1] / col.iloc[-22]) - 1 if len(col) >= 22 else 0.0
                blended = ret_1y * 0.6 + ret_1m * 0.4
                # Map: +30% → ~75, -30% → ~25, 0% → 50
                score = float(np.clip(50.0 + blended * 83.3, 5.0, 95.0))
                momentum[tkr] = round(score, 1)
            except Exception:
                momentum[tkr] = 50.0
    except Exception:
        for tkr in tickers_list:
            momentum[tkr] = 50.0
    return momentum


def _ticker_confluence(ticker: str, sig_ids: list[str], all_scores: dict, momentum_cache: dict) -> dict:
    """
    Build a PCS-weighted macro confluence score for a single ticker,
    then blend it 70/30 with that ticker's price-momentum score.
    Returns a dict compatible with compute_confluence output but with
    an `overall_score` that is genuinely ticker-specific.
    """
    # PCS weights — heavier signals carry more influence
    weights = {sid: SIGNALS[sid].get("pcs", 5) / 10.0 for sid in sig_ids if sid in SIGNALS}
    ticker_scores = {sid: all_scores.get(sid, {"score": 50, "status": "neutral"}) for sid in sig_ids}
    conf = compute_confluence(ticker_scores, weights=weights)

    macro_score = conf["overall_score"]
    mom_score   = momentum_cache.get(ticker, 50.0)

    blended = macro_score * 0.70 + mom_score * 0.30
    conf["overall_score"] = round(blended, 1)

    # Recompute case/conviction from blended score
    if blended >= 65:
        conf["case"] = "BULL"
    elif blended <= 35:
        conf["case"] = "BEAR"
    else:
        conf["case"] = "NEUTRAL" if abs(conf["bull_count"] - conf["bear_count"]) <= 1 else "MIXED"

    n = len(ticker_scores)
    agreement = max(conf["bull_count"], conf["bear_count"]) / n if n else 0
    conf["conviction"] = (
        "Very High" if agreement >= 0.80 else
        "High"      if agreement >= 0.60 else
        "Moderate"  if agreement >= 0.45 else
        "Low"
    )
    return conf


# ── Build screener table ──────────────────────────────────────────────────────
st.markdown('<div class="section-header">ALTERNATIVE DATA SCREENER</div>', unsafe_allow_html=True)
st.caption(
    "Every ticker in the Unstructured Alpha universe ranked by alternative data confluence score. "
    "Score = 70% macro signal confluence (PCS-weighted) + 30% price momentum. "
    "Click any row to open Ticker Deep Dive for full signal breakdown."
)

with st.spinner("Loading signals and price momentum…"):
    all_scores       = get_all_signal_scores()
    _momentum_cache  = load_all_ticker_momentum()

render_synthetic_data_banner(
    sum(1 for sv in all_scores.values() if sv.get("is_synthetic")),
    len(all_scores),
)

rows = []
for ticker, tmeta in TICKERS.items():
    sector = tmeta.get("sector", "Other")

    # Text search filter
    if search_text:
        company_lower = tmeta.get("name", "").lower()
        if search_text not in ticker.lower() and search_text not in company_lower:
            continue

    if sel_sectors and sector not in sel_sectors:
        continue

    sig_ids = tmeta.get("signals", list(SIGNALS.keys()))
    sig_ids = [s for s in sig_ids if SIGNALS.get(s, {}).get("pcs", 0) >= min_pcs]

    conf = _ticker_confluence(ticker, sig_ids, all_scores, _momentum_cache)

    overall = conf["overall_score"]
    case    = conf["case"]
    conv    = conf["conviction"]

    if bias_sel == "Bullish only"  and case != "BULL":  continue
    if bias_sel == "Bearish only"  and case != "BEAR":  continue
    if bias_sel == "Neutral only"  and case not in ("NEUTRAL", "MIXED"): continue
    if not (score_min <= overall <= score_max):         continue

    rows.append({
        "Ticker":      ticker,
        "Company":     tmeta.get("name", ticker),
        "Sector":      sector,
        "Score":       round(overall, 1),
        "Case":        case,
        "Conviction":  conv,
        "Bull Sigs":   conf["bull_count"],
        "Bear Sigs":   conf["bear_count"],
        "Signals":     len(sig_ids),
    })

if not rows:
    st.info("No tickers match the current filters. Try broadening your selection.")
    st.stop()

screen_df = pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)

# ── Price + daily % change ───────────────────────────────────────────────────
# Fetched AFTER filtering, not for the full ~80-ticker universe up front --
# get_batch_quotes() is cached (utils/quotes.py, 15 min), but there's no
# reason to pay for quotes on tickers the current filters already excluded.
with st.spinner(f"Loading live prices for {len(screen_df)} ticker(s)…"):
    _quotes = get_batch_quotes(list(screen_df["Ticker"]))


def _quote_price(ticker: str) -> float | None:
    return _quotes.get(ticker, {}).get("last")


def _quote_chg_1d(ticker: str) -> float | None:
    return _quotes.get(ticker, {}).get("chg_1d_pct")


screen_df["Price"] = screen_df["Ticker"].map(_quote_price)
screen_df["1D %"] = screen_df["Ticker"].map(_quote_chg_1d)

# ── Summary stats ─────────────────────────────────────────────────────────────
tot    = len(screen_df)
n_bull = (screen_df["Case"] == "BULL").sum()
n_bear = (screen_df["Case"] == "BEAR").sum()
n_neut = tot - n_bull - n_bear
avg_scr = screen_df["Score"].mean()

s1, s2, s3, s4, s5 = st.columns(5)
s1.metric("Tickers Screened", tot)
s2.metric("Bullish", n_bull, delta=f"{n_bull/tot*100:.0f}%")
s3.metric("Bearish", n_bear, delta=f"-{n_bear/tot*100:.0f}%")
s4.metric("Neutral", n_neut)
s5.metric("Avg Score", f"{avg_scr:.1f}/100")

st.markdown("")

# ── Distribution chart ────────────────────────────────────────────────────────
fig_dist = go.Figure(go.Histogram(
    x=screen_df["Score"], nbinsx=20,
    marker_color="#1C2B4A", marker_line=dict(color="#FAF7F0", width=0.5),
    hovertemplate="Score %{x:.0f}: %{y} tickers<extra></extra>",
))
fig_dist.add_vline(x=65, line=dict(color="#1B5E20", dash="dot", width=1.5),
                   annotation_text="Bull threshold", annotation_font_color="#1B5E20")
fig_dist.add_vline(x=35, line=dict(color="#7B1010", dash="dot", width=1.5),
                   annotation_text="Bear threshold", annotation_font_color="#7B1010")
fig_dist.update_layout(
    height=160, paper_bgcolor="#FAF7F0", plot_bgcolor="#FFFFFF",
    xaxis=dict(showgrid=False, tickfont=dict(color="#6B6560"), title="Confluence Score"),
    yaxis=dict(showgrid=True, gridcolor="#E8E0CE", tickfont=dict(color="#6B6560"), title="# Tickers"),
    margin=dict(l=0, r=0, t=10, b=0),
)
st.plotly_chart(fig_dist, use_container_width=True)

# ── Main screener table ───────────────────────────────────────────────────────
st.markdown('<div class="section-header">SCREENER RESULTS</div>', unsafe_allow_html=True)

screen_df["Signal"] = screen_df["Case"].map({"BULL": "▲ BULL", "BEAR": "▼ BEAR"}).fillna("● " + screen_df["Case"])

display_df = screen_df[[
    "Ticker", "Company", "Sector", "Price", "1D %", "Score", "Signal",
    "Conviction", "Bull Sigs", "Bear Sigs", "Signals"
]].copy()

event = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "Ticker":     st.column_config.TextColumn("Ticker", width="small"),
        "Company":    st.column_config.TextColumn("Company", width="medium"),
        "Sector":     st.column_config.TextColumn("Sector", width="small"),
        "Price":      st.column_config.NumberColumn("Price", format="$%.2f", width="small"),
        "1D %":       st.column_config.NumberColumn("1D %", format="%+.2f%%", width="small"),
        "Score":      st.column_config.ProgressColumn(
                          "Confluence Score", min_value=0, max_value=100, format="%.1f"
                      ),
        "Signal":     st.column_config.TextColumn("Case", width="small"),
        "Conviction": st.column_config.TextColumn("Conviction", width="small"),
        "Bull Sigs":  st.column_config.NumberColumn("Bull", format="%d", width="small"),
        "Bear Sigs":  st.column_config.NumberColumn("Bear", format="%d", width="small"),
        "Signals":    st.column_config.NumberColumn("Signals", format="%d", width="small"),
    },
    height=min(35 * len(display_df) + 38, 600),
)

# ── Inline preview when a row is selected ─────────────────────────────────────
selected_rows = event.selection.get("rows", []) if hasattr(event, "selection") else []
if selected_rows:
    sel_idx    = selected_rows[0]
    sel_row    = screen_df.iloc[sel_idx]
    sel_ticker = sel_row["Ticker"]
    sel_name   = sel_row["Company"]
    sel_score  = sel_row["Score"]
    sel_case   = sel_row["Case"]
    sel_conv   = sel_row["Conviction"]
    sel_sector = sel_row["Sector"]

    score_col = "#1B5E20" if sel_score >= 65 else ("#7B1010" if sel_score <= 35 else "#8B7355")

    # Live quote + pre/post market (cached 60s — negligible cost)
    _sel_q = fetch_live_quote(sel_ticker)
    _sel_price_str = f"${_sel_q['price']:.2f}" if _sel_q.get("price") else "—"
    _sel_chg_str   = (f"{_sel_q['pct_change']:+.2f}%" if _sel_q.get("pct_change") is not None else "")
    _sel_chg_col   = "#1B5E20" if (_sel_q.get("pct_change") or 0) >= 0 else "#7B1010"

    # Extended hours badge
    _sel_ext_html = ""
    _sel_mst = _sel_q.get("market_state")
    if _sel_mst == "PRE" and _sel_q.get("pre_price"):
        _ec = "#1B5E20" if (_sel_q.get("pre_change_pct") or 0) >= 0 else "#7B1010"
        _es = "▲" if (_sel_q.get("pre_change_pct") or 0) >= 0 else "▼"
        _sel_ext_html = (
            f'<span style="background:#EEF3FA;border-radius:3px;padding:2px 7px;'
            f'font-size:0.70rem;color:{_ec};font-weight:700;margin-left:8px;">'
            f'PRE {_es} ${_sel_q["pre_price"]:.2f} ({abs(_sel_q["pre_change_pct"]):.2f}%)</span>'
        )
    elif _sel_mst == "POST" and _sel_q.get("post_price"):
        _ec = "#1B5E20" if (_sel_q.get("post_change_pct") or 0) >= 0 else "#7B1010"
        _es = "▲" if (_sel_q.get("post_change_pct") or 0) >= 0 else "▼"
        _sel_ext_html = (
            f'<span style="background:#FBF8F0;border-radius:3px;padding:2px 7px;'
            f'font-size:0.70rem;color:{_ec};font-weight:700;margin-left:8px;">'
            f'AH {_es} ${_sel_q["post_price"]:.2f} ({abs(_sel_q["post_change_pct"]):.2f}%)</span>'
        )

    # Find top driving signals from the pre-computed all_scores dict
    # all_scores has {sig_id: {score, status, is_synthetic}} — no "config" key,
    # so we join back to SIGNALS for the display name.
    _top_bull_sigs = sorted(
        [(sig_id, sv) for sig_id, sv in all_scores.items() if sv.get("status") == "bullish"],
        key=lambda x: -x[1].get("score", 50),
    )[:3]
    _top_bear_sigs = sorted(
        [(sig_id, sv) for sig_id, sv in all_scores.items() if sv.get("status") == "bearish"],
        key=lambda x: x[1].get("score", 50),
    )[:3]
    _top_sig_lines = ""
    for _tsid, _tsv in _top_bull_sigs:
        _tname = SIGNALS.get(_tsid, {}).get("name", _tsid)[:32]
        _top_sig_lines += f'<div style="color:#1B5E20;font-size:0.75rem;">▲ {_tname} ({_tsv["score"]:.0f})</div>'
    for _tsid, _tsv in _top_bear_sigs:
        _tname = SIGNALS.get(_tsid, {}).get("name", _tsid)[:32]
        _top_sig_lines += f'<div style="color:#7B1010;font-size:0.75rem;">▼ {_tname} ({_tsv["score"]:.0f})</div>'

    st.markdown(f"""
    <div style="background:#F0EBE1;border-radius:8px;padding:18px 24px;border:1px solid #D4C9B0;
                border-left:5px solid {score_col};font-family:Georgia,serif;margin:12px 0;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">
            <div style="flex:2;min-width:220px;">
                <div style="font-size:1.1rem;font-weight:700;color:#1A1612;">{sel_name}
                    <span style="font-size:0.85rem;color:#8B7355;font-weight:400;"> ({sel_ticker})</span>
                </div>
                <div style="font-size:0.80rem;color:#8B7355;margin-top:3px;">{sel_sector}</div>
                <div style="margin-top:10px;font-size:0.80rem;color:#6B6560;line-height:1.7;">
                    Bull signals: <b>{int(sel_row['Bull Sigs'])}</b> &nbsp;·&nbsp;
                    Bear signals: <b>{int(sel_row['Bear Sigs'])}</b> &nbsp;·&nbsp;
                    Total: <b>{int(sel_row['Signals'])}</b>
                </div>
                <div style="margin-top:8px;">{_top_sig_lines}</div>
            </div>
            <div style="text-align:right;min-width:160px;">
                <div style="font-size:2rem;font-weight:700;color:{score_col};">{sel_score:.0f}<span style="font-size:1rem;color:#8B7355;">/100</span></div>
                <div style="font-size:0.80rem;color:{score_col};margin-bottom:8px;">{sel_case} — {sel_conv}</div>
                <div style="font-size:1.1rem;font-weight:700;color:#1A1612;">{_sel_price_str}
                    <span style="color:{_sel_chg_col};font-size:0.85rem;"> {_sel_chg_str}</span>
                    {_sel_ext_html}
                </div>
                <div style="font-size:0.68rem;color:#8B7355;margin-top:2px;">live · 60s</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    _prev_col, _tdd_col = st.columns([1, 1])
    with _tdd_col:
        if st.button(f"Open {sel_ticker} in Ticker Deep Dive →", type="primary", use_container_width=True, key="scr_tdd_btn"):
            st.query_params["ticker"] = sel_ticker
            st.switch_page("pages/3_Ticker_Deep_Dive.py")

    # Store selection in session state so Ticker Deep Dive can auto-load it
    if "selected_ticker" not in st.session_state or st.session_state.selected_ticker != sel_ticker:
        st.session_state.selected_ticker = sel_ticker
        st.session_state.selected_ticker_name = sel_name

st.markdown("")
st.caption(
    "Click any row to preview. For full analysis: go to Ticker Deep Dive. "
    "Scores recalculate hourly."
)

# ── Export ─────────────────────────────────────────────────────────────────────
st.divider()
csv = screen_df.to_csv(index=False).encode()
st.download_button(
    "Download Screener Results (CSV)",
    csv,
    file_name=f"UA_Screener_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
    mime="text/csv",
)
