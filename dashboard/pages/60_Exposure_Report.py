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
from utils.app_theme import product_page_header  # noqa: E402
from utils.header import render_header  # noqa: E402

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

shared = str(st.query_params.get(ui.HOLDINGS_PARAM, "") or "")
if shared and st.session_state.get("uar_loaded_link") != shared:
    linked = ui.parse_holdings_param(shared)
    if linked:
        reopened = str(st.query_params.get("reopened", "") or "") == "1"
        st.session_state["uar_loaded_link"] = shared
        st.session_state["uar_holdings"] = linked
        st.session_state["uar_name"] = "Your portfolio" if reopened else "Shared portfolio"
        st.session_state["uar_editing"] = False
        st.session_state["uar_reopened"] = reopened
        record("exposure_reopened" if reopened else "exposure_link_opened", n=len(linked))

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

product_page_header(
    "Exposure report",
    "See which economic forces a portfolio is exposed to, which holdings cause it, and how sure we can be.",
    eyebrow="Measure a portfolio",
    facts=("Three years of weekly returns", "Five economic series from FRED",
           "The market's own movement removed", "Every reading labelled by evidence"),
)

# ── onboarding / edit ───────────────────────────────────────────────────────
if editing:
    st.markdown(
        '<div class="uar"><p class="uar-lead">Start from a sample portfolio, or enter your own holdings. '
        f'Up to {max_holdings} U.S.-listed stocks, ETFs or mutual funds, each with at least two '
        'years of price history. Nothing is saved unless you choose to save it.</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown("**Start from a sample**")
    sample_cols = st.columns(len(ui.SAMPLE_KEYS))
    for col, (key, name) in zip(sample_cols, ui.SAMPLE_KEYS.items()):
        with col:
            st.markdown(ui.sample_card_html(name), unsafe_allow_html=True)
            if st.button("Measure this one", key=f"uar_sample_{key}", type="primary", width="stretch"):
                st.session_state.update(
                    uar_holdings=ex.SAMPLE_PORTFOLIOS[name], uar_name=f"Sample: {name}",
                    uar_editing=False,
                )
                record("exposure_sample_opened", sample=key, source="button")
                st.rerun()

    st.markdown("**Or look at a single company**")
    st.caption("The same measurement, run on one name. These are common examples, not suggestions.")
    for _row_start in range(0, len(ui.SINGLE_STOCKS), 4):
        for col, (ticker, company) in zip(
            st.columns(4), ui.SINGLE_STOCKS[_row_start:_row_start + 4]
        ):
            if col.button(f"{ticker} · {company}", key=f"uar_one_{ticker}", width="stretch"):
                st.session_state.update(
                    uar_holdings=[{"ticker": ticker, "weight_pct": 100}],
                    uar_name=company, uar_editing=False,
                )
                record("exposure_single_stock_opened", ticker=ticker)
                st.rerun()

    st.markdown("**Or build your own portfolio**")
    method = st.radio(
        "How would you like to add holdings?",
        ("Search by name", "Paste a list", "Upload a CSV"),
        horizontal=True, key="uar_method", label_visibility="collapsed",
    )
    text, upload = "", None

    if method == "Search by name":
        # The primary path. Typing a ticker assumes the visitor knows it; most
        # people know the fund's name, and a workplace-plan statement often
        # prints no symbol at all.
        from utils import symbol_search as sym

        draft = st.session_state.setdefault("uar_draft", [])
        query = st.text_input(
            "Search for a stock, ETF or mutual fund by name or ticker",
            placeholder="Apple · total bond market · Fidelity 500 · VTSAX",
            key="uar_query",
        )
        if query and len(query.strip()) >= 2:
            results, source = sym.search_symbols(query, limit=6)
            record_once("exposure_symbol_searched")
            if source == "offline":
                st.caption("The name lookup is unavailable right now, so these are matches from a "
                           "short built-in list. Anything missing can still be added by ticker "
                           "under “Paste a list”.")
            if not results:
                st.caption("Nothing matched. Try a shorter phrase, or the ticker itself.")
            for row in results:
                label_col, add_col = st.columns([5, 1])
                label_col.markdown(ui.search_result_html(row), unsafe_allow_html=True)
                if add_col.button("Add", key=f"uar_add_{row['ticker']}", width="stretch"):
                    # Weights stay equal until someone edits one. After that the
                    # edits are theirs to keep, so a new holding starts at zero
                    # rather than flattening a set of weights they just typed.
                    touched = st.session_state.get("uar_weights_touched", False)
                    st.session_state["uar_draft"], problem = ui.add_to_draft(
                        draft, row, max_holdings, equal=not touched)
                    if problem:
                        st.warning(problem)
                    else:
                        if not touched:
                            st.session_state["uar_gen"] = st.session_state.get("uar_gen", 0) + 1
                        record("exposure_holding_added", ticker=row["ticker"], kind=row.get("kind", ""))
                        st.rerun()

        draft = st.session_state.get("uar_draft", [])
        if draft:
            # Deleting a widget's key does NOT reset it when the same key is
            # rendered again on the next run: the browser resends the old value
            # and Streamlit restores it. Measured -- adding a second holding to
            # a 100% one left 100 + 50 = 150% on screen, which the engine then
            # rescaled to 67/33 without anyone asking for it. A generation
            # counter in the key makes a fresh widget instead, and it is bumped
            # only when the weights are meant to be reset.
            gen = st.session_state.get("uar_gen", 0)
            st.markdown(ui.draft_header_html(draft), unsafe_allow_html=True)
            for row in draft:
                name_col, weight_col, drop_col = st.columns([4, 1.4, 0.9])
                name_col.markdown(ui.draft_row_html(row), unsafe_allow_html=True)
                before = float(row.get("weight_pct") or 0.0)
                row["weight_pct"] = weight_col.number_input(
                    f"{row['ticker']} weight %", min_value=0.0, max_value=100.0, step=1.0,
                    value=before, format="%.1f", key=f"uar_w_{gen}_{row['ticker']}",
                    label_visibility="collapsed",
                )
                if row["weight_pct"] != before:
                    st.session_state["uar_weights_touched"] = True
                if drop_col.button("Remove", key=f"uar_rm_{row['ticker']}", width="stretch"):
                    equal = not st.session_state.get("uar_weights_touched", False)
                    st.session_state["uar_draft"] = ui.remove_from_draft(
                        draft, row["ticker"], equal=equal)
                    if equal:
                        st.session_state["uar_gen"] = gen + 1
                    st.rerun()
            st.caption(f"Weights total {ui.draft_total(draft):g}%. They are rescaled to 100% before "
                       f"measuring, so they can be dollar amounts or rough shares.")
        else:
            st.caption("Search above and add holdings one at a time. Weights start out equal and "
                       "can be edited.")

    elif method == "Paste a list":
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
        if method == "Search by name":
            rows = [{"ticker": r["ticker"], "weight_pct": r["weight_pct"]}
                    for r in st.session_state.get("uar_draft", [])]
            rejected = []
        elif upload is not None:
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

# The report on screen is fully described by its ?h= parameter, so put it in the
# address bar. A refresh, a bookmark, the back button and the browser's own
# memory of the last portfolio (scripts/inject_boot_splash.py) all follow from
# this one line; without it a reload dropped the visitor back on an empty form.
# uar_loaded_link is set alongside it so the shared-link branch above does not
# then treat our own URL as somebody else's portfolio and rename it.
if report.get("status") == "ok":
    # The "we reopened your last one" line describes a specific portfolio, so it
    # is tied to that portfolio's key rather than to the URL string: the stored
    # link and the normalised key can spell the same holdings in a different
    # order, and comparing the text made the line vanish on a correct reopen.
    if st.session_state.get("uar_reopened"):
        st.session_state.setdefault("uar_reopened_key", key)
        if st.session_state["uar_reopened_key"] != key:
            st.session_state["uar_reopened"] = False
            st.session_state.pop("uar_reopened_key", None)

    _param = ui.holdings_param([{"ticker": t, "weight_pct": w} for t, w in key])
    if str(st.query_params.get(ui.HOLDINGS_PARAM, "") or "") != _param:
        st.session_state["uar_loaded_link"] = _param
        st.query_params[ui.HOLDINGS_PARAM] = _param
        for _stale in ("sample", "reopened"):
            if _stale in st.query_params:
                del st.query_params[_stale]

# Read, not popped. Streamlit reruns the script on its own several times during
# a normal load, and a one-shot pop meant the line was drawn on the first run
# and gone by the time anyone saw the page. It is a statement about the report
# on screen, so it lives as long as that report does.
if st.session_state.get("uar_reopened", False):
    st.markdown(ui.reopened_html(), unsafe_allow_html=True)
    record_once("exposure_reopened_shown")

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

_summary_col, _map_col = st.columns([1.05, 1], gap="large")
with _summary_col:
    st.markdown(f'<div class="uar"><p class="uar-lead">{ui.summary_text(report)}</p></div>',
                unsafe_allow_html=True)
with _map_col:
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
st.markdown(ui.holdings_matrix_html(report), unsafe_allow_html=True)

st.markdown("## What changed")
st.markdown(ui.shifts_html(report), unsafe_allow_html=True)
st.markdown(ui.recent_moves_html(report), unsafe_allow_html=True)

st.markdown("## Economic growth")
st.markdown(ui.growth_html(report), unsafe_allow_html=True)

st.markdown(ui.notes_html(report, cleaning_notes), unsafe_allow_html=True)

with st.expander("Share or print this report"):
    st.caption("Anyone opening this link gets the same report, measured fresh. "
               "No account needed. To save a PDF, print the page.")
    st.code(ui.share_url([{"ticker": t, "weight_pct": w} for t, w in key]), language=None)

with st.expander("How to read this report"):
    st.markdown(ui.HOW_TO_READ)

ui.render_report_footer()
