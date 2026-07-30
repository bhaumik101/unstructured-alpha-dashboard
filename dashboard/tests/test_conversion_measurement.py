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


def test_landing_bounce_proxy_counts_only_sessions_entering_on_home():
    pages = [
        _page("2026-07-20T10:00:00+00:00", session="one", visitor="v1"),
        _page("2026-07-20T11:00:00+00:00", session="multi", visitor="v2"),
        _page(
            "2026-07-20T11:05:00+00:00",
            session="multi",
            visitor="v2",
            page="Ticker Deep Dive",
        ),
        _page(
            "2026-07-20T12:00:00+00:00",
            session="deep-link",
            visitor="v3",
            page="About",
        ),
        _page(
            "2026-07-20T13:00:00+00:00",
            session=None,
            visitor="v4",
        ),
    ]
    bounce = build_conversion_measurement(pages, [], now=NOW)["bounce"]

    assert bounce["landing_sessions"] == 2
    assert bounce["one_page_sessions"] == 1
    assert bounce["multi_page_sessions"] == 1
    assert bounce["one_page_rate"] == 50.0
    assert bounce["page_views_without_session"] == 1


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
