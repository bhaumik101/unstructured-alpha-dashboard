"""Research record — the forward nowcast, the candidate ledger, and past results.

A transparent research project kept separate from the product. Everything here
is read from the write-once tables; nothing is computed or restated.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Research record — Unstructured Alpha", layout="wide")

from utils import report_ui as ui  # noqa: E402
from utils.header import render_footer, render_header, render_page_header  # noqa: E402

render_header("Research record")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)
try:
    from utils.instrumentation import record_once
    record_once("research_viewed")
except Exception:
    pass

render_page_header(
    "Research record",
    "A public, write-once log of the one predictive test still running, and every candidate tested.",
)

st.markdown(
    '<div class="uar"><div class="uar-note">This is a research project, not part of the exposure report. '
    'Past testing found no reliable way to predict markets from this data. The record below exists so '
    'that claim can be checked month by month, without hindsight.</div></div>',
    unsafe_allow_html=True,
)

# ── forward nowcast ─────────────────────────────────────────────────────────
st.markdown("### Forward nowcast of U.S. manufacturing output")
try:
    from utils.nowcast import NOWCAST_TARGET_NAME, NOWCAST_TARGET_SERIES
    from utils.nowcast_log import get_forward_record, list_nowcasts
    record = get_forward_record(NOWCAST_TARGET_SERIES)
    rows = list_nowcasts(NOWCAST_TARGET_SERIES)
except Exception:
    NOWCAST_TARGET_NAME, record, rows = "Industrial Production: Manufacturing", None, []

st.markdown(
    f"Each month, before the official **{NOWCAST_TARGET_NAME}** figure is published, a model estimate "
    "and a simple &ldquo;no change&rdquo; estimate are written to a table that can't be edited. When the "
    "official number arrives, both are scored. The model has to beat &ldquo;no change&rdquo; to be "
    "worth anything. **Skill is not reported until at least 12 months are scored.**"
)

if not rows:
    st.info("No months are recorded yet.")
else:
    table = "".join(
        f"<tr><td>{r['target_month']}</td><td>{r['predicted']:.3f}</td><td>{r['naive']:.3f}</td>"
        f"<td>{'—' if r.get('actual') is None else f'{r['actual']:.3f}'}</td>"
        f"<td>{str(r.get('created_at') or '')[:10]}</td></tr>"
        for r in rows
    )
    st.markdown(
        '<div class="uar"><div class="uar-card"><div class="uar-scroll"><table class="uar-table"><thead><tr>'
        '<th>Month</th><th>Model estimate</th><th>No-change estimate</th><th>Official figure</th>'
        f'<th>Recorded on</th></tr></thead><tbody>{table}</tbody></table></div></div></div>',
        unsafe_allow_html=True,
    )
if record:
    if record.get("enough_to_judge") and record.get("skill") is not None:
        st.markdown(f"**Skill over {record['n_scored']} scored months:** {record['skill']:+.3f} "
                    f"(model closer in {100 * record['months_model_closer']:.0f}% of months).")
    else:
        st.caption(record.get("note") or "")

# ── candidate ledger ────────────────────────────────────────────────────────
st.markdown("### Candidate data ledger")
st.markdown(
    "New data sources are registered with their reasoning **before** they are tested, and each is tested "
    "once. The bar for significance tightens as more candidates are tried (Bonferroni), so exploring more "
    "can't manufacture a finding. A candidate that passes is not added to the model automatically."
)
try:
    from utils.candidate_ledger import get_ledger
    ledger = get_ledger()
except Exception:
    ledger = None

if not ledger or not (ledger.get("evaluations") or ledger.get("voided")):
    st.info("No candidates have been evaluated yet.")
else:
    st.caption(f"{ledger['n_tested']} of {ledger['n_registered']} registered candidates tested · "
               f"current threshold p < {ledger['corrected_alpha']} · survivors: "
               f"{', '.join(ledger['survivors']) or 'none'}")
    ev_rows = "".join(
        f"<tr><td>{e['candidate']}</td><td>{'—' if e.get('skill') is None else f'{e['skill']:+.3f}'}</td>"
        f"<td>{'—' if e.get('baseline_skill') is None else f'{e['baseline_skill']:+.3f}'}</td>"
        f"<td>{'—' if e.get('dm_p_value') is None else f'{e['dm_p_value']:.3f}'}</td>"
        f"<td>{'Yes' if e.get('survives_correction') else 'No'}</td>"
        f"<td>{str(e.get('evaluated_at') or '')[:10]}</td></tr>"
        for e in ledger.get("evaluations", [])
    )
    if ev_rows:
        st.markdown(
            '<div class="uar"><div class="uar-card"><div class="uar-scroll"><table class="uar-table"><thead><tr>'
            '<th>Candidate</th><th>Skill with it</th><th>Skill without it</th><th>p-value</th>'
            f'<th>Passes threshold</th><th>Tested on</th></tr></thead><tbody>{ev_rows}</tbody></table>'
            '</div></div></div>',
            unsafe_allow_html=True,
        )
    for v in ledger.get("voided", []):
        st.markdown(f'<div class="uar"><div class="uar-note uar-note-warn"><b>Voided: {v["candidate"]}.</b> '
                    f'{v["reason"]}</div></div>', unsafe_allow_html=True)

# ── negative results ────────────────────────────────────────────────────────
st.markdown("### Results so far, including what failed")
st.markdown("""
| Date | Test | Result |
|---|---|---|
| Summer 2026 | Stock direction from the macro signal library | No reliable edge |
| Summer 2026 | Power of the original signal search | Could not detect correlations weaker than about 0.35 |
| Sept 3, 2026 | Nowcasting U.S. industrial production (about ten configurations) | Best result not distinguishable from luck (p ≈ 0.13), and about zero excluding 2020 |
| Sept 3, 2026 | Correction: one backtest used data before its publication date | Result revised down publicly |
| Sept 3, 2026 | Market fragility from signal dispersion | No relationship with later volatility |
| Sept 14, 2026 | First forward nowcast recorded (August 2026) | Awaiting the official figure |
| Sept 14, 2026 | First candidate evaluation | Voided: the candidate never entered the model; re-registered |
""")
st.caption("The older signal track record and validation pages remain available under Research in the menu.")

render_footer()
