"""Every page must be reachable from the nav, or be deliberately hidden.

app.py registers the routes. utils/header.py renders a hand-written top-nav whose
docstring says it "mirrors app.py's navigation groups" -- but it is a manual
copy, so it drifted: 22 nav anchors against 32 registered routes. Ten pages
existed, were registered, resolved by URL, and could not be reached by clicking
anything. Track Record was one of them, which is how it was found.

A page nobody can navigate to is indistinguishable from a page that does not
exist, except that it still costs a build and still appears in the route table.

"Hidden" is a legitimate choice -- an onboarding step reached only after signup,
or a route kept alive purely so old bookmarks resolve. What is not legitimate is
hidden BY ACCIDENT. So hiding has to be declared here, with a reason, and
anything not declared has to be linked.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

APP = DASHBOARD / "app.py"
HEADER = DASHBOARD / "utils" / "header.py"

# Routes deliberately kept out of the nav. Add here WITH a reason, or link it.
INTENTIONALLY_UNLINKED: dict[str, str] = {
    "welcome": (
        "post-signup account setup; reached by redirect after registration, not "
        "browsed to"
    ),
    "signal-strategy": (
        "app.py marks it 'merged out of visible nav (duplicate of Portfolio "
        "Suite's backtester)' — kept only so old bookmarks resolve"
    ),
    "admin": "admin-only; rendered into the nav conditionally, not for every user",
    "upgrade-to-pro": "reached from the Upgrade button and Pro-locked states",
    "share-watchlist": (
        "public read-only view of someone else's watchlist; reached only via the "
        "link from utils/share_watchlist.build_share_url(), and putting it in the "
        "nav would offer every visitor a page that needs a slug to mean anything"
    ),
}

_PAGE = re.compile(
    r'st\.Page\("pages/([^"]+)"[^)]*?title="([^"]+)"[^)]*?url_path="([^"]+)"'
)


def _registered_routes() -> dict[str, str]:
    return {
        m.group(3): m.group(2) for m in _PAGE.finditer(APP.read_text(encoding="utf-8"))
    }


def _nav_hrefs() -> set[str]:
    nav = HEADER.read_text(encoding="utf-8").split("def _render_topnav", 1)[1]
    return set(re.findall(r'href="/([a-z0-9\-]+)"', nav))


def test_every_registered_page_is_reachable_from_the_nav() -> None:
    routes = _registered_routes()
    linked = _nav_hrefs()

    unreachable = sorted(
        slug for slug in routes
        if slug not in linked and slug not in INTENTIONALLY_UNLINKED
    )
    assert not unreachable, (
        "these pages are registered but nothing links to them, so a user can "
        "only reach them by typing the URL: "
        + ", ".join(f"/{s} ({routes[s]})" for s in unreachable)
        + ". Either add an <a> to the top-nav in utils/header.py or declare it "
        "in INTENTIONALLY_UNLINKED with a reason."
    )


def test_nav_does_not_link_to_routes_that_do_not_exist() -> None:
    """The mirror drifts both ways; a dead nav link is a 'Page not found'."""
    routes = _registered_routes()
    dangling = sorted(
        h for h in _nav_hrefs()
        if h not in routes and h not in INTENTIONALLY_UNLINKED
    )
    assert not dangling, f"nav links to routes that are not registered: {dangling}"


def test_intentionally_unlinked_entries_are_real_routes() -> None:
    """Stops the exclusion list becoming a graveyard of deleted pages."""
    routes = _registered_routes()
    stale = sorted(s for s in INTENTIONALLY_UNLINKED if s not in routes)
    assert not stale, (
        f"INTENTIONALLY_UNLINKED names routes that no longer exist: {stale}"
    )


def test_track_record_specifically_is_linked() -> None:
    """The page that surfaced this whole class of bug."""
    assert "track-record" in _nav_hrefs(), (
        "Track Record is the auditable public log — it must be clickable"
    )


MAX_ITEMS_PER_DROPDOWN = 7


def _dropdown_sizes() -> dict[str, int]:
    """Count links per nav group.

    Splits on group boundaries rather than matching to the first </div>: the
    More group contains a nested <div class="ua-tnav-drop-rule"></div>, and a
    non-greedy match stopped there and undercounted it. A size guard that
    undercounts is exactly the guard that lets an oversized dropdown through.
    """
    nav = HEADER.read_text(encoding="utf-8").split("def _render_topnav", 1)[1]
    # Bound the nav markup before splitting. The final group's chunk otherwise
    # runs on into the trailing script and mobile-footer links, which counted
    # More as 9 when it has 5 -- an overcount is as useless as the undercount it
    # replaced, just noisier.
    nav = nav.split("<script", 1)[0]
    sizes: dict[str, int] = {}
    chunks = nav.split('<div class="ua-tnav-group')
    for chunk in chunks[1:]:
        label = re.search(
            r'<span class="ua-tnav-trigger">([^<]+?)\s*<span class="ua-tnav-caret">',
            chunk,
        )
        if not label:
            continue
        # Stop at the start of the next top-level group (already split) or the
        # end of this chunk; count only anchors inside the dropdown.
        drop = chunk.split('<div class="ua-tnav-drop">', 1)
        if len(drop) < 2:
            continue
        sizes[label.group(1).strip()] = len(re.findall(r'<a[^>]*href="/', drop[1]))
    return sizes


def test_no_dropdown_is_too_long_to_scan() -> None:
    """Reachable is necessary, not sufficient.

    The first pass at this simply appended the ten orphaned pages to their
    nearest existing group, which pushed Signals to nine entries and Research to
    eight. That trades one navigation problem for another: a dropdown long
    enough to need scanning is one nobody reads to the bottom of, so the last
    items are hidden just as effectively as before. Split a group instead.
    """
    oversized = {k: v for k, v in _dropdown_sizes().items() if v > MAX_ITEMS_PER_DROPDOWN}
    assert not oversized, (
        f"dropdowns over {MAX_ITEMS_PER_DROPDOWN} items: {oversized}. Split into "
        "a new nav group rather than lengthening an existing one."
    )


def test_every_dropdown_actually_has_items() -> None:
    empty = [k for k, v in _dropdown_sizes().items() if v == 0]
    assert not empty, f"nav groups with no links: {empty}"
