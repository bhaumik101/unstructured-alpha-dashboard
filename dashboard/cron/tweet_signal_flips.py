#!/usr/bin/env python3
# cron/tweet_signal_flips.py
# Unstructured Alpha — Daily Signal-Flip Tweet Cron
#
# Runs once daily at 13:00 UTC (9:00 AM ET) via Render Cron.
# Computes the current macro signal state, detects flips since yesterday,
# and tweets a concise market briefing via the @UnstructuredAlpha Twitter/X
# account using the Twitter API v2 (OAuth 1.0a user context).
#
# TWEET STRATEGY:
#   - 0 flips:     tweet the overall macro bias + signal count as a brief pulse
#   - 1-2 flips:   one tweet per flip (precise, signal-named, score included)
#   - 3+ flips:    one summary tweet listing all tickers + direction, then
#                  a reply thread for the top 2 flips with detail
#
# DUPLICATE PROTECTION:
#   This cron runs once per day. By querying flips with days_back=1, each
#   signal flip is only visible during its first 24-hour window. As long as the
#   cron fires reliably at the same time daily, no flip gets tweeted twice.
#   (A flip that occurred 23 hours ago will show up today but not tomorrow.)
#
# REQUIRED ENV VARS (set in Render dashboard, never in source):
#   TWITTER_API_KEY             — OAuth 1.0a Consumer Key
#   TWITTER_API_SECRET          — OAuth 1.0a Consumer Secret
#   TWITTER_ACCESS_TOKEN        — OAuth 1.0a Access Token (account-level)
#   TWITTER_ACCESS_TOKEN_SECRET — OAuth 1.0a Access Token Secret
#
# IMPORTANT: This script runs OUTSIDE Streamlit. Do NOT import anything that
# calls st.* at module level.
#
# Run manually (from the dashboard/ directory):
#   python -m cron.tweet_signal_flips
# or:
#   python cron/tweet_signal_flips.py

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_here = Path(__file__).resolve().parent.parent   # dashboard/
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))


# ── Twitter credentials ───────────────────────────────────────────────────────

def _get_twitter_client():
    """
    Return a tweepy.Client (v2) wired for user-context OAuth 1.0a.
    Raises RuntimeError if any of the four required env vars are missing.
    """
    try:
        import tweepy
    except ImportError:
        raise RuntimeError(
            "tweepy is not installed — add 'tweepy>=4.14.0' to requirements.txt"
        )

    api_key    = os.environ.get("TWITTER_API_KEY", "")
    api_secret = os.environ.get("TWITTER_API_SECRET", "")
    acc_token  = os.environ.get("TWITTER_ACCESS_TOKEN", "")
    acc_secret = os.environ.get("TWITTER_ACCESS_TOKEN_SECRET", "")

    missing = [
        name for name, val in [
            ("TWITTER_API_KEY", api_key),
            ("TWITTER_API_SECRET", api_secret),
            ("TWITTER_ACCESS_TOKEN", acc_token),
            ("TWITTER_ACCESS_TOKEN_SECRET", acc_secret),
        ] if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing Twitter env var(s): {', '.join(missing)}"
        )

    return tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=acc_token,
        access_token_secret=acc_secret,
    )


# ── Signal pulse (no Streamlit cache) ────────────────────────────────────────

def _compute_signal_pulse() -> tuple[dict, int, int, int, str]:
    """
    Score all macro signals. Same logic as send_digest.py::_compute_signal_pulse()
    but duplicated here so this cron has no runtime import dependency on the
    digest cron (and because cron modules shouldn't import each other).

    Returns (scores_dict, bull_n, bear_n, neut_n, overall_bias_str)
    """
    from utils.fetchers import fetch_signal_series
    from utils.analysis import score_signal
    from utils.config import SIGNALS

    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    scores, bull, bear, neut = {}, 0, 0, 0
    for sig_id, cfg in SIGNALS.items():
        try:
            s      = fetch_signal_series(cfg, start, end)
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
            print(f"[tweet] signal {sig_id} failed: {exc}", flush=True)
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


# ── Tweet helpers ─────────────────────────────────────────────────────────────

_HASHTAGS = "#stocks #investing #quant"
_UA_URL = "unstructuredalpha.com"

_BIAS_EMOJI = {"Bullish": "📈", "Bearish": "📉", "Mixed": "⚖️"}
_DIR_EMOJI  = {"bullish": "▲", "bearish": "▼", "neutral": "●"}
_DIR_WORD   = {"bullish": "Bullish", "bearish": "Bearish", "neutral": "Neutral"}


def _tweet_pulse_only(client, bull_n: int, bear_n: int, neut_n: int, bias: str) -> None:
    """No flips today — tweet the overall macro bias as a daily pulse."""
    emoji = _BIAS_EMOJI.get(bias, "📊")
    total = bull_n + bear_n + neut_n

    body = (
        f"{emoji} Daily macro signal pulse\n\n"
        f"Bias: {bias.upper()}\n"
        f"▲ {bull_n} bullish  ▼ {bear_n} bearish  ● {neut_n} neutral\n"
        f"({total} independent data series)\n\n"
        f"{_UA_URL}\n"
        f"{_HASHTAGS}"
    )
    resp = client.create_tweet(text=body[:280])
    tweet_id = resp.data.get("id")
    print(f"[tweet] pulse tweet posted — id={tweet_id}", flush=True)


def _tweet_single_flip(client, flip: dict) -> str | None:
    """Tweet one signal flip. Returns tweet ID."""
    sig_name  = flip.get("signal_name", flip.get("signal_id", "A macro signal"))
    to_status = flip.get("to_status", "neutral").lower()
    fr_status = flip.get("from_status", "neutral").lower()
    score     = flip.get("to_score", 50)

    to_dir = _DIR_EMOJI.get(to_status, "●")
    fr_dir = _DIR_EMOJI.get(fr_status, "●")
    to_word = _DIR_WORD.get(to_status, to_status.title())

    body = (
        f"⚡ Signal flip: {sig_name}\n\n"
        f"{fr_dir} → {to_dir} {to_word}  ({score:.0f}/100)\n\n"
        f"Tracked in real-time at {_UA_URL}\n"
        f"{_HASHTAGS}"
    )
    resp = client.create_tweet(text=body[:280])
    tweet_id = resp.data.get("id")
    print(f"[tweet] flip tweet posted — id={tweet_id} signal={sig_name!r}", flush=True)
    return tweet_id


def _tweet_multi_flip_summary(
    client,
    flips: list[dict],
    bull_n: int,
    bear_n: int,
    bias: str,
) -> None:
    """
    Post a summary tweet + up to 2 reply thread tweets for 3+ flips.
    """
    emoji = _BIAS_EMOJI.get(bias, "📊")
    n = len(flips)

    # Build signal name list (truncated to fit)
    names = [f.get("signal_name", f.get("signal_id", "?")) for f in flips[:5]]
    names_str = ", ".join(names)
    if len(names_str) > 80:
        names_str = names_str[:77] + "…"

    summary = (
        f"{emoji} {n} macro signals flipped direction today\n\n"
        f"Signals: {names_str}\n\n"
        f"Overall bias: {bias}  (▲{bull_n} bull / ▼{bear_n} bear)\n\n"
        f"{_UA_URL}\n"
        f"{_HASHTAGS}"
    )
    resp = client.create_tweet(text=summary[:280])
    parent_id = resp.data.get("id")
    print(f"[tweet] summary tweet posted — id={parent_id} n_flips={n}", flush=True)

    # Reply thread: top 2 flips in detail
    for flip in flips[:2]:
        sig_name  = flip.get("signal_name", flip.get("signal_id", "Signal"))
        to_status = flip.get("to_status", "neutral").lower()
        fr_status = flip.get("from_status", "neutral").lower()
        score     = flip.get("to_score", 50)

        to_dir  = _DIR_EMOJI.get(to_status, "●")
        fr_dir  = _DIR_EMOJI.get(fr_status, "●")
        to_word = _DIR_WORD.get(to_status, to_status.title())

        reply_text = (
            f"{sig_name}\n"
            f"{fr_dir} → {to_dir} {to_word}  (score: {score:.0f}/100)\n\n"
            f"See the full signal chart at {_UA_URL}"
        )
        r = client.create_tweet(
            text=reply_text[:280],
            in_reply_to_tweet_id=parent_id,
        )
        parent_id = r.data.get("id")   # thread continuation
        print(f"[tweet] reply thread tweet posted — id={parent_id}", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def _is_no_credits(exc) -> bool:
    """True if the error is X's paid-plan / no-credits paywall (402) — an expected
    billing state, not a code bug. Keeps daily logs from looking alarming."""
    s = str(exc).lower()
    return "402" in s or "payment required" in s or "credit" in s


def main() -> None:
    print(
        f"[tweet] starting at {datetime.now(timezone.utc).isoformat()}",
        flush=True,
    )

    # 0. Global off-switch — set TWITTER_POSTING_ENABLED=false in Render to disable
    #    posting entirely (e.g. while the X API account has no posting credits), so
    #    this cron does no work and logs nothing alarming. Auto-resumes if unset.
    if os.environ.get("TWITTER_POSTING_ENABLED", "true").strip().lower() in ("false", "0", "no", "off"):
        print("[tweet] SKIPPED — TWITTER_POSTING_ENABLED is off. No work done.", flush=True)
        return

    # 1. Build Twitter client — bail early if credentials are missing
    try:
        client = _get_twitter_client()
    except RuntimeError as exc:
        print(f"[tweet] ABORT — {exc}", flush=True)
        return

    # 2. Initialize DB and compute signal state
    from utils.db import init_db
    from utils.config import SIGNALS
    from utils.score_history import get_signal_flips

    init_db()

    print("[tweet] computing signal pulse…", flush=True)
    signal_scores, bull_n, bear_n, neut_n, bias = _compute_signal_pulse()
    print(
        f"[tweet] pulse: bull={bull_n} bear={bear_n} neut={neut_n} bias={bias}",
        flush=True,
    )

    # 3. Get flips from the past 24 hours
    flips = get_signal_flips(days_back=1)
    # Annotate with human-readable signal name
    for f in flips:
        f["signal_name"] = SIGNALS.get(f["signal_id"], {}).get("name", f["signal_id"])
    print(f"[tweet] {len(flips)} flip(s) since yesterday", flush=True)

    # 4. Tweet
    try:
        if len(flips) == 0:
            _tweet_pulse_only(client, bull_n, bear_n, neut_n, bias)
        elif len(flips) <= 2:
            for flip in flips:
                _tweet_single_flip(client, flip)
        else:
            _tweet_multi_flip_summary(client, flips, bull_n, bear_n, bias)
    except Exception as exc:
        if _is_no_credits(exc):
            print("[tweet] SKIPPED — the X API account has no posting credits (paid tier "
                  "required to post). Set TWITTER_POSTING_ENABLED=false in Render to silence "
                  "this. Tweet not sent.", flush=True)
        else:
            print(f"[tweet] Twitter API error: {type(exc).__name__}: {exc}", flush=True)
        return

    print("[tweet] done.", flush=True)


if __name__ == "__main__":
    main()
