"""Convergence rendering must not repeat provider and database side effects."""

from __future__ import annotations

import sys
from types import SimpleNamespace


def test_convergence_prediction_enrichment_runs_once_per_event(monkeypatch):
    from utils import convergence

    ticker_calls: list[str] = []
    logged: list[dict] = []

    class FakeTicker:
        def __init__(self, ticker: str):
            ticker_calls.append(ticker)

        @property
        def info(self) -> dict:
            return {"currentPrice": 123.45}

    monkeypatch.setitem(
        sys.modules,
        "yfinance",
        SimpleNamespace(Ticker=FakeTicker),
    )
    monkeypatch.setitem(
        sys.modules,
        "utils.prediction_log",
        SimpleNamespace(log_prediction=lambda **kwargs: logged.append(kwargs)),
    )

    convergence._log_convergence_prediction_once.clear()
    try:
        args = {
            "ticker": "AAPL",
            "direction": "bull",
            "score": 72.0,
            "signal_count": 4,
            "signals_triggered": ("yield_curve", "credit_spread"),
        }
        assert convergence._log_convergence_prediction_once(**args) is True
        assert convergence._log_convergence_prediction_once(**args) is True
    finally:
        convergence._log_convergence_prediction_once.clear()

    assert ticker_calls == ["AAPL"]
    assert len(logged) == 1
    assert logged[0]["price"] == 123.45
    assert logged[0]["signals_triggered"] == ["yield_curve", "credit_spread"]


def test_failed_prediction_write_is_not_cached(monkeypatch):
    from utils import convergence

    attempts: list[str] = []

    monkeypatch.setitem(
        sys.modules,
        "yfinance",
        SimpleNamespace(
            Ticker=lambda ticker: SimpleNamespace(info={"currentPrice": 10.0})
        ),
    )

    def fail_write(**kwargs) -> None:
        attempts.append(kwargs["ticker"])
        raise RuntimeError("database unavailable")

    monkeypatch.setitem(
        sys.modules,
        "utils.prediction_log",
        SimpleNamespace(log_prediction=fail_write),
    )

    convergence._log_convergence_prediction_once.clear()
    try:
        args = {
            "ticker": "MSFT",
            "direction": "bear",
            "score": 31.0,
            "signal_count": 3,
            "signals_triggered": ("vix",),
        }
        for _ in range(2):
            try:
                convergence._log_convergence_prediction_once(**args)
            except RuntimeError:
                pass
    finally:
        convergence._log_convergence_prediction_once.clear()

    assert attempts == ["MSFT", "MSFT"]
