"""The weekly job that measures the S&P 500 into the stock library.

Before it, the library only filled when someone opened a stock's page, so the
public /exposure pages -- and the /ticker redirects that point at them --
existed for a handful of names.

What must hold:
  * stalest first, so a run cut short resumes where it stopped next week;
  * a stock measured this week is left alone;
  * each economic series is fetched once per run, not once per stock;
  * a stock that can't be measured is skipped, never filled in;
  * a run that measured nothing fails loudly.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from cron import measure_library as ml  # noqa: E402
from tests.test_exposure import _daily_world  # noqa: E402

NOW = datetime(2026, 9, 14, 6, 0, tzinfo=timezone.utc)
END = date(2026, 9, 11)


# ── the list ────────────────────────────────────────────────────────────────

def test_the_constituent_list_is_the_index_in_yahoo_form():
    rows = ml.load_constituents()
    tickers = [t for t, _ in rows]
    assert 495 <= len(rows) <= 510, "the S&P 500 has ~503 share classes"
    assert len(set(tickers)) == len(tickers)
    assert "BRK-B" in tickers and "BRK.B" not in tickers, "Yahoo spells class shares with a dash"
    assert dict(rows)["AAPL"] == "Apple Inc."
    assert all(name for _, name in rows)


def test_every_listed_symbol_would_get_a_page():
    from utils.exposure_pages import SYMBOL_RE

    assert all(SYMBOL_RE.match(t) for t, _ in ml.load_constituents())


# ── what to measure ─────────────────────────────────────────────────────────

def test_never_measured_first_then_oldest_and_fresh_ones_skipped():
    index = [("AAA", "A Co"), ("BBB", "B Co"), ("CCC", "C Co")]
    library = [{"ticker": "AAA", "measured_at": "2026-09-01T00:00:00+00:00", "name": "A Co"},
               {"ticker": "CCC", "measured_at": "2026-09-13T00:00:00+00:00", "name": "C Co"},
               {"ticker": "ZZZ", "measured_at": "2026-08-01T00:00:00+00:00", "name": "Viewed Co"}]
    plan = ml.plan_targets(index, library, NOW, fresh_days=6)
    assert [t for t, _ in plan] == ["BBB", "ZZZ", "AAA"], plan
    assert ("ZZZ", "Viewed Co") in plan, "a stock someone viewed is refreshed too"


def test_a_second_run_the_same_week_has_nothing_to_do():
    index = [("AAA", "A Co")]
    library = [{"ticker": "AAA", "measured_at": NOW.isoformat(), "name": "A Co"}]
    assert ml.plan_targets(index, library, NOW, fresh_days=6) == []


# ── fetching ────────────────────────────────────────────────────────────────

def test_each_series_is_fetched_once_per_run():
    calls = []

    def fetch(sid, s, e):
        calls.append(sid)
        if sid == "BAD":
            raise ConnectionError("down")
        return sid.lower()

    f = ml.memo_series(fetch)
    for _ in range(3):
        assert f("DGS10", "a", "b") == "dgs10"
        assert f("BAD", "a", "b") is None
    assert calls == ["DGS10", "BAD"], "a failure is remembered, not retried 500 times"


def _world_with(tickers):
    """The synthetic world from test_exposure, with extra stocks cloned from XOM."""
    pf, sf = _daily_world()
    base = pf(["XOM", "SPY"], "", "")

    batches = []

    def prices_batch(tickers_, start, end):
        batches.append(tuple(tickers_))
        return {t: (base["SPY"] if t == "SPY" else base["XOM"]) for t in tickers_
                if t == "SPY" or t in tickers}
    return prices_batch, sf, batches


def test_one_price_fetch_per_batch_not_per_stock():
    prices_batch, sf, batches = _world_with({"AAA", "BBB", "CCC"})
    got = list(ml.measure_batch([("AAA", "A"), ("BBB", "B"), ("CCC", "C")], prices_batch,
                                ml.memo_series(sf), END))
    assert [r["status"] for _, _, r in got] == ["ok", "ok", "ok"]
    assert len(batches) == 1 and set(batches[0]) == {"AAA", "BBB", "CCC", "SPY"}


# ── the run ─────────────────────────────────────────────────────────────────

@pytest.fixture
def store(monkeypatch, tmp_path):
    from utils import db

    engine = create_engine(f"sqlite:///{tmp_path / 'lib.db'}")
    db.metadata.create_all(engine, tables=[db.stock_measurements, db.stock_exposures])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    return engine


def _run(targets, prices_batch, sf, **kw):
    from utils import stock_library as lib

    opts = dict(record=lib.record, end=END, batch_size=2, deadline=float("inf"),
                max_rss_mb=10_000, rss=lambda: 100.0)
    opts.update(kw)
    return ml.run(targets, prices_batch=prices_batch, series=ml.memo_series(sf), **opts)


def test_measured_stocks_land_in_the_library_with_their_names(store):
    from utils import stock_library as lib

    prices_batch, sf, _ = _world_with({"AAA", "BBB", "CCC"})
    stats = _run([("AAA", "A Co"), ("BBB", "B Co"), ("CCC", "C Co")], prices_batch, sf)
    assert stats == {"targets": 3, "measured": 3, "failed": 0, "stop": "done", "remaining": 0}
    assert {s["ticker"]: s["name"] for s in lib.latest()} == {"AAA": "A Co", "BBB": "B Co",
                                                              "CCC": "C Co"}


def test_a_stock_without_prices_is_skipped_not_invented(store):
    from utils import stock_library as lib

    prices_batch, sf, _ = _world_with({"AAA"})          # GONE has no price data
    stats = _run([("AAA", "A Co"), ("GONE", "Delisted Co")], prices_batch, sf)
    assert stats["measured"] == 1 and stats["failed"] == 1
    assert lib.history("GONE") == []


def test_the_deadline_and_memory_guard_stop_between_batches(store):
    prices_batch, sf, _ = _world_with({"AAA", "BBB", "CCC", "DDD"})
    targets = [("AAA", ""), ("BBB", ""), ("CCC", ""), ("DDD", "")]
    ticks = iter([0, 100])
    stats = _run(targets, prices_batch, sf, deadline=50, clock=lambda: next(ticks))
    assert stats["stop"] == "deadline" and stats["measured"] == 2 and stats["remaining"] == 2

    stats = _run(targets, prices_batch, sf, max_rss_mb=390, rss=lambda: 400.0)
    assert stats["stop"] == "memory" and stats["measured"] == 0


def test_a_run_that_measures_nothing_fails(monkeypatch, store):
    """A prices or FRED outage must show as a failed cron run, not a quiet success."""
    import utils.db as db
    import utils.fetchers as fetchers

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(fetchers, "fetch_prices_batch", lambda *a: {})
    monkeypatch.setattr(ml, "load_constituents", lambda: [("AAA", "A Co")])
    assert ml.main(["--budget", "1"]) == 1


def test_it_refuses_to_run_without_the_production_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert ml.main([]) == 2


# ── scheduling ──────────────────────────────────────────────────────────────

def test_it_runs_weekly_in_the_grow_universe_slot_ahead_of_the_prewarm():
    import yaml

    from cron.run_group import GROUPS

    assert GROUPS["weekly-universe"][0] == "cron.measure_library"
    services = {s["name"]: s for s in yaml.safe_load((_ROOT / "render.yaml").read_text())["services"]}
    assert services["unstructured-alpha-grow-universe"]["startCommand"].endswith(
        "run_group weekly-universe")


def test_called_from_the_group_it_ignores_the_groups_own_argv(monkeypatch):
    """run_group calls main() bare while sys.argv is [run_group, 'weekly-universe']."""
    monkeypatch.setattr(sys, "argv", ["run_group.py", "weekly-universe"])
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert ml.main() == 2, "argparse rejected the group name instead of using defaults"
