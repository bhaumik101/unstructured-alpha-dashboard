"""The one-page client summary, ready to print or save as PDF.

An adviser hands a client a sheet of paper, or a PDF attached to an email —
not a web page. The report printed as eight pages of everything; this prints
as one. The layout lives in utils/client_summary.py; this page picks the
portfolio, lets the adviser put a name on it, and gets out of the way when the
browser prints.

Investor Pro and the Advisor pilot. It is the "PDF export" the pricing page
listed as in development.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Client summary — Unstructured Alpha", layout="wide")

from utils import client_summary as cs  # noqa: E402
from utils import report_charts as charts  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from utils.app_theme import product_page_header  # noqa: E402
from utils.header import render_header  # noqa: E402

render_header("Client summary")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)
st.markdown(charts.CHART_CSS, unsafe_allow_html=True)
st.markdown(cs.SUMMARY_CSS, unsafe_allow_html=True)

try:
    from utils.instrumentation import record, record_once
except Exception:  # measurement must never break the page
    def record(*_a, **_k):
        return None

    def record_once(*_a, **_k):
        return None

product_page_header(
    "Client summary",
    "One page: what the portfolio holds, what it is exposed to, and how sure we can be — "
    "ready to print or save as a PDF.",
    eyebrow="For review meetings",
)

user = st.session_state.get("user")
try:
    from utils.billing import effective_is_pro
    is_pro = bool(effective_is_pro(user))
except Exception:
    is_pro = False

if not is_pro:
    st.markdown(
        '<div class="uar"><div class="uar-card"><div class="uar-body">'
        '<div class="uar-title">The client summary is part of Investor Pro</div>'
        '<p class="uar-lead">It turns any report into a single page you can print or attach to an '
        'email: the holdings, every exposure with its range and evidence label, what carries the '
        'strongest ones, how each has been moving, and the method and caveat in plain words. The '
        'full report stays free.</p></div></div></div>', unsafe_allow_html=True)
    plans_col, back_col, _ = st.columns([1.2, 1.2, 3])
    if plans_col.button("See Investor Pro", type="primary", key="cs_to_pro"):
        st.switch_page("pages/29_Upgrade.py")
    if back_col.button("Back to the report", key="cs_back_free"):
        st.switch_page("pages/60_Exposure_Report.py")
    record_once("client_summary_gated")
    ui.render_report_footer()
    st.stop()

# ── which portfolio ─────────────────────────────────────────────────────────
linked = str(st.query_params.get(ui.HOLDINGS_PARAM, "") or "")
holdings = ui.parse_holdings_param(linked) if linked else st.session_state.get("uar_holdings") or []
default_name = str(st.query_params.get("name", "") or "") or st.session_state.get("uar_name") or ""
if not holdings:
    st.info("Open a portfolio on the report first, then choose “Client summary”.")
    if st.button("Go to the report", type="primary", key="cs_to_report"):
        st.switch_page("pages/60_Exposure_Report.py")
    ui.render_report_footer()
    st.stop()

max_holdings = ui.PRO_MAX_HOLDINGS
key, _notes = ui.prepare_holdings(holdings, max_holdings)

# ── what goes on the page (screen only) ─────────────────────────────────────
# A keyed container, because separate st.markdown calls cannot wrap widgets in
# one element; the key becomes a class the print stylesheet hides.
with st.container(key="cs_controls"):
    name_col, for_col, by_col = st.columns(3)
    name = name_col.text_input("Portfolio name", value=default_name or "Portfolio",
                               key="cs_name", max_chars=80)
    prepared_for = for_col.text_input("Prepared for (optional)", key="cs_for", max_chars=80,
                                      placeholder="Client name")
    prepared_by = by_col.text_input("Prepared by (optional)", key="cs_by", max_chars=80,
                                    placeholder="Your name or firm")

with st.spinner("Measuring this portfolio…"):
    report = ui.get_report(key, max_holdings)
if report.get("status") != "ok":
    st.markdown(ui.error_html(report), unsafe_allow_html=True)
    ui.render_report_footer()
    st.stop()

record_once("client_summary_viewed")

# The print button is a plain link the injected runtime turns into
# window.print(): st.markdown strips <script>, and a Streamlit button would run
# Python on a server that cannot open the visitor's print dialog.
st.markdown(
    '<div class="ucs-screen-only" style="display:flex;gap:10px;align-items:center;margin:4px 0 16px">'
    '<a href="#print" data-ua-print="1" class="ucs-print">Print or save as PDF</a>'
    '<span class="ucs-hint">In the print dialog, choose “Save as PDF” to attach it to an email.</span>'
    '</div>', unsafe_allow_html=True)
st.markdown(cs.summary_html(report, name, prepared_for, prepared_by), unsafe_allow_html=True)

if st.button("Back to the full report", key="cs_back"):
    st.switch_page("pages/60_Exposure_Report.py")
