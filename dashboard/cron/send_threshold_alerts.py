#!/usr/bin/env python3
"""Evaluate each watchlist once and deliver crossings to every enabled channel.

The former webhook and email crons each recomputed the same watchlists.  Worse,
the first evaluation advanced the shared crossing state, so webhook users could
lose the email copy thirty minutes later.  This dispatcher evaluates once, then
fans the same alert set out to email and (when configured) webhook delivery.
"""

from __future__ import annotations

from datetime import datetime, timezone

from utils.alerts import evaluate_watchlist
from utils.alerts_db import get_all_watchlist_users
from utils.db import init_db
from utils.email import EmailSendError, send_watchlist_alert_email
from utils.webhook import fire_alerts_for_user, get_all_webhook_users


def main() -> None:
    print(f"[threshold-alerts] starting at {datetime.now(timezone.utc).isoformat()}",
          flush=True)
    init_db()
    watchlist_users = get_all_watchlist_users()
    webhook_user_ids = {int(row["id"]) for row in get_all_webhook_users()}

    evaluated = alerts_created = emails_sent = webhooks_sent = failures = 0
    for user in watchlist_users:
        user_id = int(user["id"])
        email = user["email"]
        try:
            alerts = evaluate_watchlist(user_id)
            evaluated += 1
        except Exception as exc:
            failures += 1
            print(f"[threshold-alerts] user={user_id} evaluation_failed={exc}",
                  flush=True)
            continue

        if not alerts:
            continue
        alerts_created += len(alerts)

        try:
            send_watchlist_alert_email(email, alerts)
            emails_sent += 1
        except EmailSendError as exc:
            failures += 1
            print(f"[threshold-alerts] user={user_id} email_failed={exc}", flush=True)

        if user_id in webhook_user_ids:
            try:
                webhooks_sent += fire_alerts_for_user(user_id, alerts)
            except Exception as exc:
                failures += 1
                print(f"[threshold-alerts] user={user_id} webhook_failed={exc}",
                      flush=True)

    print(
        "[threshold-alerts] complete "
        f"users={evaluated} alerts={alerts_created} emails={emails_sent} "
        f"webhooks={webhooks_sent} failures={failures}",
        flush=True,
    )


if __name__ == "__main__":
    main()
