"""Finding a holding by name.

The front door asked for tickers. People know they own "the Vanguard total
bond fund" and "Apple"; a workplace-plan statement prints fund names with no
symbol at all. Every one of those visitors had to leave and look something up.

These tests pin the two things that decide whether the feature helps or misleads:
what gets filtered out of a provider's results, and what happens when the
lookup is down.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import symbol_search as sym  # noqa: E402


def _payload(*quotes) -> str:
    return json.dumps({"quotes": list(quotes)})


def _quote(symbol, name, quote_type="EQUITY", exchange="NMS"):
    return {"symbol": symbol, "longname": name, "quoteType": quote_type,
            "exchange": exchange, "exchDisp": "NASDAQ"}


def test_a_name_finds_the_ticker():
    rows = sym.parse_search_payload(_payload(_quote("AAPL", "Apple Inc.")))
    assert rows == [{"ticker": "AAPL", "name": "Apple Inc.", "kind": "Stock",
                     "exchange": "NASDAQ"}]


def test_mutual_funds_are_offered_because_the_engine_can_measure_them():
    """This is the bigger half of the feature.

    The page used to say "stocks or ETFs", which turned away anyone holding a
    401(k) or an adviser's model — the customer this product is for. Checked
    against the same provider the engine uses before the claim was made: VTSAX
    returns 750 daily NAV observations over three years, well past the 104
    weeks the engine requires.
    """
    rows = sym.parse_search_payload(_payload(
        _quote("VTSAX", "Vanguard Total Stock Market Index Admiral", "MUTUALFUND", "NAS")))
    assert [r["kind"] for r in rows] == ["Fund"]


def test_things_the_engine_cannot_measure_are_never_offered():
    """An index, a future or a currency pair has no holdable price series. It
    is better to show nothing than a row that fails after it is added."""
    rows = sym.parse_search_payload(_payload(
        _quote("^GSPC", "S&P 500 Index", "INDEX", "SNP"),
        _quote("BTC-USD", "Bitcoin USD", "CRYPTOCURRENCY", "CCC"),
        _quote("EURUSD=X", "EUR/USD", "CURRENCY", "CCY"),
        _quote("GC=F", "Gold Futures", "FUTURE", "CMX"),
        _quote("AAPL", "Apple Inc."),
    ))
    assert [r["ticker"] for r in rows] == ["AAPL"]


def test_foreign_listings_are_left_out_because_the_factors_are_american():
    """Rates, inflation, the dollar and credit here all mean US series. A
    London line would be measured against them silently, and the number would
    read as a finding rather than a mismatch."""
    rows = sym.parse_search_payload(_payload(
        _quote("SHEL.L", "Shell plc", "EQUITY", "LSE"),
        _quote("SHEL", "Shell plc ADR", "EQUITY", "NYQ"),
    ))
    assert [r["ticker"] for r in rows] == ["SHEL"]


def test_duplicates_and_junk_rows_are_dropped_not_guessed_at():
    rows = sym.parse_search_payload(_payload(
        _quote("AAPL", "Apple Inc."),
        _quote("AAPL", "Apple Inc. again"),
        _quote("", "No symbol"),
        {"symbol": "OK", "quoteType": "EQUITY", "exchange": "NMS"},  # no name
        "not a dict",
    ))
    assert [r["ticker"] for r in rows] == ["AAPL"]


def test_a_broken_provider_response_returns_nothing_rather_than_raising():
    for broken in ("", "not json", "null", "{}", '{"quotes": null}'):
        assert sym.parse_search_payload(broken) == []


# ── the fallback ────────────────────────────────────────────────────────────

def test_an_unreachable_lookup_falls_back_and_says_so():
    """A short list presented as the whole answer would teach people the
    product does not know their fund, when the lookup is simply down."""
    def down(_url):
        raise OSError("no network")

    rows, source = sym.search_symbols("total bond", fetcher=down)
    assert source == "offline"
    assert "BND" in [r["ticker"] for r in rows]


def test_a_live_answer_is_labelled_live():
    rows, source = sym.search_symbols(
        "apple", fetcher=lambda _u: _payload(_quote("AAPL", "Apple Inc.")))
    assert source == "live" and rows[0]["ticker"] == "AAPL"


def test_nothing_anywhere_is_reported_as_nothing():
    rows, source = sym.search_symbols(
        "qqqzzzxyz", fetcher=lambda _u: _payload())
    assert (rows, source) == ([], "none")


def test_a_one_letter_query_does_not_hit_the_provider():
    called = {"n": 0}

    def counting(_url):
        called["n"] += 1
        return _payload()

    assert sym.search_symbols("a", fetcher=counting) == ([], "none")
    assert called["n"] == 0, "every keystroke would be a request"


def test_the_offline_table_puts_an_exact_ticker_first():
    rows = sym.search_offline("vti")
    assert rows[0]["ticker"] == "VTI"


def test_the_offline_table_covers_the_holdings_the_product_ships_with():
    """The samples and the single-company shortcuts must be findable even when
    the lookup is down, or the front door contradicts itself."""
    from utils import exposure as ex
    from utils import report_ui as ui

    known = {t for t, _n, _k in sym.common_symbols()}
    shipped = {h["ticker"] for rows in ex.SAMPLE_PORTFOLIOS.values() for h in rows}
    shipped |= {t for t, _c in ui.SINGLE_STOCKS}
    missing = sorted(shipped - known)
    assert not missing, f"the product offers these but the offline table cannot find them: {missing}"


def test_every_bundled_row_is_well_formed():
    seen = set()
    for ticker, name, kind in sym.common_symbols():
        assert sym._TICKER.match(ticker), ticker
        assert ticker not in seen, f"{ticker} is listed twice"
        assert name and kind in ("Stock", "ETF", "Fund"), (ticker, name, kind)
        seen.add(ticker)


def test_a_long_fund_name_is_shortened_for_one_line():
    long_name = "Vanguard Something Extremely Long Index Fund Institutional Plus Shares Class"
    text = sym.label({"ticker": "VSOME", "name": long_name, "kind": "Fund"})
    assert text.startswith("VSOME · ") and "…" in text and len(text) < 80
