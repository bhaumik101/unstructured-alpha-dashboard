"""Catalyst Command Center: verified dates, portfolio exposure, and event plans."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Catalyst Command Center — UA", layout="wide")

from utils.billing import require_pro
from utils.catalyst_center import (
    build_portfolio_catalysts,
    fetch_fred_release_calendar,
    get_catalyst_plan,
    list_catalyst_plans,
    save_catalyst_plan,
)
from utils.header import (
    disclose_unavailable_signals,
    render_footer,
    render_guided_steps,
    render_header,
    render_page_header,
    render_sidebar_base,
)
from utils.theme import inject_premium_css


render_header("Catalyst Command Center")
section = render_sidebar_base(
    page_title="Catalyst Command Center",
    sections=("Portfolio Catalysts", "Macro Calendar", "Event Forecaster", "Review Plans"),
    section_key="catalyst_command_center_section_rail",
)
inject_premium_css()
try:
    from utils.instrumentation import record_once
    record_once("catalyst_center_viewed")
except Exception:
    pass

render_page_header(
    "Catalyst Command Center",
    "Verified event dates, weighted portfolio exposure, and a disciplined pre/post-event workflow.",
    icon="",
)
render_guided_steps(
    "Prepare for the event without pretending to predict it",
    [
        ("See what is dated", "Start with official macro releases and provider-supplied company events."),
        ("Measure exposure", "See which saved holdings and how much portfolio weight may be affected."),
        ("Write the plan", "Record scenarios and evidence to watch, then review the outcome after the event."),
    ],
    eyebrow="Catalyst workflow",
    intro="The calendar never invents a missing date and the signal read never predicts the release outcome.",
)

TODAY = date.today()
END_DAY = TODAY + timedelta(days=45)


def _calendar() -> dict:
    from utils.fetchers import _get_fred_key
    return fetch_fred_release_calendar(TODAY.isoformat(), END_DAY.isoformat(), _get_fred_key())


@st.cache_data(ttl=21_600, show_spinner=False, max_entries=24)
def _earnings_for(symbols: tuple[str, ...]) -> dict[str, dict | None]:
    from utils.earnings_awareness import next_earnings
    output: dict[str, dict | None] = {ticker: None for ticker in symbols}
    if not symbols:
        return output
    with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as pool:
        futures = {pool.submit(next_earnings, ticker, 45): ticker for ticker in symbols}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                output[ticker] = future.result()
            except Exception:
                output[ticker] = None
    return output


def _ticker_signal_map(symbols: tuple[str, ...]) -> dict[str, list[str]]:
    from utils.config import SIGNALS
    mapping = {ticker: [] for ticker in symbols}
    for signal_id, config in SIGNALS.items():
        for ticker in config.get("relevant_tickers") or []:
            symbol = str(ticker).upper()
            if symbol in mapping:
                mapping[symbol].append(signal_id)
    return mapping


def _save_plan_form(event: dict, user_id: int) -> None:
    current = get_catalyst_plan(user_id, event["event_key"]) or {}
    key = event["event_key"].replace(":", "_")
    with st.form(f"catalyst_plan_{key}"):
        base = st.text_area("Base case", value=current.get("base_case") or "", key=f"base_{key}")
        upside = st.text_area("Upside case", value=current.get("upside_case") or "", key=f"up_{key}")
        downside = st.text_area("Downside case", value=current.get("downside_case") or "", key=f"down_{key}")
        watch_for = st.text_area(
            "Evidence to watch",
            value=current.get("watch_for") or "",
            help="Write the specific print, guidance, or signal change that would alter your view.",
            key=f"watch_{key}",
        )
        if st.form_submit_button("Save private event plan", type="primary"):
            save_catalyst_plan(
                user_id=user_id,
                event_key=event["event_key"],
                event_date=event["date"],
                title=event["title"],
                base_case=base,
                upside_case=upside,
                downside_case=downside,
                watch_for=watch_for,
            )
            try:
                from utils.instrumentation import record
                record("catalyst_plan_saved", user_id=user_id, event_type=event.get("event_type"))
            except Exception:
                pass
            st.success("Private event plan saved.")


calendar = _calendar()


if section == "Macro Calendar":
    st.markdown("#### Official macro release calendar")
    st.caption("High-impact releases scheduled during the next 45 days, sourced directly from FRED.")
    if not calendar.get("available"):
        st.warning(
            "The official macro calendar is unavailable right now. No replacement or estimated dates are being shown. "
            "Configure a FRED API key in Setup, then refresh."
        )
    elif not calendar["events"]:
        st.info("FRED returned no mapped high-impact releases in this date window.")
    else:
        rows = [
            {
                "Date": event["date_str"],
                "Release": event["title"],
                "Official FRED name": event["official_name"],
                "Category": event["category"],
                "Signals monitored": ", ".join(event["signals"]),
            }
            for event in calendar["events"]
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(
            "Source: Federal Reserve Bank of St. Louis FRED API. A publisher's scheduled release date does not "
            "guarantee that the new observation will already be available on FRED that day."
        )


elif section == "Event Forecaster":
    st.markdown("#### Pre-event signal regime")
    st.caption(
        "This read describes the live macro regime around verified upcoming releases. It does not forecast the print."
    )
    if not calendar.get("available") or not calendar.get("events"):
        st.warning("A verified upcoming release is required. The product will not substitute a generic or hardcoded date.")
    else:
        from utils.signals_cache import get_all_signal_scores
        with st.spinner("Loading current signal evidence…"):
            all_scores = get_all_signal_scores()
        disclose_unavailable_signals(all_scores)
        seen_titles: set[str] = set()
        for event in calendar["events"]:
            if event["title"] in seen_titles:
                continue
            seen_titles.add(event["title"])
            available = [
                all_scores[sid] for sid in event["signals"]
                if sid in all_scores and not all_scores[sid].get("error") and not all_scores[sid].get("synthetic")
            ]
            if not available:
                continue
            bullish = sum(item.get("status") == "bullish" for item in available)
            bearish = sum(item.get("status") == "bearish" for item in available)
            regime = "Supportive" if bullish > bearish else "Challenging" if bearish > bullish else "Mixed"
            with st.expander(f'{event["date"].strftime("%b %-d")} · {event["title"]} · {regime}', expanded=True):
                st.write(f'{len(available)} verified signals available · {bullish} supportive · {bearish} challenging')
                columns = st.columns(min(4, len(available)))
                for index, signal in enumerate(available[:4]):
                    columns[index].metric(signal.get("name", "Signal"), f'{float(signal.get("score", 50)):.0f}/100')
                excluded = len(event["signals"]) - len(available)
                if excluded:
                    st.caption(f"{excluded} unavailable signal(s) excluded rather than imputed.")


elif section == "Portfolio Catalysts":
    require_pro(page_name="Catalyst Command Center")
    user = st.session_state.get("user")
    if not user:
        st.stop()
    from utils.portfolio_workspace import get_default_holdings
    try:
        holdings = get_default_holdings(user["id"])
        plans = list_catalyst_plans(user["id"])
    except Exception:
        holdings = []
        plans = []
        st.warning("Your private catalyst workspace is temporarily unavailable. The public calendar remains accessible.")
    if not holdings:
        st.info("Save your weighted holdings in Portfolio Intelligence to activate personalized catalyst ranking.")
    else:
        symbols = tuple(row["ticker"] for row in holdings)
        with st.spinner("Ranking verified events against your saved portfolio…"):
            earnings = _earnings_for(symbols)
            catalysts = build_portfolio_catalysts(
                holdings,
                calendar.get("events") or [],
                earnings,
                _ticker_signal_map(symbols),
                today=TODAY,
            )
        metrics = st.columns(4)
        metrics[0].metric("Next 21 days", sum(event["days_until"] <= 21 for event in catalysts))
        metrics[1].metric("Company events", sum(event["event_type"] == "earnings" for event in catalysts))
        metrics[2].metric("Macro releases", sum(event["event_type"] == "macro" for event in catalysts))
        metrics[3].metric("Saved plans", len(plans))
        if not calendar.get("available"):
            st.warning("Official macro dates are unavailable, so this ranking currently contains company events only.")
        if not catalysts:
            st.info("No dated catalyst was found for these holdings in the next 45 days.")
        for event in catalysts[:12]:
            estimate = " · provisional date" if event.get("is_estimate") else ""
            tickers = ", ".join(event["affected_tickers"][:8])
            with st.expander(
                f'{event["date"].strftime("%b %-d")} · {event["title"]} · {event["affected_weight"]:.1f}% affected weight',
                expanded=event["days_until"] <= 7,
            ):
                st.write(f'{event["days_until"]} days away{estimate}')
                st.write(f"Affected holdings: {tickers}")
                st.caption(f'Source: {event["source"]}')
                _save_plan_form(event, user["id"])
        st.caption(
            "Earnings dates come from the market-data provider and remain labeled provisional until company-confirmed. "
            "Macro dates come from FRED; missing dates are never synthesized."
        )


elif section == "Review Plans":
    require_pro(page_name="Catalyst Command Center")
    user = st.session_state.get("user")
    if not user:
        st.stop()
    try:
        plans = list_catalyst_plans(user["id"])
    except Exception:
        plans = []
        st.warning("Your private review book is temporarily unavailable. Try again shortly.")
    st.markdown("#### Private pre/post-event review book")
    st.caption("Compare what you expected with what happened. Plans are visible only to your account.")
    if not plans:
        st.info("No plans yet. Open Portfolio Catalysts and save a plan before an upcoming event.")
    for plan in plans:
        with st.expander(f'{plan["event_date"]} · {plan["title"]} · {plan["status"]}', expanded=False):
            st.markdown("**Base case**")
            st.write(plan.get("base_case") or "Not recorded")
            st.markdown("**Upside case**")
            st.write(plan.get("upside_case") or "Not recorded")
            st.markdown("**Downside case**")
            st.write(plan.get("downside_case") or "Not recorded")
            st.markdown("**Evidence to watch**")
            st.write(plan.get("watch_for") or "Not recorded")
            with st.form(f'review_{plan["id"]}'):
                status = st.selectbox(
                    "Review status",
                    ("planned", "reviewed"),
                    index=1 if plan["status"] == "reviewed" else 0,
                )
                outcome = st.text_area("What happened and what changed?", value=plan.get("outcome_notes") or "")
                if st.form_submit_button("Update review"):
                    save_catalyst_plan(
                        user_id=user["id"], event_key=plan["event_key"], event_date=plan["event_date"],
                        title=plan["title"], base_case=plan.get("base_case") or "",
                        upside_case=plan.get("upside_case") or "", downside_case=plan.get("downside_case") or "",
                        watch_for=plan.get("watch_for") or "", status=status, outcome_notes=outcome,
                    )
                    st.success("Review updated.")


render_footer()
