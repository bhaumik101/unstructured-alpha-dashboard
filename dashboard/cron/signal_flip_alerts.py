#!/usr/bin/env python3
# cron/signal_flip_alerts.py
# Unstructured Alpha — Signal Flip Alert Email Cron
#
# Runs every 2 hours via Render Cron. For every verified user with a watchlist,
# detects macro signal status flips (bullish ↔ neutral ↔ bearish) and emails
# a personalized alert showing which of THEIR tickers are most exposed.
#
# DE-DUPLICATION: signal_flip_log table ensures we send at most ONE email per
# (signal, calendar day) pair regardless of how many times this cron fires.
# A signal that flips bullish at 9am and gets logged won't re-alert at 11am.
#
# PERSONALIZATION: We don't blast every user about every flip. For each flip,
# we find which sectors use that signal (via SECTOR_SIGNAL_MAP), then only
# email users whose watchlist contains tickers in those affected sectors.
# A user with only energy stocks doesn't hear about a healthcare signal flip.
#
# SIGNAL CONTEXT: The email includes the signal's name, what it measures
# (from SIGNALS config "description"), and the new direction, plus the 2-3
# most exposed tickers from the user's watchlist.
#
# Run manually (from the dashboard/ directory):
#   python -m cron.signal_flip_alerts
#
# IMPORTANT: runs OUTSIDE Streamlit. No st.* imports at module level.
# All config via environment variables (DATABASE_URL, RESEND_API_KEY,
# RESEND_FROM_EMAIL, FRED_API_KEY, EIA_API_KEY).

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Ensure dashboard/ is on sys.path so utils.* imports resolve correctly
_here = Path(__file__).resolve().parent.parent  # dashboard/
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import requests
from sqlalchemy import select, delete

from utils import db
from utils.db import init_db, signal_flip_log, watchlist, users, upsert_stmt
from utils.config import SIGNALS, TICKERS
from utils.score_history import get_signal_flips
from utils.ticker_score import SECTOR_SIGNAL_MAP


# ── Email helpers ─────────────────────────────────────────────────────────────

_DEFAULT_FROM  = "Unstructured Alpha <onboarding@resend.dev>"
_RESEND_URL    = "https://api.resend.com/emails"
_SITE_URL      = os.environ.get("RENDER_EXTERNAL_URL", "https://unstructuredalpha.com")


def _resend_config() -> tuple[str, str]:
    api_key    = os.environ.get("RESEND_API_KEY", "")
    from_email = os.environ.get("RESEND_FROM_EMAIL", _DEFAULT_FROM)
    return api_key, from_email


def _send_email(to: str, subject: str, html: str, api_key: str, from_email: str) -> bool:
    """POST to Resend. Returns True on success."""
    try:
        resp = requests.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            data=json.dumps({"from": from_email, "to": [to], "subject": subject, "html": html}),
            timeout=10,
        )
        return resp.status_code in (200, 201)
    except Exception as e:
        print(f"[flip-alerts] email send error: {e}", flush=True)
        return False


# ── Reverse index: signal_id → sectors that use it ───────────────────────────

def _build_signal_sector_map() -> dict[str, list[str]]:
    """Return {signal_id: [sector, ...]} built from SECTOR_SIGNAL_MAP."""
    result: dict[str, list[str]] = defaultdict(list)
    for sector, sig_ids in SECTOR_SIGNAL_MAP.items():
        for sig_id in sig_ids:
            result[sig_id].append(sector)
    return dict(result)


def _build_sector_tickers() -> dict[str, list[str]]:
    """Return {sector: [ticker, ...]} from the TICKERS config."""
    result: dict[str, list[str]] = defaultdict(list)
    for ticker, meta in TICKERS.items():
        sector = meta.get("sector", "")
        if sector:
            result[sector].append(ticker)
    return dict(result)


# ── Already-alerted check ─────────────────────────────────────────────────────

def _already_alerted(signal_id: str, today: str) -> bool:
    """Return True if we already logged an alert for this signal today."""
    with db.engine.begin() as conn:
        row = conn.execute(
            select(signal_flip_log.c.id)
            .where(
                signal_flip_log.c.signal_id == signal_id,
                signal_flip_log.c.flip_date  == today,
            )
            .limit(1)
        ).first()
    return row is not None


def _log_flip(signal_id: str, today: str, from_status: str, to_status: str, n_users: int) -> None:
    """Upsert a flip log row. Safe to call even if the row already exists."""
    now_iso = datetime.now(timezone.utc).isoformat()
    stmt = upsert_stmt(signal_flip_log, ["signal_id", "flip_date"]).values(
        signal_id=signal_id, flip_date=today,
        from_status=from_status, to_status=to_status,
        n_users_alerted=n_users, alerted_at=now_iso,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["signal_id", "flip_date"],
        set_={"n_users_alerted": n_users, "alerted_at": now_iso},
    )
    with db.engine.begin() as conn:
        conn.execute(stmt)


# ── Per-user watchlist fetcher ────────────────────────────────────────────────

def _get_user_watchlist_tickers(user_id: int) -> list[str]:
    with db.engine.begin() as conn:
        rows = conn.execute(
            select(watchlist.c.ticker).where(watchlist.c.user_id == user_id)
        ).mappings().all()
    return [r["ticker"] for r in rows]


# ── Email HTML builder ────────────────────────────────────────────────────────

def _flip_html(
    flips: list[dict],
    exposed_tickers: list[str],
    user_email: str,
) -> tuple[str, str]:
    """
    Build (html, subject) for a signal flip alert email.

    flips: list of flip dicts from get_signal_flips()
    exposed_tickers: user's watchlist tickers that are affected
    """
    from datetime import date
    today_str = date.today().strftime("%B %-d, %Y")

    DIRECTION_COLOR = {"bullish": "#00D566", "bearish": "#FF4B4B", "neutral": "#6B7FBF"}
    DIRECTION_ICON  = {"bullish": "▲", "bearish": "▼", "neutral": "●"}
    DIRECTION_LABEL = {"bullish": "BULLISH", "bearish": "BEARISH", "neutral": "NEUTRAL"}

    n = len(flips)
    flip_noun = "Signal" if n == 1 else "Signals"

    # Build flip rows
    flip_rows_html = ""
    for f in flips[:5]:  # cap at 5 in email
        sig_id  = f["signal_id"]
        cfg     = SIGNALS.get(sig_id, {})
        name    = cfg.get("name", sig_id.replace("_", " ").title())
        desc    = cfg.get("description", "")
        # Clip description to 120 chars
        if len(desc) > 120:
            desc = desc[:117] + "…"
        from_st = f["from_status"]
        to_st   = f["to_status"]
        to_col  = DIRECTION_COLOR.get(to_st, "#8892AA")
        from_col = DIRECTION_COLOR.get(from_st, "#8892AA")
        to_icon  = DIRECTION_ICON.get(to_st, "●")

        flip_rows_html += f"""
        <tr>
          <td style="padding:14px 16px;border-bottom:1px solid rgba(255,255,255,0.05);">
            <div style="font-size:0.95rem;font-weight:700;color:#E8EEFF;
                        font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
                        margin-bottom:3px;">
              <span style="color:{to_col};margin-right:6px;">{to_icon}</span>{name}
            </div>
            <div style="font-size:0.75rem;color:#8892AA;line-height:1.5;
                        font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
              {desc}
            </div>
            <div style="margin-top:6px;display:flex;gap:8px;align-items:center;">
              <span style="font-size:0.68rem;color:{from_col};
                           font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
                {DIRECTION_LABEL.get(from_st, from_st.upper())}
              </span>
              <span style="color:#4A5568;font-size:0.68rem;">→</span>
              <span style="font-size:0.68rem;font-weight:700;color:{to_col};
                           background:rgba(0,0,0,0.3);padding:2px 8px;border-radius:8px;
                           border:1px solid {to_col}44;
                           font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
                {DIRECTION_LABEL.get(to_st, to_st.upper())}
              </span>
            </div>
          </td>
        </tr>"""

    # Exposed tickers section
    ticker_chips_html = ""
    if exposed_tickers:
        chips = ""
        for t in exposed_tickers[:6]:
            chips += (
                f'<span style="display:inline-block;background:rgba(124,58,237,0.15);'
                f'border:1px solid rgba(124,58,237,0.35);border-radius:20px;'
                f'padding:3px 10px;margin:2px;font-size:0.68rem;font-weight:700;color:#A78BFA;'
                f'font-family:-apple-system,BlinkMacSystemFont,\'Inter\',sans-serif;">'
                f'{t}</span>'
            )
        ticker_chips_html = f"""
        <div style="padding:14px 16px;border-bottom:1px solid rgba(255,255,255,0.05);">
          <div style="font-size:0.62rem;font-weight:700;color:#6B7FBF;
                      text-transform:uppercase;letter-spacing:0.10em;margin-bottom:8px;
                      font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
            Your Watchlist — Exposed Tickers
          </div>
          <div style="line-height:2.0;">{chips}</div>
        </div>"""

    # Subject
    if n == 1:
        f0      = flips[0]
        sig_nm  = SIGNALS.get(f0["signal_id"], {}).get("name", f0["signal_id"])
        to_dir  = f0["to_status"].capitalize()
        subject = f"⚡ Signal Flip: {sig_nm} just turned {to_dir.upper()}"
    else:
        subject = f"⚡ {n} Macro Signal Flips — Your Watchlist Is Exposed"

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0B0D12;">
<div style="max-width:560px;margin:0 auto;background:#12151E;
            font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#7C3AED 0%,#12151E 100%);
              padding:24px 28px;border-radius:12px 12px 0 0;">
    <div style="font-size:0.58rem;color:#A78BFA;letter-spacing:0.14em;
                text-transform:uppercase;margin-bottom:5px;">
      UNSTRUCTURED ALPHA · SIGNAL ALERT
    </div>
    <div style="font-size:1.35rem;font-weight:800;color:#FFFFFF;line-height:1.2;">
      {n} Macro {flip_noun} Just Flipped
    </div>
    <div style="font-size:0.80rem;color:#B8C0D4;margin-top:6px;">{today_str}</div>
  </div>

  <!-- Flip rows -->
  <table width="100%" style="border-collapse:collapse;">
    {flip_rows_html}
  </table>

  <!-- Exposed tickers -->
  {ticker_chips_html}

  <!-- CTA -->
  <div style="padding:20px 16px;">
    <a href="{_SITE_URL}" target="_blank"
       style="display:inline-block;background:#7C3AED;color:#FFFFFF;
              font-size:0.82rem;font-weight:700;padding:11px 24px;
              border-radius:8px;text-decoration:none;
              font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
      View Signal Dashboard →
    </a>
    <div style="font-size:0.68rem;color:#4A5568;margin-top:16px;line-height:1.6;">
      You're receiving this because you have a watchlist on Unstructured Alpha
      with tickers exposed to these signals.<br>
      These are data observations, not financial advice.
    </div>
  </div>

</div>
</body>
</html>"""

    return html, subject


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(
        f"[flip-alerts] starting at {datetime.now(timezone.utc).isoformat()}",
        flush=True,
    )

    init_db()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Detect flips (2-day window to catch anything the last run might have missed)
    all_flips: list[dict] = get_signal_flips(days_back=2)
    if not all_flips:
        print("[flip-alerts] no signal flips in last 2 days — done.", flush=True)
        return

    # 2. Filter to flips not already alerted today
    new_flips = [f for f in all_flips if not _already_alerted(f["signal_id"], today)]
    if not new_flips:
        print(
            f"[flip-alerts] {len(all_flips)} flip(s) found but all already alerted today — done.",
            flush=True,
        )
        return

    print(
        f"[flip-alerts] {len(new_flips)} new flip(s) to alert: "
        f"{[f['signal_id'] for f in new_flips]}",
        flush=True,
    )

    # 3. Build sector/ticker lookup structures
    signal_to_sectors = _build_signal_sector_map()
    sector_to_tickers = _build_sector_tickers()

    # For each new flip, compute the set of affected tickers
    flip_affected_tickers: dict[str, set[str]] = {}
    for f in new_flips:
        sig_id   = f["signal_id"]
        sectors  = signal_to_sectors.get(sig_id, [])
        affected: set[str] = set()
        for sector in sectors:
            affected.update(sector_to_tickers.get(sector, []))
        # Also include tickers that explicitly list this signal
        for ticker, meta in TICKERS.items():
            if sig_id in meta.get("signals", []):
                affected.add(ticker)
        flip_affected_tickers[sig_id] = affected

    # Global set of all tickers touched by any new flip
    all_affected_tickers: set[str] = set()
    for tickers in flip_affected_tickers.values():
        all_affected_tickers.update(tickers)

    # 4. Get verified watchlist users
    with db.engine.begin() as conn:
        user_rows = conn.execute(
            select(users.c.id, users.c.email)
            .where(users.c.email_verified == True)   # noqa: E712
            .where(users.c.digest_opted_in == True)  # noqa: E712
            .where(
                users.c.id.in_(select(watchlist.c.user_id).distinct())
            )
        ).mappings().all()

    print(f"[flip-alerts] {len(user_rows)} opted-in watchlist user(s) to check", flush=True)

    if not user_rows:
        # Still log the flips even if no users to alert
        for f in new_flips:
            _log_flip(f["signal_id"], today, f["from_status"], f["to_status"], n_users=0)
        print("[flip-alerts] no opted-in watchlist users — flips logged, done.", flush=True)
        return

    api_key, from_email = _resend_config()
    if not api_key:
        print("[flip-alerts] no RESEND_API_KEY configured — cannot send emails.", flush=True)
        return

    # 5. For each user: find their exposed tickers, send if any overlap
    users_alerted_per_flip: dict[str, int] = {f["signal_id"]: 0 for f in new_flips}
    total_sent = 0
    total_skipped = 0

    for u in user_rows:
        user_id = u["id"]
        email   = u["email"]

        user_tickers = set(_get_user_watchlist_tickers(user_id))
        if not user_tickers:
            continue

        # Which of their tickers are exposed to ANY new flip?
        exposed = list(user_tickers & all_affected_tickers)
        if not exposed:
            total_skipped += 1
            continue

        # Which flips are actually relevant to this user?
        user_flips = [
            f for f in new_flips
            if user_tickers & flip_affected_tickers[f["signal_id"]]
        ]
        if not user_flips:
            total_skipped += 1
            continue

        # Build and send email
        html, subject = _flip_html(user_flips, sorted(exposed)[:6], email)
        ok = _send_email(email, subject, html, api_key, from_email)

        if ok:
            total_sent += 1
            for f in user_flips:
                users_alerted_per_flip[f["signal_id"]] += 1
            print(f"[flip-alerts] ✓ sent to {email!r} ({len(user_flips)} flips, {len(exposed)} exposed tickers)", flush=True)
        else:
            print(f"[flip-alerts] ✗ failed to send to {email!r}", flush=True)

    # 6. Log all new flips (one row per flip, regardless of how many users were emailed)
    for f in new_flips:
        _log_flip(
            f["signal_id"], today,
            f["from_status"], f["to_status"],
            n_users=users_alerted_per_flip[f["signal_id"]],
        )

    print(
        f"[flip-alerts] done. sent={total_sent} skipped={total_skipped} "
        f"flips_logged={len(new_flips)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
