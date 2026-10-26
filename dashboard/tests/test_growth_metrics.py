"""Growth is measurable end to end, and the arithmetic on it is honest.

What must hold:
  * every click the landing page reports is one the server keeps (until
    2026-10-26 the hero's two buttons were silently dropped);
  * every public page sends one labelled page view, and the label is one the
    server accepts -- otherwise the free tools are invisible in the numbers;
  * an arrival in the app keeps its utm tags, and only as short tokens;
  * the weekly table counts distinct visitors, leaves the week in progress
    out of the verdict, and says "not enough data" rather than invent a trend.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from tests.test_explore_page import _stock
from tests.test_track_api import _post, client_and_writes  # noqa: F401  (fixture)
from seo.track_api import ALLOWED_ACTIONS, ALLOWED_PAGES
from utils import exposure_pages as ep
from utils.growth_metrics import verdict, weekly

PAGE = (Path(__file__).resolve().parent.parent / "unstructured-alpha-web" / "app" / "page.tsx").read_text(encoding="utf-8")


def test_every_click_the_landing_reports_is_one_the_server_keeps():
    union = PAGE[PAGE.index("type AppOpenAction ="):PAGE.index(";", PAGE.index("type AppOpenAction ="))]
    sent = set(re.findall(r'"([a-z_]+)"', union))
    assert {"hero_sample", "hero_own", "report_sample"} <= sent           # the parse found the union
    assert sent <= ALLOWED_ACTIONS, sorted(sent - ALLOWED_ACTIONS)


def test_a_hero_click_is_stored(client_and_writes):  # noqa: F811
    client, writes = client_and_writes
    _post(client, {"event": "app_opened", "page": "Landing", "action": "hero_sample"})
    assert len(writes) == 1 and writes[0]["properties"]["action"] == "hero_sample"


def test_public_pages_get_labels_the_server_accepts():
    assert ep.page_label("https://www.x/exposure") == "Stocks"
    assert ep.page_label("https://www.x/exposure/XOM") == "Stock page"
    assert ep.page_label("https://www.x/forces/oil") == "Force page"
    assert ep.page_label("https://www.x/sectors/energy") == "Sector page"
    assert ep.page_label("https://www.x/heatmap") == "Heatmap"
    assert ep.page_label("https://www.x/brief") is None and ep.page_label("https://www.x/") is None
    assert ep.ALL_PAGE_LABELS <= ALLOWED_PAGES
    # Every page in the site's navigation is measured.
    for href, _ in ep.NAV + ep.MORE:
        assert ep.page_label("https://www.x" + href), href


def test_a_public_page_view_is_stored_under_its_label(client_and_writes):  # noqa: F811
    client, writes = client_and_writes
    _post(client, {"event": "page_view", "page": "Stock page"})
    assert writes[0]["page"] == "Stock page"


def test_each_public_page_sends_one_labelled_beacon():
    html = ep.hub_page_html([_stock("XOM", "Exxon", oil=(2.0, "clear"))], "https://www.x", "https://app.x")
    assert html.count('navigator.sendBeacon("/api/track"') == 1
    assert 'page:"Stocks"' in html and "window.__uaTrackInit" in html
    assert "cookie" not in ep._TRACK_JS and "localStorage" not in ep._TRACK_JS


def test_app_arrivals_keep_their_utm_tags_as_short_tokens():
    from utils.header import utm_props
    assert utm_props({"utm_source": "public_tools", "utm_medium": "owned", "utm_content": "heatmap"}) == {
        "utm_source": "public_tools", "utm_medium": "owned", "utm_content": "heatmap"}
    assert utm_props({"utm_source": ["Weekly_Email"]}) == {"utm_source": "weekly_email"}
    assert utm_props({"utm_source": "<script>", "utm_content": "x" * 41, "other": "y"}) == {}
    # The public pages' links carry exactly the tags the app keeps.
    link = ep.app_link("https://app.x", "/stock", "https://www.x/heatmap")
    tags = dict(p.split("=") for p in link.split("?")[1].replace("&amp;", "&").split("&"))
    assert utm_props(tags)["utm_source"] == "public_tools" and utm_props(tags)["utm_content"] == "heatmap"


TODAY = date(2026, 10, 28)     # a Wednesday; the week of Oct 26 is in progress


def _pv(ts, visitor, site=False, page="Stocks", utm=None):
    props = {"page": page}
    if site:
        props["site"] = "marketing"
    if utm:
        props["utm_source"] = utm
    return ("page_view", ts, visitor, props)


def test_weeks_count_distinct_visitors_and_who_crossed_from_site_to_app():
    events = [_pv("2026-10-19T10:00:00", "a", site=True), _pv("2026-10-20T10:00:00", "a", site=True),
              _pv("2026-10-20T11:00:00", "a", utm="public_tools"),               # a: site then app
              _pv("2026-10-21T09:00:00", "b", site=True, page="Landing"),
              _pv("2026-10-22T09:00:00", "c"),                                   # c: app only
              ("app_opened", "2026-10-21T09:01:00", "b", {"site": "marketing", "action": "hero_sample"})]
    rows = weekly(events, ["2026-10-22T12:00:00"], weeks=2, today=TODAY)
    wk = rows[0]
    assert wk["week"] == date(2026, 10, 19) and not wk["partial"] and rows[1]["partial"]
    assert wk["site_visitors"] == 2 and wk["tool_views"] == 2          # Landing is not a tool view
    assert wk["app_visitors"] == 2 and wk["from_tools"] == 1 and wk["crossed"] == 1
    assert wk["app_opens"] == 1 and wk["signups"] == 1


def _flat_weeks(per_week):
    """One distinct site visitor per count, in each of the 8 complete weeks
    before TODAY's week, oldest first."""
    rows = weekly([], weeks=9, today=TODAY)
    for r, n in zip(rows[:-1], per_week):
        r["site_visitors"] = n
    return rows


def test_the_verdict_compares_complete_weeks_and_says_when_there_is_too_little():
    assert verdict(weekly([], weeks=9, today=TODAY))["site_visitors"] == "not enough data"
    assert verdict(_flat_weeks([10] * 4 + [15] * 4))["site_visitors"] == "growing +50%"
    assert verdict(_flat_weeks([10] * 4 + [6] * 4))["site_visitors"] == "shrinking -40%"
    assert verdict(_flat_weeks([10] * 4 + [10, 10, 10, 11]))["site_visitors"] == "flat"
    assert verdict(_flat_weeks([0] * 4 + [3] * 4))["site_visitors"].startswith("new: 12")
    # The week in progress never counts: a huge partial week changes nothing.
    rows = _flat_weeks([10] * 8)
    rows[-1]["site_visitors"] = 1000
    assert verdict(rows)["site_visitors"] == "flat"
    assert verdict(weekly([], weeks=5, today=TODAY))["signups"] == "not enough data"
