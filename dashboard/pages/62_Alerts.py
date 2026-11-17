"""Alerts — Investor Pro exposure alerts: what they are and the ones you have set.

Alerts are set on the exposure report (pages/60_Exposure_Report.py) and checked
by the weekly job (cron/send_exposure_weekly.py, utils/exposure_alerts.py). An
alert emails once when the saved portfolio's reading for a force crosses the
line, not every week it stays past. Until 2026-11 this page said alerts were in
development and recorded interest instead.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Alerts — Unstructured Alpha", layout="wide")

from utils import report_ui as ui  # noqa: E402
from utils.app_theme import product_page_header  # noqa: E402
from utils.header import render_header  # noqa: E402

render_header("Alerts")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)
try:
    from utils.instrumentation import record_once
    record_once("alerts_viewed")
except Exception:
    pass

product_page_header("Alerts", "Get told when a saved portfolio's exposure crosses a line you set.",
                    eyebrow="Stay current")

st.markdown(
    '<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
    '<div class="uar-title">Exposure alerts</div>'
    '<div class="uar-sub">Part of Investor Pro.</div></div></div>'
    '<div class="uar-body"><p class="uar-lead">Choose a force and a line, such as &ldquo;tell me when '
    'interest rates falls below &minus;1.0%&rdquo;, and get an email when your saved portfolio&rsquo;s '
    'reading crosses it. Readings are checked every week, after the new data.</p>'
    '<div class="uar-sub">An alert fires once when the reading crosses, not every week it stays past. '
    'The email gives the reading with its 90% range and evidence label. It describes the past; it is '
    'not a forecast or a recommendation.</div></div></div></div>',
    unsafe_allow_html=True,
)

user = st.session_state.get("user")
try:
    from utils.billing import effective_is_pro
    is_pro = bool(effective_is_pro(user)) if user else False
except Exception:
    is_pro = False

if user and is_pro:
    from utils import exposure_alerts as xa
    alerts = xa.list_alerts(int(user["id"]))
    if alerts:
        st.markdown("**Your alerts**")
        for a in alerts:
            st.markdown(f"- When **{xa.describe(a)}**")
    else:
        st.info("No alerts yet. Set them on the exposure report, under “Exposure alerts”.")
    if st.button("Set alerts on the report", type="primary", key="alerts_to_report"):
        st.switch_page("pages/60_Exposure_Report.py")
elif user:
    st.info("Alerts are part of Investor Pro.")
    if st.button("See Investor Pro", type="primary", key="alerts_to_pro"):
        st.switch_page("pages/29_Upgrade.py")
else:
    st.info("Sign in (top right) to set alerts on a saved portfolio.")

ui.render_report_footer()
