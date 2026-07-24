# pages/11_Model_Validation.py
# Unstructured Alpha — Model Validation Center (Point 9)
#
# The transparency moat: every signal shown as what it actually is — source,
# cadence, relative weight, confidence, validation status, and known limitations
# — plus the honest validation status of the composite models built on top of
# them. Nothing here overclaims. The per-signal labelling logic lives in
# utils/model_validation.py (unit-tested); the optional "run rigorous
# validation" button calls the real out-of-sample pass in
# utils/validation_status.py and upgrades each signal's confidence to its
# MEASURED reliability score.

import streamlit as st

st.set_page_config(page_title="Model Validation — UA", layout="wide")

import pandas as pd

from utils.header import render_header, render_sidebar_base, render_page_header, render_footer
from utils.theme import inject_all_css
from utils.config import SIGNALS
from utils.model_validation import (
    build_validation_table, validation_summary,
    render_summary_html, render_composites_html,
)
from utils.validation_status import get_static_validation_summary

render_header("Model Validation")
render_sidebar_base()
inject_all_css()

render_page_header(
    "Model Validation Center",
    "Every signal, shown as what it actually is — source, weight, confidence, and known limitations. "
    "No cherry-picking, no pretending every signal is equally strong.",
    icon="",
)

# ── Optional: run the rigorous out-of-sample validation pass ──────────────────
# Cheap by default (labels derive from tier + PCS). The button runs the real
# per-signal lag-scan (out-of-sample split + Bonferroni + cross-ticker pooling)
# and upgrades each signal's confidence to its MEASURED reliability score.
_reliabilities = st.session_state.get("_mv_reliabilities")

cta1, cta2 = st.columns([3, 1])
with cta2:
    if st.button("Run out-of-sample validation", use_container_width=True,
                 key="run_validated_lag_scan_all_signals",
                 help="Runs the real lag-scan across each signal's relevant tickers. "
                      "Slow (~a minute) the first time, then cached for 24h."):
        try:
            from utils.validation_status import validate_all_macro_signals
            with st.spinner("Validating every signal out-of-sample…"):
                _reliabilities = validate_all_macro_signals()
                st.session_state["_mv_reliabilities"] = _reliabilities
        except Exception as _e:
            st.warning(f"Validation pass unavailable right now: {_e}")

# ── Build the per-signal transparency records (grounded in config) ────────────
records = build_validation_table(SIGNALS, reliabilities=_reliabilities)
summary = validation_summary(records)

with cta1:
    st.html(render_summary_html(summary))

if _reliabilities:
    st.caption(f"Confidence upgraded to measured out-of-sample reliability for "
               f"{summary['measured']} of {summary['total']} signals. The rest reflect "
               f"tier + predictive-confidence score, capped conservatively.")
else:
    st.caption("Confidence below reflects each signal's tier + predictive-confidence score, "
               "capped conservatively (a Core signal never shows 'High' without a measured "
               "out-of-sample pass). Click **Run out-of-sample validation** for measured scores.")

st.caption(
    "**Point-in-time inputs.** The validation runs on *first-print* data — each "
    "FRED macro signal is fed the value that was actually published at the time "
    "(via ALFRED initial-release vintages), not today's revised numbers. This "
    "removes look-ahead/revision bias: a signal only gets credit for what it could "
    "have told you with the data available then. (Example: US Industrial Production "
    "for Jun-2020 was first printed at 97.5 but reads 91.6 after revisions — a 6% "
    "gap the model never sees here.) Non-revisable sources (prices, short interest) "
    "are used as-is; no point-in-time claim is made where we can't back it."
)

# ── Per-signal table ──────────────────────────────────────────────────────────
_df = pd.DataFrame([{
    "Signal": r["name"],
    "Weight": r["weight_label"],
    "Factor": r["category_name"],
    "Source": r["source"] or "—",
    "Update": (r["frequency"] or "—").title(),
    "Lead (wks)": r["lag_weeks"] if r["lag_weeks"] is not None else "—",
    "Confidence": r["confidence"],
    "Validation status": r["validation_status"],
    "Known limitation": r["known_limitation"],
    "Experimental": "Yes" if r["experimental"] else "—",
} for r in records])

st.dataframe(
    _df, use_container_width=True, hide_index=True,
    column_config={
        "Signal": st.column_config.TextColumn("Signal", width="medium"),
        "Validation status": st.column_config.TextColumn("Validation status", width="large"),
        "Known limitation": st.column_config.TextColumn("Known limitation", width="large"),
    },
)

st.caption(
    "Weight: Core / Supporting / Experimental reflects each signal's tier in the scoring stack. "
    "Confidence is a data-quality read, not a promise of predictive accuracy. Sources: "
    "FRED, SEC EDGAR, FINRA, EIA, CFTC, NY Fed, Yahoo Finance and others — each signal links to its primary source on its card."
)

# ── Composite models — the honest status of the scores built on the signals ───
st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
try:
    st.html(render_composites_html(get_static_validation_summary()))
except Exception:
    pass

render_footer(page="signals")
