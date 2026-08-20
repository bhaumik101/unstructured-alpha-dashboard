"""The half of the funnel that was never measured.

The admin Conversion Funnel chart starts at "Signed Up" and is computed from the
users table -- it shows what happens AFTER someone has an account. The half
where a 0%-conversion product actually loses people, visitor to account, had no
numbers at all, because the events that measure it were defined and never fired.

They fire now (the funnel instrumentation change), so this reads them.

TWO THINGS THIS DELIBERATELY REFUSES TO DO
------------------------------------------
Count events instead of people. One person reloading pricing five times is one
person who saw pricing; counting reloads would make the step above checkout look
healthier than it is.

Report 0 for a period nothing recorded. Every step below page_view was
unmeasured until the events were wired, and a confident zero for those weeks is
the same misleading certainty utils/conversion_measurement.py already refuses
via VISITOR_TRACKING_START.
"""

from __future__ import annotations

from datetime import datetime, timezone

from utils.conversion_measurement import ACQUISITION_STEPS, build_acquisition_funnel


def _ev(name, visitor=None, user_id=None, when="2026-08-20T00:00:00+00:00"):
    return {
        "event_name": name, "visitor_id": visitor, "user_id": user_id,
        "created_at": datetime.fromisoformat(when),
    }


def test_nothing_recorded_reads_as_uninstrumented_not_as_zero():
    out = build_acquisition_funnel([_ev("page_view", visitor="v1")])
    assert out["instrumented"] is False, (
        "page_view alone must not count as instrumented: it predates the funnel "
        "events, so the steps below it have no data rather than zero conversions"
    )


def test_one_funnel_event_marks_it_instrumented():
    out = build_acquisition_funnel([
        _ev("page_view", visitor="v1"),
        _ev("signup_started", visitor="v1"),
    ])
    assert out["instrumented"] is True
    assert out["first_seen"] is not None


def test_steps_count_people_not_events():
    rows = [_ev("page_view", visitor="v1")] + [
        _ev("pricing_viewed", visitor="v1") for _ in range(5)
    ]
    out = build_acquisition_funnel(rows)
    pricing = next(s for s in out["steps"] if s["event"] == "pricing_viewed")
    assert pricing["count"] == 1, (
        f"one visitor viewing pricing five times counted as {pricing['count']}"
    )


def test_a_signed_in_user_without_a_visitor_id_still_counts_once():
    rows = [_ev("checkout_completed", user_id=7) for _ in range(3)]
    out = build_acquisition_funnel(rows)
    done = next(s for s in out["steps"] if s["event"] == "checkout_completed")
    assert done["count"] == 1


def test_percentages_are_of_the_top_and_of_the_previous_step():
    rows = (
        [_ev("page_view", visitor=f"v{i}") for i in range(10)]
        + [_ev("signup_started", visitor=f"v{i}") for i in range(5)]
        + [_ev("signup_completed", visitor=f"v{i}") for i in range(1)]
    )
    out = build_acquisition_funnel(rows)
    by = {s["event"]: s for s in out["steps"]}
    assert by["signup_started"]["pct_of_top"] == 50.0
    assert by["signup_completed"]["pct_of_top"] == 10.0
    # 1 of the 5 who started -- the number that names where people are lost
    assert by["signup_completed"]["pct_of_prev"] == 20.0


def test_an_empty_step_does_not_divide_the_next_one_by_zero():
    rows = (
        [_ev("page_view", visitor="v1")]
        + [_ev("checkout_completed", visitor="v1")]      # nothing in between
    )
    out = build_acquisition_funnel(rows)
    done = next(s for s in out["steps"] if s["event"] == "checkout_completed")
    assert done["pct_of_prev"] is None, (
        "a step whose predecessor recorded nobody cannot state a rate against it"
    )
    assert done["count"] == 1


def test_the_steps_match_the_events_that_are_actually_fired():
    """A step naming an event nothing emits would read 0 forever."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    blob = "\n".join(
        p.read_text(encoding="utf-8")
        for p in list(root.glob("pages/*.py")) + list(root.glob("utils/*.py"))
        if "retired" not in p.parts and p.name not in ("analytics.py", "conversion_measurement.py")
    )
    import re
    src = (root / "utils" / "analytics.py").read_text(encoding="utf-8")
    const_for = {v: k for k, v in re.findall(r'^\s+([A-Z_]+)\s*=\s*"([a-z_]+)"', src, re.M)}
    unfired = [
        name for name, _ in ACQUISITION_STEPS
        if name in const_for and not re.search(rf"\b{const_for[name]}\b", blob)
    ]
    assert not unfired, (
        "these funnel steps name events that nothing fires, so they would show "
        "0 forever: " + ", ".join(unfired)
    )
