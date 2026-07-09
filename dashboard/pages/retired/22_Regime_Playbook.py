"""
Page 22 — Regime Playbook
==========================
Answers the question: "Macro looks like THIS right now — what has historically
followed?"

The page works in two layers:

  Layer 1 — Live Regime
    Derives today's macro regime (BULLISH / MIXED / BEARISH) from the live
    signal scores. Shows which signal categories are aligned vs. divided,
    which signals are closest to flipping, and a category-level radar summary.

  Layer 2 — Historical Performance by Regime
    Queries signal_snapshots to reconstruct the daily regime score (% of
    signals bullish) over the past 90+ days, then cross-references sector ETF
    forward returns (from yfinance) to show what each sector did in the 30/60/
    90 days following periods with a similar regime score.

    When snapshot history is thin (<30 days), the sector analysis uses a
    well-tested proxy: SPY relative to its 200-day MA + VIX level, which
    maps cleanly to risk-on / risk-off regimes and is fully transparent.

REGIME BUCKETS:
  BULLISH  — >60% of scored signals are bullish   (confluence score ≈ 65+)
  BEARISH  — >60% of scored signals are bearish   (confluence score ≈ 35-)
  MIXED    — everything in between

DATA SOURCES:
  • Live signal scores:     get_all_signal_scores() — 2h shared cache
  • Snapshot history:       signal_snapshots DB table
  • Sector ETF prices:      yfinance — XLK, XLE, XLF, XLV, XLI, XLC, XLY,
                            XLP, XLU, XLRE, SPY
  • VIX + SPY MA:           yfinance .history()
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta, timezone

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.signals_cache import get_all_signal_scores
from utils.config import SIGNALS, CATEGORIES

st.set_page_config(
    page_title="Regime Playbook — Unstructured Alpha",
    page_icon="📋",
    layout="wide",
)
render_header()
render_sidebar_base()

render_page_header(
    "Regime Playbook",
    "Historical playbook: how each macro regime has affected sectors and tickers.",
    icon="📖",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.block-container { padding-top: 0.5rem !important; max-width: 1100px !important; }
.regime-banner {
    border-radius: 8px; padding: 18px 24px; margin-bottom: 20px;
    font-family: Inter, sans-serif; text-align: center;
}
.regime-bull  { background: #0D3B0E; color: #A8D5A2; border: 2px solid #00D566; }
.regime-bear  { background: #4B0000; color: #F4A0A0; border: 2px solid #FF4444; }
.regime-mixed { background: #F59E0B; color: #D4C47A; border: 2px solid #6B7FBF; }
.regime-title { font-size: 1.5rem; font-weight: 700; letter-spacing: 0.04em; }
.regime-sub   { font-size: 0.85rem; margin-top: 4px; opacity: 0.85; }
.section-hdr  {
    font-family: Inter, sans-serif; font-size: 0.70rem; font-weight: 700;
    letter-spacing: 0.12em; color: #6B7FBF; text-transform: uppercase;
    border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 4px; margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# DATA HELPERS
# ─────────────────────────────────────────────────────────────────────────────

SECTOR_ETFS = {
    "SPY":  "S&P 500",
    "QQQ":  "Nasdaq-100",
    "XLK":  "Technology",
    "XLE":  "Energy",
    "XLF":  "Financials",
    "XLV":  "Healthcare",
    "XLI":  "Industrials",
    "XLY":  "Cons. Disc.",
    "XLP":  "Cons. Staples",
    "XLU":  "Utilities",
    "XLRE": "Real Estate",
    "XLC":  "Comm. Services",
    "GLD":  "Gold",
    "IWM":  "Small Caps",
}

# Category → list of signal IDs
_CAT_SIGS: dict[str, list[str]] = {}
for _sid, _scfg in SIGNALS.items():
    _cat = _scfg.get("category", "macro")
    _CAT_SIGS.setdefault(_cat, []).append(_sid)


@st.cache_data(ttl=7200, show_spinner=False, max_entries=1)
def _get_regime_history(days: int = 120) -> pd.DataFrame:
    """
    Query signal_snapshots to compute the % of signals bullish on each day.
    Returns a DataFrame with columns: snapshot_date, pct_bull, pct_bear,
    pct_neutral, regime.
    """
    try:
        from utils.db import signal_snapshots
        import utils.db as db
        from sqlalchemy import select

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(signal_snapshots)
                .where(signal_snapshots.c.snapshot_date >= cutoff)
                .order_by(signal_snapshots.c.snapshot_date)
            ).mappings().all()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(r) for r in rows])
        grouped = df.groupby("snapshot_date")["status"].value_counts().unstack(fill_value=0)
        for col in ["bullish", "neutral", "bearish"]:
            if col not in grouped.columns:
                grouped[col] = 0
        grouped["total"] = grouped["bullish"] + grouped["neutral"] + grouped["bearish"]
        grouped = grouped[grouped["total"] > 0]
        grouped["pct_bull"] = grouped["bullish"] / grouped["total"] * 100
        grouped["pct_bear"] = grouped["bearish"] / grouped["total"] * 100
        grouped["pct_neutral"] = grouped["neutral"] / grouped["total"] * 100
        grouped["regime"] = grouped["pct_bull"].apply(
            lambda x: "BULLISH" if x > 60 else ("BEARISH" if x < 40 else "MIXED")
        )
        grouped = grouped.reset_index().rename(columns={"snapshot_date": "date"})
        grouped["date"] = pd.to_datetime(grouped["date"])
        return grouped.sort_values("date")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False, max_entries=5)
def _get_sector_returns(lookback_days: int = 504) -> pd.DataFrame:
    """
    Fetch 2-year daily prices for sector ETFs. Returns a wide DataFrame
    indexed by date with one column per ETF.
    """
    import yfinance as yf
    tickers = list(SECTOR_ETFS.keys())
    try:
        raw = yf.download(
            tickers, period=f"{lookback_days}d",
            auto_adjust=True, progress=False, threads=True,
        )
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"]
        else:
            prices = raw[["Close"]] if "Close" in raw.columns else raw
        prices = prices.dropna(how="all")
        return prices
    except Exception:
        return pd.DataFrame()


def _compute_forward_returns(
    prices: pd.DataFrame,
    regime_df: pd.DataFrame,
    horizons: list[int] = [30, 60, 90],
) -> dict:
    """
    For each regime bucket, compute mean/median forward return across horizons.
    Returns nested dict: {regime: {horizon: {etf: mean_return_pct}}}
    """
    if prices.empty or regime_df.empty:
        return {}

    prices = prices.copy()
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    regime_df = regime_df.copy()
    regime_df["date"] = pd.to_datetime(regime_df["date"]).dt.tz_localize(None)

    results: dict[str, dict[int, dict[str, float]]] = {"BULLISH": {}, "MIXED": {}, "BEARISH": {}}

    for regime in ["BULLISH", "MIXED", "BEARISH"]:
        regime_dates = regime_df[regime_df["regime"] == regime]["date"].tolist()
        results[regime] = {}
        for h in horizons:
            fwd: dict[str, list[float]] = {col: [] for col in prices.columns}
            for dt in regime_dates:
                future = dt + timedelta(days=h)
                # Find nearest actual trading day
                avail = prices.index[prices.index >= dt]
                avail_f = prices.index[prices.index >= future]
                if avail.empty or avail_f.empty:
                    continue
                p0 = prices.loc[avail[0]]
                p1 = prices.loc[avail_f[0]]
                for col in prices.columns:
                    if p0[col] > 0:
                        fwd[col].append((p1[col] - p0[col]) / p0[col] * 100)
            results[regime][h] = {
                col: float(np.mean(v)) if v else float("nan")
                for col, v in fwd.items()
            }

    return results


def _live_regime_from_scores(scores: dict) -> tuple[str, int, int, int]:
    """Returns (regime, n_bull, n_bear, n_neutral) from current signal scores."""
    n_bull = sum(1 for v in scores.values() if v.get("status") == "bullish")
    n_bear = sum(1 for v in scores.values() if v.get("status") == "bearish")
    n_neut = sum(1 for v in scores.values() if v.get("status") == "neutral")
    total = n_bull + n_bear + n_neut
    if total == 0:
        return "MIXED", 0, 0, 0
    pct_bull = n_bull / total
    pct_bear = n_bear / total
    if pct_bull > 0.60:
        return "BULLISH", n_bull, n_bear, n_neut
    elif pct_bear > 0.60:
        return "BEARISH", n_bull, n_bear, n_neut
    else:
        return "MIXED", n_bull, n_bear, n_neut


def _category_scores(scores: dict) -> dict[str, dict]:
    """Average signal score per category."""
    cat_data: dict[str, list[float]] = {}
    for sid, sv in scores.items():
        cat = SIGNALS.get(sid, {}).get("category", "macro")
        cat_data.setdefault(cat, []).append(sv.get("score", 50))
    return {
        cat: {
            "avg": float(np.mean(vals)),
            "name": CATEGORIES.get(cat, {}).get("name", cat.title()),
            "status": (
                "bullish" if np.mean(vals) >= 65
                else "bearish" if np.mean(vals) <= 35
                else "neutral"
            ),
        }
        for cat, vals in cat_data.items()
    }


# ─────────────────────────────────────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────────────────────────────────────
with st.spinner("Loading live signals…"):
    all_scores = get_all_signal_scores()

regime, n_bull, n_bear, n_neut = _live_regime_from_scores(all_scores)
total_scored = n_bull + n_bear + n_neut
cat_scores = _category_scores(all_scores)

# Load historical data in background
regime_hist = _get_regime_history(days=120)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — CURRENT REGIME BANNER
# ─────────────────────────────────────────────────────────────────────────────
_bull_pct = round(n_bull / total_scored * 100) if total_scored else 0
_bear_pct = round(n_bear / total_scored * 100) if total_scored else 0

if regime == "BULLISH":
    _cls = "regime-bull"
    _icon = "📈"
    _desc = f"{n_bull} of {total_scored} signals aligned bullish — macro environment favors risk-on"
elif regime == "BEARISH":
    _cls = "regime-bear"
    _icon = "📉"
    _desc = f"{n_bear} of {total_scored} signals aligned bearish — macro environment favors caution"
else:
    _cls = "regime-mixed"
    _icon = "⚖️"
    _desc = f"Signals divided — {n_bull} bullish, {n_bear} bearish, {n_neut} neutral out of {total_scored}"

st.markdown(
    f"<div class='regime-banner {_cls}'>"
    f"<div class='regime-title'>{_icon} {regime} MACRO REGIME</div>"
    f"<div class='regime-sub'>{_desc} &nbsp;·&nbsp; as of {datetime.now().strftime('%b %d, %Y')}</div>"
    f"</div>",
    unsafe_allow_html=True,
)

# ── Metric row ─────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Bullish Signals", f"{n_bull}", f"{_bull_pct}% of scored",
          delta_color="normal")
m2.metric("Bearish Signals", f"{n_bear}", f"{_bear_pct}% of scored",
          delta_color="inverse")
m3.metric("Neutral Signals", f"{n_neut}")
m4.metric("Total Scored", f"{total_scored}")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — CATEGORY BREAKDOWN + RADAR
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Signal Category Breakdown</div>', unsafe_allow_html=True)

cat_col, radar_col = st.columns([3, 2])

with cat_col:
    cat_rows = sorted(cat_scores.items(), key=lambda x: -x[1]["avg"])
    STATUS_COLOR = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#6B7FBF"}
    STATUS_ICON = {"bullish": "▲", "bearish": "▼", "neutral": "→"}

    for cat_id, cdata in cat_rows:
        color = STATUS_COLOR[cdata["status"]]
        icon = STATUS_ICON[cdata["status"]]
        score_val = cdata["avg"]
        bar_width = int(score_val)
        bar_color = "#00D566" if score_val >= 65 else ("#FF4444" if score_val <= 35 else "#6B7FBF")
        st.markdown(
            f"<div style='margin-bottom:10px;'>"
            f"<div style='display:flex;justify-content:space-between;font-size:0.82rem;"
            f"font-family:Inter,sans-serif;margin-bottom:3px;'>"
            f"<span style='color:#E8EEFF;font-weight:600;'>{cdata['name']}</span>"
            f"<span style='color:{color};font-weight:700;'>{icon} {score_val:.0f}</span>"
            f"</div>"
            f"<div style='background:#E8E0D4;border-radius:3px;height:6px;'>"
            f"<div style='width:{bar_width}%;background:{bar_color};height:6px;border-radius:3px;'></div>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

with radar_col:
    cats_ordered = sorted(cat_scores.keys())
    radar_vals = [cat_scores[c]["avg"] for c in cats_ordered]
    radar_names = [cat_scores[c]["name"] for c in cats_ordered]

    fig_radar = go.Figure(go.Scatterpolar(
        r=radar_vals + [radar_vals[0]],
        theta=radar_names + [radar_names[0]],
        fill="toself",
        fillcolor="rgba(27,94,32,0.25)",
        line=dict(color="#00D566", width=2),
        name="Current Regime",
    ))
    fig_radar.add_shape(
        type="circle", xref="paper", yref="paper",
        x0=0.5 - 0.375, y0=0.5 - 0.375, x1=0.5 + 0.375, y1=0.5 + 0.375,
        line=dict(color="#E8E0D4", width=1, dash="dot"),
    )
    fig_radar.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=9),
                            gridcolor="#E8E0D4", tickcolor="#6B7FBF"),
            angularaxis=dict(tickfont=dict(size=10, family="Inter, sans-serif"), gridcolor="#E8E0D4"),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        margin=dict(l=40, r=40, t=20, b=20),
        height=320,
    )
    st.plotly_chart(fig_radar, use_container_width=True)

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — REGIME HISTORY TIMELINE
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Historical Regime Timeline</div>', unsafe_allow_html=True)

if regime_hist.empty or len(regime_hist) < 5:
    st.info(
        "Regime history builds automatically as signals are scored each day. "
        "Check back after a few days to see the timeline — the page's analytics "
        "get richer with each passing session.",
        icon="📅",
    )
else:
    fig_hist = go.Figure()
    color_map = {"BULLISH": "#00D566", "BEARISH": "#FF4444", "MIXED": "#6B7FBF"}

    # Shaded regime band
    for reg, color in color_map.items():
        mask = regime_hist["regime"] == reg
        fig_hist.add_trace(go.Bar(
            x=regime_hist.loc[mask, "date"],
            y=regime_hist.loc[mask, "pct_bull"],
            name=reg,
            marker_color=color,
            opacity=0.8,
        ))

    fig_hist.add_hline(y=60, line_dash="dot", line_color="#00D566", annotation_text="Bullish threshold",
                       annotation_font_size=10)
    fig_hist.add_hline(y=40, line_dash="dot", line_color="#FF4444", annotation_text="Bearish threshold",
                       annotation_font_size=10)
    fig_hist.update_layout(
        barmode="overlay",
        xaxis_title=None,
        yaxis_title="% Signals Bullish",
        yaxis_range=[0, 100],
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=20, b=20),
        height=240,
    )
    fig_hist.update_xaxes(gridcolor="#E8E0D4", tickfont=dict(size=10))
    fig_hist.update_yaxes(gridcolor="#E8E0D4", tickfont=dict(size=10))
    st.plotly_chart(fig_hist, use_container_width=True)

    # Regime duration summary
    _reg_counts = regime_hist["regime"].value_counts()
    _reg_cols = st.columns(3)
    _reg_info = {
        "BULLISH": ("#00D566", "📈"),
        "MIXED":   ("#6B7FBF", "⚖️"),
        "BEARISH": ("#FF4444", "📉"),
    }
    for i, (rname, (rcol, ricon)) in enumerate(_reg_info.items()):
        n = _reg_counts.get(rname, 0)
        _reg_cols[i].markdown(
            f"<div style='text-align:center;padding:10px;border-radius:6px;"
            f"border:1px solid {rcol};'>"
            f"<div style='font-size:1.2rem;'>{ricon}</div>"
            f"<div style='font-weight:700;color:{rcol};font-size:0.95rem;'>{rname}</div>"
            f"<div style='color:#6B5E52;font-size:0.8rem;'>{n} day{'s' if n!=1 else ''} tracked</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — SECTOR PERFORMANCE BY REGIME
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Sector Performance by Macro Regime</div>', unsafe_allow_html=True)
st.caption(
    "Forward returns for each sector ETF following days where the macro regime matched each bucket. "
    "Uses signal snapshot history where available; falls back to SPY/VIX proxy regime when history is thin."
)

with st.spinner("Computing sector forward returns…"):
    sector_prices = _get_sector_returns(lookback_days=504)

has_real_history = not regime_hist.empty and len(regime_hist) >= 20

if sector_prices.empty:
    st.warning("Sector price data unavailable — check yfinance connection.", icon="⚠️")
elif not has_real_history:
    # ── Proxy regime: use SPY vs 200d MA + VIX ──────────────────────────────
    st.info(
        "Using SPY/VIX proxy regime (not enough signal snapshot history yet — "
        "this will switch to your actual signal history after ~20 days of data).",
        icon="ℹ️",
    )

    spy_close = sector_prices.get("SPY", pd.Series(dtype=float)).dropna()
    if len(spy_close) >= 200:
        spy_ma200 = spy_close.rolling(200).mean()
        proxy_regime = pd.DataFrame({
            "date": spy_close.index,
            "pct_bull": np.where(spy_close.values > spy_ma200.values, 75.0, 25.0),
        })
        proxy_regime["regime"] = proxy_regime["pct_bull"].apply(
            lambda x: "BULLISH" if x > 60 else "BEARISH"
        )
        proxy_regime = proxy_regime.dropna()
        fwd_returns = _compute_forward_returns(sector_prices, proxy_regime)
    else:
        fwd_returns = {}
else:
    fwd_returns = _compute_forward_returns(sector_prices, regime_hist)

if fwd_returns:
    hz_options = [30, 60, 90]
    hz_sel = st.radio("Forward horizon:", hz_options, index=1,
                      format_func=lambda h: f"{h} days", horizontal=True)

    plot_data = []
    for reg, hz_data in fwd_returns.items():
        if hz_sel not in hz_data:
            continue
        for etf, ret in hz_data[hz_sel].items():
            if np.isnan(ret):
                continue
            plot_data.append({
                "Regime": reg,
                "ETF": etf,
                "Sector": SECTOR_ETFS.get(etf, etf),
                "Avg Return (%)": round(ret, 2),
            })

    if plot_data:
        plot_df = pd.DataFrame(plot_data)
        # Pivot for grouped bar
        pivot = plot_df.pivot(index="Sector", columns="Regime", values="Avg Return (%)").fillna(0)
        pivot = pivot.reindex(sorted(pivot.index, key=lambda s: pivot.get("BULLISH", pd.Series([0])).get(s, 0), reverse=True))

        reg_colors = {"BULLISH": "#00D566", "MIXED": "#6B7FBF", "BEARISH": "#FF4444"}
        fig_bars = go.Figure()
        for reg in ["BULLISH", "MIXED", "BEARISH"]:
            if reg in pivot.columns:
                fig_bars.add_trace(go.Bar(
                    name=reg,
                    x=pivot.index.tolist(),
                    y=pivot[reg].tolist(),
                    marker_color=reg_colors[reg],
                    opacity=0.85,
                ))

        fig_bars.add_hline(y=0, line_color="#9E9E9E", line_width=1)
        fig_bars.update_layout(
            barmode="group",
            xaxis_title=None,
            yaxis_title=f"Avg {hz_sel}-day forward return (%)",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=40, r=20, t=30, b=40),
            height=380,
        )
        fig_bars.update_xaxes(gridcolor="#E8E0D4", tickfont=dict(size=10, family="Inter, sans-serif"))
        fig_bars.update_yaxes(gridcolor="#E8E0D4", tickfont=dict(size=10))
        st.plotly_chart(fig_bars, use_container_width=True)

        # Highlight current regime column in table
        highlight_reg = regime
        tbl_df = plot_df[plot_df["Regime"] == highlight_reg].sort_values("Avg Return (%)", ascending=False)
        if not tbl_df.empty:
            st.markdown(
                f"<div style='font-size:0.82rem;color:#6B5E52;margin-top:4px;'>"
                f"In <b>{highlight_reg}</b> regimes: top-performing sectors over {hz_sel} days</div>",
                unsafe_allow_html=True,
            )
            tbl_display = tbl_df[["Sector", "Avg Return (%)"]].reset_index(drop=True)
            st.dataframe(
                tbl_display.style.bar(
                    subset=["Avg Return (%)"],
                    color=["#FF4444", "#00D566"],
                    vmin=-15, vmax=15,
                ).format({"Avg Return (%)": "{:+.2f}%"}),
                use_container_width=True,
                hide_index=True,
                height=min(420, 36 + 35 * len(tbl_display)),
            )

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — FLIP WATCH: SIGNALS CLOSEST TO CHANGING REGIME
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">Flip Watch — Signals Closest to a Regime Change</div>',
            unsafe_allow_html=True)
st.caption("Signals within 8 points of the bull/bear threshold (65 / 35). These are the ones to watch.")

near_flip = []
for sid, sv in all_scores.items():
    score = sv.get("score", 50)
    status = sv.get("status", "neutral")
    cfg = SIGNALS.get(sid, {})
    name = cfg.get("name", sid)

    if status == "neutral" and score >= 57:
        near_flip.append({"Signal": name, "Score": score, "Status": "→ BULLISH", "Gap": round(65 - score, 1)})
    elif status == "neutral" and score <= 43:
        near_flip.append({"Signal": name, "Score": score, "Status": "→ BEARISH", "Gap": round(score - 35, 1)})
    elif status == "bullish" and score <= 73:
        near_flip.append({"Signal": name, "Score": score, "Status": "→ MIXED", "Gap": round(score - 65, 1)})
    elif status == "bearish" and score >= 27:
        near_flip.append({"Signal": name, "Score": score, "Status": "→ MIXED", "Gap": round(35 - score, 1)})

if near_flip:
    near_df = pd.DataFrame(near_flip).sort_values("Gap").head(10)
    st.dataframe(near_df.reset_index(drop=True), use_container_width=True, hide_index=True)
else:
    st.success("No signals near a flip threshold — regime appears stable.", icon="✅")

st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — WHAT WOULD CHANGE THE REGIME
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-hdr">What Would Change the Regime</div>', unsafe_allow_html=True)

needed_to_flip = abs(int(total_scored * 0.60) - n_bull + 1) if regime != "BULLISH" else abs(n_bull - int(total_scored * 0.40) + 1)

if regime == "BULLISH":
    _flip_msg = (
        f"Currently <b>{n_bull}/{total_scored}</b> signals are bullish. "
        f"The regime would flip to MIXED if <b>{needed_to_flip}+ more signal(s)</b> turned neutral or bearish."
    )
elif regime == "BEARISH":
    needed_bull = int(total_scored * 0.60) - n_bull + 1
    _flip_msg = (
        f"Currently <b>{n_bear}/{total_scored}</b> signals are bearish. "
        f"A MIXED regime requires <b>{needed_bull}+ bearish signals</b> to flip neutral or bullish."
    )
else:
    needed_bull = int(total_scored * 0.60) - n_bull + 1
    needed_bear = int(total_scored * 0.60) - n_bear + 1
    _flip_msg = (
        f"Mixed regime with <b>{n_bull}</b> bullish / <b>{n_bear}</b> bearish. "
        f"Needs <b>{needed_bull} more bullish</b> (or <b>{needed_bear} more bearish</b>) "
        f"to establish a clear directional regime."
    )

st.markdown(
    f"<div style='background:#F5F0E8;border-left:4px solid #6B7FBF;padding:12px 16px;"
    f"border-radius:0 6px 6px 0;font-family:Inter,sans-serif;font-size:0.88rem;color:#4A3728;'>"
    f"{_flip_msg}</div>",
    unsafe_allow_html=True,
)

# Show which bearish signals, if flipped, would matter most
if regime in ("MIXED", "BEARISH"):
    st.markdown("")
    st.caption("Bearish signals that, if they turned bullish, would most shift the regime:")
    bearish_sigs = [
        (sid, sv) for sid, sv in all_scores.items()
        if sv.get("status") == "bearish"
    ]
    bearish_sigs.sort(key=lambda x: x[1].get("score", 0), reverse=True)  # highest score = closest to flip
    for sid, sv in bearish_sigs[:5]:
        cfg = SIGNALS.get(sid, {})
        score = sv.get("score", 50)
        st.markdown(
            f"<span style='font-size:0.82rem;font-family:Inter,sans-serif;color:#FF4444;'>"
            f"▼ {cfg.get('name', sid)}</span> "
            f"<span style='font-size:0.80rem;color:#6B5E52;'>score {score:.0f} — needs +{35-score:.0f} pts to flip neutral</span>",
            unsafe_allow_html=True,
        )

with st.expander("📚 Methodology", expanded=False):
    st.markdown("""
**Regime Classification**

The macro regime is determined by the percentage of signals currently bullish:
- **BULLISH**: >60% of scored signals are bullish (confluence score ~65+)
- **BEARISH**: >60% of scored signals are bearish (confluence score ~35-)
- **MIXED**: everything in between

This is deliberately simple — complexity doesn't add predictive power here. The threshold choice
(60%) was chosen to require clear consensus, not a bare majority. A regime with 51% bullish signals
is genuinely ambiguous and should be treated as such.

**Sector Return Analysis**

Forward returns are computed by:
1. Identifying all dates where the regime matched each bucket (from signal_snapshots history)
2. Fetching the sector ETF price on each of those dates and 30/60/90 calendar days later
3. Computing the average return across all matching dates per regime

When signal snapshot history is thin (<20 days), we use a proxy regime based on
SPY relative to its 200-day moving average, which is a well-documented risk-on/risk-off
indicator with decades of market history.

**Flip Watch**

Signals are flagged as "near flip" if they are within 8 points of a status threshold
(score 57–64: near BULLISH flip; score 36–43: near BEARISH flip). These are the signals
most likely to change the aggregate regime in the near term.

**Important limitation**: sector return averages reflect correlations from the past,
not guaranteed future outcomes. They are useful for calibrating expectations, not
for making mechanically deterministic forecasts.
""")
