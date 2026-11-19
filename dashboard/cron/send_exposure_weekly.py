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
    """Verified accounts that opted in (weekly=True), plus verified Investor Pro
    accounts that set an exposure alert (weekly=False: emailed only when one
    fires). Opt-in is never inferred from activity; setting an alert is the
    consent for alert emails."""
    from utils.exposure_alerts import users_with_alerts
    with engine.begin() as conn:
        rows = conn.execute(
            select(users.c.id, users.c.email, users.c.subscription_tier, users.c.exposure_email_opted_in)
            .where(users.c.email_verified.is_(True))
        ).mappings().all()
    alerting = set(users_with_alerts())
    out = []
    for r in rows:
        pro = str(r["subscription_tier"]) == "pro"
        weekly = bool(r["exposure_email_opted_in"])
        if weekly or (pro and int(r["id"]) in alerting):
            out.append({"id": r["id"], "email": r["email"], "subscription_tier": r["subscription_tier"],
                        "weekly": weekly, "alerts": pro and int(r["id"]) in alerting})
    return out


def _save_states(states: dict) -> None:
    if not states:
        return
    try:
        from utils.exposure_alerts import save_states
        save_states(states)
    except Exception as exc:
        print(f"[exposure-email] could not save alert states: {type(exc).__name__}", flush=True)


def main() -> int:
    print(f"[exposure-email] starting at {datetime.now(timezone.utc).isoformat()}", flush=True)

    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        print("[exposure-email] RESEND_API_KEY is not set — cannot send. Nothing was sent.",
              flush=True)
        return 2

    # Without a verified sender, utils.email falls back to Resend's test address
    # (onboarding@resend.dev), which can only mail the Resend account's owner:
    # every send to a real subscriber is rejected. Found in Nov 2026 -- this
    # service had RESEND_API_KEY but RESEND_FROM_EMAIL was never filled in.
    # Refuse up front so it shows as a failed run, not a week of 4xx sends.
    sender = os.environ.get("RESEND_FROM_EMAIL", "")
    if not sender or "resend.dev" in sender:
        print("[exposure-email] RESEND_FROM_EMAIL is not set to a verified sender — Resend's test "
              "address can only mail the account owner, so every send would be rejected. "
              "Nothing was sent.", flush=True)
        return 2

    # Without DATABASE_URL, init_db() silently falls back to a local SQLite file
    # that has no users — the job would then report "nobody has opted in" and
    # exit 0 every week while sending nothing. Refuse instead, so a missing
    # secret shows up as a failed run rather than a successful no-op.
    if not os.environ.get("DATABASE_URL"):
        print("[exposure-email] DATABASE_URL is not set — refusing to run against an "
              "empty local database. Nothing was sent.", flush=True)
        return 2

    init_db()
    try:
        recipients = _recipients()
    except Exception as exc:
        print(f"[exposure-email] could not read recipients: {type(exc).__name__}: {exc}", flush=True)
        return 1

    if not recipients:
        print("[exposure-email] nobody has opted in or set an alert yet", flush=True)
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

        fired, states = [], {}
        if person.get("alerts"):
            from utils.exposure_alerts import evaluate, list_alerts
            fired, states = evaluate(list_alerts(uid), report)
        if not person.get("weekly") and not fired:
            # Alerts only, and none crossed: no email, but the states still move.
            _save_states(states)
            skipped += 1
            continue

        email_body = build_weekly_email("Your saved portfolio", report, app_base=APP_BASE,
                                        fired=fired, weekly=bool(person.get("weekly")))
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
                # Only once the email is out: a failed send fires again next week.
                _save_states(states)
                if fired:
                    print(f"[exposure-email] user {uid}: {len(fired)} alert(s) fired", flush=True)
        except Exception as exc:
            print(f"[exposure-email] user {uid}: {type(exc).__name__}", flush=True)
            failed += 1

    print(f"[exposure-email] sent {sent}, skipped {skipped}, failed {failed}", flush=True)
    return 1 if failed and not sent else 0


if __name__ == "__main__":
    raise SystemExit(main())
