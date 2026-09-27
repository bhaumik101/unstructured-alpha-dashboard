"""Your portfolios: every saved portfolio at a glance.

Saving a portfolio used to be the end of the road. It went into a picker inside
an expander on the report, and nothing brought anyone back to it. This is the
place a returning visitor lands on: each saved portfolio as a card, its
strongest exposures, how the leading one has drifted, and one click to open it,
compare it, or measure it fresh.

Only portfolios already measured in the last six hours show their numbers
straight away. For the Advisor pilot the list has no limit, and measuring every
one on page load would be 10-20 seconds apiece before anything appeared — so
the rest get a button.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Your portfolios — Unstructured Alpha", layout="wide")

from utils import report_charts as charts  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from utils.app_theme import product_page_header  # noqa: E402
from utils.header import render_header  # noqa: E402

render_header("Your portfolios")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)
st.markdown(charts.CHART_CSS, unsafe_allow_html=True)

try:
    from utils.instrumentation import record, record_once
except Exception:  # measurement must never break the page
    def record(*_a, **_k):
        return None

    def record_once(*_a, **_k):
        return None

record_once("portfolios_viewed")

product_page_header(
    "Your portfolios",
    "Every portfolio you have saved, with what it is most exposed to and how that has been "
    "moving. Open one, compare two, or measure them again with this week's data.",
    eyebrow="Your workspace",
)

user = st.session_state.get("user")
if not user:
    st.markdown(
        '<div class="uar"><div class="uar-card"><div class="uar-body">'
        '<div class="uar-title">Sign in to see your saved portfolios</div>'
        '<p class="uar-lead">Portfolios are saved to an account, so they come back on any device. '
        'You can measure one without an account; saving it needs one, and a free account keeps '
        'one portfolio.</p></div></div></div>', unsafe_allow_html=True)
    if st.button("Measure a portfolio", type="primary", key="pf_to_report"):
        st.switch_page("pages/60_Exposure_Report.py")
    ui.render_report_footer()
    st.stop()

try:
    from utils.billing import effective_is_pro, saved_portfolio_limit
    is_pro = bool(effective_is_pro(user))
    limit = saved_portfolio_limit(user)
except Exception:
    is_pro, limit = False, 1
max_holdings = ui.PRO_MAX_HOLDINGS if is_pro else ui.FREE_MAX_HOLDINGS

try:
    from utils.portfolio_workspace import get_holdings, list_portfolios
    saved = list_portfolios(int(user["id"]))
except Exception:
    saved = []
    st.error("Your saved portfolios couldn't be loaded right now. Nothing has been lost; please "
             "try again shortly.")

if not saved:
    st.markdown(
        '<div class="uar"><div class="uar-card"><div class="uar-body">'
        '<div class="uar-title">Nothing saved yet</div>'
        '<p class="uar-lead">Measure a portfolio, then press <b>Save portfolio</b> on the report. '
        'It will appear here, and load automatically next time you sign in.</p>'
        '</div></div></div>', unsafe_allow_html=True)
    if st.button("Measure a portfolio", type="primary", key="pf_empty_to_report"):
        st.switch_page("pages/60_Exposure_Report.py")
    ui.render_report_footer()
    st.stop()

# ── the workspace summary ───────────────────────────────────────────────────
_cap = "unlimited" if limit is None else f"{len(saved)} of {limit}"
summary_col, email_col = st.columns([2, 1])
with summary_col:
    st.markdown(
        f'<div class="uar"><p class="uar-lead"><b>{len(saved)}</b> saved portfolio'
        f'{"" if len(saved) == 1 else "s"} ({_cap} on your plan).</p></div>',
        unsafe_allow_html=True)
with email_col:
    # The weekly summary is the reason to come back without having to
    # remember to; it belongs on the page that lists what it summarises.
    try:
        from utils.exposure_email import get_weekly_opt_in, set_weekly_opt_in
        _key = f"pf_weekly_{user['id']}"
        if _key not in st.session_state:
            st.session_state[_key] = get_weekly_opt_in(int(user["id"]))
        wants = st.toggle("Weekly summary by email", value=st.session_state[_key],
                          key="pf_weekly", help="Sundays. Most weeks nothing changes "
                          "measurably, and the email says so.")
        if wants != st.session_state[_key] and set_weekly_opt_in(int(user["id"]), wants):
            st.session_state[_key] = wants
            record("exposure_weekly_opt_in" if wants else "exposure_weekly_opt_out",
                   where="portfolios")
    except Exception:
        pass


def _key_for(portfolio_id: int) -> tuple:
    rows = get_holdings(int(user["id"]), int(portfolio_id))
    key, _ = ui.prepare_holdings([{"ticker": r["ticker"], "weight_pct": r["weight_pct"]}
                                  for r in rows], max_holdings)
    return key


keys = {p["id"]: _key_for(p["id"]) for p in saved}
reports = {pid: ui.peek_report(k, max_holdings) if k else None for pid, k in keys.items()}
missing = [p for p in saved if keys[p["id"]] and not reports[p["id"]]]

if missing:
    note_col, go_col = st.columns([3, 1])
    note_col.caption(f"{len(missing)} of these {'has' if len(missing) == 1 else 'have'} not been "
                     f"measured in the last six hours. Each takes 10 to 20 seconds.")
    if go_col.button(f"Measure {'it' if len(missing) == 1 else 'all ' + str(len(missing))}",
                     key="pf_measure_all", width="stretch"):
        try:
            from utils.ratelimit import guard
        except Exception:
            guard = None
        for p in missing:
            if guard is not None and not guard("exposure_report")[0]:
                st.warning("That's a lot of measurements in a short time; the rest will be "
                           "available in a few minutes.")
                break
            with st.spinner(f"Measuring {p['name']}…"):
                reports[p["id"]] = ui.get_report(keys[p["id"]], max_holdings)
        record("portfolios_measured", n=len(missing))
        st.rerun()

# ── the cards ───────────────────────────────────────────────────────────────
for row_start in range(0, len(saved), 3):
    columns = st.columns(3, gap="medium")
    for col, p in zip(columns, saved[row_start:row_start + 3]):
        with col:
            key = keys[p["id"]]
            st.markdown(ui.portfolio_card_html(p["name"], len(key), p.get("updated_at", ""),
                                               reports[p["id"]]), unsafe_allow_html=True)
            open_col, cmp_col = st.columns(2)
            if open_col.button("Open", key=f"pf_open_{p['id']}", type="primary", width="stretch"):
                st.session_state.update(
                    uar_holdings=[{"ticker": t, "weight_pct": w} for t, w in key],
                    uar_name=p["name"], uar_editing=False, uar_reopened=False,
                )
                st.session_state.pop("uar_draft", None)
                record("portfolio_opened_from_home")
                st.switch_page("pages/60_Exposure_Report.py")
            if cmp_col.button("Compare", key=f"pf_cmp_{p['id']}", width="stretch"):
                st.session_state.update(
                    uar_holdings=[{"ticker": t, "weight_pct": w} for t, w in key],
                    uar_name=p["name"],
                )
                st.session_state.pop("cmp_pending", None)
                record("portfolio_compared_from_home")
                st.switch_page("pages/66_Compare.py")

st.caption("A card's chips are the exposures that cleared the evidence bar; the line is the "
           "strongest one's rolling year. They describe how each portfolio has moved; they are "
           "not a forecast.")
ui.render_report_footer()
