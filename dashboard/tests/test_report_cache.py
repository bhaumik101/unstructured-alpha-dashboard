"""The shared report cache must be a cache: invisible when it works, harmless when it doesn't.

Measuring a portfolio costs ~25 seconds, and st.cache_data only helps inside
one process. This cache carries that across deploys and instances. The risk is
that a cache becomes a source of truth — serving an outage, a stale answer, or
breaking the page when the database is unavailable. These tests pin the
opposite: only successful reports are stored, rows past the TTL are never
served, and every failure path returns rather than raises.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import report_cache as rc  # noqa: E402
from utils import report_ui as ui  # noqa: E402


KEY = (("BND", 40.0), ("VTI", 60.0))


class _Result:
    def __init__(self, rows=None):
        self._rows = rows or []
    def first(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def __init__(self, store):
        self.store = store
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def execute(self, stmt, *a, **k):
        name = type(stmt).__name__
        if "Insert" in name:
            self.store["writes"].append(dict(stmt.compile().params))
            return _Result()
        if "Delete" in name:
            self.store["deletes"] += 1
            return _Result()
        return _Result(self.store["rows"])


class _Engine:
    def __init__(self, store):
        self.store = store
    def begin(self):
        return _Conn(self.store)


@pytest.fixture
def store(monkeypatch):
    from utils import db
    data = {"rows": [], "writes": [], "deletes": 0}
    monkeypatch.setattr(db, "engine", _Engine(data))
    monkeypatch.setattr(db, "IS_SQLITE", True, raising=False)
    return data


def test_the_same_portfolio_in_any_order_hits_one_key():
    assert rc.cache_key(KEY, 15) == rc.cache_key((("BND", 40.0), ("VTI", 60.0)), 15)
    assert rc.cache_key(KEY, 15) != rc.cache_key(KEY, 25), "the holding cap changes the answer"


def test_a_stored_report_comes_back(store):
    store["rows"] = [(json.dumps({"status": "ok", "as_of": "2026-09-11", "marker": 1}),)]
    assert rc.get(KEY, 15)["marker"] == 1


def test_only_successful_reports_are_stored(store):
    assert rc.put(KEY, 15, {"status": "error", "message": "provider down"}) is False
    assert rc.put(KEY, 15, {"status": "ok", "as_of": "2026-09-11"}) is True
    assert store["writes"], "a good report should be written"


def test_a_stored_failure_is_never_served(store):
    """Belt and braces: even if an error row existed, reading it must miss."""
    store["rows"] = [(json.dumps({"status": "error", "message": "provider down"}),)]
    assert rc.get(KEY, 15) is None


def test_reads_only_consider_rows_inside_the_ttl():
    """The freshness cut-off is computed from TTL_HOURS, not hard-coded."""
    cutoff = datetime.fromisoformat(rc._fresh_after())
    expected = datetime.now(timezone.utc) - timedelta(hours=rc.TTL_HOURS)
    assert abs((cutoff - expected).total_seconds()) < 5


def test_writing_prunes_rows_that_can_never_be_served(store):
    rc.put(KEY, 15, {"status": "ok", "as_of": "2026-09-11"})
    assert store["deletes"] == 1


def test_a_broken_database_never_breaks_the_page(monkeypatch):
    from utils import db

    class _Broken:
        def begin(self):
            raise RuntimeError("database is down")

    monkeypatch.setattr(db, "engine", _Broken())
    assert rc.get(KEY, 15) is None
    assert rc.put(KEY, 15, {"status": "ok"}) is False


# ── the report path uses it ─────────────────────────────────────────────────

def test_a_cached_report_skips_the_engine_entirely(monkeypatch):
    from utils import exposure as ex

    def _boom(*_a, **_k):
        raise AssertionError("the engine ran despite a warm cache")

    monkeypatch.setattr(ex, "build_live_report", _boom)
    monkeypatch.setattr(rc, "get", lambda key, max_holdings: {"status": "ok", "cached": True})
    assert ui.get_report(KEY, 15)["cached"] is True


def test_a_freshly_computed_report_is_stored_for_the_next_process(monkeypatch):
    from utils import exposure as ex

    saved = {}
    monkeypatch.setattr(ex, "build_live_report",
                        lambda holdings, max_holdings=25: {"status": "ok", "fresh": True})
    monkeypatch.setattr(rc, "get", lambda key, max_holdings: None)
    monkeypatch.setattr(rc, "put", lambda key, max_holdings, report: saved.update(report) or True)
    ui._cached_ok_report.clear()

    assert ui.get_report((("CACHEME", 100.0),), 15)["fresh"] is True
    assert saved.get("fresh") is True, "the result should be shared with other processes"
    ui._cached_ok_report.clear()
