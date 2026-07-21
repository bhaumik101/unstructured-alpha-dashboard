# utils/lead_time_ui.py
# Unstructured Alpha — Validated Lead-Time Scan Rendering
#
# Shared rendering for utils.lead_time_research's output (validated
# lag-scan + Signal Reliability Score), used by the Deep Correlation Scan
# section on Ticker Deep Dive for insider activity and short interest --
# kept separate from the page itself so the same rendering isn't
# duplicated for each new alt-data signal this gets extended to later.

import plotly.graph_objects as go
import streamlit as st


def render_validated_lag_scan(result: dict, reliability: dict, pooled: dict = None) -> None:
    """
    Render a validated lag-scan result: the in-sample lag-scan bar chart,
    the out-of-sample check, and the Signal Reliability Score with its
    full component breakdown -- the breakdown is shown EVERY time, not
    just the headline number, since hiding how a meta-score arrived at
    its number would just be building a fancier version of the opaque
    black-box scores this feature exists to be better than.
    """
    if result.get("error"):
        st.info(f"Not enough historical data to run a validated lead-time scan: {result['error']}")
        return

    rel_score = reliability["score"]
    rel_color = "#00D566" if rel_score >= 70 else ("#F59E0B" if rel_score >= 40 else "#FF4444")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Best lag found (in-sample)", f"{result['best_lag']}w")
    m2.metric("In-sample r", f"{result['in_sample_r']:+.3f}", delta=f"p={result['in_sample_p']:.4f}")
    m3.metric(
        "Survives correction?",
        "Yes" if result["survives_correction"] else "No",
        delta=f"needs p<{result['corrected_alpha']:.4f}",
    )
    oos = result.get("out_of_sample")
    m4.metric(
        "Holds out-of-sample?",
        "Yes" if result["holds_out_of_sample"] else "No",
        delta=(f"oos r={oos['r']:+.3f}" if oos else "insufficient oos data"),
    )

    rel_bg = "rgba(0,213,102,0.07)" if rel_score >= 70 else ("rgba(245,158,11,0.07)" if rel_score >= 40 else "rgba(255,68,68,0.07)")
    st.markdown(
        f'<div style="padding:12px 16px;border-left:4px solid {rel_color};background:{rel_bg};'
        f'border-radius:0 8px 8px 0;margin:8px 0;font-family:Inter,sans-serif;">'
        f'<span style="font-size:1.1rem;font-weight:700;color:{rel_color};">Signal Reliability Score: {rel_score}/100</span>'
        f'<br><span style="color:#8892AA;font-size:0.83rem;">{reliability["label"]}</span></div>',
        unsafe_allow_html=True,
    )

    with st.expander("Why this reliability score? (full breakdown, not a black box)"):
        comp = reliability["components"]
        st.markdown(f"""
        - **Survives multiple-comparisons correction:** {comp.get('corrected_significance', 0):.0f} / 35 pts —
          {result['n_comparisons']} lags were tested, so the bar for "real finding" is p < {result['corrected_alpha']:.4f}
          (Bonferroni-corrected), not the uncorrected 0.05.
        - **Holds up out-of-sample:** {comp.get('out_of_sample_validation', 0):.0f} / 35 pts — the best lag was
          chosen using only the earlier portion of history, then tested fresh against more recent data it never
          informed the choice of lag.
        - **Sample size:** {comp.get('sample_size', 0):.1f} / 15 pts — {result['n']} weekly observations
          (full credit at ~104 weeks / 2 years).
        - **Cross-ticker pooled confirmation:** {comp.get('pooled_confirmation', 0):.1f} / 15 pts —
          {f"validated on {pooled['n_tickers']} sector peers, {pooled['significance_rate']*100:.0f}% held up out-of-sample" if pooled and pooled.get('n_tickers', 0) > 1 else "no sector peer scan run"}.
        """)

    lags = list(result["in_sample_scan"].keys())
    corrs = [result["in_sample_scan"][l]["r"] for l in lags]
    bar_colors = ["#00D566" if c > 0 else "#FF4444" for c in corrs]
    if result["best_lag"] in lags:
        bar_colors[lags.index(result["best_lag"])] = "#F59E0B"
    fig = go.Figure(go.Bar(
        x=[f"{l}w" for l in lags], y=corrs, marker_color=bar_colors,
        text=[f"{c:+.3f}" for c in corrs], textposition="outside",
        textfont=dict(size=9, color="#8892AA"),
        hovertemplate="Lag %{x}: in-sample r = %{y:.4f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="rgba(255,255,255,0.15)")
    fig.update_layout(
        height=260, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
        xaxis=dict(showgrid=False, tickfont=dict(color="#8892AA"), title="Lag (weeks) — in-sample only",
                   title_font=dict(color="#6B7FBF", size=11, family="Inter,sans-serif")),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(color="#8892AA"), title="Pearson r",
                   title_font=dict(color="#6B7FBF", size=11, family="Inter,sans-serif")),
        font=dict(family="Inter,sans-serif"),
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True, theme=None)

    if oos:
        st.caption(
            f"Out-of-sample check (held-out data, never used to pick the lag): r={oos['r']:+.3f}, "
            f"p={oos['p']:.4f}, n={oos['n']} weeks, "
            f"{'same' if oos['same_sign_as_in_sample'] else 'OPPOSITE'} direction as the in-sample finding."
        )


def render_lag_decay_chart(decay: dict) -> None:
    """
    Render compute_rolling_best_lag()'s output: a line chart of the
    best-fitting lag across each trailing window, plus the first-half vs
    second-half trend summary. Deliberately framed as exploratory/
    descriptive every time it renders -- this is NOT another validated
    finding the way the lag-scan above is (see that function's docstring
    for exactly why: in-sample-only per window, heavily overlapping
    windows by construction).
    """
    if decay.get("error"):
        st.info(f"Not enough history to track lag decay over time: {decay['error']}")
        return

    trend = decay["lag_trend"]
    trend_color = {"shrinking": "#FF4444", "lengthening": "#7C3AED", "stable": "#00D566"}[trend]
    trend_word = {
        "shrinking": "shrinking — this signal's lead time looks like it's compressing over time",
        "lengthening": "lengthening — this signal's lead time looks like it's stretching out over time",
        "stable": "stable — no clear change in this signal's lead time across the available history",
    }[trend]

    trend_bg = {"shrinking": "rgba(255,68,68,0.07)", "lengthening": "rgba(124,58,237,0.07)", "stable": "rgba(0,213,102,0.07)"}[trend]
    st.markdown(
        f'<div style="padding:10px 16px;border-left:4px solid {trend_color};background:{trend_bg};'
        f'border-radius:0 8px 8px 0;margin:8px 0;font-family:Inter,sans-serif;">'
        f'<span style="font-weight:700;color:{trend_color};">Lead time looks {trend_word}</span><br>'
        f'<span style="color:#8892AA;font-size:0.83rem;">Earlier windows averaged '
        f'{decay["first_half_avg_lag"]:.1f}w · Later windows averaged {decay["second_half_avg_lag"]:.1f}w '
        f'(across {decay["n_windows"]} trailing windows)</span></div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "Exploratory, not a validated finding: each window's best lag is an in-sample pick with no "
        "out-of-sample check of its own, and consecutive windows share most of their data by "
        "construction -- read this as a descriptive trend, not the same kind of evidence as the "
        "validated lag-scan above."
    )

    windows = decay["windows"]
    fig = go.Figure(go.Scatter(
        x=[w["window_end"] for w in windows],
        y=[w["best_lag"] for w in windows],
        mode="lines+markers",
        line=dict(color="#7C3AED", width=2.5),
        marker=dict(size=7, color="#F59E0B"),
        hovertemplate="Window ending %{x|%Y-%m-%d}: best lag = %{y}w<extra></extra>",
    ))
    fig.update_layout(
        height=240, paper_bgcolor="#0B0D12", plot_bgcolor="#0F1118",
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(color="#8892AA"),
                   title="Trailing window ending", title_font=dict(color="#6B7FBF", size=11, family="Inter,sans-serif")),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.04)", tickfont=dict(color="#8892AA"),
                   title="Best-fitting lag (weeks)", title_font=dict(color="#6B7FBF", size=11, family="Inter,sans-serif")),
        font=dict(family="Inter,sans-serif"),
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True, theme=None)
