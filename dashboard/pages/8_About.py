"""About Unstructured Alpha.

This page deliberately stays at the product level. Detailed methodology lives
on How Signals Work so counts, sources, and scoring claims have one canonical
home instead of drifting across two long explanations.
"""

from __future__ import annotations

import streamlit as st

from utils.header import render_footer, render_header, render_page_header, render_sidebar_base
from utils.product_metrics import (
    ACTIVE_SIGNAL_COUNT,
    ACTIVE_SOURCE_COUNT,
    SUPPORTED_TICKER_COUNT,
    signal_sources_phrase,
)


st.set_page_config(page_title="About — Unstructured Alpha", layout="wide")
render_header("About")
_about_section = render_sidebar_base(
    page_title="About",
    sections=("Overview", "Validation Evidence"),
    section_key="about_section_rail",
)

render_page_header(
    "About Unstructured Alpha",
    "What the product does, what its numbers mean, and where to verify every claim.",
    icon="",
)


if _about_section == "Overview":
    _macro_sources = signal_sources_phrase(limit=20)

    st.markdown(
        f"""
<div style="background:linear-gradient(135deg,rgba(var(--ua-purple-rgb),0.10),rgba(var(--ua-cyan-rgb),0.05));
     border:1px solid rgba(var(--ua-purple-rgb),0.22);border-radius:16px;padding:26px 28px;
     margin-bottom:20px;font-family:Inter,sans-serif;">
  <div style="font-size:0.62rem;color:var(--ua-purple-text);font-weight:750;letter-spacing:0.14em;
       text-transform:uppercase;margin-bottom:10px;">Research context, not a prediction engine</div>
  <div style="font-size:1.18rem;font-weight:720;color:var(--ua-ink);line-height:1.45;
       max-width:920px;margin-bottom:10px;">
    Unstructured Alpha organizes {ACTIVE_SIGNAL_COUNT} registered macro and alternative-data
    series into a transparent research layer for {SUPPORTED_TICKER_COUNT} supported tickers.
  </div>
  <div style="font-size:0.84rem;color:var(--ua-ink-mut);line-height:1.75;max-width:940px;">
    The product helps investors see whether independent evidence is aligned, mixed, stale,
    or unavailable. Scores summarize context; they do not forecast a guaranteed price move
    or replace an investor's own research and risk controls.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    _cards = (
        (
            "Macro signal layer",
            f"{ACTIVE_SIGNAL_COUNT} configured series",
            f"The scored library is derived from the live registry. Its current providers are "
            f"{_macro_sources}.",
            "var(--ua-cyan)",
            "var(--ua-cyan-rgb)",
        ),
        (
            "Per-ticker intelligence",
            "Separate, on-demand evidence",
            "SEC EDGAR filings, FINRA short interest, institutional positioning, options, "
            "fundamentals, and price data power ticker tools. They are not counted as macro signals.",
            "var(--ua-purple)",
            "var(--ua-purple-rgb)",
        ),
        (
            "Evidence layer",
            "Validation stays visible",
            "Validation status, source freshness, unavailable states, and published failures are "
            "shown so a polished score never hides weak or missing evidence.",
            "var(--ua-green)",
            "var(--ua-green-rgb)",
        ),
    )
    _card_html = "".join(
        f"""
<div style="background:rgba(var(--ua-card-rgb),0.72);border:1px solid rgba({rgb},0.18);
     border-top:2px solid {color};border-radius:13px;padding:19px 20px;min-height:178px;">
  <div style="font-size:0.61rem;color:{color};font-weight:750;letter-spacing:0.12em;
       text-transform:uppercase;margin-bottom:10px;">{title}</div>
  <div style="font-size:0.96rem;color:var(--ua-ink);font-weight:700;margin-bottom:8px;">{headline}</div>
  <div style="font-size:0.78rem;color:var(--ua-ink-mut);line-height:1.7;">{body}</div>
</div>
"""
        for title, headline, body, color, rgb in _cards
    )
    st.markdown(
        f"""
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:14px;
     margin-bottom:22px;font-family:Inter,sans-serif;">
  {_card_html}
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div style="background:rgba(var(--ua-label-rgb),0.06);border:1px solid rgba(var(--ua-label-rgb),0.16);
     border-radius:14px;padding:21px 24px;margin:4px 0 24px;font-family:Inter,sans-serif;">
  <div style="font-size:0.62rem;color:var(--ua-ink-label);font-weight:750;letter-spacing:0.12em;
       text-transform:uppercase;margin-bottom:8px;">One canonical methodology</div>
  <div style="font-size:0.91rem;color:var(--ua-ink);font-weight:680;margin-bottom:7px;">
    Audit the model instead of taking the marketing copy on faith.
  </div>
  <div style="font-size:0.79rem;color:var(--ua-ink-mut);line-height:1.7;margin-bottom:14px;">
    How Signals Work contains the scoring explanation, current signal inventory, actual macro
    providers, assumptions, and limitations. Signal Research contains the measured validation,
    data-quality, and track-record views.
  </div>
  <div style="display:flex;gap:9px;flex-wrap:wrap;">
    <a href="/how-signals-work" style="display:inline-block;text-decoration:none;color:var(--ua-ink);
       background:rgba(var(--ua-purple-rgb),0.13);border:1px solid rgba(var(--ua-purple-rgb),0.30);
       border-radius:8px;padding:8px 12px;font-size:var(--ua-text-sm);font-weight:700;">
      Read How Signals Work →
    </a>
    <a href="/signal-research?section=validation" style="display:inline-block;text-decoration:none;
       color:var(--ua-ink-soft);background:rgba(var(--ua-onbg-rgb),0.04);
       border:1px solid rgba(var(--ua-onbg-rgb),0.10);border-radius:8px;padding:8px 12px;
       font-size:var(--ua-text-sm);font-weight:650;">Open validation evidence</a>
    <a href="/signal-research?section=data-quality" style="display:inline-block;text-decoration:none;
       color:var(--ua-ink-soft);background:rgba(var(--ua-onbg-rgb),0.04);
       border:1px solid rgba(var(--ua-onbg-rgb),0.10);border-radius:8px;padding:8px 12px;
       font-size:var(--ua-text-sm);font-weight:650;">Inspect data quality</a>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
<div style="font-family:Inter,sans-serif;margin:8px 0 24px;">
  <div style="font-size:0.62rem;color:var(--ua-ink-label);font-weight:750;letter-spacing:0.13em;
       text-transform:uppercase;margin-bottom:11px;">By the numbers</div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px;">
    <div style="background:rgba(var(--ua-card-rgb),0.62);border:1px solid rgba(var(--ua-onbg-rgb),0.08);
         border-radius:11px;padding:15px 17px;">
      <div style="font-size:1.35rem;color:var(--ua-ink);font-weight:780;">{ACTIVE_SIGNAL_COUNT}</div>
      <div style="font-size:0.68rem;color:var(--ua-ink-mut);margin-top:3px;">registered macro signals</div>
    </div>
    <div style="background:rgba(var(--ua-card-rgb),0.62);border:1px solid rgba(var(--ua-onbg-rgb),0.08);
         border-radius:11px;padding:15px 17px;">
      <div style="font-size:1.35rem;color:var(--ua-ink);font-weight:780;">{SUPPORTED_TICKER_COUNT}</div>
      <div style="font-size:0.68rem;color:var(--ua-ink-mut);margin-top:3px;">supported ticker profiles</div>
    </div>
    <div style="background:rgba(var(--ua-card-rgb),0.62);border:1px solid rgba(var(--ua-onbg-rgb),0.08);
         border-radius:11px;padding:15px 17px;">
      <div style="font-size:1.35rem;color:var(--ua-ink);font-weight:780;">{ACTIVE_SOURCE_COUNT}</div>
      <div style="font-size:0.68rem;color:var(--ua-ink-mut);margin-top:3px;">platform source families</div>
    </div>
  </div>
  <div style="font-size:0.68rem;color:var(--ua-ink-label);line-height:1.6;margin-top:8px;">
    Signal and ticker counts are computed from the live configuration. “Platform source families”
    includes both macro providers and separate per-ticker providers.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    _principles = (
        ("Show provenance", "Name the provider and timestamp wherever a value is presented."),
        ("Fail visibly", "Missing live data becomes an unavailable state, never an invented substitute."),
        ("Separate evidence", "Macro context and ticker-specific evidence remain clearly scoped."),
        ("Publish limitations", "Validation gaps and failed signals stay visible to the investor."),
    )
    st.markdown(
        "<div style='font-size:0.62rem;color:var(--ua-ink-label);font-weight:750;"
        "letter-spacing:0.13em;text-transform:uppercase;margin:8px 0 10px;'>Product principles</div>",
        unsafe_allow_html=True,
    )
    for _title, _body in _principles:
        st.markdown(
            f"""
<div style="display:flex;gap:14px;align-items:baseline;border-bottom:1px solid rgba(var(--ua-onbg-rgb),0.06);
     padding:10px 2px;font-family:Inter,sans-serif;">
  <div style="min-width:145px;font-size:0.78rem;color:var(--ua-ink);font-weight:700;">{_title}</div>
  <div style="font-size:0.77rem;color:var(--ua-ink-mut);line-height:1.6;">{_body}</div>
</div>
""",
            unsafe_allow_html=True,
        )

    st.markdown(
        """
<div style="margin:24px 0 8px;padding:18px 20px;background:rgba(var(--ua-card-rgb),0.58);
     border:1px solid rgba(var(--ua-onbg-rgb),0.08);border-radius:12px;font-family:Inter,sans-serif;">
  <div style="font-size:0.62rem;color:var(--ua-purple-text);font-weight:750;letter-spacing:0.12em;
       text-transform:uppercase;margin-bottom:7px;">Built by Bhaumik Giri</div>
  <div style="font-size:0.79rem;color:var(--ua-ink-mut);line-height:1.7;">
    Unstructured Alpha is an independent product built to make institutional-style evidence
    easier for individual investors to inspect and use. Product questions and feedback:
    <a href="mailto:bpgiri2005@gmail.com" style="color:var(--ua-ink-soft);">bpgiri2005@gmail.com</a>.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


if _about_section == "Validation Evidence":
    from utils.config import SIGNALS
    from utils.validation_status import get_static_validation_summary, validate_all_macro_signals

    st.markdown(
        f"""
<div style="background:rgba(var(--ua-cyan-rgb),0.07);border-left:3px solid var(--ua-cyan);
     border-radius:8px;padding:14px 18px;font-size:0.85rem;color:var(--ua-ink-soft);
     margin-bottom:20px;font-family:Inter,sans-serif;line-height:1.6;">
  <b style="color:var(--ua-ink);">What this is for:</b> each of the
  {ACTIVE_SIGNAL_COUNT} registered macro signals can be traced to a validation status.
  Live results are evidence about historical relationships, not a promise of future performance.
</div>
""",
        unsafe_allow_html=True,
    )

    _val_results = st.session_state.get("_about_validation_results")
    if st.button(
        "Run live validation",
        key="run_pcs_backtest",
        help="Runs the full out-of-sample validation pass. Results are retained for this session.",
    ):
        with st.spinner("Running validation suite…"):
            try:
                _val_results = validate_all_macro_signals()
                st.session_state["_about_validation_results"] = _val_results
            except Exception as _validation_error:
                _val_results = {}
                st.warning(f"Live validation is unavailable right now: {_validation_error}")

    if _val_results:
        import pandas as pd

        _val_rows = []
        for sig_id, res in _val_results.items():
            _val_rows.append(
                {
                    "Signal": SIGNALS.get(sig_id, {}).get("name", sig_id),
                    "Best Lag (wk)": res.get("best_lag_weeks", "—"),
                    "Sig. Tickers": res.get("significant_tickers", 0),
                    "Total Tickers": res.get("total_tickers", 0),
                    "Avg |r|": round(res.get("avg_abs_r", 0), 3),
                    "Sig. Rate %": round(res.get("sig_rate", 0) * 100, 0),
                }
            )
        _val_df = pd.DataFrame(_val_rows).sort_values("Sig. Rate %", ascending=False)
        st.dataframe(
            _val_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Sig. Rate %": st.column_config.ProgressColumn(
                    "Sig. Rate %", min_value=0, max_value=100, format="%.0f%%"
                ),
                "Avg |r|": st.column_config.NumberColumn("Avg |r|", format="%.3f"),
            },
        )
        st.caption(f"Macro signal providers in the current registry: {signal_sources_phrase(limit=20)}.")
    else:
        _static = get_static_validation_summary()
        st.markdown(
            f"<pre style='font-size:var(--ua-text-sm);color:var(--ua-ink-mut);'>{_static}</pre>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Showing the published validation summary. Run live validation to refresh the evidence."
        )


render_footer()
