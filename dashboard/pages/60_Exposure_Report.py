"""Exposure report — the product's front door.

One journey: enter holdings (or open a sample) -> a plain-English report of
which economic forces the portfolio is exposed to, which holdings cause it, and
how sure we can be -> save it. No account is needed for the first report.

All numbers come from utils/exposure.py; all wording from utils/report_ui.py.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Exposure report — Unstructured Alpha", layout="wide")

from utils import exposure as ex  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from utils.header import render_header, render_page_header  # noqa: E402

render_header("Exposure report")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)

try:
    from utils.instrumentation import record, record_once
except Exception:  # measurement must never break the page
    def record(*_a, **_k):
        return None

    def record_once(*_a, **_k):
        return None

record_once("exposure_report_viewed")

user = st.session_state.get("user")
try:
    from utils.billing import effective_is_pro
    is_pro = bool(effective_is_pro(user))
except Exception:
    is_pro = False
max_holdings = ui.PRO_MAX_HOLDINGS if is_pro else ui.FREE_MAX_HOLDINGS

# ── where the holdings come from ────────────────────────────────────────────
sample = str(st.query_params.get("sample", "") or "").lower()
if sample in ui.SAMPLE_KEYS and st.session_state.get("uar_loaded_sample") != sample:
    st.session_state["uar_loaded_sample"] = sample
    st.session_state["uar_holdings"] = ex.SAMPLE_PORTFOLIOS[ui.SAMPLE_KEYS[sample]]
    st.session_state["uar_name"] = f"Sample: {ui.SAMPLE_KEYS[sample]}"
    st.session_state["uar_editing"] = False
    record("exposure_sample_opened", sample=sample, source="link")

if user and "uar_holdings" not in st.session_state:
    try:
        from utils.portfolio_workspace import get_default_holdings
        saved = get_default_holdings(int(user["id"]))
    except Exception:
        saved = []
    if saved:
        st.session_state["uar_holdings"] = [
            {"ticker": r["ticker"], "weight_pct": r["weight_pct"]} for r in saved
        ]
        st.session_state["uar_name"] = "Your saved portfolio"

holdings = st.session_state.get("uar_holdings") or []
editing = st.session_state.get("uar_editing", False) or not holdings

render_page_header(
    "Exposure report",
    "See which economic forces a portfolio is exposed to, which holdings cause it, and how sure we can be.",
)

# ── onboarding / edit ───────────────────────────────────────────────────────
if editing:
    st.markdown(
        '<div class="uar"><p class="uar-lead">Start from a sample portfolio, or enter your own holdings. '
        f'Up to {max_holdings} U.S.-listed stocks or ETFs, each with at least two years of price '
        'history. Nothing is saved unless you choose to save it.</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("**Start from a sample**")
    sample_cols = st.columns(len(ui.SAMPLE_KEYS))
    for col, (key, name) in zip(sample_cols, ui.SAMPLE_KEYS.items()):
        with col:
            if st.button(name, key=f"uar_sample_{key}", width="stretch"):
                st.session_state.update(
                    uar_holdings=ex.SAMPLE_PORTFOLIOS[name], uar_name=f"Sample: {name}",
                    uar_editing=False,
                )
                record("exposure_sample_opened", sample=key, source="button")
                st.rerun()

    st.markdown("**Or enter your own holdings**")
    method = st.radio("How would you like to add holdings?", ("Paste a list", "Upload a CSV"),
                      horizontal=True, key="uar_method", label_visibility="collapsed")
    text, upload = "", None
    if method == "Paste a list":
        text = st.text_area(
            "One holding per line: the ticker, then its weight in percent. Weights are optional; "
            "without them every holding counts equally.",
            value=ui.holdings_to_text(holdings),
            placeholder="VTI 40\nBND 30\nVXUS 20\nGLD 10",
            height=180,
            key="uar_text",
        )
    else:
        upload = st.file_uploader(
            "A CSV with a Ticker or Symbol column, plus an optional Weight or Market Value column. "
            "Most brokerage position exports work.",
            type=["csv"],
            key="uar_csv",
        )

    submit_col, cancel_col, _ = st.columns([1.3, 1, 3])
    with submit_col:
        submitted = st.button("Measure exposure", type="primary", key="uar_submit", width="stretch")
    with cancel_col:
        if holdings and st.button("Cancel", key="uar_cancel", width="stretch"):
            st.session_state["uar_editing"] = False
            st.rerun()

    if submitted:
        if upload is not None:
            rows, rejected = ui.parse_holdings_csv(upload.getvalue())
        else:
            rows, rejected = ui.parse_holdings_text(text)
        if rejected:
            st.warning("These lines weren't understood and were skipped: " + "; ".join(rejected[:8])
                       + (" …" if len(rejected) > 8 else ""))
        if not rows:
            st.error("No holdings found. Add at least one ticker, for example VTI 60 and BND 40.")
        else:
            st.session_state.update(uar_holdings=rows, uar_name="Your portfolio", uar_editing=False)
            record("exposure_holdings_entered", n=len(rows), source="csv" if upload is not None else "paste")
            st.rerun()

    ui.render_report_footer()
    st.stop()

# ── the report ──────────────────────────────────────────────────────────────
key, cleaning_notes = ui.prepare_holdings(holdings, max_holdings)
name = st.session_state.get("uar_name") or "Your portfolio"

allowed = True
if st.session_state.get("uar_last_key") != key:
    try:
        from utils.ratelimit import guard
        allowed, _retry = guard("exposure_report")
    except Exception:
        allowed = True

if not allowed:
    report = {"status": "error", "message": "You've run a lot of reports in a short time. Please wait "
                                            "a few minutes and try again."}
else:
    with st.spinner("Measuring three years of weekly returns against five economic series. "
                    "A new portfolio usually takes 10 to 20 seconds."):
        report = ui.get_report(key, max_holdings)

if st.session_state.get("uar_last_key") != key:
    st.session_state["uar_last_key"] = key
    record("exposure_report_generated", status=report.get("status"), n=len(key),
           sample=st.session_state.get("uar_loaded_sample") or "", signed_in=bool(user))

head_col, edit_col, save_col = st.columns([3.4, 1.5, 1.3])
with head_col:
    st.markdown(ui.portfolio_header_html(name, report), unsafe_allow_html=True)
with edit_col:
    if st.button("Change holdings", key="uar_edit", width="stretch"):
        st.session_state["uar_editing"] = True
        st.rerun()
with save_col:
    save_clicked = st.button("Save portfolio", key="uar_save", width="stretch",
                             disabled=report.get("status") != "ok")

if save_clicked:
    if user:
        try:
            from utils.portfolio_workspace import replace_default_holdings
            replace_default_holdings(int(user["id"]), [{"ticker": t, "weight_pct": w} for t, w in key])
            st.session_state["uar_name"] = "Your saved portfolio"
            record("exposure_portfolio_saved", n=len(key))
            st.success("Saved. This portfolio loads automatically when you sign in.")
        except Exception:
            st.error("Couldn't save right now. Your report is still here; please try again.")
    else:
        record("exposure_save_needs_account")
        st.info("Create a free account or sign in (top right) to save this portfolio. "
                "Your holdings stay on this page while you do.")

if user and report.get("status") == "ok":
    from utils.exposure_email import get_weekly_opt_in, set_weekly_opt_in
    _opt_key = f"uar_weekly_{user['id']}"
    if _opt_key not in st.session_state:
        st.session_state[_opt_key] = get_weekly_opt_in(int(user["id"]))
    _wants_weekly = st.checkbox(
        "Email me a weekly summary of what changed in this portfolio",
        value=st.session_state[_opt_key], key="uar_weekly_optin",
        help="Sundays. Most weeks nothing changes measurably, and the email says so.",
    )
    if _wants_weekly != st.session_state[_opt_key]:
        if set_weekly_opt_in(int(user["id"]), _wants_weekly):
            st.session_state[_opt_key] = _wants_weekly
            record("exposure_weekly_opt_in" if _wants_weekly else "exposure_weekly_opt_out")
            st.caption("Saved." if _wants_weekly else "Turned off.")

if report.get("status") != "ok":
    st.markdown(ui.error_html(report), unsafe_allow_html=True)
    if report.get("retryable") and st.button("Try again", key="uar_retry"):
        st.rerun()
    ui.render_report_footer()
    st.stop()

st.markdown(f'<div class="uar"><p class="uar-lead">{ui.summary_text(report)}</p></div>',
            unsafe_allow_html=True)
st.markdown(ui.exposure_map_html(report), unsafe_allow_html=True)
st.markdown(ui.exposure_table_html(report), unsafe_allow_html=True)

readings = report["portfolio"]["readings"]
detail_keys = ui.ordered_keys(report)
st.markdown("## Which holdings drive each exposure")
chosen = st.radio(
    "Choose an economic force",
    detail_keys,
    format_func=lambda k: readings[k]["label"],
    horizontal=True,
    key="uar_factor",
    label_visibility="collapsed",
)
st.markdown(ui.factor_detail_html(report, chosen), unsafe_allow_html=True)

st.markdown("## What changed")
st.markdown(ui.shifts_html(report), unsafe_allow_html=True)
st.markdown(ui.recent_moves_html(report), unsafe_allow_html=True)

st.markdown("## Economic growth")
st.markdown(ui.growth_html(report), unsafe_allow_html=True)

st.markdown(ui.notes_html(report, cleaning_notes), unsafe_allow_html=True)

with st.expander("How to read this report"):
    st.markdown(ui.HOW_TO_READ)

ui.render_report_footer()
