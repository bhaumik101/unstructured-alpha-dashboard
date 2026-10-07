"""What changed (www/changes): each stock's newest reading against its previous.

What must hold: a reading crossing into "held up" is reported as gained and
the reverse as lost; shifts rank by the size of the change, among readings
that held up at either point; only stocks on the newest data week are
compared, each against its own previous reading (whose date is shown); the
library can return that previous week; and with nothing to compare the page
is noindex and kept out of the sitemap.
"""

from __future__ import annotations

import copy

from tests.test_explore_page import _stock, client  # noqa: F401  (fixture)
from utils import changes_page as cp


def _wk(stock, as_of):
    s = copy.deepcopy(stock)
    s["as_of"] = as_of
    return s


NOW = [_wk(_stock("XOM", "Exxon", oil=(2.4, "clear"), rates=(0.2, "indistinct"), gold=(1.0, "clear")), "2026-10-02"),
       _wk(_stock("DAL", "Delta", oil=(-1.9, "tentative"), dollar=(3.0, "indistinct")), "2026-10-02"),
       _wk(_stock("OLD", "Stale Co", oil=(3.0, "clear")), "2026-09-25")]       # not on the newest week
BEFORE = [_wk(_stock("XOM", "Exxon", oil=(2.1, "clear"), rates=(0.6, "tentative"), gold=(0.4, "indistinct")), "2026-09-25"),
          _wk(_stock("DAL", "Delta", oil=(-0.4, "indistinct"), dollar=(-2.0, "indistinct")), "2026-09-18"),
          _wk(_stock("OLD", "Stale Co", oil=(0.1, "indistinct")), "2026-09-18")]


def test_crossings_are_reported_both_ways():
    c = cp.changes(NOW, BEFORE)
    assert c["as_of"] == "2026-10-02" and c["compared"] == 2              # OLD left out
    assert [(r["ticker"], r["key"]) for r in c["gained"]] == [("DAL", "oil"), ("XOM", "gold")]
    assert [(r["ticker"], r["key"]) for r in c["lost"]] == [("XOM", "rates")]
    dal = c["gained"][0]
    assert dal["before_as_of"] == "2026-09-18"                           # its own previous, not "last week"


def test_shifts_rank_by_change_among_readings_that_held_up_at_either_point():
    c = cp.changes(NOW, BEFORE)
    order = [(r["ticker"], r["key"]) for r in c["shifts"]]
    assert order == [("DAL", "oil"), ("XOM", "gold"), ("XOM", "rates"), ("XOM", "oil")]
    # DAL's dollar reading swung 5 points but never held up: noise, not a shift.


def test_the_page_states_what_a_crossing_means():
    html = cp.changes_page_html(NOW, BEFORE, "https://www.x", "https://app.x")
    assert "2 readings now hold up that did not before and 1 no longer do" in html
    assert "almost always close to it already" in html and "not a forecast" in html
    assert "noindex" not in html


def test_nothing_to_compare_is_noindex_and_unlisted(client):  # noqa: F811
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    r = c.get("/changes")
    assert r.status_code == 200 and 'content="noindex' in r.text
    assert "/changes</loc>" not in c.get("/sitemap.xml").text


def test_the_library_returns_each_stocks_previous_week(client):  # noqa: F811
    c, _one, lib, M = client
    rep = _one("BANK")
    first = copy.deepcopy(rep)
    from datetime import date, timedelta
    week_before = (date.fromisoformat(str(rep["as_of"])[:10]) - timedelta(days=7)).isoformat()
    first["as_of"] = week_before
    assert lib.record(first, "Bank Co") and lib.record(rep, "Bank Co")
    prev = lib.previous()
    assert [p["ticker"] for p in prev] == ["BANK"] and prev[0]["as_of"] == week_before
    assert prev[0]["exposures"]
    M._exposure_cache.clear()
    r = c.get("/changes")
    assert r.status_code == 200 and "noindex" not in r.text
    assert "/changes</loc>" in c.get("/sitemap.xml").text
