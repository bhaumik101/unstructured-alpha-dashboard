"""One call site for "this happened", fanning out to analytics and onboarding.

Two separate problems motivated this module, both found by running
scripts/usage_report.py against production:

1. **The event taxonomy was decorative.** utils/analytics.py declares 27 event
   constants, but only `page_view` and `returning_user_visit` had ever reached
   the database. Every feature shipped in the last month emitted nothing, so
   there was no way to tell which ones were used.

2. **Three of four onboarding steps could never complete.** STEPS declares
   view_signals, search_ticker, add_to_watchlist and set_risk_profile, but
   `mark_step()` had exactly one call site in the codebase, for the step added
   most recently. The "Start Here" checklist sat at zero for every user
   regardless of what they did, and onboarding_progress held zero rows.

Recording an action and crediting an onboarding step are the same moment, so
they belong behind one function — the previous split is precisely why one of
them was forgotten.

Everything here is best-effort and never raises: instrumentation must not be
able to break a page. `track()` already dispatches on a daemon thread, and
`mark_step()` swallows its own database errors.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maps an event to the onboarding step it satisfies, so callers state what
# happened rather than remembering which steps exist.
_EVENT_TO_STEP: dict[str, str] = {
    "signal_dashboard_viewed": "view_signals",
    "ticker_analyzed": "search_ticker",
    "watchlist_add": "add_to_watchlist",
    "risk_profile_set": "set_risk_profile",
}


def _session_id() -> str | None:
    """Streamlit session id, for stitching anonymous activity.

    Returns None outside a script run (cron jobs, tests) rather than raising.
    """
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        return ctx.session_id if ctx else None
    except Exception:
        return None


def _current_user_id() -> int | None:
    try:
        import streamlit as st

        user = st.session_state.get("user") or {}
        uid = user.get("id")
        return int(uid) if uid is not None else None
    except Exception:
        return None


def record(event: str, user_id: int | None = None, **properties: Any) -> None:
    """Record one product event and credit any onboarding step it satisfies.

    `user_id` is resolved from the session when omitted, so call sites deep in
    a page do not each have to dig it out of session state.
    """
    uid = user_id if user_id is not None else _current_user_id()

    try:
        from utils.analytics import track

        track(event, user_id=uid, properties=properties or None,
              session_id=_session_id())
    except Exception as exc:
        logger.debug("[instrumentation] track failed for %r: %s", event, exc)

    step = _EVENT_TO_STEP.get(event)
    if step and uid is not None:
        try:
            from utils.onboarding import mark_step

            mark_step(uid, step)
        except Exception as exc:
            logger.debug("[instrumentation] mark_step failed for %r: %s", step, exc)


def record_once(event: str, dedupe_key: str | None = None, **properties: Any) -> None:
    """Record at most once per Streamlit session.

    Streamlit reruns the whole script on every interaction, so an unguarded
    `record()` at page level fires on every widget change and inflates counts
    to the point of uselessness. Use this for "user reached X" events; use
    `record()` for genuine discrete actions like clicking a button.
    """
    key = f"_instr_once::{dedupe_key or event}"
    try:
        import streamlit as st

        if st.session_state.get(key):
            return
        st.session_state[key] = True
    except Exception:
        # Outside a Streamlit context there is no session to dedupe against;
        # recording once is still better than not recording.
        pass
    record(event, **properties)


def heartbeat() -> None:
    """Emit a session heartbeat so time-on-site becomes measurable.

    Session duration is derived as (last event - first event) per session_id.
    With only a single page_view per session that difference was always zero,
    which is why every duration percentile in the usage report read 0s — not
    because sessions were short, but because there was nothing to subtract.

    This fires on each page navigation, so a session that touches three pages
    yields a real span. It is not a true dwell timer; that needs a client-side
    ping, which is a larger change and is noted in the docstring rather than
    faked here.
    """
    record("session_heartbeat")
