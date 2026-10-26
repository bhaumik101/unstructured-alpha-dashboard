""""Moved N times as much as the U.S. stock market" is the plain beta.

market_beta is the market's coefficient in the joint fit with the five forces:
its effect with credit spreads, rates and the rest held fixed. Credit spreads
move with stocks, so they absorb much of the market's move and that coefficient
runs far below the usual beta -- live on 2026-10-26 the pages said ExxonMobil
"moved 0.01 times as much as the U.S. stock market" (median across 499 stocks:
0.60). The sentence and the tile now use market_beta_total, the slope on the
market alone; attribution keeps the joint coefficient, which is right there.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from utils import exposure as ex
from utils import exposure_pages as ep


def _frame(n=300, seed=7):
    rng = np.random.default_rng(seed)
    mkt = rng.normal(0, 2.0, n)
    credit = -0.08 * mkt + rng.normal(0, 0.05, n)      # spreads widen when stocks fall
    # A stock that moves mostly through credit: 0.2 x market directly, plus
    # -10 x the spread change, which itself carries 0.8 x the market.
    y = 0.2 * mkt - 10.0 * credit + rng.normal(0, 0.3, n)
    idx = pd.date_range("2023-01-06", periods=n, freq="W-FRI")
    return pd.DataFrame({"__y__": y, "__mkt__": mkt, "credit": credit}, index=idx)


def test_the_joint_coefficient_and_the_plain_beta_are_different_numbers():
    fit = ex._fit_on_frame(_frame(), "__y__", ex.FACTORS, min_obs=52)
    assert abs(fit["market_beta"] - 0.2) < 0.1              # the market with credit held fixed
    assert abs(fit["market_beta_total"] - 1.0) < 0.1        # what the stock actually did vs the market


def _rec(**kw):
    return {"as_of": "2026-10-16", "n_obs": 156, "window_weeks": 156,
            "exposures": {"oil": {"impact": 2.0, "low": 1.0, "high": 3.0, "evidence": "clear"}}, **kw}


def test_pages_say_the_plain_beta_and_never_the_joint_coefficient():
    rec = _rec(market_beta=0.01, market_beta_total=0.62)
    text = ep.summary_sentence("XOM", rec)
    html = ep.stock_header_html("XOM", rec, "ExxonMobil", None, None)
    assert "0.62×" in html and "0.01×" not in html
    assert "0.62 times as much as the U.S. stock market" in text and "0.01" not in text


def test_a_record_stored_before_the_plain_beta_existed_omits_the_figure():
    rec = _rec(market_beta=0.01)                            # no market_beta_total yet
    html = ep.stock_header_html("XOM", rec, "ExxonMobil", None, None)
    assert "With the market" not in html and "0.01" not in html
    assert "times as much as the U.S. stock market" not in ep.summary_sentence("XOM", rec)
