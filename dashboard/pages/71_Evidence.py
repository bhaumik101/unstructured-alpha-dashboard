"""Does it hold up? The out-of-sample track record of the exposure readings.

Every reading the product shows is measured on three years of data. This page
publishes how readings measured that way held up over the following year,
across the S&P 500 and many start dates (utils/track_record.py, run monthly by
cron/track_record.py) -- whatever the numbers show.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Does it hold up? — Unstructured Alpha", layout="wide")

from utils import dashboard_ui as dash  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from utils import track_record as tr  # noqa: E402
from utils import track_record_ui as tui  # noqa: E402
from utils.app_theme import product_page_header  # noqa: E402
from utils.header import render_header  # noqa: E402

render_header("Does it hold up?")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)
st.markdown(dash.DASHBOARD_CSS, unsafe_allow_html=True)
st.markdown(tui.EVIDENCE_CSS, unsafe_allow_html=True)

try:
    from utils.instrumentation import record_once
    record_once("evidence_viewed")
except Exception:
    pass

product_page_header(
    "Does it hold up?",
    "Every reading here is measured on three years of data. This is how readings measured that "
    "way held up over the year that followed — published whatever it shows.",
    eyebrow="Out-of-sample evidence",
)

result = tr.latest()
if not result or not result.get("available"):
    st.markdown(tui.empty_html(), unsafe_allow_html=True)
else:
    st.markdown(tui.coverage_html(result), unsafe_allow_html=True)
    st.markdown(tui.headline_html(result), unsafe_allow_html=True)
    st.markdown("## Did the direction last?")
    st.markdown(tui.direction_html(result), unsafe_allow_html=True)
    st.markdown("## Did the size last?")
    st.markdown(tui.consistency_html(result), unsafe_allow_html=True)
    st.markdown("## By force")
    st.markdown(tui.by_force_html(result), unsafe_allow_html=True)
    st.markdown(tui.method_html(result), unsafe_allow_html=True)

ui.render_report_footer()
