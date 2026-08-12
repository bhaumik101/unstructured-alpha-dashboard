"""Every page must expose its title as a real <h1>.

Measured on the deployed app 2026-08-11: Signal Dashboard had **zero** heading
elements of any level -- `document.querySelectorAll('h1,h2,h3,h4,h5,h6')`
returned an empty list. Signal Research had two, both `<h4>`. The visible page
title was a styled `<div>`, so it was a heading to a sighted reader and nothing
at all to a screen reader or a crawler.

That matters more here than in most apps: scripts/inject_boot_splash.py exists
partly to give search engines crawlable body content, and heading-jump is the
primary way a screen-reader user skims a page.

Two emitters produce a page title, and they are mutually exclusive by
construction -- Home passes `hero_title` to render_header(), every other page
calls render_page_header(). These tests pin that both emit an <h1>, and that no
page can start emitting two.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_HEADER = _ROOT / "utils" / "header.py"
_HEADER_SRC = _HEADER.read_text(encoding="utf-8")


def _pages() -> list[Path]:
    pages = [p for p in _ROOT.glob("pages/*.py") if p.is_file()]
    assert pages, "no pages found -- the layout changed"
    return pages


def test_the_interior_page_title_is_an_h1():
    """render_page_header covers 29 of the app's pages."""
    idx = _HEADER_SRC.find("def render_page_header")
    assert idx != -1, "render_page_header is gone"
    body = _HEADER_SRC[idx : idx + 2600]
    assert "{title}" in body, "the title interpolation moved -- re-point this test"
    title_line = next(
        (ln for ln in body.splitlines() if "{title}" in ln), ""
    )
    # The title sits in a <span> inside the heading; walk back to the open tag.
    before = body[: body.find("{title}")]
    open_tag = re.findall(r"<(h1|div|span|p)\b", before)
    assert "h1" in open_tag, (
        "the page title must be an <h1>, not a styled div -- the deployed "
        f"Signal Dashboard had no headings at all. Title line: {title_line.strip()!r}"
    )


def test_the_home_hero_title_is_an_h1():
    """Home has no render_page_header call; its hero IS the page title."""
    assert re.search(r'<h1 class="ua-hero-title">\{hero_title\}</h1>', _HEADER_SRC), (
        "the Home hero title must be an <h1> -- it is the only page title Home has"
    )


def test_both_h1s_outrank_the_global_heading_rule():
    """This is a semantics change, not a design change.

    The stylesheet carries a broad `h1, h2, h3 { ... !important }` plus
    `h1 { font-size: 1.75rem !important }`. An !important rule beats a plain
    class AND a plain inline style, so simply swapping div -> h1 restyles the
    title on all 30 pages. Measured in the browser before it shipped:

        home hero      32.8px / 700 / -0.9px  ->  28px / 700 / -0.3px + 18.76px margin
        page title     28.8px / 720 / -0.55px ->  28px / 700 / -0.3px

    Every declaration that the global rule sets must therefore be !important
    here too. None of the existing type-scale or ratchet tests can see this.
    """
    contested = ["font-size", "font-weight", "letter-spacing", "font-family", "margin"]

    # Strip comments first: the explanatory comment inside the rule quotes a
    # CSS snippet containing a closing brace, which truncated this slice.
    src = re.sub(r"/\*.*?\*/", "", _HEADER_SRC, flags=re.S)

    hero = src[src.find(".ua-hero-title {") :]
    hero = hero[: hero.find("}") + 1]
    idx = src.find("def render_page_header")
    body = src[idx : idx + 2600]
    page = body[body.find("<h1") : body.find("{title}")]

    for name, css in ((".ua-hero-title", hero), ("render_page_header's h1", page)):
        for prop in contested:
            m = re.search(rf"{prop}\s*:[^;]*;", css)
            assert m, f"{name}: no {prop} declaration to protect"
            assert "!important" in m.group(0), (
                f"{name}: `{m.group(0).strip()}` loses to the global "
                f"`h1,h2,h3 {{ ... !important }}` rule and will restyle the title"
            )


def test_no_page_emits_two_page_titles():
    """One h1 per page. The two emitters must stay mutually exclusive.

    A page passing hero_title AND calling render_page_header would produce two
    h1s, which is the drift this guards against.
    """
    both = [
        p.relative_to(_ROOT).as_posix()
        for p in _pages()
        if "hero_title" in (src := p.read_text(encoding="utf-8"))
        and "render_page_header" in src
    ]
    assert not both, (
        f"these pages would render two <h1> elements: {both}. Pick one emitter."
    )
