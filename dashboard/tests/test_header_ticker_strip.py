"""Regression coverage for the non-blocking global market strip."""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from utils.header import _fetch_ticker_strip, _fetch_ticker_strip_uncached


def test_header_ticker_strip_uses_one_small_batch_download(monkeypatch):
    """One batched request for all nine symbols, never nine separate ones.

    Targets the uncached producer directly. It used to be the @st.cache_data
    entry point and needed .clear() around it; the caching now lives in front
    of it (see _fetch_ticker_strip), so the download contract can be asserted
    without any cache bookkeeping.
    """
    calls: list[dict] = []
    symbols = ("SPY", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD")
    columns = pd.MultiIndex.from_product([symbols, ["Close"]])
    raw = pd.DataFrame(
        [
            [100.0 + index for index in range(len(symbols))],
            [101.0 + index for index in range(len(symbols))],
        ],
        columns=columns,
    )

    def fake_download(tickers, **kwargs):
        calls.append({"tickers": tuple(tickers), **kwargs})
        return raw

    monkeypatch.setattr(yf, "download", fake_download)
    result = _fetch_ticker_strip_uncached()

    assert len(calls) == 1
    assert calls[0]["tickers"] == symbols
    assert calls[0]["period"] == "5d"
    assert calls[0]["interval"] == "1d"
    assert calls[0]["group_by"] == "ticker"
    assert len(result) == len(symbols)
    assert result[0][0] == "SPY"
    assert result[0][2] == 101.0
    assert round(result[0][3], 2) == 1.0


def test_strip_is_served_through_the_shared_cache(monkeypatch):
    """The header must not call Yahoo directly.

    This is the perf fix itself: page.home.header was 72-77% of total render
    (max 2607ms) because the download sat on the critical path of every page.
    If someone reverts _fetch_ticker_strip to call the producer inline, the
    regression is invisible in local dev — Redis is empty there too — and only
    shows up as a slow tail in production. So pin the wiring.
    """
    seen = {}

    def fake_get_or_refresh(key, producer, **kwargs):
        seen["key"] = key
        seen["producer"] = producer
        seen["fresh_seconds"] = kwargs.get("fresh_seconds")
        return [("SPY", "S&P 500", 1.0, 2.0)]

    import utils.shared_cache as sc
    monkeypatch.setattr(sc, "get_or_refresh", fake_get_or_refresh)

    def explode(*a, **k):
        raise AssertionError("header called Yahoo on the request path")
    monkeypatch.setattr(yf, "download", explode)

    out = _fetch_ticker_strip()
    assert out == [("SPY", "S&P 500", 1.0, 2.0)]
    assert seen["key"] == "header_ticker_strip"
    assert seen["producer"] is _fetch_ticker_strip_uncached
    assert seen["fresh_seconds"] == 900
