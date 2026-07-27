"""
utils/analytics.py — Lightweight event tracking abstraction.

Design goals:
  1. Never crash the app — all exceptions are swallowed at every layer
  2. Non-blocking — fires in a daemon thread, never adds latency to page render
  3. Pluggable backend — ANALYTICS_PROVIDER env var selects destination
  4. Clean event constants — typed strings, no magic literals scattered across codebase

Usage:
    from utils.analytics import track, Event
    track(Event.DASHBOARD_VIEWED, user_id=42)
    track(Event.UPGRADE_CTA_CLICKED, user_id=42, properties={"page": "tdd", "cta": "score_gate"})

Providers (set ANALYTICS_PROVIDER env var):
  db       (default) — writes to analytics_events table in the app database
  posthog  — sends to PostHog (also requires POSTHOG_API_KEY + POSTHOG_HOST env vars)
  none     — disables all tracking

Kill switch:
  ANALYTICS_ENABLED=false  — disables tracking regardless of provider
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_ENABLED  = os.getenv("ANALYTICS_ENABLED",  "true").lower() != "false"
_PROVIDER = os.getenv("ANALYTICS_PROVIDER", "db").lower()


def _request_headers() -> dict:
    """Capture request headers while still on the Streamlit render thread."""
    try:
        import streamlit as st
        return {str(k).lower(): str(v) for k, v in st.context.headers.items()}
    except Exception:
        return {}


def _client_address(headers: dict) -> Optional[str]:
    """Return a validated proxy-provided client address, never persisted raw."""
    candidate = (
        headers.get("cf-connecting-ip")
        or (headers.get("x-forwarded-for", "").split(",", 1)[0].strip())
        or headers.get("x-real-ip")
        or ""
    ).strip()
    if not candidate:
        return None
    # Some proxies append a port to an IPv4 address.
    if candidate.count(":") == 1 and "." in candidate:
        candidate = candidate.rsplit(":", 1)[0]
    try:
        return ipaddress.ip_address(candidate).compressed
    except ValueError:
        return None


def _device_signature(user_agent: str) -> tuple[str, str]:
    """
    Reduce a user agent to broad, non-identifying device characteristics.

    The full user-agent string is intentionally discarded. The coarse signature
    only helps distinguish, for example, a phone and laptop sharing one IP.
    """
    ua = (user_agent or "").lower()
    if not ua:
        return "unknown", "unknown|unknown"

    if re.search(r"\b(bot|spider|crawler|slurp|headless|preview)\b", ua):
        device = "bot"
    elif "ipad" in ua or "tablet" in ua or ("android" in ua and "mobile" not in ua):
        device = "tablet"
    elif any(token in ua for token in ("mobile", "iphone", "ipod", "windows phone")):
        device = "mobile"
    else:
        device = "desktop"

    if any(token in ua for token in ("iphone", "ipad", "ipod")):
        os_family = "ios"
    elif "android" in ua:
        os_family = "android"
    elif "windows" in ua:
        os_family = "windows"
    elif any(token in ua for token in ("macintosh", "mac os")):
        os_family = "macos"
    elif "linux" in ua:
        os_family = "linux"
    else:
        os_family = "other"

    # Browser family/version is deliberately excluded: switching browsers on
    # the same device should not manufacture another "unique" visitor.
    return device, f"{device}|{os_family}"


def _visitor_salt() -> str:
    """Use a dedicated secret in production, with a stable local-dev fallback."""
    return (
        os.getenv("ANALYTICS_HASH_SALT")
        or os.getenv("UNSTRUCTURED_ALPHA_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or "unstructured-alpha-local-analytics"
    )


def visitor_context(
    user_id: Optional[int] = None,
    headers: Optional[dict] = None,
) -> dict:
    """
    Build a privacy-safe, stable visitor identity for aggregate analytics.

    Raw IP and full user agent are used only in memory to create a salted HMAC
    and are never returned, logged, or stored. When no network address is
    available, signed-in users get a user/device fallback; anonymous visitors
    remain unidentified rather than being miscounted as sessions.
    """
    normalized = {
        str(k).lower(): str(v)
        for k, v in (headers if headers is not None else _request_headers()).items()
    }
    device_type, device_signature = _device_signature(normalized.get("user-agent", ""))
    client_address = _client_address(normalized)
    if client_address:
        material = f"ip:{client_address}|device:{device_signature}"
    elif user_id is not None:
        material = f"user:{user_id}|device:{device_signature}"
    else:
        return {"visitor_id": None, "device_type": device_type}

    visitor_id = hmac.new(
        _visitor_salt().encode("utf-8"),
        material.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return {"visitor_id": visitor_id, "device_type": device_type}


# ── Event name constants (use these everywhere — no bare strings) ─────────────
class Event:
    # Navigation
    PAGE_VIEW              = "page_view"
    DASHBOARD_VIEWED       = "dashboard_viewed"
    PRICING_VIEWED         = "pricing_viewed"
    HOW_IT_WORKS_VIEWED    = "how_it_works_viewed"

    # Auth lifecycle
    SIGNUP_STARTED         = "signup_started"
    SIGNUP_COMPLETED       = "signup_completed"
    LOGIN                  = "login"
    RETURNING_USER         = "returning_user_visit"

    # Onboarding
    ONBOARDING_STARTED     = "onboarding_started"
    ONBOARDING_STEP        = "onboarding_step_completed"
    ONBOARDING_COMPLETED   = "onboarding_completed"

    # Signal engagement
    SIGNAL_CARD_CLICKED    = "signal_card_clicked"
    SIGNAL_SEARCHED        = "signal_searched"
    CHART_EXPANDED         = "chart_expanded"

    # Ticker engagement
    TICKER_SEARCHED        = "ticker_searched"
    TICKER_DEEP_DIVE       = "ticker_deep_dive_viewed"
    WATCHLIST_UPDATED      = "watchlist_updated"
    PORTFOLIO_SAVED        = "portfolio_saved"
    DECISION_QUEUE_VIEWED  = "decision_queue_viewed"
    PORTFOLIO_FIT_SIMULATED = "portfolio_fit_simulated"
    INVESTOR_CHECKUP_VIEWED = "investor_checkup_viewed"
    DECISION_COCKPIT_VIEWED = "decision_cockpit_viewed"
    DECISION_COCKPIT_MODE   = "decision_cockpit_mode_changed"
    DECISION_COCKPIT_ACTION = "decision_cockpit_action"
    CATALYST_CENTER_VIEWED = "catalyst_center_viewed"
    CATALYST_PLAN_SAVED    = "catalyst_plan_saved"

    # Conversion events
    UPGRADE_CTA_CLICKED    = "upgrade_cta_clicked"
    PRO_PREVIEW_CLICKED    = "pro_preview_clicked"
    CHECKOUT_STARTED       = "checkout_started"
    CHECKOUT_COMPLETED     = "checkout_completed"

    # Retention hooks
    EMAIL_CAPTURE          = "email_capture"
    ALERT_SET              = "alert_set"
    SHARE_CLICKED          = "share_clicked"
    DIGEST_CTA_CLICKED     = "digest_cta_clicked"

    # Errors / reliability
    ERROR_TRIGGERED        = "error_triggered"
    API_FALLBACK           = "api_fallback"


def track(
    event: str,
    user_id: Optional[int] = None,
    properties: Optional[dict] = None,
    session_id: Optional[str] = None,
) -> None:
    """
    Fire an analytics event. Non-blocking (daemon thread) and never raises.

    Args:
        event:      Event name — use Event.* constants.
        user_id:    Logged-in user ID, or None for anonymous events.
        properties: Any JSON-serialisable dict of additional context.
        session_id: Optional Streamlit session ID for anonymous session stitching.
    """
    if not _ENABLED or _PROVIDER == "none":
        return

    identity = visitor_context(user_id=user_id)
    payload = {
        "event":      event,
        "user_id":    user_id,
        "session_id": session_id,
        "visitor_id": identity["visitor_id"],
        "device_type": identity["device_type"],
        "properties": properties or {},
        "ts":         datetime.now(timezone.utc).isoformat(),
    }
    threading.Thread(target=_dispatch, args=(payload,), daemon=True).start()


def _dispatch(payload: dict) -> None:
    """Route to the configured provider. Swallows all exceptions."""
    try:
        if _PROVIDER == "db":
            _write_db(payload)
        elif _PROVIDER == "posthog":
            _write_posthog(payload)
        else:
            logger.debug(
                "[analytics] %s | user=%s | %s",
                payload["event"], payload["user_id"], payload["properties"],
            )
    except Exception as exc:
        logger.debug("[analytics] dispatch error for %r: %s", payload["event"], exc)


def _write_db(payload: dict) -> None:
    from utils.db import engine
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO analytics_events
                    (event_name, user_id, session_id, visitor_id, device_type,
                     properties, created_at)
                VALUES
                    (:event, :uid, :sid, :visitor_id, :device_type, :props, :ts)
            """),
            {
                "event":       payload["event"],
                "uid":         payload["user_id"],
                "sid":         payload.get("session_id"),
                "visitor_id":  payload.get("visitor_id"),
                "device_type": payload.get("device_type"),
                "props":       json.dumps(payload["properties"]),
                "ts":          payload["ts"],
            },
        )
        conn.commit()


def _write_posthog(payload: dict) -> None:
    """Send to PostHog. Requires POSTHOG_API_KEY env var."""
    import requests
    api_key = os.getenv("POSTHOG_API_KEY", "")
    host    = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
    if not api_key:
        return
    requests.post(
        f"{host}/capture/",
        json={
            "api_key":     api_key,
            "event":       payload["event"],
            "distinct_id": str(
                payload["user_id"]
                or payload.get("visitor_id")
                or payload.get("session_id")
                or "anon"
            ),
            "properties": {
                **payload["properties"],
                "$device_type": payload.get("device_type"),
            },
            "timestamp":   payload["ts"],
        },
        timeout=3,
    )
