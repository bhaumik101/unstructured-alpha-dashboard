"""Force pages are rendered once per data week, not on every request.

Built per request they took 0.5-3.6s each (Nov 2026 live crawl). The cache
key carries the library's data week and size, so a weekly refresh or a newly
measured stock produces a fresh page -- never last week's numbers.
"""

from __future__ import annotations

from tests.test_explore_page import client  # noqa: F401  (fixture)


def test_rendered_once_per_week_and_rebuilt_when_the_data_changes(client, monkeypatch):  # noqa: F811
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank Co")
    M._exposure_cache.clear()
    import utils.force_pages as fp
    calls = []
    real = fp.force_page_html
    monkeypatch.setattr(fp, "force_page_html", lambda *a, **k: calls.append(a[0]) or real(*a, **k))
    first = c.get("/forces/oil")
    assert first.status_code == 200 and c.get("/forces/oil").text == first.text
    assert calls == ["oil"]                                   # the second request was served from cache
    c.get("/forces/rates")
    assert calls == ["oil", "rates"]                          # each force its own page
    assert lib.record(_one("PLAIN"), "Plain Co")              # the library changes
    M._exposure_cache.pop("__all__", None)
    c.get("/forces/oil")
    assert calls == ["oil", "rates", "oil"]                   # rebuilt, not served stale
