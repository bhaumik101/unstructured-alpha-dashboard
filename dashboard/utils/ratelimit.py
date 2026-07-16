"""
utils/ratelimit.py — distributed rate limiting.

Primary backend: Redis (Render Key Value), shared across every web process/
instance, using an ATOMIC fixed-window counter (Lua) so concurrent requests
can't race past the limit. If REDIS_URL is unset or Redis is unreachable, we
fall back to a per-process in-memory limiter (weaker — not shared across
instances/restarts — but keeps the app working). backend() reports which.

Public API:
    allowed, retry_after = check(key, limit, window_seconds)
    allowed, retry_after = limit_action(actor, action)   # uses POLICIES

Notes: fixed-window (INCR+EXPIRE), short TTL keys, FAIL-OPEN on Redis errors
(availability > perfect enforcement), never raises to callers.
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "").strip()

_LUA = """
local c = redis.call('INCR', KEYS[1])
if c == 1 then
  redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
local ttl = redis.call('TTL', KEYS[1])
return {c, ttl}
"""

_KEY_PREFIX = "rl:"

_client = None
_client_init = False
_lua_sha = None
_client_lock = threading.Lock()


def _init_client():
    global _client, _client_init, _lua_sha
    with _client_lock:
        if _client_init:
            return
        _client_init = True
        if not _REDIS_URL:
            logger.info("[ratelimit] REDIS_URL unset — in-process fallback")
            return
        try:
            import redis
            c = redis.from_url(_REDIS_URL, socket_connect_timeout=2, socket_timeout=2,
                               retry_on_timeout=False, health_check_interval=30)
            c.ping()
            try:
                _lua_sha = c.script_load(_LUA)
            except Exception:
                _lua_sha = None
            _client = c
            logger.info("[ratelimit] Redis backend active")
        except Exception as exc:
            logger.warning("[ratelimit] Redis unavailable (%s) — in-process fallback", exc)
            _client = None


def _get_client():
    if not _client_init:
        _init_client()
    return _client


def backend() -> str:
    return "redis" if _get_client() is not None else "memory"


_fallback: dict[str, tuple[int, float]] = {}
_fallback_lock = threading.Lock()


def _fallback_incr(key: str, window: int) -> tuple[int, int]:
    now = time.monotonic()
    with _fallback_lock:
        cnt, exp = _fallback.get(key, (0, 0.0))
        if now >= exp:
            cnt, exp = 0, now + window
        cnt += 1
        _fallback[key] = (cnt, exp)
        if len(_fallback) > 5000:
            for k in [k for k, (_, e) in _fallback.items() if e <= now][:1000]:
                _fallback.pop(k, None)
        return cnt, max(0, int(exp - now))


def check(key: str, limit: int, window: int) -> tuple[bool, int]:
    k = _KEY_PREFIX + key
    cli = _get_client()
    if cli is not None:
        try:
            if _lua_sha:
                try:
                    res = cli.evalsha(_lua_sha, 1, k, window, limit)
                except Exception:
                    res = cli.eval(_LUA, 1, k, window, limit)
            else:
                res = cli.eval(_LUA, 1, k, window, limit)
            count, ttl = int(res[0]), int(res[1])
            allowed = count <= limit
            return allowed, (max(ttl, 1) if not allowed else 0)
        except Exception as exc:
            logger.warning("[ratelimit] redis check error (%s) — allowing", exc)
            return True, 0
    count, ttl = _fallback_incr(k, window)
    allowed = count <= limit
    return allowed, (max(ttl, 1) if not allowed else 0)


POLICIES: dict[str, tuple[int, int]] = {
    "ticker_analysis": (30, 300),
    "ai_research":     (10, 3600),
    "export":          (10, 600),
    "screener_scan":   (60, 300),
    "login_ip":        (25, 900),
    "signup_ip":       (10, 3600),
    "anon_page":       (120, 60),
}


def limit_action(actor: str, action: str) -> tuple[bool, int]:
    pol = POLICIES.get(action)
    if not pol:
        return True, 0
    limit, window = pol
    return check(f"{action}:{actor}", limit, window)
