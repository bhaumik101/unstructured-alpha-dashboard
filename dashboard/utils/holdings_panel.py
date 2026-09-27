# utils/holdings_panel.py
# Unstructured Alpha — the holdings a report is measuring, editable in place
#
# WHY THIS EXISTS
# ---------------
# Adding or removing one holding meant leaving the report, going back to a
# form, finding the row, changing it, and measuring again. So nobody did it.
# A portfolio is not entered once and left alone; it is fiddled with, and the
# interesting question is usually "what happens if I take this one out".
#
# This is one panel, used in both places: the empty state where a portfolio is
# built from nothing, and the report itself, where it sits under the numbers so
# a holding can be changed without losing the page.
#
# Two things it deliberately does NOT do:
#
#   - re-measure on every keystroke. A report is 10-20 seconds of real work
#     against two providers; doing that per edit would be slower, not faster,
#     and would hammer them. Edits are instant, and one button re-measures.
#   - show a price as live. Yahoo's daily close is exactly that, so the panel
#     says "close" and prints the date it belongs to. "Live" on a number that
#     can be a day old is the kind of small lie this product does not tell.

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import streamlit as st

from utils import holdings as hold
from utils import report_ui as ui

_STALE = "uar_stale"


def mark_stale() -> None:
    st.session_state[_STALE] = True


def is_stale() -> bool:
    return bool(st.session_state.get(_STALE))


def clear_stale() -> None:
    st.session_state.pop(_STALE, None)


def _bump() -> None:
    """New widget keys for the amount inputs.

    A number_input's stored widget state outranks the value= it is given, so a
    row whose amount is recomputed keeps the old number on screen until the
    widget itself is new. Measured once already on this page: adding a holding
    to a 100% one showed 150%.
    """
    st.session_state["uar_gen"] = st.session_state.get("uar_gen", 0) + 1


def render_search(max_holdings: int, *, key_prefix: str = "uar") -> bool:
    """The add-a-holding box. True when something was added."""
    from utils import symbol_search as sym

    draft = st.session_state.setdefault("uar_draft", [])
    query = st.text_input(
        "Add a stock, ETF or mutual fund by name or ticker",
        placeholder="Apple · total bond market · Fidelity 500 · VTSAX",
        key=f"{key_prefix}_query",
    )
    if not query or len(query.strip()) < 2:
        return False

    results, source = sym.search_symbols(query, limit=6)
    if source == "offline":
        st.caption("The name lookup is unavailable right now, so these are matches from a "
                   "short built-in list. Anything missing can still be added by ticker "
                   "under “Paste a list”.")
    if not results:
        st.caption("Nothing matched. Try a shorter phrase, or the ticker itself.")
    for row in results:
        label_col, add_col = st.columns([5, 1])
        label_col.markdown(ui.search_result_html(row), unsafe_allow_html=True)
        if add_col.button("Add", key=f"{key_prefix}_add_{row['ticker']}", width="stretch"):
            touched = st.session_state.get("uar_weights_touched", False)
            st.session_state["uar_draft"], problem = ui.add_to_draft(
                draft, row, max_holdings, equal=not touched)
            if problem:
                st.warning(problem)
                return False
            if not touched:
                _bump()
            mark_stale()
            return True
    return False


def _mode_selector(key_prefix: str) -> str:
    # The label is collapsed because the radio is drawn as a pill row, and a
    # visible widget label there renders as an empty pill beside the options.
    mode = st.radio(
        "How are you giving the amounts?",
        hold.MODES,
        format_func=lambda m: hold.MODE_LABELS[m],
        horizontal=True,
        key=f"{key_prefix}_mode",
        label_visibility="collapsed",
    )
    st.caption(hold.MODE_HELP[mode])
    return mode


def render(max_holdings: int, *, key_prefix: str = "uar",
           empty_hint: str = "Search above and add holdings one at a time.",
           show_mode: bool = True) -> Tuple[List[dict], str, Dict[str, dict], List[str]]:
    """Draw the panel. Returns (draft, mode, prices, problems).

    The caller decides what to do about `problems` and about is_stale(); this
    only edits the list and says what it could not work out.
    """
    draft: List[dict] = st.session_state.get("uar_draft", [])
    mode = _mode_selector(key_prefix) if show_mode else st.session_state.get(
        f"{key_prefix}_mode", "percent")

    if not draft:
        st.caption(empty_hint)
        return [], mode, {}, []

    prices: Dict[str, dict] = {}
    if mode == "shares":
        prices = hold.latest_closes([r["ticker"] for r in draft])

    gen = st.session_state.get("uar_gen", 0)
    st.markdown(ui.holdings_head_html(draft, mode), unsafe_allow_html=True)

    field = {"percent": "weight_pct", "amount": "amount", "shares": "shares"}[mode]
    for row in draft:
        name_col, amount_col, value_col, drop_col = st.columns([3.2, 1.4, 1.6, 1.2])
        name_col.markdown(ui.draft_row_html(row), unsafe_allow_html=True)

        before = row.get(field)
        before = float(before) if isinstance(before, (int, float)) else 0.0
        entered = amount_col.number_input(
            f"{row['ticker']} {hold.MODE_COLUMN[mode]}",
            min_value=0.0, max_value=1e12 if mode != "percent" else 100.0,
            step=1.0, value=before, format="%.4f" if mode == "shares" else "%.2f",
            key=f"{key_prefix}_amt_{mode}_{gen}_{row['ticker']}",
            label_visibility="collapsed",
        )
        if entered != before:
            row[field] = entered
            st.session_state["uar_weights_touched"] = True
            mark_stale()
        else:
            row[field] = entered

        value_col.markdown(ui.holding_value_html(row, mode, prices, draft=draft),
                           unsafe_allow_html=True)

        if drop_col.button("Remove", key=f"{key_prefix}_rm_{row['ticker']}", width="stretch"):
            equal = not st.session_state.get("uar_weights_touched", False)
            st.session_state["uar_draft"] = ui.remove_from_draft(draft, row["ticker"], equal=equal)
            if equal:
                _bump()
            mark_stale()
            st.rerun()

    weights, problems = hold.to_weights(draft, mode, prices)
    st.markdown(ui.holdings_total_html(draft, mode, prices, weights),
                unsafe_allow_html=True)
    for problem in problems:
        st.warning(problem)
    return draft, mode, prices, problems


def draft_to_holdings(draft: List[dict], mode: str,
                      prices: Optional[Dict[str, dict]] = None) -> List[dict]:
    """What the engine measures, from whatever units the panel was given."""
    return hold.to_weights(draft, mode, prices or {})[0]
