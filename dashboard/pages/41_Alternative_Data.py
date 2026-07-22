# pages/41_Alternative_Data.py
# Unstructured Alpha — Alternative Data Hub
# Combines Congress Tracker and Options Flow into one page.
# Congress trades: free. Options Flow: free preview, full analysis for Pro.

import streamlit as st

st.set_page_config(page_title="Alternative Data — UA", layout="wide")

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.theme import inject_premium_css, PLOTLY_CONFIG

render_header("Alternative Data")
render_sidebar_base()
inject_premium_css()

render_page_header(
    "Alternative Data",
    "Congressional stock disclosures and unusual options activity — signals that don't show up in any price chart.",
    icon="",
)

tab_congress, tab_options = st.tabs(["Congress Trades", "Options Flow"])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — CONGRESS TRACKER
# ─────────────────────────────────────────────────────────────────────────────
with tab_congress:
    import html as _h
    from datetime import datetime, timedelta
    import pandas as pd
    import plotly.graph_objects as go
    import requests

    _HOUSE_URL  = "https://house-stock-watcher-data.s3-us-east-2.amazonaws.com/data/all_transactions.json"
    _SENATE_URL = "https://senate-stock-watcher-data.s3-us-east-2.amazonaws.com/aggregate/all_transactions.json"

    @st.cache_data(ttl=3600, show_spinner=False, max_entries=2)
    def _load_congress_trades(days: int = 90) -> pd.DataFrame:
        frames = []
        for url, chamber in [(_HOUSE_URL,"House"), (_SENATE_URL,"Senate")]:
            try:
                r = requests.get(url, timeout=15)
                r.raise_for_status()
                data = r.json()
                df = pd.json_normalize(data) if isinstance(data, list) else pd.DataFrame()
                df["chamber"] = df.get("chamber", chamber)
                frames.append(df)
            except Exception:
                pass

        if not frames:
            unavailable = pd.DataFrame()
            unavailable.attrs["fetch_error"] = True
            unavailable.attrs["provider"] = "congressional_disclosures"
            return unavailable

        df = pd.concat(frames, ignore_index=True)
        date_col = next((c for c in ["transaction_date","transactionDate","date"] if c in df.columns), None)
        if date_col:
            df["transaction_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        df = df[df["transaction_date"] >= cutoff].copy()

        for col, alias in [("representative","representative"),("asset_description","ticker"),
                           ("type","type"),("amount","amount")]:
            if col not in df.columns:
                df[col] = alias if alias in df.columns else "—"
        if "ticker" not in df.columns and "asset_description" in df.columns:
            df["ticker"] = df["asset_description"].str.extract(r"\(([A-Z]{1,5})\)").fillna("—")

        disclosure_col = next((c for c in ["disclosure_date","disclosureDate","filed"] if c in df.columns), None)
        df["disclosure_date"] = df[disclosure_col] if disclosure_col else "—"

        return df.fillna("—")

    c1, c2, c3 = st.columns(3)
    days_back = c1.selectbox("Lookback", [30, 60, 90, 180], index=1, key="cong_days")
    type_filter = c2.multiselect("Trade type", ["Purchase","Sale"], default=[], key="cong_type")
    chamber_filter = c3.multiselect("Chamber", ["House","Senate"], default=[], key="cong_chamber")

    with st.spinner("Loading congressional disclosures…"):
        cdf = _load_congress_trades(days_back)

    if cdf.attrs.get("fetch_error"):
        st.warning("Congressional disclosure feeds are temporarily unavailable. No placeholder trades are shown.")

    if type_filter and "type" in cdf.columns:
        cdf = cdf[cdf["type"].isin(type_filter)]
    if chamber_filter and "chamber" in cdf.columns:
        cdf = cdf[cdf["chamber"].isin(chamber_filter)]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Disclosures", len(cdf))
    purchases = len(cdf[cdf.get("type","").str.contains("Purchase", na=False)]) if "type" in cdf.columns else 0
    sales     = len(cdf[cdf.get("type","").str.contains("Sale",     na=False)]) if "type" in cdf.columns else 0
    m2.metric("Purchases", purchases)
    m3.metric("Sales", sales)
    m4.metric("P/S Ratio", f"{purchases/max(sales,1):.1f}")

    if not cdf.empty:
        cols_show = [c for c in ["transaction_date","disclosure_date","representative","chamber","ticker","type","amount"] if c in cdf.columns]
        disp = cdf[cols_show].sort_values("transaction_date", ascending=False).head(100)
        disp.columns = [c.replace("_"," ").title() for c in disp.columns]
        st.dataframe(disp, use_container_width=True, hide_index=True)

        st.caption(
            "**Trade Date** = when the transaction occurred. **Disclosure Date** = when the SEC received it. "
            "STOCK Act requires filing within 45 days. UA's signal engine uses the disclosure date as "
            "'known as of' to prevent this signal appearing more predictive than it is."
        )

        if "ticker" in cdf.columns and "type" in cdf.columns:
            top = (cdf.groupby("ticker")
                      .size().reset_index(name="count")
                      .sort_values("count", ascending=False).head(15))
            fig = go.Figure(go.Bar(
                x=top["ticker"], y=top["count"],
                marker=dict(color="#4A9EFF", line=dict(width=0)),
            ))
            fig.update_layout(
                title="Most-traded tickers by Congress members",
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#8892AA", family="Inter", size=11),
                xaxis=dict(showgrid=False, color="#4A5568"),
                yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", color="#4A5568"),
                margin=dict(t=40, b=40, l=40, r=20), height=280,
            )
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
    else:
        st.info("No trades found for the selected filters.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — OPTIONS FLOW
# ─────────────────────────────────────────────────────────────────────────────
with tab_options:
    from utils.billing import require_pro
    require_pro("Alternative Data")

    import yfinance as yf
    import pandas as pd
    import plotly.graph_objects as go

    _POPULAR = [
        "SPY","QQQ","NVDA","AAPL","MSFT","AMZN","META","GOOGL",
        "TSLA","AMD","PLTR","XOM","JPM","GS","CCJ","CEG","VST",
    ]
    _VOL_OI_THRESH = 1.0
    _MIN_VOL       = 100

    def _flag_unusual(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "volume" not in df.columns or "openInterest" not in df.columns:
            return df
        df = df.copy()
        df["volume"]        = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
        df["openInterest"]  = pd.to_numeric(df["openInterest"], errors="coerce").fillna(0)
        df["vol_oi"]        = df["volume"] / df["openInterest"].replace(0, float("nan"))
        df["unusual"]       = (df["vol_oi"] >= _VOL_OI_THRESH) & (df["volume"] >= _MIN_VOL)
        return df

    @st.cache_data(ttl=900, show_spinner=False, max_entries=10)
    def _fetch_options(ticker: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        try:
            obj = yf.Ticker(ticker)
            exps = obj.options
            if not exps:
                return pd.DataFrame(), pd.DataFrame()
            calls_frames, puts_frames = [], []
            for exp in exps[:4]:
                chain = obj.option_chain(exp)
                c = chain.calls.copy(); c["expiry"] = exp; calls_frames.append(c)
                p = chain.puts.copy();  p["expiry"] = exp; puts_frames.append(p)
            calls = _flag_unusual(pd.concat(calls_frames, ignore_index=True)) if calls_frames else pd.DataFrame()
            puts  = _flag_unusual(pd.concat(puts_frames,  ignore_index=True)) if puts_frames  else pd.DataFrame()
            return calls, puts
        except Exception:
            return pd.DataFrame(), pd.DataFrame()

    oc1, oc2 = st.columns([2, 3])
    with oc1:
        ticker_input = st.text_input("Ticker", value="NVDA", key="opt_ticker").upper().strip()
    with oc2:
        st.markdown("<div style='padding-top:28px'>", unsafe_allow_html=True)
        pop_cols = st.columns(len(_POPULAR[:9]))
        for i, t in enumerate(_POPULAR[:9]):
            if pop_cols[i].button(t, key=f"opt_pop_{t}", use_container_width=True):
                ticker_input = t
        st.markdown("</div>", unsafe_allow_html=True)

    with st.spinner(f"Fetching options chain for {ticker_input}…"):
        calls_df, puts_df = _fetch_options(ticker_input)

    if calls_df.empty and puts_df.empty:
        st.warning(f"No options data available for {ticker_input}.")
    else:
        unusual_calls = calls_df[calls_df.get("unusual", False)] if not calls_df.empty else pd.DataFrame()
        unusual_puts  = puts_df[puts_df.get("unusual",  False)] if not puts_df.empty  else pd.DataFrame()

        ua1, ua2, ua3, ua4 = st.columns(4)
        ua1.metric("Unusual Calls", len(unusual_calls))
        ua2.metric("Unusual Puts",  len(unusual_puts))
        ua3.metric("Total Calls", len(calls_df) if not calls_df.empty else 0)
        ua4.metric("Total Puts",  len(puts_df)  if not puts_df.empty  else 0)

        bias = "Neutral"
        if len(unusual_calls) > len(unusual_puts) * 1.5:
            bias = " Bullish lean"
        elif len(unusual_puts) > len(unusual_calls) * 1.5:
            bias = " Bearish lean"

        st.markdown(
            f'<div style="background:rgba(255,255,255,0.03);border:0.5px solid rgba(255,255,255,0.10);'
            f'border-radius:8px;padding:10px 16px;margin:8px 0 16px;font-size:0.80rem;color:#8892AA;">'
            f'Options bias for <b style="color:#E8EEFF;">{ticker_input}</b>: '
            f'<b style="color:#4A9EFF;">{bias}</b> based on {len(unusual_calls)} unusual calls '
            f'vs {len(unusual_puts)} unusual puts</div>',
            unsafe_allow_html=True,
        )

        display_cols = ["expiry","strike","lastPrice","volume","openInterest","vol_oi","impliedVolatility"]
        for label, df in [(" Unusual Calls", unusual_calls), (" Unusual Puts", unusual_puts)]:
            if not df.empty:
                st.markdown(f"**{label}** — {len(df)} contracts")
                show = df[[c for c in display_cols if c in df.columns]].copy()
                show = show.rename(columns={
                    "expiry":"Expiry","strike":"Strike","lastPrice":"Last",
                    "volume":"Volume","openInterest":"Open Int","vol_oi":"Vol/OI",
                    "impliedVolatility":"IV",
                })
                if "IV" in show.columns:
                    show["IV"] = (show["IV"] * 100).round(1).astype(str) + "%"
                if "Vol/OI" in show.columns:
                    show["Vol/OI"] = show["Vol/OI"].round(2)
                st.dataframe(show.sort_values("Volume", ascending=False).head(20),
                             use_container_width=True, hide_index=True)

        st.caption(
            "Volume > Open Interest (Vol/OI ≥ 1.0) on a contract signals fresh directional positioning "
            "rather than existing position management. Data is 15-min delayed from yfinance."
        )
