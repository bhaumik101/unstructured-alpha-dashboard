"""The exposure report is the product. Every claim it makes is tested here on
synthetic data where the true answer is known.

1. It recovers a real exposure, and its range contains the truth.
2. It does not manufacture findings from noise, even testing five factors.
3. It separates a factor from plain stock-market exposure.
4. Holding contributions add up to the portfolio number exactly.
5. Missing data is excluded and named, never filled in.
6. Its sentences describe the past; they never forecast or advise.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils import exposure as ex  # noqa: E402


FACTOR_SD = {"rates": 0.12, "inflation": 0.06, "dollar": 0.9, "oil": 4.0, "credit": 0.05}


def _weekly(rng, n=156, market_sd=2.2):
    idx = pd.date_range("2023-06-02", periods=n, freq="W-FRI")
    market = pd.Series(rng.normal(0.2, market_sd, n), idx)
    factors = {k: pd.Series(rng.normal(0, sd, n), idx) for k, sd in FACTOR_SD.items()}
    return idx, market, factors


# ── 1. recovers a real exposure ─────────────────────────────────────────────

def test_a_real_rate_exposure_is_recovered_and_its_range_contains_the_truth():
    rng = np.random.default_rng(7)
    idx, market, factors = _weekly(rng)
    y = 0.9 * market - 5.0 * factors["rates"] + pd.Series(rng.normal(0, 1.2, len(idx)), idx)

    fit = ex.fit_exposure(y, market, factors)
    rates = fit["readings"]["rates"]
    truth = -5.0 * 0.25
    assert rates["low"] <= truth <= rates["high"]
    assert rates["evidence"] == "clear"
    assert fit["n_obs"] == 156


# ── 2. does not manufacture findings ────────────────────────────────────────

def test_noise_is_rarely_called_clear_even_across_five_factors():
    """Bonferroni across five factors targets 1% per factor. Newey-West errors
    run slightly optimistic at n=156, so allow up to 2.5%."""
    rng = np.random.default_rng(11)
    clear = tests = 0
    for _ in range(300):
        idx, market, factors = _weekly(rng)
        y = market + pd.Series(rng.normal(0, 1.5, len(idx)), idx)
        for r in ex.fit_exposure(y, market, factors)["readings"].values():
            tests += 1
            clear += r["evidence"] == "clear"
    assert clear / tests <= 0.025, f"{clear}/{tests} null readings were labelled Clear"


def test_evidence_thresholds():
    assert ex.evidence_for(2.6, 156) == "clear"
    assert ex.evidence_for(-2.0, 156) == "tentative"
    assert ex.evidence_for(1.0, 156) == "indistinct"
    assert ex.evidence_for(9.0, 60) == "not_enough_data"
    assert ex.CLEAR_T == pytest.approx(2.5758, abs=1e-3), (
        "Clear must be corrected for testing five factors at once"
    )


# ── 3. separates a factor from the market ───────────────────────────────────

def test_a_stock_that_only_follows_the_market_is_not_called_rate_sensitive():
    """Rates co-move with stocks. Without the market in the regression, a pure
    market-tracking holding reads as strongly rate-sensitive."""
    rng = np.random.default_rng(3)
    idx, market, factors = _weekly(rng)
    factors["rates"] = 0.04 * market + pd.Series(rng.normal(0, 0.08, len(idx)), idx)
    y = 1.2 * market + pd.Series(rng.normal(0, 1.0, len(idx)), idx)

    fit = ex.fit_exposure(y, market, factors)
    assert fit["readings"]["rates"]["evidence"] != "clear"
    assert fit["market_beta"] == pytest.approx(1.2, abs=0.15)


def test_factors_that_move_together_are_flagged_as_hard_to_separate():
    rng = np.random.default_rng(5)
    idx, market, factors = _weekly(rng)
    factors["inflation"] = 0.9 * factors["rates"] + pd.Series(rng.normal(0, 0.02, len(idx)), idx)
    y = market + pd.Series(rng.normal(0, 1.0, len(idx)), idx)

    readings = ex.fit_exposure(y, market, factors)["readings"]
    assert readings["inflation"]["vif"] > ex.VIF_WARN
    assert readings["inflation"]["hard_to_separate_from"] == "Interest rates"


# ── end-to-end on synthetic daily data ──────────────────────────────────────

def _daily_world(seed=21, days=1000, short=None, fail=()):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end="2026-09-11", periods=days)
    n = len(idx)
    mkt_r = rng.normal(0.04, 1.0, n)
    ch = {"rates": rng.normal(0, 0.05, n), "inflation": rng.normal(0, 0.025, n),
          "dollar": rng.normal(0, 0.4, n), "oil": rng.normal(0, 1.8, n),
          "credit": rng.normal(0, 0.02, n)}

    def price(r):
        return pd.Series(100 * np.cumprod(1 + r / 100.0), idx)

    prices = {
        "SPY": price(mkt_r),
        "TLT": price(0.2 * mkt_r - 16 * ch["rates"] + rng.normal(0, 0.4, n)),
        "XOM": price(0.8 * mkt_r + 0.25 * ch["oil"] + rng.normal(0, 0.9, n)),
        "VTI": price(1.0 * mkt_r + rng.normal(0, 0.2, n)),
    }
    if short:
        prices[short] = prices[short].iloc[-300:]
    levels = {
        "DGS10": pd.Series(4 + np.cumsum(ch["rates"]), idx),
        "T10YIE": pd.Series(2.3 + np.cumsum(ch["inflation"]), idx),
        "DTWEXBGS": pd.Series(120 * np.cumprod(1 + ch["dollar"] / 100), idx),
        "DCOILWTICO": pd.Series(80 * np.cumprod(1 + ch["oil"] / 100), idx),
        "BAA10Y": pd.Series(1.8 + np.cumsum(ch["credit"]), idx),
        "INDPRO": pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.5, 40) / 100),
                            pd.date_range(end="2026-08-01", periods=40, freq="MS")),
    }

    def prices_fetcher(tickers, start, end):
        return {t: prices[t] for t in tickers if t in prices}

    def series_fetcher(series_id, start, end):
        if series_id in fail:
            raise ConnectionError("provider down")
        return levels[series_id]

    return prices_fetcher, series_fetcher


HOLDINGS = [{"ticker": "TLT", "weight_pct": 40}, {"ticker": "XOM", "weight_pct": 30},
            {"ticker": "VTI", "weight_pct": 30}]


def _report(**kw):
    pf, sf = _daily_world(**{k: v for k, v in kw.items() if k in ("short", "fail", "seed")})
    return ex.build_exposure_report(kw.get("holdings", HOLDINGS), pf, sf, end=date(2026, 9, 11))


def test_the_report_finds_the_exposures_that_were_built_in_and_names_their_source():
    report = _report()
    assert report["status"] == "ok"
    readings = report["portfolio"]["readings"]
    assert readings["rates"]["impact"] < 0 and readings["rates"]["evidence"] == "clear"
    assert readings["oil"]["impact"] > 0 and readings["oil"]["evidence"] == "clear"
    assert report["contributions"]["rates"][0]["ticker"] == "TLT"
    assert report["contributions"]["oil"][0]["ticker"] == "XOM"
    assert report["top_exposures"][:2] and set(report["top_exposures"][:2]) <= {"rates", "oil"}


# ── 4. contributions add up ─────────────────────────────────────────────────

def test_holding_contributions_sum_exactly_to_the_portfolio_exposure():
    report = _report()
    for key, reading in report["portfolio"]["readings"].items():
        total = sum(r["contribution"] for r in report["contributions"][key])
        assert total == pytest.approx(reading["impact"], abs=1e-8), key


# ── 5. missing data is excluded, never filled in ────────────────────────────

def test_a_holding_with_short_history_is_excluded_named_and_weights_rescaled():
    report = _report(short="XOM")
    assert [x["ticker"] for x in report["excluded"]] == ["XOM"]
    assert "weeks of price history" in report["excluded"][0]["reason"]
    assert report["excluded_weight_pct"] == pytest.approx(30.0)
    assert sum(p["weight_pct"] for p in report["positions"]) == pytest.approx(100.0)
    assert any("couldn't be measured" in n for n in report["notes"])


def test_a_failed_economic_series_is_left_out_not_estimated():
    report = _report(fail=("DCOILWTICO",))
    assert report["status"] == "ok"
    assert "Oil and energy" in report["unavailable_factors"]
    assert "oil" not in report["portfolio"]["readings"]
    assert "rates" in report["portfolio"]["readings"]
    assert any("Nothing was estimated" in n for n in report["notes"])


def test_missing_market_data_stops_the_report_instead_of_guessing():
    pf, sf = _daily_world()
    report = ex.build_exposure_report(HOLDINGS, lambda t, s, e: {k: v for k, v in pf(t, s, e).items()
                                                                 if k != "SPY"}, sf,
                                      end=date(2026, 9, 11))
    assert report["status"] == "error" and report.get("retryable")
    assert "Nothing has been estimated" in report["message"]


def test_empty_or_unknown_holdings_give_a_clear_error():
    assert _report(holdings=[])["status"] == "error"
    unknown = _report(holdings=[{"ticker": "ZZZZ", "weight_pct": 100}])
    assert unknown["status"] == "error"
    assert unknown["excluded"][0]["reason"] == "no price data was found for this symbol"


def test_positions_are_cleaned_without_silently_dropping_intent():
    positions, notes = ex.normalize_positions([
        {"ticker": "$aapl", "weight_pct": "50%"}, {"ticker": "AAPL", "weight_pct": 10},
        {"ticker": "MSFT", "weight_pct": -5}, {"ticker": "BND"},
    ])
    by = {p["ticker"]: p["weight_pct"] for p in positions}
    assert set(by) == {"AAPL", "BND"}
    assert sum(by.values()) == pytest.approx(100.0)
    assert any("short positions" in n for n in notes)
    assert any("Combined repeated" in n for n in notes)


def test_a_negative_oil_price_does_not_produce_infinite_changes():
    idx = pd.bdate_range("2020-04-13", periods=10)
    levels = pd.Series([20, 18, 10, 5, -37.6, 10, 12, 13, 15, 16], idx, dtype=float)
    changes = ex.to_changes(levels, "pct")
    assert np.isfinite(changes).all()


# ── what changed ────────────────────────────────────────────────────────────

def test_a_real_shift_in_sensitivity_is_flagged_and_a_stable_one_is_not():
    rng = np.random.default_rng(9)
    idx, market, factors = _weekly(rng)
    beta = np.where(np.arange(len(idx)) >= len(idx) - ex.RECENT_WEEKS, -14.0, -2.0)
    noise = pd.Series(rng.normal(0, 1.0, len(idx)), idx)
    frame = pd.concat({"__mkt__": market, **factors}, axis=1)
    frame["__portfolio__"] = market + beta * factors["rates"] + noise

    def shifts(f):
        recent = ex._fit_on_frame(f.iloc[-ex.RECENT_WEEKS:], "__portfolio__", ex.FACTORS, ex.MIN_RECENT_WEEKS)
        earlier = ex._fit_on_frame(f.iloc[:-ex.RECENT_WEEKS], "__portfolio__", ex.FACTORS, ex.MIN_RECENT_WEEKS)
        return {s["key"]: s for s in ex._shifts(recent, earlier)}

    assert shifts(frame)["rates"]["significant"]

    frame["__portfolio__"] = market - 2.0 * factors["rates"] + noise
    assert not shifts(frame)["rates"]["significant"]


# ── 6. language ─────────────────────────────────────────────────────────────

_BANNED = re.compile(r"\b(will|predict\w*|forecast\w*|expect(?!ations)\w*|should|buy|sell|"
                     r"recommend\w*|guarantee\w*|outperform\w*)\b", re.I)


def test_every_sentence_describes_the_past_and_never_advises():
    report = _report()
    sentences = [r["sentence"] for r in report["portfolio"]["readings"].values()]
    sentences += [s["sentence"] for s in report["shifts"]]
    sentences += [report["growth"].get("note", "")] + report["notes"]
    sentences += [f.why for f in ex.FACTORS] + [ex.GROWTH_FACTOR.why]
    sentences += list(ex.EVIDENCE_EXPLAINED.values())
    for text in sentences:
        assert not _BANNED.search(text), f"forward-looking or advisory language: {text!r}"


def test_growth_is_always_labelled_limited_evidence():
    growth = _report()["growth"]
    assert growth["limited"] is True
    assert "limited evidence" in growth["note"]
