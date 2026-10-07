"""The public landing page describes the product as it is.

It said "Six economic forces" after there were nineteen. Next.js cannot read
the Python engine, so the numbers and links in its copy are checked here
against the engine and the route table instead.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import exposure as ex  # noqa: E402

PAGE = (_ROOT / "unstructured-alpha-web" / "app" / "page.tsx").read_text(encoding="utf-8")
APP = (_ROOT / "app.py").read_text(encoding="utf-8")
NEXT = (_ROOT / "unstructured-alpha-web" / "next.config.ts").read_text(encoding="utf-8")


def test_force_counts_match_the_engine():
    total = len(ex.FACTORS) + len(ex.EXTRA_FACTORS)
    extra = len(ex.EXTRA_FACTORS)
    assert f"{total} economic forces, from public sources" in PAGE
    assert f"any of {total} forces" in PAGE
    assert f"{extra} more forces measured beyond them" in PAGE
    assert f"{extra} more are measured" in PAGE
    assert not re.search(r"\b(Six|Five|five|six) economic forces\b", PAGE)


def test_every_extra_force_is_named_on_the_page():
    text = PAGE.lower()
    for f in ex.EXTRA_FACTORS:
        word = f.label.lower().split()[-1]
        assert word in text, f"{f.label} is measured but not mentioned"


def test_every_tool_the_page_links_to_exists():
    assert 'url_path="scenarios"' in APP and "{APP_URL}/scenarios" in PAGE
    # The track record is linked on www: a public page anyone can open or index
    # (seo/main.py /evidence), not the in-app page that needs a live session.
    for path in ("/forces", "/evidence"):
        assert f'href="{path}"' in PAGE and f'source: "{path}"' in NEXT, path


def test_the_hero_looks_up_one_stock_through_the_public_search():
    """The hero's ticker box submits to /go, which the SEO service serves and www proxies."""
    assert '<form className="lp-lookup" action="/go" method="get" role="search">' in PAGE
    assert 'name="t"' in PAGE and 'htmlFor="lp-lookup-t"' in PAGE
    import seo.main as M
    assert any(getattr(r, "path", "") == "/go" for r in M.app.routes)
