"""Removing the boot splash must not remove anything else.

`scripts/inject_boot_splash.py` is named for the splash but injects five
independent things into Streamlit's served index.html. Until now the first four
were not independent at all: the theme bootstrap, the client-side navigation
proxy and the proxy links' accessibility marking all sat INSIDE the
`ua-boot-splash` markers, because that is simply where the first injected
`<script>` happened to go.

So "delete the splash" and "delete the theme (dark-to-light flash on every
load), client-side navigation (a full reload per click) and the proxy links'
aria-hidden/tabindex" were the same edit. The handoff doc flagged the SEO half
of this; the runtime half was not on anyone's list.

Each block now has its own marker pair — ua-runtime, ua-boot-splash, ua-meta,
ua-seo, ua-global-css — and this pins that they stay separable.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

_DASHBOARD = Path(__file__).resolve().parent.parent
_REPO = _DASHBOARD.parent
_SCRIPT = _DASHBOARD / "scripts" / "inject_boot_splash.py"

FRESH = "<html><head><title>Streamlit</title></head><body><div id='root'></div></body></html>"
NAV_PROXY_SENTINEL = "Client-side navigation proxy"


def _load(path: Path, name: str = "ibs"):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ibs():
    return _load(_SCRIPT)


def _build(mod, html: str, digest: str = "testdigest") -> str:
    """The same order main() uses: splash first, runtime second.

    Both insert directly after <body>, so injecting the runtime second is what
    puts it FIRST in document order — which is what the theme bootstrap needs.
    """
    html, _n, _a = mod._inject_or_replace(html, mod._build_splash())
    html, _ = mod._inject_runtime(html)
    html, _ = mod._inject_meta(html)
    html = mod._inject_seo_body(html)
    html, _ = mod._inject_global_css_link(html, digest)
    return html


def _between(html: str, start: str, end: str) -> str:
    return html[html.index(start) : html.index(end)]


def test_every_block_lands_under_its_own_markers(ibs):
    out = _build(ibs, FRESH)
    for start, end in [
        (ibs.RUNTIME_START, ibs.RUNTIME_END),
        (ibs.START_MARKER, ibs.END_MARKER),
        (ibs.META_START, ibs.META_END),
        (ibs.SEO_START, ibs.SEO_END),
    ]:
        assert start in out and end in out, f"{start} block missing"
    assert "ua-global.css" in out


def test_removing_the_splash_leaves_everything_else(ibs):
    """The whole point of the split.

    Deleting the splash block must leave the runtime, both SEO blocks and the
    stylesheet link untouched. Before the split this test could not pass:
    the nav proxy and theme bootstrap were inside the splash markers.
    """
    out = _build(ibs, FRESH)
    stripped = re.sub(
        re.escape(ibs.START_MARKER) + ".*?" + re.escape(ibs.END_MARKER),
        "",
        out,
        flags=re.DOTALL,
    )
    assert "ua-boot-splash" not in stripped, "the splash should be gone"
    assert ibs.RUNTIME_START in stripped, "the runtime went with the splash"
    assert NAV_PROXY_SENTINEL in stripped, "client-side navigation went with the splash"
    assert "ua-theme" in stripped, "the theme bootstrap went with the splash"
    assert ibs.META_START in stripped, "the social/SEO meta went with the splash"
    assert ibs.SEO_START in stripped, "the crawlable body went with the splash"
    assert "ua-global.css" in stripped, "the stylesheet link went with the splash"


def test_the_splash_block_holds_no_runtime(ibs):
    splash = ibs._build_splash()
    assert NAV_PROXY_SENTINEL not in splash
    assert "uaMarkProxyLinks" not in splash
    assert "uaSetTheme" not in splash


def test_the_runtime_block_holds_all_three_runtime_concerns(ibs):
    runtime = ibs._build_runtime()
    assert "ua-theme" in runtime, "theme bootstrap"
    assert NAV_PROXY_SENTINEL in runtime, "client-side navigation proxy"
    assert "uaMarkProxyLinks" in runtime, "proxy-link a11y marking"


def test_the_runtime_runs_before_the_splash(ibs):
    """Theme must be set before first paint, or every load flashes."""
    out = _build(ibs, FRESH)
    assert out.index(ibs.RUNTIME_START) < out.index(ibs.START_MARKER), (
        "the runtime must precede the splash in document order"
    )


def test_main_actually_injects_the_runtime(ibs):
    """The functional tests above call _inject_runtime directly.

    That is a real blind spot: deleting the call from main() leaves every one
    of them green while the deployed page loses its theme and client-side
    navigation. Caught by mutating main() and watching nothing fail. This
    reads main() itself.
    """
    src = _SCRIPT.read_text(encoding="utf-8")
    body = src[src.index("def main()") :]
    assert "_inject_runtime(" in body, (
        "main() no longer injects the runtime — the deployed page would lose "
        "the theme bootstrap and client-side navigation"
    )
    assert body.index("_inject_or_replace(") < body.index("_inject_runtime("), (
        "main() must inject the splash first so the runtime lands ahead of it"
    )


def test_rebuilding_is_idempotent(ibs):
    once = _build(ibs, FRESH)
    twice = _build(ibs, once)
    assert once == twice, "a second build must not duplicate or drift"


def test_upgrading_a_pre_split_deployment_leaves_one_runtime(ibs):
    """The live index.html still has the old combined block.

    On the next deploy _inject_or_replace rewrites the splash markers with
    splash-only content -- taking the old runtime with them -- and
    _inject_runtime adds it back under its own markers. Exactly one of each,
    in the right order.
    """
    old_src = subprocess.run(
        ["git", "show", "HEAD:dashboard/scripts/inject_boot_splash.py"],
        capture_output=True, text=True, cwd=_REPO,
    ).stdout
    if "_build_runtime" in old_src or not old_src.strip():
        pytest.skip("HEAD already contains the split; upgrade path covered when it landed")

    old_path = _DASHBOARD / "tests" / "_pre_split_injector.tmp.py"
    old_path.write_text(old_src, encoding="utf-8")
    try:
        old = _load(old_path, "ibs_old")
        deployed, _n, _a = old._inject_or_replace(FRESH, old._build_splash())
        deployed, _ = old._inject_meta(deployed)
        deployed = old._inject_seo_body(deployed)
        assert NAV_PROXY_SENTINEL in _between(deployed, old.START_MARKER, old.END_MARKER), (
            "fixture is wrong: the pre-split build should have the proxy inside the splash"
        )

        upgraded = _build(ibs, deployed)
        assert upgraded.count(NAV_PROXY_SENTINEL) == 1, "nav proxy duplicated or lost"
        assert upgraded.count(ibs.RUNTIME_START) == 1
        assert upgraded.count(ibs.START_MARKER) == 1
        assert upgraded.index(ibs.RUNTIME_START) < upgraded.index(ibs.START_MARKER)
        assert NAV_PROXY_SENTINEL not in _between(
            upgraded, ibs.START_MARKER, ibs.END_MARKER
        ), "the splash block still carries runtime after the upgrade"
    finally:
        old_path.unlink(missing_ok=True)
