# utils/library_snapshot.py
# Unstructured Alpha — the last good copy of the stock library, kept in Redis
#
# On 2026-10-27 the database became unreachable and stayed so for more than a
# day. The SEO service held the library only in process memory, which a restart
# empties, so every public page could only answer 503. This keeps the newest
# good library in Redis (same private network, independent of Postgres), so an
# outage serves the stored readings, with their date and a notice, instead.
#
# RULES
#   * Only real stored readings: the copy is exactly what the library returned.
#     Nothing is estimated, filled in or carried forward beyond what was stored.
#   * A small or empty read never overwrites a good copy (MIN_STOCKS).
#   * Best-effort both ways: no Redis, no copy, never an error.

from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

KEY = "ua:library:latest"
MIN_STOCKS = 50       # a read smaller than this is not trusted to replace the copy


def _client():
    try:
        from utils.ratelimit import _get_client
        return _get_client()
    except Exception:
        return None


def save(stocks: List[dict], client=None) -> bool:
    """Store the library if it looks complete. True when written."""
    if len(stocks or []) < MIN_STOCKS:
        return False
    c = client if client is not None else _client()
    if c is None:
        return False
    try:
        doc = {"saved_at": datetime.now(timezone.utc).isoformat(), "stocks": stocks}
        c.set(KEY, gzip.compress(json.dumps(doc, default=str, separators=(",", ":")).encode()))
        return True
    except Exception as exc:
        logger.warning("[library_snapshot] save failed: %s", str(exc)[:120])
        return False


def load(client=None) -> Optional[Tuple[str, List[dict]]]:
    """(saved_at, stocks) of the last good copy, or None."""
    c = client if client is not None else _client()
    if c is None:
        return None
    try:
        blob = c.get(KEY)
        if not blob:
            return None
        doc = json.loads(gzip.decompress(blob))
        stocks = doc.get("stocks") or []
        return (str(doc.get("saved_at") or ""), stocks) if stocks else None
    except Exception as exc:
        logger.warning("[library_snapshot] load failed: %s", str(exc)[:120])
        return None
