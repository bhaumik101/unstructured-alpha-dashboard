"""How much of something you hold, in the units you actually hold it in.

The report asked for percentages. Almost nobody holds a portfolio in
percentages: a statement lists share counts, an adviser thinks in dollars, and
only the summary line is a percentage. Asking for percentages made someone do
the arithmetic before they could use the product, and arithmetic done in a
hurry is how a portfolio gets entered wrong.

The rule these tests are mostly about: A MISSING PRICE IS NOT A ZERO. A holding
quietly weighted at nothing is a portfolio the visitor did not describe, and
every number in the report would then be measuring something else with no sign
that it had happened.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import holdings as hold  # noqa: E402

CLOSES = {"VTI": 300.0, "BND": 72.0, "AAPL": 190.0}


def _fake_prices(tickers):
    index = pd.to_datetime(["2026-09-23", "2026-09-24", "2026-09-25"])
    out = {}
    for ticker in tickers:
        if ticker not in CLOSES:
            out[ticker] = pd.Series(dtype=float)     # a symbol with no history
        else:
            out[ticker] = pd.Series([1.0, 2.0, CLOSES[ticker]], index=index)
    return out


@pytest.fixture
def prices():
    return hold.latest_closes(["VTI", "BND", "AAPL", "ZZZZ"], fetcher=_fake_prices)


def test_a_price_comes_back_with_the_day_it_belongs_to(prices):
    """It is a daily close, not a live quote, and the page says which day."""
    assert prices["VTI"] == {"close": 300.0, "date": "2026-09-25"}
    assert "ZZZZ" not in prices, "a symbol with no history must be absent, not zero"


def test_a_pricing_outage_degrades_the_mode_it_does_not_raise():
    def broken(_tickers):
        raise OSError("provider down")

    assert hold.latest_closes(["VTI"], fetcher=broken) == {}


# ── the three ways of saying how much ───────────────────────────────────────

def test_share_counts_become_weights_through_the_last_close(prices):
    weights, problems = hold.to_weights(
        [{"ticker": "VTI", "shares": 100}, {"ticker": "BND", "shares": 250}],
        "shares", prices)
    assert problems == []
    assert [(w["ticker"], round(w["weight_pct"], 1)) for w in weights] == \
        [("VTI", 62.5), ("BND", 37.5)]


def test_dollar_values_become_weights_without_needing_a_price():
    weights, problems = hold.to_weights(
        [{"ticker": "VTI", "amount": 30000}, {"ticker": "BND", "amount": 10000}], "amount", {})
    assert problems == []
    assert [round(w["weight_pct"], 1) for w in weights] == [75.0, 25.0]


def test_percentages_still_work_and_do_not_have_to_add_to_100():
    weights, _ = hold.to_weights(
        [{"ticker": "VTI", "weight_pct": 3}, {"ticker": "BND", "weight_pct": 1}], "percent")
    assert [round(w["weight_pct"], 1) for w in weights] == [75.0, 25.0]


def test_an_unpriceable_holding_is_named_and_left_out_never_weighted_at_zero(prices):
    weights, problems = hold.to_weights(
        [{"ticker": "VTI", "shares": 10}, {"ticker": "ZZZZ", "shares": 5}], "shares", prices)
    assert [w["ticker"] for w in weights] == ["VTI"]
    assert problems and "ZZZZ" in problems[0] and "no recent price" in problems[0].lower()


def test_no_amount_entered_is_a_different_sentence_from_no_price(prices):
    """Switching a percentage portfolio into share counts leaves every row with
    no shares yet. Calling that "no recent price" sends someone looking for a
    data problem that is not there — which is what the first version did."""
    _weights, problems = hold.to_weights(
        [{"ticker": "VTI", "shares": 0}, {"ticker": "BND", "shares": 0}], "shares", prices)
    assert problems and "share count" in problems[0]
    assert "no recent price" not in problems[0].lower()


def test_nothing_measurable_says_so_rather_than_returning_a_silent_empty_list():
    weights, problems = hold.to_weights([], "percent")
    assert weights == [] and problems


def test_a_negative_or_nonsense_amount_is_not_a_holding(prices):
    weights, _ = hold.to_weights(
        [{"ticker": "VTI", "shares": -5}, {"ticker": "BND", "shares": "many"},
         {"ticker": "AAPL", "shares": 10}], "shares", prices)
    assert [w["ticker"] for w in weights] == ["AAPL"]


# ── the total ───────────────────────────────────────────────────────────────

def test_the_portfolio_total_is_only_claimed_when_it_is_known(prices):
    assert hold.portfolio_value(
        [{"ticker": "VTI", "shares": 100}], "shares", prices) == 30000.0
    assert hold.portfolio_value(
        [{"ticker": "VTI", "amount": 1234.5}], "amount", {}) == 1234.5
    assert hold.portfolio_value([{"ticker": "VTI", "weight_pct": 60}], "percent") is None, (
        "percentages describe proportions and say nothing about size"
    )


def test_money_and_share_counts_are_formatted_for_people():
    assert hold.fmt_money(30012.0) == "$30,012"
    assert hold.fmt_money(12.5) == "$12.50"
    assert hold.fmt_money(None) == "—"
    assert hold.fmt_shares(100.0) == "100"
    assert hold.fmt_shares(10.25) == "10.25"
    assert hold.fmt_shares(None) == "—"


# ── the panel ───────────────────────────────────────────────────────────────

def test_the_panel_never_re_measures_on_an_edit():
    """A report is 10-20 seconds of real work against two providers. Doing that
    per keystroke would be slower, not faster, and would hammer them."""
    source = (_ROOT / "utils" / "holdings_panel.py").read_text(encoding="utf-8")
    assert "def mark_stale" in source and "def clear_stale" in source
    page = (_ROOT / "pages" / "60_Exposure_Report.py").read_text(encoding="utf-8")
    assert "panel.is_stale()" in page and "Measure the new list" in page


def test_the_panel_calls_a_close_a_close():
    """Yahoo's daily close can be a day old. Calling it live would be the kind
    of small lie this product does not tell."""
    source = (_ROOT / "utils" / "report_ui.py").read_text(encoding="utf-8")
    block = source[source.index("def holding_value_html"):source.index("def holdings_total_html")]
    assert "close" in block and "live" not in block.lower()
    assert 'quote["date"]' in block, "the date the price belongs to has to be shown"
