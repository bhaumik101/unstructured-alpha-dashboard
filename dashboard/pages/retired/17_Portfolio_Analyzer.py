"""
Page 17 — Portfolio Macro Analyzer
=====================================
Enter your portfolio (tickers + optional weights) and get an aggregate
macro overlay in under 5 seconds.

What this answers that nothing else does for free:
  - "What % of my portfolio has macro tailwinds right now?"
  - "Which of my holdings are most exposed to the current macro regime?"
  - "Am I concentrated in sectors where signals are turning bearish?"
  - "My portfolio's aggregate confluence score vs 30 days ago"

Data: uses the same 2h-cached macro signal scores that power the rest of
the site — zero extra API calls for macro data. Price data (for portfolio
value estimates) is 15-min cached via yfinance.

User input is never stored anywhere — session-only, never persisted to DB.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from utils.header import render_header, render_sidebar_base, render_page_header, go_to_ticker
from utils.config import TICKERS, SIGNALS
from utils.db import init_db
from utils.theme import source_badge

st.set_page_config(page_title="Portfolio Analyzer — UA", layout="wide")

from utils.billing import require_pro
require_pro("Portfolio Analyzer")
render_header("Portfolio Analyzer")
render_sidebar_base()

render_page_header(
    "Portfolio Analyzer",
    "Macro factor exposure and confluence scores across your holdings.",
    icon="💼",
)
init_db()

# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=7200, show_spinner=False, max_entries=2)
def _get_all_macro_scores(signal_hash: int = 0) -> dict[str, dict]:
    """Get macro score for every tracked ticker from the shared cache."""
    from utils.top_tickers import get_top_tickers
    from utils.signals_cache import get_all_signal_scores
    _raw = get_all_signal_scores()
    data = get_top_tickers(len(_raw))
    return {row["ticker"]: row for row in data.get("all", [])}


@st.cache_data(ttl=900, show_spinner=False, max_entries=5)
def _get_current_prices(tickers_tuple: tuple[str, ...]) -> dict[str, float | None]:
    """Fetch latest close prices for portfolio tickers."""
    import yfinance as yf
    result: dict[str, float | None] = {}
    try:
        if len(tickers_tuple) == 1:
            data = yf.download(tickers_tuple[0], period="2d", auto_adjust=True, progress=False)
            result[tickers_tuple[0]] = float(data["Close"].iloc[-1]) if not data.empty else None
        else:
            data = yf.download(
                list(tickers_tuple), period="2d", auto_adjust=True,
                progress=False, group_by="ticker"
            )
            for t in tickers_tuple:
                try:
                    col = data["Close"][t] if len(tickers_tuple) > 1 else data["Close"]
                    result[t] = float(col.dropna().iloc[-1])
                except Exception:
                    result[t] = None
    except Exception:
        for t in tickers_tuple:
            result[t] = None
    return result


def _parse_portfolio_input(raw: str) -> list[dict]:
    """
    Parse user's portfolio input. Accepts formats:
      - 'AAPL'
      - 'AAPL 10'
      - 'AAPL,10' or 'AAPL, 10'
      - One ticker per line
    Returns [{"ticker": str, "weight": float}] normalised to sum=1.
    """
    rows = []
    for line in raw.strip().splitlines():
        line = line.strip().replace(",", " ")
        if not line:
            continue
        parts = line.upper().split()
        if not parts:
            continue
        ticker = parts[0].strip()
        if not ticker or not ticker.replace(".", "").replace("-", "").isalnum():
            continue
        try:
            weight = float(parts[1]) if len(parts) > 1 else 1.0
        except ValueError:
            weight = 1.0
        rows.append({"ticker": ticker, "weight": max(0.0, weight)})

    if not rows:
        return []

    # Normalise weights to sum to 1
    total = sum(r["weight"] for r in rows) or 1.0
    for r in rows:
        r["weight"] = round(r["weight"] / total, 4)
    return rows


# ── Page header ───────────────────────────────────────────────────────────────

st.markdown("# 📊 Portfolio Macro Analyzer")
st.markdown(
    '<div style="font-family:Inter,sans-serif;font-size:0.92rem;color:#8892AA;margin-bottom:18px;'
    'background:#0F1118;border-left:4px solid #7C3AED;padding:12px 16px;border-radius:0 8px 8px 0;">'
    'Enter your holdings and get an instant macro overlay. See which positions have the wind at '
    'their back right now, which are sailing into macro headwinds, and how your total portfolio '
    'exposure stacks up across sectors. Bloomberg PORT charges $25,000/year for this. It\'s free here.'
    '</div>',
    unsafe_allow_html=True,
)

# ── Input ─────────────────────────────────────────────────────────────────────

_c1, _c2 = st.columns([1, 2])
with _c1:
    st.markdown("**Enter your tickers**")
    st.caption("One per line. Optionally add a weight or share count after the ticker (e.g. `AAPL 30`). Equal-weight assumed if no numbers given.")
    _raw_input = st.text_area(
        "Portfolio tickers",
        height=220,
        placeholder="AAPL 25\nMSFT 20\nNVDA 15\nXOM 10\nGLD 5\nSPY",
        label_visibility="collapsed",
        key="portfolio_input",
    )

with _c2:
    st.markdown("**How it works**")
    st.markdown("""
Our 38-signal macro engine assigns a 0–100 score to every ticker in the universe.

**Tailwind** — macro score ≥ 65 (bullish alignment)
**Neutral** — macro score 35–65
**Headwind** — macro score ≤ 35 (bearish alignment)

The portfolio view weights these by your position sizes so a 30% AAPL position getting a headwind signal counts 3× more than a 10% position getting the same signal.

Tickers not in our 193-ticker universe get estimated scores based on their sector's average.
""")

    _analyze_clicked = st.button("🔍 Analyze Portfolio", type="primary", use_container_width=True, key="analyze_btn")

if not _analyze_clicked:
    st.stop()

# ── Parse + validate ──────────────────────────────────────────────────────────

_parsed = _parse_portfolio_input(_raw_input)
if not _parsed:
    st.error("Couldn't parse any valid tickers from your input. Please enter at least one ticker symbol.")
    st.stop()

# ── Load macro data ───────────────────────────────────────────────────────────

with st.spinner(f"Loading macro scores for {len(_parsed)} holdings…"):
    from utils.signals_cache import get_all_signal_scores as _gss
    _raw_signals = _gss()
    _macro_scores = _get_all_macro_scores(len(_raw_signals))

    # Sector averages for tickers not in our universe
    _sector_avgs: dict[str, float] = {}
    for _row in _macro_scores.values():
        s = _row.get("sector", "Other")
        _sector_avgs.setdefault(s, []).append(_row.get("score", 50))  # type: ignore
    _sector_avgs = {s: round(sum(v) / len(v), 1) for s, v in _sector_avgs.items() if v}  # type: ignore
    _global_avg = round(sum(_sector_avgs.values()) / max(len(_sector_avgs), 1), 1) if _sector_avgs else 50.0

    # Prices
    _unique_tickers = tuple(r["ticker"] for r in _parsed)
    _prices = _get_current_prices(_unique_tickers)

# ── Build portfolio DataFrame ─────────────────────────────────────────────────

_portfolio_rows = []
for _r in _parsed:
    _t = _r["ticker"]
    _w = _r["weight"]
    _macro = _macro_scores.get(_t)

    if _macro:
        _score    = _macro.get("score", 50)
        _case     = _macro.get("case", "NEUTRAL")
        _bull_n   = _macro.get("bull", 0)
        _bear_n   = _macro.get("bear", 0)
        _sector   = _macro.get("sector", "Other")
        _name     = _macro.get("name", TICKERS.get(_t, {}).get("name", _t))
        _conv     = _macro.get("conv", "")
        _in_universe = True
    else:
        # Estimate from sector if available
        _sector   = TICKERS.get(_t, {}).get("sector", "Other")
        _score    = _sector_avgs.get(_sector, _global_avg)
        _case     = "BULL" if _score >= 65 else ("BEAR" if _score <= 35 else "NEUTRAL")
        _bull_n   = 0
        _bear_n   = 0
        _name     = TICKERS.get(_t, {}).get("name", _t)
        _conv     = "estimated"
        _in_universe = False

    _bias = "Tailwind" if _score >= 65 else ("Headwind" if _score <= 35 else "Neutral")
    _price = _prices.get(_t)
    _portfolio_rows.append({
        "ticker":        _t,
        "name":          _name,
        "sector":        _sector,
        "weight":        _w,
        "weight_pct":    round(_w * 100, 1),
        "macro_score":   round(_score, 1),
        "case":          _case,
        "bias":          _bias,
        "bull_signals":  _bull_n,
        "bear_signals":  _bear_n,
        "conviction":    _conv,
        "price":         _price,
        "in_universe":   _in_universe,
    })

_df = pd.DataFrame(_portfolio_rows)
_df["weighted_score"] = _df["macro_score"] * _df["weight"]

# ── Aggregate Metrics ─────────────────────────────────────────────────────────

_agg_score = round(_df["weighted_score"].sum(), 1)
_tailwind_pct  = round(_df[_df["bias"] == "Tailwind"]["weight"].sum() * 100, 1)
_headwind_pct  = round(_df[_df["bias"] == "Headwind"]["weight"].sum() * 100, 1)
_neutral_pct   = round(100 - _tailwind_pct - _headwind_pct, 1)

_agg_bias = (
    "TAILWIND" if _agg_score >= 65 else
    ("HEADWIND" if _agg_score <= 35 else "NEUTRAL")
)
_agg_color = "#00D566" if _agg_bias == "TAILWIND" else ("#FF4444" if _agg_bias == "HEADWIND" else "#6B7FBF")

st.divider()

# ── Score Banner ──────────────────────────────────────────────────────────────

st.markdown(
    f'<div style="background:#7C3AED;border-radius:12px;padding:20px 28px;margin-bottom:24px;">'
    f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;">'
    f'<div>'
    f'  <div style="font-size:0.68rem;color:#C9A84C;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:4px;">PORTFOLIO MACRO SCORE</div>'
    f'  <div style="font-size:2.8rem;font-weight:800;color:{_agg_color};font-family:Inter,sans-serif;">{_agg_score}</div>'
    f'  <div style="font-size:0.90rem;color:{_agg_color};font-weight:700;">{_agg_bias}</div>'
    f'</div>'
    f'<div style="display:flex;gap:24px;flex-wrap:wrap;">'
    f'  <div style="text-align:center;">'
    f'    <div style="font-size:1.6rem;font-weight:700;color:#00D566;">{_tailwind_pct}%</div>'
    f'    <div style="font-size:0.70rem;color:#A0A8B8;">Tailwind</div>'
    f'  </div>'
    f'  <div style="text-align:center;">'
    f'    <div style="font-size:1.6rem;font-weight:700;color:#6B7FBF;">{_neutral_pct}%</div>'
    f'    <div style="font-size:0.70rem;color:#A0A8B8;">Neutral</div>'
    f'  </div>'
    f'  <div style="text-align:center;">'
    f'    <div style="font-size:1.6rem;font-weight:700;color:#FF4444;">{_headwind_pct}%</div>'
    f'    <div style="font-size:0.70rem;color:#A0A8B8;">Headwind</div>'
    f'  </div>'
    f'  <div style="text-align:center;">'
    f'    <div style="font-size:1.6rem;font-weight:700;color:#EEF3FA;">{len(_df)}</div>'
    f'    <div style="font-size:0.70rem;color:#A0A8B8;">Holdings</div>'
    f'  </div>'
    f'</div>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Charts row ────────────────────────────────────────────────────────────────

_ch1, _ch2, _ch3 = st.columns(3)

with _ch1:
    # Macro bias donut
    _bias_counts = _df.groupby("bias")["weight"].sum().reset_index()
    _bias_counts["weight_pct"] = (_bias_counts["weight"] * 100).round(1)
    _bias_color_map = {"Tailwind": "#00D566", "Neutral": "#6B7FBF", "Headwind": "#FF4444"}
    _fig_donut = go.Figure(go.Pie(
        labels=_bias_counts["bias"].tolist(),
        values=_bias_counts["weight_pct"].tolist(),
        hole=0.62,
        marker_colors=[_bias_color_map.get(b, "#6B7FBF") for b in _bias_counts["bias"]],
        textinfo="label+percent",
        hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
    ))
    _fig_donut.update_layout(
        title=dict(text="Macro Bias Mix", font=dict(size=14, color="#7C3AED"), x=0.5),
        margin=dict(t=40, b=10, l=10, r=10), height=220,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    st.plotly_chart(_fig_donut, use_container_width=True)

with _ch2:
    # Sector exposure bar chart, colored by weighted score
    _sector_g = _df.groupby("sector").agg(
        weight_pct=("weight_pct", "sum"),
        macro_score=("weighted_score", "sum"),
    ).reset_index()
    _sector_g["macro_score"] = (_sector_g["macro_score"] / (_sector_g["weight_pct"] / 100)).round(1)
    _sector_g = _sector_g.sort_values("weight_pct", ascending=True)
    _bar_colors = [
        "#00D566" if s >= 65 else ("#FF4444" if s <= 35 else "#6B7FBF")
        for s in _sector_g["macro_score"]
    ]
    _fig_sector = go.Figure(go.Bar(
        y=_sector_g["sector"].tolist(),
        x=_sector_g["weight_pct"].tolist(),
        orientation="h",
        marker_color=_bar_colors,
        text=[f'{s:.0f}' for s in _sector_g["macro_score"]],
        textposition="inside",
        hovertemplate="%{y}: %{x:.1f}% weight, macro %{text}/100<extra></extra>",
    ))
    _fig_sector.update_layout(
        title=dict(text="Sector Exposure (macro score in bar)", font=dict(size=14, color="#7C3AED"), x=0.5),
        xaxis_title="Portfolio Weight %",
        margin=dict(t=40, b=30, l=10, r=10), height=220,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#8892AA"),
    )
    st.plotly_chart(_fig_sector, use_container_width=True)

with _ch3:
    # Bubble chart: macro score vs weight, bubble size = weight
    _fig_bubble = go.Figure()
    for _, _row in _df.iterrows():
        _c = "#00D566" if _row["macro_score"] >= 65 else ("#FF4444" if _row["macro_score"] <= 35 else "#6B7FBF")
        _fig_bubble.add_trace(go.Scatter(
            x=[_row["macro_score"]],
            y=[_row["weight_pct"]],
            mode="markers+text",
            marker=dict(size=max(10, _row["weight_pct"] * 3), color=_c, opacity=0.75, line=dict(width=1, color="white")),
            text=[_row["ticker"]],
            textposition="middle center",
            textfont=dict(size=9, color="white"),
            hovertemplate=f"{_row['ticker']}: macro {_row['macro_score']:.0f}, weight {_row['weight_pct']:.1f}%<extra></extra>",
        ))
    _fig_bubble.add_vline(x=65, line_dash="dot", line_color="#00D566", opacity=0.4)
    _fig_bubble.add_vline(x=35, line_dash="dot", line_color="#FF4444", opacity=0.4)
    _fig_bubble.update_layout(
        title=dict(text="Score vs Weight (bubble = weight)", font=dict(size=14, color="#7C3AED"), x=0.5),
        xaxis=dict(title="Macro Score", range=[0, 100]),
        yaxis=dict(title="Weight %"),
        showlegend=False,
        margin=dict(t=40, b=30, l=40, r=10), height=220,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(245,241,232,0.5)",
        font=dict(family="Inter, sans-serif", color="#8892AA"),
    )
    st.plotly_chart(_fig_bubble, use_container_width=True)

st.markdown(
    f"&nbsp; {source_badge('yfinance', 'Price data · sector classification')} "
    f"&nbsp; {source_badge('ua', 'Confluence Score · UA internal')}",
    unsafe_allow_html=True,
)

# ── Holdings table ────────────────────────────────────────────────────────────

st.divider()
st.markdown(
    '<div style="font-size:0.68rem;font-weight:700;color:#6B7FBF;letter-spacing:0.10em;'
    'text-transform:uppercase;margin-bottom:12px;">HOLDINGS BREAKDOWN</div>',
    unsafe_allow_html=True,
)

# Sort by macro score (worst headwinds first for immediate attention)
_df_display = _df.sort_values("macro_score").reset_index(drop=True)

_BIAS_COLORS = {"Tailwind": "#00D566", "Neutral": "#6B7FBF", "Headwind": "#FF4444"}
_BIAS_BG     = {"Tailwind": "rgba(0,213,102,0.08)", "Neutral": "rgba(107,127,191,0.06)", "Headwind": "rgba(255,68,68,0.08)"}
_BIAS_ICONS  = {"Tailwind": "▲", "Neutral": "→", "Headwind": "▼"}

for _, _row in _df_display.iterrows():
    _bc = _BIAS_COLORS.get(_row["bias"], "#6B7FBF")
    _bb = _BIAS_BG.get(_row["bias"], "rgba(107,127,191,0.06)")
    _bi = _BIAS_ICONS.get(_row["bias"], "●")
    _est_note = ' <span style="color:#9E9E8E;font-size:0.62rem;">(sector-estimated)</span>' if not _row["in_universe"] else ""
    _price_html = f'${_row["price"]:,.2f}' if _row["price"] else "N/A"

    _hbox = st.container()
    _hc1, _hc2, _hc3, _hc4 = _hbox.columns([2, 1.5, 1.5, 1])
    with _hc1:
        go_to_ticker(_row["ticker"], key=f"port_{_row['ticker']}")
        st.markdown(
            f'<div style="font-size:0.72rem;color:#6B7FBF;">{_row["sector"]} · {_row["name"][:32]}{_est_note}</div>',
            unsafe_allow_html=True,
        )
    with _hc2:
        st.markdown(
            f'<div style="font-family:Inter,sans-serif;font-size:0.85rem;padding-top:4px;">'
            f'Weight: <b>{_row["weight_pct"]:.1f}%</b><br>'
            f'Price: <span style="color:#8892AA;">{_price_html}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with _hc3:
        _sig_html = (
            f'<span style="color:#00D566;">▲ {_row["bull_signals"]} bull</span> · '
            f'<span style="color:#FF4444;">▼ {_row["bear_signals"]} bear</span>'
            if _row["in_universe"] else
            f'<span style="color:#9E9E8E;">Universe coverage pending</span>'
        )
        st.markdown(
            f'<div style="font-size:0.72rem;padding-top:4px;color:#8892AA;">{_sig_html}</div>',
            unsafe_allow_html=True,
        )
    with _hc4:
        st.markdown(
            f'<div style="background:{_bb};border-radius:6px;padding:6px 10px;text-align:center;'
            f'border-left:3px solid {_bc};margin-top:2px;">'
            f'<div style="font-size:1.1rem;font-weight:800;color:{_bc};">{_row["macro_score"]:.0f}</div>'
            f'<div style="font-size:0.68rem;color:{_bc};font-weight:700;">{_bi} {_row["bias"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# ── Interpretation ────────────────────────────────────────────────────────────

st.divider()

_worst = _df.nsmallest(3, "macro_score")
_best  = _df.nlargest(3, "macro_score")

st.markdown(
    '<div style="background:#0F1118;border-radius:10px;padding:16px 20px;border:1px solid rgba(255,255,255,0.08);'
    'font-family:Inter,sans-serif;">'
    '<div style="font-size:0.68rem;font-weight:700;color:#6B7FBF;text-transform:uppercase;'
    'letter-spacing:0.10em;margin-bottom:10px;">MACHINE INTERPRETATION</div>',
    unsafe_allow_html=True,
)

_interp_parts = []
if _tailwind_pct >= 50:
    _interp_parts.append(f"More than half your portfolio ({_tailwind_pct}%) is positioned with macro tailwinds. The overall regime supports your current positioning.")
elif _headwind_pct >= 50:
    _interp_parts.append(f"Macro headwinds affect {_headwind_pct}% of your portfolio by weight. The current signal environment is working against these positions.")
else:
    _interp_parts.append(f"Your portfolio is largely neutral from a macro signal perspective ({_neutral_pct}% neutral weight). The machine has no strong bias for or against your current positioning.")

if not _worst.empty:
    _worst_names = ", ".join(_worst["ticker"].tolist())
    _interp_parts.append(f"Your weakest macro positions are {_worst_names} — these face the most direct signal headwinds right now.")

if not _best.empty:
    _best_names = ", ".join(_best["ticker"].tolist())
    _interp_parts.append(f"Your strongest macro positions are {_best_names} — multiple signals are aligned in their favor.")

for _p in _interp_parts:
    st.markdown(f'<div style="font-size:0.85rem;color:#8892AA;margin-bottom:6px;line-height:1.6;">● {_p}</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

if _df[~_df["in_universe"]].shape[0] > 0:
    _out_count = _df[~_df["in_universe"]].shape[0]
    st.caption(
        f"⚠️ {_out_count} of your tickers aren't in our 193-ticker universe. "
        f"Their macro scores are estimated from their sector average. "
        f"Visit Ticker Deep Dive for any of them to start building their signal history."
    )

st.markdown("""
<div class="disclaimer">
<b>Not financial advice.</b> Macro scores are based on signal alignment, not price forecasts.
A "tailwind" score means macro data is aligned with a bullish reading — not a guarantee of positive returns.
Portfolio weights you entered are session-only and never stored.
</div>
""", unsafe_allow_html=True)
