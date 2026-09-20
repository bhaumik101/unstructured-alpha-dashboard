# utils/report_cache.py
# Unstructured Alpha — computed exposure reports, cached across processes
#
# WHY
# ---
# Measuring a portfolio costs ~25 seconds: three years of weekly prices for
# every holding plus six economic series, then the regressions. st.cache_data
# makes the SECOND view instant, but only inside one Python process — a deploy,
# a restart, or a second Render instance drops it, and the next visitor waits
# again for work someone already did.
#
# This is that cache, in the database the app already has. It is a cache and
# nothing more:
#   * a miss is never an error — the caller just computes
#   * a write failure is never an error — the report is already in hand
#   * only successful reports are stored, so an outage is retried, not served
#
# Rows are keyed by the normalized portfolio (tickers, weights, holding cap),
# so two people with the same holdings share one computation.

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select

from utils import db
from utils.db import report_cache

TTL_HOURS = 6
MAX_ROWS = 500


def cache_key(key: tuple, max_holdings: int) -> str:
    """One key per (portfolio, holding cap). Stable across processes."""
    payload = json.dumps({"holdings": [list(item) for item in key], "max": int(max_holdings)},
                         sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fresh_after() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=TTL_HOURS)).isoformat()


def get(key: tuple, max_holdings: int) -> Optional[dict]:
    """The stored report, or None. Never raises: a cache miss is not an error."""
    try:
        with db.engine.begin() as conn:
            row = conn.execute(
                select(report_cache.c.payload)
                .where(report_cache.c.cache_key == cache_key(key, max_holdings))
                .where(report_cache.c.created_at >= _fresh_after())
            ).first()
        if not row:
            return None
        report = json.loads(row[0])
        return report if isinstance(report, dict) and report.get("status") == "ok" else None
    except Exception:
        return None


def put(key: tuple, max_holdings: int, report: dict) -> bool:
    """Store a successful report. Returns False rather than raising."""
    if not isinstance(report, dict) or report.get("status") != "ok":
        return False
    try:
        values = {
            "cache_key": cache_key(key, max_holdings),
            "as_of": str(report.get("as_of") or "")[:16],
            "payload": json.dumps(report, default=str),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if db.IS_SQLITE:
            from sqlalchemy.dialects.sqlite import insert as _ins
        else:
            from sqlalchemy.dialects.postgresql import insert as _ins
        stmt = _ins(report_cache).values(**values).on_conflict_do_update(
            index_elements=["cache_key"],
            set_={"payload": values["payload"], "as_of": values["as_of"],
                  "created_at": values["created_at"]},
        )
        with db.engine.begin() as conn:
            conn.execute(stmt)
            # Bounded on write: a cache that grows forever is a storage bill,
            # and rows past the TTL can never be served anyway.
            conn.execute(delete(report_cache).where(report_cache.c.created_at < _fresh_after()))
        return True
    except Exception:
        return False
