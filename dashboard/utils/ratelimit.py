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


def redis_ping(timeout: float = 1.5) -> "bool | None":
    """
    Live Redis PING for readiness checks. Returns:
      True  — Redis reachable,
      False — REDIS_URL set but Redis unreachable,
      None  — REDIS_URL not configured (limiter runs on the in-process fallback).
    Never raises; bounded by the client's socket timeout.
    """
    if not _REDIS_URL:
        return None
    cli = _get_client()
    if cli is None:
        return False
    try:
        return bool(cli.ping())
    except Exception:
        return False


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
    "options_flow":    (20, 300),   # provider-heavy (yfinance options chains)
    "export":          (10, 600),
    "checkout":        (5, 900),    # prevent duplicate Stripe sessions / scripted abuse
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
    allowed, retry_after = check(f"{action}:{actor}", limit, window)
    if not allowed:
        # Structured denial event — the key signal for spotting abuse / storms.
        # Actor is a hashed-ish id (u<id>/s<session>/ip), not PII. Best-effort.
        try:
            from utils.observability import log_event
            log_event("rate_limit_block", action=action, actor=actor,
                      limit=limit, window=window, retry_after=retry_after,
                      backend=backend())
        except Exception:
            pass
    return allowed, retry_after


# ── Streamlit convenience helpers (lazy streamlit import — keeps this module
#    testable without streamlit and importable by non-web callers) ─────────────
def client_ip() -> str:
    """
    Best-effort client IP from Render's X-Forwarded-For (first hop). Render's
    edge sets this to the real remote address; the leading value is the client.
    NOTE: XFF can be spoofed by a client, so IP limits are a supplement, not the
    sole control (login also has a DB per-account lockout). '?' if unknown.
    """
    try:
        import streamlit as st
        headers = getattr(getattr(st, "context", None), "headers", None)
        if headers:
            xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for") or ""
            if xff:
                return xff.split(",")[0].strip()
    except Exception:
        pass
    return "?"


def session_actor() -> str:
    """User id if signed in, else the Streamlit session id, else 'anon'."""
    try:
        import streamlit as st
        u = (st.session_state.get("user") or {}).get("id")
        if u:
            return f"u{u}"
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        return f"s{getattr(ctx, 'session_id', 'anon')}" if ctx else "anon"
    except Exception:
        return "anon"


def guard(action: str, actor: str | None = None) -> tuple[bool, int]:
    """limit_action for `action`, defaulting the actor to session_actor()."""
    return limit_action(actor if actor is not None else session_actor(), action)
