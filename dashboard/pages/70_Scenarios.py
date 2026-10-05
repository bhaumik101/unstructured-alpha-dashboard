"""Scenario lab: stress-test a portfolio against moves in the market and up to
nineteen economic forces.

"If rates rose a point and stocks fell 15%, what does this portfolio's last
three years suggest?" -- the question an adviser is asked in every review
meeting, answered from the same weekly data as the report, with the range of
uncertainty and the holdings that carry the move. The estimate comes from one
joint regression (utils/scenario.py); this page picks the portfolio and the
levers and draws the result (utils/scenario_ui.py).
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Scenario lab — Unstructured Alpha", layout="wide")

from utils import exposure as ex  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from utils import scenario as sc  # noqa: E402
from utils import scenario_ui as sui  # noqa: E402
from utils.app_theme import product_page_header  # noqa: E402
from utils.header import render_header  # noqa: E402

render_header("Scenario lab")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)
st.markdown(sui.SCENARIO_CSS, unsafe_allow_html=True)

try:
    from utils.instrumentation import record, record_once
except Exception:  # measurement must never break the page
    def record(*_a, **_k):
        return None

    def record_once(*_a, **_k):
        return None

product_page_header(
    "Scenario lab",
    "Move the stock market and any of nineteen economic forces, and see what this portfolio's "
    "last three years suggest — the estimated move, its range, and the holdings that carry it.",
    eyebrow="Stress test",
)

# ── which portfolio ─────────────────────────────────────────────────────────
holdings = st.session_state.get("uar_holdings") or []
name = st.session_state.get("uar_name") or ""
if not holdings:
    pick = st.selectbox("Portfolio", list(ui.SAMPLE_KEYS.values()), key="scn_sample",
                        help="Open your own portfolio on the report first to stress-test it here.")
    holdings, name = ex.SAMPLE_PORTFOLIOS[pick], f"Sample: {pick}"
st.caption(f"Stress-testing **{name or 'your portfolio'}** · "
           f"{len(holdings)} holding{'s' if len(holdings) != 1 else ''}")

key, _notes = ui.prepare_holdings(holdings, ui.PRO_MAX_HOLDINGS)
with st.spinner("Loading this portfolio's weekly history…"):
    report = ui.get_report(key, ui.PRO_MAX_HOLDINGS)
    if report.get("status") == "ok" and not sc.available(report):
        # Measured before scenarios existed: measure again so the weekly data is kept.
        fresh = ex.build_live_report([{"ticker": t, "weight_pct": w} for t, w in key],
                                     max_holdings=ui.PRO_MAX_HOLDINGS)
        if fresh.get("status") == "ok":
            from utils import report_cache

            report_cache.put(key, ui.PRO_MAX_HOLDINGS, fresh)
            report = fresh
if report.get("status") != "ok":
    st.markdown(ui.error_html(report), unsafe_allow_html=True)
    ui.render_report_footer()
    st.stop()
record_once("scenario_lab_viewed")

levers = sc.available_levers(report)
lever_keys = [lv.key for lv in levers]


def _apply(moves: dict) -> None:
    for k in lever_keys:
        st.session_state[f"scn_{k}"] = float(moves.get(k, 0.0))


# ── controls ────────────────────────────────────────────────────────────────
left, right = st.columns([1, 1.35], gap="large")
with left:
    st.markdown("## Start from a scenario")
    st.caption("Hypothetical moves, roughly the size markets have made over a few months. "
               "They are starting points, not forecasts.")
    for row_start in range(0, len(sc.PRESETS), 2):
        cols = st.columns(2)
        for col, p in zip(cols, sc.PRESETS[row_start:row_start + 2]):
            col.button(p.title, key=f"scn_p_{p.key}", help=p.blurb, width="stretch",
                       on_click=_apply, args=({k: v for k, v in p.moves.items() if k in lever_keys},))
    st.button("Reset every lever to zero", key="scn_reset", on_click=_apply, args=({},))

    st.markdown("## Move the forces")
    for group, title in sc.GROUP_TITLES.items():
        group_levers = [lv for lv in levers if lv.group == group]
        if not group_levers:
            continue
        with st.expander(title, expanded=group in ("market", "core")):
            for lv in group_levers:
                lo, hi, step = sc.lever_range(lv)
                st.slider(f"{lv.label} ({lv.unit})", min_value=lo, max_value=hi, step=step,
                          format="%.2f" if step < 1 else "%.0f",
                          key=f"scn_{lv.key}", value=st.session_state.get(f"scn_{lv.key}", 0.0))

moves = {k: float(st.session_state.get(f"scn_{k}", 0.0)) for k in lever_keys}
moves = {k: v for k, v in moves.items() if v}

# ── result ──────────────────────────────────────────────────────────────────
with right:
    if not moves:
        st.markdown('<div class="uar"><div class="uar-card"><div class="uar-body"><p class="uar-lead">'
                    'Pick a scenario or move a lever, and the estimated move for this portfolio '
                    'appears here, with its range and the holdings that carry it.</p></div></div></div>',
                    unsafe_allow_html=True)
    else:
        out = sc.run(report, moves)
        if not out["available"]:
            st.markdown(f'<div class="uar"><div class="uar-note">{out["reason"]}</div></div>',
                        unsafe_allow_html=True)
        else:
            record("scenario_run", n_moves=len(moves))
            st.markdown(sui.headline_html(out, ui.carry_over()), unsafe_allow_html=True)
            st.markdown(sui.contributions_html(out), unsafe_allow_html=True)
            st.markdown(sui.holdings_html(out), unsafe_allow_html=True)
            st.markdown(sui.method_html(out), unsafe_allow_html=True)

ui.render_report_footer()
