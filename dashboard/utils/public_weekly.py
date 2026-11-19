# utils/public_weekly.py
# Unstructured Alpha — the weekly public email: what moved, in plain words
#
# For anyone who signed up on a public page (utils/subscribers.py): once a
# week, after the library is re-measured, the readings that started or stopped
# holding up, and links back to the free tools. No account, no portfolio.
#
# RULES
#   * Built from the same comparison as /changes (utils/changes_page.changes),
#     so the email and the page never disagree. No week to compare, no email.
#   * Every email names why the person gets it and carries a one-click
#     unsubscribe link and List-Unsubscribe headers.
#   * Each address gets each data week once (subscribers.last_sent_week), so a
#     re-run never double-sends; a failed send is retried next run.
#   * Describes the past. No advice language.
#   * Sends only where RESEND_API_KEY is set and the sender is not Resend's
#     owner-only test address. The sign-up form is not shown until the SEO
#     service (which sends the confirmation) can send (enabled()).
#   * Kept free of Streamlit imports: it runs inside the SEO web service.

from __future__ import annotations

import os
from html import escape
from typing import Callable, Optional

RESEND_URL = "https://api.resend.com/emails"
SHOWN = 5


# Our verified sending domain; the same default the weekly portfolio job uses.
DEFAULT_SENDER = "Unstructured Alpha <brief@unstructuredalpha.com>"


def _config() -> tuple[str, str]:
    return os.environ.get("RESEND_API_KEY", ""), os.environ.get("RESEND_FROM_EMAIL", "") or DEFAULT_SENDER


def enabled() -> bool:
    """True when a send can actually go out from where this runs: a key, and a
    sender that is not Resend's owner-only test address."""
    key, sender = _config()
    return bool(key) and "resend.dev" not in sender


def _date(iso: str) -> str:
    from datetime import date
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _frame(body: str, base_url: str, why: str, unsub: str = "") -> str:
    foot = (f'<p><small>{why} It describes the past and is not a forecast or investment advice.'
            + (f' <a href="{escape(unsub)}">Unsubscribe</a>.' if unsub else "") + '</small></p>')
    return ('<div style="max-width:600px;margin:0 auto;padding:20px;font-family:Inter,Helvetica,Arial,sans-serif;'
            'color:#14213d;line-height:1.55">'
            f'<p><a href="{escape(base_url)}/" style="color:#14213d;font-weight:800;text-decoration:none">'
            'UNSTRUCTURED <span style="color:#d39b0f">ALPHA</span></a></p>'
            f'{body}<hr style="border:0;border-top:1px solid #e3e8f0;margin:22px 0">{foot}</div>')


def confirm_email(base_url: str, token: str) -> dict:
    link = f"{base_url}/subscribe/confirm?t={token}"
    body = ('<h1>Confirm your weekly email</h1>'
            '<p>Someone (we hope you) asked for the weekly Unstructured Alpha email at this address: which '
            'stocks&#39; links to interest rates, oil, the dollar and more started or stopped holding up '
            'this week, with the uncertainty shown.</p>'
            f'<p><a href="{escape(link)}" style="display:inline-block;background:#2f6fbd;color:#fff;padding:10px 16px;'
            'border-radius:8px;text-decoration:none;font-weight:700">Yes, send it weekly</a></p>'
            '<p>If this was not you, ignore this email and nothing more will be sent.</p>')
    return {"subject": "Confirm your weekly Unstructured Alpha email",
            "html": _frame(body, base_url, "You are getting this because this address was entered on "
                           "unstructuredalpha.com.")}


def _rows(rows: list, base_url: str, which: str) -> str:
    from utils.changes_page import _label
    from utils.exposure_pages import fmt_pct
    from utils.force_pages import FORCE_BY_KEY
    out = []
    for r in rows[:SHOWN]:
        e = r[which]
        force = FORCE_BY_KEY[r["key"]].label.lower() if r["key"] in FORCE_BY_KEY else r["key"]
        out.append(f'<li><a href="{escape(base_url)}/exposure/{escape(r["ticker"])}"><b>{escape(r["ticker"])}</b></a>'
                   + (f' {escape(r["name"])}' if r.get("name") else "")
                   + f' with {escape(force.replace("u.s.", "U.S."))}: {fmt_pct(e["impact"])} '
                   f'(90% range {fmt_pct(e["low"])} to {fmt_pct(e["high"])}, {escape(_label(e))})</li>')
    return "<ul>" + "".join(out) + "</ul>"


def weekly_email(base_url: str, c: dict, token: str) -> dict:
    """c: utils.changes_page.changes(latest, previous)."""
    unsub = f"{base_url}/unsubscribe?t={token}"
    g, lost = c.get("gained") or [], c.get("lost") or []
    parts = [f'<h1>What moved with the economy this week</h1>'
             f'<p>Data through {escape(_date(c["as_of"]))}. {c["compared"]:,} stocks and ETFs re-measured and '
             'compared with the week before. Each figure is a stock&#39;s typical weekly move beyond the '
             'market when a force moved by its standard amount, over three years.</p>']
    if g:
        parts.append(f'<h2>Started holding up ({len(g)})</h2>' + _rows(g, base_url, "now"))
    if lost:
        parts.append(f'<h2>Stopped holding up ({len(lost)})</h2>' + _rows(lost, base_url, "before"))
    if not g and not lost:
        parts.append('<p>No reading started or stopped holding up this week. Most links are stable from one '
                     'week to the next, and that is an answer too.</p>')
    parts.append(f'<p><a href="{escape(base_url)}/changes">Every change this week</a> · '
                 f'<a href="{escape(base_url)}/quiz">Today&#39;s quiz</a> · '
                 f'<a href="{escape(base_url)}/xray">X-ray a portfolio</a></p>')
    n = len(g) + len(lost)
    subject = (f"This week: {len(g)} links started holding up, {len(lost)} stopped" if n
               else "This week: the links held steady") + f" (data through {_date(c['as_of'])})"
    return {"subject": subject, "unsubscribe": unsub,
            "html": _frame("".join(parts), base_url, "You are getting this because you confirmed the weekly "
                           "email at unstructuredalpha.com.", unsub)}


def _post(to: str, mail: dict, kind: str, key: str, post: Optional[Callable] = None) -> bool:
    api_key, sender = _config()
    if post is None:
        import requests
        post = requests.post
    body = {"from": sender, "to": [to], "subject": mail["subject"], "html": mail["html"],
            "tags": [{"name": "email_type", "value": kind}]}
    if mail.get("unsubscribe"):
        body["headers"] = {"List-Unsubscribe": f"<{mail['unsubscribe']}>",
                           "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    r = post(RESEND_URL, json=body, timeout=15,
             headers={"Authorization": f"Bearer {api_key}", "Idempotency-Key": key[:256]})
    return 200 <= int(getattr(r, "status_code", 0) or 0) < 300


def send_confirmation(base_url: str, email: str, token: str, post: Optional[Callable] = None) -> bool:
    return _post(email, confirm_email(base_url, token), "public_confirm", f"confirm-{token}", post)


def run(base_url: str, load_latest: Callable[[], list], load_previous: Callable[[], list],
        post: Optional[Callable] = None) -> int:
    """Send this data week's email to every confirmed address not yet sent it.
    Returns 0, or 1 if any send failed (each failure is retried next run).
    The library is loaded only when someone is subscribed."""
    from utils import subscribers
    from utils.changes_page import changes
    if not enabled():
        print("[public-weekly] no verified sender configured; nothing sent", flush=True)
        return 0
    if not subscribers.counts().get("confirmed"):
        print("[public-weekly] no confirmed subscribers yet; nothing sent", flush=True)
        return 0
    c = changes(load_latest(), load_previous())
    if not c["as_of"] or not c["compared"]:
        print("[public-weekly] no week to compare; nothing sent", flush=True)
        return 0
    sent = failed = 0
    for email, token in subscribers.due(c["as_of"]):
        try:
            ok = _post(email, weekly_email(base_url, c, token), "public_weekly", f"weekly-{c['as_of']}-{token}", post)
        except Exception:
            ok = False
        if ok:
            subscribers.mark_sent(email, c["as_of"])
            sent += 1
        else:
            failed += 1
    print(f"[public-weekly] week={c['as_of']} sent={sent} failed={failed}", flush=True)
    return 1 if failed else 0


# ── The sign-up box on the public pages ────────────────────────────────────────
# Shown on the pages where "come back next week" fits, and only when sends can
# actually go out (enabled()). The answer shown is the same whatever happened:
# the endpoint never says whether an address was already on the list.
SIGNUP_PAGES = frozenset({"What changed", "Quiz", "Guess", "Learn", "X-ray"})

_SIGNUP_CSS = ('<style>.wk.card{position:relative;margin:34px 0 6px;padding:24px;border:0;color:#e6edf7;overflow:hidden;'
               'background:radial-gradient(600px 220px at 100% 0%,rgba(255,194,75,.16),transparent 60%),'
               'linear-gradient(160deg,var(--navy),var(--navy2));background-color:var(--navy)}'
               '.wk h2{margin:0 0 6px;color:#fff}.wk .small{color:#bccadd;max-width:60ch}'
               '.wk form{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}'
               '.wk input{flex:1 1 240px;min-height:46px;padding:0 14px;border:1px solid rgba(255,255,255,.22);'
               'border-radius:11px;font:inherit;background:rgba(255,255,255,.06);color:#fff}'
               '.wk input::placeholder{color:#91a6c2}.wk input:focus{outline:2px solid var(--bright);outline-offset:1px}'
               '.wk .btn{min-height:46px;border:0;cursor:pointer;font:inherit;font-weight:700}'
               '.wk #wk-say{color:#ffe2a3;margin-top:8px}</style>')

_SIGNUP_JS = r"""
(function(){
  var f = document.getElementById('wk-form'); if (!f) return;
  var say = document.getElementById('wk-say');
  f.addEventListener('submit', function(e){
    e.preventDefault();
    var email = document.getElementById('wk-email').value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { say.textContent = 'That does not look like an email address.'; return; }
    f.querySelector('button').disabled = true;
    fetch('/api/subscribe', {method: 'POST', headers: {'Content-Type': 'application/json'},
                             body: JSON.stringify({email: email, source: f.getAttribute('data-source')})})
      .then(function(r){ say.textContent = r.ok ? 'Check your inbox: one click in that email confirms it.'
                                                : 'Sign-up is not available right now. Please try again later.'; })
      .catch(function(){ say.textContent = 'Sign-up is not available right now. Please try again later.'; })
      .then(function(){ f.querySelector('button').disabled = false; });
  });
})();
"""


def signup_html(label: str | None) -> str:
    if label not in SIGNUP_PAGES or not enabled():
        return ""
    return (_SIGNUP_CSS + '<section class="card wk" aria-labelledby="wk-h"><h2 id="wk-h">The weekly email</h2>'
            '<p class="small">Once a week, after the new data: which stocks&#39; links to rates, oil, the dollar '
            'and more started or stopped holding up, with the uncertainty shown. No account. One-click '
            'unsubscribe.</p>'
            f'<form id="wk-form" data-source="{escape(label)}" novalidate>'
            '<label for="wk-email" class="sr-only" style="position:absolute;left:-9999px">Email address</label>'
            '<input id="wk-email" type="email" autocomplete="email" placeholder="you@example.com" maxlength="254" required>'
            '<button type="submit" class="btn btn-primary">Send it weekly</button></form>'
            '<p class="small" id="wk-say" aria-live="polite"></p></section>'
            f'<script>{_SIGNUP_JS}</script>')
