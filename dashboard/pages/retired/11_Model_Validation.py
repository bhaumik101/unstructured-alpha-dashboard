"""
Page 11 — Model Validation Dashboard
Consolidates the validation status of EVERY score this product computes
into one place: every macro/FRED-style signal's real backtest result
(significance rate, average |r|, sample size), plus the per-ticker
differentiator signals and composite scores, each described with exactly
what's been validated, what hasn't, and why -- pulling from
utils/validation_status.py rather than restating anything from memory.

This page exists because it's the actual differentiator this product can
defend: TipRanks' Smart Score, Seeking Alpha's Quant Rating, and similar
composite scores disclose none of their validation status. A platform
that shows "here's exactly how well-supported this number is, including
when it ISN'T" is a different kind of product, not a fancier version of
the same one. That only works if every claim on this page is genuinely
accurate -- nothing here is allowed to be approximated or rounded up.
"""

import pandas as pd
import streamlit as st

from utils.header import render_header, render_sidebar_base, render_page_header
from utils.config import SIGNALS, CATEGORIES
from utils.validation_status import validate_all_macro_signals, get_static_validation_summary
from utils.theme import inject_premium_css, source_badge

st.set_page_config(page_title="Model Validation — UA", layout="wide")
render_header("Model Validation Dashboard")
render_sidebar_base()
inject_premium_css()

render_page_header(
    "Model Validation",
    "Out-of-sample backtest results and signal reliability metrics.",
    icon="🧪",
)

st.markdown("""
<div style="background:rgba(0,200,224,0.07);border-left:3px solid #00C8E0;border-radius:8px;
            padding:14px 18px;font-size:0.85rem;color:#B8C0D4;margin-bottom:20px;
            font-family:Inter,sans-serif;line-height:1.6;">
<b style="color:#E8EEFF;">What this page is for:</b> every score on this site traces back to a
real, checkable validation status — backtested with real significance numbers, validated
per-ticker on demand, or explicitly <b>not</b> validated and documented as to why. Most platforms
that show a composite "smart score" disclose none of this. This page is the single place that does,
including for the cases where the honest answer is "this hasn't held up" — that's the point, not
an embarrassment to hide.
</div>
""", unsafe_allow_html=True)

# ── Methodology Callout Cards ─────────────────────────────────────────────────
with st.expander("ℹ️ How this validation works", expanded=False):
    _v_css = (
        "background:rgba(18,21,30,0.8);border:1px solid rgba(255,255,255,0.07);"
        "border-radius:10px;padding:14px 16px;height:100%;"
    )
    _v_title = (
        "font-weight:700;font-size:0.82rem;letter-spacing:0.04em;"
        "color:#E8EEFF;margin-bottom:6px;font-family:Inter,sans-serif;"
    )
    _v_body = (
        "font-size:0.78rem;color:#8892AA;line-height:1.55;font-family:Inter,sans-serif;"
    )
    _vc1, _vc2, _vc3, _vc4 = st.columns(4)
    with _vc1:
        st.markdown(f"""
<div style="{_v_css}">
  <div style="{_v_title}">🔍 LAG SCAN</div>
  <div style="{_v_body}">
    For each signal, we test 1–26 week lags against a ticker's forward price return using
    Pearson correlation. A signal at lag <em>k</em> is "significant" if its p-value clears
    the Bonferroni-corrected threshold — meaning we divide alpha (0.05) by the number of
    lags tested, not just check p &lt; 0.05 once.
  </div>
</div>""", unsafe_allow_html=True)
    with _vc2:
        st.markdown(f"""
<div style="{_v_css}">
  <div style="{_v_title}">🔬 OUT-OF-SAMPLE SPLIT</div>
  <div style="{_v_body}">
    The best lag found in-sample is re-tested on the held-out ~30% of history it was never
    fit to. A signal only "holds out-of-sample" if it's still significant on that unseen slice.
    Without this step, signals can look good by chance on the in-sample window.
  </div>
</div>""", unsafe_allow_html=True)
    with _vc3:
        st.markdown(f"""
<div style="{_v_css}">
  <div style="{_v_title}">📊 CROSS-TICKER POOLING</div>
  <div style="{_v_body}">
    Each signal is tested against multiple tickers (up to 5 relevant peers). A pooled
    pass counts how many show significance — a signal that looks good against one ticker
    but not others is scored lower than one that holds across all of them.
  </div>
</div>""", unsafe_allow_html=True)
    with _vc4:
        st.markdown(f"""
<div style="{_v_css}">
  <div style="{_v_title}">🏆 RELIABILITY SCORE</div>
  <div style="{_v_body}">
    A 0–100 composite of: corrected in-sample significance, out-of-sample hold-up, sample
    size adequacy, and cross-ticker consistency. 70+ = "Reasonably well-supported".
    Below 50 = weak or unvalidated — shown as-is, not hidden, because that's the point.
  </div>
</div>""", unsafe_allow_html=True)

# ── Composite scores + differentiator signals ──────────────────────────────────
st.markdown('<div class="section-header">COMPOSITE SCORES & DIFFERENTIATOR SIGNALS</div>', unsafe_allow_html=True)

_STATUS_COLOR = {
    "Backtested — NOT validated":                              "#FF4444",
    "Validated methodology available — per-ticker, on demand": "#F59E0B",
    "Deliberately NOT lag-scanned":                            "#6B7FBF",
}
_STATUS_ICON = {
    "Backtested — NOT validated":                              "⚠️",
    "Validated methodology available — per-ticker, on demand": "🔬",
    "Deliberately NOT lag-scanned":                            "ℹ️",
}

for entry in get_static_validation_summary():
    color = _STATUS_COLOR.get(entry["status"], "#6B7FBF")
    icon  = _STATUS_ICON.get(entry["status"], "•")
    st.markdown(f"""
    <div style="border-left:3px solid {color};background:rgba(18,21,30,0.8);
                border:1px solid rgba(255,255,255,0.06);border-left:3px solid {color};
                border-radius:8px;padding:12px 16px;margin-bottom:10px;
                font-family:Inter,sans-serif;">
        <div style="font-weight:700;color:#E8EEFF;font-size:0.92rem;">{entry['category']}</div>
        <div style="color:{color};font-weight:600;font-size:0.78rem;margin:3px 0 6px 0;
                    letter-spacing:0.03em;">{icon} {entry['status']}</div>
        <div style="color:#B8C0D4;font-size:0.82rem;line-height:1.5;">{entry['detail']}</div>
        <div style="color:#6B7FBF;font-size:0.72rem;margin-top:6px;">
            Source: {entry['source']}
        </div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ── Macro signal library — universal lag validation ─────────────────────────
st.markdown('<div class="section-header">MACRO SIGNAL LIBRARY — VALIDATED LEAD-TIME RESULTS</div>', unsafe_allow_html=True)
st.caption(
    f"All {len(SIGNALS)} macro/FRED-style signals, now run through the SAME rigorous methodology "
    "originally built only for insider activity and short interest: an out-of-sample split, "
    "Bonferroni correction across every lag tested, and cross-ticker pooled confirmation -- "
    "rolled up into one transparent Signal Reliability Score per signal (utils/lead_time_research.py). "
    "Every signal held to the same bar, no exceptions."
)

run_validated = st.button(
    "Run Universal Lag Validation (out-of-sample + corrected, every signal)",
    key="run_validated_lag_scan_all_signals",
)

validated_results = {}
if run_validated:
    with st.spinner(
        "Running the validated lag-scan for every signal against up to 5 tickers each — "
        "this is heavier than a simple correlation pass, may take a minute or two…"
    ):
        validated_results = validate_all_macro_signals()
    n_scored = sum(1 for r in validated_results.values() if not r["validation"].get("error"))
    n_reliable = sum(1 for r in validated_results.values() if r["reliability"]["score"] >= 70)
    st.success(
        f"Validation complete: {n_scored} of {len(SIGNALS)} signals had enough data to score. "
        f"{n_reliable} scored 70+ (\"Reasonably well-supported\"). The rest are shown exactly as "
        f"scored below, including the weak ones — that's the point of this page."
    )

rows = []
for sig_id, cfg in SIGNALS.items():
    cat = CATEGORIES.get(cfg["category"], {})
    vr = validated_results.get(sig_id)
    if vr is None:
        reliability_str  = "Not yet run"
        survives_str     = "—"
        holds_oos_str     = "—"
        best_lag_str      = "—"
    elif vr["validation"].get("error"):
        reliability_str  = "Insufficient data"
        survives_str     = "—"
        holds_oos_str     = "—"
        best_lag_str      = "—"
    else:
        rel = vr["reliability"]
        v   = vr["validation"]
        reliability_str = f"{rel['score']}/100 — {rel['label']}"
        survives_str    = "Yes" if v.get("survives_correction") else "No"
        holds_oos_str    = "Yes" if v.get("holds_out_of_sample") else "No"
        best_lag_str     = f"{v.get('best_lag', '—')}w"

    rows.append({
        "Signal": cfg["name"],
        "Category": cat.get("name", cfg["category"]),
        "Reliability Score": reliability_str,
        "Survives Correction": survives_str,
        "Holds Out-of-Sample": holds_oos_str,
        "Best Lag (in-sample)": best_lag_str,
    })

_val_df = pd.DataFrame(rows)
st.dataframe(
    _val_df, use_container_width=True, hide_index=True,
    column_config={
        "Reliability Score": st.column_config.TextColumn(
            "Reliability Score",
            help="0-100, from utils/lead_time_research.py's compute_signal_reliability_score(): "
                 "corrected significance + out-of-sample hold-up + sample size + cross-ticker pooling.",
        ),
        "Survives Correction": st.column_config.TextColumn(
            "Survives Correction", help="Best in-sample lag's p-value beats alpha/n_lags (Bonferroni).",
        ),
        "Holds Out-of-Sample": st.column_config.TextColumn(
            "Holds Out-of-Sample",
            help="That same lag, re-tested on the held-out ~30% of history it was never fit to.",
        ),
    },
)

st.markdown(
    source_badge("fred") + "&nbsp;&nbsp;" +
    source_badge("yfinance", "price history") + "&nbsp;&nbsp;" +
    '<span style="font-size:0.70rem;color:#6B7FBF;font-family:Inter,sans-serif;">'
    "· Lag scan via <code>utils/lead_time_research.py</code></span>",
    unsafe_allow_html=True,
)

with st.expander("How is this different from the simpler backtest on the About page?"):
    st.markdown(
        "The About page's signal library still shows a simpler, same-sample significance test "
        "(`compute_backtested_pcs` — fast, tests against up to 5 tickers, no out-of-sample split or "
        "multiple-comparisons correction). It's a reasonable quick overview but, on its own, will show "
        "more signals looking \"significant\" than actually survive the stricter bar above — that gap "
        "is expected and is exactly why this page exists. Live confluence-score weighting "
        "(`utils/ticker_score.py`) is unaffected by either backtest; it uses its own real-time, "
        "per-ticker correlation regardless of what either validation pass finds."
    )

st.markdown("""
<div style="background:rgba(18,21,30,0.6);border:1px solid rgba(255,255,255,0.05);border-radius:8px;
            padding:12px 16px;font-size:0.75rem;color:#6B7FBF;font-family:Inter,sans-serif;
            line-height:1.5;margin-top:16px;">
<b style="color:#8892AA;">Not financial advice.</b> Validation status describes how a score's
methodology has performed against historical data — it is not a guarantee of future performance,
and a "validated" signal can still be wrong on any individual occasion. Do your own research
before making any investment decision.
</div>
""", unsafe_allow_html=True)
