"""The weekly public email: sign-up, confirmation and unsubscribe.

Endpoints (proxied through www by next.config.ts):
  POST /api/subscribe          {email, source} -> always {"ok": true} (same answer whatever
                               happened, so the list cannot be probed); the confirmation is
                               sent after the response.
  GET  /subscribe/confirm?t=   a page with a button; POST confirms.
  GET  /unsubscribe?t=         a page with a button; POST unsubscribes (also the RFC 8058
                               one-click target named in every email's List-Unsubscribe).

Why buttons, not bare links: mail scanners open links in incoming email. A link
that confirmed or unsubscribed on GET would let a scanner do either on the
reader's behalf. See utils/subscribers.py and utils/public_weekly.py for the
rules.
"""

from __future__ import annotations

import json
import logging
import os
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_BODY = 1024


def _base() -> str:
    return os.environ.get("SEO_BASE_URL", "https://seo.unstructuredalpha.com")


def _app() -> str:
    return os.environ.get("APP_URL", "https://app.unstructuredalpha.com")


def _page(title: str, body: str, path: str) -> HTMLResponse:
    from utils.exposure_pages import _shell
    html = _shell(title, title, f"{_base()}{path}", {"@context": "https://schema.org", "@type": "WebPage",
                                                     "name": title}, body, _app(), robots="noindex, nofollow")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


async def _token(request: Request) -> str:
    t = request.query_params.get("t", "")
    if request.method == "POST" and not t:
        raw = (await request.body())[:MAX_BODY].decode("utf-8", "ignore")
        t = (parse_qs(raw).get("t") or [""])[0]
    return t.strip()[:64]


def _button_page(title: str, lead: str, action: str, token: str, label: str, path: str) -> HTMLResponse:
    body = (f'<h1>{escape(title)}</h1><p class="lead">{lead}</p>'
            f'<form method="post" action="{action}"><input type="hidden" name="t" value="{escape(token)}">'
            f'<button type="submit" class="btn btn-primary">{escape(label)}</button></form>')
    return _page(title, body, path)


@router.post("/api/subscribe")
async def subscribe(request: Request, background: BackgroundTasks) -> JSONResponse:
    from utils import public_weekly, subscribers
    ok = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
    if not public_weekly.enabled():
        return JSONResponse({"ok": False}, status_code=503)
    try:
        raw = await request.body()
        if len(raw) > MAX_BODY:
            return ok
        payload = json.loads(raw or b"{}")
        if not isinstance(payload, dict):
            return ok
        email, source = str(payload.get("email") or ""), str(payload.get("source") or "")
        from seo.main import _get_engine
        _get_engine()
        holder: dict = {}

        def remember(e: str, t: str) -> bool:      # send after the response, not inside it
            holder["e"], holder["t"] = e, t
            return True
        outcome = subscribers.subscribe(email, source, send=remember)
        if outcome == "sent" and holder:
            background.add_task(public_weekly.send_confirmation, _base(), holder["e"], holder["t"])
        logger.info("[subscribe] outcome=%s source=%s", outcome, source[:40])
    except Exception as exc:          # the visitor sees the same answer either way
        logger.warning("[subscribe] dropped: %s", type(exc).__name__)
    return ok


@router.get("/subscribe/confirm", response_class=HTMLResponse)
async def confirm_page(request: Request) -> HTMLResponse:
    t = await _token(request)
    return _button_page("Confirm your weekly email", "One click and the weekly email starts: which stocks&#39; "
                        "links to the economy started or stopped holding up, with the uncertainty shown.",
                        "/subscribe/confirm", t, "Yes, send it weekly", "/subscribe/confirm")


@router.post("/subscribe/confirm", response_class=HTMLResponse)
async def confirm(request: Request) -> HTMLResponse:
    from seo.main import _get_engine
    from utils import subscribers
    _get_engine()
    if subscribers.confirm(await _token(request)):
        body = ('<h1>You are subscribed</h1><p class="lead">The first email comes after the next weekly '
                'measurement. Every email has a one-click unsubscribe link.</p>'
                '<div class="actions"><a class="btn btn-primary" href="/quiz">Today&#39;s quiz</a>'
                '<a class="btn btn-secondary" href="/xray">X-ray a portfolio</a></div>')
    else:
        body = ('<h1>That link did not work</h1><p class="lead">It may be from an older email, or the address '
                'was unsubscribed. You can sign up again from any page.</p>')
    return _page("Weekly email", body, "/subscribe/confirm")


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_page(request: Request) -> HTMLResponse:
    t = await _token(request)
    return _button_page("Unsubscribe from the weekly email", "One click and no more weekly emails go to "
                        "this address.", "/unsubscribe", t, "Unsubscribe", "/unsubscribe")


@router.post("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(request: Request) -> HTMLResponse:
    from seo.main import _get_engine
    from utils import subscribers
    _get_engine()
    done = subscribers.unsubscribe(await _token(request))
    body = ('<h1>You are unsubscribed</h1><p class="lead">No more weekly emails will go to this address.</p>'
            if done else '<h1>That link did not work</h1><p class="lead">It may be from an older email.</p>')
    return _page("Weekly email", body, "/unsubscribe")
