"""
Page 21 — Unusual Options Activity
Real-time options chain analysis powered by yfinance. Surfaces contracts where
today's volume exceeds open interest — a signal that fresh, directional bets
are being placed rather than existing positions being closed.

No API key required. Data from yfinance options endpoints (15-min delayed).
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.options_metrics import (
    CONTRACT_MULTIPLIER,
    days_to_expiration,
    summarize,
)
from utils.theme import PLOTLY_CONFIG

st.set_page_config(page_title="Options Flow — UA", layout="wide")

from utils.billing import require_pro
require_pro("Options Flow")

render_header("Unusual Options Activity")
_options_section = render_sidebar_base(
    page_title="Options Flow",
    sections=("Market Snapshot", "Strike Positioning", "Unusual Activity", "Full Chain", "Methodology"),
    section_key="options_flow_section_rail",
)
try:
    from utils.instrumentation import record_once
    record_once("options_flow_viewed")
except Exception:
    pass

render_page_header(
    "Unusual Options Activity",
    "Detect outsized options positioning as a potential directional signal.",
    icon="",
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


# _itm_pct lived here: defined, never called, and counting rows rather than
# weighting by open interest — it treated a strike with 4 open contracts the
# same as one with 40,000. Replaced by options_metrics.itm_fraction, which is
# OI-weighted and now surfaced in the header metrics.


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

    # Every expiration previously drew in the same green (calls) or red (puts),
    # so three expirations produced three indistinguishable curves and a legend
    # that was the only way to tell them apart. Nearer expiries now draw
    # brightest, which also matches which curve the user most likely cares about.
    _CALL_SHADES = ["#4CAF50", "#2E7D46", "#1B5E2A"]
    _PUT_SHADES = ["#EF5350", "#B03A38", "#7A2725"]

    call_exps = list(calls["expiration"].unique()) if not calls.empty else []
    put_exps = list(puts["expiration"].unique()) if not puts.empty else []

    for i, exp in enumerate(call_exps):
        c = calls[calls["expiration"] == exp].copy()
        c = c[(c["impliedVolatility"] > 0) & (c["volume"] > 0)].sort_values("strike")
        if len(c) < 3:
            continue
        fig.add_trace(go.Scatter(
            x=c["strike"], y=(c["impliedVolatility"] * 100).round(1),
            mode="lines+markers", name=f"Calls {exp}",
            line=dict(color=_CALL_SHADES[i % len(_CALL_SHADES)], width=1.5),
            marker=dict(size=4),
            hovertemplate=f"Call {exp} — strike $%{{x:.0f}} IV %{{y:.1f}}%<extra></extra>",
        ))

    for i, exp in enumerate(put_exps):
        p = puts[puts["expiration"] == exp].copy()
        p = p[(p["impliedVolatility"] > 0) & (p["volume"] > 0)].sort_values("strike")
        if len(p) < 3:
            continue
        fig.add_trace(go.Scatter(
            x=p["strike"], y=(p["impliedVolatility"] * 100).round(1),
            mode="lines+markers", name=f"Puts {exp}",
            line=dict(color=_PUT_SHADES[i % len(_PUT_SHADES)], width=1.5, dash="dot"),
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


def _oi_bars(calls: pd.DataFrame, puts: pd.DataFrame, exp: str | None,
             spot: float | None, max_pain_strike: float | None) -> go.Figure:
    """Open interest by strike — the standing position.

    The page previously charted volume only. Volume is one day of churn; open
    interest is what remains held, and the two often peak at different strikes.
    Without this chart the max-pain figure in the header had nothing to stand on.
    """
    c = calls[calls["expiration"] == exp] if exp and not calls.empty else calls
    p = puts[puts["expiration"] == exp] if exp and not puts.empty else puts

    fig = go.Figure()
    if c is not None and not c.empty and "openInterest" in c.columns:
        agg = c.groupby("strike", as_index=False)["openInterest"].sum()
        fig.add_trace(go.Bar(
            x=agg["strike"], y=agg["openInterest"], name="Call OI",
            marker_color="#4CAF50", opacity=0.75,
            hovertemplate="Call $%{x:.0f} — OI %{y:,.0f}<extra></extra>",
        ))
    if p is not None and not p.empty and "openInterest" in p.columns:
        agg = p.groupby("strike", as_index=False)["openInterest"].sum()
        fig.add_trace(go.Bar(
            x=agg["strike"], y=agg["openInterest"], name="Put OI",
            marker_color="#EF5350", opacity=0.75,
            hovertemplate="Put $%{x:.0f} — OI %{y:,.0f}<extra></extra>",
        ))

    if spot:
        fig.add_vline(x=spot, line_color="rgba(255,255,255,0.45)", line_dash="dash",
                      annotation_text=f" spot ${spot:,.2f}",
                      annotation_font_color="#8892AA", annotation_font_size=10)
    if max_pain_strike:
        fig.add_vline(x=max_pain_strike, line_color="#C9A84C", line_dash="dot",
                      annotation_text=f" max pain ${max_pain_strike:,.0f}",
                      annotation_font_color="#C9A84C", annotation_font_size=10)

    fig.update_layout(
        barmode="group", height=280, margin=dict(l=0, r=0, t=10, b=40),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8892AA", size=11),
        xaxis=dict(title="Strike", gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(title="Open Interest", gridcolor="rgba(255,255,255,0.06)"),
        legend=dict(font=dict(size=10), orientation="h", y=1.05),
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

if _options_section != "Methodology":
    # ── Ticker selector ───────────────────────────────────────────────────────────
    col_pick, col_custom = st.columns([2, 1])
    with col_pick:
        # Search the full US-listed universe (~12.6k) — options chains exist for far
        # more than our scored tickers. index=None + placeholder (not a sentinel
        # option, which Streamlit renders as the box's VALUE and breaks searching).
        try:
            from utils.symbols import get_symbol_index as _gsi
            _of_idx = dict(_gsi())
        except Exception:
            _of_idx = {t: t for t in _POPULAR}
        selected_popular = st.selectbox(
            "Search any stock", list(_of_idx.keys()), index=None,
            placeholder=" Symbol or company…",
            format_func=lambda t: _of_idx.get(t, t), key="opts_popular",
        )
    with col_custom:
        custom_ticker = st.text_input(
            "Or enter any ticker", value="", placeholder="e.g. PLTR",
            key="opts_custom",
        ).strip().upper()

    ticker = (custom_ticker or selected_popular or "").strip().upper() or None

    if not ticker:
        st.info("Select a ticker above to view its options flow.")
        st.stop()

    # ── Load ──────────────────────────────────────────────────────────────────────
    from utils.fetchers import fetch_options_chain  # noqa: E402 — deferred to avoid import at module level

    # Per-user rate limit — options chains are provider-heavy (yfinance pulls up to 6
    # expirations). Dedupe by distinct ticker so reruns for the SAME ticker (which hit
    # the 30-min cache, no provider call) aren't throttled — only a new ticker counts.
    from utils.ratelimit import guard  # noqa: E402
    if st.session_state.get("_opts_rl_ticker") != ticker:
        _rl_ok, _rl_retry = guard("options_flow")
        st.session_state["_opts_rl_ticker"] = ticker
        st.session_state["_opts_rl_blocked"] = (not _rl_ok, _rl_retry)
    _opts_blocked, _opts_retry = st.session_state.get("_opts_rl_blocked", (False, 0))
    if _opts_blocked:
        st.warning(f"You're loading options chains quickly — give it about "
                   f"{_opts_retry}s and try again.")
        st.stop()

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

if _options_section == "Market Snapshot":
    # ── Header metrics ────────────────────────────────────────────────────────────
    st.markdown(f"### {ticker}" + (f" — ${spot:,.2f}" if spot else ""))

    _S = summarize(calls_raw, puts_raw, spot,
                   nearest_expiration=expirations[0] if expirations else None)


    def _pct(x, dp: int = 0) -> str:
        return f"{x * 100:.{dp}f}%" if x is not None else "—"


    def _ratio(x) -> str:
        return f"{x:.2f}x" if x is not None else "—"


    def _usd(x) -> str:
        return f"${_fmt_num(x)}" if x else "—"


    # Row 1 — flow: what traded today, in contracts and in dollars.
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("P/C Ratio · Volume", _ratio(_S["pcr_volume"]),
              help="Put volume / call volume across loaded expirations — today's flow.")
    m2.metric("P/C Ratio · Open Int", _ratio(_S["pcr_oi"]),
              help="Put OI / call OI — positions still held, not just today's trades. "
                   "This routinely disagrees with the volume ratio.")
    m3.metric("Call Premium", _usd(_S["call_premium"]),
              help="Volume x last price x 100. Dollars behind call buying.")
    m4.metric("Put Premium", _usd(_S["put_premium"]),
              help="Volume x last price x 100. Dollars behind put buying.")
    _bias = _S["net_premium_bias"]
    m5.metric("Net Premium Bias",
              ("Calls " if _bias > 0 else "Puts ") + _usd(abs(_bias)) if _bias else "—",
              delta=("bullish tilt" if _bias > 0 else "bearish tilt") if _bias else None,
              delta_color="normal" if _bias > 0 else "inverse",
              help="Call premium minus put premium — which side the money is on.")
    m6.metric("Max Pain", f"${_S['max_pain']:,.0f}" if _S["max_pain"] else "—",
              delta=(f"{(_S['max_pain'] - spot) / spot * 100:+.1f}% vs spot"
                     if _S["max_pain"] and spot else None),
              delta_color="off",
              help="Strike where the most open contracts expire worthless. "
                   "A positioning statistic, not a price target.")

    # Row 2 — structure: what is standing open, how it is priced, how tradeable it is.
    n1, n2, n3, n4, n5, n6 = st.columns(6)
    n1.metric("Call Volume", _fmt_num(_S["call_volume"]))
    n2.metric("Put Volume", _fmt_num(_S["put_volume"]))
    n3.metric("Call Open Int", _fmt_num(_S["call_oi"]),
              help="Contracts still open — the standing position, versus volume's daily churn.")
    n4.metric("Put Open Int", _fmt_num(_S["put_oi"]))
    n5.metric("ATM IV",
              f"{_S['atm_iv_call']:.1f}%" if _S["atm_iv_call"] is not None else "—",
              delta=(f"puts {_S['atm_iv_put']:.1f}%" if _S["atm_iv_put"] is not None else None),
              delta_color="off",
              help="Implied vol at the strike nearest spot. A chain-wide average would be "
                   "dominated by illiquid far-OTM contracts.")
    n6.metric("Nearest Expiry",
              f"{_S['dte']}d" if _S["dte"] is not None else "—",
              delta=(expirations[0] if expirations else None), delta_color="off")

    # Row 3 — positioning and liquidity context.
    o1, o2, o3, o4, o5, o6 = st.columns(6)
    o1.metric("Unusual Calls", f"{len(unusual_calls):,}")
    o2.metric("Unusual Puts", f"{len(unusual_puts):,}")
    o3.metric("Calls ITM", _pct(_S["itm_calls"]),
              help="Share of call open interest currently in the money, OI-weighted.")
    o4.metric("Puts ITM", _pct(_S["itm_puts"]))
    o5.metric("Call Spread", f"{_S['call_spread_pct']:.1f}%" if _S["call_spread_pct"] is not None else "—",
              help="Median bid-ask as a percent of mid. Wide spreads mean the quoted "
                   "prices are not realistically tradeable.")
    o6.metric("Put Spread", f"{_S['put_spread_pct']:.1f}%" if _S["put_spread_pct"] is not None else "—")

    st.divider()

    # ── Layout: gauge + IV smile ──────────────────────────────────────────────────
    g_col, iv_col = st.columns([1, 3])
    with g_col:
        if pcr == pcr:
            st.plotly_chart(_pcr_gauge(pcr), use_container_width=True, config=PLOTLY_CONFIG, theme=None)
        else:
            st.markdown("**Put/Call Ratio:** unavailable")

    with iv_col:
        st.markdown("#### Implied Volatility Smile")
        # Show only first 3 expirations for readability
        c_sub = calls_raw[calls_raw["expiration"].isin(expirations[:3])] if not calls_raw.empty else pd.DataFrame()
        p_sub = puts_raw[puts_raw["expiration"].isin(expirations[:3])]   if not puts_raw.empty  else pd.DataFrame()
        st.plotly_chart(_iv_surface(c_sub, p_sub, spot), use_container_width=True, config=PLOTLY_CONFIG, theme=None)

if _options_section == "Strike Positioning":
    # ── Volume by strike ──────────────────────────────────────────────────────────
    st.markdown("#### Positioning by Strike")
    exp_options = ["All expirations"] + list(expirations[:6])
    chosen_exp = st.selectbox("Expiration", exp_options, key="opts_exp")
    exp_filter = None if chosen_exp == "All expirations" else chosen_exp

    vol_col, oi_col = st.columns(2)
    with vol_col:
        st.caption("**Volume** — contracts traded today (one day of flow).")
        st.plotly_chart(_volume_bars(calls_raw, puts_raw, exp_filter),
                        use_container_width=True, config=PLOTLY_CONFIG, theme=None)
    with oi_col:
        st.caption("**Open interest** — contracts still held, with spot and max pain marked.")
        st.plotly_chart(_oi_bars(calls_raw, puts_raw, exp_filter, spot, _S["max_pain"]),
                        use_container_width=True, config=PLOTLY_CONFIG, theme=None)

    st.divider()

if _options_section == "Unusual Activity":
    # ── Unusual contracts table ───────────────────────────────────────────────────
    st.markdown("####  Unusual Contracts — Volume > Open Interest")
    st.caption(
        f"Contracts where Vol/OI ≥ {_UNUSUAL_VOL_OI_THRESHOLD:.0f}x AND volume ≥ {_UNUSUAL_MIN_VOLUME:,}. "
        "These suggest fresh positioning, not just rolling existing trades."
    )

    _unusual_view = st.segmented_control(
        "Contract view",
        ["Unusual Calls", "Unusual Puts", "Combined"],
        default="Combined",
        key="options_unusual_view",
    )

_DISPLAY_COLS = ["type", "expiration", "dte", "strike", "lastPrice", "bid", "ask",
                 "volume", "openInterest", "vol_oi_ratio", "premium",
                 "impliedVolatility", "inTheMoney"]
_COL_LABELS = {
    "type": "Type", "expiration": "Expiry", "dte": "DTE",
    "strike": "Strike", "lastPrice": "Last",
    "bid": "Bid", "ask": "Ask", "volume": "Volume", "openInterest": "Open Int",
    "vol_oi_ratio": "Vol/OI", "premium": "Premium",
    "impliedVolatility": "IV", "inTheMoney": "ITM",
}


def _prep_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()

    # Dollars behind the trade, not just contract count: 10,000 contracts at
    # $0.05 is $50k, while 200 at $12 is $240k. Sorting an "unusual activity"
    # table by contract count alone puts the cheap lottery tickets on top.
    if {"volume", "lastPrice"} <= set(df.columns):
        df["premium"] = (
            pd.to_numeric(df["volume"], errors="coerce").fillna(0)
            * pd.to_numeric(df["lastPrice"], errors="coerce").fillna(0)
            * CONTRACT_MULTIPLIER
        )
    if "expiration" in df.columns:
        df["dte"] = df["expiration"].map(lambda e: days_to_expiration(e))

    cols = [c for c in _DISPLAY_COLS if c in df.columns]
    out = df[cols].copy()
    if "premium" in out.columns:
        out["premium"] = out["premium"].apply(
            lambda x: f"${_fmt_num(x)}" if x == x and x else "—"
        )
    if "dte" in out.columns:
        out["dte"] = out["dte"].apply(lambda x: f"{int(x)}d" if x == x and x is not None else "—")
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
        out["inTheMoney"] = out["inTheMoney"].map({True: " ITM", False: "OTM"})
    out = out.rename(columns=_COL_LABELS)
    return out.sort_values("Vol/OI", ascending=False) if "Vol/OI" in out.columns else out


if _options_section == "Unusual Activity":
    if _unusual_view == "Unusual Calls":
        if unusual_calls.empty:
            st.info("No unusual call activity found with current thresholds.")
        else:
            st.dataframe(_prep_display(unusual_calls), use_container_width=True, hide_index=True)

    if _unusual_view == "Unusual Puts":
        if unusual_puts.empty:
            st.info("No unusual put activity found with current thresholds.")
        else:
            st.dataframe(_prep_display(unusual_puts), use_container_width=True, hide_index=True)

    if _unusual_view == "Combined":
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
            # Carry the Call/Put tag THROUGH _prep_display rather than pasting it on
            # afterwards. _prep_display sorts by Vol/OI, so assigning a positional
            # array of tags to the sorted frame paired every row with the wrong
            # label — puts were shown as calls and vice versa, which on a
            # directional-positioning table inverts the read entirely.
            prep = _prep_display(all_unusual)
            st.dataframe(prep, use_container_width=True, hide_index=True)

if _options_section == "Full Chain":
    # ── Full chain viewer ─────────────────────────────────────────────────────────
    st.divider()
    with st.expander("Full options chain (all contracts)"):
        exp_chain = st.selectbox("Expiration", list(expirations[:6]), key="full_chain_exp")
        _chain_side = st.segmented_control(
            "Contract side",
            ["Calls", "Puts"],
            default="Calls",
            key="options_chain_side",
        )

        def _full_table(df: pd.DataFrame, exp: str):
            sub = df[df["expiration"] == exp] if not df.empty else pd.DataFrame()
            if sub.empty:
                st.info("No data for this expiration.")
                return
            # _DISPLAY_COLS already contains vol_oi_ratio; appending it again
            # produced a duplicated column, which pandas selects twice and renders
            # as two identical "Vol/OI" columns. Reuse the shared formatter instead
            # of maintaining a second, drifting copy of the same logic.
            st.dataframe(_prep_display(sub), use_container_width=True, hide_index=True)

        if _chain_side == "Calls":
            _full_table(calls_raw, exp_chain)
        if _chain_side == "Puts":
            _full_table(puts_raw, exp_chain)

if _options_section == "Methodology":
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
