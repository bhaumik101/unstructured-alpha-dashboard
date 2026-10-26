"""One canonical origin for the whole site: https://www.unstructuredalpha.com.

The apex 308-redirects to www. Until 2026-10-26 the landing page -- the site's
most important URL -- declared the apex as its canonical, og:url and JSON-LD
url, while the sitemap and all 544 other pages said www: search engines were
told the homepage's real address was a redirect. A sitemap-wide crawl found it.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "unstructured-alpha-web" / "app"
WWW = "https://www.unstructuredalpha.com"


def test_the_landing_and_the_sitemap_agree_on_www():
    layout = (WEB / "layout.tsx").read_text(encoding="utf-8")
    assert f'const SITE_URL = "{WWW}";' in layout
    assert "canonical: SITE_URL" in layout
    # No apex URL left anywhere in the layout (canonical, og, JSON-LD).
    assert not re.search(r'"https://unstructuredalpha\.com', layout)
    sitemap = (WEB / "sitemap.xml" / "route.ts").read_text(encoding="utf-8")
    assert f'const BRAND_ORIGIN = "{WWW}";' in sitemap


def test_no_page_repeats_the_brand_the_layout_template_adds():
    layout = (WEB / "layout.tsx").read_text(encoding="utf-8")
    assert 'template: "%s | Unstructured Alpha"' in layout
    for page in WEB.rglob("page.tsx"):
        src = page.read_text(encoding="utf-8")
        m = re.search(r'export const metadata[^=]*=\s*\{\s*(?://[^\n]*\n\s*)*title:\s*"([^"]+)"', src)
        if m:
            assert not m.group(1).endswith("| Unstructured Alpha"), page
