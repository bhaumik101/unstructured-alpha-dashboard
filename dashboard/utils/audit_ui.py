# utils/audit_ui.py
# Unstructured Alpha — Audit Trail UI Helper
#
# Renders the "evidence" list added to score_insider_activity(),
# score_short_interest(), and score_13f_positioning() in utils/analysis.py
# -- every score on this page should be traceable back to the actual
# filings behind it, not just a number, which is the entire point of this
# feature. Deliberately a single small shared helper rather than three
# copies of similar rendering code in the page itself.

import pandas as pd
import streamlit as st


def render_evidence_expander(evidence: list, label: str = "Why this score?") -> None:
    """
    Render an expander listing the underlying records behind a score, each
    with a direct source link where one genuinely exists. Renders nothing
    at all if evidence is empty (e.g. "no_data" status) -- an empty
    "Why this score?" expander would be worse than no expander.
    """
    if not evidence:
        return

    n = len(evidence)
    with st.expander(f"{label} ({n} underlying record{'s' if n != 1 else ''})"):
        for ev in evidence:
            raw_date = ev.get("date")
            date_str = raw_date.strftime("%Y-%m-%d") if pd.notna(raw_date) else "—"
            line = f"**{date_str}** — {ev.get('description', '')}"

            if ev.get("source_url"):
                st.markdown(f"{line}  \n[View source filing →]({ev['source_url']})")
            elif ev.get("source_label"):
                # A genuine record with no stable per-record deep link
                # (e.g. FINRA short interest) -- named plainly rather than
                # given a fake clickable link that doesn't point anywhere
                # specific.
                st.markdown(f"{line}  \n*{ev['source_label']}*")
            else:
                st.markdown(line)
            st.divider()
