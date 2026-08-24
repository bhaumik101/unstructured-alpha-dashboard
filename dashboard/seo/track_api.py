"""Public analytics beacon for the marketing site.

Why this exists: the Next.js landing page at unstructuredalpha.com had no
analytics of any kind, so the top of the funnel was completely invisible. Every
stored page view came from the Streamlit app, which a visitor only reaches after
already deciding to click through. Visitor -> signup conversion therefore could
not be computed at all: the denominator was never recorded.

Why it lives in the SEO service rather than in Next.js: this process already
imports utils.db and utils.analytics, so landing traffic is written with the
SAME schema and, critically, the SAME visitor_id derivation as in-app traffic.
A visitor who reads the landing page and then opens the app resolves to one
identity, which is what makes a funnel measurable rather than two disconnected
counts. It also keeps database credentials out of the public web deployment.

This is a public, unauthenticated write path into the analytics table, so it is
deliberately strict. Only an allowlisted set of event names and a bounded page
label are accepted; anything else is rejected rather than stored. A metrics
table that anyone on the internet can write arbitrary rows into is worse than no
metrics table, because the numbers would still look plausible.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from utils.analytics import Event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

# Only these may be written from the public internet. Adding to this list means
# accepting that anyone can generate that event, so it stays minimal.
ALLOWED_EVENTS = frozenset({Event.PAGE_VIEW, Event.APP_OPENED})

# Landing pages we recognise. An unknown label is stored as "Other" rather than
# echoed back into the database, so the page dimension cannot be used to inject
# arbitrary strings into admin views.
ALLOWED_PAGES = frozenset(
    {"Landing", "Uranium", "Pricing", "How It Works", "Other"}
)

MAX_BODY_BYTES = 2_048

ALLOWED_ACTIONS = frozenset({
    "nav",
    "mobile_nav",
    "hero_ticker",
    "watchlist",
    "signal_preview",
    "free_plan",
    "pro_trial",
    "closing",
    "footer",
})


def _no_content() -> Response:
    """Always 204.

    The beacon must never change what a visitor sees, and must never give an
    anonymous caller a signal about whether their row was stored -- that would
    turn this into a probe for the allowlist. Failures are logged, not returned.
    """
    return Response(status_code=204)


@router.post("/api/track")
async def track_landing_event(request: Request) -> Response:
    """Record one marketing-site event. Never raises, never blocks the page."""
    try:
        raw = await request.body()
        if len(raw) > MAX_BODY_BYTES:
            logger.debug("[track] rejected oversized body: %d bytes", len(raw))
            return _no_content()

        payload = json.loads(raw or b"{}")
        if not isinstance(payload, dict):
            return _no_content()

        event = str(payload.get("event") or "").strip()
        if event not in ALLOWED_EVENTS:
            logger.debug("[track] rejected event name: %r", event[:64])
            return _no_content()

        page = str(payload.get("page") or "").strip()
        if page not in ALLOWED_PAGES:
            page = "Other"

        properties: dict[str, str] = {"page": page, "site": "marketing"}
        if event == Event.APP_OPENED:
            action = str(payload.get("action") or "").strip()
            if action not in ALLOWED_ACTIONS:
                return _no_content()
            properties["action"] = action
            ticker = str(payload.get("ticker") or "").strip().upper()
            if ticker and re.fullmatch(r"[A-Z0-9.-]{1,10}", ticker):
                properties["ticker"] = ticker

        headers = {str(k).lower(): str(v) for k, v in request.headers.items()}

        # This endpoint trusts the x-forwarded-for it is handed, because the
        # marketing relay is the only thing that knows the visitor's real
        # address. That trust has to be earned: without a shared secret, anyone
        # could POST a forged IP and manufacture unlimited fake visitors,
        # corrupting the exact number this endpoint exists to make trustworthy.
        #
        # Fails closed. If the token is unset, nothing is accepted -- an open
        # write path producing plausible-looking numbers is worse than no data.
        expected = os.getenv("TRACK_INGEST_TOKEN", "")
        if not expected:
            logger.error("[track] TRACK_INGEST_TOKEN unset; refusing all events")
            return _no_content()
        if not hmac.compare_digest(headers.get("x-ua-track-token", ""), expected):
            logger.debug("[track] rejected: bad or missing ingest token")
            return _no_content()

        # Same derivation as the Streamlit app, so one person browsing the
        # landing page and then the app is one visitor, not two.
        from utils.analytics import visitor_context

        identity = visitor_context(headers=headers)
        visitor_id = identity.get("visitor_id")
        device_type = identity.get("device_type")

        # Bots are dropped rather than stored. Counting them would inflate the
        # visitor denominator and understate conversion -- the precise number
        # this endpoint exists to make trustworthy.
        if device_type == "bot":
            return _no_content()

        # No address means no stable identity. Storing the row anyway would add
        # a page view that can never be attributed to a visitor, which is what
        # already makes 80% of the historical table unusable.
        if not visitor_id:
            logger.debug("[track] no client address; not stored")
            return _no_content()

        _write_event(
            event=event,
            page=page,
            visitor_id=visitor_id,
            device_type=device_type,
            properties=properties,
        )
    except Exception as exc:  # never surface an error to the marketing site
        logger.debug("[track] dropped event: %s", exc)
    return _no_content()


def _write_event(
    *,
    event: str,
    page: str,
    visitor_id: str,
    device_type: str | None,
    properties: dict[str, str] | None = None,
) -> None:
    """Insert one row using the same columns utils/analytics.py writes.

    session_id is deliberately left NULL. On the marketing site there is no
    Streamlit connection, and inventing a per-request identifier would recreate
    the exact defect just removed from the bounce metric: an id that changes on
    every navigation and so reports one reader as many one-page visits. Visits
    are reconstructed from visitor_id and timestamps instead.
    """
    from sqlalchemy import text

    from utils.db import engine

    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO analytics_events
                    (event_name, user_id, session_id, visitor_id, device_type,
                     properties, created_at)
                VALUES
                    (:event, NULL, NULL, :visitor_id, :device_type,
                     :props, :ts)
                """
            ),
            {
                "event": event,
                "visitor_id": visitor_id,
                "device_type": device_type,
                # "site" distinguishes marketing traffic from in-app traffic so
                # the funnel can be split without guessing from the page label.
                "props": json.dumps(properties or {"page": page, "site": "marketing"}),
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )
        conn.commit()
