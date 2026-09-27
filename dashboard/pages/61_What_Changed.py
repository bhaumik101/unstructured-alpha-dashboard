"""What changed — how a portfolio's exposures and recent moves have shifted.

Uses the portfolio from this session's report, or the signed-in user's saved
portfolio. The weekly email version of this view is not built yet and says so.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="What changed — Unstructured Alpha", layout="wide")

from utils import report_charts as charts  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from utils.app_theme import product_page_header  # noqa: E402
from utils.header import render_header  # noqa: E402

render_header("What changed")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)
st.markdown(charts.CHART_CSS, unsafe_allow_html=True)
try:
    from utils.instrumentation import record_once
    record_once("what_changed_viewed")
except Exception:
    pass

product_page_header(
    "What changed",
    "How this portfolio's exposures have shifted, and what moved it in recent weeks.",
    eyebrow="Recent movement",
)

user = st.session_state.get("user")
holdings = st.session_state.get("uar_holdings") or []
name = st.session_state.get("uar_name") or "Your portfolio"
if not holdings and user:
    try:
        from utils.portfolio_workspace import get_default_holdings
        holdings = [{"ticker": r["ticker"], "weight_pct": r["weight_pct"]}
                    for r in get_default_holdings(int(user["id"]))]
        name = "Your saved portfolio"
    except Exception:
        holdings = []

if not holdings:
    st.markdown(
        '<div class="uar"><div class="uar-card"><div class="uar-body">'
        '<div class="uar-title">No portfolio yet</div>'
        '<p class="uar-lead">Create an exposure report first. Once a portfolio is open or saved, this '
        'page shows how its exposures have changed and what moved it recently.</p></div></div></div>',
        unsafe_allow_html=True,
    )
    if st.button("Create an exposure report", type="primary", key="wc_to_report"):
        st.switch_page("pages/60_Exposure_Report.py")
    ui.render_report_footer()
    st.stop()

try:
    from utils.billing import effective_is_pro
    max_holdings = ui.PRO_MAX_HOLDINGS if effective_is_pro(user) else ui.FREE_MAX_HOLDINGS
except Exception:
    max_holdings = ui.FREE_MAX_HOLDINGS

key, _notes = ui.prepare_holdings(holdings, max_holdings)
with st.spinner("Measuring this portfolio…"):
    report = ui.get_report(key, max_holdings)

st.markdown(ui.portfolio_header_html(name, report), unsafe_allow_html=True)
if report.get("status") != "ok":
    st.markdown(ui.error_html(report), unsafe_allow_html=True)
    ui.render_report_footer()
    st.stop()

_order = ui.ordered_keys(report)
_rolling_html = charts.rolling_charts_html(report, _order)
if _rolling_html:
    st.markdown("## How each exposure has moved")
    st.markdown(_rolling_html, unsafe_allow_html=True)
st.markdown("## Changes in exposure")
st.markdown(ui.shifts_html(report), unsafe_allow_html=True)
st.markdown("## Recent weeks")
st.markdown(ui.recent_moves_html(report), unsafe_allow_html=True)
_paths_html = charts.factor_paths_html(report, _order)
if _paths_html:
    st.markdown("## What the forces themselves did")
    st.markdown(_paths_html, unsafe_allow_html=True)

st.markdown(
    '<div class="uar"><div class="uar-note"><b>Get this by email.</b> Sign in, open the portfolio '
    'on the report page and tick &ldquo;Email me a weekly summary&rdquo;. It arrives on Sundays, '
    'and most weeks it says plainly that nothing changed.</div></div>',
    unsafe_allow_html=True,
)
ui.render_report_footer()
