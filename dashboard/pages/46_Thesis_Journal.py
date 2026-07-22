"""Pro decision journal for saved ticker theses."""

from datetime import datetime

import streamlit as st

from utils.auth_ui import require_login
from utils.billing import require_pro
from utils.header import render_header, render_page_header, render_sidebar_base, render_guided_steps, render_footer
from utils.theme import inject_premium_css
from utils.thesis import list_user_theses


st.set_page_config(page_title="Thesis Journal — UA", layout="wide")
render_header("Thesis Journal")
_journal_section = render_sidebar_base(
    page_title="Thesis Journal",
    sections=("Active Theses", "Closed Decisions", "Invalidated Theses"),
    section_key="thesis_journal_section_rail",
)
inject_premium_css()

render_page_header(
    "Thesis Journal",
    "Your private record of investment reasoning, invalidation conditions, and outcomes.",
    icon="",
)

user = require_login()
require_pro(
    "Thesis Journal",
    benefit="Build a durable decision record tied to live scores, prices, risks, and review outcomes.",
)

render_guided_steps(
    "Create a decision record you can audit later",
    [
        ("Start with a ticker", "Open its Thesis Workspace from Ticker Deep Dive and record your stance, catalysts, risks, and invalidation rule."),
        ("Review the live thesis", "Return as evidence changes to compare the original reasoning with updated scores, prices, and market context."),
        ("Close the feedback loop", "Mark the decision closed or invalidated and capture what happened so future decisions improve."),
    ],
    eyebrow="Private thesis workflow",
    intro="Your thesis journal is private to your account and separates active ideas from completed and invalidated decisions.",
)
_new_ticker_col, _new_action_col, _new_space_col = st.columns([2, 2, 4])
with _new_ticker_col:
    _new_thesis_ticker = st.text_input(
        "Ticker for a new thesis",
        value=st.session_state.get("selected_ticker", ""),
        placeholder="e.g. NVDA",
        key="journal_new_thesis_ticker",
        max_chars=10,
    ).strip().upper()
with _new_action_col:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(
        "Start Thesis in Deep Dive",
        type="primary",
        use_container_width=True,
        disabled=not bool(_new_thesis_ticker),
    ):
        st.session_state["selected_ticker"] = _new_thesis_ticker
        st.session_state["dive_section"] = "Thesis Workspace"
        st.switch_page("pages/3_Ticker_Deep_Dive.py")

_status_map = {
    "Active Theses": "active",
    "Closed Decisions": "closed",
    "Invalidated Theses": "invalidated",
}
_status = _status_map[_journal_section or "Active Theses"]
_theses = list_user_theses(user["id"], status=_status)

_header_cols = st.columns(3)
_header_cols[0].metric("Theses in View", len(_theses))
if _theses:
    _bullish = sum(1 for item in _theses if item["stance"] == "Bullish")
    _bearish = sum(1 for item in _theses if item["stance"] == "Bearish")
    _header_cols[1].metric("Bullish", _bullish)
    _header_cols[2].metric("Bearish", _bearish)
else:
    _header_cols[1].metric("Bullish", 0)
    _header_cols[2].metric("Bearish", 0)

if not _theses:
    st.info(
        "No decisions are in this section yet. Enter a ticker above and select "
        "**Start Thesis in Deep Dive** to create your first decision record."
    )
    if st.button("Open Ticker Deep Dive", type="primary"):
        st.switch_page("pages/3_Ticker_Deep_Dive.py")
else:
    for _item in _theses:
        _stance_color = {
            "Bullish": "#00D566",
            "Bearish": "#FF4444",
            "Neutral": "#F59E0B",
        }.get(_item["stance"], "#8892AA")
        _updated = str(_item.get("updated_at") or "")[:10]
        try:
            _updated = datetime.fromisoformat(str(_item["updated_at"]).replace("Z", "+00:00")).strftime("%b %-d, %Y")
        except Exception:
            pass

        with st.container(border=True):
            _title_col, _meta_col, _action_col = st.columns([2.2, 2.4, 1])
            with _title_col:
                st.markdown(f"### {_item['ticker']}")
                st.markdown(
                    f'<span style="color:{_stance_color};font-size:.78rem;font-weight:800;'
                    f'letter-spacing:.07em;text-transform:uppercase;">{_item["stance"]}</span>',
                    unsafe_allow_html=True,
                )
            with _meta_col:
                _entry = f"${_item['entry_price']:,.2f}" if _item.get("entry_price") else "Not recorded"
                _score = f"{_item['entry_score']:.0f}/100" if _item.get("entry_score") is not None else "Not recorded"
                st.caption(
                    f"Entry {_entry} · score {_score} · horizon {_item['horizon_weeks']} weeks · updated {_updated}"
                )
            with _action_col:
                if st.button("Review", key=f"review_thesis_{_item['ticker']}", use_container_width=True):
                    st.session_state["selected_ticker"] = _item["ticker"]
                    st.session_state["dive_section"] = "Thesis Workspace"
                    st.switch_page("pages/3_Ticker_Deep_Dive.py")

            st.markdown(_item["thesis"])
            _detail_cols = st.columns(3)
            with _detail_cols[0]:
                st.caption("CATALYSTS")
                st.write(_item.get("catalysts") or "Not recorded")
            with _detail_cols[1]:
                st.caption("RISKS")
                st.write(_item.get("risks") or "Not recorded")
            with _detail_cols[2]:
                st.caption("INVALIDATION")
                st.write(_item.get("invalidation") or "Not recorded")
            if _item.get("outcome_notes"):
                st.caption("REVIEW NOTES")
                st.write(_item["outcome_notes"])

render_footer()
