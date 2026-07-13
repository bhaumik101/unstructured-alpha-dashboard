#!/usr/bin/env python3
# cron/send_brief_subscribers.py
# Unstructured Alpha — Sunday Free Subscriber Brief Cron
#
# Runs every Sunday at 16:00 UTC (12:00 PM ET) — one hour after the Pro
# weekly brief (15:00 UTC). Sends the latest macro_narratives row to every
# contact in the Resend audience (landing page email capture), as a clean
# plain-English brief with a link to the public /brief page on the SEO service.
#
# This is the free-tier retention anchor: subscribers get value every Sunday
# without needing a dashboard account. The email CTA drives them to create one.
#
# REQUIRED ENV VARS:
#   DATABASE_URL       -- PostgreSQL connection string
#   RESEND_API_KEY     -- Resend API key
#   RESEND_FROM_EMAIL  -- Verified sending address (e.g. brief@unstructuredalpha.com)
#   RESEND_AUDIENCE_ID -- Resend audience ID for landing page subscribers
#
# OPTIONAL ENV VARS:
#   SEO_BASE_URL       -- Public URL of the SEO service (default: https://stocks.unstructuredalpha.com)
#   APP_BASE_URL       -- Public URL of the dashboard (default: https://unstructuredalpha.com)
#
# Run manually from dashboard/:
#   python -m cron.send_brief_subscribers

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap

import requests

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from utils.db import init_db, engine, macro_narratives
from sqlalchemy import select

_RESEND_API_URL  = "https://api.resend.com/emails"
_SEO_BASE_URL    = os.environ.get("SEO_BASE_URL", "https://stocks.unstructuredalpha.com").rstrip("/")
_APP_BASE_URL    = os.environ.get("APP_BASE_URL", "https://unstructuredalpha.com").rstrip("/")
_FROM_EMAIL      = os.environ.get("RESEND_FROM_EMAIL", "Unstructured Alpha <brief@unstructuredalpha.com>")
_API_KEY         = os.environ.get("RESEND_API_KEY", "")
_AUDIENCE_ID     = os.environ.get("RESEND_AUDIENCE_ID", "")


# ── Fetch latest brief from DB ────────────────────────────────────────────────

def _get_latest_brief() -> dict | None:
    """Return the most recent macro_narratives row as a dict, or None."""
    try:
        with engine.begin() as conn:
            row = conn.execute(
                select(
                    macro_narratives.c.id,
                    macro_narratives.c.headline,
                    macro_narratives.c.body,
                    macro_narratives.c.note_date,
                    macro_narratives.c.regime,
                    macro_narratives.c.bull_count,
                    macro_narratives.c.bear_count,
                )
                .where(macro_narratives.c.note_date.isnot(None))
                .order_by(macro_narratives.c.note_date.desc())
                .limit(1)
            ).mappings().fetchone()
        if row:
            return dict(row)
    except Exception as exc:
        print(f"[brief-subscribers] DB error fetching brief: {exc}", flush=True)
    return None


# ── Fetch Resend audience contacts ────────────────────────────────────────────

def _get_audience_contacts() -> list[dict]:
    """
    Return all non-unsubscribed contacts from the Resend audience.
    Each dict has at least: {email, first_name, unsubscribed}.
    Returns [] on any error.
    """
    if not _API_KEY or not _AUDIENCE_ID:
        print("[brief-subscribers] RESEND_API_KEY or RESEND_AUDIENCE_ID not set — skipping.", flush=True)
        return []

    url = f"https://api.resend.com/audiences/{_AUDIENCE_ID}/contacts"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {_API_KEY}"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        # Resend returns {"data": [...contacts...]}
        contacts = data.get("data", [])
        active = [c for c in contacts if not c.get("unsubscribed", False)]
        print(f"[brief-subscribers] audience contacts: {len(contacts)} total, {len(active)} active", flush=True)
        return active
    except Exception as exc:
        print(f"[brief-subscribers] Resend audience fetch failed: {exc}", flush=True)
        return []


# ── Build email HTML ──────────────────────────────────────────────────────────

def _build_brief_html(brief: dict, first_name: str = "") -> tuple[str, str]:
    """
    Build HTML email for the weekly brief.
    Returns (html_body, subject_line).
    """
    headline  = brief.get("headline") or "This Week's Macro Signal Brief"
    body      = brief.get("body") or ""
    note_date = brief.get("note_date") or ""
    regime    = brief.get("regime") or "MIXED / TRANSITION"
    bull_n    = brief.get("bull_count") or 0
    bear_n    = brief.get("bear_count") or 0

    # Format date
    date_str = ""
    if note_date:
        try:
            from datetime import datetime as _dt
            date_str = _dt.strptime(str(note_date)[:10], "%Y-%m-%d").strftime("%B %d, %Y")
        except Exception:
            date_str = str(note_date)[:10]

    # Truncate body to first 3 paragraphs for email preview (rest behind link)
    paras = [p.strip() for p in body.split("\n\n") if p.strip()]
    preview_paras = paras[:3]
    has_more = len(paras) > 3

    # Regime chip color
    regime_colors = {
        "RISK-ON":            "#00D566",
        "CAUTIOUSLY BULLISH": "#33A85D",
        "MIXED / TRANSITION": "#F59E0B",
        "CAUTIOUSLY BEARISH": "#E05C2E",
        "RISK-OFF":           "#FF4444",
    }
    regime_color = regime_colors.get(regime, "#6B7FBF")

    greeting = f"Hi {first_name}," if first_name else "Hi,"

    paras_html = "".join(
        f'<p style="color:#B8C0D4;font-size:15px;line-height:1.75;margin:0 0 14px;">{p}</p>'
        for p in preview_paras
    )

    more_html = (
        f'<p style="margin:20px 0 0;">'
        f'<a href="{_SEO_BASE_URL}/brief" style="color:#A78BFA;font-weight:600;text-decoration:none;">'
        f'Continue reading → full brief at stocks.unstructuredalpha.com</a></p>'
        if has_more else ""
    )

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#0A0D14;font-family:Inter,-apple-system,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:32px 20px;">

  <!-- Header -->
  <div style="margin-bottom:28px;">
    <div style="font-size:11px;font-weight:700;letter-spacing:0.14em;color:#6B7FBF;
                text-transform:uppercase;margin-bottom:6px;">Weekly Macro Brief</div>
    <div style="font-size:22px;font-weight:800;color:#E8EEFF;line-height:1.3;margin-bottom:12px;">
      {headline}
    </div>
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
      <span style="font-size:10px;font-weight:700;letter-spacing:0.10em;padding:3px 10px;
                   border-radius:3px;background:{regime_color}18;color:{regime_color};
                   border:1px solid {regime_color}33;">{regime}</span>
      <span style="font-size:12px;color:#6B7FBF;">{date_str} · {bull_n} bullish · {bear_n} bearish</span>
    </div>
  </div>

  <!-- Divider -->
  <div style="border-top:1px solid rgba(255,255,255,0.08);margin-bottom:24px;"></div>

  <!-- Greeting -->
  <p style="color:#C8D0E4;font-size:15px;margin:0 0 16px;">{greeting}</p>

  <!-- Brief body preview -->
  {paras_html}
  {more_html}

  <!-- Divider -->
  <div style="border-top:1px solid rgba(255,255,255,0.08);margin:28px 0;"></div>

  <!-- CTA -->
  <div style="background:rgba(167,139,250,0.07);border:1px solid rgba(167,139,250,0.20);
              border-radius:10px;padding:22px 24px;margin-bottom:24px;text-align:center;">
    <div style="font-size:14px;font-weight:700;color:#E8EEFF;margin-bottom:6px;">
      Want the full signal dashboard?
    </div>
    <div style="font-size:13px;color:#8892AA;margin-bottom:16px;line-height:1.5;">
      47 macro signals scored daily. Ticker Deep Dive. Model validation published in full.
      Free to start — no credit card.
    </div>
    <a href="{_APP_BASE_URL}" style="display:inline-block;background:#7C3AED;color:#fff;
       font-size:13px;font-weight:700;padding:10px 22px;border-radius:6px;text-decoration:none;">
      Open Dashboard →
    </a>
  </div>

  <!-- Disclaimer + unsubscribe -->
  <p style="font-size:11px;color:#4A5478;line-height:1.65;margin:0;">
    <strong style="color:#6B7FBF;">Not investment advice.</strong>
    Signal readings reflect publicly available data from FRED, SEC EDGAR, FINRA, EIA, and CBOE.
    Past performance does not predict future results. Do your own research.<br><br>
    You're receiving this because you subscribed at unstructuredalpha.com.
    <a href="{_SEO_BASE_URL}/brief" style="color:#4A5478;">Read in browser</a> ·
    To unsubscribe, reply with "unsubscribe" or manage your preferences via Resend.
  </p>

</div>
</body>
</html>"""

    subject = f"Weekly Macro Brief: {headline[:60]}{'…' if len(headline) > 60 else ''}"
    return html, subject


# ── Send one email ────────────────────────────────────────────────────────────

def _send_email(to_email: str, html: str, subject: str) -> bool:
    """Send a single email via Resend. Returns True on success."""
    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": _FROM_EMAIL,
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=20,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        print(f"[brief-subscribers] send failed to {to_email!r}: {exc}", flush=True)
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"[brief-subscribers] starting — {datetime.now(timezone.utc).isoformat()}", flush=True)

    if not _API_KEY:
        print("[brief-subscribers] RESEND_API_KEY not set — exiting.", flush=True)
        return

    init_db()

    brief = _get_latest_brief()
    if not brief:
        print("[brief-subscribers] no brief in DB — nothing to send.", flush=True)
        return

    print(
        f"[brief-subscribers] found brief id={brief['id']} date={brief['note_date']!r} "
        f"headline={brief['headline'][:60]!r}",
        flush=True,
    )

    contacts = _get_audience_contacts()
    if not contacts:
        print("[brief-subscribers] no active contacts — done.", flush=True)
        return

    sent = failed = 0
    for contact in contacts:
        email = (contact.get("email") or "").strip().lower()
        if not email:
            continue
        first_name = (contact.get("first_name") or "").strip()
        html, subject = _build_brief_html(brief, first_name=first_name)
        ok = _send_email(email, html, subject)
        if ok:
            sent += 1
        else:
            failed += 1

    print(f"[brief-subscribers] done — sent={sent} failed={failed}", flush=True)


if __name__ == "__main__":
    main()
