"""Tests for the instrumentation layer.

The bug being guarded against is not a crash — it is silence. Three of four
onboarding steps had no `mark_step()` call site anywhere, so the checklist could
never advance, and 25 of 27 declared analytics events had never been written.
Neither failure raised anything; both simply produced no data.

So these tests assert on *coverage*: that every declared onboarding step is
reachable through some event, and that the wiring exists in the pages that are
supposed to emit it. A test that only checked "record() does not raise" would
have passed against the broken code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from utils.instrumentation import _EVENT_TO_STEP, record, record_once
from utils.onboarding import STEPS

DASHBOARD = Path(__file__).resolve().parent.parent


# ── Coverage: the actual bug ──────────────────────────────────────────────────

def test_every_onboarding_step_is_reachable_from_some_event():
    """The regression that shipped: steps existed with no way to complete them."""
    declared = {s["id"] for s in STEPS}
    mapped = set(_EVENT_TO_STEP.values())
    missing = declared - mapped
    assert not missing, (
        f"onboarding steps with no event that completes them: {sorted(missing)}. "
        "A step that nothing can mark done leaves the checklist stuck at zero."
    )


def test_no_event_maps_to_an_undeclared_step():
    """A typo in the mapping would silently never match a real step."""
    declared = {s["id"] for s in STEPS}
    unknown = set(_EVENT_TO_STEP.values()) - declared
    assert not unknown, f"events mapped to non-existent steps: {sorted(unknown)}"


@pytest.mark.parametrize("step_id", [s["id"] for s in STEPS])
def test_each_step_has_a_wired_call_site_in_the_codebase(step_id):
    """Assert the emitting code actually exists, not just the mapping.

    The mapping alone is not enough: `add_to_watchlist` could be mapped and
    still never fire if nothing calls record() with it.
    """
    events = [e for e, s in _EVENT_TO_STEP.items() if s == step_id]
    assert events, f"no event maps to {step_id}"

    sources = list((DASHBOARD / "pages").rglob("*.py")) + list((DASHBOARD / "utils").rglob("*.py"))
    blob = "\n".join(
        p.read_text(encoding="utf-8") for p in sources
        if p.name != "instrumentation.py"  # the mapping itself does not count
    )
    assert any(f'"{e}"' in blob for e in events), (
        f"step {step_id!r} maps to {events} but no page or util calls record() "
        "with any of them, so it can never complete"
    )


# ── Behaviour ─────────────────────────────────────────────────────────────────

def test_record_never_raises_without_streamlit_or_db(monkeypatch):
    """Instrumentation must not be able to break a page."""
    import utils.instrumentation as instr

    def boom(*a, **k):
        raise RuntimeError("analytics is down")

    monkeypatch.setattr("utils.analytics.track", boom)
    record("some_event", user_id=1, ticker="AAPL")  # must not raise


def test_record_forwards_event_user_and_properties(monkeypatch):
    seen = {}

    def fake_track(event, user_id=None, properties=None, session_id=None):
        seen.update(event=event, user_id=user_id, properties=properties)

    monkeypatch.setattr("utils.analytics.track", fake_track)
    record("ticker_analyzed", user_id=7, ticker="CCJ")

    assert seen["event"] == "ticker_analyzed"
    assert seen["user_id"] == 7
    assert seen["properties"] == {"ticker": "CCJ"}


def test_record_marks_the_mapped_onboarding_step(monkeypatch):
    marked = []
    monkeypatch.setattr("utils.analytics.track", lambda *a, **k: None)
    monkeypatch.setattr("utils.onboarding.mark_step",
                        lambda uid, step: marked.append((uid, step)))

    record("watchlist_add", user_id=42, ticker="LEU")
    assert marked == [(42, "add_to_watchlist")]


def test_record_skips_step_for_anonymous_users(monkeypatch):
    marked = []
    monkeypatch.setattr("utils.analytics.track", lambda *a, **k: None)
    monkeypatch.setattr("utils.onboarding.mark_step",
                        lambda uid, step: marked.append((uid, step)))

    record("watchlist_add", user_id=None)
    assert marked == [], "cannot credit an onboarding step without a user"


def test_record_tolerates_mark_step_failure(monkeypatch):
    monkeypatch.setattr("utils.analytics.track", lambda *a, **k: None)

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr("utils.onboarding.mark_step", boom)
    record("watchlist_add", user_id=1)  # must not raise


def test_unmapped_event_marks_no_step(monkeypatch):
    marked = []
    monkeypatch.setattr("utils.analytics.track", lambda *a, **k: None)
    monkeypatch.setattr("utils.onboarding.mark_step",
                        lambda uid, step: marked.append(step))

    record("options_flow_viewed", user_id=3)
    assert marked == []


def test_record_once_falls_back_to_recording_outside_streamlit(monkeypatch):
    """No session to dedupe against is not a reason to record nothing."""
    calls = []
    monkeypatch.setattr("utils.analytics.track",
                        lambda event, **k: calls.append(event))
    record_once("screener_viewed")
    assert calls == ["screener_viewed"]


# ── Wiring ────────────────────────────────────────────────────────────────────

def test_heartbeat_is_wired_into_the_header():
    """Without a per-navigation event, every session duration computes to 0s."""
    src = (DASHBOARD / "utils" / "header.py").read_text(encoding="utf-8")
    assert "heartbeat()" in src, (
        "no heartbeat in render_header: session duration is derived as "
        "(last event - first event), which is zero when a session emits one event"
    )


def test_watchlist_add_is_instrumented_at_the_choke_point():
    """Instrumenting the buttons instead would miss any future add path."""
    src = (DASHBOARD / "utils" / "alerts_db.py").read_text(encoding="utf-8")
    assert "watchlist_add" in src


@pytest.mark.parametrize("page,event", [
    ("40_Stock_Recommender.py", "recommender_viewed"),
    ("44_Portfolio_Suite.py", "portfolio_suite_viewed"),
    ("45_Options_Flow.py", "options_flow_viewed"),
    ("10_Watchlist.py", "watchlist_viewed"),
    ("30_Track_Record_Live.py", "track_record_viewed"),
    ("6_Stock_Screener.py", "screener_viewed"),
    ("1_Signal_Dashboard.py", "signal_dashboard_viewed"),
])
def test_feature_pages_emit_a_reached_event(page, event):
    """So "which features are actually used" becomes answerable."""
    path = DASHBOARD / "pages" / page
    if not path.exists():
        pytest.skip(f"{page} not present")
    assert event in path.read_text(encoding="utf-8")


def test_page_level_events_use_record_once_not_record():
    """record() at page level fires on every Streamlit rerun and inflates counts."""
    offenders = []
    for path in (DASHBOARD / "pages").rglob("*.py"):
        for m in re.finditer(r'^\s*record\("(\w+_viewed)"', path.read_text(encoding="utf-8"), re.M):
            offenders.append(f"{path.name}: {m.group(1)}")
    assert not offenders, (
        "page-reached events must use record_once, or Streamlit reruns inflate "
        f"them: {offenders}"
    )
