"""More forces: a second layer measured beyond the market and the core five.

Each extra force is fitted on its own -- returns ~ market + core five + that
force -- on the same weeks as the core model. What must hold:

  * an exposure built into the data is found, and one that isn't, isn't;
  * the core readings are exactly what they were without the extras;
  * an extra is measured BEYOND the core: a stock that only moves with the
    10-year yield shows no separate short-rate exposure;
  * the bar is stricter than the core's and tightens as forces are added;
  * a failed series is named and left out, never filled in;
  * the readings are stored in the stock library and shown on every surface.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import exposure as ex  # noqa: E402

END = date(2026, 9, 11)


def _world(seed=7, days=1000, fail=()):
    """Daily world with known exposures.

    FRONT is the 2-year yield moving on its own (the 10-year held fixed).
    BANK moves with FRONT. LONGONLY moves with the 10-year only. PLAIN moves
    with the market only.
    """
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end="2026-09-11", periods=days)
    n = len(idx)
    mkt = rng.normal(0.04, 1.0, n)
    ch = {"rates": rng.normal(0, 0.05, n), "inflation": rng.normal(0, 0.025, n),
          "dollar": rng.normal(0, 0.4, n), "oil": rng.normal(0, 1.8, n),
          "credit": rng.normal(0, 0.02, n)}
    front = rng.normal(0, 0.03, n)                    # 2-year beyond the 10-year
    vix = rng.normal(0, 1.2, n)
    mort = rng.normal(0, 0.02, n)
    # Gold moves with the dollar (a core force) AND on its own.
    gold_own = rng.normal(0, 0.8, n)
    gold = -0.6 * ch["dollar"] + gold_own
    copper = 0.3 * ch["oil"] + rng.normal(0, 1.2, n)
    gas = 0.4 * ch["oil"] + rng.normal(0, 3.0, n)
    btc = rng.normal(0, 3.5, n)
    # Style spreads: each fund pair's daily gap. Value leans on rates (a core force).
    size_gap = rng.normal(0, 0.5, n)
    value_gap = -3 * ch["rates"] + rng.normal(0, 0.45, n)
    mom_gap = rng.normal(0, 0.5, n)

    def price(r):
        return pd.Series(100 * np.cumprod(1 + r / 100.0), idx)

    prices = {
        "SPY": price(mkt),
        "BANK": price(0.9 * mkt + 30 * front + rng.normal(0, 0.8, n)),
        "LONGONLY": price(0.5 * mkt - 16 * ch["rates"] + rng.normal(0, 0.5, n)),
        "PLAIN": price(1.0 * mkt + rng.normal(0, 0.6, n)),
        # MINER moves with gold's own part, not with the dollar.
        "MINER": price(0.7 * mkt + 1.2 * gold_own + rng.normal(0, 0.8, n)),
        "GLD": price(gold),
        "CPER": price(copper),
        # SMALLCAP moves with small companies beating large ones.
        "SMALLCAP": price(1.0 * mkt + 1.5 * size_gap + rng.normal(0, 0.7, n)),
        "IWB": price(mkt + rng.normal(0, 0.05, n)),
        "IWF": price(mkt + rng.normal(0, 0.05, n)),
    }
    prices["IWM"] = price(np.diff(np.log(prices["IWB"].to_numpy()), prepend=np.log(100)) * 100
                          + size_gap)
    prices["IWD"] = price(np.diff(np.log(prices["IWF"].to_numpy()), prepend=np.log(100)) * 100
                          + value_gap)
    prices["MTUM"] = price(mkt + mom_gap)
    levels = {
        "DGS10": pd.Series(4 + np.cumsum(ch["rates"]), idx),
        "T10YIE": pd.Series(2.3 + np.cumsum(ch["inflation"]), idx),
        "DTWEXBGS": pd.Series(120 * np.cumprod(1 + ch["dollar"] / 100), idx),
        "DCOILWTICO": pd.Series(80 * np.cumprod(1 + ch["oil"] / 100), idx),
        "BAA10Y": pd.Series(1.8 + np.cumsum(ch["credit"]), idx),
        "INDPRO": pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.5, 40) / 100),
                            pd.date_range(end="2026-08-01", periods=40, freq="MS")),
        # The 2-year moves with the 10-year AND on its own.
        "DGS2": pd.Series(3.8 + np.cumsum(ch["rates"] + front), idx),
        "VIXCLS": pd.Series(18 + np.cumsum(vix), idx),
        # Weekly, Thursdays: the engine's Friday resample must still line it up.
        "MORTGAGE30US": pd.Series(6.5 + np.cumsum(ch["rates"] + mort), idx)[idx.dayofweek == 3],
        "DHHNGSP": pd.Series(3 * np.cumprod(1 + gas / 100), idx),
        "CBBTCUSD": pd.Series(60000 * np.cumprod(1 + btc / 100), idx),
    }

    def prices_fetcher(tickers, start, end):
        return {t: prices[t] for t in tickers if t in prices and t not in fail}

    def series_fetcher(series_id, start, end):
        if series_id in fail:
            raise ConnectionError("provider down")
        return levels[series_id]

    return prices_fetcher, series_fetcher


_ALL_EXTRAS = (tuple(f.series_id for f in ex.EXTRA_FACTORS if f.source == "fred")
               + tuple(t for t in ex.EXTRA_PRICE_TICKERS if t != ex.MARKET_TICKER))


def _one(ticker, **kw):
    pf, sf = _world(**kw)
    return ex.build_exposure_report([{"ticker": ticker, "weight_pct": 100}], pf, sf, end=END)


@pytest.fixture(scope="module")
def bank():
    r = _one("BANK")
    assert r["status"] == "ok"
    return r


# ── the statistics ──────────────────────────────────────────────────────────

def test_a_built_in_short_rate_exposure_is_found(bank):
    r = bank["extras"]["readings"]["short_rates"]
    assert r["evidence"] == "clear" and r["impact"] > 0
    assert r["group"] == "markets"
    # 30 per point of FRONT, expressed per 0.25 pp: +7.5%. Within 3 standard
    # errors, not the 90% range, which misses the truth 1 time in 10 by design.
    assert abs(r["impact"] - 7.5) < 3 * r["se_impact"]


def test_no_exposure_is_invented_where_none_was_built():
    extras = _one("PLAIN")["extras"]["readings"]
    assert set(extras) == {f.key for f in ex.EXTRA_FACTORS}
    for key, r in extras.items():
        assert r["evidence"] != "clear", f"{key} was called Clear on a stock with no exposure"


def test_an_extra_is_measured_beyond_the_core_not_instead_of_it():
    """LONGONLY moves with the 10-year yield only. The 2-year moves with the
    10-year too, so a model without the core would credit short rates; beyond
    the core there is nothing left."""
    rep = _one("LONGONLY")
    assert rep["portfolio"]["readings"]["rates"]["evidence"] == "clear"
    assert rep["extras"]["readings"]["short_rates"]["evidence"] != "clear"
    assert rep["extras"]["readings"]["mortgage"]["evidence"] != "clear"


def test_the_core_readings_are_untouched_by_the_extras():
    with_extras = _one("BANK")
    without = _one("BANK", fail=_ALL_EXTRAS)
    for key, r in with_extras["portfolio"]["readings"].items():
        assert r == without["portfolio"]["readings"][key], key


def test_the_bar_is_stricter_than_the_core_and_counts_every_force():
    from scipy.stats import norm

    n = len(ex.FACTORS) + len(ex.EXTRA_FACTORS)
    assert ex.EXTRA_CLEAR_T == pytest.approx(norm.ppf(1 - 0.05 / (2 * n)), abs=1e-9)
    assert ex.EXTRA_CLEAR_T > ex.CLEAR_T
    assert ex._bonferroni_t(5) == pytest.approx(ex.CLEAR_T, abs=1e-9)


def test_the_extra_reading_says_what_it_was_measured_beyond(bank):
    assert "the five core forces" in bank["extras"]["readings"]["short_rates"]["sentence"]
    assert "five core forces" not in bank["portfolio"]["readings"]["rates"]["sentence"]


def test_a_failed_series_is_named_and_left_out_never_filled_in():
    rep = _one("BANK", fail=("VIXCLS",))
    assert "volatility" not in rep["extras"]["readings"]
    assert rep["extras"]["unavailable"] == ["Market volatility"]
    assert "short_rates" in rep["extras"]["readings"]


def test_weekly_thursday_series_line_up_with_friday_weeks(bank):
    assert bank["extras"]["readings"]["mortgage"]["n_obs"] >= ex.MIN_WEEKS


def test_every_extra_says_why_it_matters_and_belongs_to_a_listed_group():
    keys = [f.key for f in ex.FACTORS + ex.EXTRA_FACTORS]
    assert len(keys) == len(set(keys)), "an extra reuses a core key"
    for f in ex.EXTRA_FACTORS:
        assert f.group in ex.EXTRA_GROUPS
        assert f.why and f.shock_phrase and len(f.key) <= 24   # stock_exposures.factor width


# ── storage ─────────────────────────────────────────────────────────────────

@pytest.fixture
def store(monkeypatch, tmp_path):
    from utils import db

    engine = create_engine(f"sqlite:///{tmp_path / 'x.db'}")
    db.metadata.create_all(engine, tables=[db.stock_measurements, db.stock_exposures])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    return engine


def test_the_library_stores_the_extras_beside_the_core(store, bank):
    from utils import stock_library as lib

    assert lib.record(bank, "Bank Co")
    stored = lib.history("BANK")[0]["exposures"]
    assert set(stored) == {f.key for f in ex.FACTORS + ex.EXTRA_FACTORS}
    assert stored["short_rates"]["evidence"] == "clear"


# ── display ─────────────────────────────────────────────────────────────────

def test_the_report_card_groups_the_extras_and_states_the_stricter_bar(bank):
    from utils import report_ui as ui

    html = ui.extras_html(bank)
    assert "More forces, beyond the core five" in html
    assert '<div class="uar-group" role="heading" aria-level="3">Markets and rates</div>' in html
    assert "Short-term rates" in html and f"|t| ≥ {ex.EXTRA_CLEAR_T:.2f}" in html
    assert "it is not a forecast" in html


def test_a_report_cached_before_extras_existed_shows_nothing(bank):
    from utils import report_ui as ui

    old = {k: v for k, v in bank.items() if k != "extras"}
    assert ui.extras_html(old) == ""


def test_all_extras_failing_says_so_plainly():
    from utils import report_ui as ui

    rep = _one("BANK", fail=_ALL_EXTRAS)
    html = ui.extras_html(rep)
    assert "couldn&#39;t be measured" in html and "Nothing was estimated" in html


def test_the_public_page_shows_stored_extras(store, bank):
    from utils import exposure_pages as ep
    from utils import stock_library as lib

    lib.record(bank, "Bank Co")
    h = lib.history("BANK")
    html = ep.stock_page_html("BANK", h[0], h, [], "https://www.x", "https://app.x")
    assert "More forces, beyond the core five" in html and "Short-term rates" in html


@pytest.mark.slow
def test_on_stocks_with_no_exposure_about_one_in_a_hundred_extras_is_called_clear():
    """The methodology page states this rate; this is where it comes from."""
    # 150 stocks x every extra force: with ten forces that is 1,500 readings,
    # plenty for a <=2% bound, and it keeps CI's serial run from growing with
    # every group added.
    clear = total = 0
    for seed in range(150):
        pf, sf = _world(seed=1000 + seed)
        r = ex.build_exposure_report([{"ticker": "PLAIN", "weight_pct": 100}], pf, sf, end=END)
        for v in r["extras"]["readings"].values():
            total += 1
            clear += v["evidence"] == "clear"
    # The page says "about 1 in 100"; measured 26 of 3,000 (0.87%) over 300
    # stocks with ten extra forces. 1.5% is where "about 1 in 100" stops being true.
    assert clear / total <= 0.015, f"{clear}/{total} extra readings falsely Clear"


def test_the_methodology_page_documents_every_extra_force():
    src = (_ROOT / "pages" / "63_Methodology.py").read_text(encoding="utf-8")
    assert "## More forces" in src and "ex.EXTRA_FACTORS" in src and "ex.EXTRA_CLEAR_T" in src
    # The false-Clear figure is a measurement, not computed at render time:
    # adding a force means re-running the slow simulation and updating it.
    assert f"measured with {len(ex.EXTRA_FACTORS)} extra forces" in src, (
        "the methodology's false-Clear figure was measured with a different set of forces")


# ── group 2: commodities and crypto ─────────────────────────────────────────

def test_gold_is_found_beyond_the_dollar():
    """MINER moves with gold's own part. Gold also moves with the dollar, a
    core force, so this is the reading 'beyond the core' in practice."""
    r = _one("MINER")["extras"]["readings"]["gold"]
    assert r["evidence"] == "clear" and r["impact"] > 0 and r["group"] == "commodities"


def test_price_sourced_forces_come_from_the_price_batch_not_fred():
    asked = []
    pf, sf = _world()

    def prices(tickers, start, end):
        asked.append(tuple(tickers))
        return pf(tickers, start, end)

    def series(sid, start, end):
        assert sid not in ex.EXTRA_PRICE_TICKERS, f"{sid} was asked of FRED"
        return sf(sid, start, end)

    ex.build_exposure_report([{"ticker": "MINER", "weight_pct": 100}], prices, series, end=END)
    assert len(asked) == 1, "one price fetch for holdings, market and price-sourced forces"
    assert {"GLD", "CPER", "MINER", "SPY"} <= set(asked[0])


def test_a_missing_fund_price_is_named_not_filled():
    rep = _one("MINER", fail=("GLD",))
    assert "gold" not in rep["extras"]["readings"] and "Gold" in rep["extras"]["unavailable"]
    assert "copper" in rep["extras"]["readings"]


def test_the_methodology_page_names_the_right_source_for_each_force():
    src = (_ROOT / "pages" / "63_Methodology.py").read_text(encoding="utf-8")
    assert 'f.source == "fred"' in src and "Yahoo Finance" in src


# ── group 3: investing styles ───────────────────────────────────────────────

def test_a_small_company_tilt_is_found():
    r = _one("SMALLCAP")["extras"]["readings"]["size"]
    assert r["evidence"] == "clear" and r["impact"] > 0 and r["group"] == "styles"


def test_a_style_is_the_gap_between_two_funds_weekly_returns():
    f = next(f for f in ex.EXTRA_FACTORS if f.key == "size")
    assert f.source == "spread" and ex._spread_legs(f) == ("IWM", "IWB")
    assert {"IWM", "IWB", "IWD", "IWF", "MTUM"} <= set(ex.EXTRA_PRICE_TICKERS)


def test_a_style_missing_one_leg_is_named_not_half_measured():
    rep = _one("SMALLCAP", fail=("IWB",))
    assert "size" not in rep["extras"]["readings"]
    assert "Small vs large companies" in rep["extras"]["unavailable"]
