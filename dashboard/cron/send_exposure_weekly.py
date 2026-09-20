#!/usr/bin/env python3
# cron/send_exposure_weekly.py
# Unstructured Alpha — weekly exposure summary
#
# Sunday 13:00 UTC. For every user who saved a portfolio AND opted in, measure
# it and send one email saying what changed. Opt-in only: the column defaults
# to false and is set from a checkbox on the exposure report.
#
# Most weeks nothing measurable changes and the email says so. That is the
# point — a weekly email that always claims news would be the same overclaiming
# the product was rebuilt to remove.
#
# REQUIRED ENV VARS:
#   DATABASE_URL       -- PostgreSQL connection string
#   RESEND_API_KEY     -- Resend API key
# OPTIONAL:
#   RESEND_FROM_EMAIL  -- verified sender (default: brief@unstructuredalpha.com)
#   FRED_API_KEY       -- without it the engine reads FRED's public CSV instead
#   APP_BASE_URL       -- link target in the email
#
# Run manually from dashboard/:
#   python -m cron.send_exposure_weekly

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from sqlalchemy import select

from utils import exposure as ex
from utils import report_ui as ui
from utils.db import engine, init_db, users
from utils.exposure_email import build_weekly_email
from utils.portfolio_workspace import get_default_holdings

FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "Unstructured Alpha <brief@unstructuredalpha.com>")
APP_BASE = os.environ.get("APP_BASE_URL", "https://app.unstructuredalpha.com").rstrip("/")


def _recipients() -> list[dict]:
    """Verified accounts that opted in. Opt-in is never inferred from activity."""
    with engine.begin() as conn:
        rows = conn.execute(
            select(users.c.id, users.c.email, users.c.subscription_tier)
            .where(users.c.exposure_email_opted_in.is_(True))
            .where(users.c.email_verified.is_(True))
        ).mappings().all()
    return [dict(r) for r in rows]


def main() -> int:
    print(f"[exposure-email] starting at {datetime.now(timezone.utc).isoformat()}", flush=True)

    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        print("[exposure-email] RESEND_API_KEY is not set — cannot send. Nothing was sent.",
              flush=True)
        return 2

    init_db()
    try:
        recipients = _recipients()
    except Exception as exc:
        print(f"[exposure-email] could not read recipients: {type(exc).__name__}: {exc}", flush=True)
        return 1

    if not recipients:
        print("[exposure-email] nobody has opted in yet", flush=True)
        return 0

    from utils.email import _post_resend_email  # lazy: keeps requests off the import path

    week = datetime.now(timezone.utc).strftime("%G-W%V")
    sent = skipped = failed = 0
    for person in recipients:
        uid, email = int(person["id"]), str(person["email"])
        try:
            holdings = [{"ticker": r["ticker"], "weight_pct": r["weight_pct"]}
                        for r in get_default_holdings(uid)]
        except Exception:
            holdings = []
        if not holdings:
            print(f"[exposure-email] user {uid}: no saved portfolio — skipped", flush=True)
            skipped += 1
            continue

        max_holdings = (ui.PRO_MAX_HOLDINGS if str(person.get("subscription_tier")) == "pro"
                        else ui.FREE_MAX_HOLDINGS)
        positions, _notes = ex.normalize_positions(holdings, max_holdings)
        report = ex.build_live_report(positions, max_holdings=max_holdings)
        if report.get("status") != "ok":
            # An unmeasurable week is not an email. Nothing is estimated to fill it.
            print(f"[exposure-email] user {uid}: {report.get('message', 'not measurable')} — skipped",
                  flush=True)
            skipped += 1
            continue

        email_body = build_weekly_email("Your saved portfolio", report, app_base=APP_BASE)
        try:
            response = _post_resend_email(
                api_key=api_key,
                from_email=FROM_EMAIL,
                to_email=email,
                subject=email_body["subject"],
                html=email_body["html"],
                email_type="exposure_weekly",
                # One send per user per ISO week, however often this runs.
                idempotency_key=f"exposure-weekly-{uid}-{week}",
            )
            if response.status_code >= 300:
                print(f"[exposure-email] user {uid}: Resend {response.status_code}", flush=True)
                failed += 1
            else:
                sent += 1
        except Exception as exc:
            print(f"[exposure-email] user {uid}: {type(exc).__name__}", flush=True)
            failed += 1

    print(f"[exposure-email] sent {sent}, skipped {skipped}, failed {failed}", flush=True)
    return 1 if failed and not sent else 0


if __name__ == "__main__":
    raise SystemExit(main())
