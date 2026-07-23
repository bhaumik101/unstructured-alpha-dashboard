"""Free plain-English orientation for a small set of tracked tickers."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from html import escape

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Portfolio Checkup — UA", layout="wide")

from utils.header import (
    render_footer,
    render_guided_steps,
    render_header,
    render_page_header,
    render_sidebar_base,
)
from utils.investor_checkup import (
    FREE_TICKER_LIMIT,
    build_investor_checkup,
    load_recent_score_evidence,
    normalize_checkup_tickers,
)
from utils.theme import inject_premium_css


render_header("Portfolio Checkup")
section = render_sidebar_base(
    page_title="Portfolio Checkup",
    sections=("Overview", "What Changed", "Upcoming Events", "Learn the Read"),
    section_key="investor_checkup_section_rail",
)
inject_premium_css()
try:
    from utils.instrumentation import record_once
    record_once("investor_checkup_viewed")
except Exception:
    pass

render_page_header(
    "Portfolio Checkup",
    "A fast, plain-English orientation for up to five stocks—free, evidence-backed, and honest about what is missing.",
    icon="",
)
render_guided_steps(
    "Understand the backdrop without learning the entire model first",
    [
        ("Enter a few tickers", "Use stocks you own or are seriously researching. Nothing is saved from this box."),
        ("Read the group", "See whether recent recorded evidence is broadly supportive, mixed, or challenging."),
        ("Open one next step", "Use the highest-attention ticker to continue into the full evidence, not a trade instruction."),
    ],
    eyebrow="Everyday investor workflow",
    intro="This checkup equally weights the tickers you enter. It is not a weighted portfolio analysis or a recommendation engine.",
)


def _watchlist_default() -> str:
    user = st.session_state.get("user") or {}
    if not user.get("id"):
        return ""
    try:
        from utils.share_watchlist import get_watchlist_for_user
        return " ".join(get_watchlist_for_user(user["id"])[:FREE_TICKER_LIMIT])
    except Exception:
        return ""


@st.cache_data(ttl=21_600, show_spinner=False, max_entries=32)
def _earnings_for(symbols: tuple[str, ...]) -> dict[str, dict | None]:
    from utils.earnings_awareness import next_earnings
    output: dict[str, dict | None] = {ticker: None for ticker in symbols}
    if not symbols:
        return output
    with ThreadPoolExecutor(max_workers=min(FREE_TICKER_LIMIT, len(symbols))) as pool:
        futures = {pool.submit(next_earnings, ticker, 21): ticker for ticker in symbols}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                output[ticker] = future.result()
            except Exception:
                output[ticker] = None
    return output


if "investor_checkup_input" not in st.session_state:
    st.session_state["investor_checkup_input"] = _watchlist_default()

with st.form("investor_checkup_form"):
    raw_tickers = st.text_input(
        "Stocks to check",
        value=st.session_state["investor_checkup_input"],
        placeholder="AAPL, MSFT, XOM",
        help="Enter up to five ticker symbols separated by spaces or commas.",
    )
    run_checkup = st.form_submit_button("Run free checkup", type="primary")
if run_checkup:
    st.session_state["investor_checkup_input"] = raw_tickers

tickers, invalid = normalize_checkup_tickers(raw_tickers)
raw_count = len([value for value in raw_tickers.replace(",", " ").split() if value])
if invalid:
    st.warning("Skipped invalid ticker text: " + ", ".join(invalid[:5]))
if raw_count > FREE_TICKER_LIMIT:
    st.info(f"The free checkup uses the first {FREE_TICKER_LIMIT} unique tickers. Weighted Pro tools support a larger saved portfolio.")

if not tickers:
    st.info("Enter one to five ticker symbols above to begin. Signed-in users automatically start with their watchlist.")
    st.markdown(
        "**What you will get:** recent recorded score coverage, a simple group read, the largest evidence changes, "
        "upcoming earnings context, and direct links into the supporting research."
    )
    render_footer()
    st.stop()

try:
    evidence = load_recent_score_evidence(tickers)
except Exception:
    evidence = [{"ticker": ticker, "available": False, "score": None} for ticker in tickers]
    st.warning("Recorded score evidence is temporarily unavailable. No substitute values are being shown.")

earnings = _earnings_for(tuple(tickers)) if section == "Upcoming Events" else {}
checkup = build_investor_checkup(evidence, earnings)


if section == "Overview":
    metrics = st.columns(4)
    metrics[0].metric("Stocks checked", checkup["ticker_count"])
    metrics[1].metric("Current evidence", f'{checkup["covered_count"]}/{checkup["ticker_count"]}')
    metrics[2].metric("Group score", f'{checkup["average_score"]:.0f}/100' if checkup["average_score"] is not None else "Unavailable")
    metrics[3].metric("Needs a current record", checkup["missing_count"])

    with st.container(border=True):
        st.markdown(f'### {checkup["headline"]}')
        st.write(checkup["explanation"])
        st.caption(
            f'{checkup["supportive_count"]} supportive · {checkup["mixed_count"]} mixed · '
            f'{checkup["challenging_count"]} challenging · {checkup["missing_count"]} unavailable'
        )

    rows = []
    for row in checkup["evidence"]:
        score = row.get("score")
        status = "Supportive" if score is not None and score >= 65 else "Challenging" if score is not None and score <= 35 else "Mixed" if score is not None else "Unavailable"
        rows.append({
            "Ticker": row["ticker"],
            "Recorded score": round(score, 1) if score is not None else None,
            "Plain-English read": status,
            "Change": row.get("delta_30d"),
            "Evidence date": row.get("snapshot_date") or "No current record",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("Unavailable tickers are excluded from the group score, not filled with neutral or placeholder values.")


elif section == "What Changed":
    st.markdown("#### Where to look first")
    st.caption("Ranked by recorded score movement first, then distance from the neutral range. This is research priority—not trade priority.")
    if not checkup["attention"]:
        st.info("No current recorded scores are available for these tickers yet.")
    for index, row in enumerate(checkup["attention"], start=1):
        delta = row.get("delta_30d")
        movement = f'{delta:+.1f} points across available history' if delta is not None else "No earlier comparison snapshot yet"
        with st.container(border=True):
            left, right = st.columns([4, 1])
            left.markdown(f'**{index}. {escape(row["ticker"])}** · score {float(row["score"]):.0f}/100')
            left.caption(movement)
            right.markdown(
                f'<a href="/ticker-deep-dive?ticker={escape(row["ticker"])}" '
                'style="color:#A78BFA;text-decoration:none;font-weight:700;">Open evidence →</a>',
                unsafe_allow_html=True,
            )
    missing = [row["ticker"] for row in checkup["evidence"] if not row.get("available")]
    if missing:
        st.warning(
            "No current full-score record for: " + ", ".join(missing) + ". "
            "Open each ticker in Deep Dive to calculate a current real-data score."
        )


elif section == "Upcoming Events":
    st.markdown("#### Upcoming earnings context")
    st.caption("Provider-supplied forward earnings dates are provisional until company-confirmed. No date means none is shown.")
    if not checkup["upcoming_earnings"]:
        st.info("No provider-supplied earnings date was found for these tickers in the next 21 days.")
    for event in checkup["upcoming_earnings"]:
        event_date = event.get("date")
        date_text = event_date.strftime("%b %-d") if hasattr(event_date, "strftime") else str(event_date)
        with st.container(border=True):
            st.markdown(f'**{escape(event["ticker"])} earnings** · {date_text}')
            st.caption(
                f'{int(event.get("days_until", 0))} days away · provisional date · '
                "An earnings print can dominate the slower macro backdrop."
            )


elif section == "Learn the Read":
    st.markdown("#### Four terms, in plain English")
    definitions = (
        ("Recorded score", "The last full Confluence Score saved by the platform. It is evidence context, not a price target."),
        ("Supportive", "A score of 65 or higher. More of the tracked macro evidence is in a historically favorable range."),
        ("Mixed", "A score between 35 and 65. The evidence is not strongly aligned in either direction."),
        ("Challenging", "A score of 35 or lower. More of the tracked macro evidence is in a historically unfavorable range."),
    )
    for term, meaning in definitions:
        with st.expander(term):
            st.write(meaning)
    st.markdown("#### What this free checkup does not know")
    st.write(
        "It does not know your position sizes, cost basis, tax situation, goals, or risk capacity. It equally weights the ticker list "
        "and deliberately avoids portfolio-level recommendations."
    )
    st.info(
        "Pro Portfolio Intelligence adds saved weights, concentration, factor overlap, stress testing, decision triage, and catalyst planning."
    )
    if st.button("See Pro portfolio tools", type="primary", key="checkup_upgrade"):
        st.switch_page("pages/29_Upgrade.py")


render_footer()
