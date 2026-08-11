"""Guards for the client-side navigation proxy.

The visible top nav is raw <a href> markup, so every click used to be a FULL
browser navigation. Measured locally, warm session, same destination:

    full browser navigation   10,893 ms click -> settled
    proxied client-side nav        663 ms click -> settled   (16.4x faster)

The mechanism: render one hidden st.page_link per destination (those carry a
React onClick that navigates client-side) and forward nav clicks to the matching
one. Each test below pins a property that, when it broke during development,
broke SILENTLY -- the app still rendered, so nothing else would have caught it.
"""

from __future__ import annotations

import ast
import re
import sys
import warnings
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_HEADER = _ROOT / "utils" / "header.py"
_INJECTOR = _ROOT / "scripts" / "inject_boot_splash.py"

_HEADER_SRC = _HEADER.read_text(encoding="utf-8")
_INJECTOR_SRC = _INJECTOR.read_text(encoding="utf-8")

PROXY_TESTID = 'data-testid="stPageLink-NavLink"'
RAIL_SCOPE = ".st-key-ua_spa_proxy_rail"


def _click_proxy_block() -> str:
    """The injector's click-proxy section, comments included.

    Sliced by heading rather than a fixed character count: a fixed window
    silently starts failing when someone adds a comment, which says nothing
    about the code being wrong.
    """
    start = _INJECTOR_SRC.find("Client-side navigation proxy")
    assert start != -1, "nav proxy block not found in the injector"
    end = _INJECTOR_SRC.find("uaMarkProxyLinks", start)
    return _INJECTOR_SRC[start : end if end != -1 else start + 4000]


def _page_targets():
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from utils.nav_links import page_targets

    return page_targets()


def test_nav_hrefs_all_have_a_page_target():
    """Every visible nav href must map to a registered page.

    An href with no matching page_link silently falls back to a full reload --
    the slow path, with no error raised anywhere. This is the drift guard: it
    fails the moment someone adds a nav item pointing at an unregistered route.
    """
    slugs = {url.strip("/") for url, _script in _page_targets()}
    hrefs = re.findall(r'class="ua-tnav-item[^"]*"\s+href="([^"]+)"', _HEADER_SRC)
    hrefs += re.findall(r'href="(/[^"]*)"[^>]*class="ua-tnav-item', _HEADER_SRC)

    assert hrefs, "no nav hrefs matched -- the markup this test relies on changed"

    unmatched = sorted(
        {h for h in hrefs if h.startswith("/") and h.strip("/") not in slugs}
    )
    assert not unmatched, (
        f"nav hrefs with no page_link target (these silently full-reload): {unmatched}"
    )


def test_hidden_proxy_css_targets_the_element_not_a_wrapper():
    """The hiding rule must match the page-link element itself.

    This actually broke in development. The rule targeted only a `.ua-spa-proxy`
    wrapper emitted as st.markdown('<div>') ... st.markdown('</div>'). Those two
    calls land in SEPARATE Streamlit containers, so the browser closes the first
    div immediately and it wraps nothing. Result: 33 stray visible links on every
    page -- with the whole suite green.
    """
    assert PROXY_TESTID in _HEADER_SRC, (
        "the proxy-hiding CSS must target [data-testid=stPageLink-NavLink] "
        "directly; a wrapper class alone silently wraps nothing (see docstring)"
    )


def _selector_lines(src: str) -> list[str]:
    """Every CSS selector line mentioning the page-link testid."""
    return [ln.strip() for ln in src.splitlines() if PROXY_TESTID in ln and "/*" not in ln]


def test_hidden_proxy_css_is_scoped_to_the_rail():
    """The hiding rule must not reach page_links outside the proxy rail.

    This shipped broken and stayed that way: the rule was written unscoped, so
    it hid EVERY st.page_link in the app. Signal Research's three real links
    (e.g. "Open advanced earnings and signal attribution") rendered at height 0
    -- present in the DOM, invisible to users, and passing every test, because
    nothing here asserted the scope.
    """
    unscoped = [
        ln
        for ln in _selector_lines(_HEADER_SRC)
        if ln.startswith("[") or (RAIL_SCOPE not in ln and ln.endswith(("{", ",")))
    ]
    assert not unscoped, (
        f"these rules hide every page_link in the app, not just the rail's "
        f"proxies -- prefix each with '{RAIL_SCOPE} ': {unscoped}"
    )


def test_a11y_marking_is_scoped_to_the_rail():
    """tabindex=-1 / aria-hidden must not land on real, visible page_links.

    The CSS scope alone is not enough: the injector stamps both attributes in
    the live DOM, so an unscoped query pulls genuinely visible links out of the
    keyboard tab order and hides them from screen readers -- with the link
    still perfectly visible on screen. Same class of bug, different mechanism.
    """
    idx = _INJECTOR_SRC.find("uaMarkProxyLinks")
    block = _INJECTOR_SRC[idx : idx + 900]
    query_lines = [ln for ln in block.splitlines() if PROXY_TESTID in ln]
    assert query_lines, "the a11y marking query is missing"
    assert all(RAIL_SCOPE in ln for ln in query_lines), (
        f"the a11y marking query must be scoped to '{RAIL_SCOPE}' so it only "
        f"marks the rail's proxies: {query_lines}"
    )


def test_click_proxy_leaves_real_page_links_alone():
    """A page_link already navigates client-side -- proxying one is a no-op at
    best and forwards the click to a different element at worst.

    Only reachable once the visible page_links stopped being hidden, so there
    is nothing in the click-proxy history to catch it.
    """
    block = _click_proxy_block()
    guard = block.find(f"a.closest('[{PROXY_TESTID}]')")
    match = block.find("if(lh === slug)")
    assert guard != -1, "the click proxy must skip anchors that are page_links"
    assert guard < match, "the skip must come before the forwarding logic"


def test_proxy_links_are_clipped_not_display_none():
    """display:none / visibility:hidden elements cannot be reliably clicked.

    Hiding them that way makes every nav click a no-op, which is strictly worse
    than the slowness this replaces.
    """
    idx = _HEADER_SRC.find(PROXY_TESTID)
    block = _HEADER_SRC[idx : idx + 600]
    assert "clip" in block, "expected the clip-rect hiding technique"
    assert "display: none" not in block and "display:none" not in block
    assert "visibility: hidden" not in block and "visibility:hidden" not in block


def test_proxy_links_are_removed_from_the_tab_order():
    """~33 invisible links would otherwise sit in the keyboard tab order.

    Applied per-element by the injector, because there is no server-side wrapper
    to do it with (see test_hidden_proxy_css_targets_the_element_not_a_wrapper).
    """
    idx = _INJECTOR_SRC.find("uaMarkProxyLinks")
    assert idx != -1, "the a11y marking function is missing from the injector"
    block = _INJECTOR_SRC[idx : idx + 900]
    assert "'tabindex','-1'" in block.replace(" ", ""), "proxy links must be tabindex=-1"
    assert "aria-hidden" in block


def test_injector_click_proxy_uses_a_real_click():
    """A synthetic MouseEvent does not trigger React's handler; only .click().

    Verified against a live Streamlit instance. If someone "modernises" this into
    dispatchEvent(new MouseEvent('click')), navigation silently stops working
    while every test that only checks rendering still passes.
    """
    assert ".click()" in _INJECTOR_SRC
    assert "dispatchEvent" not in _INJECTOR_SRC, (
        "synthetic events do not trigger React's onClick -- use a real .click()"
    )


def test_proxy_intercepts_any_internal_link_not_only_the_nav():
    """Logo and footer links were still forcing a full reload.

    Measured on production: 23 of 27 internal anchors were inside the nav and
    already client-side; "/" (logo), /about-methodology and /privacy-terms were
    not. Widening to any internal href is safe precisely because interception
    still requires a matching page_link, so SEO-service paths such as
    /ticker/AAPL -- which are NOT Streamlit pages -- find no proxy and fall
    through to a real navigation.
    """
    block = _click_proxy_block()
    assert "closest('a[href^=\"/\"]')" in block, (
        "the click proxy must match any internal link, not only .ua-tnav-item"
    )


def test_injector_falls_back_to_the_real_href():
    """Degradation must be safe: a miss keeps today's (slow) behaviour.

    preventDefault must be reachable only AFTER a matching proxy is found.
    Hoisting it above the match would swallow clicks that have no proxy --
    turning "slow" into "the nav does nothing", a far worse failure.
    """
    block = _click_proxy_block()
    pd = block.find("ev.preventDefault()")
    match = block.find("if(lh === slug)")
    assert match != -1, "proxy match condition not found"
    assert pd > match, (
        "preventDefault must come only after a matching proxy link is found"
    )


def test_injector_js_blob_compiles_without_syntax_warnings():
    r"""The JS contains regex literals such as /^\/+|\/+$/.

    In a non-raw Python string, "\/" is an invalid escape sequence: a
    SyntaxWarning today, a SyntaxError in a future Python. Compiling with
    warnings-as-errors is the assertion.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        compile(_INJECTOR_SRC, str(_INJECTOR), "exec", dont_inherit=True)


def test_page_targets_are_unique_and_resolvable():
    """Duplicate slugs would make the click proxy pick an arbitrary target."""
    targets = _page_targets()
    assert targets, "no pages parsed from app.py"

    slugs = [u for u, _ in targets]
    dupes = sorted({s for s in slugs if slugs.count(s) > 1})
    assert not dupes, f"duplicate slugs make click routing ambiguous: {dupes}"

    missing = [s for _u, s in targets if not (_ROOT / s).exists()]
    assert not missing, f"page_targets points at missing files: {missing}"


def test_nav_links_parses_app_py_rather_than_hardcoding():
    """The URL->file map must be derived from app.py, not duplicated.

    A hand-maintained copy drifts the moment a page is renamed, and the only
    symptom is that one nav item quietly goes back to full-reload speed.
    """
    src = (_ROOT / "utils" / "nav_links.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imports = {
        n.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for n in [node]
        if node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "ast" in imports, "nav_links must parse app.py with ast, not hardcode routes"
    assert "app.py" in src
