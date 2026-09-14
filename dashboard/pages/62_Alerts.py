"""Alerts — exposure threshold alerts are not built yet, and this page says so.

The only action here is real: a signed-in user can register interest, which is
recorded as an event so demand can be measured before anything is built.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Alerts — Unstructured Alpha", layout="wide")

from utils import report_ui as ui  # noqa: E402
from utils.header import render_header, render_page_header  # noqa: E402

render_header("Alerts")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)
try:
    from utils.instrumentation import record, record_once
    record_once("alerts_viewed")
except Exception:
    def record(*_a, **_k):
        return None

render_page_header("Alerts", "Get told when a saved portfolio's exposure changes.")

st.markdown(
    '<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
    '<div class="uar-title">Exposure alerts are in development</div>'
    '<div class="uar-sub">Nothing on this page sends alerts yet.</div></div></div>'
    '<div class="uar-body"><p class="uar-lead">The plan: choose a saved portfolio and a threshold, such '
    'as &ldquo;tell me if interest-rate sensitivity becomes Clear&rdquo; or &ldquo;tell me if oil '
    'exposure changes by more than its uncertainty&rdquo;, and get an email when it happens.</p>'
    '<div class="uar-sub">Alerts will use the same measurements and evidence labels as the report, so '
    'an alert only fires on a change that is larger than the noise.</div></div></div></div>',
    unsafe_allow_html=True,
)

user = st.session_state.get("user")
if user:
    if st.session_state.get("alerts_interest_recorded"):
        st.success("Thanks. You're on the list, and we'll email you when alerts are ready.")
    elif st.button("Tell me when alerts are ready", type="primary", key="alerts_interest"):
        record("exposure_alerts_interest")
        st.session_state["alerts_interest_recorded"] = True
        st.rerun()
else:
    st.info("Sign in (top right) to be told when alerts are ready.")

ui.render_report_footer()
