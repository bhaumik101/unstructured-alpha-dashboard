"""Real-data guards for the redesign conversion measurement."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from utils.conversion_measurement import build_conversion_measurement


NOW = datetime(2026, 7, 29, 18, 0, tzinfo=timezone.utc)


def _page(
    created_at: str,
    *,
    page: str = "Home",
    visitor: str | None = "visitor-1",
    session: str | None = "session-1",
    user_id: int | None = None,
) -> dict:
    return {
        "created_at": created_at,
        "properties": json.dumps({"page": page}),
        "visitor_id": visitor,
        "session_id": session,
        "user_id": user_id,
    }


def _signup(created_at: str, *, user_id: int) -> dict:
    return {"id": user_id, "created_at": created_at}


def test_daily_visitors_and_weekly_conversion_use_exact_real_counts():
    pages = [
        _page("2026-07-21T10:00:00+00:00", visitor="v1", session="s1"),
        _page("2026-07-21T11:00:00+00:00", visitor="v1", session="s1", page="About"),
        _page("2026-07-21T12:00:00+00:00", visitor="v2", session="s2"),
        _page("2026-07-23T10:00:00+00:00", visitor="v3", session="s3"),
    ]
    signups = [_signup("2026-07-23T11:00:00+00:00", user_id=7)]

    result = build_conversion_measurement(pages, signups, now=NOW)
    july_21 = next(row for row in result["daily"] if row["date"] == "2026-07-21")
    rollout_week = next(
        row for row in result["weekly"] if row["week_start"] == "2026-07-20"
    )

    assert july_21["unique_visitors"] == 2
    assert july_21["signups"] == 0
    assert rollout_week["unique_visitors"] == 3
    assert rollout_week["signups"] == 1
    assert rollout_week["conversion_rate"] == pytest.approx(100 / 3)
    assert rollout_week["phase"] == "Redesign rollout overlap"


def test_missing_visitor_identity_is_unavailable_not_zero_or_interpolated():
    pages = [
        _page("2026-07-21T10:00:00+00:00", visitor="v1"),
        _page("2026-07-21T11:00:00+00:00", visitor=None),
    ]
    result = build_conversion_measurement(pages, [], now=NOW)
    day = next(row for row in result["daily"] if row["date"] == "2026-07-21")
    week = next(
        row for row in result["weekly"] if row["week_start"] == "2026-07-20"
    )

    assert day["identified_visitors"] == 1
    assert day["unique_visitors"] is None
    assert day["excluded_page_views"] == 1
    assert week["unique_visitors"] is None
    assert week["conversion_rate"] is None
    assert result["totals"]["unique_visitors"] is None
    assert result["totals"]["conversion_rate"] is None


def test_landing_bounce_proxy_counts_only_visits_entering_on_home():
    pages = [
        # v1: lands on Home, leaves. A real one-page visit.
        _page("2026-07-20T10:00:00+00:00", session="one", visitor="v1"),
        # v2: Home then a second page. Engaged, not a bounce.
        _page("2026-07-20T11:00:00+00:00", session="multi", visitor="v2"),
        _page(
            "2026-07-20T11:05:00+00:00",
            session="multi",
            visitor="v2",
            page="Ticker Deep Dive",
        ),
        # v3 enters deep on About, so is not a landing visit at all.
        _page(
            "2026-07-20T12:00:00+00:00",
            session="deep-link",
            visitor="v3",
            page="About",
        ),
        # v4 has NO session_id but is a real identified visitor landing on Home.
        # The previous session-keyed implementation silently dropped this person.
        _page("2026-07-20T13:00:00+00:00", session=None, visitor="v4"),
    ]
    bounce = build_conversion_measurement(pages, [], now=NOW)["bounce"]

    assert bounce["landing_sessions"] == 3          # v1, v2, v4 -- v3 entered deep
    assert bounce["one_page_sessions"] == 2         # v1 and v4
    assert bounce["multi_page_sessions"] == 1       # v2
    assert bounce["one_page_rate"] == pytest.approx(66.666, rel=1e-3)
    assert bounce["unavailable_reason"] is None
    assert bounce["page_views_without_visitor"] == 0


def test_one_visitor_across_many_streamlit_sessions_is_one_visit():
    """The bug this metric had: session_id is a connection id, not a visit.

    Before PR #103 the top nav was raw <a href>, so every click was a full page
    load and Streamlit issued a NEW session_id. On real stored data one visitor
    produced 86 distinct session_ids across 89 page views, and 96% of sessions
    held exactly one page view -- so an engaged reader was reported as dozens of
    bounces. Keying on session_id also meant PR #103 would appear to slash the
    bounce rate overnight while nobody's behaviour changed.

    Same visitor, five pages, five different session_ids, minutes apart: that is
    ONE engaged visit and ZERO bounces.
    """
    pages = [
        _page("2026-07-20T10:00:00+00:00", session="s1", visitor="v1"),
        _page("2026-07-20T10:02:00+00:00", session="s2", visitor="v1",
              page="Signal Dashboard"),
        _page("2026-07-20T10:04:00+00:00", session="s3", visitor="v1",
              page="Ticker Deep Dive"),
        _page("2026-07-20T10:06:00+00:00", session="s4", visitor="v1",
              page="Stock Screener"),
        _page("2026-07-20T10:08:00+00:00", session="s5", visitor="v1",
              page="Today's Brief"),
    ]
    bounce = build_conversion_measurement(pages, [], now=NOW)["bounce"]

    assert bounce["landing_sessions"] == 1
    assert bounce["multi_page_sessions"] == 1
    assert bounce["one_page_sessions"] == 0
    assert bounce["one_page_rate"] == 0.0


def test_return_visit_after_the_inactivity_gap_is_a_separate_visit():
    """The same visitor returning hours later is a new visit, not one long one."""
    pages = [
        _page("2026-07-20T10:00:00+00:00", session="s1", visitor="v1"),
        _page("2026-07-20T18:00:00+00:00", session="s2", visitor="v1"),
    ]
    bounce = build_conversion_measurement(pages, [], now=NOW)["bounce"]

    assert bounce["landing_sessions"] == 2
    assert bounce["one_page_sessions"] == 2


def test_bounce_rate_is_withheld_when_visitor_identity_is_incomplete():
    """Estimating over the identified minority would misdescribe the population.

    Visitor identity only began recording 2026-07-27, so most stored traffic can
    never be reconstructed into visits. The metric says so instead of guessing.
    """
    pages = [
        _page("2026-07-20T10:00:00+00:00", session="s1", visitor="v1"),
        _page("2026-07-20T11:00:00+00:00", session="s2", visitor=None),
    ]
    bounce = build_conversion_measurement(pages, [], now=NOW)["bounce"]

    assert bounce["one_page_rate"] is None
    assert bounce["unavailable_reason"] is not None
    assert "visitor identifier" in bounce["unavailable_reason"]
    assert bounce["page_views_without_visitor"] == 1


def test_untracked_period_reports_unknown_visitors_not_zero():
    """"0 visitors" must not be asserted for a period nothing was recorded in.

    Seen on real data: the week of 2026-07-06 rendered as 0 unique visitors
    beside 2 actual signups, because an empty period trivially satisfied
    "identified == total". Zero visitors producing two signups is incoherent and
    discredits every other number on the panel. Absence of measurement is not
    measurement of absence.
    """
    signups = [
        {"id": 1, "created_at": "2026-07-08T10:00:00+00:00"},
        {"id": 2, "created_at": "2026-07-09T10:00:00+00:00"},
    ]
    result = build_conversion_measurement([], signups, now=NOW)

    week = next(
        row for row in result["weekly"] if row["week_start"] == "2026-07-06"
    )
    assert week["signups"] == 2
    assert week["unique_visitors"] is None, "untracked week must not claim 0 visitors"
    assert week["conversion_rate"] is None

    day = next(row for row in result["daily"] if row["date"] == "2026-07-08")
    assert day["unique_visitors"] is None


def test_genuinely_empty_day_after_tracking_began_is_a_real_zero():
    """Once identity is recording, no traffic really does mean zero.

    The guard above must not turn every quiet day into "unknown" forever.
    """
    result = build_conversion_measurement(
        [_page("2026-07-27T10:00:00+00:00", visitor="v1")], [], now=NOW
    )
    # 2026-07-28 is after VISITOR_TRACKING_START and inside the 30-day window.
    quiet = next(row for row in result["daily"] if row["date"] == "2026-07-28")
    assert quiet["page_views"] == 0
    assert quiet["unique_visitors"] == 0


def test_attribution_coverage_is_none_when_there_are_no_signups():
    """'100% coverage' of an empty set reads as healthy when nothing was measured."""
    result = build_conversion_measurement(
        [_page("2026-07-20T10:00:00+00:00", visitor="v1")], [], now=NOW
    )
    assert result["attribution"]["coverage"] is None


def test_signup_last_page_attribution_excludes_unlinkable_signups():
    pages = [
        _page(
            "2026-07-23T10:00:00+00:00",
            page="Pricing",
            visitor="v7",
            session="s7",
        ),
        _page(
            "2026-07-23T10:30:00+00:00",
            page="Ticker Deep Dive",
            visitor="v7",
            session="s7",
        ),
        # A later identified view supplies the otherwise-missing signup link.
        _page(
            "2026-07-23T11:15:00+00:00",
            page="Account Setup",
            visitor="v7",
            session="s7",
            user_id=7,
        ),
    ]
    signups = [
        _signup("2026-07-23T11:00:00+00:00", user_id=7),
        _signup("2026-07-24T11:00:00+00:00", user_id=8),
    ]

    attribution = build_conversion_measurement(pages, signups, now=NOW)["attribution"]

    assert attribution["pages"] == [{"page": "Ticker Deep Dive", "signups": 1}]
    assert attribution["attributed_count"] == 1
    assert attribution["unattributed_count"] == 1
    assert attribution["coverage"] == 50.0
    assert "signup_completed" in attribution["schema_gap"]
    assert "last_page" in attribution["smallest_addition"]


def test_redesign_boundary_is_explicit_and_post_period_is_not_backfilled():
    pages = [
        _page("2026-07-18T10:00:00+00:00", visitor="pre", session="pre"),
        _page("2026-07-26T10:00:00+00:00", visitor="roll", session="roll"),
        _page("2026-08-05T10:00:00+00:00", visitor="post", session="post"),
    ]
    result = build_conversion_measurement(
        pages,
        [],
        now=datetime(2026, 8, 10, 18, 0, tzinfo=timezone.utc),
    )
    phases = {row["phase"] for row in result["weekly"]}

    assert result["redesign_start"] == "2026-07-25"
    assert result["redesign_end"] == "2026-07-28"
    assert {"Pre-redesign", "Redesign rollout overlap", "Post-redesign"} <= phases


def test_admin_conversion_view_uses_only_shared_svg_charts():
    source = Path("pages/38_Admin.py").read_text(encoding="utf-8")
    conversion_view = source.split(
        "def _render_conversion_measurement", 1
    )[1].split("# ── Load data", 1)[0]

    assert "ua_charts.CHART_CSS" in conversion_view
    assert "ua_charts.bar_v" in conversion_view
    assert "ua_charts.bar_h" in conversion_view
    assert "plotly" not in conversion_view.lower()
    assert "Stored-schema limit" in conversion_view
    assert "No values were substituted" in source
