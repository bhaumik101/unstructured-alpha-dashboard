"""The out-of-sample track record: do readings hold up a year later?

What must hold:
  * "next" never sees the data "then" was measured on (no leakage);
  * a stable built-in exposure keeps its direction; noise sits near a coin flip;
  * the summary arithmetic is right;
  * every run is kept, and the page shows the newest -- or says none exists;
  * the cron runs monthly inside the weekly group, batch by batch, and fails
    loudly when it measured nothing.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import exposure as ex  # noqa: E402
from utils import track_record as tr  # noqa: E402

END = date(2026, 9, 11)


def _world(seed=3, days=2100, n_noise=6, flip_at=None):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end="2026-09-11", periods=days)
    n = len(idx)
    mkt = rng.normal(0.04, 1.0, n)
    ch = {"rates": rng.normal(0, .05, n), "inflation": rng.normal(0, .025, n),
          "dollar": rng.normal(0, .4, n), "oil": rng.normal(0, 1.8, n), "credit": rng.normal(0, .02, n)}

    def P(r):
        return pd.Series(100 * np.cumprod(1 + r / 100), idx)

    prices = {"SPY": P(mkt), "STABLE": P(.8 * mkt + .3 * ch["oil"] + rng.normal(0, .9, n))}
    for i in range(n_noise):
        prices[f"NOISE{i}"] = P(mkt + rng.normal(0, .9, n))
    if flip_at is not None:
        beta = np.where(idx <= pd.Timestamp(flip_at), .4, -.4)
        prices["FLIP"] = P(.8 * mkt + beta * ch["oil"] + rng.normal(0, .6, n))
    levels = {"DGS10": pd.Series(4 + np.cumsum(ch["rates"]), idx),
              "T10YIE": pd.Series(2.3 + np.cumsum(ch["inflation"]), idx),
              "DTWEXBGS": pd.Series(120 * np.cumprod(1 + ch["dollar"] / 100), idx),
              "DCOILWTICO": pd.Series(80 * np.cumprod(1 + ch["oil"] / 100), idx),
              "BAA10Y": pd.Series(1.8 + np.cumsum(ch["credit"]), idx)}
    return prices, levels


@pytest.fixture(scope="module")
def study():
    prices, levels = _world()
    return tr.run_study(prices, levels, END)


def test_a_stable_exposure_keeps_its_direction():
    prices, levels = _world()
    rows = [r for r in tr.study_pairs(prices, levels, END)
            if r["ticker"] == "STABLE" and r["factor"] == "oil"]
    assert len(rows) >= 5
    assert all(r["evidence"] == "clear" for r in rows)
    assert sum(r["then"] * r["next"] > 0 for r in rows) / len(rows) >= 0.9


def test_noise_lands_near_a_coin_flip(study):
    zero = study["by_label"]["indistinct"]
    assert zero["n"] >= 100 and 0.35 <= zero["same_direction"] <= 0.65


def test_next_never_sees_then_s_data():
    """FLIP's oil exposure reverses exactly at an origin. If "next" leaked any
    of "then"'s weeks it would lean back toward the old sign."""
    prices, levels = _world(n_noise=0, flip_at="2024-03-08")
    weekly = ex.to_weekly_returns(prices["FLIP"])
    market = ex.to_weekly_returns(prices["SPY"])
    origin = pd.Timestamp("2024-03-08")
    rows = [r for r in tr.pairs_for_stock(weekly, market, tr.weekly_changes(levels), [origin])
            if r["factor"] == "oil"]
    # Built in: +0.4 before, -0.4 after, i.e. +4% / -4% per 10% oil. A "next"
    # that saw any pre-origin weeks would be pulled toward zero.
    assert rows and rows[0]["then"] == pytest.approx(4.0, abs=1.0)
    assert rows[0]["next"] == pytest.approx(-4.0, abs=1.0)


def test_summary_arithmetic():
    pairs = [
        {"origin": "2024-01-05", "factor": "oil", "evidence": "clear", "then": 2.0, "then_se": .2,
         "next": 1.8, "next_se": .3, "ticker": "A"},   # same sign, consistent
        {"origin": "2024-01-05", "factor": "oil", "evidence": "clear", "then": 2.0, "then_se": .2,
         "next": -1.0, "next_se": .3, "ticker": "B"},  # flipped, inconsistent
        {"origin": "2024-01-05", "factor": "rates", "evidence": "indistinct", "then": .1,
         "then_se": .5, "next": .2, "next_se": .5, "ticker": "A"},
    ]
    s = tr.summarize(pairs)
    assert s["by_label"]["clear"] == {"n": 2, "same_direction": 0.5, "consistent": 0.5}
    assert s["by_label"]["tentative"] is None
    assert s["n_pairs"] == 3 and s["n_stocks"] == 2


def test_origins_leave_room_for_both_windows(study):
    origins = [pd.Timestamp(o) for o in study["origins"]]
    assert origins and all(o.weekday() == 4 for o in origins)
    assert max(origins) <= pd.Timestamp(END) - pd.Timedelta(weeks=tr.NEXT_WEEKS)
    assert all((b - a).days == 26 * 7 for a, b in zip(origins, origins[1:]))


# ── storage and the cron ────────────────────────────────────────────────────

@pytest.fixture
def store(monkeypatch, tmp_path):
    from utils import db

    engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}")
    db.metadata.create_all(engine, tables=[db.research_results])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    return engine


def test_every_run_is_kept_and_the_newest_is_shown(store, study):
    from sqlalchemy import func, select

    from utils import db

    assert tr.latest() is None
    assert tr.save(dict(study, marker="first")) and tr.save(dict(study, marker="second"))
    assert tr.latest()["marker"] == "second"
    with store.begin() as conn:
        assert conn.execute(select(func.count()).select_from(db.research_results)).scalar() == 2


def test_the_cron_reruns_monthly():
    from cron import track_record as job

    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    assert not job.is_fresh(None, now)
    assert job.is_fresh({"computed_at": (now - timedelta(days=5)).isoformat()}, now)
    assert not job.is_fresh({"computed_at": (now - timedelta(days=40)).isoformat()}, now)


def test_a_run_cut_short_is_redone_next_week():
    """A deadline-stopped run covers part of the index; it must not count as
    this month's result."""
    from cron import track_record as job

    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    recent = (now - timedelta(days=5)).isoformat()
    assert job.is_fresh({"computed_at": recent, "stopped": None}, now)
    assert not job.is_fresh({"computed_at": recent, "stopped": "deadline"}, now)


def test_batches_give_the_same_answer_as_one_pass():
    from cron import track_record as job

    prices, levels = _world(days=2400)
    whole = tr.summarize([dict(r) for r in tr.study_pairs(prices, levels, END)])
    fetched = []

    def prices_batch(tickers, start, end):
        fetched.append(tickers)
        return {t: prices[t] for t in tickers if t in prices}

    batched = job.study_in_batches([t for t in prices if t != "SPY"], prices_batch,
                                   lambda sid, s, e: levels[sid], END, batch=3)
    assert len(fetched) >= 3, "prices were not fetched in batches"
    assert batched["by_label"] == whole["by_label"] and batched["n_pairs"] == whole["n_pairs"]


def test_a_download_that_never_returns_cannot_stall_the_run():
    """The first live run sat silent for hours: yfinance's threaded download
    waits for every thread with no limit. A hung batch must fall back to
    one-at-a-time fetches and give the same answer, not hold the process."""
    import threading
    import time

    from cron import track_record as job

    prices, levels = _world(days=2400)
    whole = tr.summarize([dict(r) for r in tr.study_pairs(prices, levels, END)])
    never = threading.Event()

    def hung_batch(tickers, start, end):
        never.wait()   # a download that never answers

    t0 = time.monotonic()
    out = job.study_in_batches([t for t in prices if t != "SPY"], hung_batch,
                               lambda sid, s, e: levels[sid], END, batch=3,
                               one=lambda t, s, e: prices[t], batch_timeout=0.2)
    assert time.monotonic() - t0 < 30
    assert out["by_label"] == whole["by_label"] and out["n_pairs"] == whole["n_pairs"]
    never.set()


def test_the_deadline_stops_between_batches_and_says_so():
    from cron import track_record as job

    prices, levels = _world(days=2400)
    ticks = iter(range(1000))
    batches = []

    def prices_batch(tickers, start, end):
        batches.append(tickers)
        return {t: prices[t] for t in tickers if t in prices}

    out = job.study_in_batches([t for t in prices if t != "SPY"], prices_batch,
                               lambda sid, s, e: levels[sid], END, batch=2,
                               deadline=1.5, clock=lambda: next(ticks))
    assert out["stopped"] == "deadline"
    assert 0 < len(batches) < 4 and out["n_stocks"] <= 2 * len(batches)


def test_each_batch_is_dropped_from_the_price_cache():
    """The batch fetcher is st.cache_data: left alone it keeps ten years of
    prices for every batch in memory for the rest of the run."""
    from cron import track_record as job

    prices, levels = _world(days=2400)
    cleared = []

    def prices_batch(tickers, start, end):
        return {t: prices[t] for t in tickers if t in prices}

    prices_batch.clear = lambda: cleared.append(1)
    job.study_in_batches([t for t in prices if t != "SPY"], prices_batch,
                         lambda sid, s, e: levels[sid], END, batch=3)
    assert len(cleared) == 3   # 7 stocks in batches of 3


def test_it_refuses_without_the_production_database(monkeypatch):
    from cron import track_record as job

    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert job.main([]) == 2


def test_it_runs_last_in_the_weekly_group():
    from cron.run_group import GROUPS

    assert GROUPS["weekly-universe"][-1] == "cron.track_record"


# ── the page ────────────────────────────────────────────────────────────────

def _page(monkeypatch, result):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from tests.conftest import DASHBOARD_ROOT

    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    monkeypatch.setattr(tr, "latest", lambda: result)
    at = AppTest.from_file(str(DASHBOARD_ROOT / "pages/71_Evidence.py"), default_timeout=120)
    at.run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    return " ".join(m.value for m in at.markdown)


def test_the_page_says_plainly_when_no_run_exists(monkeypatch):
    text = _page(monkeypatch, None)
    assert "has not been published yet" in text


def test_the_page_shows_the_newest_run(monkeypatch, study):
    text = _page(monkeypatch, dict(study, computed_at="2026-10-02T03:00:00+00:00"))
    assert "Same direction a year later" in text and "50%: a coin flip" in text
    assert "Consistent within the uncertainty" in text and "By force" in text
    assert "it is not a forecast" in text


def test_the_page_says_when_a_run_was_partial(monkeypatch, study):
    full = dict(study, computed_at="2026-10-02T03:00:00+00:00", universe=503, stopped=None)
    text = _page(monkeypatch, full)
    assert f"{study['n_stocks']:,} of 503 S&amp;P 500 companies" in text
    assert "stopped at its time limit" not in text

    text = _page(monkeypatch, dict(full, stopped="deadline"))
    assert "stopped at its time limit" in text and "only the companies it reached" in text
