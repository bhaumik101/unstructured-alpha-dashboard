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
from datetime import datetime, timezone

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
    "macro_narratives": (
        "note_date",
        9,
        "the weekly brief; generated Sundays, so 9 days catches a week that "
        "produced nothing before subscribers are mailed a repeat",
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


def _db_target(engine) -> str:
    """host/dbname of the database being read. Never credentials.

    Thin wrapper over utils.db.db_target so the writer (score_universe) and the
    reader (this module) report the target in an identical format -- comparing
    two log lines only works if they are the same shape.
    """
    from utils.db import db_target

    return db_target(engine)


def _wrong_database(engine) -> str | None:
    """Return a reason string when the engine is not the production Postgres.

    The first scheduled run failed with three "unreadable" tables and reported
    that a pipeline had stopped writing. It had not. DATABASE_URL was never set
    on the new Render service (render.yaml declares it `sync: false`, which means
    "set this by hand"), so utils.db fell back to a local SQLite file where the
    Postgres-only ::timestamptz cast is a syntax error.

    A monitor that misdiagnoses is worse than no monitor -- it teaches you to
    ignore its alerts. Checking the dialect first keeps "we cannot reach the
    database" separate from "the pipeline stopped writing". Both still fail; only
    the message differs.
    """
    dialect = engine.dialect.name
    if dialect != "postgresql":
        return (
            f"connected to '{dialect}', not the production Postgres. "
            "DATABASE_URL is unset or unreachable for this service"
        )
    return None


def main() -> int:
    from utils.db import engine

    today = datetime.now(timezone.utc).date()
    stale: list[str] = []
    missing: list[str] = []
    ok: list[str] = []

    misconfigured = _wrong_database(engine)
    if misconfigured:
        print("[freshness] checked at " + datetime.now(timezone.utc).isoformat(), flush=True)
        print(f"[freshness] CONFIG  {misconfigured}", flush=True)
        print(
            "[freshness] FAILED — configuration error, not a data problem. "
            "Freshness was NOT verified; set DATABASE_URL on this service and "
            "re-run before drawing any conclusion about the pipelines.",
            flush=True,
        )
        return 1

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
    print(f"[freshness] reading  db={_db_target(engine)}", flush=True)
    for line in ok:
        print(f"[freshness] OK      {line}", flush=True)
    for line in stale:
        print(f"[freshness] STALE   {line}", flush=True)
    for line in missing:
        print(f"[freshness] MISSING {line}", flush=True)

    if stale or missing:
        # Say only what was actually observed. Stale means a writer has fallen
        # behind its threshold; unreadable/empty means the check could not reach
        # the data at all, which has other causes (a renamed table, a permission
        # change) and should not be reported as a stalled pipeline.
        parts = []
        if stale:
            parts.append(
                f"{len(stale)} table(s) stopped advancing — a writer is behind"
            )
        if missing:
            parts.append(
                f"{len(missing)} table(s) unreadable or empty — cause not established"
            )
        print(f"[freshness] FAILED — {'; '.join(parts)}.", flush=True)
        return 1

    print(f"[freshness] PASS — all {len(ok)} tracked tables current.", flush=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
