#!/usr/bin/env python3
# cron/send_digest.py
# Unstructured Alpha — Morning Digest Cron Script
#
# Designed to run as a Render Cron Job at 07:00 ET daily (12:00 UTC).
# It computes the current signal pulse, fetches flips and score movers
# from the DB, and emails every opted-in user.
#
# IMPORTANT: This script runs OUTSIDE of Streamlit. It must NOT import
# anything that calls st.* at module level (no @st.cache_data, no
# st.secrets). Configuration is read exclusively from environment
# variables (DATABASE_URL, RESEND_API_KEY, RESEND_FROM_EMAIL, etc.),
# which Render injects the same way it does for the web service.
#
# Run manually (from the dashboard/ directory):
#   python -m cron.send_digest
# or:
#   python cron/send_digest.py

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure the dashboard/ directory is on sys.path so `utils.*` imports work
# regardless of whether this is run as a module or a direct script.
_here = Path(__file__).resolve().parent.parent   # dashboard/
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from sqlalchemy import select

from utils.db import engine, users, init_db
from utils.score_history import get_signal_flips
from utils.config import SIGNALS

# ── Admin override ────────────────────────────────────────────────────────────
# Admins always receive the morning digest regardless of their DB subscription
# tier or digest_opted_in flag. Add any admin email here.
_ADMIN_EMAILS: list[str] = [
    "bpgiri2005@gmail.com",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_signal_pulse() -> tuple[dict, int, int, int, str]:
    """
    Score all signals without Streamlit's cache. Returns:
        (scores_dict, bull_n, bear_n, neut_n, overall_bias_str)
    """
    from datetime import datetime
    from utils.fetchers import fetch_signal_series
    from utils.analysis import score_signal

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    scores, bull, bear, neut = {}, 0, 0, 0
    for sig_id, cfg in SIGNALS.items():
        try:
            s = fetch_signal_series(cfg, start, end)
            scored = score_signal(s, inverse=cfg.get("inverse", False))
            status = scored.get("status", "neutral")
            scores[sig_id] = {
                "name":   cfg["name"],
                "score":  scored.get("score", 50),
                "status": status,
            }
            if status == "bullish":
                bull += 1
            elif status == "bearish":
                bear += 1
            else:
                neut += 1
        except Exception as exc:
            print(f"[digest] signal {sig_id} failed: {exc}", flush=True)
            scores[sig_id] = {"name": cfg["name"], "score": 50, "status": "neutral"}
            neut += 1

    total = bull + bear + neut or 1
    if bull / total >= 0.5:
        bias = "Bullish"
    elif bear / total >= 0.5:
        bias = "Bearish"
    else:
        bias = "Mixed"

    return scores, bull, bear, neut, bias


def _get_score_movers(days_back: int = 7) -> list[dict]:
    """Same logic as get_score_movers() in pages/2_Today_Digest.py but
    without @st.cache_data — safe to call in a cron context."""
    from utils.db import score_snapshots
    import pandas as pd

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(score_snapshots)
                .where(score_snapshots.c.snapshot_date >= cutoff)
                .order_by(score_snapshots.c.ticker, score_snapshots.c.snapshot_date)
            ).mappings().all()
    except Exception:
        return []

    if not rows:
        return []

    df = pd.DataFrame([dict(r) for r in rows])
    results = []
    for ticker, grp in df.groupby("ticker"):
        grp = grp.sort_values("snapshot_date")
        if len(grp) < 2:
            continue
        earliest, latest = grp.iloc[0], grp.iloc[-1]
        delta = latest["score"] - earliest["score"]
        results.append({
            "ticker":     ticker,
            "from_score": round(float(earliest["score"]), 1),
            "to_score":   round(float(latest["score"]), 1),
            "delta":      round(float(delta), 1),
            "case":       latest.get("case", "NEUTRAL") or "NEUTRAL",
        })

    results.sort(key=lambda r: -abs(r["delta"]))
    return results[:8]


def _get_opted_in_emails() -> list[tuple[str, str]]:
    """
    Return [(email, display_name_or_email)] for:
      - Pro users who have opted in (digest_opted_in=True, subscription_tier='pro')
      - Admin emails from _ADMIN_EMAILS (always included, no DB check required)
    Deduplication is applied so an admin who is also a Pro subscriber only
    receives one copy.
    """
    seen: set[str] = set()
    result: list[tuple[str, str]] = []

    # 1. Pro opted-in users from DB
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(users.c.email)
                .where(users.c.digest_opted_in == True)   # noqa: E712
                .where(users.c.email_verified == True)
                .where(users.c.subscription_tier == "pro")
            ).fetchall()
        for row in rows:
            email = row[0].strip().lower()
            if email not in seen:
                seen.add(email)
                result.append((row[0], row[0]))
    except Exception as exc:
        print(f"[digest] DB query for opted-in users failed: {exc}", flush=True)

    # 2. Admin override — always included
    for admin_email in _ADMIN_EMAILS:
        normalized = admin_email.strip().lower()
        if normalized not in seen:
            seen.add(normalized)
            result.append((admin_email, admin_email))
            print(f"[digest] admin override added: {admin_email!r}", flush=True)

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[digest] starting at {datetime.now(timezone.utc).isoformat()}", flush=True)

    init_db()

    # 1. Compute signal pulse
    print("[digest] computing signal pulse…", flush=True)
    signal_scores, bull_n, bear_n, neut_n, bias = _compute_signal_pulse()
    print(f"[digest] pulse: bull={bull_n} bear={bear_n} neut={neut_n} bias={bias}", flush=True)

    # 2. Record signal snapshots (so flips are detectable tomorrow)
    from utils.score_history import record_signal_snapshot
    for sig_id, sv in signal_scores.items():
        try:
            record_signal_snapshot(sig_id, sv["score"], sv["status"])
        except Exception:
            pass

    # 3. Get flips and movers
    flips = get_signal_flips(days_back=1)
    print(f"[digest] flips since yesterday: {len(flips)}", flush=True)

    # Annotate flip dicts with signal name for the email template
    for f in flips:
        f["signal_name"] = SIGNALS.get(f["signal_id"], {}).get("name", f["signal_id"])

    movers = _get_score_movers()
    print(f"[digest] score movers: {len(movers)}", flush=True)

    # 4. Get opted-in users
    recipients = _get_opted_in_emails()
    print(f"[digest] opted-in recipients: {len(recipients)}", flush=True)

    if not recipients:
        print("[digest] no opted-in users — nothing to send. done.", flush=True)
        return

    # 5. Send
    from utils.email import send_digest_email, EmailSendError

    sent, failed = 0, 0
    for email_addr, _ in recipients:
        try:
            send_digest_email(
                to_email=email_addr,
                signal_flips=flips,
                score_movers=movers,
                overall_bias=bias,
                bull_n=bull_n,
                bear_n=bear_n,
                neut_n=neut_n,
                signal_scores=signal_scores,
            )
            sent += 1
            print(f"[digest] sent to {email_addr!r}", flush=True)
        except EmailSendError as exc:
            failed += 1
            print(f"[digest] FAILED to {email_addr!r}: {exc}", flush=True)

    print(f"[digest] done — sent={sent} failed={failed}", flush=True)


if __name__ == "__main__":
    main()
