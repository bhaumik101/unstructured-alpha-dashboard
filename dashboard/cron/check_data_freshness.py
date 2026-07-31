"""Fail loudly when a data pipeline stops writing.

Why this exists: on 2026-07-31 a routine performance check found that
score_snapshots had not been written since 2026-07-21 -- ten days. The Screener
and every ticker Confluence Score had been served from stale data that whole
time, and nothing anywhere said so. signal_snapshots was fine, which is exactly
why it went unnoticed: the site looked alive.

For a product whose entire claim is data integrity, silently serving ten-day-old
scores is worse than being down. Down is obvious.

This runs daily and exits non-zero when any tracked table is older than its
threshold, so Render marks the cron failed and surfaces it instead of it
decaying quietly. It writes nothing and reads only max(snapshot_date).
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta, timezone

# Each entry: table -> (date column, max age in days, why that number).
#
# Thresholds are deliberately a little looser than the cron cadence so a single
# skipped run is not treated as an outage; they catch a pipeline that has
# actually stopped, not one that hiccupped.
CHECKS: dict[str, tuple[str, int, str]] = {
    "signal_snapshots": (
        "snapshot_date",
        2,
        "written daily by the scoring cron; 2 days tolerates one missed run",
    ),
    "score_snapshots": (
        "snapshot_date",
        4,
        "score-core runs daily and score-rest Mon/Wed/Fri; 4 days spans the "
        "widest legitimate gap",
    ),
    "analytics_events": (
        "created_at",
        3,
        "any real traffic writes here; silence means tracking broke, which is "
        "how the funnel became unmeasurable before",
    ),
}


def _newest(conn, table: str, column: str):
    """Return the newest value in `column`, or None.

    created_at is stored as character varying on analytics_events, so the cast
    is required -- comparing a varchar to a timestamp raises rather than
    returning nothing, which would look like an empty table.
    """
    from sqlalchemy import text

    row = conn.execute(
        text(f"SELECT max({column}::timestamptz) FROM {table}")
    ).scalar()
    return row


def main() -> int:
    from sqlalchemy import text  # noqa: F401  (imported for _newest)

    from utils.db import engine

    today = datetime.now(timezone.utc).date()
    stale: list[str] = []
    missing: list[str] = []
    ok: list[str] = []

    with engine.connect() as conn:
        for table, (column, max_age_days, reason) in CHECKS.items():
            try:
                newest = _newest(conn, table, column)
            except Exception as exc:
                # A table that cannot be read is a failure, not a pass. Treating
                # an error as "fine" is how a broken pipeline stays invisible.
                missing.append(f"{table}: unreadable ({type(exc).__name__}: {exc})")
                continue

            if newest is None:
                missing.append(f"{table}: empty")
                continue

            newest_date = newest.date() if isinstance(newest, datetime) else newest
            age = (today - newest_date).days
            line = f"{table:<20} newest={newest_date}  age={age}d  limit={max_age_days}d"
            if age > max_age_days:
                stale.append(f"{line}   <-- STALE ({reason})")
            else:
                ok.append(line)

    print("[freshness] checked at " + datetime.now(timezone.utc).isoformat(), flush=True)
    for line in ok:
        print(f"[freshness] OK      {line}", flush=True)
    for line in stale:
        print(f"[freshness] STALE   {line}", flush=True)
    for line in missing:
        print(f"[freshness] MISSING {line}", flush=True)

    if stale or missing:
        print(
            f"[freshness] FAILED — {len(stale)} stale, {len(missing)} missing. "
            "A pipeline has stopped writing; the app is serving old data.",
            flush=True,
        )
        return 1

    print(f"[freshness] PASS — all {len(ok)} tracked tables current.", flush=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
