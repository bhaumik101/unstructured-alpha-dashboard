"""One company's exposure to the economic forces, and its stored history.

The same engine and the same method as a portfolio report: the stock is
measured as a one-holding portfolio at 100%, over three years of weekly
returns, with the stock market's own movement removed first. What this page
adds is the stock library -- every stock measured here is kept, one row per
data week, so a company's history builds up as it is viewed and the main page
can rank everything that has been measured.

Free, like the report. Reached from the report's "look at a single company"
buttons, from the nav, and by URL: /stock?t=XOM.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Stock exposure — Unstructured Alpha", layout="wide")

from utils import report_charts as charts  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from utils import stock_library as lib  # noqa: E402
from utils import stock_ui as sui  # noqa: E402
from utils.app_theme import product_page_header  # noqa: E402
from utils.header import render_header  # noqa: E402

render_header("Stock exposure")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)
st.markdown(charts.CHART_CSS, unsafe_allow_html=True)
st.markdown(sui.STOCK_CSS, unsafe_allow_html=True)

try:
    from utils.instrumentation import record, record_once
except Exception:  # measurement must never break the page
    def record(*_a, **_k):
        return None

    def record_once(*_a, **_k):
        return None

NAMES = dict(ui.SINGLE_STOCKS)
# Handed over by the report's single-company buttons. Session state rather than
# switch_page(query_params=...), which requirements.txt's Streamlit floor lacks.
_handoff = st.session_state.pop("ua_stock_ticker", None)
if _handoff:
    st.query_params["t"] = _handoff

product_page_header(
    "Stock exposure",
    "How one company has moved with interest rates, inflation, the dollar, oil and credit "
    "spreads — measured the same way as a portfolio, with the uncertainty shown.",
    eyebrow="One company",
)


def _open(ticker: str, name: str = "") -> None:
    st.query_params["t"] = ticker
    if name:
        st.session_state[f"ua_stock_name_{ticker}"] = name
    st.rerun()


# ── choose a stock ──────────────────────────────────────────────────────────
query = st.text_input("Look up a company by name or ticker",
                      placeholder="Exxon · Apple · JPM · Caterpillar", key="usl_query")
if query and len(query.strip()) >= 2:
    from utils import symbol_search as sym

    results, source = sym.search_symbols(query, limit=6)
    if source == "offline":
        st.caption("The name lookup is unavailable right now; these are matches from a short "
                   "built-in list. Any ticker can still be typed directly.")
    stocks = [r for r in results if r.get("kind", "Stock") == "Stock"] or results
    if not stocks:
        typed = query.strip().upper()
        if ui._TICKER_RE.match(typed):
            if st.button(f"Measure {typed}", key="usl_typed", type="primary"):
                _open(typed)
        else:
            st.caption("Nothing matched. Try a shorter phrase, or the ticker itself.")
    for row in stocks:
        label_col, go_col = st.columns([5, 1])
        label_col.markdown(ui.search_result_html(row), unsafe_allow_html=True)
        if go_col.button("View", key=f"usl_view_{row['ticker']}", width="stretch"):
            record("stock_page_searched", ticker=row["ticker"])
            _open(row["ticker"], row.get("name", ""))

ticker = str(st.query_params.get("t", "") or "").strip().upper()

if not ticker:
    st.markdown("## Common examples")
    st.caption("Examples, not suggestions.")
    for _row_start in range(0, len(ui.SINGLE_STOCKS), 4):
        for col, (t, company) in zip(st.columns(4), ui.SINGLE_STOCKS[_row_start:_row_start + 4]):
            if col.button(f"{t} · {company}", key=f"usl_pick_{t}", width="stretch"):
                _open(t, company)
    measured = lib.latest(limit=24)
    if measured:
        st.markdown("## Already measured here")
        st.markdown(sui.library_chips_html(measured, limit=24), unsafe_allow_html=True)
    record_once("stock_page_landing")
    ui.render_report_footer()
    st.stop()

if not ui._TICKER_RE.match(ticker):
    st.error(f"“{ticker}” doesn't look like a ticker symbol.")
    ui.render_report_footer()
    st.stop()

name = st.session_state.get(f"ua_stock_name_{ticker}") or NAMES.get(ticker, "")
key = ((ticker, 100.0),)
with st.spinner(f"Measuring {ticker} against five economic forces…"):
    report = ui.get_report(key, ui.FREE_MAX_HOLDINGS)

if report.get("status") != "ok":
    st.markdown(ui.error_html(report), unsafe_allow_html=True)
    ui.render_report_footer()
    st.stop()

# File it. Never blocks the page: record() returns False rather than raising.
lib.record(report, name)
record_once("stock_page_viewed", dedupe_key=f"stock_page_viewed:{ticker}", ticker=ticker)

st.markdown(sui.stock_header_html(ticker, name, report), unsafe_allow_html=True)
_summary_col, _map_col = st.columns([1.05, 1], gap="large")
with _summary_col:
    st.markdown(f'<div class="uar"><p class="uar-lead">{sui.as_stock(ui.summary_text(report))}</p></div>',
                unsafe_allow_html=True)
with _map_col:
    st.markdown(sui.as_stock(ui.exposure_map_html(report), ticker), unsafe_allow_html=True)
st.markdown(sui.as_stock(ui.exposure_table_html(report)), unsafe_allow_html=True)

order = ui.ordered_keys(report)
_rolling = charts.rolling_charts_html(report, order)
if _rolling:
    st.markdown(f"## How {ticker}'s exposures have moved")
    st.markdown(sui.as_stock(_rolling), unsafe_allow_html=True)

st.markdown(f"## {ticker} on record")
_history = lib.history(ticker)
_table = sui.history_html(_history, order)
if _table:
    st.markdown(_table, unsafe_allow_html=True)
else:
    st.caption(f"This is the first week of {ticker} on record here. Each week it is viewed adds "
               "a row, so how its exposures shift can be followed over time.")

st.markdown("## Use it")
_port_col, _cmp_col, _ = st.columns([1.3, 1.3, 2])
if _port_col.button("Build a portfolio around it", key="usl_to_report", type="primary",
                    width="stretch"):
    # Opens the report on this one stock with the holdings panel seeded from
    # it, which is where more holdings are added. A leftover draft from an
    # earlier visit would otherwise be what the panel shows.
    st.session_state.update(uar_holdings=[{"ticker": ticker, "weight_pct": 100}],
                            uar_name=name or ticker, uar_editing=False,
                            uar_draft=[{"ticker": ticker, "name": name, "weight_pct": 100.0}],
                            uar_mode="percent", uar_weights_touched=True)
    record("stock_page_to_report", ticker=ticker)
    st.switch_page("pages/60_Exposure_Report.py")
if _cmp_col.button("Compare with a portfolio", key="usl_to_compare", width="stretch"):
    st.session_state.update(uar_holdings=[{"ticker": ticker, "weight_pct": 100}],
                            uar_name=name or ticker)
    record("stock_page_to_compare", ticker=ticker)
    st.switch_page("pages/66_Compare.py")

ui.render_report_footer()
