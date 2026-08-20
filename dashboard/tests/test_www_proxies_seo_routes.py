"""Every SEO route the sitemap advertises must be reachable on the canonical host.

The SEO service runs at seo.unstructuredalpha.com, and the marketing site
proxies selected paths so the pages live on www -- the consolidation that exists
so ranking accrues to the brand domain instead of a subdomain nobody links to.

That proxy is a hand-maintained list in unstructured-alpha-web/next.config.ts.
Adding a route to seo/main.py does not add it to the list, and nothing noticed:

    seo.unstructuredalpha.com/brief   200
    www.unstructuredalpha.com/brief   404      <- caught live, after shipping

The consequences were all silent. The sitemap emits {BASE_URL}/brief with
BASE_URL set to www, so Google was handed a 404. The subscriber email's "Read
in browser" link pointed at the same dead URL. And the page itself was fine, so
nothing in the service's own health or tests complained.

This compares the two lists directly instead of trusting either to stay in step.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SEO = (_ROOT / "seo" / "main.py").read_text(encoding="utf-8")
_CONFIG = (_ROOT / "unstructured-alpha-web" / "next.config.ts").read_text(encoding="utf-8")

# Served by the SEO app but deliberately NOT proxied to www.
_NOT_PROXIED = {
    "/",            # www has its own landing page
    "/healthz",     # ops endpoints belong to the service, not the brand domain
    "/readyz",
    "/version",
}


def _seo_routes() -> set[str]:
    return {
        m.group(1)
        for m in re.finditer(r'@app\.get\(\s*"([^"]+)"', _SEO)
    }


def _proxied_sources() -> set[str]:
    return {
        m.group(1)
        for m in re.finditer(r'source:\s*"([^"]+)"', _CONFIG)
    }


def _normalise(path: str) -> str:
    """/ticker/{symbol} and /ticker/:symbol describe the same route.

    Segment-based rather than a pattern over the whole string: sitemap URLs are
    built inside f-strings, so a path can arrive as /brief/{_n['id'] -- the
    quote inside the subscript truncates any capture that stops at a quote, and
    a {...} pattern then fails to match the fragment at all. Treating any
    segment that contains an interpolation as a parameter handles every shape.
    """
    out = []
    for seg in path.split("/"):
        if not seg:
            continue
        out.append(":p" if ("{" in seg or seg.startswith(":")) else seg)
    return "/" + "/".join(out) if out else "/"


def test_every_public_seo_route_is_proxied_to_www():
    proxied = {_normalise(p) for p in _proxied_sources()}
    missing = sorted(
        route for route in _seo_routes()
        if route not in _NOT_PROXIED and _normalise(route) not in proxied
    )
    assert not missing, (
        "these routes are served by the SEO app but not proxied to www, so they "
        "404 on the canonical domain:\n  " + "\n  ".join(missing)
        + "\n\nadd them to rewrites() in unstructured-alpha-web/next.config.ts"
    )


def test_everything_in_the_sitemap_is_reachable_on_the_canonical_host():
    """The stricter half: a sitemap entry that 404s is handed to Google."""
    # Capture the whole path INCLUDING interpolations. A pattern that stops at
    # the first "{" turns {BASE_URL}/ticker/{symbol} into "/ticker", which is
    # not a route anyone serves — the first version of this test failed on that
    # rather than on a real gap.
    sitemap_paths = {
        _normalise(m.group(1))
        for m in re.finditer(r'\{BASE_URL\}(/[^"\'<\s]*)', _SEO)
    }
    proxied = {_normalise(p) for p in _proxied_sources()} | {_normalise(p) for p in _NOT_PROXIED}
    # Per-item URLs are built from f-strings with ids in them; normalise those.
    unreachable = sorted(
        p for p in sitemap_paths
        if p not in proxied and p not in {"/", "/:p"}
    )
    assert not unreachable, (
        "the sitemap advertises these on the canonical host, but www does not "
        "proxy them:\n  " + "\n  ".join(unreachable)
    )


def test_the_exemption_list_only_holds_routes_that_exist():
    routes = _seo_routes()
    stale = sorted(p for p in _NOT_PROXIED if p not in routes)
    assert not stale, (
        "these are exempted from proxying but no longer exist: " + ", ".join(stale)
    )
