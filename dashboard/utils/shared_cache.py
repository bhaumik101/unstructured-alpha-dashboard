"""
Cross-process cache for values that are expensive to produce and identical for
every visitor, backed by Render Key Value (Redis).

WHY THIS EXISTS
    Measured on production 2026-08-02, the home page's own PERF instrumentation
    reported:

        page.home.total    max 3364ms   avg 2167ms
        page.home.header   max 2607ms   avg 1558ms   <- 72-77% of the page
        (everything else on the page except imports/snapshot was <= 4ms)

    The header renders on EVERY page, so that cost is paid on every navigation.
    Its expensive part is a synchronous `yf.download()` of nine symbols for the
    market ticker strip. `@st.cache_data` already wraps it, but that cache is
    per-process and per-15-minutes, so every cache miss makes one real visitor
    wait out a Yahoo round-trip, and the first visitor to any fresh container
    always pays it.

WHAT THIS CHANGES
    The value is shared in Redis, so a miss in one process is usually a hit
    from another. Two properties matter more than the raw hit rate:

      • STALE-WHILE-REVALIDATE. An expired-but-present value is returned
        immediately rather than blocking. A slightly old share price is a
        completely acceptable trade for not making someone wait ~2s; a blank
        strip or a stall is not.
      • SINGLE REFRESHER. Only the caller that wins a short Redis lock does the
        slow work. Everyone else serves stale. Without the lock, an expiry
        during a traffic burst would send every concurrent process to Yahoo at
        once — the stampede this is meant to prevent.

    So at most one visitor per refresh interval GLOBALLY can wait, instead of
    one per process per 15 minutes. Only a completely cold Redis blocks anyone.

DELIBERATELY NOT THREADED
    The obvious "refresh in the background" design is off the table here:
    utils/quotes.py records that wrapping yfinance in external threads crashed
    production, because curl_cffi (yfinance's HTTP client) does not tolerate it.
    Refresh therefore happens inline, on one caller, holding a lock.

FAIL-OPEN
    Every Redis path is best-effort. If Redis is unset, unreachable or corrupt,
    this degrades to calling the producer directly — i.e. exactly today's
    behaviour. A cache must never be able to take the page down.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "").strip()
_PREFIX = "sc:"

_client = None
_client_init = False
_client_lock = threading.Lock()


def _init_client():
    """Lazily build the Redis client. Mirrors utils/ratelimit.py's approach."""
    global _client, _client_init
    with _client_lock:
        if _client_init:
            return _client
        _client_init = True
        if not _REDIS_URL:
            return None
        try:
            import redis
            c = redis.from_url(_REDIS_URL, socket_timeout=1.5,
                               socket_connect_timeout=1.5, decode_responses=True)
            c.ping()
            _client = c
        except Exception as exc:
            logger.warning("shared_cache: Redis unavailable (%s)", str(exc)[:120])
            _client = None
        return _client


def backend() -> str:
    return "redis" if _init_client() else "none"


def get_or_refresh(key: str, producer: Callable[[], Any], *,
                   fresh_seconds: int = 900,
                   hard_ttl_seconds: int = 86400,
                   lock_seconds: int = 30) -> Any:
    """Return a shared cached value, refreshing at most one caller at a time.

    fresh_seconds     — age past which the value is considered stale.
    hard_ttl_seconds  — how long a stale value stays servable. Generous on
                        purpose: a day-old strip still beats a blocking fetch,
                        and the value is refreshed long before then in practice.
    lock_seconds      — refresh lock lifetime; must exceed a slow producer call
                        so a crashed refresher cannot wedge the key for long.
    """
    client = _init_client()
    if client is None:
        return producer()                      # no Redis: today's behaviour

    rkey, lkey = _PREFIX + key, _PREFIX + key + ":lock"

    cached, age = None, None
    try:
        raw = client.get(rkey)
        if raw:
            env = json.loads(raw)
            cached = env.get("v")
            age = time.time() - float(env.get("t", 0))
    except Exception as exc:
        logger.warning("shared_cache: read failed for %s (%s)", key, str(exc)[:80])

    if cached is not None and age is not None and age < fresh_seconds:
        return cached

    # Stale or missing. Try to become the single refresher.
    got_lock = False
    try:
        got_lock = bool(client.set(lkey, "1", nx=True, ex=lock_seconds))
    except Exception:
        got_lock = False

    if not got_lock and cached is not None:
        return cached          # someone else is refreshing; serve stale, no wait

    if not got_lock and cached is None:
        # Nothing to serve and another caller holds the lock. Producing here is
        # still better than rendering an empty strip; the lock only exists to
        # thin a stampede, not to block the very first visitor entirely.
        return producer()

    try:
        value = producer()
    except Exception:
        try:
            client.delete(lkey)
        except Exception:
            pass
        return cached if cached is not None else None

    try:
        client.set(rkey, json.dumps({"v": value, "t": time.time()}),
                   ex=hard_ttl_seconds)
    except Exception as exc:
        logger.warning("shared_cache: write failed for %s (%s)", key, str(exc)[:80])
    finally:
        try:
            client.delete(lkey)
        except Exception:
            pass
    return value
