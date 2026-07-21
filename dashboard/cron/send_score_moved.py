#!/usr/bin/env python3
# cron/send_score_moved.py
# Unstructured Alpha — Score-Movement Email Cron
#
# Runs once daily (11:30 AM ET / 15:30 UTC via Render Cron).
# For every verified user who has at least one watchlist entry, it computes
# the current Confluence Score for each watched ticker and compares it against
# the last score we emailed them about (stored in alert_state.last_score_emailed).
# If any ticker has shifted ±10 or more points since that baseline, the user
# gets a single batched email summarising all moved tickers.
#
# WHY a separate field (last_score_emailed) instead of reusing last_score:
#   The hourly threshold-crossing cron (send_watchlist_alerts.py) updates
#   last_score on every run -- so if we used that as the baseline here, the
#   delta we'd see is only the movement since the *last hour*, not since the
#   last time we alerted the user about a meaningful trend shift. A 10-point
#   move spread over several hours would never be detected. last_score_emailed
#   is only updated by THIS cron, so it captures true multi-day deltas.
#
# FIRST-RUN BEHAVIOUR: If last_score_emailed is NULL (new ticker, or first time
# this cron has run for an existing user), we store the current score as the
# baseline and send no email. The user gets alerted on the *next* run if the
# score subsequently moves ±10pts from that baseline.
#
# IMPORTANT: This script runs OUTSIDE Streamlit. Do NOT import anything that
# calls st.* at module level. Configuration is read from environment variables
# (DATABASE_URL, RESEND_API_KEY, RESEND_FROM_EMAIL, FRED_API_KEY, EIA_API_KEY),
# which Render injects identically for the web service and all cron jobs.
#
# Run manually (from the dashboard/ directory):
#   python -m cron.send_score_moved
# or:
#   python cron/send_score_moved.py

import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure dashboard/ is on sys.path so `utils.*` imports resolve correctly
# whether this runs as a module or a direct script.
_here = Path(__file__).resolve().parent.parent   # dashboard/
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from utils.db import init_db, alert_state, engine, upsert_stmt
from utils.alerts_db import get_all_watchlist_users, get_watchlist, get_alert_state
from utils.email import send_score_moved_email, EmailSendError

# Minimum absolute score change (points) before we notify.
MOVE_THRESHOLD = 10.0


def _get_last_score_emailed(user_id: int, ticker: str) -> float | None:
    """Read last_score_emailed for this user/ticker from alert_state. Returns
    None if no row exists yet or the field has never been written."""
    state = get_alert_state(user_id, ticker)
    if state is None:
        return None
    return state.get("last_score_emailed")  # may also be None


def _set_last_score_emailed(user_id: int, ticker: str, score: float) -> None:
    """Upsert last_score_emailed without touching any other alert_state fields."""
    ticker = ticker.upper().strip()
    stmt = upsert_stmt(alert_state, ["user_id", "ticker"]).values(
        user_id=user_id,
        ticker=ticker,
        last_score_emailed=score,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "ticker"],
        set_={"last_score_emailed": score},
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def check_user(user_id: int) -> list[dict]:
    """
    For a single user, compute current scores for all watched tickers and
    return a list of move-dicts for any ticker that crossed MOVE_THRESHOLD.
    Also updates the last_score_emailed baseline for tickers that triggered
    (so the next run compares from the new level, not the original one).
    Tickers whose score changed but not enough, or first-run tickers, have
    their baseline set silently with no alert.
    """
    watchlist = get_watchlist(user_id)
    moved = []

    for row in watchlist:
        ticker = row["ticker"]
        try:
            from utils.score_cache import get_full_ticker_score
            full = get_full_ticker_score(ticker).result
            current = float(full["confluence"]["overall_score"])
        except Exception as exc:
            print(
                f"[score-moved] user={user_id} ticker={ticker}: score error — {exc}",
                flush=True,
            )
            continue

        baseline = _get_last_score_emailed(user_id, ticker)

        if baseline is None:
            # First time this cron has seen this ticker for this user.
            # Store the current score as baseline; alert on the NEXT run.
            _set_last_score_emailed(user_id, ticker, current)
            print(
                f"[score-moved] user={user_id} ticker={ticker}: "
                f"first run — baseline set to {current:.1f}",
                flush=True,
            )
            continue

        delta = current - baseline
        if abs(delta) >= MOVE_THRESHOLD:
            moved.append({
                "ticker":    ticker,
                "old_score": baseline,
                "new_score": current,
                "delta":     delta,
            })
            # Update baseline to the new level so next comparison starts here.
            _set_last_score_emailed(user_id, ticker, current)
            print(
                f"[score-moved] user={user_id} ticker={ticker}: "
                f"MOVED {baseline:.1f} → {current:.1f} (Δ{delta:+.1f})",
                flush=True,
            )
        else:
            print(
                f"[score-moved] user={user_id} ticker={ticker}: "
                f"no move ({baseline:.1f} → {current:.1f}, Δ{delta:+.1f})",
                flush=True,
            )

    return moved


def main() -> None:
    print(
        f"[score-moved] starting at {datetime.now(timezone.utc).isoformat()}",
        flush=True,
    )

    init_db()

    watchlist_users = get_all_watchlist_users()
    print(
        f"[score-moved] {len(watchlist_users)} user(s) with watchlist entries",
        flush=True,
    )

    if not watchlist_users:
        print("[score-moved] no watchlist users — nothing to do. done.", flush=True)
        return

    total_emails_sent   = 0
    total_emails_failed = 0
    total_moved_tickers = 0

    for u in watchlist_users:
        user_id = u["id"]
        email   = u["email"]

        try:
            moved = check_user(user_id)
        except Exception as exc:
            print(
                f"[score-moved] user={user_id} ({email}): check_user ERROR — {exc}",
                flush=True,
            )
            continue

        if not moved:
            continue

        total_moved_tickers += len(moved)
        try:
            send_score_moved_email(email, moved)
            total_emails_sent += 1
            print(
                f"[score-moved] user={user_id} ({email}): "
                f"emailed {len(moved)} moved ticker(s)",
                flush=True,
            )
        except EmailSendError as exc:
            total_emails_failed += 1
            print(
                f"[score-moved] user={user_id} ({email}): email FAILED — {exc}",
                flush=True,
            )

    print(
        f"[score-moved] done. "
        f"{total_moved_tickers} ticker move(s) across "
        f"{total_emails_sent} email(s) sent, {total_emails_failed} failed.",
        flush=True,
    )


if __name__ == "__main__":
    main()
