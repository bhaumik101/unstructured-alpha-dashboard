"""Links users share or click must not depend on RENDER_EXTERNAL_URL alone.

RENDER_EXTERNAL_URL is injected by Render on WEB services only. A cron job has
no public URL and never receives it, so any cron reading it falls straight
through to its default. Three places read it to build user-facing links:

    utils/referral.py          referral link  -> {base}/upgrade-to-pro?ref=CODE
    cron/send_weekly_brief.py  referral link  -> {base}?ref=CODE
    cron/signal_flip_alerts.py alert email <a href>

The first two defaulted to http://localhost:8501. render.yaml declares
RENDER_EXTERNAL_URL for the weekly-brief and signal-flip crons with
`sync: false`, which does NOT populate it -- it only asks a human to set it in
the dashboard. The referral link is the product's acquisition mechanism, and a
localhost URL in it is worth nothing to anybody.

Even on the web service, where Render does set the variable, it carries the
.onrender.com host rather than app.unstructuredalpha.com -- a working link, but
the wrong brand and a hostage to the hosting provider.

So the resolution order is APP_BASE_URL -> RENDER_EXTERNAL_URL -> dev default,
and the services that need APP_BASE_URL must actually declare it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_RENDER = yaml.safe_load((_ROOT / "render.yaml").read_text(encoding="utf-8"))

# Services whose code builds a link a human is expected to follow. Explicit
# rather than derived: most crons import utils/email.py, whose own APP_BASE_URL
# default is already the correct production host, so deriving would flag every
# service in the file and the test would get deleted.
_SERVICES_NEEDING_APP_BASE_URL = {
    "unstructured-alpha",                    # in-app referral links
    "unstructured-alpha-weekly-brief",       # referral link in the Pro brief
    "unstructured-alpha-signal-flip-alerts", # alert email CTA
    "unstructured-alpha-digest",             # already had it; keeps it
}


def test_app_base_url_is_preferred_over_render_external_url():
    """RENDER_EXTERNAL_URL may be a fallback, never the only source.

    Matched on the AST, not on a text window. The resolution chain spans several
    lines and puts APP_BASE_URL BEFORE the RENDER_EXTERNAL_URL it guards, so any
    slice anchored on the match itself reads the wrong direction and reports
    every fixed call site as broken. Asking the enclosing statement whether it
    mentions APP_BASE_URL at all is the question actually worth asking.
    """
    offenders = []
    for path in sorted(_ROOT.rglob("*.py")):
        if "retired" in path.parts or "tests" in path.parts:
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        if "RENDER_EXTERNAL_URL" not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:                     # not ours to police
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.stmt):
                continue
            segment = ast.get_source_segment(src, node) or ""
            if "RENDER_EXTERNAL_URL" not in segment:
                continue
            # Only the innermost statement holding the read, so an enclosing
            # function body does not absorb an unrelated APP_BASE_URL nearby.
            if any(
                isinstance(child, ast.stmt)
                and child is not node
                and "RENDER_EXTERNAL_URL" in (ast.get_source_segment(src, child) or "")
                for child in ast.walk(node)
            ):
                continue
            if "APP_BASE_URL" not in segment:
                offenders.append(f"{path.relative_to(_ROOT)}:{node.lineno}")
    assert not offenders, (
        "these read RENDER_EXTERNAL_URL without preferring APP_BASE_URL first; "
        "on a cron service it is never set:\n  " + "\n  ".join(sorted(offenders))
    )


def test_services_that_build_shared_links_declare_app_base_url():
    missing = []
    for svc in _RENDER.get("services", []):
        name = svc.get("name")
        if name not in _SERVICES_NEEDING_APP_BASE_URL:
            continue
        keys = {e.get("key") for e in (svc.get("envVars") or [])}
        if "APP_BASE_URL" not in keys:
            missing.append(name)
    assert not missing, (
        "these services build user-facing links but do not set APP_BASE_URL, so "
        "the code falls back to a dev default:\n  " + "\n  ".join(missing)
    )


def test_declared_app_base_urls_point_at_a_real_host():
    """A typo here ships a dead link to every reader; localhost ships nothing."""
    bad = []
    for svc in _RENDER.get("services", []):
        for e in (svc.get("envVars") or []):
            if e.get("key") != "APP_BASE_URL":
                continue
            val = str(e.get("value") or "")
            if not val:
                continue  # sync:false — set in the dashboard, nothing to check
            if "localhost" in val or not val.startswith("https://"):
                bad.append(f"{svc.get('name')}: {val!r}")
    assert not bad, "APP_BASE_URL must be an https production host:\n  " + "\n  ".join(bad)


def test_the_service_list_is_honest():
    """Every named service must still exist in render.yaml."""
    names = {s.get("name") for s in _RENDER.get("services", [])}
    stale = sorted(_SERVICES_NEEDING_APP_BASE_URL - names)
    assert not stale, "these services no longer exist:\n  " + "\n  ".join(stale)


# Link builders whose DESTINATION is a route the app does not register. Distinct
# from the host problem above: these resolve to the right server and still land
# nowhere. Listed rather than silently tolerated, because each one is a feature
# the UI actively offers.
_UNROUTED_DESTINATIONS: set[str] = set()
# EMPTY. /Share_Watchlist was the only entry: the page had been retired while
# utils/share_watchlist.build_share_url() kept emitting links to it and the
# Watchlist page kept telling users to "copy and share freely".
#
# Restored as pages/35_Share_Watchlist.py with url_path="share-watchlist", and
# the builder now emits that slug. Anything added here again is a feature the
# UI offers that leads nowhere.


def test_generated_link_paths_resolve_to_registered_routes():
    """A share link that leaves the product must land somewhere real."""
    routes = set(
        re.findall(r'url_path="([^"]+)"', (_ROOT / "app.py").read_text(encoding="utf-8"))
    )
    bad = []
    for path in sorted(_ROOT.rglob("*.py")):
        if "retired" in path.parts or "tests" in path.parts:
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        # Only files that actually resolve an APP base URL. Without this the
        # match fires on any local variable named `base` -- utils/fetchers.py
        # builds f"{base}/index.json" against an SEC EDGAR archive host, which
        # has nothing to do with app routing.
        if not re.search(r'os\.environ\.get\(\s*"(?:APP_BASE_URL|RENDER_EXTERNAL_URL)"', src):
            continue
        for m in re.finditer(r'f"\{(?:base|_BASE_URL|_SITE_URL)\}(/[A-Za-z0-9_%-]+)', src):
            dest = m.group(1)
            if dest.strip("/") not in routes and dest not in _UNROUTED_DESTINATIONS:
                bad.append(f"{path.relative_to(_ROOT)}: {dest}")
    assert not bad, (
        "these build links to paths app.py does not route:\n  " + "\n  ".join(bad)
    )


def test_the_unrouted_list_is_honest():
    """Drop entries once the route exists -- the list must not outlive the bug."""
    routes = set(
        re.findall(r'url_path="([^"]+)"', (_ROOT / "app.py").read_text(encoding="utf-8"))
    )
    stale = sorted(d for d in _UNROUTED_DESTINATIONS if d.strip("/") in routes)
    assert not stale, (
        "these are registered now; remove them from _UNROUTED_DESTINATIONS:\n  "
        + "\n  ".join(stale)
    )


def test_the_share_link_query_param_matches_what_the_page_reads():
    """The builder and the page must agree on the parameter name.

    The path half of this contract already drifted once -- the page was retired
    while the builder kept emitting links to it. The query string is the other
    half: build_share_url() emits ?id=<slug>, and the page has to look for
    exactly that key or every shared link renders "No watchlist link provided".
    """
    builder = (_ROOT / "utils" / "share_watchlist.py").read_text(encoding="utf-8")
    page = (_ROOT / "pages" / "35_Share_Watchlist.py").read_text(encoding="utf-8")

    emitted = re.search(r'f"\{base\}/share-watchlist\?([A-Za-z0-9_]+)=', builder)
    assert emitted, "build_share_url no longer emits a /share-watchlist?<param>= link"
    param = emitted.group(1)

    assert re.search(rf'st\.query_params\.get\(\s*["\']{re.escape(param)}["\']', page), (
        f"build_share_url emits ?{param}= but the page does not read that key"
    )


def test_the_share_page_does_not_build_its_own_cookie_manager():
    """app.py owns the single CookieManager for the run.

    Constructing a second one raises StreamlitDuplicateElementKey and takes the
    whole page down. This page shipped that call from before app.py took
    ownership, and it crashed on the first render after being restored.
    """
    page = (_ROOT / "pages" / "35_Share_Watchlist.py").read_text(encoding="utf-8")
    # Strip comments first. The page carries a comment explaining why it must
    # NOT call this, and a plain substring check fails on the explanation --
    # exactly the false positive that makes a test look broken and get deleted.
    code = "\n".join(re.sub(r"#.*$", "", line) for line in page.splitlines())
    assert "init_cookies_for_this_run()" not in code, (
        "the share page constructs its own CookieManager; app.py already made "
        "one for this run and a second raises StreamlitDuplicateElementKey"
    )
