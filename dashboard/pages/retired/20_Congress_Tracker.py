"""
Page 20 — Congressional Trade Tracker
Real-time view of Congress members' stock trades under the STOCK Act,
cross-referenced with Unstructured Alpha signal scores.

Data: House Stock Watcher + Senate Stock Watcher (community-parsed official
STOCK Act disclosures from disclosures.house.gov and efds.senate.gov).
"""

import html as _h
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

from utils.header import render_header, render_sidebar_base, render_page_header

st.set_page_config(page_title="Congress Tracker — UA", layout="wide")
render_header("Congressional Trade Tracker")
render_sidebar_base()

render_page_header(
    "Congressional Trade Tracker",
    "Follow insider-adjacent congressional stock trades with signal overlay.",
    icon="🏛️",
)


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────────────────────────────────────

_HOUSE_URL = (
    "https://house-stock-watcher-data.s3-us-east-2.amazonaws.com"
    "/data/all_transactions.json"
)
_SENATE_URL = (
    "https://senate-stock-watcher-data.s3-us-east-2.amazonaws.com"
    "/aggregate/all_transactions.json"
)


@st.cache_data(ttl=3600 * 6, show_spinner=False, max_entries=2)
def fetch_congress_trades(days: int = 180) -> pd.DataFrame:
    """
    Fetch congressional trades from House + Senate Stock Watcher S3 endpoints,
    which parse the official STOCK Act disclosures from disclosures.house.gov
    and efds.senate.gov daily. Returns an empty frame when both are unavailable.

    Returns unified DataFrame with columns:
        disclosure_date, transaction_date, member, party, chamber, state,
        ticker, type (Purchase / Sale (Full) / Sale (Partial)), amount
    """
    cutoff = datetime.now() - timedelta(days=days)
    records = []

    # ── House ──────────────────────────────────────────────────────────────
    try:
        r = requests.get(_HOUSE_URL, timeout=20,
                         headers={"User-Agent": "UnstructuredAlpha/1.0 research@unstructuredalpha.com"})
        r.raise_for_status()
        data = r.json()
        for item in data:
            ticker = (item.get("ticker") or "").strip().upper()
            if not ticker or ticker in ("--", "N/A", ""):
                continue
            t_date = pd.to_datetime(item.get("transaction_date", ""), errors="coerce")
            d_date = pd.to_datetime(item.get("disclosure_date", ""), errors="coerce")
            if pd.isna(t_date) or t_date < cutoff:
                continue
            tx_type = item.get("type", "")
            if not tx_type:
                continue
            records.append({
                "disclosure_date":  d_date,
                "transaction_date": t_date,
                "member":  item.get("representative", "Unknown"),
                "party":   item.get("party", "Unknown"),
                "chamber": "House",
                "state":   item.get("district", "")[:2] if item.get("district") else item.get("state", ""),
                "ticker":  ticker,
                "type":    tx_type,
                "amount":  item.get("amount", ""),
            })
    except Exception:
        pass  # continue with the Senate feed

    # ── Senate ─────────────────────────────────────────────────────────────
    try:
        r = requests.get(_SENATE_URL, timeout=20,
                         headers={"User-Agent": "UnstructuredAlpha/1.0 research@unstructuredalpha.com"})
        r.raise_for_status()
        data = r.json()
        for item in data:
            ticker = (item.get("ticker") or "").strip().upper()
            if not ticker or ticker in ("--", "N/A", ""):
                continue
            t_date = pd.to_datetime(item.get("transaction_date", ""), errors="coerce")
            d_date = pd.to_datetime(item.get("disclosure_date", ""), errors="coerce")
            if pd.isna(t_date) or t_date < cutoff:
                continue
            party_raw = item.get("party", "") or ""
            party = "Democrat" if party_raw.upper().startswith("D") else \
                    "Republican" if party_raw.upper().startswith("R") else party_raw
            records.append({
                "disclosure_date":  d_date,
                "transaction_date": t_date,
                "member":  item.get("senator", "Unknown"),
                "party":   party,
                "chamber": "Senate",
                "state":   item.get("state", ""),
                "ticker":  ticker,
                "type":    item.get("type", ""),
                "amount":  item.get("amount", ""),
            })
    except Exception:
        pass

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    return df.sort_values("disclosure_date", ascending=False).reset_index(drop=True)


def _amount_midpoint(amount_str: str) -> float:
    """Convert '$15,001 - $50,000' style string to midpoint float for sorting."""
    try:
        clean = amount_str.replace("$", "").replace(",", "").strip()
        if " - " in clean:
            lo, hi = clean.split(" - ")
            return (float(lo) + float(hi)) / 2
        return float(clean)
    except Exception:
        return 0.0


def _type_badge(tx_type: str) -> str:
    tx = (tx_type or "").lower()
    if "purchase" in tx or "buy" in tx:
        return "🟢 Buy"
    if "sale" in tx or "sell" in tx:
        return "🔴 Sell"
    return tx_type


def _party_color(party: str) -> str:
    p = (party or "").lower()
    if "democrat" in p or p == "d":
        return "#4472C4"
    if "republican" in p or p == "r":
        return "#C00000"
    return "#888888"


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL OVERLAY — cross-reference tickers with UA scores
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200, show_spinner=False, max_entries=1)
def _get_ticker_scores() -> dict:
    """Map ticker → (score, status) from all tracked signals. Safe default {}."""
    try:
        from utils.signals_cache import get_all_signal_scores
        from utils.config import SIGNALS
        # Build a ticker→signal mapping
        ticker_to_sigs: dict = {}
        for sig_id, cfg in SIGNALS.items():
            for ticker in cfg.get("tickers", []):
                ticker_to_sigs.setdefault(ticker.upper(), []).append(sig_id)

        all_sv = get_all_signal_scores()
        # Simple average score across signals mapped to each ticker
        result = {}
        for ticker, sig_ids in ticker_to_sigs.items():
            scores = [all_sv[s]["score"] for s in sig_ids if s in all_sv and not all_sv[s]["error"]]
            if scores:
                avg = sum(scores) / len(scores)
                if avg >= 65:
                    status = "bullish"
                elif avg <= 35:
                    status = "bearish"
                else:
                    status = "neutral"
                result[ticker] = {"score": round(avg, 1), "status": status}
        return result
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# PAGE LAYOUT
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("## Congressional Trade Tracker")
st.caption(
    "Real-time STOCK Act disclosures — every stock trade made by members of Congress, "
    "cross-referenced with Unstructured Alpha signal scores to detect smart-money alignment."
)

# ── Controls ──────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
with c1:
    days_back = st.selectbox("Period", [30, 60, 90, 180], index=2, format_func=lambda d: f"Last {d} days")
with c2:
    chamber_filter = st.selectbox("Chamber", ["All", "House", "Senate"])
with c3:
    party_filter = st.selectbox("Party", ["All", "Democrat", "Republican"])
with c4:
    type_filter = st.selectbox("Type", ["All", "Purchases only", "Sales only"])

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Loading congressional disclosures…"):
    df_raw = fetch_congress_trades(days=days_back)

if df_raw.empty:
    st.warning("Congressional trade endpoints are unavailable. No placeholder trades are shown.")

# ── Filter ────────────────────────────────────────────────────────────────────
df = df_raw.copy()
cutoff = datetime.now() - timedelta(days=days_back)
df = df[df["transaction_date"] >= cutoff]

if chamber_filter != "All":
    df = df[df["chamber"] == chamber_filter]
if party_filter != "All":
    df = df[df["party"].str.contains(party_filter, case=False, na=False)]
if type_filter == "Purchases only":
    df = df[df["type"].str.lower().str.contains("purchase|buy", na=False)]
elif type_filter == "Sales only":
    df = df[df["type"].str.lower().str.contains("sale|sell", na=False)]

if df.empty:
    st.info("No trades match the current filters.")
    st.stop()

# ── Ticker signal scores ───────────────────────────────────────────────────────
ticker_scores = _get_ticker_scores()

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY METRICS
# ─────────────────────────────────────────────────────────────────────────────
buys  = df[df["type"].str.lower().str.contains("purchase|buy", na=False)]
sells = df[df["type"].str.lower().str.contains("sale|sell", na=False)]
unique_tickers = df["ticker"].nunique()
unique_members = df["member"].nunique()

# Signal alignment: purchases in tickers where UA is also bullish
if ticker_scores:
    aligned_buys = buys[buys["ticker"].map(
        lambda t: ticker_scores.get(t, {}).get("status") == "bullish"
    )]
    alignment_pct = len(aligned_buys) / max(len(buys), 1) * 100
else:
    alignment_pct = None

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Trades", f"{len(df):,}")
m2.metric("Members Active", f"{unique_members}")
m3.metric("Unique Tickers", f"{unique_tickers}")
if alignment_pct is not None:
    m4.metric("Buy ↔ Signal Alignment", f"{alignment_pct:.0f}%",
              help="% of congressional purchases where UA signals are also bullish")
else:
    m4.metric("Net Buy/Sell", f"{len(buys)}/{len(sells)}")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# CHARTS — Top tickers + Party split
# ─────────────────────────────────────────────────────────────────────────────
ch_left, ch_right = st.columns([3, 2])

with ch_left:
    st.markdown("#### Most Traded Tickers")
    ticker_counts = df.groupby("ticker").size().sort_values(ascending=False).head(15)
    buy_counts  = buys.groupby("ticker").size()
    sell_counts = sells.groupby("ticker").size()

    top_tickers = ticker_counts.index.tolist()
    bc = [buy_counts.get(t, 0) for t in top_tickers]
    sc = [sell_counts.get(t, 0) for t in top_tickers]

    # Color bars by UA signal status
    ua_colors = []
    for t in top_tickers:
        status = ticker_scores.get(t, {}).get("status", "neutral")
        ua_colors.append("#4CAF50" if status == "bullish" else
                         "#EF5350" if status == "bearish" else "#888888")

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(name="Buys",  x=top_tickers, y=bc, marker_color="#4CAF50"))
    fig_bar.add_trace(go.Bar(name="Sells", x=top_tickers, y=sc, marker_color="#EF5350"))
    fig_bar.update_layout(
        barmode="group", height=320,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=0, r=0, t=10, b=40),
        font=dict(color="#8892AA", size=11),
        xaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
    )
    st.plotly_chart(fig_bar, use_container_width=True)

with ch_right:
    st.markdown("#### Purchases by Party")
    party_buys = buys.groupby("party").size().reset_index(name="count")
    if not party_buys.empty:
        colors_pie = [_party_color(p) for p in party_buys["party"]]
        fig_pie = go.Figure(go.Pie(
            labels=party_buys["party"], values=party_buys["count"],
            marker_colors=colors_pie, hole=0.45,
            textfont=dict(color="#0F1118", size=12),
        ))
        fig_pie.update_layout(
            height=280, margin=dict(l=0, r=0, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(font=dict(color="#8892AA")),
            showlegend=True,
        )
        st.plotly_chart(fig_pie, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL ALIGNMENT TABLE — Congress buys where UA also bullish
# ─────────────────────────────────────────────────────────────────────────────
if ticker_scores:
    st.divider()
    st.markdown("#### 🎯 Smart Money Alignment — Congress Buys + UA Bullish Signal")
    st.caption("Transactions where a member bought stock AND our macro signals rate the ticker as bullish.")

    aligned = buys.copy()
    aligned["ua_score"]  = aligned["ticker"].map(lambda t: ticker_scores.get(t, {}).get("score", None))
    aligned["ua_status"] = aligned["ticker"].map(lambda t: ticker_scores.get(t, {}).get("status", ""))
    aligned = aligned[aligned["ua_status"] == "bullish"].sort_values("ua_score", ascending=False)

    if aligned.empty:
        st.info("No purchases currently align with bullish UA signals in the filtered date range.")
    else:
        display_cols = ["transaction_date", "member", "party", "chamber", "ticker", "amount", "ua_score"]
        aligned_disp = aligned[display_cols].copy()
        aligned_disp["transaction_date"] = aligned_disp["transaction_date"].dt.strftime("%Y-%m-%d")
        aligned_disp["ua_score"] = aligned_disp["ua_score"].apply(lambda x: f"{x:.0f}/100" if x else "—")
        aligned_disp = aligned_disp.rename(columns={
            "transaction_date": "Trade Date", "member": "Member", "party": "Party",
            "chamber": "Chamber", "ticker": "Ticker", "amount": "Amount", "ua_score": "UA Score",
        })
        st.dataframe(aligned_disp, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# FULL TRADE TABLE
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.markdown("#### All Recent Trades")

# Ticker filter
ticker_search = st.text_input("Filter by ticker", placeholder="e.g. NVDA").strip().upper()

df_show = df.copy()
if ticker_search:
    df_show = df_show[df_show["ticker"] == ticker_search]

# Add UA signal column
df_show["ua_score"]  = df_show["ticker"].map(lambda t: ticker_scores.get(t, {}).get("score", None))
df_show["ua_status"] = df_show["ticker"].map(lambda t: ticker_scores.get(t, {}).get("status", ""))
df_show["trade_type"] = df_show["type"].apply(_type_badge)

display = df_show[[
    "transaction_date", "disclosure_date", "member", "party",
    "chamber", "ticker", "trade_type", "amount", "ua_score", "ua_status",
]].copy()
display["transaction_date"]  = display["transaction_date"].dt.strftime("%Y-%m-%d")
display["disclosure_date"]   = display["disclosure_date"].dt.strftime("%Y-%m-%d")
display["ua_score"] = display["ua_score"].apply(lambda x: f"{x:.0f}" if x == x and x is not None else "—")
display["ua_status"] = display["ua_status"].apply(
    lambda s: "🟢 Bullish" if s == "bullish" else "🔴 Bearish" if s == "bearish" else "⚪ Neutral" if s else "—"
)
display = display.rename(columns={
    "transaction_date": "Trade Date", "disclosure_date": "Filed",
    "member": "Member", "party": "Party", "chamber": "Chamber",
    "ticker": "Ticker", "trade_type": "Type", "amount": "Amount",
    "ua_score": "UA Score", "ua_status": "UA Signal",
})

st.dataframe(display.head(300), use_container_width=True, hide_index=True)
st.caption(
    "**Trade Date** = when the transaction actually occurred. "
    "**Filed** = when the disclosure was received by the system — the earliest a market participant "
    "could have acted on this information. STOCK Act requires filing within 45 days of the trade; "
    "late filers are common. UA's signal engine uses the Filed date as the 'known as of' timestamp "
    "to prevent the congressional signal from appearing more predictive than it actually is."
)

# ─────────────────────────────────────────────────────────────────────────────
# NET SENTIMENT PER TICKER
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
st.markdown("#### Congressional Net Sentiment by Ticker")
st.caption("Positive = more buys than sells. Bars colored by UA signal status.")

buy_n  = buys.groupby("ticker").size()
sell_n = sells.groupby("ticker").size()
all_t  = set(buy_n.index) | set(sell_n.index)
net_df = pd.DataFrame({
    "ticker": list(all_t),
    "net":    [buy_n.get(t, 0) - sell_n.get(t, 0) for t in all_t],
}).sort_values("net", ascending=False).head(20)

if not net_df.empty:
    net_colors = []
    for t in net_df["ticker"]:
        status = ticker_scores.get(t, {}).get("status", "neutral")
        if net_df.loc[net_df["ticker"] == t, "net"].values[0] >= 0:
            net_colors.append("#4CAF50" if status == "bullish" else "#A0A8B8")
        else:
            net_colors.append("#EF5350" if status == "bearish" else "#A0A8B8")

    fig_net = go.Figure(go.Bar(
        x=net_df["ticker"], y=net_df["net"],
        marker_color=net_colors,
        hovertemplate="%{x}: %{y:+d} net<extra></extra>",
    ))
    fig_net.update_layout(
        height=280, margin=dict(l=0, r=0, t=10, b=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8892AA", size=11),
        xaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.06)", title="Net Trades (Buy - Sell)"),
        showlegend=False,
    )
    fig_net.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)
    st.plotly_chart(fig_net, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# METHODOLOGY FOOTER
# ─────────────────────────────────────────────────────────────────────────────
with st.expander("Data sources & methodology"):
    st.markdown("""
**Data source:** Official STOCK Act disclosures filed with the U.S. House of Representatives
([disclosures.house.gov](https://disclosures.house.gov)) and U.S. Senate
([efds.senate.gov](https://efds.senate.gov)), aggregated and parsed daily by the open-source
[House Stock Watcher](https://housestockwatcher.com) and Senate Stock Watcher community projects.

**Filing lag:** STOCK Act requires disclosure within 45 days of the transaction. The trade date
shown is the actual transaction date; the disclosure date is when it was filed publicly.

**Signal Alignment:** UA macro signal scores are computed independently of congressional trade data.
"Bullish" alignment means a purchase was made in a ticker where the *existing* alternative data
signals already rate the macro environment as bullish — it does not imply causation or prediction.

**Limitations:** This is not investment advice. Congressional members may have material non-public
information unavailable to retail investors. Some tickers cannot be matched to UA signals.
""")
