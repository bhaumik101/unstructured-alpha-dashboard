"""Read-only usage report against the live database.

Answers "how much is this actually used, and how well" from analytics_events,
users, watchlist and onboarding_progress. Prints only aggregates — no emails,
no tokens, no per-user identifiers.

    python scripts/usage_report.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env.render")

# Same driver pinning as utils/db.py: SQLAlchemy 2.1 reads a bare
# postgresql:// as psycopg 3, which is not installed.
_url = os.environ["DATABASE_URL"]
for _bare in ("postgresql://", "postgres://"):
    if _url.startswith(_bare):
        _url = "postgresql+psycopg2://" + _url[len(_bare):]
ENGINE = create_engine(_url, pool_pre_ping=True)

NOW = datetime.now(timezone.utc)


def q(sql: str, **params):
    with ENGINE.connect() as conn:
        return conn.execute(text(sql), params).fetchall()


def ago(days: int) -> str:
    return (NOW - timedelta(days=days)).isoformat()


def pct(sorted_vals, p: float):
    return sorted_vals[min(int(len(sorted_vals) * p), len(sorted_vals) - 1)] if sorted_vals else 0


def section(title: str):
    print(f"\n{'=' * 66}\n{title}\n{'=' * 66}")


section("TABLE SIZES")
for tbl in ("users", "analytics_events", "watchlist", "alerts", "score_snapshots",
            "prediction_log", "onboarding_progress", "referrals", "score_components"):
    try:
        print(f"  {tbl:24s} {q(f'select count(*) from {tbl}')[0][0]:>8}")
    except Exception as exc:
        print(f"  {tbl:24s} ERROR {str(exc)[:50]}")

section("USERS")
try:
    r = q("""select count(*),
                    count(*) filter (where subscription_tier = 'pro'),
                    count(*) filter (where created_at >= :d7),
                    count(*) filter (where created_at >= :d30),
                    min(created_at), max(created_at)
             from users""", d7=ago(7), d30=ago(30))[0]
    print(f"  total={r[0]}  pro={r[1]}  new_7d={r[2]}  new_30d={r[3]}")
    print(f"  first signup: {str(r[4])[:19]}   latest: {str(r[5])[:19]}")
except Exception as exc:
    print(f"  ERROR {exc}")

section("DAILY ACTIVITY (last 21 days)")
try:
    rows = q("""select substr(created_at, 1, 10) d, count(*),
                       count(distinct session_id), count(distinct user_id)
                from analytics_events where created_at >= :d
                group by 1 order by 1 desc""", d=ago(21))
    if not rows:
        print("  (no events in window)")
    for d, n, s, u in rows:
        print(f"  {d}   events={n:>6}   sessions={s:>5}   signed-in users={u:>4}")
except Exception as exc:
    print(f"  ERROR {exc}")

section("TOP EVENTS (all time)")
try:
    for name, n, s in q("""select event_name, count(*), count(distinct session_id)
                           from analytics_events group by 1 order by 2 desc limit 30"""):
        print(f"  {str(name)[:40]:42s} {n:>7}   sessions={s}")
except Exception as exc:
    print(f"  ERROR {exc}")

section("PAGE VIEWS BY PAGE")
try:
    counts: dict[str, int] = {}
    for props, n in q("""select properties, count(*) from analytics_events
                         where event_name = 'page_view' group by 1"""):
        try:
            page = json.loads(props or "{}").get("page", "(unknown)")
        except Exception:
            page = "(unparseable)"
        counts[str(page)] = counts.get(str(page), 0) + n
    for page, n in sorted(counts.items(), key=lambda kv: -kv[1])[:30]:
        print(f"  {page[:44]:46s} {n:>7}")
    if not counts:
        print("  (no page_view events)")
except Exception as exc:
    print(f"  ERROR {exc}")

section("SESSION DEPTH AND DURATION")
try:
    rows = q("""select session_id, min(created_at), max(created_at), count(*)
                from analytics_events where session_id is not null group by 1""")
    durations, depths = [], []
    for _sid, a, b, n in rows:
        depths.append(n)
        try:
            ta = datetime.fromisoformat(str(a).replace("Z", "+00:00"))
            tb = datetime.fromisoformat(str(b).replace("Z", "+00:00"))
            durations.append((tb - ta).total_seconds())
        except Exception:
            pass
    durations.sort()
    depths.sort()
    if durations:
        print(f"  sessions with events: {len(rows)}")
        print(f"  duration   median={pct(durations, .5):>7.0f}s   "
              f"p75={pct(durations, .75):>7.0f}s   p90={pct(durations, .9):>7.0f}s   "
              f"max={max(durations):>7.0f}s")
        print(f"  events/session  median={pct(depths, .5)}   p90={pct(depths, .9)}   "
              f"max={max(depths)}")
        short = sum(1 for d in durations if d < 10)
        one = sum(1 for d in depths if d == 1)
        print(f"  sessions under 10s: {short}/{len(durations)} = "
              f"{short / len(durations) * 100:.1f}%")
        print(f"  single-event sessions: {one}/{len(depths)} = "
              f"{one / len(depths) * 100:.1f}%")
    else:
        print("  (no sessions)")
except Exception as exc:
    print(f"  ERROR {exc}")

section("ACTIVATION")
try:
    total = q("select count(*) from users")[0][0]
    wl = q("select count(distinct user_id) from watchlist")[0][0]
    print(f"  users with at least one watchlist ticker: {wl}/{total}"
          + (f" = {wl / total * 100:.1f}%" if total else ""))
    rows = q("""select step_id, count(distinct user_id) from onboarding_progress
                group by 1 order by 2 desc""")
    for step, n in rows:
        print(f"  onboarding · {str(step):26s} {n}")
    if not rows:
        print("  onboarding: no rows recorded")
except Exception as exc:
    print(f"  ERROR {exc}")

section("SCORE SNAPSHOT COVERAGE")
try:
    for kind, n, t, d0, d1 in q("""select score_kind, count(*), count(distinct ticker),
                                          min(snapshot_date), max(snapshot_date)
                                   from score_snapshots group by 1 order by 2 desc"""):
        print(f"  {str(kind):18s} rows={n:>7}  tickers={t:>6}  {d0} .. {d1}")
except Exception as exc:
    print(f"  ERROR {exc}")

print()
