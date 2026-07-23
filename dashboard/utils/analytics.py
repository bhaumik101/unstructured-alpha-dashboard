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

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_ENABLED  = os.getenv("ANALYTICS_ENABLED",  "true").lower() != "false"
_PROVIDER = os.getenv("ANALYTICS_PROVIDER", "db").lower()


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

    payload = {
        "event":      event,
        "user_id":    user_id,
        "session_id": session_id,
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
                    (event_name, user_id, session_id, properties, created_at)
                VALUES
                    (:event, :uid, :sid, :props, :ts)
            """),
            {
                "event": payload["event"],
                "uid":   payload["user_id"],
                "sid":   payload.get("session_id"),
                "props": json.dumps(payload["properties"]),
                "ts":    payload["ts"],
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
            "distinct_id": str(payload["user_id"] or payload.get("session_id") or "anon"),
            "properties":  payload["properties"],
            "timestamp":   payload["ts"],
        },
        timeout=3,
    )
