"""
pages/35_Signal_Strategy.py
Unstructured Alpha — Signal-Driven Strategy Backtester

Interactive page showing how macro signal confluence translates into
mechanical, rules-based positioning — and how that has performed
vs. SPY buy-and-hold since 2010.

Key design decisions:
  - No lookahead bias: position on day D uses composite score from day D-1
  - Transaction costs: 0.1% round-trip applied on every position change
  - Rolling 252-day percentile normalization (same as live signals in dashboard)
  - Three states: LONG (100% SPY), REDUCED (50% SPY), CASH (0% SPY)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils.header import render_header
from utils.theme import inject_all_css, PLOTLY_CONFIG

st.set_page_config(page_title="Signal Strategy | Unstructured Alpha", layout="wide")
from utils.billing import require_pro
require_pro(
    "Signal Backtester",
    "Test configurable signal thresholds with point-in-time rules, costs, and benchmark comparisons.",
)
inject_all_css()
render_header()

# ── Page header ──────────────────────────────────────────────────────────────
st.markdown("""
<div style='text-align:center; padding: 2rem 0 1rem;'>
  <h1 style='font-size:2.2rem; font-weight:700; margin-bottom:0.5rem;'>Signal-Driven Strategy Backtest</h1>
  <p style='color:var(--text-muted); font-size:1.05rem; max-width:640px; margin:0 auto;'>
    A rules-based strategy built on Unstructured Alpha's macro signals.
    Tested from 2010 to present using only data available at the time of each trade.
  </p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ── Sidebar: parameters ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("###  Strategy Parameters")
    long_threshold   = st.slider("Bullish threshold (→ LONG)", 50, 80, 65, 5,
                                 help="Composite score above this = 100% long SPY")
    reduce_threshold = st.slider("Bearish threshold (→ CASH)", 20, 50, 35, 5,
                                 help="Composite score below this = 0% (cash)")
    reduce_weight    = st.slider("Reduced exposure weight", 0.25, 0.75, 0.50, 0.05,
                                 help="Position size when score is between the two thresholds")
    start_year       = st.selectbox("Backtest start", [2010, 2012, 2015, 2018, 2020], index=0)

    st.markdown("---")
    st.markdown("""
**Signals used:**
- Yield Curve (10Y–2Y)
- HY Credit Spread
- VIX (Fear Index)
- 10Y Treasury Yield
- Copper/Gold Ratio
- Put/Call Ratio
- M2 Money Supply

All scored as rolling 252-day percentile.
Higher score = better macro backdrop.
    """)
    st.markdown("""
<div style='font-size:0.7rem; color:var(--text-muted); margin-top:1rem;'>
<b>Disclaimer:</b> Backtests show what <i>would have happened</i> given perfect
execution of the strategy rules. Past performance does not guarantee future results.
This is not investment advice.
</div>
""", unsafe_allow_html=True)

# ── Run backtest (cached) ─────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False, max_entries=50)
def _run(start_year: int, long_t: float, reduce_t: float, reduce_w: float) -> dict:
    from utils.strategy import run_backtest
    return run_backtest(
        start=f"{start_year}-01-01",
        long_threshold=long_t,
        reduce_threshold=reduce_t,
        reduce_weight=reduce_w,
    )


with st.spinner("Running backtest — fetching macro signals..."):
    result = _run(start_year, float(long_threshold), float(reduce_threshold), float(reduce_weight))

if result.get("error"):
    st.error(f"Backtest failed: {result['error']}")
    st.info("Check that `pandas_datareader` is installed and FRED/yfinance are reachable.")
    st.stop()

df      = result["results_df"]
strat_m = result["strategy_metrics"]
bench_m = result["benchmark_metrics"]
params  = result["params"]

# ── Live signal state ─────────────────────────────────────────────────────────
from utils.strategy import get_current_position
live = get_current_position(result)

if live:
    pos_color = {
        "LONG":    "#22c55e",
        "REDUCED": "#f59e0b",
        "CASH":    "#ef4444",
    }.get(live["position"], "#94a3b8")

    st.markdown(f"""
<div style='background:var(--card-bg); border:1px solid var(--border); border-radius:12px;
            padding:1.25rem 1.5rem; margin-bottom:1.5rem; display:flex; align-items:center; gap:2rem;'>
  <div>
    <div style='font-size:0.75rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:.05em;'>Current Signal Position</div>
    <div style='font-size:1.8rem; font-weight:700; color:{pos_color};'>{live["position"]} ({int(live["position_pct"])}%)</div>
    <div style='font-size:0.8rem; color:var(--text-muted);'>As of {live["as_of"]}</div>
  </div>
  <div>
    <div style='font-size:0.75rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:.05em;'>Composite Score</div>
    <div style='font-size:1.8rem; font-weight:700;'>{live["composite_score"]:.0f}<span style='font-size:1rem;color:var(--text-muted);'>/100</span></div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Performance metric cards ──────────────────────────────────────────────────
st.markdown("### Performance Summary")

def _delta_color(val: float) -> str:
    return "#22c55e" if val >= 0 else "#ef4444"

def _metric_html(label: str, strat_val, bench_val, fmt: str = "{:.1f}%", higher_better: bool = True) -> str:
    s_str = fmt.format(strat_val)
    b_str = fmt.format(bench_val)
    diff  = strat_val - bench_val
    arrow = "▲" if diff >= 0 else "▼"
    col   = "#22c55e" if (diff >= 0) == higher_better else "#ef4444"
    diff_str = fmt.format(abs(diff))
    return f"""
<div style='background:var(--card-bg); border:1px solid var(--border); border-radius:10px;
            padding:1rem 1.25rem;'>
  <div style='font-size:0.7rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:.05em; margin-bottom:.4rem;'>{label}</div>
  <div style='font-size:1.5rem; font-weight:700;'>{s_str}</div>
  <div style='font-size:0.75rem; color:var(--text-muted);'>SPY: {b_str}
    <span style='color:{col}; margin-left:.5rem;'>{arrow} {diff_str}</span>
  </div>
</div>"""

cols = st.columns(4)
with cols[0]:
    st.html(_metric_html("CAGR", strat_m["cagr"], bench_m["cagr"]))
with cols[1]:
    st.html(_metric_html("Sharpe Ratio", strat_m["sharpe"], bench_m["sharpe"], fmt="{:.2f}"))
with cols[2]:
    st.markdown(_metric_html("Max Drawdown", strat_m["max_drawdown"], bench_m["max_drawdown"],
                             higher_better=False), unsafe_allow_html=True)
with cols[3]:
    st.html(_metric_html("Calmar Ratio", strat_m["calmar"], bench_m["calmar"], fmt="{:.2f}"))

st.markdown("<br>", unsafe_allow_html=True)

# ── Equity curve chart ────────────────────────────────────────────────────────
st.markdown("### Equity Curve")

fig = make_subplots(
    rows=3, cols=1,
    shared_xaxes=True,
    row_heights=[0.55, 0.22, 0.23],
    vertical_spacing=0.04,
    subplot_titles=("Portfolio Value (starting $1)", "Composite Signal Score", "Strategy Position"),
)

# Panel 1: equity curves
fig.add_trace(go.Scatter(
    x=df.index, y=df["strat_cum"],
    name="Signal Strategy",
    line=dict(color="#6366f1", width=2),
    fill="tozeroy", fillcolor="rgba(99,102,241,0.08)",
), row=1, col=1)
fig.add_trace(go.Scatter(
    x=df.index, y=df["spy_cum"],
    name="SPY Buy-and-Hold",
    line=dict(color="#94a3b8", width=1.5, dash="dot"),
), row=1, col=1)

# Panel 2: composite score with threshold bands
fig.add_hrect(y0=long_threshold, y1=100, fillcolor="rgba(34,197,94,0.08)",
              line_width=0, row=2, col=1)
fig.add_hrect(y0=0, y1=reduce_threshold, fillcolor="rgba(239,68,68,0.08)",
              line_width=0, row=2, col=1)
fig.add_trace(go.Scatter(
    x=df.index, y=df["composite_score"],
    name="Composite Score",
    line=dict(color="#818cf8", width=1.5),
    showlegend=False,
), row=2, col=1)
fig.add_hline(y=long_threshold,   line=dict(color="#22c55e", width=1, dash="dash"), row=2, col=1)
fig.add_hline(y=reduce_threshold, line=dict(color="#ef4444", width=1, dash="dash"), row=2, col=1)

# Panel 3: position (step chart)
fig.add_trace(go.Scatter(
    x=df.index, y=df["position"] * 100,
    name="Exposure (%)",
    line=dict(color="#f59e0b", width=1.5, shape="hv"),
    fill="tozeroy", fillcolor="rgba(245,158,11,0.12)",
    showlegend=False,
), row=3, col=1)

fig.update_layout(
    height=680,
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", size=12, color="#94a3b8"),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        bgcolor="rgba(0,0,0,0)",
    ),
    margin=dict(l=0, r=0, t=32, b=0),
    hovermode="x unified",
)
fig.update_xaxes(showgrid=False, zeroline=False, tickfont=dict(size=11))
fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.05)", zeroline=False)
fig.update_yaxes(title_text="Value ($)", row=1, col=1)
fig.update_yaxes(title_text="Score (0–100)", row=2, col=1, range=[0, 100])
fig.update_yaxes(title_text="Exposure (%)", row=3, col=1, range=[0, 110])

st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, theme=None)

# ── Individual signal scores ──────────────────────────────────────────────────
st.markdown("### Individual Signal Scores")
st.markdown("<p style='color:var(--text-muted); font-size:0.875rem;'>Each signal scored 0–100 (rolling 252-day percentile). Higher = more bullish. Weighted composite drives the position.</p>", unsafe_allow_html=True)

sig_scores = result["signal_scores"]
if sig_scores and live.get("signal_scores"):
    cols2 = st.columns(min(len(live["signal_scores"]), 4))
    sig_items = list(live["signal_scores"].items())

    def _score_color(s):
        if s is None:
            return "#94a3b8"
        if s >= 65:
            return "#22c55e"
        if s <= 35:
            return "#ef4444"
        return "#f59e0b"

    for i, (name, score) in enumerate(sig_items):
        col = cols2[i % 4]
        color = _score_color(score)
        score_str = f"{score:.0f}" if score is not None else "N/A"
        label = "Bullish" if (score or 0) >= 65 else ("Bearish" if (score or 0) <= 35 else "Neutral")
        with col:
            st.markdown(f"""
<div style='background:var(--card-bg); border:1px solid var(--border); border-radius:10px;
            padding:.875rem 1rem; margin-bottom:.75rem;'>
  <div style='font-size:0.7rem; color:var(--text-muted); margin-bottom:.3rem;'>{name}</div>
  <div style='font-size:1.6rem; font-weight:700; color:{color};'>{score_str}</div>
  <div style='font-size:0.7rem; color:{color};'>{label}</div>
</div>""", unsafe_allow_html=True)

# ── Detailed metrics table ────────────────────────────────────────────────────
st.markdown("### Full Performance Comparison")

metrics_df = pd.DataFrame({
    "Metric":    ["Total Return", "CAGR", "Ann. Volatility", "Sharpe Ratio",
                  "Max Drawdown", "Win Rate (daily)", "Calmar Ratio"],
    "Strategy":  [
        f"{strat_m['total_return']:.1f}%",
        f"{strat_m['cagr']:.1f}%",
        f"{strat_m['volatility']:.1f}%",
        f"{strat_m['sharpe']:.2f}",
        f"{strat_m['max_drawdown']:.1f}%",
        f"{strat_m['win_rate']:.1f}%",
        f"{strat_m['calmar']:.2f}",
    ],
    "SPY B&H":   [
        f"{bench_m['total_return']:.1f}%",
        f"{bench_m['cagr']:.1f}%",
        f"{bench_m['volatility']:.1f}%",
        f"{bench_m['sharpe']:.2f}",
        f"{bench_m['max_drawdown']:.1f}%",
        f"{bench_m['win_rate']:.1f}%",
        f"{bench_m['calmar']:.2f}",
    ],
})
st.dataframe(metrics_df.set_index("Metric"), use_container_width=True)

# ── Methodology note ──────────────────────────────────────────────────────────
with st.expander(" Methodology & Limitations"):
    st.markdown(f"""
**How the composite score is built:**
Each of the {params['n_signals']} signals is independently normalized using a rolling {params['rolling_window']}-day (1-year)
percentile rank. A high score on an individual signal means today's reading is historically elevated
(favourable for risk assets, after inverting where appropriate). The composite is a weighted average
of all signal scores.

**Position rules (no lookahead):**
Yesterday's composite score determines today's position. The signal is never used in the same bar
it was computed — this eliminates lookahead bias.

| Composite Score | Position |
|---|---|
| ≥ {params['long_threshold']} | 100% long SPY |
| {params['reduce_threshold']} – {params['long_threshold']} | {int(params['reduce_weight']*100)}% long SPY |
| ≤ {params['reduce_threshold']} | Cash (0%) |

**Transaction costs:** {0.1:.1f}% round-trip applied on every position change (position fraction × 0.001).

**Signals (all daily-frequency):**
- **Yield Curve (T10Y2Y, FRED)** — inverted signal: a flatter/inverted curve scores lower
- **HY Credit Spread (BAMLH0A0HYM2, FRED)** — inverted: wider spreads = worse backdrop
- **VIX (^VIX, yfinance)** — inverted: higher fear = lower score
- **10Y Treasury Yield (^TNX, yfinance)** — inverted: used as a risk-off indicator
- **Copper/Gold Ratio (HG=F ÷ GLD, yfinance)** — direct: rising ratio = risk-on
- **Put/Call Ratio (CPCE, FRED)** — inverted: extreme fear is contrarian-bullish
- **M2 Money Supply (M2SL, FRED)** — direct: expanding money supply is supportive

**Important limitations:**
- Past performance is not indicative of future results
- The 1-year percentile window means the strategy adapts slowly to new regimes
- SPY is used as both the signal vehicle and benchmark; real execution would have slippage
- FRED data may be revised; the backtest uses latest-available values, not real-time vintage
- This analysis is purely for educational/research purposes and is NOT investment advice
    """)

# ── Footer disclaimer ─────────────────────────────────────────────────────────
st.markdown("""
<div style='border-top:1px solid var(--border); margin-top:3rem; padding-top:1rem;
            font-size:0.7rem; color:var(--text-muted); text-align:center;'>
Unstructured Alpha — Signal Strategy Backtester. For informational and educational purposes only.
Not investment advice. Past performance does not guarantee future results. Data sourced from FRED and Yahoo Finance.
</div>
""", unsafe_allow_html=True)
