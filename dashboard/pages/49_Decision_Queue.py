"""Pro daily research triage across the user's existing evidence surfaces."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from html import escape

import streamlit as st

st.set_page_config(page_title="Decision Queue — UA", layout="wide")

from utils.billing import require_pro
from utils.header import (
    render_footer,
    render_guided_steps,
    render_header,
    render_page_header,
    render_sidebar_base,
)
from utils.theme import inject_premium_css


render_header("Decision Queue")
section = render_sidebar_base(
    page_title="Decision Queue",
    sections=("Priority Queue", "Watching", "Completed", "Methodology"),
    section_key="decision_queue_section_rail",
)
inject_premium_css()
require_pro(page_name="Decision Queue")
try:
    from utils.instrumentation import record_once
    record_once("decision_queue_viewed")
except Exception:
    pass

render_page_header(
    "Decision Queue",
    "A daily, evidence-ranked workflow for the portfolio decisions that deserve review now.",
    icon="",
)

render_guided_steps(
    "Turn fragmented evidence into a controlled review process",
    [
        ("Review priority", "Start with the highest-ranked evidence change, catalyst, thesis conflict, or concentration exception."),
        ("Open the source", "Move directly into the ticker, thesis, or portfolio workspace behind the queue item."),
        ("Triage explicitly", "Watch, complete, or snooze the item. New underlying evidence automatically reopens it."),
    ],
    eyebrow="Investment committee workflow",
    intro="The queue ranks recorded facts only. It does not create price targets, trade instructions, or synthetic observations.",
)


if section == "Methodology":
    st.markdown("#### How the queue ranks work")
    st.markdown(
        "The engine evaluates five review conditions: material seven-day score movement, "
        "upcoming earnings, conflict between an active thesis and current score evidence, "
        "an elapsed thesis horizon, and portfolio concentration. Missing score coverage is "
        "also elevated so unavailable evidence is never silently treated as neutral."
    )
    st.markdown("#### What it deliberately does not do")
    st.markdown(
        "It does not predict an earnings result, alter the canonical Confluence Score, infer "
        "a position you did not save, or recommend a transaction. Earnings dates supplied by "
        "the market-data provider are labeled provisional. Completed work reopens only when "
        "its evidence fingerprint changes."
    )
    st.markdown("#### Priority order")
    st.dataframe(
        {
            "Review condition": [
                "Imminent earnings / material score move",
                "Thesis conflict / missing evidence",
                "Near earnings / elapsed thesis horizon",
                "Portfolio concentration",
            ],
            "Why it ranks there": [
                "New information or event risk can quickly dominate the existing read.",
                "The user's recorded decision and the available evidence require reconciliation.",
                "A scheduled review is due before the decision record becomes stale.",
                "Position size increases the portfolio consequence of otherwise unchanged evidence.",
            ],
        },
        use_container_width=True,
        hide_index=True,
    )
    render_footer()
    st.stop()


user = st.session_state.get("user")
if not user:
    st.info("Sign in with an active Pro account to build your private Decision Queue.")
    st.stop()


@st.cache_data(ttl=21_600, show_spinner=False)
def _load_earnings(symbols: tuple[str, ...]) -> dict[str, dict | None]:
    """Bounded parallel fetch; the underlying provider call is also cached."""
    from utils.earnings_awareness import next_earnings

    output: dict[str, dict | None] = {ticker: None for ticker in symbols}
    if not symbols:
        return output
    with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as pool:
        futures = {pool.submit(next_earnings, ticker): ticker for ticker in symbols}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                output[ticker] = future.result()
            except Exception:
                output[ticker] = None
    return output


from utils.decision_queue import (
    apply_queue_states,
    build_decision_queue,
    list_queue_states,
    load_score_changes,
    set_queue_state,
)
from utils.personalized_brief import load_portfolio_evidence
from utils.thesis import list_user_theses


evidence = load_portfolio_evidence(user["id"], limit=25)
if not evidence:
    st.info(
        "Save your holdings in Portfolio Intelligence or add securities to your watchlist. "
        "The queue never invents a portfolio when no account evidence exists."
    )
    if st.button("Build my portfolio", type="primary"):
        st.switch_page("pages/44_Portfolio_Suite.py")
    render_footer()
    st.stop()

tickers = tuple(str(row["ticker"]).upper() for row in evidence)
with st.spinner("Prioritizing recorded evidence…"):
    score_changes = load_score_changes(tickers, days=7)
    theses = list_user_theses(user["id"])
    earnings = _load_earnings(tickers)
    raw_items = build_decision_queue(
        evidence,
        score_changes=score_changes,
        theses=theses,
        earnings=earnings,
    )
    items = apply_queue_states(raw_items, list_queue_states(user["id"]))

open_items = [row for row in items if row["status"] == "open"]
watching_items = [row for row in items if row["status"] in {"watching", "snoozed"}]
done_items = [row for row in items if row["status"] == "done"]

metrics = st.columns(4)
metrics[0].metric("Needs review", len(open_items))
metrics[1].metric("Urgent", sum(row["severity"] == "urgent" for row in open_items))
metrics[2].metric("Watching", len(watching_items))
metrics[3].metric(
    "Evidence coverage",
    f'{sum((row.get("snapshot") or {}).get("score") is not None for row in evidence)}/{len(evidence)}',
)

source = str(evidence[0].get("source") or "watchlist")
st.caption(
    f"Built from your saved {source}, persisted score history, private thesis journal, and provider-supplied earnings dates. "
    "Unavailable inputs stay unavailable."
)


def _open_source(item: dict) -> None:
    ticker = item["ticker"]
    st.session_state["selected_ticker"] = ticker
    if item["route"] == "thesis":
        st.switch_page("pages/46_Thesis_Journal.py")
    elif item["route"] == "portfolio":
        st.session_state["portfolio_suite_section_rail"] = "Portfolio Fit Lab"
        st.switch_page("pages/44_Portfolio_Suite.py")
    else:
        st.switch_page("pages/3_Ticker_Deep_Dive.py")


def _set(item: dict, status: str) -> None:
    until = date.today() + timedelta(days=7) if status == "snoozed" else None
    set_queue_state(
        user["id"],
        item["item_key"],
        item["evidence_hash"],
        status,
        snoozed_until=until,
        note=item.get("note") or "",
    )
    st.rerun()


def _render_item(item: dict) -> None:
    accent = {"urgent": "#C98282", "high": "#C5A46D", "review": "#7FA7B7"}[item["severity"]]
    score_text = f'{item["score"]:.0f}' if item.get("score") is not None else "N/A"
    snooze_text = f' · snoozed until {item["snoozed_until"]}' if item.get("snoozed_until") else ""
    st.markdown(
        f'<div style="background:linear-gradient(145deg,#111720,#0E131B);border:1px solid rgba(255,255,255,.08);'
        f'border-left:3px solid {accent};border-radius:11px;padding:17px 18px 15px;margin:8px 0 4px;">'
        f'<div style="display:flex;justify-content:space-between;gap:18px;align-items:flex-start;">'
        f'<div><div style="font-size:.60rem;color:{accent};font-weight:800;letter-spacing:.12em;text-transform:uppercase;">'
        f'{escape(item["severity"])} review · priority {item["priority"]:.0f}{escape(snooze_text)}</div>'
        f'<div style="font-size:1.12rem;color:#E7ECF5;font-weight:760;margin-top:5px;">'
        f'{escape(item["ticker"])} · {escape(item["headline"])}</div></div>'
        f'<div style="text-align:right;min-width:82px;"><div style="font-size:1.45rem;color:#E7ECF5;font-weight:780;">{score_text}</div>'
        f'<div style="font-size:.58rem;color:#8D97A8;letter-spacing:.09em;">SCORE</div></div></div>'
        f'<div style="font-size:.79rem;color:#B6BFCC;line-height:1.55;margin-top:11px;">{escape(item["why_now"])}</div>'
        f'<div style="font-size:.68rem;color:#8D97A8;margin-top:10px;">{escape(item["next_action"])}'
        + (f' · {item["weight_pct"]:.1f}% portfolio weight' if item["source"] == "portfolio" else "")
        + '</div></div>',
        unsafe_allow_html=True,
    )
    with st.expander(f"Evidence details · {item['ticker']}"):
        for trigger in item["triggers"]:
            st.markdown(f"**{trigger['title']}** — {trigger['detail']}")
        st.caption(
            f"Snapshot: {item.get('snapshot_date') or 'unavailable'} · "
            f"Evidence fingerprint: {item['evidence_hash'][:10]}"
        )
    controls = st.columns([1.5, 1, 1, 1])
    if controls[0].button("Open source research", key=f"open_{section}_{item['item_key']}", use_container_width=True):
        _open_source(item)
    if controls[1].button("Watch", key=f"watch_{section}_{item['item_key']}", use_container_width=True):
        _set(item, "watching")
    if controls[2].button("Complete", key=f"done_{section}_{item['item_key']}", use_container_width=True):
        _set(item, "done")
    if controls[3].button("Snooze 7d", key=f"snooze_{section}_{item['item_key']}", use_container_width=True):
        _set(item, "snoozed")


if section == "Priority Queue":
    visible = open_items
    empty = "No current evidence exceptions require review. The queue will reopen automatically when facts change."
elif section == "Watching":
    visible = watching_items
    empty = "Nothing is being watched or snoozed."
else:
    visible = done_items
    empty = "No current evidence fingerprint has been completed yet."

if not visible:
    st.success(empty)
else:
    for item in visible:
        _render_item(item)

render_footer()
