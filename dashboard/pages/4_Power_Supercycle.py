"""
Page 4 — Power Supercycle Tracker
Multi-signal convergence for the nuclear + AI + copper + gas infrastructure thesis.
arXiv quantum paper velocity. Federal contract awards for nuclear companies.

RESTRUCTURED 2026-06-23: Previously 657 lines of 7 stacked sections all
rendering on every page visit regardless of what the user came to see —
the same clutter audit that split Ticker Deep Dive and Market Overview.
Now uses st.segmented_control (lazy-loading via if/elif, not st.tabs which
executes all branches) for the 6 detailed sections below the always-visible
score banner and leg cards.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from utils.config import SIGNALS, POWER_SUPERCYCLE_TICKERS
from utils.fetchers import (
    fetch_signal_series, is_unavailable, fetch_basket, fetch_arxiv_velocity, fetch_cot, fetch_federal_contracts,
)
from utils.analysis import (
    score_signal, score_cot, compute_supercycle_score, score_contract_velocity,
)
from utils.header import render_header, render_sidebar_base, render_page_header, ticker_chips, render_data_unavailable_banner, render_footer
from utils.theme import source_badge, inject_premium_css, inject_skeleton_css, section_label, PLOTLY_CONFIG

st.set_page_config(page_title="Power Supercycle — UA", layout="wide")
render_header("Power Supercycle")
render_sidebar_base()
inject_premium_css()
inject_skeleton_css()

render_page_header(
    "Power Supercycle",
    "Tracking the multi-year bull thesis in energy infrastructure, nuclear, and AI.",
    icon="",
)

END   = datetime.now().strftime("%Y-%m-%d")
START = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
COLS  = {"Nuclear Fuel Chain": "#4A1B6B", "Grid & Power Infra": "#F59E0B",
         "Copper & Materials": "#B34700",  "Gas Pipelines": "#00D566",
         "AI / Hyperscalers": "#7C3AED"}

STATUS_COLOR = {"bullish": "#00D566", "bearish": "#FF4444", "neutral": "#6B7FBF"}

with st.expander("The Thesis — Read This First", expanded=False):
    st.markdown("""
    ### The Power Supercycle — Why It Matters

    This is the most underserved investment thesis in retail finance right now. Here's the causal chain:

    ```
    AI training requires massive compute
         ↓
    Compute requires power (data centers consuming 2.94x more electricity than standard DCs)
         ↓
    Power requires grid infrastructure (PJM queue shortfall of 6,623 MW in Dec 2025)
         ↓
    Grid requires copper, transformers, new dispatchable generation
         ↓
    Nuclear and gas fill the gap (first non-light-water reactor construction permit issued March 2026)
         ↓
    Uranium and SWU enrichment become the bottleneck
    ```

    **What makes this different from regular energy investing:**
    You're tracking the *entire supply chain* simultaneously, using independent data signals
    that each provide weeks to months of lead time, not just one commodity in isolation.

    **The signal stack — every entry below is real non-price alternative data
    (a physical/economic data series), not a relabeled stock or ETF price:**
    | Leg | Signal | Lead Time | Implication |
    |---|---|---|---|
    | Nuclear fuel | Uranium market (URA proxy) | 8-12 weeks | Reactor commitments forming |
    | Grid buildout | Copper futures (COMEX) | 4-8 weeks | Physical material demand tightening |
    | AI demand | Hyperscaler capex | 26+ weeks | Power demand locked in for 2028-2030 |
    | Gas bridge | Henry Hub spot | 3-4 weeks | Data center co-located generation |
    | Macro backdrop | ATA Trucking, Jobless Claims | 4-6 weeks | Economy healthy enough to support capex |

    *(Critical minerals and quantum computing were previously tracked here using equity-ETF
    prices as "signals" — that was circular, since an ETF's price is just an aggregate of
    the same stocks it claims to predict. Those were removed. Real federal contract award
    data and arXiv research-paper velocity track those themes elsewhere on this page and
    on Ticker Deep Dive without that problem.)*
    """)

# ── Always-visible: Load signals + compute Supercycle Score ───────────────────
supercycle_sig_ids = ["uranium_proxy", "copper", "natural_gas", "hyperscaler_capex",
                      "semiconductor_etf", "ata_trucking", "jobless_claims", "ism_pmi", "crude_oil"]

with st.spinner("Loading Power Supercycle signals…"):
    sc_scores = {}
    sc_data   = {}

    for sid in supercycle_sig_ids:
        cfg = SIGNALS.get(sid)
        if not cfg:
            continue
        try:
            s = fetch_signal_series(cfg, START, END)
            sc_scores[sid] = score_signal(s, inverse=cfg.get("inverse", False))
            sc_data[sid]   = s
        except Exception:
            sc_scores[sid] = {"score": 50, "status": "neutral"}

    supercycle = compute_supercycle_score(sc_scores)

    # Blend nuclear-sector contract velocity into the top-level score.
    # fetch_federal_contracts is cached, so the Nuclear Contracts tab below
    # reuses these same results at zero extra network cost.
    _nuclear_companies = {"Centrus Energy": None, "Cameco": None, "Uranium Energy": None}
    _nuclear_vel_scores = []
    for _name in _nuclear_companies:
        _c = fetch_federal_contracts(_name, years=2)
        _nuclear_companies[_name] = (_c, score_contract_velocity(_c))
        _v = _nuclear_companies[_name][1]
        if _v.get("status") != "no_data" and _v.get("award_count", 0) >= 3:
            _nuclear_vel_scores.append(_v["score"])

    if _nuclear_vel_scores:
        _avg_contract_score = sum(_nuclear_vel_scores) / len(_nuclear_vel_scores)
        _blended = supercycle["overall_score"] * 0.85 + _avg_contract_score * 0.15
        supercycle["overall_score"] = round(_blended, 1)
        if _blended >= 62:
            supercycle["case"] = "BULL"
        elif _blended <= 38:
            supercycle["case"] = "BEAR"
        if _blended >= 72:
            supercycle["thesis_status"] = "STRONGLY ALIGNED — Most legs of the Power Supercycle are reading bullish right now"
        elif _blended >= 60:
            supercycle["thesis_status"] = "ALIGNING — Some signals bullish, not yet a strong majority"
        elif _blended >= 45:
            supercycle["thesis_status"] = "MIXED — Signals are split between bullish and bearish readings"
        else:
            supercycle["thesis_status"] = "DIVERGING — Most signals are currently reading against the thesis"

render_data_unavailable_banner(
    sum(1 for s in sc_data.values() if is_unavailable(s)),
    len(sc_data),
)

# ── Always-visible: Supercycle Score Banner ───────────────────────────────────
sc_score  = supercycle["overall_score"]
sc_case   = supercycle["case"]
sc_conv   = supercycle["conviction"]
sc_status = supercycle["thesis_status"]
sc_color  = "#00D566" if sc_case == "BULL" else ("#FF4444" if sc_case == "BEAR" else "#6B7FBF")

st.markdown(f"""
<div class="ua-gradient-border" style="margin-bottom:20px;">
  <div style="display:flex;align-items:center;gap:28px;flex-wrap:wrap;padding:22px 26px;">
    <div style="text-align:center;min-width:110px;">
      <div style="font-size:0.60rem;font-weight:700;color:#8892AA;text-transform:uppercase;
                  letter-spacing:0.14em;margin-bottom:6px;">Supercycle Score</div>
      <div class="ua-kpi-animate" style="font-size:4.2rem;font-weight:900;color:{sc_color};
           line-height:1.0;text-shadow:0 0 32px {sc_color}55,0 0 8px {sc_color}35;
           letter-spacing:-3px;">{sc_score:.0f}</div>
      <div style="font-size:0.65rem;color:#8892AA;margin-top:3px;">/ 100</div>
    </div>
    <div style="width:1px;height:72px;background:rgba(255,255,255,0.08);flex-shrink:0;"></div>
    <div style="flex:1;min-width:210px;">
      <div style="font-size:0.96rem;font-weight:700;color:#E8EEFF;margin-bottom:8px;
                  line-height:1.35;">{sc_status}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;">
        <span style="font-size:0.64rem;font-weight:700;background:rgba(0,213,102,0.10);
                     color:#00D566;border:1px solid rgba(0,213,102,0.22);border-radius:20px;
                     padding:2px 9px;">▲ {supercycle['bull_count']} bullish</span>
        <span style="font-size:0.64rem;font-weight:700;background:rgba(255,68,68,0.10);
                     color:#FF4444;border:1px solid rgba(255,68,68,0.22);border-radius:20px;
                     padding:2px 9px;">▼ {supercycle['bear_count']} bearish</span>
        <span style="font-size:0.64rem;font-weight:700;background:rgba(107,127,191,0.10);
                     color:#6B7FBF;border:1px solid rgba(107,127,191,0.22);border-radius:20px;
                     padding:2px 9px;">● {supercycle['neutral_count']} neutral</span>
      </div>
      <div style="height:5px;background:rgba(255,255,255,0.06);border-radius:4px;overflow:hidden;">
        <div style="height:100%;width:{sc_score:.0f}%;border-radius:4px;
             background:linear-gradient(90deg,{sc_color}80,{sc_color});
             transition:width 0.8s ease;"></div>
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:4px;">
        <span style="font-size:0.60rem;color:#8892AA;">Bear</span>
        <span style="font-size:0.62rem;font-weight:700;color:{sc_color};">
          {sc_case} &nbsp;·&nbsp; {sc_conv} conviction
        </span>
        <span style="font-size:0.60rem;color:#8892AA;">Bull</span>
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

st.caption(
    "This score describes how aligned the 8 underlying signals are RIGHT NOW, weighted toward the "
    "legs judged most central to the thesis. A walk-forward backtest against 6 tickers found no "
    "statistically significant relationship between this score and forward returns — treat it as a "
    "real-time read of signal alignment, not a forecast. See About → Methodology for the full backtest."
)

# ── Always-visible: Five Leg Cards ────────────────────────────────────────────
st.markdown("### Five Legs of the Supercycle")

leg_map = {
    "Nuclear Fuel":   ["uranium_proxy"],
    "Grid & Copper":  ["copper"],
    "Gas Bridge":     ["natural_gas"],
    "AI Demand":      ["hyperscaler_capex", "semiconductor_etf"],
    "Macro Backdrop": ["ata_trucking", "jobless_claims", "ism_pmi", "crude_oil"],
}

leg_cols = st.columns(len(leg_map))
for col, (leg_name, leg_sigs) in zip(leg_cols, leg_map.items()):
    with col:
        leg_scores = [sc_scores.get(s, {}).get("score", 50) for s in leg_sigs]
        leg_avg    = np.mean(leg_scores) if leg_scores else 50
        leg_color  = "#00D566" if leg_avg >= 65 else ("#FF4444" if leg_avg <= 35 else "#6B7FBF")
        leg_symbol = "▲" if leg_avg >= 65 else ("▼" if leg_avg <= 35 else "●")

        _sig_names = ', '.join(SIGNALS[s]['name'][:16] + '…' for s in leg_sigs if s in SIGNALS)
        st.markdown(f"""
        <div class="ua-spotlight ua-kpi-animate"
             style="--ua-spotlight-accent:{leg_color};text-align:center;padding:18px 14px 16px;">
          <div style="font-size:0.62rem;font-weight:700;color:#8892AA;text-transform:uppercase;
                      letter-spacing:0.12em;margin-bottom:8px;">{leg_name}</div>
          <div style="font-size:2.6rem;font-weight:900;color:{leg_color};line-height:1.0;
               text-shadow:0 0 24px {leg_color}45;letter-spacing:-1.5px;margin-bottom:6px;">
            {leg_symbol} {leg_avg:.0f}
          </div>
          <div style="font-size:0.60rem;color:#6B7FBF;line-height:1.5;">{_sig_names}</div>
        </div>
        """, unsafe_allow_html=True)

st.divider()

# ── Segmented control: lazy-load the 6 detailed sections ─────────────────────
section = st.segmented_control(
    "View",
    ["Signal Trends", "Ticker Performance", "Copper COT", "Quantum", "Nuclear Contracts", "Confluence"],
    default="Signal Trends",
    key="psc_section",
)

# ─────────────────────────────────────────────────────────────────────────────
# TAB: Signal Trends
# ─────────────────────────────────────────────────────────────────────────────
if section == "Signal Trends":
    st.html(section_label("Signal Trends by Leg", dot="#7C3AED"))
    st.caption("Each series normalized to 100 at the start of the selected window. One panel per leg.")

    _LEG_PERIOD_OPTS = ["1H", "1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "ALL"]
    _LEG_PERIOD_DAYS = {
        "1H": 1, "1D": 1, "1W": 7, "1M": 30, "3M": 90, "6M": 182,
        "YTD": None, "1Y": 365, "ALL": 0,
    }

    leg_period = st.radio(
        "Signal trend window",
        _LEG_PERIOD_OPTS,
        index=7,
        horizontal=True,
        label_visibility="collapsed",
        key="psc_leg_period",
    )

    with st.expander("Reading these charts"):
        st.markdown(f"""
        Each series is normalized to 100 at the **start of the selected window** ({leg_period}),
        grouped so the lines that belong together are easy to compare.

        - Lines **rising together within a panel** = that leg is strengthening
        - Lines **diverging** = mixed, not a clean signal yet
        - **Most panels trending the same direction** = whole supercycle moving together

        **Short windows (1H/1D/1W):** most signals are published daily/weekly/monthly — a short
        window will show only the native data points that exist, which is honest, not a rendering error.
        """)

    leg_colors = {
        "uranium_proxy": "#4A1B6B", "copper": "#B34700", "natural_gas": "#F59E0B",
        "hyperscaler_capex": "#7C3AED", "semiconductor_etf": "#00C8E0",
        "ata_trucking": "#00D566", "jobless_claims": "#FF4444",
        "ism_pmi": "#5D4037", "crude_oil": "#6B7FBF",
    }

    def _window_and_resample(s: pd.Series, period: str) -> pd.Series:
        s = s.dropna().sort_index()
        if s.empty:
            return s
        days = _LEG_PERIOD_DAYS.get(period)
        if period == "YTD":
            yr_start = pd.Timestamp(datetime.now().year, 1, 1, tz=s.index.tz)
            windowed = s[s.index >= yr_start]
        elif days == 0:
            windowed = s
        else:
            cutoff = pd.Timestamp(datetime.now(), tz=s.index.tz) - pd.Timedelta(days=days)
            windowed = s[s.index >= cutoff]
        if len(windowed) < 2:
            windowed = s.tail(min(6, len(s)))
        resample_rule = "D" if period in ("1H", "1D", "1W") else "W"
        try:
            out = windowed.resample(resample_rule).mean().dropna()
            return out if len(out) >= 2 else windowed
        except Exception:
            return windowed

    _LEG_COLS = 3
    _n_rows = -(-len(leg_map) // _LEG_COLS)

    fig_legs = make_subplots(
        rows=_n_rows, cols=_LEG_COLS,
        subplot_titles=list(leg_map.keys()),
        horizontal_spacing=0.07, vertical_spacing=0.22,
    )

    for i, (leg_name, leg_sig_ids) in enumerate(leg_map.items()):
        row, col = (i // _LEG_COLS) + 1, (i % _LEG_COLS) + 1
        for sid in leg_sig_ids:
            if sid not in sc_data or sc_data[sid].empty:
                continue
            s = _window_and_resample(sc_data[sid], leg_period)
            if s.empty:
                continue
            s_idx = s.index.tz_localize(None) if s.index.tz else s.index
            norm  = s.values / s.values[0] * 100 if s.values[0] != 0 else s.values
            cfg   = SIGNALS.get(sid, {})
            fig_legs.add_trace(
                go.Scatter(
                    x=s_idx, y=norm,
                    name=cfg.get("name", sid)[:22],
                    mode="lines+markers" if len(s) <= 8 else "lines",
                    line=dict(color=leg_colors.get(sid, "#888888"), width=1.8),
                    marker=dict(size=5),
                    hovertemplate=f"{cfg.get('name', sid)[:22]}: %{{y:.1f}}<extra></extra>",
                    legendgroup=leg_name,
                ),
                row=row, col=col,
            )
        fig_legs.add_hline(y=100, line_dash="dot", line_color="#9E9E8E", line_width=1, row=row, col=col)

    fig_legs.update_layout(
        height=260 * _n_rows, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
        font=dict(color="#E8EEFF"), showlegend=True,
        legend=dict(font=dict(size=9, color="#E8EEFF"), bgcolor="rgba(18,21,30,0.90)",
                    orientation="h", y=-0.06, x=0.5, xanchor="center"),
        margin=dict(l=0, r=0, t=40, b=10),
    )
    fig_legs.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9, color="#8892AA"))
    fig_legs.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(size=9, color="#8892AA"))
    fig_legs.update_annotations(font=dict(size=11, color="#7C3AED"))
    st.plotly_chart(fig_legs, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
    st.markdown(
        f"&nbsp; {source_badge('fred')} &nbsp; {source_badge('yfinance')}",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# TAB: Ticker Performance
# ─────────────────────────────────────────────────────────────────────────────
elif section == "Ticker Performance":
    st.html(section_label("Ticker Performance by Supercycle Leg", dot="#00C8E0"))
    st.caption("How each basket of supercycle-relevant tickers has performed over the last 2 years.")

    with st.expander("Why these specific tickers?"):
        st.markdown("""
        | Leg | Key Tickers | Why |
        |---|---|---|
        | Nuclear Fuel Chain | CCJ, LEU, UEC, URA | Uranium miners and enrichers |
        | Grid & Power Infra | PWR, ETN, VRT, VST, CEG | Grid contractors + utilities with nuclear exposure |
        | Copper & Materials | FCX, SCCO, COPX | Copper miners benefit from grid buildout demand |
        | Gas Pipelines | WMB, KMI, OKE | Data center co-located gas = long-term contracted revenue |
        | AI / Hyperscalers | NVDA, MSFT, AMZN | Direct beneficiaries of AI compute buildout |
        """)

    perf_fig = go.Figure()
    with st.spinner("Loading basket performance data…"):
        for basket_name, tickers in POWER_SUPERCYCLE_TICKERS.items():
            basket_series = fetch_basket(tickers, START, END)
            if not basket_series.empty:
                b_idx = basket_series.index.tz_localize(None) if basket_series.index.tz else basket_series.index
                perf_fig.add_trace(go.Scatter(
                    x=b_idx, y=basket_series.values,
                    name=basket_name, mode="lines",
                    line=dict(color=COLS.get(basket_name, "#ccc"), width=2),
                    hovertemplate=f"{basket_name}: %{{y:.1f}}<extra></extra>",
                ))

    perf_fig.add_hline(y=100, line_dash="dash", line_color="#9E9E8E", annotation_text="Baseline (100)")
    perf_fig.update_layout(
        height=360, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(color="#8892AA")),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(color="#8892AA"),
                   title="Equal-Weight Basket (normalized to 100)"),
        legend=dict(font=dict(size=10, color="#E8EEFF"), bgcolor="rgba(18,21,30,0.90)"),
        hovermode="x unified", margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(perf_fig, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
    st.markdown(f"&nbsp; {source_badge('yfinance')}", unsafe_allow_html=True)

    st.caption("Click any ticker to open its full Ticker Deep Dive analysis:")
    for basket_name, basket_tickers in POWER_SUPERCYCLE_TICKERS.items():
        bc1, bc2 = st.columns([1, 5])
        bc1.markdown(
            f'<div style="font-size:0.75rem;color:#6B7FBF;font-family:Inter,sans-serif;'
            f'padding-top:6px;font-weight:600;">{basket_name}</div>',
            unsafe_allow_html=True,
        )
        with bc2:
            ticker_chips(basket_tickers, key_prefix=f"psc_{basket_name.replace(' ','_')}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB: Copper COT
# ─────────────────────────────────────────────────────────────────────────────
elif section == "Copper COT":
    st.html(section_label("Copper COT — Commercial Positioning", dot="#F59E0B"))

    with st.expander("Why copper COT matters for the supercycle"):
        st.markdown("""
        **Commercial hedgers in copper COT** are the copper miners, manufacturers, and utilities that
        actually use or produce copper. When they take **extreme net long positions**, they're locking
        in purchase prices because they expect copper to be scarce — and expensive.

        When commercial positioning hits the 80th percentile or above, it has historically preceded
        significant copper price appreciation. **The AI/data center angle:** copper demand from grid
        buildout overtook EVs as the primary growth driver in June 2026. Commercial hedgers in copper
        see this demand in their order books *months before* it shows up in macro data.
        """)

    with st.spinner("Loading CFTC copper COT data…"):
        copper_cot = fetch_cot("copper")
        cot_scored = score_cot(copper_cot)

    cot1, cot2, cot3 = st.columns(3)
    cot_status = cot_scored.get("status", "neutral")
    cot1.metric("COT Score", f"{cot_scored['score']:.0f}/100",
                delta="Bullish" if cot_status == "bullish" else cot_status.capitalize())
    cot2.metric("Spec Net Position", f"{cot_scored['spec_net']:+,}",
                delta=f"{cot_scored['spec_net_pct']:.0f}th percentile")
    cot3.metric("Commercial Net", f"{cot_scored['comm_net']:+,}",
                delta=f"{cot_scored['comm_net_pct']:.0f}th percentile")

    contrarian = cot_scored.get("contrarian_signal")
    if contrarian:
        st.warning(f"**Contrarian Signal:** {contrarian}")

    if not copper_cot.empty:
        cot_chart = copper_cot.tail(52).copy()
        cot_chart["spec_net"] = cot_chart["spec_long"] - cot_chart["spec_short"]
        cot_chart["comm_net"] = cot_chart["comm_long"] - cot_chart["comm_short"]

        fig_cot = go.Figure()
        fig_cot.add_trace(go.Bar(
            x=cot_chart["date"], y=cot_chart["spec_net"],
            name="Speculator Net", marker_color="#7C3AED", opacity=0.8,
        ))
        fig_cot.add_trace(go.Bar(
            x=cot_chart["date"], y=cot_chart["comm_net"],
            name="Commercial Net", marker_color="#F59E0B", opacity=0.8,
        ))
        fig_cot.add_hline(y=0, line_color="#9E9E8E")
        fig_cot.update_layout(
            title="Copper COT — Speculator vs. Commercial Positioning (52 weeks)",
            height=320, barmode="group", paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
            xaxis=dict(showgrid=False, tickfont=dict(color="#8892AA")),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(color="#8892AA"),
                       title="Net Contracts"),
            legend=dict(font=dict(color="#E8EEFF"), bgcolor="rgba(18,21,30,0.90)"),
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig_cot, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
        st.markdown(f"&nbsp; {source_badge('cftc', 'CFTC Commitment of Traders')}", unsafe_allow_html=True)
    else:
        st.info("CFTC COT data temporarily unavailable.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB: Quantum
# ─────────────────────────────────────────────────────────────────────────────
elif section == "Quantum":
    st.html(section_label("Quantum Computing — arXiv Paper Velocity", dot="#4A1B6B"))

    with st.expander("Why arXiv paper velocity is a leading indicator"):
        st.markdown("""
        Institutional investors who specialize in quantum computing track **arXiv preprints** —
        academic papers posted *before* peer review. This is where breakthroughs appear first.

        - Papers appear on arXiv **2-6 weeks before** the press release
        - When Google published the Willow chip paper, institutional money rotated into quantum stocks
          **within weeks** of the preprint
        - A sustained spike in publication velocity from major labs signals an imminent milestone

        **What "below-threshold error correction" means for investors:** this is the critical technical
        hurdle for fault-tolerant quantum computing. When any major lab achieves this reliably, it
        unlocks commercial viability — and a major re-rating of IONQ, RGTI, QBTS.

        This tracker is unique to Unstructured Alpha. No retail finance platform monitors arXiv velocity.
        """)

    with st.spinner("Fetching arXiv quantum paper data…"):
        arxiv_series = fetch_arxiv_velocity()

    if not arxiv_series.empty:
        arxiv_4w_avg  = float(arxiv_series.tail(4).mean())
        arxiv_52w_avg = float(arxiv_series.mean())
        arxiv_pct_above = (arxiv_4w_avg - arxiv_52w_avg) / arxiv_52w_avg * 100 if arxiv_52w_avg > 0 else 0

        ax1, ax2, ax3 = st.columns(3)
        ax1.metric("Papers this week", f"{arxiv_series.iloc[-1]:.0f}" if len(arxiv_series) > 0 else "—")
        ax2.metric("4-week avg",       f"{arxiv_4w_avg:.1f}")
        ax3.metric("vs. 52-week avg",  f"{arxiv_pct_above:+.1f}%",
                   delta="Elevated" if arxiv_pct_above > 10 else ("Suppressed" if arxiv_pct_above < -10 else "Normal"))

        rolling_4w = arxiv_series.rolling(4).mean()
        fig_arx = go.Figure()
        fig_arx.add_trace(go.Bar(
            x=arxiv_series.index, y=arxiv_series.values,
            name="Papers/week", marker_color="#4A1B6B", opacity=0.75,
        ))
        fig_arx.add_trace(go.Scatter(
            x=rolling_4w.index, y=rolling_4w.values,
            name="4-week rolling avg", mode="lines",
            line=dict(color="#00C8E0", width=2),
        ))
        fig_arx.add_hline(
            y=arxiv_52w_avg, line_dash="dash", line_color="#9E9E8E",
            annotation_text="52w avg", annotation_font_size=9,
        )
        fig_arx.update_layout(
            title="Quantum Computing Papers on arXiv (quant-ph, error correction / fault tolerant)",
            height=320, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
            xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(color="#8892AA")),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(color="#8892AA"),
                       title="Papers per week"),
            legend=dict(font=dict(color="#E8EEFF"), bgcolor="rgba(18,21,30,0.90)"),
            margin=dict(l=0, r=0, t=30, b=0),
        )
        st.plotly_chart(fig_arx, use_container_width=True, config=PLOTLY_CONFIG, theme=None)
        st.caption("Source: arXiv.org API — papers in quant-ph category matching 'qubit', 'error correction', 'fault tolerant'. [Browse arXiv →](https://arxiv.org/list/quant-ph/recent)")
    else:
        st.info("arXiv data temporarily unavailable. The API occasionally rate-limits; try refreshing in a few minutes.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB: Nuclear Contracts
# ─────────────────────────────────────────────────────────────────────────────
elif section == "Nuclear Contracts":
    st.html(section_label("DoE Nuclear Contract Awards", dot="#00D566"))

    with st.expander("Why DoE contract awards are a leading indicator for nuclear stocks"):
        st.markdown("""
        The **Department of Energy** has committed over $3.5 billion to nuclear projects since 2025:
        - $800M to TVA and Holtec for SMR deployment
        - $1.52B loan guarantee for Palisades restart
        - $900M SMR solicitation (March 2025)
        - TerraPower construction permit and funding (Natrium design)

        When DoE awards a conditional commitment, the **capital cycle starts**. Suppliers, fuel
        contractors, and enrichment companies begin signing long-term agreements. This activity
        precedes earnings impacts by 12-36 months.

        Contract award velocity for Centrus Energy (LEU) and Cameco (CCJ) is one of the most
        reliable leading indicators for nuclear equity performance.
        """)

    # Reuse the contract data already fetched for score blending above —
    # fetch_federal_contracts is cached so these are instant reads, not new HTTP calls.
    nuclear_display = {
        "Centrus Energy (LEU)": "Centrus Energy",
        "Cameco":               "Cameco",
        "Uranium Energy":       "Uranium Energy",
    }

    nuke_cols = st.columns(len(nuclear_display))
    for col, (display_name, search_name) in zip(nuke_cols, nuclear_display.items()):
        _contracts, vel = _nuclear_companies[search_name]
        vel_color  = STATUS_COLOR.get(vel.get("status", "neutral"), "#FF9800")
        vel_pct    = vel.get("pct_change", 0.0)
        vel_recent = vel.get("recent_total", 0)
        vel_prior  = vel.get("prior_total", 0)
        col.markdown(f"""
        <div class="ua-spotlight ua-kpi-animate"
             style="--ua-spotlight-accent:{vel_color};margin-bottom:8px;padding:16px 14px;">
            <div style="font-size:0.78rem;font-weight:700;color:#E8EEFF;margin-bottom:6px;">{display_name}</div>
            <div style="font-size:1.8rem;font-weight:800;color:{vel_color};letter-spacing:-0.5px;
                 text-shadow:0 0 20px {vel_color}40;line-height:1.1;">{vel_pct:+.1f}%</div>
            <div style="font-size:0.70rem;color:#8892AA;margin-top:6px;line-height:1.6;">
                Recent 6m: <b style="color:#B8C0D4;">${vel_recent:,.0f}</b><br>
                Prior 6m: <b style="color:#B8C0D4;">${vel_prior:,.0f}</b>
            </div>
        </div>
        """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB: Confluence
# ─────────────────────────────────────────────────────────────────────────────
elif section == "Confluence":
    st.html(section_label("Full Signal Confluence Summary", dot="#00D566"))

    _leg_by_sig = {
        "uranium_proxy":     "Nuclear Fuel",
        "copper":            "Grid & Copper",
        "natural_gas":       "Gas Bridge",
        "hyperscaler_capex": "AI Demand",
        "semiconductor_etf": "AI Demand",
        "ata_trucking":      "Macro",
        "jobless_claims":    "Macro",
        "ism_pmi":           "Macro",
        "crude_oil":         "Macro",
    }

    rows = []
    for sid in supercycle_sig_ids:
        cfg = SIGNALS.get(sid)
        sv  = sc_scores.get(sid, {})
        if not cfg:
            continue
        rows.append({
            "Signal":    cfg["name"],
            "Leg":       _leg_by_sig.get(sid, "Other"),
            "Status":    (" Bullish" if sv.get("status") == "bullish"
                          else (" Bearish" if sv.get("status") == "bearish" else " Neutral")),
            "Score":     round(sv.get("score", 50), 1),
            "Z-Score":   round(sv.get("z_score", 0), 2),
            "Dev %":     round(sv.get("deviation_pct", 0), 2),
            "PCS":       cfg["pcs"],
            "Lead (wk)": cfg["lag_weeks"],
        })

    if rows:
        sum_df = pd.DataFrame(rows).sort_values("Score", ascending=False)
        st.dataframe(
            sum_df, use_container_width=True, hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
            },
        )

render_footer()
