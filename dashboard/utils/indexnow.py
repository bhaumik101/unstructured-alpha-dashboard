# utils/indexnow.py
# Unstructured Alpha — tell search engines when the public pages change
#
# IndexNow (indexnow.org) is an open protocol: one POST lists changed URLs and
# every participating engine (Bing -- which also feeds DuckDuckGo and ChatGPT
# search --, Yandex, Seznam, Naver) learns of them at once instead of waiting
# to recrawl. The stock, sector and force pages all change every week when the
# library is re-measured, which is exactly the case it exists for.
#
# RULES
#   * The key is public by design: it proves we control the host because the
#     same value is served at https://<host>/<key>.txt (the landing's public/
#     folder; a test keeps the two in step). It is not a secret.
#   * Only URLs on our own host are ever submitted, taken from our own sitemap.
#   * Submitting is best-effort: a refusal is logged and reported, never
#     retried in a loop, and never blocks the weekly measurement.

from __future__ import annotations

import re
from typing import Callable, Iterable, List

KEY = "d05e1d1f867a8ca93f29d4d85497587a"
HOST = "www.unstructuredalpha.com"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
SITEMAP = f"https://{HOST}/sitemap.xml"
MAX_URLS = 10_000          # the protocol's limit per request

_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")


def urls_from_sitemap(xml: str) -> List[str]:
    """Every <loc> on our own host, in order, without duplicates."""
    seen, out = set(), []
    for u in _LOC.findall(xml or ""):
        if u.startswith(f"https://{HOST}/") or u == f"https://{HOST}":
            if u not in seen:
                seen.add(u)
                out.append(u)
    return out


def payload(urls: Iterable[str]) -> dict:
    return {"host": HOST, "key": KEY, "keyLocation": KEY_LOCATION, "urlList": list(urls)[:MAX_URLS]}


def submit(urls: List[str], post: Callable | None = None) -> int:
    """POST the URLs; returns the HTTP status (200 or 202 means accepted).
    0 when there is nothing to send."""
    if not urls:
        return 0
    if post is None:
        import requests
        post = requests.post
    r = post(ENDPOINT, json=payload(urls), timeout=30,
             headers={"Content-Type": "application/json; charset=utf-8"})
    return int(getattr(r, "status_code", 0) or 0)
