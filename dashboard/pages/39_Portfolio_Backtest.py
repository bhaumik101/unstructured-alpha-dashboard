# pages/39_Portfolio_Backtest.py
# Unstructured Alpha — Signal Portfolio Backtester
#
# Simulates a long/short paper portfolio driven entirely by UA's confluence
# scores. At each rebalance date: go long the top-N bullish tickers and short
# the bottom-N bearish tickers, equal-weighted. Tracks realized returns, P&L,
# and standard risk-adjusted performance metrics.
#
# Two backtest modes:
#   1. Live Score History  — uses actual score_snapshots from the DB.
#      True walk-forward: scores were recorded at the time, prices are real.
#      Date range limited to when the system has been running (months, not years).
#
#   2. Reconstructed (Multi-Year) — uses TODAY's macro confluence scores to
#      rank tickers, then traces those FIXED rankings back through 3 years of
#      historical prices. Equivalent to asking: "If I had owned the machine's
#      current top picks for the last N years, what would have happened?"
#      ⚠ Look-ahead bias applies — treat as signal quality validation, not
#      a true walk-forward test.

import streamlit as st

st.set_page_config(
    page_title="Portfolio Backtest — UA",
    layout="wide",
    initial_sidebar_state="expanded",
)

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.theme import inject_premium_css
from utils.config import TICKERS
from utils.billing import require_pro

render_header("Portfolio Backtest")
render_sidebar_base()
inject_premium_css()

require_pro(page_name="Signal Portfolio Backtest")

render_page_header(
    "Signal Portfolio Backtest",
    "Long the most bullish tickers, short the most bearish — driven entirely by UA's confluence scores.",
    icon="📈",
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _portfolio_stats(equity: pd.Series, rf_annual: float = 0.05) -> dict:
    """Standard annualised performance metrics for an equity curve."""
    if len(equity) < 5 or equity.iloc[0] == 0:
        return {}
    daily_ret = equity.pct_change().dropna()
    total_ret  = (equity.iloc[-1] / equity.iloc[0] - 1) * 100
    n_days     = max((equity.index[-1] - equity.index[0]).days, 1)
    years      = n_days / 365.25
    cagr       = ((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) * 100 if years > 0 else 0
    daily_rf   = rf_annual / 252
    excess     = daily_ret - daily_rf
    sharpe     = float(excess.mean() / excess.std() * np.sqrt(252)) if excess.std() > 0 else 0.0
    roll_max   = equity.cummax()
    drawdowns  = (equity / roll_max - 1)
    max_dd     = float(drawdowns.min() * 100)
    win_rate   = float((daily_ret > 0).mean() * 100)
    return {
        "Total Return":   f"{total_ret:+.1f}%",
        "CAGR":           f"{cagr:+.1f}%",
        "Sharpe Ratio":   f"{sharpe:.2f}",
        "Max Drawdown":   f"{max_dd:.1f}%",
        "Win Rate (day)": f"{win_rate:.0f}%",
        "Days":           str(n_days),
    }


def _render_stats_row(stats: dict, label: str, color: str) -> None:
    if not stats:
        st.info("Not enough data to compute statistics.")
        return
    st.markdown(
        f'<div style="font-size:0.65rem;font-weight:700;color:{color};'
        f'text-transform:uppercase;letter-spacing:0.10em;margin-bottom:8px;">{label}</div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(stats))
    for col, (k, v) in zip(cols, stats.items()):
        color_val = (
            "#00D566" if (v.startswith("+") or (k == "Sharpe Ratio" and float(v) > 0))
            else "#FF4444" if (v.startswith("-") or (k == "Max Drawdown"))
            else "#E2E8F0"
        )
        col.markdown(
            f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);'
            f'border-radius:8px;padding:12px 10px;text-align:center;">'
            f'<div style="font-size:1.0rem;font-weight:800;color:{color_val};">{v}</div>'
            f'<div style="font-size:0.60rem;color:#8892AA;margin-top:4px;text-transform:uppercase;'
            f'letter-spacing:0.08em;">{k}</div></div>',
            unsafe_allow_html=True,
        )


def _equity_chart(curves: dict[str, pd.Series], title: str) -> go.Figure:
    """Multi-curve equity chart (all rebased to 100)."""
    palette = {
        "Long Portfolio": "#00D566",
        "Short Portfolio": "#FF4444",
        "Long–Short Combined": "#4A9EFF",
        "SPY Benchmark": "#8892AA",
    }
    fig = go.Figure()
    for name, curve in curves.items():
        if curve is None or len(curve) < 2:
            continue
        rebased = curve / curve.iloc[0] * 100
        fig.add_trace(go.Scatter(
            x=rebased.index, y=rebased.values,
            name=name,
            line=dict(color=palette.get(name, "#FFFFFF"), width=2),
            hovertemplate=f"<b>{name}</b><br>%{{x|%b %d, %Y}}<br>Value: %{{y:.1f}}<extra></extra>",
        ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=13, color="#E2E8F0"), x=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8892AA", family="Inter"),
        xaxis=dict(showgrid=False, color="#4A5568"),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", ticksuffix="", color="#4A5568",
                   title="Value (rebased to 100)"),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        margin=dict(t=40, b=40, l=50, r=20),
        height=360,
        hovermode="x unified",
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

with st.expander("⚙️ Backtest Configuration", expanded=True):
    cfg_c1, cfg_c2, cfg_c3, cfg_c4 = st.columns(4)
    with cfg_c1:
        bull_thresh  = st.slider("Long threshold (score ≥)", 55, 80, 65, 1,
                                  help="Tickers scoring above this are eligible for the long portfolio.")
        bear_thresh  = st.slider("Short threshold (score ≤)", 20, 45, 35, 1,
                                  help="Tickers scoring below this are eligible for the short portfolio.")
    with cfg_c2:
        n_positions  = st.slider("Positions per side", 3, 20, 5, 1,
                                  help="Number of long positions and number of short positions held simultaneously.")
        rebal_label  = st.radio("Rebalance frequency", ["Weekly", "Monthly"], horizontal=True)
        rebal_days   = 7 if rebal_label == "Weekly" else 30
    with cfg_c3:
        lookback_reco = st.slider("Reconstructed history (years)", 1, 5, 3, 1,
                                   help="How many years of price history to use for the reconstructed backtest.")
    with cfg_c4:
        capital      = st.number_input("Starting capital ($)", value=10_000, step=1_000, min_value=1_000)

# ─────────────────────────────────────────────────────────────────────────────
# Current Live Positions (fast — uses cached macro scores, no price fetch)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("### 📋 Current Portfolio Positions")
st.caption("What the model would hold right now, based on live macro confluence scores.")

try:
    from utils.top_tickers import get_top_tickers
    from utils.signals_cache import get_all_signal_scores
    _all_scores = get_all_signal_scores()
    _top = get_top_tickers(signal_scores_hash=len(_all_scores))

    _all_rows = sorted(
        _top.get("bullish", []) + _top.get("bearish", []) +
        [r for r in _top.get("by_sector", {}).values()
         if isinstance(r, list) for r in r],
        key=lambda r: -r["score"]
    )
    # Deduplicate
    _seen = set()
    _deduped = []
    for r in _all_rows:
        if r["ticker"] not in _seen:
            _seen.add(r["ticker"])
            _deduped.append(r)

    _longs  = [r for r in _deduped if r["score"] >= bull_thresh][:n_positions]
    _shorts = [r for r in reversed(_deduped) if r["score"] <= bear_thresh][:n_positions]

    def _pos_card(row, side):
        c = "#00D566" if side == "long" else "#FF4444"
        label = "LONG" if side == "long" else "SHORT"
        bar_w = int(row["score"])
        bar_c = c
        return (
            f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
            f'border-left:3px solid {c};border-radius:8px;padding:12px 14px;margin-bottom:8px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<div><span style="font-size:1.0rem;font-weight:800;color:#E8EEFF;">{row["ticker"]}</span>'
            f'<span style="font-size:0.70rem;color:#8892AA;margin-left:8px;">{row["name"]}</span></div>'
            f'<div style="display:flex;align-items:center;gap:10px;">'
            f'<span style="font-size:0.62rem;font-weight:700;color:{c};background:rgba(0,0,0,0.3);'
            f'padding:2px 8px;border-radius:10px;">{label}</span>'
            f'<span style="font-size:0.92rem;font-weight:700;color:{c};">{row["score"]:.0f}</span>'
            f'</div></div>'
            f'<div style="margin-top:8px;background:rgba(255,255,255,0.05);border-radius:4px;height:4px;">'
            f'<div style="width:{bar_w}%;background:{bar_c};border-radius:4px;height:4px;"></div></div>'
            f'<div style="font-size:0.60rem;color:#6B7FBF;margin-top:6px;">'
            f'▲{row["bull"]} bullish · ▼{row["bear"]} bearish · {row["signals"]} signals · {row["sector"]}'
            f'</div></div>'
        )

    pos_col1, pos_col2 = st.columns(2)
    with pos_col1:
        st.markdown('<div style="font-size:0.65rem;font-weight:700;color:#00D566;letter-spacing:0.10em;'
                    'text-transform:uppercase;margin-bottom:10px;">🟢 Long Positions</div>',
                    unsafe_allow_html=True)
        if _longs:
            for r in _longs:
                st.markdown(_pos_card(r, "long"), unsafe_allow_html=True)
        else:
            st.info(f"No tickers currently score ≥ {bull_thresh}. Lower the long threshold.")
    with pos_col2:
        st.markdown('<div style="font-size:0.65rem;font-weight:700;color:#FF4444;letter-spacing:0.10em;'
                    'text-transform:uppercase;margin-bottom:10px;">🔴 Short Positions</div>',
                    unsafe_allow_html=True)
        if _shorts:
            for r in _shorts:
                st.markdown(_pos_card(r, "short"), unsafe_allow_html=True)
        else:
            st.info(f"No tickers currently score ≤ {bear_thresh}. Raise the short threshold.")
except Exception as _e:
    st.warning(f"Could not load live positions: {_e}")

st.markdown("---")

# ─────────────────────────────────────────────────────────────────────────────
# Backtest Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_live, tab_reco = st.tabs([
    "📊 Live Score History (Walk-Forward)",
    "🔭 Reconstructed Multi-Year View",
])

# ── Tab 1: Live walk-forward backtest ─────────────────────────────────────────
with tab_live:
    st.markdown("""
    <div style="background:rgba(0,200,224,0.06);border:1px solid rgba(0,200,224,0.18);
                border-radius:8px;padding:12px 16px;margin-bottom:18px;">
    <span style="font-size:0.75rem;font-weight:700;color:#00C8E0;">✓ Walk-Forward Backtest</span>
    <span style="font-size:0.78rem;color:#8892AA;margin-left:8px;">
    Uses actual UA confluence scores recorded at the time — no hindsight bias.
    Date range is limited to when the platform has been running.
    </span></div>
    """, unsafe_allow_html=True)

    @st.cache_data(ttl=3600, show_spinner=False, max_entries=4)
    def run_live_backtest(bull_t: float, bear_t: float, n_pos: int, rebal_days: int, capital: float):
        """
        Walk-forward portfolio simulation from real score_snapshots.
        Returns equity curves and per-ticker contribution.
        """
        import yfinance as yf
        from sqlalchemy import select
        from utils.db import score_snapshots, engine

        # 1. Load all snapshots
        try:
            with engine.begin() as conn:
                rows = conn.execute(
                    select(score_snapshots).order_by(
                        score_snapshots.c.ticker,
                        score_snapshots.c.snapshot_date,
                    )
                ).mappings().all()
        except Exception:
            return None

        if not rows:
            return None

        df_snap = pd.DataFrame([dict(r) for r in rows])
        df_snap["snapshot_date"] = pd.to_datetime(df_snap["snapshot_date"])

        # Date range
        date_min = df_snap["snapshot_date"].min()
        date_max = df_snap["snapshot_date"].max()
        if (date_max - date_min).days < 14:
            return None  # too little history

        # 2. Pivot to wide (date × ticker) and forward-fill
        pivot = (
            df_snap.pivot_table(index="snapshot_date", columns="ticker", values="score", aggfunc="last")
            .asfreq("D")
            .ffill()
        )

        # 3. Fetch price data for all tickers in snapshot universe + SPY
        all_tickers = list(pivot.columns) + (["SPY"] if "SPY" not in pivot.columns else [])
        price_start = (date_min - timedelta(days=5)).strftime("%Y-%m-%d")
        price_end   = (date_max + timedelta(days=5)).strftime("%Y-%m-%d")

        try:
            prices_raw = yf.download(
                all_tickers, start=price_start, end=price_end,
                auto_adjust=True, progress=False, threads=True,
            )
            if isinstance(prices_raw.columns, pd.MultiIndex):
                prices = prices_raw["Close"].copy()
            else:
                prices = prices_raw[["Close"]].copy()
                prices.columns = [all_tickers[0]]
        except Exception:
            return None

        prices.index = pd.to_datetime(prices.index).tz_localize(None)

        # 4. Build rebalance schedule
        rebal_dates = []
        cursor = date_min
        while cursor <= date_max:
            rebal_dates.append(cursor)
            cursor += timedelta(days=rebal_days)

        # 5. Simulate portfolio day-by-day
        date_range = pd.date_range(date_min, date_max, freq="D")
        long_pnl  = pd.Series(index=date_range, dtype=float).fillna(0.0)
        short_pnl = pd.Series(index=date_range, dtype=float).fillna(0.0)
        spy_pnl   = pd.Series(index=date_range, dtype=float).fillna(0.0)

        ticker_contributions: dict[str, float] = {}
        current_longs: list[str] = []
        current_shorts: list[str] = []

        for i, rb_date in enumerate(rebal_dates):
            next_rb = rebal_dates[i + 1] if i + 1 < len(rebal_dates) else date_max
            period_dates = pd.date_range(rb_date, next_rb - timedelta(days=1), freq="D")

            # Get scores on rebalance date (forward-filled)
            snap_row = pivot[pivot.index <= rb_date]
            if snap_row.empty:
                continue
            scores_now = snap_row.iloc[-1].dropna()

            longs  = scores_now[scores_now >= bull_t].nlargest(n_pos).index.tolist()
            shorts = scores_now[scores_now <= bear_t].nsmallest(n_pos).index.tolist()

            # Remove cross-side tickers (safety)
            longs  = [t for t in longs  if t not in shorts]
            shorts = [t for t in shorts if t not in longs]

            current_longs  = longs
            current_shorts = shorts

            # Compute daily returns for each position
            for d_idx, d in enumerate(period_dates):
                if d not in date_range:
                    continue
                d_prev = d - timedelta(days=1)

                # Long portfolio daily return (equal weight)
                long_day_ret = 0.0
                long_count   = 0
                for t in longs:
                    if t in prices.columns:
                        p_now  = prices.loc[prices.index <= d,  t].dropna()
                        p_prev = prices.loc[prices.index <= d_prev, t].dropna()
                        if not p_now.empty and not p_prev.empty and p_prev.iloc[-1] != 0:
                            ret = (p_now.iloc[-1] / p_prev.iloc[-1] - 1)
                            long_day_ret += ret
                            long_count += 1
                            ticker_contributions[t] = ticker_contributions.get(t, 0.0) + ret
                if long_count > 0:
                    long_pnl[d] = long_pnl.get(d, 0.0) + long_day_ret / long_count

                # Short portfolio daily return (inverted, equal weight)
                short_day_ret = 0.0
                short_count   = 0
                for t in shorts:
                    if t in prices.columns:
                        p_now  = prices.loc[prices.index <= d,  t].dropna()
                        p_prev = prices.loc[prices.index <= d_prev, t].dropna()
                        if not p_now.empty and not p_prev.empty and p_prev.iloc[-1] != 0:
                            ret = -(p_now.iloc[-1] / p_prev.iloc[-1] - 1)  # inverted for short
                            short_day_ret += ret
                            short_count += 1
                            ticker_contributions[t] = ticker_contributions.get(t, 0.0) + ret
                if short_count > 0:
                    short_pnl[d] = short_pnl.get(d, 0.0) + short_day_ret / short_count

                # SPY
                if "SPY" in prices.columns:
                    p_now  = prices.loc[prices.index <= d,  "SPY"].dropna()
                    p_prev = prices.loc[prices.index <= d_prev, "SPY"].dropna()
                    if not p_now.empty and not p_prev.empty and p_prev.iloc[-1] != 0:
                        spy_pnl[d] = p_now.iloc[-1] / p_prev.iloc[-1] - 1

        # 6. Build equity curves
        def _to_equity(ret_series, cap):
            eq = (1 + ret_series).cumprod() * cap
            eq.iloc[0] = cap
            return eq.dropna()

        long_eq  = _to_equity(long_pnl.dropna(), capital)
        short_eq = _to_equity(short_pnl.dropna(), capital)
        spy_eq   = _to_equity(spy_pnl.dropna(), capital)

        # Combined long-short
        combined_ret = (long_pnl + short_pnl) / 2
        combined_eq  = _to_equity(combined_ret.dropna(), capital)

        return {
            "long_eq": long_eq,
            "short_eq": short_eq,
            "combined_eq": combined_eq,
            "spy_eq": spy_eq,
            "ticker_contributions": ticker_contributions,
            "date_range": (date_min.date().isoformat(), date_max.date().isoformat()),
            "current_longs": current_longs,
            "current_shorts": current_shorts,
        }

    with st.spinner("Running walk-forward backtest from score history…"):
        live_result = run_live_backtest(
            bull_thresh, bear_thresh, n_positions, rebal_days, float(capital)
        )

    if live_result is None:
        st.info(
            "Not enough historical score snapshots yet to run a walk-forward backtest. "
            "Scores are recorded each time tickers are viewed; the database needs at least "
            "2 weeks of history across multiple tickers. Check back as the platform accumulates data, "
            "or see the Reconstructed tab for a multi-year view."
        )
    else:
        dr = live_result["date_range"]
        st.caption(f"Score snapshot range: {dr[0]} → {dr[1]}")

        fig_live = _equity_chart({
            "Long Portfolio":      live_result["long_eq"],
            "Short Portfolio":     live_result["short_eq"],
            "Long–Short Combined": live_result["combined_eq"],
            "SPY Benchmark":       live_result["spy_eq"],
        }, "Portfolio Equity Curves (rebased to 100)")
        st.plotly_chart(fig_live, use_container_width=True)

        s1, s2 = st.columns(2)
        with s1:
            _render_stats_row(_portfolio_stats(live_result["long_eq"]),
                              "Long Portfolio", "#00D566")
        with s2:
            _render_stats_row(_portfolio_stats(live_result["short_eq"]),
                              "Short Portfolio", "#FF4444")
        st.markdown("<br>", unsafe_allow_html=True)
        _render_stats_row(_portfolio_stats(live_result["combined_eq"]),
                          "Long–Short Combined", "#4A9EFF")

        # Per-ticker contributions
        if live_result["ticker_contributions"]:
            st.markdown("#### Per-Ticker Return Contribution")
            contrib = pd.DataFrame([
                {"Ticker": t, "Cumulative Return Contribution": f"{v*100:+.2f}%",
                 "Side": "Long" if t in live_result["current_longs"] else "Short"}
                for t, v in sorted(live_result["ticker_contributions"].items(),
                                   key=lambda x: -abs(x[1]))
            ])
            st.dataframe(contrib, use_container_width=True, hide_index=True)


# ── Tab 2: Reconstructed multi-year view ──────────────────────────────────────
with tab_reco:
    st.markdown(f"""
    <div style="background:rgba(245,158,11,0.07);border:1px solid rgba(245,158,11,0.28);
                border-left:4px solid #F59E0B;border-radius:8px;padding:12px 16px;margin-bottom:18px;">
    <span style="font-size:0.75rem;font-weight:700;color:#F59E0B;">⚠ Methodology Note</span>
    <span style="font-size:0.78rem;color:#8892AA;margin-left:8px;">
    This view uses <b>today's macro scores</b> to rank tickers, then traces those fixed rankings back
    through {lookback_reco} years of historical prices. It answers: "If I had held the machine's
    current top picks for the last {lookback_reco} years, what would have happened?"
    This is a <b>look-ahead bias</b> test — current scores incorporate signal patterns that may not
    have been apparent historically. Use as signal quality validation, not a predictive claim.
    </span></div>
    """, unsafe_allow_html=True)

    @st.cache_data(ttl=7200, show_spinner=False, max_entries=4)
    def run_reconstructed_backtest(
        bull_t: float, bear_t: float, n_pos: int, years: int, capital: float
    ):
        import yfinance as yf
        from utils.top_tickers import get_top_tickers
        from utils.signals_cache import get_all_signal_scores

        all_scores = get_all_signal_scores()
        top = get_top_tickers(signal_scores_hash=len(all_scores))

        # Build full ranked list
        all_rows: list[dict] = []
        seen: set = set()
        for r in (top.get("bullish", []) + top.get("bearish", [])):
            if r["ticker"] not in seen:
                seen.add(r["ticker"])
                all_rows.append(r)
        all_rows.sort(key=lambda r: -r["score"])

        longs_meta  = [r for r in all_rows if r["score"] >= bull_t][:n_pos]
        shorts_meta = [r for r in reversed(all_rows) if r["score"] <= bear_t][:n_pos]

        long_tickers  = [r["ticker"] for r in longs_meta]
        short_tickers = [r["ticker"] for r in shorts_meta]

        if not long_tickers and not short_tickers:
            return None

        all_fetch = list(set(long_tickers + short_tickers + ["SPY"]))
        start = (datetime.now() - timedelta(days=int(years * 365.25))).strftime("%Y-%m-%d")
        end   = datetime.now().strftime("%Y-%m-%d")

        try:
            raw = yf.download(all_fetch, start=start, end=end,
                              auto_adjust=True, progress=False, threads=True)
            if isinstance(raw.columns, pd.MultiIndex):
                prices = raw["Close"].copy()
            else:
                prices = raw[["Close"]].copy()
                prices.columns = [all_fetch[0]]
        except Exception:
            return None

        prices.index = pd.to_datetime(prices.index).tz_localize(None)
        prices = prices.dropna(how="all")

        def _portfolio_curve(tickers, invert=False):
            """Equal-weight portfolio equity curve."""
            available = [t for t in tickers if t in prices.columns]
            if not available:
                return None
            rets = prices[available].pct_change().dropna(how="all")
            port_ret = rets.mean(axis=1)
            if invert:
                port_ret = -port_ret
            eq = (1 + port_ret).cumprod() * capital
            eq.iloc[0] = capital
            return eq

        spy_eq  = _portfolio_curve(["SPY"])
        long_eq  = _portfolio_curve(long_tickers)
        short_eq = _portfolio_curve(short_tickers, invert=True)

        if long_eq is not None and short_eq is not None:
            # Align on common dates
            common = long_eq.index.intersection(short_eq.index)
            combined_ret = (
                long_eq[common].pct_change().fillna(0) +
                short_eq[common].pct_change().fillna(0)
            ) / 2
            combined_eq = (1 + combined_ret).cumprod() * capital
            combined_eq.iloc[0] = capital
        else:
            combined_eq = long_eq or short_eq

        return {
            "long_eq":    long_eq,
            "short_eq":   short_eq,
            "combined_eq": combined_eq,
            "spy_eq":     spy_eq,
            "long_tickers":  [{"ticker": r["ticker"], "name": r["name"],
                                "score": r["score"], "sector": r["sector"]} for r in longs_meta],
            "short_tickers": [{"ticker": r["ticker"], "name": r["name"],
                                "score": r["score"], "sector": r["sector"]} for r in shorts_meta],
        }

    with st.spinner(f"Fetching {lookback_reco} years of price history…"):
        reco_result = run_reconstructed_backtest(
            bull_thresh, bear_thresh, n_positions, lookback_reco, float(capital)
        )

    if reco_result is None:
        st.info("No tickers meet the current thresholds. Adjust the long/short thresholds above.")
    else:
        # Show which tickers are in each portfolio
        rc1, rc2 = st.columns(2)
        with rc1:
            st.markdown("**Long basket (current top picks)**")
            for r in reco_result["long_tickers"]:
                st.markdown(f'`{r["ticker"]}` {r["name"]} — score **{r["score"]:.0f}**')
        with rc2:
            st.markdown("**Short basket (current bottom picks)**")
            for r in reco_result["short_tickers"]:
                st.markdown(f'`{r["ticker"]}` {r["name"]} — score **{r["score"]:.0f}**')

        st.markdown("<br>", unsafe_allow_html=True)

        fig_reco = _equity_chart({
            "Long Portfolio":      reco_result["long_eq"],
            "Short Portfolio":     reco_result["short_eq"],
            "Long–Short Combined": reco_result["combined_eq"],
            "SPY Benchmark":       reco_result["spy_eq"],
        }, f"Reconstructed {lookback_reco}-Year Portfolio (rebased to 100, fixed composition)")
        st.plotly_chart(fig_reco, use_container_width=True)

        rs1, rs2 = st.columns(2)
        with rs1:
            _render_stats_row(
                _portfolio_stats(reco_result["long_eq"]) if reco_result["long_eq"] is not None else {},
                "Long Portfolio", "#00D566"
            )
        with rs2:
            _render_stats_row(
                _portfolio_stats(reco_result["short_eq"]) if reco_result["short_eq"] is not None else {},
                "Short Portfolio", "#FF4444"
            )
        if reco_result["combined_eq"] is not None:
            st.markdown("<br>", unsafe_allow_html=True)
            _render_stats_row(
                _portfolio_stats(reco_result["combined_eq"]),
                "Long–Short Combined", "#4A9EFF"
            )

        # Per-ticker historical return table
        st.markdown("#### Historical Returns by Ticker")
        import yfinance as _yf
        @st.cache_data(ttl=7200, show_spinner=False, max_entries=4)
        def _ticker_rets(tickers, years):
            start = (datetime.now() - timedelta(days=int(years * 365.25))).strftime("%Y-%m-%d")
            try:
                raw = _yf.download(tickers, start=start, auto_adjust=True,
                                   progress=False, threads=True)
                prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
                return prices
            except Exception:
                return pd.DataFrame()

        all_t = (
            [r["ticker"] for r in reco_result["long_tickers"]] +
            [r["ticker"] for r in reco_result["short_tickers"]]
        )
        _hist = _ticker_rets(all_t, lookback_reco)
        if not _hist.empty:
            rets_table = []
            for r in reco_result["long_tickers"] + reco_result["short_tickers"]:
                t = r["ticker"]
                side = "Long" if r in reco_result["long_tickers"] else "Short"
                if t in _hist.columns:
                    col = _hist[t].dropna()
                    if len(col) >= 2:
                        total = (col.iloc[-1] / col.iloc[0] - 1) * 100
                        # flip sign for short
                        reported = total if side == "Long" else -total
                        rets_table.append({
                            "Ticker": t, "Name": r["name"], "Side": side,
                            "UA Score": f"{r['score']:.0f}",
                            f"Return ({lookback_reco}Y)": f"{reported:+.1f}%",
                            "Sector": r["sector"],
                        })
            if rets_table:
                st.dataframe(pd.DataFrame(rets_table), use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# Footer note
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(
    "Past performance of simulated portfolios does not guarantee future results. "
    "This is a research tool, not investment advice. Confluence scores are based on "
    "macro signal alignment — they do not incorporate transaction costs, slippage, or "
    "bid-ask spreads. Short positions carry theoretically unlimited downside risk. "
    "Unstructured Alpha is not a registered investment adviser."
)
