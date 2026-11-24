"""The Cleveland Fed cross-check of the inflation reading (exposure.inflation_crosscheck).

  * Both measures are fitted the same way on the same months; the headline is
    compared by direction and evidence only (the two move on different scales).
  * Verdicts: confirmed / same_direction / unconfirmed / contradicted /
    no_headline / unchecked -- and a missing series is "not checked", never filled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from utils import exposure as ex


def _world(k_model: float, seed: int = 7, months: int = 72):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2020-11-02", periods=months * 21)
    me = pd.date_range(days[0], days[-1], freq="ME")
    model_m = pd.Series(np.cumsum(rng.normal(0, 0.08, len(me))), index=me) + 2.3
    be_m = model_m + pd.Series(rng.normal(0, 0.05, len(me)), index=me)    # the breakeven tracks it, with noise
    model = model_m.reindex(days, method="ffill").bfill()
    be = be_m.reindex(days, method="ffill").bfill()
    mkt = pd.Series(np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(days)))) * 100, index=days)
    # the holding's monthly return answers the model's monthly change (k per 1pp) plus noise
    noise = pd.Series(np.exp(np.cumsum(rng.normal(0, 0.004, len(days)))), index=days)
    hold = mkt * noise * np.exp(k_model * (model - model.iloc[0]))
    return {"AAA": hold}, {"AAA": 1.0}, mkt, be, model


def _headline(impact: float, evidence: str = "clear") -> dict:
    return {"impact": impact, "evidence": evidence}


def test_a_reading_that_holds_on_both_is_confirmed():
    daily, w, mkt, be, model = _world(k_model=-0.25)
    out = ex.inflation_crosscheck(daily, w, mkt, be, model, _headline(-0.4))
    assert out["available"] and out["n_obs"] >= ex.CROSS_MIN_MONTHS
    assert out["model"]["impact"] < 0 and out["model"]["evidence"] == "clear"
    assert out["verdict"] == "confirmed"
    assert out["n_obs"] <= ex.CROSS_WINDOW_MONTHS


def test_opposite_signs_are_called_a_contradiction():
    daily, w, mkt, be, model = _world(k_model=-0.25)
    assert ex.inflation_crosscheck(daily, w, mkt, be, model, _headline(+0.4))["verdict"] == "contradicted"


def test_no_link_on_the_model_leaves_the_headline_unconfirmed():
    daily, w, mkt, be, model = _world(k_model=0.0)
    out = ex.inflation_crosscheck(daily, w, mkt, be, model, _headline(-0.4))
    assert out["model"]["evidence"] not in ("clear", "tentative")
    assert out["verdict"] in ("same_direction", "unconfirmed")


def test_a_headline_that_did_not_hold_up_is_not_confirmed_by_anything():
    daily, w, mkt, be, model = _world(k_model=-0.25)
    assert ex.inflation_crosscheck(daily, w, mkt, be, model, _headline(-0.1, "indistinct"))["verdict"] == "no_headline"


def test_a_missing_series_is_not_checked_never_filled():
    daily, w, mkt, be, model = _world(k_model=-0.25)
    out = ex.inflation_crosscheck(daily, w, mkt, be, None, _headline(-0.4))
    assert out == {"available": False, "reason": "the Cleveland Fed series was unavailable"}
    short = ex.inflation_crosscheck(daily, w, mkt, be.iloc[-400:], model.iloc[-400:], _headline(-0.4))
    assert not short["available"] and "months line up" in short["reason"]


def test_the_report_carries_it():
    import inspect
    src = inspect.getsource(ex.build_exposure_report)
    assert '"inflation_check": inflation_check' in src
    assert "series_fetcher(INFLATION_MODEL.series_id, s, e)" in src
    assert ex.INFLATION_MODEL.series_id == "EXPINF10YR"


def _rep(check: dict, head: dict) -> dict:
    return {"inflation_check": check, "portfolio": {"readings": {"inflation": head}}}


def test_the_panel_shares_one_axis_and_says_when_the_time_scale_matters():
    import re
    from utils import report_ui as ui
    head = {"impact": 0.28, "t": 2.2, "evidence": "tentative"}
    check = {"available": True, "verdict": "same_direction", "n_obs": 60, "start": "2021-12-31",
             "end": "2026-11-30", "clear_t": 2.8,
             "breakeven": {"impact": -0.5, "t": -9.0, "evidence": "clear"},   # strong: a per-row scale would move its tick
             "model": {"impact": 0.02, "t": 0.3, "evidence": "indistinct"}}
    html = ui.inflation_check_html(_rep(check, head))
    ticks = set(re.findall(r'class="uxc-tick" style="left:([0-9.]+)%', html))
    assert len(ticks) == 1, "every row's Clear tick sits at the same place"
    assert "Same direction, weaker on the model" in html
    assert "depends on the time scale" in html                     # monthly breakeven disagrees with weekly
    check["breakeven"]["impact"] = 0.5
    assert "depends on the time scale" not in ui.inflation_check_html(_rep(check, head))
    assert ui.inflation_check_html(_rep({"available": False}, head)) == ""
    assert ui.inflation_check_html(_rep(dict(check, verdict="unchecked"), head)) == ""
    from tests.test_exposure import _BANNED
    text = re.sub(r"<[^>]+>", " ", html).replace("it is not a forecast", "")   # the standard disclaimer
    assert not _BANNED.search(text)
