"""The app's served <head>: what crawlers read before any JavaScript runs.

What must hold:
  * every app URL is noindex, follow -- the indexable public surface is www,
    and a crawler that renders an app URL opens a live, database-backed
    session (found Nov 2026 inflating "app visitors");
  * the canonical and social URLs name www, the one canonical origin, not the
    bare domain that redirects to it;
  * the crawler-floor links are app routes (relative), not bare-domain URLs
    that land on www and 404.
"""

from __future__ import annotations

import re

from tests.test_injected_blocks_are_separable import _SCRIPT, _load

ibs = _load(_SCRIPT)


def test_the_app_is_noindex_follow_in_the_served_html():
    meta = ibs._build_meta()
    assert '<meta name="robots" content="noindex, follow">' in meta


def test_canonical_and_social_urls_are_www():
    meta = ibs._build_meta()
    assert '<link rel="canonical" href="https://www.unstructuredalpha.com">' in meta
    assert re.findall(r'https://unstructuredalpha\.com', meta) == []        # never the bare domain
    assert '"url":"https://www.unstructuredalpha.com"' in meta


def test_crawler_floor_links_stay_on_the_app():
    body = ibs._build_seo_body()
    hrefs = re.findall(r'href="([^"]+)"', body)
    assert hrefs and all(h.startswith("/") for h in hrefs), hrefs
