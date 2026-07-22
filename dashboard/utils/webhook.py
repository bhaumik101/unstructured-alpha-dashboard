# utils/webhook.py
# Unstructured Alpha — Webhook Alert Delivery
#
# Fires alert notifications to Discord, Slack, or any generic JSON webhook
# endpoint when threshold crossings are detected in a user's watchlist.
#
# Platform detection is URL-based:
#   discord.com/api/webhooks  → Discord embed format
#   hooks.slack.com           → Slack Block Kit format
#   everything else           → generic JSON payload
#
# Three delivery paths coexist:
#   1. fire_alerts_for_user() called from alerts.evaluate_ticker() in a
#      daemon thread — immediate fire on page-load alert evaluation, without
#      blocking the page. If the webhook times out, the cron catches it next
#      run anyway.
#   2. cron/fire_webhooks.py — hourly proactive sweep for ALL webhook users,
#      so alerts reach people even when they're offline (not waiting for a
#      page load to trigger the evaluation).
#   3. Manual test button in the Watchlist settings UI (Pro-gated). Sends a
#      dummy alert so the user can verify their webhook is wired up before
#      waiting for a real crossing.
#
# All fire_* functions are exception-safe — a webhook timeout or HTTP error
# must never crash the alert evaluation pipeline or block a page load.
#
# API-key security note: webhook URLs are stored in the users table (fetched
# at runtime), never in source code, environment variables, or logs. They're
# user-supplied and user-managed — we only store and fire them.

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from sqlalchemy import select, update

from utils import db

_TIMEOUT = 8    # seconds — long enough for a slow webhook, short enough not to stall a page
_UA = "UnstructuredAlpha/1.0"


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_webhook_url(user_id: int) -> str | None:
    """Return this user's saved webhook URL, or None if not configured."""
    with db.engine.begin() as conn:
        row = conn.execute(
            select(db.users.c.webhook_url).where(db.users.c.id == user_id)
        ).fetchone()
    return row[0] if row and row[0] else None


def set_webhook_url(user_id: int, url: str | None) -> None:
    """Persist (or clear) the user's webhook URL. Pass None or "" to unset."""
    with db.engine.begin() as conn:
        conn.execute(
            update(db.users)
            .where(db.users.c.id == user_id)
            .values(webhook_url=url or None)
        )


def get_all_webhook_users() -> list[dict]:
    """
    Return [{id, email, webhook_url}] for every user who has a webhook URL
    configured. Used by cron/fire_webhooks.py to proactively push alerts.
    """
    with db.engine.begin() as conn:
        rows = conn.execute(
            select(db.users.c.id, db.users.c.email, db.users.c.webhook_url)
            .where(db.users.c.webhook_url.isnot(None))
            .where(db.users.c.webhook_url != "")
        ).mappings().all()
    return [dict(r) for r in rows]


# ── Platform detection ────────────────────────────────────────────────────────

def _is_discord(url: str) -> bool:
    return "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url


def _is_slack(url: str) -> bool:
    return "hooks.slack.com" in url


def detect_platform(url: str) -> str:
    """Return "discord", "slack", or "generic" for display in the settings UI."""
    if _is_discord(url):
        return "discord"
    if _is_slack(url):
        return "slack"
    return "generic"


# ── Payload formatters ────────────────────────────────────────────────────────

_DIR_EMOJI = {"bullish": "📈", "bearish": "📉"}
# Discord embed color integers (hex → int)
_DIR_COLOR_INT = {"bullish": 0x00D566, "bearish": 0xFF4444}

_TYPE_LABEL = {
    "score_threshold": "Confluence Score",
    "price_move":      "Price Move",
    "insider":         "Insider Activity",
    "short_interest":  "Short Interest",
    "13f":             "13F Positioning",
    "screen_entry":    "Saved Screen Entrant",
}


def _format_discord(alert: dict) -> dict:
    """Discord webhook payload — single embed per alert."""
    direction = alert.get("direction") or "neutral"
    emoji = _DIR_EMOJI.get(direction, "⚠️")
    color = _DIR_COLOR_INT.get(direction, 0x6B7FBF)
    type_label = _TYPE_LABEL.get(alert.get("alert_type", ""), alert.get("alert_type", "Alert"))
    ticker = alert.get("ticker", "")
    message = alert.get("message", "")
    return {
        "username":   "Unstructured Alpha",
        "embeds": [{
            "title":       f"{emoji} {ticker} — {type_label}",
            "description": message,
            "color":       color,
            "footer": {
                "text": "Unstructured Alpha · unstructuredalpha.com",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }],
    }


def _format_slack(alert: dict) -> dict:
    """Slack webhook payload — Block Kit section + context block."""
    direction = alert.get("direction") or "neutral"
    emoji = _DIR_EMOJI.get(direction, "⚠️")
    type_label = _TYPE_LABEL.get(alert.get("alert_type", ""), alert.get("alert_type", "Alert"))
    ticker = alert.get("ticker", "")
    message = alert.get("message", "")
    return {
        # fallback text for notifications
        "text": f"{emoji} *{ticker}* — {type_label}: {message}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{emoji} *{ticker}* — {type_label}\n{message}",
                },
            },
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": "_Unstructured Alpha · <https://unstructuredalpha.com|unstructuredalpha.com>_",
                }],
            },
        ],
    }


def _format_generic(alert: dict) -> dict:
    """Generic JSON payload for any other webhook endpoint (Zapier, n8n, etc.)."""
    direction = alert.get("direction") or "neutral"
    type_label = _TYPE_LABEL.get(alert.get("alert_type", ""), alert.get("alert_type", "Alert"))
    return {
        "source":     "unstructured_alpha",
        "ticker":     alert.get("ticker", ""),
        "alert_type": alert.get("alert_type", ""),
        "type_label": type_label,
        "direction":  direction,
        "message":    alert.get("message", ""),
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }


# ── HTTP delivery ─────────────────────────────────────────────────────────────

def fire_alert(webhook_url: str, alert: dict) -> bool:
    """
    POST one alert to the given webhook URL.
    Detects platform from URL and formats payload accordingly.
    Returns True on 2xx response, False on any failure. Never raises.
    """
    try:
        if _is_discord(webhook_url):
            payload = _format_discord(alert)
        elif _is_slack(webhook_url):
            payload = _format_slack(alert)
        else:
            payload = _format_generic(alert)

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent":   _UA,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def fire_alerts(webhook_url: str, alerts: list[dict]) -> int:
    """
    Fire a list of alerts to the same webhook URL, one HTTP call each.
    Returns the count of successful deliveries (HTTP 2xx).
    """
    return sum(fire_alert(webhook_url, a) for a in alerts)


def fire_alerts_for_user(user_id: int, alerts: list[dict]) -> int:
    """
    Look up this user's webhook URL and fire all given alerts to it.
    Returns 0 immediately if no webhook is configured — safe to call always.
    """
    try:
        url = get_webhook_url(user_id)
        if not url:
            return 0
        return fire_alerts(url, alerts)
    except Exception:
        # This path is commonly called from a background alert thread. A DB
        # migration race, shutdown, or transient connection error must not
        # escape the thread and pollute page/test execution.
        return 0


# ── Test-fire helper (used by Watchlist settings UI) ─────────────────────────

def fire_test_alert(webhook_url: str) -> bool:
    """
    Send a synthetic "connection test" alert so the user can verify their
    webhook is wired up before waiting for a real threshold crossing.
    """
    test_alert = {
        "ticker":     "TEST",
        "alert_type": "score_threshold",
        "direction":  "bullish",
        "message":    "✅ Your Unstructured Alpha webhook is connected. You'll receive real alerts here when your watchlist tickers cross a threshold.",
    }
    return fire_alert(webhook_url, test_alert)
