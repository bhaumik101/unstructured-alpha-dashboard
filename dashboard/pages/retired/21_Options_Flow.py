"""
Page 21 — Unusual Options Activity
Real-time options chain analysis powered by yfinance. Surfaces contracts where
today's volume exceeds open interest — a signal that fresh, directional bets
are being placed rather than existing positions being closed.

No API key required. Data from yfinance options endpoints (15-min delayed).
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.header import render_header, render_sidebar_base, render_page_header

st.set_page_config(page_title="Options Flow — UA", layout="wide")

from utils.billing import require_pro
require_pro("Options Flow")

render_header("Unusual Options Activity")
render_sidebar_base()

render_page_header(
    "Unusual Options Activity",
    "Detect outsized options positioning as a potential directional signal.",
    icon="📡",
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_POPULAR = [
    "SPY", "QQQ", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL",
    "TSLA", "AMD", "PLTR", "XOM", "JPM", "GS", "CCJ", "CEG", "VST",
]

_UNUSUAL_VOL_OI_THRESHOLD = 1.0   # vol/OI ratio to flag as "unusual"
_UNUSUAL_MIN_VOLUME       = 100   # minimum absolute volume to filter noise


def _flag_unusual(df: pd.DataFrame) -> pd.DataFrame:
    """Add 'unusual' bool column: vol/OI > threshold AND absolute vol > min."""
    if df.empty:
        return df
    df = df.copy()
    oi = df.get("openInterest", pd.Series(dtype=float)).fillna(0)
    vol = df.get("volume", pd.Series(dtype=float)).fillna(0)
    df["vol_oi_ratio"] = vol / oi.clip(lower=1)
    df["unusual"] = (df["vol_oi_ratio"] >= _UNUSUAL_VOL_OI_THRESHOLD) & (vol >= _UNUSUAL_MIN_VOLUME)
    return df


def _fmt_num(x) -> str:
    if x != x or x is None:
        return "—"
    x = float(x)
    if x >= 1_000_000:
        return f"{x/1_000_000:.1f}M"
    if x >= 1_000:
        return f"{x/1_000:.0f}K"
    return f"{x:.0f}"


def _itm_pct(df: pd.DataFrame, current_price: float | None, call: bool) -> str:
    """% of contracts ITM."""
    if df.empty or not current_price:
        return "—"
    if call:
        itm = (df["strike"] <= current_price).sum()
    else:
        itm = (df["strike"] >= current_price).sum()
    return f"{100 * itm / max(len(df), 1):.0f}%"


def _pcr_gauge(pcr: float) -> go.Figure:
    """Speedometer-style gauge for put/call ratio."""
    if pcr != pcr:
        pcr = 1.0
    capped = min(pcr, 3.0)
    if pcr < 0.7:
        label, color = "Bullish (Low Fear)", "#4CAF50"
    elif pcr < 1.1:
        label, color = "Neutral", "#C9A84C"
    elif pcr < 1.5:
        label, color = "Elevated Fear", "#FF9800"
    else:
        label, color = "Extreme Fear", "#EF5350"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=pcr,
        number={"suffix": "x", "font": {"color": color, "size": 28}},
        title={"text": f"Put/Call Ratio<br><span style='font-size:12px;color:{color}'>{label}</span>",
               "font": {"color": "#8892AA", "size": 14}},
        gauge={
            "axis": {"range": [0, 3], "tickcolor": "#8A9AB8", "tickfont": {"size": 10}},
            "bar":  {"color": color, "thickness": 0.25},
            "bgcolor": "rgba(0,0,0,0)",
            "bordercolor": "rgba(0,0,0,0)",
            "steps": [
                {"range": [0,   0.7], "color": "rgba(76,175,80,0.15)"},
                {"range": [0.7, 1.1], "color": "rgba(201,168,76,0.15)"},
                {"range": [1.1, 1.5], "color": "rgba(255,152,0,0.15)"},
                {"range": [1.5, 3.0], "color": "rgba(239,83,80,0.15)"},
            ],
            "threshold": {"line": {"color": "#0F1118", "width": 2}, "value": 1.0},
        },
    ))
    fig.update_layout(
        height=220, margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#8892AA"),
    )
    return fig


def _iv_surface(calls: pd.DataFrame, puts: pd.DataFrame, current_price: float | None) -> go.Figure:
    """IV smile/surface: IV vs strike, coloured by call/put and expiration."""
    fig = go.Figure()

    for exp in calls["expiration"].unique() if not calls.empty else []:
        c = calls[calls["expiration"] == exp].copy()
        c = c[(c["impliedVolatility"] > 0) & (c["volume"] > 0)].sort_values("strike")
        if len(c) < 3:
            continue
        fig.add_trace(go.Scatter(
            x=c["strike"], y=(c["impliedVolatility"] * 100).round(1),
            mode="lines+markers", name=f"Calls {exp}",
            line=dict(color="#4CAF50", width=1.5),
            marker=dict(size=4),
            hovertemplate=f"Call {exp} — strike $%{{x:.0f}} IV %{{y:.1f}}%<extra></extra>",
        ))

    for exp in puts["expiration"].unique() if not puts.empty else []:
        p = puts[puts["expiration"] == exp].copy()
        p = p[(p["impliedVolatility"] > 0) & (p["volume"] > 0)].sort_values("strike")
        if len(p) < 3:
            continue
        fig.add_trace(go.Scatter(
            x=p["strike"], y=(p["impliedVolatility"] * 100).round(1),
            mode="lines+markers", name=f"Puts {exp}",
            line=dict(color="#EF5350", width=1.5, dash="dot"),
            marker=dict(size=4),
            hovertemplate=f"Put {exp} — strike $%{{x:.0f}} IV %{{y:.1f}}%<extra></extra>",
        ))

    if current_price:
        fig.add_vline(x=current_price, line_color="rgba(255,255,255,0.4)",
                      line_dash="dash", annotation_text=f"  Current ${current_price:,.2f}",
                      annotation_font_color="#8892AA")

    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=20, b=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8892AA", size=11),
        xaxis=dict(title="Strike Price", gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(title="Implied Volatility (%)", gridcolor="rgba(255,255,255,0.06)"),
        legend=dict(font=dict(size=10), orientation="h", y=1.05),
        showlegend=True,
    )
    return fig


def _volume_bars(calls: pd.DataFrame, puts: pd.DataFrame, exp: str | None) -> go.Figure:
    """Volume by strike for a chosen expiration — calls vs puts side by side."""
    if exp:
        c = calls[calls["expiration"] == exp] if not calls.empty else pd.DataFrame()
        p = puts[puts["expiration"] == exp]  if not puts.empty  else pd.DataFrame()
    else:
        c, p = calls, puts

    c = c.sort_values("strike") if not c.empty else c
    p = p.sort_values("strike") if not p.empty else p

    fig = go.Figure()
    if not c.empty:
        fig.add_trace(go.Bar(
            x=c["strike"], y=c["volume"].fillna(0),
            name="Call Volume", marker_color="#4CAF50", opacity=0.75,
            hovertemplate="Call $%{x:.0f} — vol %{y:,.0f}<extra></extra>",
        ))
    if not p.empty:
        fig.add_trace(go.Bar(
            x=p["strike"], y=p["volume"].fillna(0),
            name="Put Volume",  marker_color="#EF5350", opacity=0.75,
            hovertemplate="Put $%{x:.0f} — vol %{y:,.0f}<extra></extra>",
        ))

    fig.update_layout(
        barmode="group", height=280, margin=dict(l=0, r=0, t=10, b=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8892AA", size=11),
        xaxis=dict(title="Strike", gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(title="Volume", gridcolor="rgba(255,255,255,0.06)"),
        legend=dict(font=dict(size=10), orientation="h", y=1.05),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# PAGE UI
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("## Unusual Options Activity")
st.caption(
    "Real-time options flow powered by yfinance — no API key required. "
    "'Unusual' = today's volume exceeds open interest, signalling fresh directional bets."
)

# ── Ticker selector ───────────────────────────────────────────────────────────
col_pick, col_custom = st.columns([2, 1])
with col_pick:
    selected_popular = st.selectbox(
        "Popular tickers", ["(enter custom below)"] + _POPULAR,
        index=0, key="opts_popular",
    )
with col_custom:
    custom_ticker = st.text_input(
        "Or enter any ticker", value="", placeholder="e.g. PLTR",
        key="opts_custom",
    ).strip().upper()

ticker = custom_ticker if custom_ticker else (selected_popular if selected_popular != "(enter custom below)" else None)

if not ticker:
    st.info("Select a ticker above to view its options flow.")
    st.stop()

# ── Load ──────────────────────────────────────────────────────────────────────
from utils.fetchers import fetch_options_chain  # noqa: E402 — deferred to avoid import at module level

with st.spinner(f"Loading options chain for **{ticker}**…"):
    chain = fetch_options_chain(ticker)

if not chain:
    st.error(f"Could not load options data for **{ticker}**. The ticker may not have listed options, or data is temporarily unavailable.")
    st.stop()

calls_raw = chain.get("calls", pd.DataFrame())
puts_raw  = chain.get("puts",  pd.DataFrame())
pcr       = chain.get("put_call_ratio", float("nan"))
spot      = chain.get("current_price", None)
expirations = chain.get("expirations", [])

calls_raw = _flag_unusual(calls_raw)
puts_raw  = _flag_unusual(puts_raw)

unusual_calls = calls_raw[calls_raw["unusual"]] if not calls_raw.empty else pd.DataFrame()
unusual_puts  = puts_raw[puts_raw["unusual"]]   if not puts_raw.empty  else pd.DataFrame()

# ── Header metrics ────────────────────────────────────────────────────────────
st.markdown(f"### {ticker}" + (f" — ${spot:,.2f}" if spot else ""))

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Put/Call Ratio", f"{pcr:.2f}x" if pcr == pcr else "—",
          help="Total put volume / total call volume across all expirations loaded")
m2.metric("Unusual Calls", f"{len(unusual_calls):,}")
m3.metric("Unusual Puts",  f"{len(unusual_puts):,}")
m4.metric("Total Call Vol",
          _fmt_num(calls_raw["volume"].sum() if not calls_raw.empty else 0))
m5.metric("Total Put Vol",
          _fmt_num(puts_raw["volume"].sum() if not puts_raw.empty  else 0))

st.divider()

# ── Layout: gauge + IV smile ──────────────────────────────────────────────────
g_col, iv_col = st.columns([1, 3])
with g_col:
    if pcr == pcr:
        st.plotly_chart(_pcr_gauge(pcr), use_container_width=True)
    else:
        st.markdown("**Put/Call Ratio:** unavailable")

with iv_col:
    st.markdown("#### Implied Volatility Smile")
    # Show only first 3 expirations for readability
    c_sub = calls_raw[calls_raw["expiration"].isin(expirations[:3])] if not calls_raw.empty else pd.DataFrame()
    p_sub = puts_raw[puts_raw["expiration"].isin(expirations[:3])]   if not puts_raw.empty  else pd.DataFrame()
    st.plotly_chart(_iv_surface(c_sub, p_sub, spot), use_container_width=True)

# ── Volume by strike ──────────────────────────────────────────────────────────
st.markdown("#### Volume by Strike")
exp_options = ["All expirations"] + list(expirations[:6])
chosen_exp = st.selectbox("Expiration", exp_options, key="opts_exp")
exp_filter = None if chosen_exp == "All expirations" else chosen_exp
st.plotly_chart(_volume_bars(calls_raw, puts_raw, exp_filter), use_container_width=True)

st.divider()

# ── Unusual contracts table ───────────────────────────────────────────────────
st.markdown("#### 🔥 Unusual Contracts — Volume > Open Interest")
st.caption(
    f"Contracts where Vol/OI ≥ {_UNUSUAL_VOL_OI_THRESHOLD:.0f}x AND volume ≥ {_UNUSUAL_MIN_VOLUME:,}. "
    "These suggest fresh positioning, not just rolling existing trades."
)

tab_calls, tab_puts, tab_combined = st.tabs(["Unusual Calls", "Unusual Puts", "Combined (all)"])

_DISPLAY_COLS = ["expiration", "strike", "lastPrice", "bid", "ask",
                 "volume", "openInterest", "vol_oi_ratio", "impliedVolatility", "inTheMoney"]
_COL_LABELS = {
    "expiration": "Expiry", "strike": "Strike", "lastPrice": "Last",
    "bid": "Bid", "ask": "Ask", "volume": "Volume", "openInterest": "Open Int",
    "vol_oi_ratio": "Vol/OI", "impliedVolatility": "IV", "inTheMoney": "ITM",
}


def _prep_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cols = [c for c in _DISPLAY_COLS if c in df.columns]
    out = df[cols].copy()
    if "impliedVolatility" in out.columns:
        out["impliedVolatility"] = (out["impliedVolatility"] * 100).round(1).astype(str) + "%"
    if "vol_oi_ratio" in out.columns:
        out["vol_oi_ratio"] = out["vol_oi_ratio"].round(2)
    if "lastPrice" in out.columns:
        out["lastPrice"] = out["lastPrice"].apply(lambda x: f"${x:.2f}" if x == x else "—")
    if "bid" in out.columns:
        out["bid"] = out["bid"].apply(lambda x: f"${x:.2f}" if x == x else "—")
    if "ask" in out.columns:
        out["ask"] = out["ask"].apply(lambda x: f"${x:.2f}" if x == x else "—")
    if "strike" in out.columns:
        out["strike"] = out["strike"].apply(lambda x: f"${x:.1f}")
    if "inTheMoney" in out.columns:
        out["inTheMoney"] = out["inTheMoney"].map({True: "✅ ITM", False: "OTM"})
    out = out.rename(columns=_COL_LABELS)
    return out.sort_values("Vol/OI", ascending=False) if "Vol/OI" in out.columns else out


with tab_calls:
    if unusual_calls.empty:
        st.info("No unusual call activity found with current thresholds.")
    else:
        st.dataframe(_prep_display(unusual_calls), use_container_width=True, hide_index=True)

with tab_puts:
    if unusual_puts.empty:
        st.info("No unusual put activity found with current thresholds.")
    else:
        st.dataframe(_prep_display(unusual_puts), use_container_width=True, hide_index=True)

with tab_combined:
    all_unusual = pd.DataFrame()
    if not unusual_calls.empty:
        c_tag = unusual_calls.copy()
        c_tag["type"] = "Call"
        all_unusual = pd.concat([all_unusual, c_tag], ignore_index=True)
    if not unusual_puts.empty:
        p_tag = unusual_puts.copy()
        p_tag["type"] = "Put"
        all_unusual = pd.concat([all_unusual, p_tag], ignore_index=True)
    if all_unusual.empty:
        st.info("No unusual activity found.")
    else:
        display_combined = all_unusual.copy()
        prep = _prep_display(display_combined)
        if "type" in display_combined.columns:
            prep.insert(0, "Type", display_combined["type"].values[:len(prep)])
        st.dataframe(prep, use_container_width=True, hide_index=True)

# ── Full chain viewer ─────────────────────────────────────────────────────────
st.divider()
with st.expander("Full options chain (all contracts)"):
    exp_chain = st.selectbox("Expiration", list(expirations[:6]), key="full_chain_exp")
    fc_tab_c, fc_tab_p = st.tabs(["Calls", "Puts"])

    def _full_table(df: pd.DataFrame, exp: str):
        sub = df[df["expiration"] == exp] if not df.empty else pd.DataFrame()
        if sub.empty:
            st.info("No data for this expiration.")
            return
        cols = [c for c in _DISPLAY_COLS + ["vol_oi_ratio"] if c in sub.columns]
        out = sub[cols].copy()
        if "impliedVolatility" in out.columns:
            out["impliedVolatility"] = (out["impliedVolatility"] * 100).round(1).astype(str) + "%"
        if "vol_oi_ratio" in out.columns:
            out["vol_oi_ratio"] = out["vol_oi_ratio"].round(2)
        out = out.rename(columns=_COL_LABELS)
        st.dataframe(out, use_container_width=True, hide_index=True)

    with fc_tab_c:
        _full_table(calls_raw, exp_chain)
    with fc_tab_p:
        _full_table(puts_raw, exp_chain)

# ── Methodology note ──────────────────────────────────────────────────────────
with st.expander("Methodology & interpretation"):
    st.markdown("""
**What makes a contract "unusual"?**

Volume-to-Open-Interest (Vol/OI) ratio ≥ 1.0 means today's traded volume equals or exceeds
yesterday's total open interest. Since every new contract requires a buyer AND seller,
a ratio >1 is only possible if entirely new positions are being opened — it cannot happen
from existing holders simply closing positions.

**Put/Call Ratio interpretation:**
- < 0.7 = Sentiment is bullish; demand for calls far outpaces puts
- 0.7–1.1 = Neutral / balanced market hedging
- 1.1–1.5 = Elevated fear; put buying picking up
- > 1.5 = Extreme fear / potential capitulation signal

Note: High P/C ratio is a CONTRARIAN signal — when everyone is hedging, it can mark bottoms.

**IV Smile:** Implied volatility typically rises for deep out-of-the-money puts
("put skew") as traders hedge tail risk more aggressively than calls. A flatter smile
means the market sees symmetric risk in both directions.

**Data:** yfinance options data is delayed approximately 15 minutes for equity options.
Options data is not available for all tickers (ETFs, some small-caps, non-US listings).
""")
