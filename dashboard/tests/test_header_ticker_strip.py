"""Regression coverage for the non-blocking global market strip."""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from utils.header import _fetch_ticker_strip


def test_header_ticker_strip_uses_one_small_batch_download(monkeypatch):
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

    _fetch_ticker_strip.clear()
    monkeypatch.setattr(yf, "download", fake_download)
    result = _fetch_ticker_strip()
    _fetch_ticker_strip.clear()

    assert len(calls) == 1
    assert calls[0]["tickers"] == symbols
    assert calls[0]["period"] == "5d"
    assert calls[0]["interval"] == "1d"
    assert calls[0]["group_by"] == "ticker"
    assert len(result) == len(symbols)
    assert result[0][0] == "SPY"
    assert result[0][2] == 101.0
    assert round(result[0][3], 2) == 1.0
