"""Compare two portfolios, measured the same way over the same weeks.

The question an adviser brings to a review is rarely "what is this portfolio
exposed to" on its own. It is "what does moving from this to that do": the
client's current allocation against the one being proposed. The report could
answer each half separately; this puts them side by side, with the difference
shown only where it is more than noise, and the trade list underneath.

Each side can be the portfolio already open on the report, a saved portfolio,
a sample, or holdings typed in. A comparison is carried in the URL (?a= and
?b=, the same format as a report link), so it can be bookmarked or sent.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Compare portfolios — Unstructured Alpha", layout="wide")

from utils import exposure as ex  # noqa: E402
from utils import report_charts as charts  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from utils.app_theme import product_page_header  # noqa: E402
from utils.header import render_header  # noqa: E402

render_header("Compare portfolios")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)
st.markdown(charts.CHART_CSS, unsafe_allow_html=True)

try:
    from utils.instrumentation import record, record_once
except Exception:  # measurement must never break the page
    def record(*_a, **_k):
        return None

    def record_once(*_a, **_k):
        return None

record_once("compare_viewed")

product_page_header(
    "Compare portfolios",
    "Two portfolios measured with the same method over the same three years, side by side — "
    "what each is exposed to, what separates them, and what the trade between them is.",
    eyebrow="Current against proposed",
)

user = st.session_state.get("user")
try:
    from utils.billing import effective_is_pro
    is_pro = bool(effective_is_pro(user))
except Exception:
    is_pro = False
max_holdings = ui.PRO_MAX_HOLDINGS if is_pro else ui.FREE_MAX_HOLDINGS


def _saved_portfolios() -> list[dict]:
    if not user:
        return []
    try:
        from utils.portfolio_workspace import list_portfolios
        return list_portfolios(int(user["id"]))
    except Exception:
        return []


def _pick(side: str, default_source: str) -> tuple[list[dict], str]:
    """One side's chooser. Returns (holdings, display name)."""
    sources = []
    if st.session_state.get("uar_holdings"):
        sources.append("The portfolio on the report")
    saved = _saved_portfolios()
    if saved:
        sources.append("A saved portfolio")
    sources += ["A sample", "Type the holdings"]

    index = sources.index(default_source) if default_source in sources else 0
    source = st.radio(f"Portfolio {side}", sources, index=index, key=f"cmp_src_{side}",
                      label_visibility="collapsed")

    if source == "The portfolio on the report":
        name = st.session_state.get("uar_name") or "The portfolio on the report"
        st.caption(ui.holdings_param(st.session_state["uar_holdings"]).replace(",", " · "))
        return list(st.session_state["uar_holdings"]), name

    if source == "A saved portfolio":
        from utils.portfolio_workspace import get_holdings
        choice = st.selectbox("Saved portfolio", saved, format_func=lambda p: p["name"],
                              key=f"cmp_saved_{side}", label_visibility="collapsed")
        rows = get_holdings(int(user["id"]), int(choice["id"])) if choice else []
        return ([{"ticker": r["ticker"], "weight_pct": r["weight_pct"]} for r in rows],
                choice["name"] if choice else "")

    if source == "A sample":
        name = st.selectbox("Sample", list(ex.SAMPLE_PORTFOLIOS), key=f"cmp_sample_{side}",
                            label_visibility="collapsed",
                            index=0 if side == "A" else min(1, len(ex.SAMPLE_PORTFOLIOS) - 1))
        return list(ex.SAMPLE_PORTFOLIOS[name]), name

    text = st.text_area("Holdings", key=f"cmp_text_{side}", height=150,
                        placeholder="VTI 60\nBND 40", label_visibility="collapsed")
    rows, rejected = ui.parse_holdings_text(text)
    if rejected:
        st.caption("Skipped: " + "; ".join(rejected[:4]))
    return rows, f"Portfolio {side}"


# ── a shared link opens straight into its comparison ────────────────────────
_link_a = str(st.query_params.get("a", "") or "")
_link_b = str(st.query_params.get("b", "") or "")
if _link_a and _link_b and st.session_state.get("cmp_loaded") != (_link_a, _link_b):
    st.session_state["cmp_loaded"] = (_link_a, _link_b)
    st.session_state["cmp_pending"] = (
        ui.parse_holdings_param(_link_a), "Portfolio A",
        ui.parse_holdings_param(_link_b), "Portfolio B")
    record("compare_link_opened")

left, right = st.columns(2, gap="large")
with left:
    st.markdown("## Portfolio A")
    st.caption("Usually what is held now.")
    rows_a, name_a = _pick("A", "The portfolio on the report")
with right:
    st.markdown("## Portfolio B")
    st.caption("Usually what is being proposed.")
    rows_b, name_b = _pick("B", "A saved portfolio" if _saved_portfolios() else "A sample")

if st.button("Compare them", type="primary", key="cmp_go"):
    st.session_state["cmp_pending"] = (rows_a, name_a, rows_b, name_b)

pending = st.session_state.get("cmp_pending")
if not pending:
    st.caption("Choose two portfolios and compare them. Each is measured in full, so a new "
               "pair usually takes 20 to 40 seconds; one you have measured before is instant.")
    ui.render_report_footer()
    st.stop()

rows_a, name_a, rows_b, name_b = pending
key_a, _ = ui.prepare_holdings(rows_a, max_holdings)
key_b, _ = ui.prepare_holdings(rows_b, max_holdings)
if not key_a or not key_b:
    st.error("Both sides need at least one holding.")
    ui.render_report_footer()
    st.stop()
if key_a == key_b:
    st.warning("Those are the same portfolio, so there is nothing to compare.")
    ui.render_report_footer()
    st.stop()

# The same abuse guard the report uses, applied per new portfolio: a
# comparison is two full measurements, not a free way round the limit.
for _key in (key_a, key_b):
    if st.session_state.get("cmp_measured", set()) and _key in st.session_state["cmp_measured"]:
        continue
    try:
        from utils.ratelimit import guard
        allowed, _retry = guard("exposure_report")
    except Exception:
        allowed = True
    if not allowed:
        st.error("You've run a lot of measurements in a short time. Please wait a few minutes "
                 "and try again.")
        ui.render_report_footer()
        st.stop()

with st.spinner("Measuring both portfolios over the same three years…"):
    report_a = ui.get_report(key_a, max_holdings)
    report_b = ui.get_report(key_b, max_holdings)
st.session_state.setdefault("cmp_measured", set()).update({key_a, key_b})

# The comparison is addressable, so it can be bookmarked or sent.
_param_a = ui.holdings_param([{"ticker": t, "weight_pct": w} for t, w in key_a])
_param_b = ui.holdings_param([{"ticker": t, "weight_pct": w} for t, w in key_b])
if (st.query_params.get("a"), st.query_params.get("b")) != (_param_a, _param_b):
    st.session_state["cmp_loaded"] = (_param_a, _param_b)
    st.query_params["a"], st.query_params["b"] = _param_a, _param_b

for report, name in ((report_a, name_a), (report_b, name_b)):
    if report.get("status") != "ok":
        st.markdown(f'<div class="uar"><div class="uar-note uar-note-warn"><b>{ui.escape(name)}</b> '
                    f'could not be measured.</div></div>', unsafe_allow_html=True)
        st.markdown(ui.error_html(report), unsafe_allow_html=True)
        ui.render_report_footer()
        st.stop()

record("compare_generated", n_a=len(key_a), n_b=len(key_b))

head_a, head_b = st.columns(2, gap="large")
with head_a:
    st.markdown(ui.portfolio_header_html(name_a, report_a), unsafe_allow_html=True)
    st.markdown(ui.exposure_map_html(report_a), unsafe_allow_html=True)
with head_b:
    st.markdown(ui.portfolio_header_html(name_b, report_b), unsafe_allow_html=True)
    st.markdown(ui.exposure_map_html(report_b), unsafe_allow_html=True)

st.markdown("## What separates them")
st.markdown(ui.comparison_html(report_a, report_b, name_a, name_b), unsafe_allow_html=True)

st.markdown("## The trade between them")
st.markdown(ui.holdings_diff_html(key_a, key_b, name_a, name_b), unsafe_allow_html=True)

with st.expander("Share this comparison"):
    st.caption("Anyone opening this link gets the same two portfolios, measured fresh. "
               "No account needed.")
    import urllib.parse as _up
    st.code(f"{ui.APP_BASE}/compare?a={_up.quote(_param_a, safe=':,.')}"
            f"&b={_up.quote(_param_b, safe=':,.')}", language=None)

ui.render_report_footer()
