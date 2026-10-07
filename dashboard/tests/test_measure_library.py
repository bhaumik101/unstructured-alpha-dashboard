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
    from utils import exposure as ex

    # The price-sourced forces (gold, copper) ride in the same batch fetch.
    assert len(batches) == 1
    assert set(batches[0]) == {"AAA", "BBB", "CCC", "SPY", *ex.EXTRA_PRICE_TICKERS}


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
    assert ml.main(["--budget", "1", "--passes", "1"]) == 1


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


def test_a_price_yahoo_cant_return_does_not_refetch_the_batch_per_stock():
    """GLD missing from every answer must still mean one fetch per batch."""
    prices_batch, sf, batches = _world_with({"AAA", "BBB", "CCC", "DDD"})
    list(ml.measure_batch([("AAA", ""), ("BBB", ""), ("CCC", ""), ("DDD", "")], prices_batch,
                          ml.memo_series(sf), END))
    assert len(batches) == 1, f"{len(batches)} fetches for one batch"


# ── order and cost (after the first live run reached only A..EBAY) ──────────

def test_the_largest_companies_are_measured_before_the_alphabet():
    index = [("AAA", "A Co"), ("MSFT", "Microsoft"), ("ABC", "ABC Co"), ("JPM", "JPMorgan")]
    plan = ml.plan_targets(index, [], NOW, fresh_days=6, priority=["MSFT", "JPM"])
    assert [t for t, _ in plan] == ["MSFT", "JPM", "AAA", "ABC"]


def test_priority_never_jumps_ahead_of_a_stale_refresh():
    """Order only among equals: never-measured still goes before anything
    measured, and a stale refresh still goes oldest first."""
    index = [("MSFT", "Microsoft"), ("AAA", "A Co")]
    library = [{"ticker": "MSFT", "measured_at": "2026-09-01T00:00:00+00:00", "name": "Microsoft"}]
    plan = ml.plan_targets(index, library, NOW, fresh_days=6, priority=["MSFT"])
    assert [t for t, _ in plan] == ["AAA", "MSFT"]


def test_every_priority_name_is_in_the_index():
    listed = {t for t, _ in ml.load_constituents()}
    assert ml.PRIORITY and set(ml.PRIORITY) <= listed
    assert len(set(ml.PRIORITY)) == len(ml.PRIORITY)


def test_the_library_does_not_fetch_ten_years_per_stock():
    """It stores readings only, so the rolling line's history is skipped: the
    fetch window stays near the report's own three years (plus the growth
    reading's), and the readings are identical to a full report's."""
    from datetime import date as _date

    from utils import exposure as ex

    windows = []
    pf, sf = _daily_world()

    def prices(tickers, start, end):
        windows.append((_date.fromisoformat(start), _date.fromisoformat(end)))
        return pf(tickers, start, end)

    lib_report = list(ml.measure_batch([("XOM", "Exxon")], prices, ml.memo_series(sf), END))[0][2]
    start, end = windows[0]
    assert (end - start).days < 5 * 365
    assert lib_report["rolling"] == {}
    full = ex.build_exposure_report([{"ticker": "XOM", "weight_pct": 100}], pf, sf, end=END,
                                    max_holdings=1)
    assert lib_report["portfolio"]["readings"] == full["portfolio"]["readings"]
    assert lib_report["extras"]["readings"] == full["extras"]["readings"]


# ── memory: stop on the run's own trend (live: 75 of 426 at 422MB, guard 390) ─

def _rss_seq(start, per_batch):
    """rss() is read before and after each batch; memory grows per_batch each."""
    state = {"v": start, "reads": 0}

    def rss():
        state["reads"] += 1
        if state["reads"] % 2 == 0:          # the read after a batch
            state["v"] += per_batch
        return state["v"]
    return rss


def test_a_flat_run_is_not_stopped_by_the_old_390mb_guard(store):
    targets = [(f"T{i}", f"Co {i}") for i in range(8)]
    prices_batch, sf, _ = _world_with({t for t, _ in targets})
    stats = _run(targets, prices_batch, sf, max_rss_mb=ml.DEFAULT_MAX_RSS_MB,
                 rss=_rss_seq(400.0, 1.0))
    assert stats["stop"] == "done" and stats["measured"] == 8


def test_a_growing_run_stops_before_the_next_batch_would_cross(store):
    targets = [(f"T{i}", f"Co {i}") for i in range(10)]
    prices_batch, sf, _ = _world_with({t for t, _ in targets})
    # 380 -> 410 -> 440: a third batch growing like the first would reach 470+.
    stats = _run(targets, prices_batch, sf, max_rss_mb=460, rss=_rss_seq(380.0, 30.0))
    assert stats["stop"] == "memory" and stats["measured"] == 4      # two batches of 2


def test_each_batch_is_dropped_from_the_price_cache(store):
    targets = [(f"T{i}", f"Co {i}") for i in range(6)]
    prices_batch, sf, _ = _world_with({t for t, _ in targets})
    cleared = []
    prices_batch.clear = lambda: cleared.append(1)
    _run(targets, prices_batch, sf)
    assert len(cleared) == 3


def test_the_ceiling_is_the_librarys_own_and_under_render_s_limit():
    import inspect

    assert 390 < ml.DEFAULT_MAX_RSS_MB < 512
    assert "MEASURE_MAX_RSS_MB" in inspect.getsource(ml)


def test_the_weekly_job_runs_after_the_dollar_series_is_published():
    """A week counts only when all five core series have it, and the dollar
    (DTWEXBGS, Fed H.10) is published Mondays. Run on Sunday, the 2026-10-04
    library said "data through Sep 25" with Oct 2's closes already in."""
    import re

    from tests.conftest import DASHBOARD_ROOT

    yaml = (DASHBOARD_ROOT / "render.yaml").read_text(encoding="utf-8")
    block = yaml.split("name: unstructured-alpha-grow-universe", 1)[1].split("- type:", 1)[0]
    minute, hour, _dom, _mon, dow = re.search(r'schedule:\s*"([^"]+)"', block).group(1).split()
    assert dow == "2", "Tuesday: the first day after Monday's H.10 release"
    assert int(hour) < 4, "before score-core at 04:10 UTC"


# ── passes: fresh processes until the index is fresh ────────────────────────

def _passes(statuses, deadline_min=40, passes=12, skip="", clock=None):
    """Drive _supervise with scripted pass results; returns (rc, calls)."""
    calls = []
    script = iter(statuses)

    def run_pass(argv, timeout_s):
        calls.append(argv)
        return next(script)

    args = ml._parse(["--passes", str(passes), "--deadline-min", str(deadline_min), "--skip", skip])
    rc = ml._supervise(args, run_pass=run_pass, clock=clock or (lambda: 0.0))
    return rc, calls


def test_passes_continue_until_everything_is_fresh():
    """The live run stopped on memory after 75 stocks in 3 of its 40 minutes."""
    rc, calls = _passes([
        {"targets": 300, "measured": 75, "failed": 0, "stop": "memory"},
        {"targets": 225, "measured": 75, "failed": 0, "stop": "memory"},
        {"targets": 150, "measured": 150, "failed": 0, "stop": "done"},
        {"targets": 0, "measured": 0, "failed": 0, "stop": "fresh"},
    ])
    assert rc == 0 and len(calls) == 4
    assert all("--passes" in c and c[c.index("--passes") + 1] == "1" for c in calls)


def test_a_stock_that_failed_is_skipped_by_later_passes():
    rc, calls = _passes([
        {"targets": 100, "measured": 50, "failed": 2, "failed_tickers": ["BAD1", "BAD2"]},
        {"targets": 48, "measured": 47, "failed": 1, "failed_tickers": ["BAD3"]},
        {"targets": 0, "measured": 0},
    ], skip="OLD")
    assert "--skip" not in calls[0][:-2] or calls[0][calls[0].index("--skip") + 1] == "OLD"
    assert calls[1][calls[1].index("--skip") + 1] == "OLD,BAD1,BAD2"
    assert calls[2][calls[2].index("--skip") + 1] == "OLD,BAD1,BAD2,BAD3"


def test_a_pass_that_measures_nothing_stops_the_run():
    rc, calls = _passes([
        {"targets": 300, "measured": 75},
        {"targets": 225, "measured": 0, "stop": "memory"},
        {"targets": 225, "measured": 75},          # never reached
    ])
    assert rc == 0 and len(calls) == 2


def test_an_outage_from_the_first_pass_fails_the_run():
    rc, calls = _passes([{"targets": 300, "measured": 0, "failed": 300}])
    assert rc == 1 and len(calls) == 1


def test_a_week_with_nothing_to_do_is_not_a_failure():
    rc, calls = _passes([{"targets": 0, "measured": 0, "stop": "fresh"}])
    assert rc == 0


def test_a_pass_that_died_stops_the_run():
    rc, calls = _passes([{"targets": 300, "measured": 75}, None, {"targets": 1, "measured": 1}])
    assert rc == 0 and len(calls) == 2


def test_the_deadline_is_shared_and_each_pass_gets_what_is_left():
    t = iter([0, 0, 600, 2370])         # seconds: start, before pass 1, before pass 2, before pass 3
    rc, calls = _passes([{"targets": 300, "measured": 75}, {"targets": 225, "measured": 75}],
                        deadline_min=40, clock=lambda: next(t))
    assert len(calls) == 2
    assert calls[0][calls[0].index("--deadline-min") + 1] == "40"
    assert calls[1][calls[1].index("--deadline-min") + 1] == "30"


def test_a_pass_writes_its_status_for_the_supervisor(monkeypatch, store, tmp_path):
    import json

    import utils.db as db
    import utils.fetchers as fetchers

    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr(db, "init_db", lambda: None)
    monkeypatch.setattr(fetchers, "fetch_prices_batch", lambda *a: {})
    monkeypatch.setattr(ml, "load_constituents", lambda: [("AAA", "A Co"), ("BBB", "B Co")])
    path = tmp_path / "status.json"
    assert ml.main(["--passes", "1", "--skip", "BBB", "--status-file", str(path)]) == 1
    st = json.loads(path.read_text())
    assert st["targets"] == 1 and st["measured"] == 0 and st["failed_tickers"] == ["AAA"]


@pytest.mark.slow     # spawns a real interpreter
def test_a_pass_that_dies_before_writing_its_status_reads_as_dead():
    assert ml._run_pass_subprocess(["--no-such-flag"], timeout_s=60) is None


def test_the_group_runs_passes_by_default():
    assert ml._parse(None).passes == ml.DEFAULT_PASSES > 1


def test_main_supervises_unless_it_is_one_pass(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setattr(ml, "_supervise", lambda args: 41)
    monkeypatch.setattr(ml, "_one_pass", lambda args: 42)
    assert ml.main([]) == 41                                    # the group's call
    assert ml.main(["--passes", "1"]) == 42
    assert ml.main(["--status-file", "/tmp/x.json"]) == 42      # a pass never spawns passes
