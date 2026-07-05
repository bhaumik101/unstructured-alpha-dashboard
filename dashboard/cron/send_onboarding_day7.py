#!/usr/bin/env python3
# cron/send_onboarding_day7.py
# Unstructured Alpha — Day-7 Retention Email Cron
#
# Runs daily at 15:00 UTC (11:00 AM ET).
# Targets email-verified users who signed up 7–8 days ago and have NOT yet
# received this specific email (guarded by the `day7_email_sent` column).
#
# Email content: "One week in — what the machine is seeing right now"
# - Current macro regime
# - Machine's top 3 tickers by confluence score
# - Most notable signal flip in the past 7 days
# - Soft Pro upgrade CTA for free users
#
# Run manually from dashboard/:
#   python -m cron.send_onboarding_day7

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from sqlalchemy import select, update
from utils.db import init_db, engine, users
from utils.email import send_day7_onboarding_email, EmailSendError
from utils.billing import get_user_tier

# ── Config ────────────────────────────────────────────────────────────────────
DAY7_MIN = 7   # send after this many days since signup
DAY7_MAX = 8   # but not after this many


# ── Recipient lookup ──────────────────────────────────────────────────────────

def _get_recipients() -> list[dict]:
    """
    Return email-verified users who signed up 7–8 days ago and haven't
    received the day-7 email yet.
    """
    now     = datetime.now(timezone.utc)
    min_ago = (now - timedelta(days=DAY7_MAX)).isoformat()
    max_ago = (now - timedelta(days=DAY7_MIN)).isoformat()

    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(
                    users.c.id,
                    users.c.email,
                    users.c.subscription_tier,
                    users.c.created_at,
                )
                .where(users.c.email_verified == True)           # noqa: E712
                .where(users.c.created_at >= min_ago)
                .where(users.c.created_at <= max_ago)
                .where(
                    (users.c.day7_email_sent == None) |          # noqa: E711
                    (users.c.day7_email_sent == "")
                )
            ).fetchall()
        return [
            {"id": r[0], "email": r[1], "tier": r[2], "created_at": r[3]}
            for r in rows
        ]
    except Exception as exc:
        print(f"[day7] DB query failed: {exc}", flush=True)
        return []


def _mark_sent(user_id: int) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(day7_email_sent="true")
            )
    except Exception as exc:
        print(f"[day7] mark_sent failed for user {user_id}: {exc}", flush=True)


# ── Live data helpers ─────────────────────────────────────────────────────────

def _get_top_tickers() -> list[dict]:
    """Return top 3 bullish tickers as list of {ticker, score, status}."""
    try:
        from utils.top_tickers import get_top_tickers
        result = get_top_tickers(signal_scores_hash=0)
        bull = result.get("bullish", [])
        return [
            {"ticker": t.get("ticker"), "score": float(t.get("score", 0)), "status": "Bullish"}
            for t in bull[:3]
        ]
    except Exception:
        return []


def _get_regime() -> str:
    try:
        from utils.signals_cache import get_all_signal_scores
        scores = get_all_signal_scores()
        bull  = sum(1 for v in scores.values() if v.get("status") == "bullish")
        bear  = sum(1 for v in scores.values() if v.get("status") == "bearish")
        total = max(len(scores), 1)
        if bull / total >= 0.50:
            return "Bullish"
        if bear / total >= 0.50:
            return "Bearish"
        return "Mixed"
    except Exception:
        return "Mixed"


def _get_recent_flip() -> dict | None:
    """Return the most notable signal flip in the past 7 days, or None."""
    try:
        from utils.signals_cache import get_signal_diff
        diffs = get_signal_diff(days_back=7) or []
        # Prefer bull→bear or bear→bull flips (ignore neutral transitions)
        strong = [
            d for d in diffs
            if "bullish" in (d.get("old_status", ""), d.get("new_status", ""))
            or "bearish" in (d.get("old_status", ""), d.get("new_status", ""))
        ]
        if strong:
            d = strong[0]
            return {
                "name":        d.get("name", d.get("signal_id", "A signal")),
                "from_status": d.get("old_status", "neutral"),
                "to_status":   d.get("new_status", "neutral"),
            }
        # Fall back to first diff if no strong flip
        if diffs:
            d = diffs[0]
            return {
                "name":        d.get("name", d.get("signal_id", "A signal")),
                "from_status": d.get("old_status", "neutral"),
                "to_status":   d.get("new_status", "neutral"),
            }
        return None
    except Exception:
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[day7] starting — {datetime.now(timezone.utc).isoformat()}", flush=True)

    init_db()

    recipients = _get_recipients()
    print(f"[day7] qualifying recipients: {len(recipients)}", flush=True)
    if not recipients:
        print("[day7] nobody qualifies — done.", flush=True)
        return

    # Compute shared data once
    regime     = _get_regime()
    top_tickers = _get_top_tickers()
    flip        = _get_recent_flip()
    print(
        f"[day7] regime={regime}, top_tickers={[t['ticker'] for t in top_tickers]}, "
        f"flip={flip and flip.get('name')}",
        flush=True,
    )

    sent = failed = 0
    for rec in recipients:
        try:
            is_pro = rec["tier"] == "pro"
            send_day7_onboarding_email(
                rec["email"],
                is_pro=is_pro,
                regime_label=regime,
                top_tickers=top_tickers,
                signal_flip=flip,
            )
            _mark_sent(rec["id"])
            sent += 1
            print(f"[day7] sent to {rec['email']!r}", flush=True)
        except EmailSendError as exc:
            failed += 1
            print(f"[day7] SEND FAILED to {rec['email']!r}: {exc}", flush=True)
        except Exception as exc:
            failed += 1
            print(f"[day7] unexpected error for {rec['email']!r}: {exc}", flush=True)

    print(f"[day7] done — sent={sent} failed={failed}", flush=True)


if __name__ == "__main__":
    main()
