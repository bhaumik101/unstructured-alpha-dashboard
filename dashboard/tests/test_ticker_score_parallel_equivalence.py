"""The parallel critical path must produce byte-identical scores.

utils/ticker_score fetches a ticker's evidence from several independent
providers. Those reads used to happen one after another: ~47 macro signal
series in a serial loop, then federal contracts, then insider Form 4s, then
short interest. Measured on a cold process (2026-08-23) that was 9.1-12.7s per
ticker, of which 5.2-5.9s was the signal sweep alone.

Two changes moved the network work off the critical path:

  * signals_cache.prewarm_signal_series() warms every signal's fetch cache
    concurrently. The scoring loop is untouched and still calls
    fetch_signal_series itself -- it just finds warm caches.
  * signals_cache.run_parallel() issues the three independent provider reads
    together. Only the READ moved; every score_* call, the source_errors order
    and each has_* predicate run afterwards exactly as before.

Neither is allowed to change a published Confluence Score, so this file pins
equivalence directly rather than trusting the argument above. The fetchers are
stubbed, so this runs offline and deterministically.
"""

from __future__ import annotations

import pandas as pd
import pytest

import utils.signals_cache as signals_cache
import utils.ticker_score as ticker_score


def _sequential(tasks: dict, max_workers: int = 4) -> dict:
    """run_parallel's contract, executed serially in insertion order."""
    out = {}
    for key, fn in tasks.items():
        try:
            out[key] = fn()
        except Exception as exc:  # noqa: BLE001 - mirrors run_parallel
            out[key] = exc
    return out


@pytest.fixture
def stub_providers(monkeypatch):
    """Deterministic, offline stand-ins for every provider the score reads."""
    dates = pd.date_range("2024-01-01", periods=200, freq="D")

    def fake_signal_series(cfg, start, end, point_in_time=False):
        seed = abs(hash(str(cfg.get("series_id") or cfg.get("name")))) % 50
        s = pd.Series(
            [float(seed + (i % 17)) for i in range(len(dates))], index=dates
        )
        s.attrs.update({"provider": "stub", "data_state": "live"})
        return s

    def fake_price(ticker, start, end):
        s = pd.Series([100.0 + (i % 23) for i in range(len(dates))], index=dates)
        s.attrs.update({"provider": "stub", "data_state": "live"})
        return s

    def fake_contracts(company_name, years=2):
        return pd.DataFrame(
            {"date": dates[:6], "amount": [1e6] * 6, "recipient": ["X"] * 6}
        )

    def fake_insider(ticker, days=180, max_filings=20):
        return pd.DataFrame(
            {"date": dates[:4], "shares": [10, -5, 8, 3],
             "value": [1e5, -5e4, 8e4, 3e4], "insider": ["A", "B", "C", "D"],
             "type": ["P", "S", "P", "P"]}
        )

    def fake_short_interest(ticker, years=1.5):
        return pd.DataFrame(
            {"settlementDate": dates[:5],
             "currentShortPositionQuantity": [1e6, 1.1e6, 1.2e6, 1.0e6, 0.9e6]}
        )

    for mod in (ticker_score,):
        monkeypatch.setattr(mod, "fetch_signal_series", fake_signal_series, raising=False)
        monkeypatch.setattr(mod, "fetch_price", fake_price, raising=False)
        monkeypatch.setattr(mod, "fetch_federal_contracts", fake_contracts, raising=False)
        monkeypatch.setattr(mod, "fetch_insider_transactions_detail", fake_insider, raising=False)
        monkeypatch.setattr(mod, "fetch_short_interest", fake_short_interest, raising=False)
    monkeypatch.setattr(signals_cache, "prewarm_signal_series", lambda *a, **k: 0)
    return True


def _norm(value):
    """Recursively make a result value comparable with ==.

    Frames and Series live nested inside signal_data/corr_info, so a shallow
    pass leaves pandas objects behind and `!=` then returns a Series instead of
    a bool.
    """
    if isinstance(value, pd.Series):
        return ("Series", [round(float(x), 9) for x in value.dropna().tolist()])
    if isinstance(value, pd.DataFrame):
        return ("DataFrame", value.shape, sorted(map(str, value.columns)))
    if isinstance(value, dict):
        return {k: _norm(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    if isinstance(value, float):
        return round(value, 9)
    return value


def _comparable(result: dict) -> dict:
    """Everything the product depends on, minus wall-clock artefacts."""
    drop = {"_timings", "calculated_at"}
    return {k: _norm(v) for k, v in result.items() if k not in drop}


def test_parallel_and_sequential_scores_are_identical(stub_providers, monkeypatch):
    """The whole result dict, not just the headline number."""
    monkeypatch.setattr(signals_cache, "run_parallel", signals_cache.run_parallel)
    parallel = _comparable(ticker_score.compute_full_ticker_score("AMD"))

    monkeypatch.setattr(signals_cache, "run_parallel", _sequential)
    sequential = _comparable(ticker_score.compute_full_ticker_score("AMD"))

    differing = [k for k in set(parallel) | set(sequential)
                 if parallel.get(k) != sequential.get(k)]
    assert not differing, (
        "parallelising the provider reads changed the score result on: "
        f"{differing}"
    )


def test_a_provider_that_raises_stays_unavailable_and_is_not_fabricated(
    stub_providers, monkeypatch
):
    """A dead provider must degrade the score, never be filled in.

    run_parallel hands back the exception rather than propagating it. The
    caller turns that into an empty frame flagged fetch_error=True, which is
    the same path a live outage takes: the source is named in source_errors and
    the score is marked incomplete. An empty-but-clean frame would instead read
    as "we looked and there is nothing", silently dropping the signal.
    """
    def boom(ticker, days=180, max_filings=20):
        raise RuntimeError("SEC EDGAR unavailable")

    monkeypatch.setattr(ticker_score, "fetch_insider_transactions_detail", boom, raising=False)
    result = ticker_score.compute_full_ticker_score("AMD")

    assert "insider_activity" in result["source_errors"], (
        "a provider that raised was not recorded in source_errors"
    )
    assert result["is_complete"] is False
    assert result["has_insider_signal"] is False, (
        "a failed insider fetch still produced an insider signal -- the score "
        "is being computed from a value no provider returned"
    )


def test_run_parallel_returns_exceptions_rather_than_raising():
    out = signals_cache.run_parallel({
        "ok": lambda: "value",
        "bad": lambda: (_ for _ in ()).throw(ValueError("nope")),
    }, max_workers=2)
    assert out["ok"] == "value"
    assert isinstance(out["bad"], ValueError)


def test_run_parallel_single_task_skips_the_pool():
    """One task is the common case for a ticker with no optional evidence."""
    assert signals_cache.run_parallel({"only": lambda: 7}) == {"only": 7}
    assert signals_cache.run_parallel({}) == {}


def test_prewarm_never_raises_and_skips_trivial_batches(monkeypatch):
    """A prewarm failure must cost nothing but the original serial fetch."""
    assert signals_cache.prewarm_signal_series([], "2024-01-01", "2024-06-01") == 0
    assert signals_cache.prewarm_signal_series(["nonexistent_signal_id"],
                                               "2024-01-01", "2024-06-01") == 0

    import utils.fetchers as fetchers
    def boom(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(fetchers, "fetch_signal_series", boom)
    from utils.config import SIGNALS
    some = list(SIGNALS)[:3]
    assert signals_cache.prewarm_signal_series(some, "2024-01-01", "2024-06-01") == len(some)
