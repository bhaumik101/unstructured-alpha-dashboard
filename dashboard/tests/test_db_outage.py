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
