#!/usr/bin/env python3
# cron/send_weekly_brief.py
# Unstructured Alpha — Sunday AI Portfolio Brief Cron
#
# Runs every Sunday at 15:00 UTC (11:00 AM ET) via Render Cron.
# Sends a personalized weekly brief to every Pro user who has opted
# in to the morning digest. The brief contains:
#
#   1. Watchlist composite score + week-over-week delta
#   2. Top 3 movers on the user's watchlist (7d delta)
#   3. Market-wide macro signal flips this week
#   4. AI "what to watch next week" paragraph (Haiku, personalized)
#   5. Machine's Best Ideas — top 3 market-wide (acquisition hook)
#   6. Referral link CTA (acquisition + retention)
#
# DESIGN INTENT:
#   This email is the weekly retention anchor — it keeps Pro users
#   engaged even in quiet weeks. It is ALSO designed as a viral loop:
#   the "Best Ideas" section contains public content worth forwarding,
#   and the referral CTA rewards sharing with a free month.
#
# REQUIRED ENV VARS:
#   DATABASE_URL, RESEND_API_KEY, RESEND_FROM_EMAIL,
#   ANTHROPIC_API_KEY, FRED_API_KEY, EIA_API_KEY,
#   RENDER_EXTERNAL_URL (for referral link base URL)
#
# Run manually from dashboard/:
#   python -m cron.send_weekly_brief

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from sqlalchemy import select
from utils.db import (
    init_db, engine,
    users, watchlist, score_snapshots,
)
from utils.email import send_weekly_brief_email, EmailSendError

_ADMIN_EMAILS: list[str] = [
    e.strip() for e in os.environ.get("ADMIN_EMAILS", "bpgiri2005@gmail.com").split(",")
    if e.strip()
]

# Prefer an explicit APP_BASE_URL. RENDER_EXTERNAL_URL is injected by Render only
# on WEB services -- a cron job has no public URL and never receives it -- so any
# cron reading it silently falls through to the localhost default and ships a
# dead link. Even where Render does set it, it carries the .onrender.com host
# rather than the custom domain.
_BASE_URL = (
    os.environ.get("APP_BASE_URL")
    or os.environ.get("RENDER_EXTERNAL_URL")
    or "http://localhost:8501"
).rstrip("/")


# ── Recipient lookup ──────────────────────────────────────────────────────────

def _get_recipients() -> list[tuple[str, int | None]]:
    """
    Return [(email, user_id_or_None)] for:
      - Pro users with digest_opted_in=True and email_verified=True
      - Admin overrides (always included)
    Deduplicated.
    """
    seen: set[str] = set()
    result: list[tuple[str, int | None]] = []

    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(users.c.id, users.c.email)
                .where(users.c.digest_opted_in == True)   # noqa: E712
                .where(users.c.email_verified  == True)
                .where(users.c.subscription_tier == "pro")
            ).fetchall()
        for row in rows:
            email = row[1].strip().lower()
            if email not in seen:
                seen.add(email)
                result.append((row[1], row[0]))
    except Exception as exc:
        print(f"[weekly-brief] DB query failed: {exc}", flush=True)

    for admin_email in _ADMIN_EMAILS:
        normalized = admin_email.strip().lower()
        if normalized not in seen:
            seen.add(normalized)
            uid: int | None = None
            try:
                with engine.begin() as conn:
                    row = conn.execute(
                        select(users.c.id).where(users.c.email == admin_email)
                    ).fetchone()
                    if row:
                        uid = row[0]
            except Exception:
                pass
            result.append((admin_email, uid))
            print(f"[weekly-brief] admin override: {admin_email!r} uid={uid}", flush=True)

    return result


# ── Watchlist helpers ─────────────────────────────────────────────────────────

def _get_user_watchlist_tickers(user_id: int) -> list[str]:
    """Return all tickers for a user's watchlist."""
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(watchlist.c.ticker)
                .where(watchlist.c.user_id == user_id)
                .order_by(watchlist.c.added_at.desc())
            ).fetchall()
        return [row[0].upper() for row in rows]
    except Exception:
        return []


def _compute_watchlist_composite(tickers: list[str]) -> dict | None:
    """
    Compute week-over-week composite score from score_snapshots.
    Returns {current_score, week_delta, label, n_tickers} or None.
    """
    if not tickers:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(
                    score_snapshots.c.ticker,
                    score_snapshots.c.score,
                    score_snapshots.c.snapshot_date,
                )
                .where(score_snapshots.c.ticker.in_(tickers))
                .where(score_snapshots.c.snapshot_date >= cutoff)
                .order_by(score_snapshots.c.ticker, score_snapshots.c.snapshot_date)
            ).fetchall()
    except Exception:
        return None

    from collections import defaultdict
    by_ticker: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for r in rows:
        if r[1] is not None:
            by_ticker[r[0]].append((r[2], float(r[1])))

    if not by_ticker:
        return None

    # Most recent date common to at least half the tickers
    all_dates: list[str] = sorted(
        {d for entries in by_ticker.values() for d, _ in entries}
    )
    if not all_dates:
        return None

    recent_date = all_dates[-1]
    week_ago_date = all_dates[0] if len(all_dates) == 1 else all_dates[0]

    recent_scores, old_scores = [], []
    for ticker, entries in by_ticker.items():
        entries_sorted = sorted(entries)
        if entries_sorted:
            recent_scores.append(entries_sorted[-1][1])
            if len(entries_sorted) >= 2:
                old_scores.append(entries_sorted[0][1])

    if not recent_scores:
        return None

    current = round(sum(recent_scores) / len(recent_scores), 1)
    delta: float | None = None
    if old_scores:
        old_avg = sum(old_scores) / len(old_scores)
        delta = round(current - old_avg, 1)

    label = "Bullish" if current >= 65 else ("Bearish" if current <= 35 else "Mixed")
    return {
        "current_score": current,
        "week_delta":    delta,
        "label":         label,
        "n_tickers":     len(by_ticker),
    }


def _compute_watchlist_movers(tickers: list[str]) -> list[dict]:
    """
    Return top 3 movers by absolute score delta over the last 7 days,
    with current score, delta, and case label.
    """
    if not tickers:
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(
                    score_snapshots.c.ticker,
                    score_snapshots.c.score,
                    score_snapshots.c.snapshot_date,
                )
                .where(score_snapshots.c.ticker.in_(tickers))
                .where(score_snapshots.c.snapshot_date >= cutoff)
                .order_by(score_snapshots.c.ticker, score_snapshots.c.snapshot_date)
            ).fetchall()
    except Exception:
        return []

    from collections import defaultdict
    by_ticker: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for r in rows:
        if r[1] is not None:
            by_ticker[r[0]].append((r[2], float(r[1])))

    # Get ticker names from top_tickers
    name_map: dict[str, str] = {}
    try:
        from utils.signals_cache import get_all_signal_scores
        from utils.top_tickers import get_top_tickers
        result = get_top_tickers(signal_scores_hash=0)
        for row in result.get("all", []):
            name_map[row["ticker"]] = row.get("name", row["ticker"])
    except Exception:
        pass

    movers = []
    for ticker, entries in by_ticker.items():
        entries_sorted = sorted(entries)
        if len(entries_sorted) < 2:
            continue
        old_score = entries_sorted[0][1]
        cur_score = entries_sorted[-1][1]
        delta     = round(cur_score - old_score, 1)
        if abs(delta) < 0.5:
            continue
        case = "BULL" if cur_score >= 65 else ("BEAR" if cur_score <= 35 else "NEUT")
        movers.append({
            "ticker": ticker,
            "name":   name_map.get(ticker, ticker),
            "score":  cur_score,
            "delta":  delta,
            "case":   case,
        })

    movers.sort(key=lambda x: -abs(x["delta"]))
    return movers[:3]


# ── Market-wide signal flips ──────────────────────────────────────────────────

def _get_signal_flips_7d() -> list[dict]:
    """
    Return signal flips over the last 7 days.
    Each dict has: signal_id, name, from_status, to_status.
    """
    try:
        from utils.score_history import get_signal_diff
        diff = get_signal_diff(days_back=7)
        flips = []
        for f in diff.get("flipped_bullish", []):
            flips.append({
                "signal_id":   f["signal_id"],
                "name":        f["name"],
                "from_status": f.get("from_status", "bearish"),
                "to_status":   "bullish",
            })
        for f in diff.get("flipped_bearish", []):
            flips.append({
                "signal_id":   f["signal_id"],
                "name":        f["name"],
                "from_status": f.get("from_status", "bullish"),
                "to_status":   "bearish",
            })
        return flips[:6]
    except Exception as exc:
        print(f"[weekly-brief] signal diff failed: {exc}", flush=True)
        return []


# ── Best Ideas ────────────────────────────────────────────────────────────────

def _get_best_ideas(top_n: int = 3) -> list[dict]:
    """
    Top tickers by rank_score (same logic as pages/34_Best_Ideas.py).
    """
    try:
        from utils.signals_cache import get_all_signal_scores
        from utils.top_tickers import get_top_tickers
        from utils.score_history import get_batch_velocity_stats

        signal_scores = get_all_signal_scores()
        result = get_top_tickers(signal_scores_hash=len(signal_scores))
        all_rows = result.get("all", [])
        candidates = [r for r in all_rows if float(r.get("score", 0)) >= 62.0]
        if not candidates:
            return []

        tickers = [r["ticker"] for r in candidates]
        vel_map = get_batch_velocity_stats(tickers)

        enriched = []
        for row in candidates:
            t  = row["ticker"]
            vd = vel_map.get(t)
            if not vd or vd["velocity"] <= 0 or vd["n_windows"] < 6:
                continue
            vel = vd["velocity"]
            enriched.append({
                **row,
                "velocity":   round(vel, 2),
                "rank_score": float(row["score"]) + min(vel * 3, 12.0),
            })

        enriched.sort(key=lambda x: -x["rank_score"])
        return enriched[:top_n]
    except Exception as exc:
        print(f"[weekly-brief] best ideas failed: {exc}", flush=True)
        return []


# ── AI "What to Watch" paragraph ─────────────────────────────────────────────

def _generate_watchout(
    tickers: list[str],
    watchlist_movers: list[dict],
    signal_flips: list[dict],
    regime_label: str,
    best_ideas: list[dict],
) -> str | None:
    """
    Ask Haiku to write a 2-3 sentence "what to watch next week" paragraph
    personalized to this user's watchlist and the current macro regime.
    Returns None if ANTHROPIC_API_KEY is missing or the call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        # Build context string
        mover_lines = ""
        if watchlist_movers:
            mover_lines = "\n".join(
                f"  {m['ticker']}: {m['score']:.0f}/100, "
                f"{'+' if m['delta'] >= 0 else ''}{m['delta']:.1f} pts 7d"
                for m in watchlist_movers
            )
        else:
            mover_lines = "  (no watchlist data)"

        flip_lines = ""
        if signal_flips:
            flip_lines = "\n".join(
                f"  {f['name']}: {f['from_status']} → {f['to_status']}"
                for f in signal_flips[:4]
            )
        else:
            flip_lines = "  (no signal flips this week — regime stable)"

        idea_lines = ""
        if best_ideas:
            idea_lines = ", ".join(
                f"{r['ticker']} ({float(r['score']):.0f}/100)"
                for r in best_ideas
            )
        else:
            idea_lines = "(none qualifying)"

        prompt = (
            f"Weekly macro context:\n"
            f"  Regime: {regime_label}\n"
            f"  Signal flips this week:\n{flip_lines}\n\n"
            f"User's watchlist movers:\n{mover_lines}\n\n"
            f"Machine's top ideas right now: {idea_lines}\n\n"
            f"Write 2-3 sentences for a Pro investor: (1) what the week's signal "
            f"changes imply about the macro environment, (2) what specific data or "
            f"catalysts they should watch next week. Be specific, cite signals or "
            f"tickers by name. Do not start with 'I'. Do not use hype. "
            f"Do not add disclaimers. Plain English, no bullet points."
        )

        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=160,
            system=(
                "You are a terse, data-driven macro analyst writing a weekly briefing paragraph. "
                "Specific numbers and signal names. No hype. No disclaimers. No bullet points."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        print(f"[weekly-brief] AI watchout generated ({len(text)} chars)", flush=True)
        return text
    except Exception as exc:
        print(f"[weekly-brief] AI watchout failed (non-blocking): {exc}", flush=True)
        return None


# ── Referral link ─────────────────────────────────────────────────────────────

def _get_referral_link(user_id: int) -> str | None:
    try:
        from utils.referral import get_or_create_referral_code
        code = get_or_create_referral_code(user_id)
        return f"{_BASE_URL}?ref={code}"
    except Exception:
        return None


# ── Overall regime ────────────────────────────────────────────────────────────

def _get_regime_label() -> str:
    try:
        from utils.signals_cache import get_all_signal_scores
        scores = get_all_signal_scores()
        bull = sum(1 for v in scores.values() if v.get("status") == "bullish")
        bear = sum(1 for v in scores.values() if v.get("status") == "bearish")
        total = max(bull + bear + sum(1 for v in scores.values() if v.get("status") == "neutral"), 1)
        if bull / total >= 0.5:
            return "Bullish"
        if bear / total >= 0.5:
            return "Bearish"
        return "Mixed"
    except Exception:
        return "Mixed"


# ── Week string ───────────────────────────────────────────────────────────────

def _week_str() -> str:
    today = datetime.now(timezone.utc).date()
    # Sunday = start of the week we're sending from
    week_start = today - timedelta(days=today.weekday() + 1)  # last Monday
    week_end   = today
    if week_start.month == week_end.month:
        return f"{week_start.strftime('%b %-d')} – {week_end.strftime('%-d, %Y')}"
    return f"{week_start.strftime('%b %-d')} – {week_end.strftime('%b %-d, %Y')}"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[weekly-brief] starting — {datetime.now(timezone.utc).isoformat()}", flush=True)

    init_db()

    recipients = _get_recipients()
    print(f"[weekly-brief] recipients: {len(recipients)}", flush=True)
    if not recipients:
        print("[weekly-brief] no recipients — done.", flush=True)
        return

    # Compute market-wide sections once (shared across all users)
    print("[weekly-brief] computing market-wide sections…", flush=True)
    signal_flips = _get_signal_flips_7d()
    print(f"[weekly-brief] signal flips 7d: {len(signal_flips)}", flush=True)

    best_ideas = _get_best_ideas()
    print(f"[weekly-brief] best ideas: {len(best_ideas)}", flush=True)

    regime_label = _get_regime_label()
    print(f"[weekly-brief] regime: {regime_label}", flush=True)

    week = _week_str()

    sent, failed = 0, 0
    for email_addr, user_id in recipients:
        try:
            # Per-user personalization
            tickers: list[str] = []
            composite: dict | None = None
            movers: list[dict] = []
            ai_watchout: str | None = None
            referral_link: str | None = None

            if user_id is not None:
                tickers = _get_user_watchlist_tickers(user_id)
                if tickers:
                    composite = _compute_watchlist_composite(tickers)
                    movers    = _compute_watchlist_movers(tickers)
                    print(
                        f"[weekly-brief] user {user_id}: {len(tickers)} tickers, "
                        f"composite={composite and composite.get('current_score'):.0f if composite else 'n/a'}, "
                        f"movers={len(movers)}",
                        flush=True,
                    )

                ai_watchout   = _generate_watchout(tickers, movers, signal_flips, regime_label, best_ideas)
                referral_link = _get_referral_link(user_id)

            send_weekly_brief_email(
                to_email=email_addr,
                composite_score=composite["current_score"] if composite else None,
                composite_delta=composite["week_delta"]    if composite else None,
                composite_label=composite["label"]         if composite else regime_label,
                n_tickers=composite["n_tickers"]           if composite else 0,
                watchlist_movers=movers or None,
                signal_flips_7d=signal_flips or None,
                best_ideas=best_ideas or None,
                ai_watchout=ai_watchout,
                referral_link=referral_link,
                week_str=week,
            )
            sent += 1
            print(f"[weekly-brief] sent to {email_addr!r}", flush=True)

        except EmailSendError as exc:
            failed += 1
            print(f"[weekly-brief] SEND FAILED to {email_addr!r}: {exc}", flush=True)
        except Exception as exc:
            failed += 1
            print(f"[weekly-brief] unexpected error for {email_addr!r}: {exc}", flush=True)

    print(f"[weekly-brief] done — sent={sent} failed={failed}", flush=True)


if __name__ == "__main__":
    main()
