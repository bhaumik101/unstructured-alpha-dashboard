"""The global stylesheet must be servable, complete, and safe to fall back from.

Context: every top-nav click is a FULL browser navigation (the nav is real
<a href> anchors), so ~161 KB of inline <style> was re-sent and re-parsed on
every page change and could never be browser-cached. Moving it to one external
file fixes that -- but a previous attempt was reverted because it linked
`/_stapp/static/...`, which returns Streamlit's HTML shell rather than the file.
Loading HTML as a stylesheet leaves the entire app unstyled.

These tests pin the two things that actually broke it: the URL, and the
fallback.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ibs", ROOT / "scripts" / "inject_boot_splash.py"
)
ibs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ibs)


def test_stylesheet_href_uses_the_only_path_that_serves_real_files():
    """/app/static/ is the ONLY prefix that returns the file itself.

    Verified against production: /_stapp/static/ and /static/ both return
    Streamlit's index.html with content-type text/html. A <link> to either loads
    HTML as CSS, the browser refuses it, and the app renders unstyled -- which is
    exactly why the earlier attempt was reverted.
    """
    assert ibs.GLOBAL_CSS_HREF == "/app/static/ua-global.css"
    assert not ibs.GLOBAL_CSS_HREF.startswith("/_stapp/")


def test_stylesheet_contains_everything_the_inline_path_injected():
    """Skipping inline injection is only safe if nothing is lost."""
    css = ibs.build_global_css()

    assert "--ua-royal" in css, "theme tokens missing"
    assert "--ua-green-rgb" in css, "RGB triples missing"
    assert 'data-ua-theme="light"' in css, "light-mode overrides missing"
    assert ".ua-chart" in css, "chart primitives missing"
    assert len(css) > 50_000, "stylesheet suspiciously small"


def test_stylesheet_covers_both_global_injection_points():
    """render_header and theme.inject_all_css both stop injecting inline when
    this file exists, so it must contain everything BOTH of them used to send.
    Missing one block means 8 pages silently lose their skeleton/counter styles.
    """
    from utils.header import _CSS
    from utils.theme import _COUNTER_CSS, _MODERN_UI_CSS, _SKELETON_CSS

    css = ibs.build_global_css()

    def head(block: str, n: int = 90) -> str:
        return block.replace("<style>", "").replace("</style>", "").strip()[:n]

    for name, block in (
        ("_CSS", _CSS),
        ("_SKELETON_CSS", _SKELETON_CSS),
        ("_COUNTER_CSS", _COUNTER_CSS),
        ("_MODERN_UI_CSS", _MODERN_UI_CSS),
    ):
        assert head(block) in css, f"{name} missing from the served stylesheet"


def test_shared_block_is_not_duplicated():
    """_MODERN_UI_CSS is used by BOTH entry points; it was being delivered twice
    per page. It must appear exactly once in the file."""
    from utils.theme import _MODERN_UI_CSS

    css = ibs.build_global_css()
    marker = _MODERN_UI_CSS.replace("<style>", "").replace("</style>", "").strip()[:90]
    assert css.count(marker) == 1


def test_stylesheet_has_no_nested_style_tags():
    """It is served as a .css file; a <style> tag inside would be a parse error."""
    css = ibs.build_global_css()
    assert "<style>" not in css and "</style>" not in css


def test_link_injection_is_idempotent():
    """The build can run repeatedly; index.html must not accumulate links."""
    html = "<html><head><title>t</title></head><body></body></html>"
    once, first = ibs._inject_global_css_link(html)
    twice, second = ibs._inject_global_css_link(once)

    assert once.count("ua-global.css") == 1
    assert once == twice
    assert "injected" in first and "already present" in second


def test_link_lands_inside_head():
    html = "<html><head><title>t</title></head><body></body></html>"
    out, _ = ibs._inject_global_css_link(html)
    assert out.index("ua-global.css") < out.index("</head>")


def test_missing_head_is_survived_not_crashed():
    """A future Streamlit index.html shape must not break the build."""
    out, action = ibs._inject_global_css_link("<html><body></body></html>")
    assert "skipped" in action
    assert "ua-global.css" not in out


def test_runtime_falls_back_to_inline_when_the_file_is_absent():
    """An unstyled app is far worse than a slow one.

    If the build step did not run (local dev, skipped step), render_header must
    still inject the CSS inline exactly as before.
    """
    header = pytest.importorskip("utils.header")
    header.global_stylesheet_available.cache_clear()

    stylesheet = ROOT / "static" / "ua-global.css"
    if stylesheet.is_file():
        pytest.skip("stylesheet present in this checkout; fallback path not exercised")

    assert header.global_stylesheet_available() is False


# ── Cache busting ────────────────────────────────────────────────────────────
#
# Streamlit's static handler sets NO cache-control on ua-global.css and the
# filename is fixed, so browsers cache it heuristically and a returning visitor
# can paint a previous deploy's stylesheet. Observed live on 2026-08-03: the
# origin was serving the new Inter typography from #112 while a browser that
# had visited before still rendered the old Fraunces hero.


def test_write_global_css_returns_a_content_digest():
    """The digest is what makes the URL change. Without it the link falls back
    to the bare href and the staleness returns silently."""
    import tempfile
    digest = ibs.write_global_css(tempfile.mkdtemp())
    assert digest, "no digest — cache busting is inert"
    assert len(digest) == 12 and all(c in "0123456789abcdef" for c in digest)


def test_the_same_css_yields_the_same_url():
    """Must NOT bust on every build, or the stylesheet is uncacheable and every
    visitor re-downloads ~129KB on every visit — the opposite failure."""
    import tempfile
    a = ibs.write_global_css(tempfile.mkdtemp())
    b = ibs.write_global_css(tempfile.mkdtemp())
    assert a == b


def test_changed_css_yields_a_different_url(monkeypatch):
    """The property under test: edit the CSS, get a new URL."""
    import tempfile
    before = ibs.write_global_css(tempfile.mkdtemp())
    real = ibs.build_global_css
    monkeypatch.setattr(ibs, "build_global_css", lambda: real() + "\n.ua-x{color:red}")
    after = ibs.write_global_css(tempfile.mkdtemp())
    assert before != after, "CSS changed but the URL did not — visitors keep the stale file"


def test_injected_link_carries_the_digest_and_keeps_the_served_path():
    """Path resolution must stay byte-identical.

    Only /app/static/<file> returns the real file; the query string is appended
    so the URL changes without touching the prefix the module warns about.
    """
    out, action = ibs._inject_global_css_link("<html><head></head></html>", "abc123def456")
    assert "css-link injected" == action
    assert 'href="/app/static/ua-global.css?v=abc123def456"' in out


def test_link_still_emitted_when_no_digest_is_available():
    """Degrade to today's behaviour rather than dropping the stylesheet.

    A missing digest must never mean a missing <link> — an unstyled app is far
    worse than a stale one.
    """
    out, _ = ibs._inject_global_css_link("<html><head></head></html>", "")
    assert 'href="/app/static/ua-global.css"' in out
    assert "?v=" not in out
