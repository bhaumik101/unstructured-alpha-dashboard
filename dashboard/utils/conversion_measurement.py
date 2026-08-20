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

# Visits are reconstructed per visitor from this inactivity gap rather than read
# from Streamlit's session_id. 30 minutes is the long-standing web-analytics
# convention, chosen here so the number is comparable to any external tool the
# owner comes to rely on.
VISIT_INACTIVITY_GAP = timedelta(minutes=30)

# Visitor identity began recording on this date. Before it, no per-person metric
# is reconstructable from stored evidence, so those metrics are withheld.
VISITOR_TRACKING_START = date(2026, 7, 27)


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
        # An empty period is only a measured zero if identity was recording then.
        # Before VISITOR_TRACKING_START nothing was captured, so "0 visitors" would
        # assert an absence of traffic that was never observed -- the week of
        # 2026-07-06 otherwise rendered as 0 visitors alongside 2 real signups.
        exact = len(identified) == len(rows) and (
            bool(rows) or day >= VISITOR_TRACKING_START
        )
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
        # Same rule as the daily rows: an empty week only counts as a measured
        # zero once visitor identity was actually being recorded.
        exact_identity = len(identified) == len(week_pages) and (
            bool(week_pages) or max(week_days) >= VISITOR_TRACKING_START
        )
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

    # Sessionise by VISITOR with an inactivity gap, never by session_id.
    #
    # session_id is a Streamlit connection id, not a user session. It is reset by
    # every full browser navigation, and until PR #103 the top nav was raw <a href>
    # markup, so every nav click started a new one. Measured on real stored data:
    # one visitor produced 86 distinct session_ids across 89 page views, and 96%
    # of all sessions contained exactly one page view. Grouping by session_id
    # therefore reports an engaged reader as ~86 separate bounces.
    #
    # PR #103 made navigation client-side, so session_id now survives a nav click.
    # A bounce rate built on it would appear to improve dramatically on that date
    # while user behaviour was unchanged -- a performance fix masquerading as an
    # engagement win. That is precisely the kind of number this product must not
    # publish, internally or otherwise.
    bounce_unavailable_reason: str | None = None
    identified_pages = [row for row in pages if row["visitor_id"]]
    page_views_without_visitor = len(pages) - len(identified_pages)

    visits: dict[str, list[dict]] = defaultdict(list)
    for row in identified_pages:
        visits[row["visitor_id"]].append(row)

    landing_sessions: list[list[dict]] = []
    for rows in visits.values():
        ordered = sorted(rows, key=lambda row: row["created_at"])
        current_visit: list[dict] = []
        for row in ordered:
            if (
                current_visit
                and row["created_at"] - current_visit[-1]["created_at"]
                > VISIT_INACTIVITY_GAP
            ):
                landing_sessions.append(current_visit)
                current_visit = []
            current_visit.append(row)
        if current_visit:
            landing_sessions.append(current_visit)

    landing_sessions = [
        visit
        for visit in landing_sessions
        if visit[0]["page"].strip().lower() in {"home", "landing"}
    ]
    one_page_sessions = sum(len(rows) == 1 for rows in landing_sessions)
    multi_page_sessions = sum(len(rows) > 1 for rows in landing_sessions)
    landing_total = len(landing_sessions)

    if page_views_without_visitor:
        # Visitor identity only began recording on 2026-07-27. Reconstructing
        # visits for earlier traffic is not possible, and estimating it would be
        # inventing evidence, so the metric is withheld rather than approximated.
        bounce_unavailable_reason = (
            f"{page_views_without_visitor:,} of {len(pages):,} stored page views "
            "carry no visitor identifier (identity recording began "
            "2026-07-27), so visits cannot be reconstructed for that traffic. "
            "Reported as unavailable rather than estimated."
        )

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
            # Withheld whenever any page view lacks visitor identity: a rate
            # computed over the identified minority would silently describe a
            # different population than the header count suggests.
            "one_page_rate": (
                one_page_sessions / landing_total * 100
                if landing_total and not bounce_unavailable_reason
                else None
            ),
            "unavailable_reason": bounce_unavailable_reason,
            "page_views_without_visitor": page_views_without_visitor,
            "visit_gap_minutes": int(
                VISIT_INACTIVITY_GAP.total_seconds() // 60
            ),
            "identity_coverage": (
                (total_page_views - page_views_without_visitor)
                / total_page_views
                * 100
                if total_page_views
                else 100.0
            ),
            "method": (
                "Visits are reconstructed per visitor using a "
                f"{int(VISIT_INACTIVITY_GAP.total_seconds() // 60)}-minute "
                "inactivity gap. Streamlit's session_id is deliberately NOT used: "
                "it is a connection id that reset on every full page navigation "
                "before PR #103, which would count one engaged reader as dozens "
                "of bounces."
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
            # None, not 100%, when there are no signups. "100% coverage" of an
            # empty set reads as a healthy metric when nothing was measured.
            "coverage": (
                len(attributed_signups) / len(signups) * 100 if signups else None
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


# ── Acquisition funnel ───────────────────────────────────────────────────────
# The admin funnel chart starts at "Signed Up" and is computed from the users
# table, so it shows what happens AFTER someone has an account. The half where a
# 0%-conversion product actually loses people -- visitor to account -- had no
# numbers at all, because the events that measure it were defined and never
# fired. They fire now; this reads them.

ACQUISITION_STEPS: tuple[tuple[str, str], ...] = (
    ("page_view",          "Visited"),
    ("signup_started",     "Started signup"),
    ("signup_completed",   "Verified email"),
    ("pricing_viewed",     "Viewed pricing"),
    ("checkout_started",   "Started checkout"),
    ("checkout_completed", "Subscribed"),
)


def build_acquisition_funnel(event_rows: Iterable[dict]) -> dict:
    """Count the visitor-to-subscriber steps from stored events.

    Returns {"instrumented": bool, "first_seen": str|None, "steps": [...]}.

    A step counts DISTINCT visitors, not events: one person reloading the
    pricing page five times is one person who saw pricing, and counting the
    reloads would make the step above checkout look healthier than it is.

    `instrumented` distinguishes "nobody did this" from "nothing recorded it".
    Every step below page_view was unmeasured until the events were wired, so
    rendering a confident 0 for a period that predates the instrumentation
    would be the same misleading certainty this module already refuses
    elsewhere -- see VISITOR_TRACKING_START above.
    """
    names = {name for name, _ in ACQUISITION_STEPS}
    seen: dict[str, set[str]] = {name: set() for name in names}
    first_seen: str | None = None
    funnel_names = names - {"page_view"}

    for row in event_rows:
        name = row.get("event_name")
        if name not in names:
            continue
        who = row.get("visitor_id") or (
            f"user:{row['user_id']}" if row.get("user_id") is not None else None
        )
        if who:
            seen[name].add(str(who))
        if name in funnel_names:
            created = row.get("created_at")
            stamp = created.isoformat() if isinstance(created, datetime) else str(created or "")
            if stamp and (first_seen is None or stamp < first_seen):
                first_seen = stamp

    steps = []
    top = len(seen["page_view"])
    prev: int | None = None
    for name, label in ACQUISITION_STEPS:
        count = len(seen[name])
        steps.append({
            "event": name,
            "label": label,
            "count": count,
            # Share of the top of the funnel, and of the step immediately above.
            # The second is what names the step that is actually losing people.
            "pct_of_top": round(100 * count / top, 1) if top else None,
            "pct_of_prev": round(100 * count / prev, 1) if prev else None,
        })
        prev = count if count else None

    # Which step to point at. NOT the lowest retention percentage: on a real
    # funnel the tail is tiny, so "Subscribed kept 0% of 1 person" wins that
    # contest and says nothing. Measured on the live shape -- 190 visits, 11
    # signups, 4 verified, 3 pricing, 1 checkout, 0 paid -- lowest-percentage
    # named Subscribed while the funnel actually loses 179 people at the first
    # step.
    #
    # Absolute people lost is what a founder can act on, and it is robust to a
    # denominator of one.
    biggest_drop = None
    prev_count = None
    for step in steps:
        if prev_count is not None:
            lost = prev_count - step["count"]
            if lost > 0 and (biggest_drop is None or lost > biggest_drop["lost"]):
                biggest_drop = {
                    "label": step["label"],
                    "event": step["event"],
                    "lost": lost,
                    "pct_of_prev": step["pct_of_prev"],
                }
        prev_count = step["count"]

    return {
        "instrumented": first_seen is not None,
        "first_seen": first_seen,
        "steps": steps,
        "biggest_drop": biggest_drop,
    }


def load_acquisition_rows(*, days: int = 30, now: datetime | None = None) -> list[dict]:
    """Read the events the acquisition funnel is built from."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = datetime.combine(
        current.date() - timedelta(days=days - 1), time.min, tzinfo=timezone.utc
    ).isoformat()
    names = [name for name, _ in ACQUISITION_STEPS]
    with engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                select(
                    analytics_events.c.event_name,
                    analytics_events.c.visitor_id,
                    analytics_events.c.user_id,
                    analytics_events.c.created_at,
                ).where(
                    analytics_events.c.event_name.in_(names),
                    analytics_events.c.created_at >= cutoff,
                )
            ).mappings()
        ]
