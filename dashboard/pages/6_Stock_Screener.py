"""
Page 6 — Stock Screener
Filter and rank every ticker in the Unstructured Alpha universe by confluence
score, sector, signal direction, and signal strength. Click any row to jump to
the Ticker Deep Dive, or enter any ticker symbol for a quick analysis.

Search behaviour:
  - Sidebar search filters the ~80-ticker tracked universe first.
  - If the search term matches nothing in the universe, it is automatically
    treated as a custom ticker symbol and analyzed via yfinance + sector signals.
    This way you are never dead-ended with "no results."
  - The "Analyze Any Ticker" block at the top also accepts any yfinance symbol.
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
from utils.header import render_header, render_sidebar_base, render_page_header, render_data_unavailable_banner, render_footer
from utils.theme import source_badge, inject_premium_css, section_label, PLOTLY_CONFIG
from utils.quotes import get_batch_quotes
from utils.signals_cache import get_all_signal_scores

st.set_page_config(page_title="Stock Screener — UA", layout="wide")
render_header("Stock Screener")
render_sidebar_base()
try:
    from utils.instrumentation import record_once
    record_once("screener_viewed")
except Exception:
    pass
inject_premium_css()

render_page_header(
    "Stock Screener",
    f"Filter {len(TICKERS)} tickers by Macro + Momentum Rank, sector, and price momentum.",
    icon="",
)

tab_screener, tab_rank, tab_squeeze = st.tabs([
    " Stock Screener",
    " Rankings",
    " Short Squeeze Radar",
])

with tab_screener:
    st.markdown(
        '<div style="font-size:0.76rem;color:#6B7FBF;font-family:Inter,sans-serif;'
        'margin:-4px 0 12px;">The <b>Macro + Momentum Rank</b> orders tickers by current signal '
        'agreement (70% macro / 30% price momentum) — a fast screen, not a validated return '
        'forecast. For a ticker\'s full <b>Confluence Score</b> (with insider, 13F and short-interest '
        'overlays) open its Ticker Deep Dive. See About → Methodology for the backtest.</div>',
        unsafe_allow_html=True,
    )

    END   = datetime.now().strftime("%Y-%m-%d")
    START = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    # Dark-theme status palette
    STATUS_COLOR = {
        "bullish":          "#00D566",
        "bearish":          "#FF4444",
        "neutral":          "#6B7FBF",
        "insufficient_data":"#8892AA",
    }
    STATUS_SYM = {
        "bullish": "▲", "bearish": "▼", "neutral": "●", "insufficient_data": "○",
    }

    SECTOR_SIGNAL_MAP = {
        "Technology":             ["hyperscaler_capex", "semiconductor_etf", "ten_year_yield", "hy_spread", "vix"],
        "Energy":                 ["crude_oil", "crude_inventories", "natural_gas", "gas_storage", "dollar_index"],
        "Financial Services":     ["yield_curve", "hy_spread", "ten_year_yield", "vix", "bank_lending_standards", "credit_card_delinquency"],
        "Healthcare":             ["jobless_claims", "consumer_sentiment", "hy_spread", "ten_year_yield", "fda_approval_velocity"],
        "Consumer Cyclical":      ["retail_sales", "consumer_sentiment", "jobless_claims", "ata_trucking", "retail_job_openings", "ecommerce_share"],
        "Consumer Defensive":     ["retail_sales", "food_cpi", "jobless_claims", "consumer_sentiment", "retail_job_openings"],
        "Industrials":            ["ism_pmi", "ata_trucking", "rail_traffic", "durable_goods", "hy_spread", "construction_spending"],
        "Basic Materials":        ["copper", "dollar_index", "ism_pmi", "crude_oil", "shipping_index"],
        "Utilities":              ["ten_year_yield", "natural_gas", "uranium_proxy", "power_demand_growth", "vix"],
        "Real Estate":            ["ten_year_yield", "housing_starts", "hy_spread", "vix"],
        "Communication Services": ["hyperscaler_capex", "jobless_claims", "ten_year_yield", "hy_spread"],
    }
    _DEFAULT_SIGS = ["ata_trucking", "hy_spread", "ten_year_yield", "vix", "yield_curve"]


    def _score_custom_ticker(symbol: str) -> dict | None:
        """Fetch price data + sector from yfinance and return a scored result dict."""
        try:
            t    = yf.Ticker(symbol)
            info = t.info or {}
            hist = t.history(period="1y")
            if hist.empty or "Close" not in hist.columns:
                return None
            close      = hist["Close"].dropna()
            last       = float(close.iloc[-1])
            prev       = float(close.iloc[-2]) if len(close) > 1 else last
            yr_start   = float(close.iloc[0])
            chg_1d     = (last - prev) / prev * 100
            chg_1y     = (last - yr_start) / yr_start * 100
            sector_raw = info.get("sector", "Unknown")
            company    = info.get("longName") or info.get("shortName") or symbol
            sig_ids    = SECTOR_SIGNAL_MAP.get(sector_raw, _DEFAULT_SIGS)
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
            return {
                "symbol": symbol, "company": company, "sector": sector_raw,
                "last": last, "chg_1d": chg_1d, "chg_1y": chg_1y,
                "conf": conf, "sig_count": len(ticker_scores),
            }
        except Exception:
            return None


    def _render_custom_card(r: dict):
        """Render the dark-theme quick-analysis card for a custom ticker result."""
        conf  = r["conf"]
        score = conf["overall_score"]
        ac    = "#00D566" if score >= 65 else ("#FF4444" if score <= 35 else "#6B7FBF")
        ac_bg = f"rgba({','.join(str(int(ac[i:i+2], 16)) for i in (1, 3, 5))},0.07)" if ac.startswith('#') else "rgba(107,127,191,0.07)"
        chg_c = "#00D566" if r["chg_1d"] >= 0 else "#FF4444"
        chg_a = "▲" if r["chg_1d"] >= 0 else "▼"
        yr_c  = "#00D566" if r["chg_1y"] >= 0 else "#FF4444"

        in_universe = r["symbol"] in TICKERS
        badge = (
            '<span style="background:rgba(0,213,102,0.1);color:#00D566;border:1px solid rgba(0,213,102,0.25);'
            'padding:1px 6px;border-radius:4px;font-size:0.60rem;font-weight:700;margin-left:6px;">IN UNIVERSE</span>'
            if in_universe else
            '<span style="background:rgba(107,127,191,0.1);color:#6B7FBF;border:1px solid rgba(107,127,191,0.2);'
            'padding:1px 6px;border-radius:4px;font-size:0.60rem;font-weight:700;margin-left:6px;">QUICK SCORE</span>'
        )

        st.markdown(f"""
    <div style="background:{ac_bg};border:1px solid {ac}33;border-left:4px solid {ac};
                border-radius:12px;padding:20px 24px;font-family:Inter,sans-serif;margin:10px 0;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;">
            <div style="flex:2;min-width:200px;">
                <div style="font-size:1.1rem;font-weight:700;color:#E8EEFF;letter-spacing:-0.2px;">
                    {r['company']} {badge}
                </div>
                <div style="font-size:0.75rem;color:#8892AA;margin-top:3px;letter-spacing:0.04em;">
                    {r['symbol']} &nbsp;·&nbsp; {r['sector']}
                </div>
                <div style="margin-top:12px;font-size:0.80rem;color:#8892AA;">
                    Price: <b style="color:#E8EEFF;">${r['last']:,.2f}</b>
                    &nbsp;·&nbsp;
                    1D: <span style="color:{chg_c};">{chg_a}{abs(r['chg_1d']):.2f}%</span>
                    &nbsp;·&nbsp;
                    1Y: <span style="color:{yr_c};">{r['chg_1y']:+.1f}%</span>
                </div>
                <div style="margin-top:6px;font-size:0.76rem;color:#6B7FBF;">
                    {r['sig_count']} macro signals mapped · {conf['bull_count']} bullish
                    · {conf['bear_count']} bearish
                    · {r['sig_count'] - conf['bull_count'] - conf['bear_count']} neutral
                </div>
            </div>
            <div style="text-align:center;min-width:120px;">
                <div style="font-size:0.58rem;letter-spacing:0.14em;color:{ac};font-weight:700;margin-bottom:4px;">CONFLUENCE SCORE</div>
                <div style="font-size:2.6rem;font-weight:900;color:{ac};letter-spacing:-1px;line-height:1;">{score:.0f}</div>
                <div style="font-size:0.74rem;color:{ac};margin-top:3px;font-weight:600;">{conf['case']} · {conf['conviction']}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

        if not in_universe:
            st.markdown(
                '<div style="font-size:0.72rem;color:#6B7FBF;font-family:Inter,sans-serif;'
                'margin:-4px 0 8px;padding-left:2px;">'
                ' Not in tracked universe — score uses sector-mapped signals as a proxy. '
                'For the deepest analysis, open Ticker Deep Dive with this symbol.</div>',
                unsafe_allow_html=True,
            )

        _btn_col, _ = st.columns([1, 3])
        with _btn_col:
            if st.button(f"Open {r['symbol']} in Deep Dive →", type="primary",
                         use_container_width=True, key=f"cust_tdd_{r['symbol']}"):
                st.session_state["selected_ticker"] = r["symbol"]
                st.switch_page("pages/3_Ticker_Deep_Dive.py")


    # ── Quick Analyze Any Ticker ──────────────────────────────────────────────────
    st.markdown("""
    <div style="font-size:0.58rem;letter-spacing:0.16em;font-weight:700;color:#00D566;
                font-family:Inter,sans-serif;margin-bottom:6px;">ANALYZE ANY TICKER</div>
    <div style="font-size:0.80rem;color:#8892AA;font-family:Inter,sans-serif;margin-bottom:10px;">
        Any global symbol — US stocks, ETFs, crypto (BTC-USD), indices (^GSPC), international (MC.PA).
        If it's on Yahoo Finance, it works.
    </div>
    """, unsafe_allow_html=True)

    _qa1, _qa2 = st.columns([2, 1])
    with _qa1:
        custom_ticker = st.text_input(
            "Enter any ticker symbol",
            placeholder="e.g. HOOD, COIN, MSTR, BTC-USD, ^GSPC, MC.PA …",
            key="quick_ticker",
            label_visibility="collapsed",
        ).strip().upper()
    with _qa2:
        run_quick = st.button("→ Analyze", type="primary", key="run_quick_btn", use_container_width=True)

    if custom_ticker and run_quick:
        with st.spinner(f"Analyzing {custom_ticker}…"):
            _res = _score_custom_ticker(custom_ticker)
        if _res is None:
            st.error(
                f"No data found for **{custom_ticker}**. Check the symbol and try again. "
                "Use Yahoo Finance format: `BTC-USD` for crypto, `^GSPC` for S&P 500, `MC.PA` for LVMH."
            )
        else:
            _render_custom_card(_res)

    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    st.markdown(
        '<hr style="border:none;border-top:1px solid rgba(255,255,255,0.06);margin:8px 0 20px;">',
        unsafe_allow_html=True,
    )

    # ── Sidebar filters ───────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            '<div style="font-size:0.70rem;font-weight:700;letter-spacing:0.12em;'
            'color:#8892AA;font-family:Inter,sans-serif;margin-bottom:10px;">SCREENER FILTERS</div>',
            unsafe_allow_html=True,
        )
        search_text = st.text_input(
            "Search ticker or company",
            placeholder="NVDA, Goldman, Energy…",
            key="scr_search",
        ).strip()

        all_sectors = sorted(set(v.get("sector", "Other") for v in TICKERS.values() if v.get("sector")))
        sel_sectors = st.multiselect("Sectors", all_sectors, default=all_sectors, key="scr_sectors")

        bias_opts = ["All", "Bullish only", "Bearish only", "Neutral only"]
        bias_sel  = st.selectbox("Signal Bias", bias_opts, key="scr_bias")

        min_pcs = st.slider("Min signal quality (PCS)", 1, 10, 5, key="scr_pcs")
        score_min, score_max = st.slider("Macro + Momentum Rank range", 0, 100, (0, 100), key="scr_score")

        st.divider()
        st.caption("Scores update every 2h. Click any row then open Ticker Deep Dive for the full breakdown.")


    # ── Load signals + momentum (shared caches) ──────────────────────────────────
    @st.cache_data(ttl=1800, show_spinner=False)
    def load_all_ticker_momentum() -> dict:
        tickers_list = list(TICKERS.keys())
        momentum = {}
        try:
            raw    = yf.download(tickers_list, period="1y", auto_adjust=True, progress=False, threads=True)
            closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
            for tkr in tickers_list:
                try:
                    col = closes[tkr] if tkr in closes.columns else pd.Series(dtype=float)
                    col = col.dropna()
                    if len(col) < 10:
                        momentum[tkr] = 50.0
                        continue
                    ret_1y  = (col.iloc[-1] / col.iloc[0]) - 1 if len(col) >= 200 else 0.0
                    ret_1m  = (col.iloc[-1] / col.iloc[-22]) - 1 if len(col) >= 22 else 0.0
                    blended = ret_1y * 0.6 + ret_1m * 0.4
                    momentum[tkr] = round(float(np.clip(50.0 + blended * 83.3, 5.0, 95.0)), 1)
                except Exception:
                    momentum[tkr] = 50.0
        except Exception:
            for tkr in tickers_list:
                momentum[tkr] = 50.0
        return momentum


    def _ticker_confluence(ticker: str, sig_ids: list, all_scores: dict, momentum_cache: dict) -> dict:
        weights       = {sid: SIGNALS[sid].get("pcs", 5) / 10.0 for sid in sig_ids if sid in SIGNALS}
        ticker_scores = {sid: all_scores.get(sid, {"score": 50, "status": "neutral"}) for sid in sig_ids}
        conf          = compute_confluence(ticker_scores, weights=weights)
        macro_score   = conf["overall_score"]
        mom_score     = momentum_cache.get(ticker, 50.0)
        blended       = macro_score * 0.70 + mom_score * 0.30
        conf["overall_score"] = round(blended, 1)
        if blended >= 65:   conf["case"] = "BULL"
        elif blended <= 35: conf["case"] = "BEAR"
        else:               conf["case"] = "NEUTRAL" if abs(conf["bull_count"] - conf["bear_count"]) <= 1 else "MIXED"
        n         = len(ticker_scores)
        agreement = max(conf["bull_count"], conf["bear_count"]) / n if n else 0
        conf["conviction"] = (
            "Very High" if agreement >= 0.80 else
            "High"      if agreement >= 0.60 else
            "Moderate"  if agreement >= 0.45 else
            "Low"
        )
        return conf


    # ── Build screener table ──────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="font-size:0.58rem;letter-spacing:0.16em;font-weight:700;color:#00D566;
                font-family:Inter,sans-serif;margin-bottom:4px;">ALTERNATIVE DATA SCREENER</div>
    <div style="font-size:0.76rem;color:#8892AA;font-family:Inter,sans-serif;margin-bottom:12px;">
        {len(TICKERS)} tickers ranked by <b>Macro + Momentum Rank</b> = 70% macro signal confluence (PCS-weighted) + 30% price momentum.
        This is a fast screen; the full Confluence Score (with insider, 13F &amp; short-interest overlays) lives on each Ticker Deep Dive.
        Click any row to preview. Can't find your ticker? Use the search box above or type it in "Analyze Any Ticker."
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Loading signals and price momentum…"):
        all_scores      = get_all_signal_scores()
        _momentum_cache = load_all_ticker_momentum()

    render_data_unavailable_banner(
        sum(1 for sv in all_scores.values() if sv.get("unavailable") or sv.get("error")),
        len(all_scores),
    )

    # Build rows — apply sidebar filters
    _search_lower = search_text.lower()
    rows = []
    for ticker, tmeta in TICKERS.items():
        sector = tmeta.get("sector", "Other")
        if _search_lower:
            if _search_lower not in ticker.lower() and _search_lower not in tmeta.get("name", "").lower():
                continue
        if sel_sectors and sector not in sel_sectors:
            continue
        sig_ids = [s for s in tmeta.get("signals", list(SIGNALS.keys()))
                   if SIGNALS.get(s, {}).get("pcs", 0) >= min_pcs]
        conf    = _ticker_confluence(ticker, sig_ids, all_scores, _momentum_cache)
        overall = conf["overall_score"]
        case    = conf["case"]
        conv    = conf["conviction"]
        if bias_sel == "Bullish only"  and case != "BULL":  continue
        if bias_sel == "Bearish only"  and case != "BEAR":  continue
        if bias_sel == "Neutral only"  and case not in ("NEUTRAL", "MIXED"): continue
        if not (score_min <= overall <= score_max):          continue
        rows.append({
            "Ticker":    ticker,
            "Company":   tmeta.get("name", ticker),
            "Sector":    sector,
            "Score":     round(overall, 1),
            "Case":      case,
            "Conviction":conv,
            "Bull Sigs": conf["bull_count"],
            "Bear Sigs": conf["bear_count"],
            "Signals":   len(sig_ids),
        })

    # ── No results? Try to auto-analyze search term as a custom symbol ────────────
    if not rows:
        _candidate = search_text.strip().upper()
        if _candidate:
            st.markdown(
                f'<div style="background:rgba(107,127,191,0.06);border:1px solid rgba(107,127,191,0.15);'
                f'border-left:3px solid #6B7FBF;border-radius:8px;padding:14px 18px;'
                f'font-family:Inter,sans-serif;margin-bottom:16px;">'
                f'<div style="font-size:0.84rem;color:#E8EEFF;font-weight:600;margin-bottom:4px;">'
                f'"{_candidate}" not found in our tracked universe</div>'
                f'<div style="font-size:0.76rem;color:#8892AA;">'
                f'Analyzing it as a custom symbol using sector-mapped macro signals…</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            with st.spinner(f"Fetching data for {_candidate}…"):
                _auto_res = _score_custom_ticker(_candidate)
            if _auto_res:
                _render_custom_card(_auto_res)
            else:
                st.info(
                    f"Could not find price data for **{_candidate}**. "
                    "Double-check the ticker format (e.g. `BTC-USD`, `^GSPC`, `9984.T`) "
                    "or use the 'Analyze Any Ticker' box above."
                )
        else:
            st.info("No tickers match the current filters. Try broadening your selection.")
        st.stop()

    screen_df = pd.DataFrame(rows).sort_values("Score", ascending=False).reset_index(drop=True)

    # Free the per-ticker intermediate frames built during the 280-ticker scan
    # (the transient peak that was tipping the 512MB instance into OOM).
    from utils.memory import release_memory
    del rows
    release_memory()

    with st.spinner(f"Loading live prices for {len(screen_df)} ticker(s)…"):
        _quotes = get_batch_quotes(list(screen_df["Ticker"]))

    screen_df["Price"] = screen_df["Ticker"].map(lambda t: _quotes.get(t, {}).get("last"))
    screen_df["1D %"]  = screen_df["Ticker"].map(lambda t: _quotes.get(t, {}).get("chg_1d_pct"))

    # ── Summary stats ─────────────────────────────────────────────────────────────
    tot     = len(screen_df)
    n_bull  = (screen_df["Case"] == "BULL").sum()
    n_bear  = (screen_df["Case"] == "BEAR").sum()
    n_neut  = tot - n_bull - n_bear
    avg_scr = screen_df["Score"].mean()

    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Tickers Screened", tot)
    s2.metric("Bullish", n_bull, delta=f"{n_bull/tot*100:.0f}%")
    s3.metric("Bearish", n_bear, delta=f"-{n_bear/tot*100:.0f}%")
    s4.metric("Neutral", n_neut)
    s5.metric("Avg Score", f"{avg_scr:.1f}/100")

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # ── Distribution chart — dark theme ──────────────────────────────────────────
    fig_dist = go.Figure(go.Histogram(
        x=screen_df["Score"], nbinsx=20,
        marker_color="rgba(0,213,102,0.55)",
        marker_line=dict(color="rgba(0,213,102,0.8)", width=0.5),
        hovertemplate="Score %{x:.0f}: %{y} tickers<extra></extra>",
    ))
    fig_dist.add_vline(
        x=65, line=dict(color="#00D566", dash="dot", width=1.5),
        annotation_text="Bull", annotation_font_color="#00D566",
        annotation_font_size=10,
    )
    fig_dist.add_vline(
        x=35, line=dict(color="#FF4444", dash="dot", width=1.5),
        annotation_text="Bear", annotation_font_color="#FF4444",
        annotation_font_size=10,
    )
    fig_dist.update_layout(
        height=140,
        paper_bgcolor="#0B0D12",
        plot_bgcolor="#0F1118",
        xaxis=dict(
            showgrid=False,
            tickfont=dict(color="#8892AA", size=10, family="Inter, sans-serif"),
            title=dict(text="Macro + Momentum Rank", font=dict(color="#6B7FBF", size=10)),
            linecolor="rgba(255,255,255,0.08)",
        ),
        yaxis=dict(
            showgrid=True, gridcolor="rgba(255,255,255,0.05)",
            tickfont=dict(color="#8892AA", size=10, family="Inter, sans-serif"),
            title=dict(text="# Tickers", font=dict(color="#6B7FBF", size=10)),
        ),
        margin=dict(l=8, r=8, t=10, b=8),
        font=dict(family="Inter, sans-serif", color="#8892AA"),
    )
    st.plotly_chart(fig_dist, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
    st.markdown(
        f"&nbsp; {source_badge('yfinance', 'Live quotes · price history')} "
        f"&nbsp; {source_badge('ua', 'Macro + Momentum Rank · UA internal')}",
        unsafe_allow_html=True,
    )

    # ── Main screener table ───────────────────────────────────────────────────────
    screen_df["Signal"] = screen_df["Case"].map(
        {"BULL": "▲ BULL", "BEAR": "▼ BEAR"}
    ).fillna("● " + screen_df["Case"])

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
                              "Macro+Momentum Rank", min_value=0, max_value=100, format="%.1f"
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

        ac     = "#00D566" if sel_score >= 65 else ("#FF4444" if sel_score <= 35 else "#6B7FBF")
        ac_bg  = f"rgba({','.join(str(int(ac[i:i+2],16)) for i in (1,3,5))},0.07)"

        # Live quote
        _sel_q      = fetch_live_quote(sel_ticker)
        _price      = _sel_q.get("price")
        _chg        = _sel_q.get("pct_change")
        _price_str  = f"${_price:.2f}" if _price else "—"
        _chg_str    = f"{_chg:+.2f}%" if _chg is not None else ""
        _chg_c      = "#00D566" if (_chg or 0) >= 0 else "#FF4444"

        # Extended hours badge
        _ext_html = ""
        _mst = _sel_q.get("market_state")
        if _mst == "PRE" and _sel_q.get("pre_price"):
            _pc = _sel_q.get("pre_change_pct") or 0
            _ec = "#00D566" if _pc >= 0 else "#FF4444"
            _ext_html = (
                f'<span style="background:rgba({",".join(str(int(_ec[i:i+2],16)) for i in (1,3,5))},0.10);'
                f'color:{_ec};border:1px solid {_ec}33;padding:2px 7px;border-radius:5px;'
                f'font-size:0.68rem;font-weight:700;margin-left:8px;">'
                f'PRE {"▲" if _pc>=0 else "▼"} ${_sel_q["pre_price"]:.2f} ({abs(_pc):.2f}%)</span>'
            )
        elif _mst == "POST" and _sel_q.get("post_price"):
            _pc = _sel_q.get("post_change_pct") or 0
            _ec = "#00D566" if _pc >= 0 else "#FF4444"
            _ext_html = (
                f'<span style="background:rgba({",".join(str(int(_ec[i:i+2],16)) for i in (1,3,5))},0.10);'
                f'color:{_ec};border:1px solid {_ec}33;padding:2px 7px;border-radius:5px;'
                f'font-size:0.68rem;font-weight:700;margin-left:8px;">'
                f'AH {"▲" if _pc>=0 else "▼"} ${_sel_q["post_price"]:.2f} ({abs(_pc):.2f}%)</span>'
            )

        # Top driving signals
        _top_bull_sigs = sorted(
            [(sid, sv) for sid, sv in all_scores.items() if sv.get("status") == "bullish"],
            key=lambda x: -x[1].get("score", 50),
        )[:4]
        _top_bear_sigs = sorted(
            [(sid, sv) for sid, sv in all_scores.items() if sv.get("status") == "bearish"],
            key=lambda x: x[1].get("score", 50),
        )[:3]
        _sig_rows = ""
        for _tsid, _tsv in _top_bull_sigs:
            _tn = SIGNALS.get(_tsid, {}).get("name", _tsid)[:36]
            _sig_rows += (
                f'<div style="font-size:0.72rem;color:#00D566;padding:2px 0;">'
                f'▲ {_tn} <span style="color:#6B7FBF;">({_tsv["score"]:.0f})</span></div>'
            )
        for _tsid, _tsv in _top_bear_sigs:
            _tn = SIGNALS.get(_tsid, {}).get("name", _tsid)[:36]
            _sig_rows += (
                f'<div style="font-size:0.72rem;color:#FF4444;padding:2px 0;">'
                f'▼ {_tn} <span style="color:#6B7FBF;">({_tsv["score"]:.0f})</span></div>'
            )

        st.markdown(f"""
    <div style="background:{ac_bg};border:1px solid {ac}33;border-left:4px solid {ac};
                border-radius:12px;padding:20px 24px;font-family:Inter,sans-serif;margin:14px 0;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:20px;">
            <div style="flex:2;min-width:220px;">
                <div style="font-size:1.05rem;font-weight:700;color:#E8EEFF;letter-spacing:-0.2px;">
                    {sel_name}
                    <span style="font-size:0.80rem;color:#8892AA;font-weight:400;margin-left:6px;">
                        ({sel_ticker})
                    </span>
                </div>
                <div style="font-size:0.72rem;color:#6B7FBF;margin-top:2px;">{sel_sector}</div>
                <div style="margin-top:10px;font-size:0.78rem;color:#8892AA;">
                    {int(sel_row['Bull Sigs'])} bullish signals &nbsp;·&nbsp;
                    {int(sel_row['Bear Sigs'])} bearish signals &nbsp;·&nbsp;
                    {int(sel_row['Signals'])} total
                </div>
                <div style="margin-top:10px;border-top:1px solid rgba(255,255,255,0.05);padding-top:10px;">
                    {_sig_rows}
                </div>
            </div>
            <div style="text-align:right;min-width:160px;">
                <div style="font-size:0.56rem;letter-spacing:0.14em;color:{ac};font-weight:700;margin-bottom:3px;">CONFLUENCE SCORE</div>
                <div style="font-size:2.6rem;font-weight:900;color:{ac};letter-spacing:-1px;line-height:1;">
                    {sel_score:.0f}
                </div>
                <div style="font-size:0.74rem;color:{ac};font-weight:600;margin-top:3px;">
                    {sel_case} · {sel_conv}
                </div>
                <div style="margin-top:14px;border-top:1px solid rgba(255,255,255,0.06);padding-top:10px;">
                    <div style="font-size:1.3rem;font-weight:700;color:#E8EEFF;letter-spacing:-0.3px;">
                        {_price_str}
                        <span style="font-size:0.85rem;color:{_chg_c};"> {_chg_str}</span>
                        {_ext_html}
                    </div>
                    <div style="font-size:0.62rem;color:#6B7FBF;margin-top:2px;">live · 60s cache</div>
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

        _btn_l, _btn_r, _ = st.columns([1, 1, 2])
        with _btn_l:
            if st.button(f"Ticker Deep Dive: {sel_ticker} →", type="primary",
                         use_container_width=True, key="scr_tdd_btn"):
                st.query_params["ticker"] = sel_ticker
                st.switch_page("pages/3_Ticker_Deep_Dive.py")
        with _btn_r:
            if st.button(f"Chart: {sel_ticker} →", use_container_width=True, key="scr_chart_btn"):
                st.session_state["chart_ticker"] = sel_ticker
                st.switch_page("pages/14_Stock_Chart.py")

        if "selected_ticker" not in st.session_state or st.session_state.selected_ticker != sel_ticker:
            st.session_state.selected_ticker      = sel_ticker
            st.session_state.selected_ticker_name = sel_name

    st.markdown(
        '<div style="font-size:0.68rem;color:#6B7FBF;font-family:Inter,sans-serif;margin-top:8px;">'
        'Click any row to preview. Scores recalculate every 2 hours. '
        'Ticker not listed? Use "Analyze Any Ticker" above or type it in the sidebar search — '
        'it will automatically fall through to a custom analysis.</div>',
        unsafe_allow_html=True,
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


with tab_rank:
    from utils.top_tickers import get_top_tickers as _get_top
    from utils.theme import inject_premium_css as _ipc2

    st.markdown("### Live Score Rankings")
    st.caption(f"All {len(TICKERS)} tickers ranked by macro confluence score. Green ≥ 65 · Red ≤ 35 · White = neutral.")

    @st.cache_data(ttl=7200, show_spinner=False, max_entries=1)
    def _rank_all_tickers():
        import pandas as pd
        top = _get_top()
        all_r = top.get("bullish", []) + top.get("neutral", []) + top.get("bearish", [])
        return pd.DataFrame([
            {"Ticker": r["ticker"], "Name": r.get("name","")[:30],
             "Sector": r.get("sector","—"), "Score": round(r.get("score",50),0),
             "Signal": "" if r.get("score",50) >= 65 else "" if r.get("score",50) <= 35 else ""}
            for r in all_r
        ]).sort_values("Score", ascending=False)

    with st.spinner("Loading rankings…"):
        _rank_df = _rank_all_tickers()

    _rank_col1, _rank_col2 = st.columns(2)
    _rank_col1.metric(" Bullish", int((_rank_df["Score"] >= 65).sum()))
    _rank_col2.metric(" Bearish", int((_rank_df["Score"] <= 35).sum()))

    import plotly.graph_objects as _go_r
    _rank_top25 = _rank_df.head(25)
    _rank_bot25 = _rank_df.tail(25)
    _r1, _r2 = st.columns(2)
    with _r1:
        st.markdown("**Top 25 Bullish**")
        _fig_top = _go_r.Figure(_go_r.Bar(
            x=_rank_top25["Ticker"], y=_rank_top25["Score"],
            marker=dict(color="#00D566", line=dict(width=0)),
        ))
        _fig_top.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8892AA", family="Inter", size=10),
            yaxis=dict(range=[0,100], gridcolor="rgba(255,255,255,0.06)", showgrid=True, color="#4A5568"),
            xaxis=dict(showgrid=False, color="#4A5568"),
            margin=dict(t=10,b=40,l=40,r=10), height=220)
        st.plotly_chart(_fig_top, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
    with _r2:
        st.markdown("**Bottom 25 Bearish**")
        _fig_bot = _go_r.Figure(_go_r.Bar(
            x=_rank_bot25["Ticker"], y=_rank_bot25["Score"],
            marker=dict(color="#FF4444", line=dict(width=0)),
        ))
        _fig_bot.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#8892AA", family="Inter", size=10),
            yaxis=dict(range=[0,100], gridcolor="rgba(255,255,255,0.06)", showgrid=True, color="#4A5568"),
            xaxis=dict(showgrid=False, color="#4A5568"),
            margin=dict(t=10,b=40,l=40,r=10), height=220)
        st.plotly_chart(_fig_bot, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

    st.dataframe(
        _rank_df, use_container_width=True, hide_index=True,
        column_config={"Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f")},
    )

with tab_squeeze:
    import pandas as pd
    import yfinance as yf
    from datetime import datetime, timedelta, timezone
    from utils.config import TICKERS as _SQ_TICKERS
    from utils.top_tickers import get_top_tickers as _get_top_sq
    from utils.theme import source_badge as _src_badge

    st.markdown("### Short Squeeze Radar")
    st.caption(
        "High short interest + bullish macro confluence + insider buying cluster → squeeze setup. "
        "Squeeze Score = Short Ratio Rank (35%) + Macro Score (40%) + Insider Bonus (25%)."
    )

    @st.cache_data(ttl=900, show_spinner=False, max_entries=1)
    def _sq_short_interest(tickers_t):
        result = {}
        for t in tickers_t:
            try:
                info = yf.Ticker(t).info
                ratio = info.get("shortRatio") or info.get("shortPercentOfFloat")
                result[t] = float(ratio) if ratio is not None else None
            except Exception:
                result[t] = None
        return result

    @st.cache_data(ttl=3600, show_spinner=False, max_entries=1)
    def _sq_insider_clusters(tickers_t):
        from utils.fetchers import fetch_insider_transactions
        clusters = {}
        cutoff = datetime.now(timezone.utc) - timedelta(days=21)
        for t in tickers_t:
            try:
                txns = fetch_insider_transactions(t)
                buys = [tx for tx in txns if tx.get("transaction_type","").lower() in ("p","purchase","buy")
                        and tx.get("date") and tx["date"] >= cutoff]
                clusters[t] = len(buys)
            except Exception:
                clusters[t] = 0
        return clusters

    with st.spinner("Building squeeze radar…"):
        top_data = _get_top_sq()
        _all_t = [r["ticker"] for r in top_data.get("bullish",[]) + top_data.get("bearish",[]) + top_data.get("neutral",[])]
        _macro_lookup = {r["ticker"]: r.get("score",50) for cat in ("bullish","bearish","neutral") for r in top_data.get(cat,[])}
        _short_data = _sq_short_interest(tuple(_all_t[:50]))

    _sq_rows = []
    for t, macro_sc in sorted(_macro_lookup.items(), key=lambda x: -x[1])[:50]:
        si = _short_data.get(t)
        if si is None:
            continue
        si_rank = min(100.0, si / 20 * 100)
        insider_bonus = 0  # skip slow insider fetch in tab; user can open TDD for that
        sq_score = si_rank * 0.35 + macro_sc * 0.40 + insider_bonus * 0.25
        _sq_rows.append({
            "Ticker": t,
            "Name": _SQ_TICKERS.get(t, {}).get("name","")[:28],
            "Macro Score": round(macro_sc, 0),
            "Short Ratio": round(si, 1),
            "Squeeze Score": round(sq_score, 0),
        })

    if _sq_rows:
        _sq_df = pd.DataFrame(_sq_rows).sort_values("Squeeze Score", ascending=False).head(20)
        st.dataframe(
            _sq_df, use_container_width=True, hide_index=True,
            column_config={"Squeeze Score": st.column_config.ProgressColumn("Squeeze Score", min_value=0, max_value=100, format="%.0f")},
        )
        _src_badge("FINRA · yfinance · EDGAR")
    else:
        st.info("Short interest data loading — try again in a moment.")

render_footer()
