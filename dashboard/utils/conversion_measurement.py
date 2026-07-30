"""Real-data conversion measurement for the admin dashboard.

The functions in this module deliberately distinguish zero from unavailable.
An old page view without the visitor identity added in PR #70 is not silently
counted as a new visitor, and a weekly conversion rate is only emitted when
every recorded page view in that week has an identity.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

from sqlalchemy import select

from utils.db import analytics_events, engine, users


REDESIGN_START = date(2026, 7, 25)
REDESIGN_END = date(2026, 7, 28)


def _as_utc(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _page_name(properties: object) -> str:
    if isinstance(properties, dict):
        payload = properties
    else:
        try:
            payload = json.loads(str(properties or "{}")) or {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return "Unknown page"
    return str(payload.get("page") or "Unknown page")


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _phase_for_week(start: date) -> str:
    end = start + timedelta(days=6)
    if end < REDESIGN_START:
        return "Pre-redesign"
    if start > REDESIGN_END:
        return "Post-redesign"
    return "Redesign rollout overlap"


def load_conversion_rows(
    *,
    now: datetime | None = None,
) -> tuple[list[dict], list[dict]]:
    """Read the bounded page-view and signup rows used by the measurement."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start_day = current.date() - timedelta(days=29)
    cutoff = datetime.combine(start_day, time.min, tzinfo=timezone.utc).isoformat()

    with engine.connect() as conn:
        page_rows = [
            dict(row)
            for row in conn.execute(
                select(
                    analytics_events.c.visitor_id,
                    analytics_events.c.session_id,
                    analytics_events.c.user_id,
                    analytics_events.c.properties,
                    analytics_events.c.created_at,
                ).where(
                    analytics_events.c.event_name == "page_view",
                    analytics_events.c.created_at >= cutoff,
                )
            ).mappings()
        ]
        signup_rows = [
            dict(row)
            for row in conn.execute(
                select(users.c.id, users.c.created_at).where(
                    users.c.created_at >= cutoff
                )
            ).mappings()
        ]
    return page_rows, signup_rows


def build_conversion_measurement(
    page_rows: Iterable[dict],
    signup_rows: Iterable[dict],
    *,
    now: datetime | None = None,
) -> dict:
    """Build the five requested conversion measures without filling data gaps."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start_day = current.date() - timedelta(days=29)
    days = [start_day + timedelta(days=offset) for offset in range(30)]

    pages: list[dict] = []
    invalid_page_timestamps = 0
    for raw in page_rows:
        created_at = _as_utc(raw.get("created_at"))
        if created_at is None:
            invalid_page_timestamps += 1
            continue
        if not start_day <= created_at.date() <= current.date():
            continue
        pages.append(
            {
                "visitor_id": str(raw.get("visitor_id") or "") or None,
                "session_id": str(raw.get("session_id") or "") or None,
                "user_id": raw.get("user_id"),
                "page": _page_name(raw.get("properties")),
                "created_at": created_at,
            }
        )

    signups: list[dict] = []
    invalid_signup_timestamps = 0
    for raw in signup_rows:
        created_at = _as_utc(raw.get("created_at"))
        if created_at is None:
            invalid_signup_timestamps += 1
            continue
        if not start_day <= created_at.date() <= current.date():
            continue
        signups.append({"id": raw.get("id"), "created_at": created_at})

    pages_by_day: dict[date, list[dict]] = defaultdict(list)
    signups_by_day: Counter[date] = Counter()
    for row in pages:
        pages_by_day[row["created_at"].date()].append(row)
    for row in signups:
        signups_by_day[row["created_at"].date()] += 1

    daily = []
    for day in days:
        rows = pages_by_day[day]
        identified = [row for row in rows if row["visitor_id"]]
        exact = len(identified) == len(rows)
        daily.append(
            {
                "date": day.isoformat(),
                "page_views": len(rows),
                "identified_page_views": len(identified),
                "excluded_page_views": len(rows) - len(identified),
                "identity_coverage": (
                    len(identified) / len(rows) * 100 if rows else 100.0
                ),
                "unique_visitors": (
                    len({row["visitor_id"] for row in identified}) if exact else None
                ),
                "identified_visitors": len(
                    {row["visitor_id"] for row in identified}
                ),
                "signups": signups_by_day[day],
            }
        )

    week_starts = sorted({_week_start(day) for day in days})
    weekly = []
    for week in week_starts:
        week_days = {
            week + timedelta(days=offset)
            for offset in range(7)
            if start_day <= week + timedelta(days=offset) <= current.date()
        }
        week_pages = [
            row for row in pages if row["created_at"].date() in week_days
        ]
        identified = [row for row in week_pages if row["visitor_id"]]
        visitors = {row["visitor_id"] for row in identified}
        signup_count = sum(signups_by_day[day] for day in week_days)
        exact_identity = len(identified) == len(week_pages)
        conversion = (
            signup_count / len(visitors) * 100
            if exact_identity and visitors
            else None
        )
        weekly.append(
            {
                "week_start": week.isoformat(),
                "week_end": min(
                    week + timedelta(days=6), current.date()
                ).isoformat(),
                "phase": _phase_for_week(week),
                "unique_visitors": len(visitors) if exact_identity else None,
                "identified_visitors": len(visitors),
                "signups": signup_count,
                "conversion_rate": conversion,
                "identity_coverage": (
                    len(identified) / len(week_pages) * 100
                    if week_pages
                    else 100.0
                ),
                "excluded_page_views": len(week_pages) - len(identified),
            }
        )

    sessions: dict[str, list[dict]] = defaultdict(list)
    page_views_without_session = 0
    for row in pages:
        if row["session_id"]:
            sessions[row["session_id"]].append(row)
        else:
            page_views_without_session += 1
    landing_sessions = []
    for rows in sessions.values():
        ordered = sorted(rows, key=lambda row: row["created_at"])
        if ordered and ordered[0]["page"].strip().lower() in {"home", "landing"}:
            landing_sessions.append(ordered)
    one_page_sessions = sum(len(rows) == 1 for rows in landing_sessions)
    multi_page_sessions = sum(len(rows) > 1 for rows in landing_sessions)
    landing_total = len(landing_sessions)

    user_identity: dict[object, dict[str, set[str]]] = defaultdict(
        lambda: {"sessions": set(), "visitors": set()}
    )
    for row in pages:
        if row["user_id"] is None:
            continue
        if row["session_id"]:
            user_identity[row["user_id"]]["sessions"].add(row["session_id"])
        if row["visitor_id"]:
            user_identity[row["user_id"]]["visitors"].add(row["visitor_id"])

    attributed_pages: Counter[str] = Counter()
    attributed_signups = []
    for signup in signups:
        identity = user_identity.get(signup["id"])
        if not identity:
            continue
        candidates = [
            row
            for row in pages
            if row["created_at"] <= signup["created_at"]
            and (
                (
                    row["session_id"]
                    and row["session_id"] in identity["sessions"]
                )
                or (
                    row["visitor_id"]
                    and row["visitor_id"] in identity["visitors"]
                )
            )
        ]
        if not candidates:
            continue
        latest = max(candidates, key=lambda row: row["created_at"])
        attributed_pages[latest["page"]] += 1
        attributed_signups.append(
            {
                "user_id": signup["id"],
                "signup_at": signup["created_at"].isoformat(),
                "last_page": latest["page"],
            }
        )

    total_page_views = len(pages)
    identified_page_views = sum(bool(row["visitor_id"]) for row in pages)
    all_visitors = {
        row["visitor_id"] for row in pages if row["visitor_id"]
    }
    full_identity_coverage = identified_page_views == total_page_views
    conversion_30d = (
        len(signups) / len(all_visitors) * 100
        if full_identity_coverage and all_visitors
        else None
    )

    return {
        "window_start": start_day.isoformat(),
        "window_end": current.date().isoformat(),
        "redesign_start": REDESIGN_START.isoformat(),
        "redesign_end": REDESIGN_END.isoformat(),
        "daily": daily,
        "weekly": weekly,
        "bounce": {
            "landing_sessions": landing_total,
            "one_page_sessions": one_page_sessions,
            "multi_page_sessions": multi_page_sessions,
            "one_page_rate": (
                one_page_sessions / landing_total * 100 if landing_total else None
            ),
            "page_views_without_session": page_views_without_session,
            "session_coverage": (
                (total_page_views - page_views_without_session)
                / total_page_views
                * 100
                if total_page_views
                else 100.0
            ),
        },
        "attribution": {
            "pages": [
                {"page": page, "signups": count}
                for page, count in attributed_pages.most_common()
            ],
            "attributed_signups": attributed_signups,
            "attributed_count": len(attributed_signups),
            "unattributed_count": len(signups) - len(attributed_signups),
            "coverage": (
                len(attributed_signups) / len(signups) * 100 if signups else 100.0
            ),
            "schema_gap": (
                "Signup rows do not store visitor_id, session_id, or last_page, "
                "and signup_completed is declared but never recorded. Attribution "
                "therefore includes only signups linkable through a later identified "
                "page view; all others are excluded."
            ),
            "smallest_addition": (
                "Record one signup_completed event with user_id, visitor_id, "
                "session_id, and last_page when account creation commits."
            ),
        },
        "totals": {
            "page_views": total_page_views,
            "identified_page_views": identified_page_views,
            "excluded_page_views": total_page_views - identified_page_views,
            "identity_coverage": (
                identified_page_views / total_page_views * 100
                if total_page_views
                else 100.0
            ),
            "unique_visitors": (
                len(all_visitors) if full_identity_coverage else None
            ),
            "identified_visitors": len(all_visitors),
            "signups": len(signups),
            "conversion_rate": conversion_30d,
        },
        "excluded": {
            "invalid_page_timestamps": invalid_page_timestamps,
            "invalid_signup_timestamps": invalid_signup_timestamps,
        },
    }
