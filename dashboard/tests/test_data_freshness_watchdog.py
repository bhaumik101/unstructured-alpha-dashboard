"""The watchdog must diagnose correctly, not just fail loudly.

Its first scheduled run in production exited 1 with three "unreadable" tables and
announced that a pipeline had stopped writing. Nothing had stopped writing:
DATABASE_URL was never set on the new Render service, so utils.db fell back to
SQLite and the Postgres-only ::timestamptz cast became a syntax error.

Exiting non-zero was right. The explanation was wrong, and a monitor that
misattributes its own misconfiguration to your data pipeline is how alerts get
ignored. These tests pin the distinction: configuration failure, stale table, and
unreadable table are three different findings that all still fail.
"""

from __future__ import annotations

import builtins
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parent.parent
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

from cron import check_data_freshness as watchdog  # noqa: E402


class _FakeConn:
    def __init__(self, result):
        self._result = result

    def execute(self, _stmt):
        if isinstance(self._result, Exception):
            raise self._result
        return types.SimpleNamespace(scalar=lambda: self._result)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakeEngine:
    def __init__(self, dialect: str, result=None):
        self.dialect = types.SimpleNamespace(name=dialect)
        self._result = result

    def connect(self):
        return _FakeConn(self._result)


def _install_engine(monkeypatch, engine):
    """main() does `from utils.db import engine`, so patch that module."""
    fake_db = types.ModuleType("utils.db")
    fake_db.engine = engine
    monkeypatch.setitem(sys.modules, "utils.db", fake_db)


def test_non_postgres_is_reported_as_configuration_not_stale_data(monkeypatch, capsys):
    """The exact production failure: SQLite fallback from a missing DATABASE_URL."""
    _install_engine(monkeypatch, _FakeEngine("sqlite"))

    exit_code = watchdog.main()
    out = capsys.readouterr().out

    assert exit_code == 1, "a watchdog that cannot reach the database must still fail"
    assert "CONFIG" in out
    assert "DATABASE_URL" in out
    assert "not a data problem" in out
    # The bug being pinned: it must NOT blame the pipelines for its own config.
    assert "stopped advancing" not in out
    assert "serving old data" not in out


def test_fresh_postgres_data_passes(monkeypatch, capsys):
    fresh = datetime.now(timezone.utc)
    _install_engine(monkeypatch, _FakeEngine("postgresql", result=fresh))

    exit_code = watchdog.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "PASS" in out


def test_stale_table_fails_and_names_the_writer_as_behind(monkeypatch, capsys):
    ancient = datetime.now(timezone.utc) - timedelta(days=99)
    _install_engine(monkeypatch, _FakeEngine("postgresql", result=ancient))

    exit_code = watchdog.main()
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "STALE" in out
    assert "stopped advancing" in out


def test_unreadable_table_is_not_described_as_a_stalled_writer(monkeypatch, capsys):
    """An unreadable table has other causes; don't assert one we haven't shown."""
    _install_engine(
        monkeypatch, _FakeEngine("postgresql", result=RuntimeError("permission denied"))
    )

    exit_code = watchdog.main()
    out = capsys.readouterr().out

    assert exit_code == 1
    assert "unreadable" in out
    assert "cause not established" in out
    assert "stopped advancing" not in out


def test_thresholds_are_not_silently_loosened():
    """Guard the numbers themselves — the fix for a false alarm must never be
    to widen the window until the alarm stops."""
    assert watchdog.CHECKS["signal_snapshots"][1] == 2
    assert watchdog.CHECKS["score_snapshots"][1] == 4
    assert watchdog.CHECKS["analytics_events"][1] == 3


def test_db_target_never_leaks_credentials():
    """The whole point is that this string is safe to print in a build log."""
    from sqlalchemy.engine import make_url

    class _E:
        url = make_url("postgresql://user:sup3rsecret@db.example.com:5432/appdb")

    target = watchdog._db_target(_E())
    assert target == "db.example.com:5432/appdb"
    assert "sup3rsecret" not in target
    assert "user" not in target


def test_db_target_is_printed_next_to_the_verdict(monkeypatch, capsys):
    """score-core reported written=538 while the app's table sat ten days stale.
    Two services, two databases, no way to see it. Print what we read."""
    from sqlalchemy.engine import make_url

    engine = _FakeEngine("postgresql", result=datetime.now(timezone.utc))
    engine.url = make_url("postgresql://u:p@prod-host:5432/unstructured")
    _install_engine(monkeypatch, engine)

    watchdog.main()
    out = capsys.readouterr().out
    assert "db=prod-host:5432/unstructured" in out
