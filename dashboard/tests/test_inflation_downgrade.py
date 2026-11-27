"""Inflation readings keep "Clear" only if they hold up on weeks they never saw."""

from __future__ import annotations

import inspect
import re

import numpy as np
import pandas as pd

from utils import explain as xp
from utils import exposure as ex
from utils import report_ui as ui

KEYS = [f.key for f in ex.FACTORS]


def _frame(n=156, b_infl=-6.0, b_rates=0.0, flip_infl=None, flip_rates=None, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-12-01", periods=n, freq="W-FRI")
    data = {"__mkt__": rng.normal(0.2, 2.0, n)}
    scale = {f.key: abs(f.shock) for f in ex.FACTORS}
    for k in KEYS:
        data[k] = rng.normal(0, scale[k], n)
    bi = np.full(n, b_infl)
    br = np.full(n, b_rates)
    if flip_infl is not None:
        bi[flip_infl:] = -b_infl
    if flip_rates is not None:
        br[flip_rates:] = -b_rates
    y = data["__mkt__"] + bi * data["inflation"] + br * data["rates"] + rng.normal(0, 0.3, n)
    frame = pd.DataFrame(data, index=idx)
    frame["__portfolio__"] = y
    return frame


def _fit(frame):
    fit = ex._fit_on_frame(frame, "__portfolio__", ex.FACTORS, ex.MIN_WEEKS)
    return ex._require_out_of_sample(fit, frame, "__portfolio__", ex.FACTORS)


def test_an_inflation_reading_that_holds_up_on_new_weeks_stays_clear():
    r = _fit(_frame())["readings"]["inflation"]
    assert r["evidence"] == "clear" and "downgraded" not in r
    assert r["oos"]["passed"] and r["oos"]["hits"] / r["oos"]["big_weeks"] >= ex.OOS_PASS


def test_an_inflation_reading_that_reversed_is_shown_as_tentative_with_the_reason():
    frame = _frame(b_infl=-9.0, flip_infl=110)
    raw = ex._fit_on_frame(frame, "__portfolio__", ex.FACTORS, ex.MIN_WEEKS)["readings"]["inflation"]
    assert raw["evidence"] == "clear"                      # the usual test alone would call it Clear
    r = _fit(frame)["readings"]["inflation"]
    assert r["evidence"] == "tentative" and r["evidence_label"] == ex.EVIDENCE_LABELS["tentative"]
    assert r["downgraded"]["from"] == "clear" and r["downgraded"]["reason"] == "failed"
    assert r["impact"] == raw["impact"] and r["low"] == raw["low"]      # numbers unchanged, only the label
    assert "did not hold up" in r["sentence"] and "The evidence is tentative." not in r["sentence"]


def test_other_forces_are_not_held_to_the_extra_test():
    r = _fit(_frame(b_infl=0.0, b_rates=-6.0, flip_rates=110))["readings"]["rates"]
    assert "downgraded" not in r and "oos" not in r


def test_too_little_data_to_check_means_tentative_until_it_can_be():
    frame = _frame(n=ex.MIN_WEEKS, b_infl=-9.0)     # enough to measure, too few to split and check
    r = _fit(frame)["readings"]["inflation"]
    assert r["evidence"] == "tentative" and r["downgraded"]["reason"] == "untested"


def test_the_engine_applies_it_to_the_portfolio_and_every_holding():
    src = inspect.getsource(ex.build_exposure_report)
    assert 'portfolio = _require_out_of_sample(_fit_on_frame(now, "__portfolio__"' in src
    assert "_require_out_of_sample(_fit_on_frame(now, t," in src
    assert ex.OOS_REQUIRED == ("inflation", "china", "natgas", "mortgage", "momentum", "bitcoin")
    assert ex.OOS_PASS == 0.7
    assert "if f.key in OOS_REQUIRED:" in inspect.getsource(ex.fit_extras)        # extras face it too


def test_the_table_marks_a_downgraded_reading(monkeypatch):
    frame = _frame(b_infl=-9.0, flip_infl=110)
    fit = _fit(frame)
    report = {"portfolio": {**fit, "readings": fit["readings"]}, "contributions": {}, "top_exposures": []}
    monkeypatch.setattr(ui, "_main_holding", lambda r, k: ("—", ""))
    monkeypatch.setattr(ui, "_top_name", lambda r, k: "")
    html = ui.exposure_table_html(report)
    assert html.count("was Clear") == 1 and "Downgraded after a stricter test" in html
    assert re.search(r"matched \d+ of \d+ big weeks", html)
    assert xp.downgrade_note({"evidence": "clear"}) == ""


def test_a_weak_extra_force_that_fails_new_weeks_is_shown_as_tentative():
    import numpy as np
    rng = np.random.default_rng(5)
    frame = _frame(b_infl=0.0)
    n = len(frame)
    mom = pd.Series(rng.normal(0, 1.0, n), frame.index)
    b = np.full(n, 1.5)
    b[130:] = -1.5          # reverses for the last 26 weeks: Clear over the window, a coin flip on new weeks
    frame["__portfolio__"] = frame["__portfolio__"] + b * mom.to_numpy()
    out = ex.fit_extras(frame, "__portfolio__", ex.FACTORS, {"momentum": mom})
    r = out["momentum"]
    assert r["evidence"] == "tentative" and r["downgraded"]["reason"] == "failed"
    assert "the overall stock market" not in r["sentence"] or ex.CORE_CONTROL in r["sentence"]
