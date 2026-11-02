"""Widely held ETFs are measured weekly beside the S&P 500.

What must hold: the list is real tickers with names and a category; no fund
that simply tracks the S&P 500 is on it (every reading is beyond the market,
and the market control is SPY, so there is nothing to measure); the weekly job
targets the funds; fund pages say InvestmentFund, not Corporation; the stocks
hub can filter to ETFs.
"""

from __future__ import annotations

import re

from tests.test_explore_page import _stock
from utils import exposure as ex
from utils import exposure_pages as ep
from utils import funds as fd


def test_the_list_is_clean_and_has_no_market_tracker():
    f = fd.funds()
    assert len(f) >= 40
    for t, (name, cat) in f.items():
        assert re.fullmatch(r"[A-Z]{2,5}", t) and name and cat, t
    assert not (set(f) & fd.MARKET_TRACKERS) and ex.MARKET_TICKER not in f
    assert {"TLT", "QQQ", "SCHD", "XLE", "GLD"} <= set(f)


def test_the_weekly_job_targets_the_funds(monkeypatch):
    import cron.measure_library as ml
    src = open(ml.__file__, encoding="utf-8").read()
    assert "load_constituents() + load_funds()" in src
    targets = ml.plan_targets(ml.load_constituents() + fd.load_funds(), [], ml.datetime(2026, 11, 3,
                              tzinfo=ml.timezone.utc), fresh_days=5)
    assert {"TLT", "SCHD"} <= {t for t, _ in targets}


def test_a_fund_page_is_described_as_a_fund():
    rec = {"as_of": "2026-10-16", "n_obs": 156, "name": "iShares 20+ Year Treasury Bond ETF",
           "exposures": {"rates": {"impact": -3.9, "low": -4.3, "high": -3.5, "evidence": "clear"}}}
    html = ep.stock_page_html("TLT", rec, [], [], "https://www.x", "https://app.x")
    assert '"@type":"InvestmentFund"' in html and '"@type":"Corporation"' not in html


def test_the_hub_filters_to_etfs():
    html = ep.hub_page_html([_stock("TLT", "iShares 20+ Year Treasury", rates=(-3.9, "clear")),
                             _stock("XOM", "Exxon", oil=(2.0, "clear"))], "https://www.x", "https://app.x")
    assert '<option value="etf">ETFs</option>' in html and 'data-s="etf"' in html
