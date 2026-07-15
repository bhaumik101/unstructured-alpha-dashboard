#!/usr/bin/env python3
# cron/tweet_best_ideas.py
# Unstructured Alpha — Daily "Machine's Best Ideas" Tweet Cron
#
# Runs once daily at 14:00 UTC (10:00 AM ET) via Render Cron.
# Finds the top high-conviction + rising-momentum tickers and tweets a
# curated list as a daily market briefing.
#
# TWEET STRATEGY:
#   - 0 qualifying tickers: tweet a "no strong momentum" macro note
#   - 1–5 qualifying tickers: single tweet listing all with score + velocity
#
# QUALIFYING CRITERIA (same as pages/34_Best_Ideas.py):
#   - Confluence Score ≥ 65 (bullish threshold)
#   - Score velocity > 0 (score is rising, not stagnant)
#   - At least 6 historical velocity windows (trustworthy baseline)
#   - Top 5 ranked by rank_score = score + min(velocity×3, 12)
#
# REQUIRED ENV VARS:
#   TWITTER_API_KEY, TWITTER_API_SECRET,
#   TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET
#
# Run manually from dashboard/:
#   python -m cron.tweet_best_ideas

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

_SCORE_FLOOR  = 65.0
_RANK_VEL_CAP = 12.0
_TOP_N_TWEET  = 5
_UA_URL       = "unstructuredalpha.com/Best_Ideas"
_HASHTAGS     = "#stocks #macro #quant"


# ── Twitter credentials ───────────────────────────────────────────────────────

def _get_twitter_client():
    try:
        import tweepy
    except ImportError:
        raise RuntimeError("tweepy not installed — add tweepy>=4.14.0 to requirements.txt")

    keys = {
        "TWITTER_API_KEY":             os.environ.get("TWITTER_API_KEY", ""),
        "TWITTER_API_SECRET":          os.environ.get("TWITTER_API_SECRET", ""),
        "TWITTER_ACCESS_TOKEN":        os.environ.get("TWITTER_ACCESS_TOKEN", ""),
        "TWITTER_ACCESS_TOKEN_SECRET": os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", ""),
    }
    missing = [k for k, v in keys.items() if not v]
    if missing:
        raise RuntimeError(f"Missing Twitter env var(s): {', '.join(missing)}")

    return tweepy.Client(
        consumer_key=keys["TWITTER_API_KEY"],
        consumer_secret=keys["TWITTER_API_SECRET"],
        access_token=keys["TWITTER_ACCESS_TOKEN"],
        access_token_secret=keys["TWITTER_ACCESS_TOKEN_SECRET"],
    )


# ── Candidate computation ─────────────────────────────────────────────────────

def _get_best_ideas(top_n: int = _TOP_N_TWEET) -> list[dict]:
    """
    Returns up to `top_n` tickers that are bullish + rising, ranked by rank_score.
    Same logic as pages/34_Best_Ideas.py::_load_candidates().
    """
    from utils.signals_cache import get_all_signal_scores
    from utils.top_tickers import get_top_tickers
    from utils.score_history import get_batch_velocity_stats

    signal_scores = get_all_signal_scores()
    result = get_top_tickers(signal_scores_hash=len(signal_scores))
    all_rows = result.get("all", [])

    candidates = [r for r in all_rows if float(r.get("score", 0)) >= _SCORE_FLOOR]
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
            "velocity":   vel,
            "rank_score": float(row["score"]) + min(vel * 3, _RANK_VEL_CAP),
        })

    enriched.sort(key=lambda x: -x["rank_score"])
    return enriched[:top_n]


# ── Tweet construction ────────────────────────────────────────────────────────

def _build_tweet(ideas: list[dict], bias: str) -> str:
    today = datetime.now(timezone.utc).strftime("%b %-d")
    if not ideas:
        return (
            f"📊 Machine's Best Ideas — {today}\n\n"
            f"No tickers currently meet the high-conviction + rising criteria.\n"
            f"Overall macro bias: {bias}\n\n"
            f"{_UA_URL}\n{_HASHTAGS}"
        )

    lines = []
    for row in ideas:
        vel  = row["velocity"]
        sign = "+" if vel >= 0 else ""
        lines.append(
            f"🟢 {row['ticker']}: {row['score']:.0f}/100  ▲ {sign}{vel:.1f} pts/day"
        )

    body = "\n".join(lines)
    tweet = (
        f"🎯 Machine's Best Ideas — {today}\n\n"
        f"High conviction + rising score momentum:\n"
        f"{body}\n\n"
        f"28-signal macro engine · {_UA_URL}\n"
        f"{_HASHTAGS}"
    )
    # Twitter limit
    if len(tweet) > 280:
        # Trim ticker lines to first 3
        lines = lines[:3]
        body  = "\n".join(lines)
        tweet = (
            f"🎯 Machine's Best Ideas — {today}\n\n"
            f"{body}\n\n"
            f"+ more → {_UA_URL}\n"
            f"{_HASHTAGS}"
        )
    return tweet[:280]


# ── Main ──────────────────────────────────────────────────────────────────────

def _is_no_credits(exc) -> bool:
    """True if the error is X's paid-plan / no-credits paywall (402) — expected
    billing state, not a code bug."""
    s = str(exc).lower()
    return "402" in s or "payment required" in s or "credit" in s


def main() -> None:
    print(f"[best-ideas-tweet] starting — {datetime.now(timezone.utc).isoformat()}", flush=True)

    # Off-switch — set TWITTER_POSTING_ENABLED=false in Render to disable posting
    # entirely (e.g. while the X API account has no posting credits).
    if os.environ.get("TWITTER_POSTING_ENABLED", "true").strip().lower() in ("false", "0", "no", "off"):
        print("[best-ideas-tweet] SKIPPED — TWITTER_POSTING_ENABLED is off. No work done.", flush=True)
        return

    try:
        client = _get_twitter_client()
    except RuntimeError as exc:
        print(f"[best-ideas-tweet] ABORT — {exc}", flush=True)
        return

    from utils.db import init_db
    init_db()

    print("[best-ideas-tweet] computing candidates…", flush=True)
    ideas = _get_best_ideas()
    print(f"[best-ideas-tweet] {len(ideas)} qualifying ticker(s)", flush=True)
    for row in ideas:
        print(
            f"  {row['ticker']}  score={row['score']:.0f}  vel={row['velocity']:+.2f}  "
            f"rank={row['rank_score']:.1f}",
            flush=True,
        )

    # Get overall bias for no-results fallback
    bias = "Mixed"
    try:
        from utils.signals_cache import get_all_signal_scores
        scores = get_all_signal_scores()
        bull = sum(1 for v in scores.values() if v.get("status") == "bullish")
        bear = sum(1 for v in scores.values() if v.get("status") == "bearish")
        total = max(bull + bear + sum(1 for v in scores.values() if v.get("status") == "neutral"), 1)
        bias = "Bullish" if bull / total >= 0.5 else ("Bearish" if bear / total >= 0.5 else "Mixed")
    except Exception:
        pass

    tweet_text = _build_tweet(ideas, bias)
    print(f"[best-ideas-tweet] tweet ({len(tweet_text)} chars):\n{tweet_text}", flush=True)

    try:
        resp = client.create_tweet(text=tweet_text)
        tweet_id = resp.data.get("id")
        print(f"[best-ideas-tweet] posted — id={tweet_id}", flush=True)
    except Exception as exc:
        if _is_no_credits(exc):
            print("[best-ideas-tweet] SKIPPED — X API account has no posting credits (paid tier "
                  "required). Set TWITTER_POSTING_ENABLED=false in Render to silence this.", flush=True)
        else:
            print(f"[best-ideas-tweet] Twitter API error: {type(exc).__name__}: {exc}", flush=True)

    print("[best-ideas-tweet] done.", flush=True)


if __name__ == "__main__":
    main()
