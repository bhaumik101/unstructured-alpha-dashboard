"""A database outage must never read as "nothing has been measured".

Live on 2026-10-27 the SEO service could not reach Postgres (/readyz: db down).
The library functions return [] on any error, so every stock page answered 404
and the hub a 200 "No stock has been measured yet" -- to a search engine, 500
pages gone. Now: the last good copy is served while one is held, otherwise 503
with Retry-After (come back later); the sitemap 503s rather than shrink.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_explore_page import client  # noqa: F401  (fixture)


def _down(M, monkeypatch):
    from utils import stock_library
    monkeypatch.setattr(stock_library, "latest", lambda limit=500: [])
    monkeypatch.setattr(stock_library, "history", lambda t, limit=26: [])
    monkeypatch.setattr(M, "_check_db", lambda timeout=3.0: False)


def test_an_outage_is_a_503_not_a_404_or_an_empty_page(client, monkeypatch):  # noqa: F811
    c, _one, lib, M = client
    _down(M, monkeypatch)
    for path in ("/exposure/XOM", "/exposure", "/forces/oil", "/sitemap.xml", "/landing.json"):
        r = c.get(path)
        assert r.status_code == 503, path
        assert r.headers.get("retry-after") == "600", path


def test_a_stock_that_is_not_measured_is_still_a_404_when_the_database_is_up(client, monkeypatch):  # noqa: F811
    c, _one, lib, M = client
    monkeypatch.setattr(M, "_check_db", lambda timeout=3.0: True)
    assert c.get("/exposure/ZZZZ").status_code == 404


def test_the_last_good_copy_is_served_through_an_outage(client, monkeypatch):  # noqa: F811
    c, _one, lib, M = client
    assert lib.record(_one("BANK"), "Bank")
    assert "BANK" in c.get("/exposure").text                     # warms the cache
    M._exposure_cache["__all__"] = (-1e12, M._exposure_cache["__all__"][1])   # and lets it expire
    _down(M, monkeypatch)
    r = c.get("/exposure")
    assert r.status_code == 200 and "BANK" in r.text


def test_the_www_sitemap_never_shrinks_to_a_fallback_on_an_upstream_failure():
    route = (Path(__file__).resolve().parent.parent / "unstructured-alpha-web" / "app" / "sitemap.xml"
             / "route.ts").read_text(encoding="utf-8")
    catch = route[route.index("} catch (error) {"):]
    assert "status: 503" in catch and "fallbackSitemap()" not in catch


def test_a_dead_database_fails_in_seconds():
    src = (Path(__file__).resolve().parent.parent / "utils" / "db.py").read_text(encoding="utf-8")
    assert '"connect_args": {"connect_timeout": 5}' in src and '"pool_timeout": 10' in src


def test_a_fresh_process_with_the_database_down_answers_503_and_retries(monkeypatch):
    import pytest
    from fastapi import HTTPException

    import seo.main as M
    from utils import db

    def boom():
        raise RuntimeError("could not connect to server")
    monkeypatch.setattr(db, "init_db", boom)
    monkeypatch.setattr(M, "_ENGINE_READY", False)
    with pytest.raises(HTTPException) as e:
        M._get_engine()
    assert e.value.status_code == 503 and M._ENGINE_READY is False


class _FakeRedis:
    def __init__(self):
        self.d = {}

    def set(self, k, v):
        self.d[k] = v

    def get(self, k):
        return self.d.get(k)


def test_the_snapshot_keeps_only_a_complete_library():
    from utils import library_snapshot as snap
    r = _FakeRedis()
    assert not snap.save([{"ticker": "A"}], client=r) and snap.load(client=r) is None
    stocks = [{"ticker": f"T{i}", "as_of": "2026-10-16", "exposures": {}} for i in range(60)]
    assert snap.save(stocks, client=r)
    saved_at, back = snap.load(client=r)
    assert back == stocks and saved_at
    assert not snap.save(stocks[:3], client=r) and len(snap.load(client=r)[1]) == 60   # never shrunk


def test_after_a_restart_the_stored_copy_is_served_with_a_notice(client, monkeypatch):  # noqa: F811
    from utils import exposure_pages, library_snapshot

    c, _one, lib, M = client
    r = _FakeRedis()
    monkeypatch.setattr(library_snapshot, "_client", lambda: r)
    monkeypatch.setattr(library_snapshot, "MIN_STOCKS", 1)
    monkeypatch.setitem(exposure_pages.SITE_NOTICE, "html", "")
    assert lib.record(_one("BANK"), "Bank")
    assert c.get("/exposure").status_code == 200 and r.get(library_snapshot.KEY)   # saved on a good read
    M._exposure_cache.clear()                                                         # a restart
    _down(M, monkeypatch)
    hub = c.get("/exposure")
    assert hub.status_code == 200 and "BANK" in hub.text
    assert "Live data is temporarily unavailable" in hub.text and 'role="status"' in hub.text
    page = c.get("/exposure/BANK")
    assert page.status_code == 200 and "Live data is temporarily unavailable" in page.text
    assert c.get("/exposure/ZZZZ").status_code == 404        # not in the stored copy either


def test_the_notice_goes_once_the_database_is_back(client, monkeypatch):  # noqa: F811
    from utils import exposure_pages

    c, _one, lib, M = client
    monkeypatch.setitem(exposure_pages.SITE_NOTICE, "html", "<b>Live data is temporarily unavailable.</b>")
    assert lib.record(_one("BANK"), "Bank")
    M._exposure_cache.clear()
    r = c.get("/exposure")
    assert r.status_code == 200 and "temporarily unavailable" not in r.text


def test_readyz_names_why_the_database_is_down_without_leaking_anything(monkeypatch):
    import seo.main as M
    from fastapi.testclient import TestClient

    neon = ('connection to server at "ep-cool-name-123.us-east-2.aws.neon.tech" (3.1.2.3), port 5432 '
            'failed: ERROR:  Your account or project has exceeded the compute time quota. '
            'Upgrade your plan to increase limits.')
    cases = {
        neon: "compute_quota_exceeded",
        "ERROR: Your project has exceeded the data transfer quota.": "data_transfer_quota_exceeded",
        "ERROR: The endpoint has been disabled. Enable it using Neon API and retry.": "endpoint_disabled",
        'FATAL:  password authentication failed for user "neondb_owner"': "auth_failed",
        'FATAL:  role "neondb_owner" does not exist': "auth_failed",
        'FATAL:  database "neondb" does not exist': "project_not_found",
        'could not translate host name "ep-x.neon.tech" to address': "dns",
        "timeout expired": "timeout",
    }
    for msg, kind in cases.items():
        assert M.db_error_kind(RuntimeError(msg)) == kind, msg
    assert M.db_error_kind(ValueError("something new")) == "other:ValueError"

    from utils import db

    class Down:
        def connect(self):
            raise RuntimeError(neon)
    monkeypatch.setattr(db, "engine", Down())
    r = TestClient(M.app).get("/readyz")
    assert r.status_code == 503 and r.json()["db_error"] == "compute_quota_exceeded"
    assert "neon.tech" not in r.text and "3.1.2.3" not in r.text and "neondb" not in r.text
