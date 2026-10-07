"""Public pages may be cached at the edge; nothing private or dynamic may be.

What must hold: a successful public HTML page carries the shared-cache header;
a request with credentials, a redirect, a 404, JSON, and any route that sets
its own Cache-Control are left alone.
"""

from __future__ import annotations

from tests.test_explore_page import client  # noqa: F401  (fixture)


def test_public_pages_are_edge_cached(client):  # noqa: F811
    c, _one, lib, M = client
    for path in ("/exposure", "/forces", "/tools", "/sectors"):
        assert c.get(path).headers["cache-control"] == M.PAGE_CACHE, path


def test_private_dynamic_and_failed_responses_are_not(client):  # noqa: F811
    c, _one, lib, M = client
    r = c.get("/exposure", headers={"Authorization": "Bearer x"})
    assert r.headers.get("cache-control") != M.PAGE_CACHE
    r = c.get("/go", params={"t": "bank"}, follow_redirects=False)
    assert r.status_code == 302 and r.headers.get("cache-control") != M.PAGE_CACHE
    r = c.get("/exposure/NOPE")
    assert r.status_code == 404 and r.headers.get("cache-control") != M.PAGE_CACHE
    assert c.get("/healthz").headers.get("cache-control") != M.PAGE_CACHE


def test_a_routes_own_cache_header_wins(client):  # noqa: F811
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank Co")
    M._og_cache.clear()
    assert c.get("/og/BANK.png").headers["cache-control"] == "public, max-age=86400"
    assert c.get("/status").headers["cache-control"] == "no-store"


def test_the_guards_hold_for_html_too(client):  # noqa: F811
    """No route today returns non-200 HTML or HTML with its own header; the
    guards must still hold when one does."""
    from fastapi.responses import HTMLResponse

    c, _one, lib, M = client
    M.app.add_api_route("/__t/html404", lambda: HTMLResponse("<p>gone</p>", status_code=404))
    M.app.add_api_route("/__t/htmlown", lambda: HTMLResponse("<p>x</p>", headers={"Cache-Control": "no-store"}))
    try:
        assert c.get("/__t/html404").headers.get("cache-control") != M.PAGE_CACHE
        assert c.get("/__t/htmlown").headers["cache-control"] == "no-store"
    finally:
        # Other tests enumerate the app's routes (the www proxy list); leave none behind.
        M.app.router.routes[:] = [r for r in M.app.router.routes
                                  if not getattr(r, "path", "").startswith("/__t/")]
