# utils/growth_metrics.py
# Unstructured Alpha — is it growing? Week by week, from analytics_events.
#
# One table, one row per ISO week (Monday start), and a verdict that compares
# the last four complete weeks with the four before them. Read by
# scripts/usage_report.py; pure functions, so the arithmetic is tested offline.
#
# WHAT EACH COLUMN COUNTS
#   site_visitors  distinct visitors on the public site (landing + free tools)
#   tool_views     page views of the free tools (public pages other than Landing)
#   app_visitors   distinct visitors in the app
#   from_tools     distinct app visitors who arrived from a public page
#                  (utm_source=public_tools on their app page view)
#   crossed        distinct visitors seen on the public site AND in the app that
#                  week -- the same visitor_id, by design (seo/track_api.py)
#   app_opens      clicks on the landing's app buttons (app_opened events)
#   signups        accounts created
#
# RULES
#   * Distinct visitors, never raw rows, for anything called "visitors".
#   * The week in progress is shown but left out of the verdict: a partial week
#     always looks like a decline.
#   * Too little data is said plainly ("not enough data"), never dressed up
#     as a trend.

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

COLUMNS = ("site_visitors", "tool_views", "app_visitors", "from_tools", "crossed", "app_opens", "signups")
VERDICT_ON = ("site_visitors", "from_tools", "crossed", "signups")


def week_of(ts) -> Optional[date]:
    """The Monday of the ISO week a timestamp falls in (text or datetime)."""
    try:
        d = ts if isinstance(ts, (datetime, date)) else datetime.fromisoformat(str(ts)[:19])
    except ValueError:
        return None
    d = d.date() if isinstance(d, datetime) else d
    return d - timedelta(days=d.weekday())


def _props(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        v = json.loads(raw or "{}")
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


def weekly(events: Iterable[Tuple], signups: Iterable = (), weeks: int = 8,
           today: Optional[date] = None) -> List[dict]:
    """events: (event_name, created_at, visitor_id, properties) rows.
    signups: created_at of each account. Returns the last `weeks` ISO weeks,
    oldest first, each {"week": date, "partial": bool, <COLUMNS>: int}."""
    today = today or date.today()
    this_week = today - timedelta(days=today.weekday())
    starts = [this_week - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    sets: Dict[date, Dict[str, set]] = {w: {"site": set(), "app": set(), "tools": set()} for w in starts}
    counts: Dict[date, Dict[str, int]] = {w: {"tool_views": 0, "app_opens": 0, "signups": 0} for w in starts}
    for name, ts, visitor, raw in events:
        w = week_of(ts)
        if w not in sets:
            continue
        p = _props(raw)
        marketing = p.get("site") == "marketing"
        if name == "app_opened":
            counts[w]["app_opens"] += marketing
            continue
        if name != "page_view":
            continue
        if marketing:
            if visitor:
                sets[w]["site"].add(visitor)
            counts[w]["tool_views"] += p.get("page") not in ("Landing", None)
        elif visitor:
            sets[w]["app"].add(visitor)
            if p.get("utm_source") == "public_tools":
                sets[w]["tools"].add(visitor)
    for ts in signups:
        w = week_of(ts)
        if w in counts:
            counts[w]["signups"] += 1
    return [{"week": w, "partial": w == this_week,
             "site_visitors": len(sets[w]["site"]), "tool_views": counts[w]["tool_views"],
             "app_visitors": len(sets[w]["app"]), "from_tools": len(sets[w]["tools"]),
             "crossed": len(sets[w]["site"] & sets[w]["app"]),
             "app_opens": counts[w]["app_opens"], "signups": counts[w]["signups"]}
            for w in starts]


def verdict(rows: List[dict], span: int = 4) -> Dict[str, str]:
    """For each headline column: the last `span` complete weeks against the
    `span` before, as 'growing +N%', 'flat', 'shrinking -N%', or
    'not enough data' when either half is all zeros or too short."""
    done = [r for r in rows if not r["partial"]]
    out = {}
    for col in VERDICT_ON:
        if len(done) < 2 * span:
            out[col] = "not enough data"
            continue
        now = sum(r[col] for r in done[-span:])
        before = sum(r[col] for r in done[-2 * span:-span])
        if before == 0:
            out[col] = "not enough data" if now == 0 else f"new: {now} in {span} weeks, none before"
            continue
        change = 100 * (now - before) / before
        out[col] = ("flat" if abs(change) < 5 else
                    f"growing +{change:.0f}%" if change > 0 else f"shrinking {change:.0f}%")
    return out


def table(rows: List[dict]) -> str:
    head = "  week of     " + "".join(f"{c:>14s}" for c in COLUMNS)
    lines = [head]
    for r in rows:
        lines.append(f"  {r['week'].isoformat()}{'*' if r['partial'] else ' '}  "
                     + "".join(f"{r[c]:>14d}" for c in COLUMNS))
    lines.append("  * week in progress: shown, left out of the verdict")
    return "\n".join(lines)
