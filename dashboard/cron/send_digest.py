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

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Ensure the dashboard/ directory is on sys.path so `utils.*` imports work
# regardless of whether this is run as a module or a direct script.
_here = Path(__file__).resolve().parent.parent   # dashboard/
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from sqlalchemy import select

from utils.db import engine, users, watchlist, score_snapshots, init_db
from utils.score_history import get_signal_flips
from utils.config import SIGNALS, TICKERS

# ── Admin override ────────────────────────────────────────────────────────────
# Admins always receive the morning digest regardless of their DB subscription
# tier or digest_opted_in flag. Add any admin email here.
_ADMIN_EMAILS: list[str] = [
    "bpgiri2005@gmail.com",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compute_signal_pulse() -> tuple[dict, int, int, int, int, str]:
    """
    Score all signals without Streamlit's cache. Returns:
        (scores_dict, bull_n, bear_n, neut_n, unavailable_n, overall_bias_str)
    """
    from datetime import datetime
    from utils.fetchers import fetch_signal_series, is_unavailable
    from utils.analysis import score_signal

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    scores, bull, bear, neut, unavailable = {}, 0, 0, 0, 0
    for sig_id, cfg in SIGNALS.items():
        try:
            s = fetch_signal_series(cfg, start, end)
            if is_unavailable(s):
                unavailable += 1
                print(f"[digest] signal {sig_id} unavailable — excluded", flush=True)
                continue
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
            unavailable += 1

    total = bull + bear + neut or 1
    if bull / total >= 0.5:
        bias = "Bullish"
    elif bear / total >= 0.5:
        bias = "Bearish"
    else:
        bias = "Mixed"

    return scores, bull, bear, neut, unavailable, bias


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


def _generate_watchlist_narrative(
    items: list[dict],
    bias: str,
    flips: list[dict],
) -> str | None:
    """
    Call Claude Haiku to write a 2-3 sentence plain-English summary of the
    user's watchlist relative to the current macro environment.

    items: [{ticker, name, score, case, delta}]
    bias:  "Bullish" | "Bearish" | "Mixed"
    flips: [{signal_name, from_status, to_status}]

    Returns the narrative string, or None on any failure (never raises).
    The email still sends without it if this fails.
    """
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or not items:
        return None

    # Build a compact data summary for the prompt
    ticker_lines = []
    for it in items:
        delta_str = f"{it['delta']:+.1f}pt 7d" if it.get("delta") is not None else "no 7d data"
        ticker_lines.append(
            f"  - {it['ticker']} ({it['name']}): score {it['score']:.0f}/100, "
            f"{it['case']}, {delta_str}"
        )

    flip_lines = []
    for f in flips[:3]:
        flip_lines.append(
            f"  - {f.get('signal_name', f.get('signal_id', ''))} flipped "
            f"{f['from_status']} → {f['to_status']}"
        )

    prompt = (
        f"Today's macro regime: {bias}.\n"
        f"The user's watched tickers:\n" + "\n".join(ticker_lines) + "\n"
    )
    if flip_lines:
        prompt += "Overnight signal flips:\n" + "\n".join(flip_lines) + "\n"
    prompt += (
        "\nWrite 2-3 sentences addressed directly to the user (start with 'Your') "
        "summarising what the data above means for their specific holdings today. "
        "Be specific — reference actual ticker names and scores. "
        "No hype. No disclaimers. No markdown. Plain prose only."
    )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=180,
            system=(
                "You are a terse, data-driven equity analyst writing a personalised morning "
                "briefing. Write in plain English. Cite specific numbers. Never use hype or "
                "promotional language. Never add disclaimers. No bullet points."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        narrative = response.content[0].text.strip()
        print(f"[digest] narrative generated ({len(narrative)} chars)", flush=True)
        return narrative
    except Exception as exc:
        print(f"[digest] narrative generation failed (non-blocking): {exc}", flush=True)
        return None


def _get_opted_in_emails() -> list[tuple[str, str, int | None]]:
    """
    Return [(email, display_name_or_email, user_id_or_None)] for:
      - Pro users who have opted in (digest_opted_in=True, subscription_tier='pro')
      - Admin emails from _ADMIN_EMAILS (always included, no DB check required)
    Deduplication is applied so an admin who is also a Pro subscriber only
    receives one copy.
    """
    seen: set[str] = set()
    result: list[tuple[str, str, int | None]] = []

    # 1. Pro opted-in users from DB
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(users.c.id, users.c.email)
                .where(users.c.digest_opted_in == True)   # noqa: E712
                .where(users.c.email_verified == True)
                .where(users.c.subscription_tier == "pro")
            ).fetchall()
        for row in rows:
            email = row[1].strip().lower()
            if email not in seen:
                seen.add(email)
                result.append((row[1], row[1], row[0]))
    except Exception as exc:
        print(f"[digest] DB query for opted-in users failed: {exc}", flush=True)

    # 2. Admin override — always included; look up user_id so watchlist works
    for admin_email in _ADMIN_EMAILS:
        normalized = admin_email.strip().lower()
        if normalized not in seen:
            seen.add(normalized)
            admin_uid: int | None = None
            try:
                with engine.begin() as conn:
                    row = conn.execute(
                        select(users.c.id).where(users.c.email == admin_email)
                    ).fetchone()
                    if row:
                        admin_uid = row[0]
            except Exception:
                pass
            result.append((admin_email, admin_email, admin_uid))
            print(f"[digest] admin override added: {admin_email!r} user_id={admin_uid}", flush=True)

    return result


def _get_user_watchlist_tickers(user_id: int) -> list[str]:
    """Return the user's watchlist tickers (newest-added first, max 3)."""
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(watchlist.c.ticker)
                .where(watchlist.c.user_id == user_id)
                .order_by(watchlist.c.added_at.desc())
                .limit(3)
            ).fetchall()
        return [row[0].upper() for row in rows]
    except Exception:
        return []


def _compute_watchlist_scores(
    tickers: list[str],
    all_signal_scores: dict,
) -> list[dict]:
    """
    Quick per-ticker confluence for the digest. Uses already-cached
    get_all_signal_scores() so no extra API calls are needed.
    Adds a 7-day score delta from score_snapshots when available.
    Adds signal alignment (conviction) — how many relevant signals
    point the same direction as the score.

    Returns list of:
        {ticker, name, score, case, delta, aligned, total_relevant}
    """
    from utils.analysis import compute_confluence
    from datetime import datetime, timedelta, timezone

    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    results = []

    for ticker in tickers:
        meta = TICKERS.get(ticker, {})
        relevant_sids = set(meta.get("signals", list(SIGNALS.keys())))

        ticker_signals = {
            sid: sv for sid, sv in all_signal_scores.items()
            if sid in relevant_sids and not sv.get("error")
        }
        if not ticker_signals:
            continue

        cf    = compute_confluence(ticker_signals)
        score = cf["overall_score"]
        case  = cf["case"]

        # 7-day delta from score_snapshots
        delta: float | None = None
        try:
            with engine.begin() as conn:
                snap_rows = conn.execute(
                    select(score_snapshots.c.score, score_snapshots.c.snapshot_date)
                    .where(score_snapshots.c.ticker == ticker)
                    .where(score_snapshots.c.snapshot_date >= seven_days_ago)
                    .order_by(score_snapshots.c.snapshot_date)
                ).fetchall()
            if len(snap_rows) >= 2:
                delta = round(score - float(snap_rows[0][0]), 1)
        except Exception:
            pass

        # Signal alignment — count how many relevant signals agree with the score direction.
        # Pure arithmetic on already-fetched data; no extra imports or API calls needed.
        direction = (
            "bullish" if score >= 55 else
            "bearish" if score <= 45 else
            "neutral"
        )
        aligned   = sum(
            1 for sv in ticker_signals.values()
            if sv.get("status") == direction
        )
        total_rel = len(ticker_signals)

        results.append({
            "ticker":         ticker,
            "name":           meta.get("name", ticker),
            "score":          round(score, 1),
            "case":           case,
            "delta":          delta,
            "aligned":        aligned,
            "total_relevant": total_rel,
        })

    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[digest] starting at {datetime.now(timezone.utc).isoformat()}", flush=True)

    # Render cron schedules are UTC and do not observe US daylight saving
    # time. The Blueprint invokes us at both possible UTC hours; only the
    # genuine 7 AM America/New_York run proceeds.
    now_et = datetime.now(ZoneInfo("America/New_York"))
    if now_et.hour != 7 and os.environ.get("FORCE_DIGEST_SEND") != "1":
        print(f"[digest] local time is {now_et:%H:%M %Z}; outside 7 AM window — skipping", flush=True)
        return

    init_db()

    # 1. Compute signal pulse
    print("[digest] computing signal pulse…", flush=True)
    signal_scores, bull_n, bear_n, neut_n, unavailable_n, bias = _compute_signal_pulse()
    print(
        f"[digest] pulse: bull={bull_n} bear={bear_n} neut={neut_n} "
        f"unavailable={unavailable_n} bias={bias}",
        flush=True,
    )

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

    # 4. Load signal scores once — reused for all per-user watchlist lookups
    from utils.signals_cache import get_all_signal_scores
    all_signal_scores: dict = {}
    try:
        all_signal_scores = get_all_signal_scores()
        print(f"[digest] signal scores loaded: {len(all_signal_scores)} signals", flush=True)
    except Exception as exc:
        print(f"[digest] signal scores cache failed: {exc} — watchlist scores skipped", flush=True)

    # 5. Get opted-in users
    recipients = _get_opted_in_emails()
    print(f"[digest] opted-in recipients: {len(recipients)}", flush=True)

    if not recipients:
        print("[digest] no opted-in users — nothing to send. done.", flush=True)
        return

    # 6. Send — personalised watchlist section per user
    from utils.email import send_digest_email, EmailSendError

    sent, failed = 0, 0
    for email_addr, _, user_id in recipients:
        # Per-user watchlist scores + AI narrative (best-effort — never blocks the send)
        watchlist_items: list[dict] = []
        watchlist_narrative: str | None = None
        if user_id is not None and all_signal_scores:
            try:
                tickers = _get_user_watchlist_tickers(user_id)
                if tickers:
                    watchlist_items = _compute_watchlist_scores(tickers, all_signal_scores)
                    print(f"[digest] watchlist for user {user_id}: {tickers} → {len(watchlist_items)} scored", flush=True)
                    if watchlist_items:
                        watchlist_narrative = _generate_watchlist_narrative(
                            watchlist_items, bias, flips
                        )
            except Exception as exc:
                print(f"[digest] watchlist score failed for user {user_id}: {exc}", flush=True)

        try:
            send_digest_email(
                to_email=email_addr,
                signal_flips=flips,
                score_movers=movers,
                overall_bias=bias,
                bull_n=bull_n,
                bear_n=bear_n,
                neut_n=neut_n,
                unavailable_n=unavailable_n,
                signal_scores=signal_scores,
                watchlist_items=watchlist_items or None,
                watchlist_narrative=watchlist_narrative,
            )
            sent += 1
            print(f"[digest] sent to {email_addr!r}", flush=True)
        except EmailSendError as exc:
            failed += 1
            print(f"[digest] FAILED to {email_addr!r}: {exc}", flush=True)

    print(f"[digest] done — sent={sent} failed={failed}", flush=True)


if __name__ == "__main__":
    main()
