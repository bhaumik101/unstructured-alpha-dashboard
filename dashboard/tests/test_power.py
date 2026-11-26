"""Holm's step-down and the five-year confirmation (docs/RESEARCH_2026-11.md §7)."""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd

from utils import explain as xp
from utils import exposure as ex
from utils import report_ui as ui

ROOT = Path(__file__).resolve().parent.parent


def test_the_first_holm_bar_is_todays_clear_bar_and_the_rest_step_down():
    bars = ex.holm_bars()
    assert len(bars) == 5 and abs(bars[0] - ex.CLEAR_T) < 1e-9
    assert all(a > b for a, b in zip(bars, bars[1:])) and abs(bars[-1] - 1.959964) < 1e-4


def _readings(ts):
    keys = [f.key for f in ex.FACTORS][:len(ts)]
    return {k: {"t": t, "impact": 0.1 * np.sign(t), "low": 0.0, "high": 0.2,
                "evidence": ex.evidence_for(t, 156), "evidence_label": "", "sentence": ""}
            for k, t in zip(keys, ts)}, {f.key: f for f in ex.FACTORS}


def test_a_second_reading_is_promoted_only_while_each_step_passes():
    r, by = _readings([3.0, 2.55, 2.30, -2.2, 0.4])
    ex._holm_step_down(r, by, 156, ex.MIN_WEEKS, "this portfolio", "weeks", "the market")
    ev = [v["evidence"] for v in r.values()]
    assert ev == ["clear", "clear", "tentative", "tentative", "indistinct"]   # 2.30 < 2.394 stops the walk
    assert r["inflation"].get("holm") and "holm" not in r["rates"]
    assert "The evidence is tentative" not in r["inflation"]["sentence"]


def test_nothing_is_promoted_when_the_strongest_misses_todays_bar():
    r, by = _readings([2.5, 2.49, 2.4, 2.3, 2.2])
    ex._holm_step_down(r, by, 156, ex.MIN_WEEKS, "this portfolio", "weeks", "the market")
    assert all(v["evidence"] == "tentative" for v in r.values())


def test_the_step_down_never_takes_a_clear_away():
    r, by = _readings([4.0, 3.9, 3.8, 3.7, 3.6])
    ex._holm_step_down(r, by, 156, ex.MIN_WEEKS, "this portfolio", "weeks", "the market")
    assert all(v["evidence"] == "clear" for v in r.values())


def _long(n=520, flip_at=None, seed=11, before=4.0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2016-12-02", periods=n, freq="W-FRI")
    mkt = pd.Series(rng.normal(0.2, 2.0, n), idx)
    ch = {f.key: pd.Series(rng.normal(0, abs(f.shock), n), idx) for f in ex.FACTORS}
    b = np.full(n, -4.0)
    if flip_at is not None:
        b[:flip_at] = before                               # the opposite exposure before the last years
    y = pd.Series(mkt.to_numpy() + b * ch["rates"].to_numpy() + rng.normal(0, 0.3, n), idx)
    return {"FUND": y}, mkt, ch


def _fit3(weekly, mkt, ch):
    frame = pd.concat({"FUND": weekly["FUND"], "__mkt__": mkt, **ch}, axis=1).dropna().iloc[-156:]
    frame["__portfolio__"] = frame["FUND"]
    return ex._fit_on_frame(frame, "__portfolio__", ex.FACTORS, ex.MIN_WEEKS, holm=True)


def test_a_reading_that_lasts_five_years_is_confirmed():
    weekly, mkt, ch = _long()
    fit = _fit3(weekly, mkt, ch)
    assert fit["readings"]["rates"]["evidence"] == "clear"
    ex._confirm_long_window(fit, {"FUND": 1.0}, weekly, mkt, ch, ex.FACTORS)
    assert fit["readings"]["rates"]["confirmed_5y"] is True and fit["readings"]["rates"]["confirm_weeks"] == 260


def test_a_reading_that_was_the_other_way_before_is_not_confirmed():
    # Only the last 156 weeks carry today's sign; the 104 before them, strongly the
    # other way, so five years reads Clear in the OPPOSITE direction.
    weekly, mkt, ch = _long(flip_at=520 - 156, before=30.0)
    fit = _fit3(weekly, mkt, ch)
    assert fit["readings"]["rates"]["evidence"] == "clear"
    ex._confirm_long_window(fit, {"FUND": 1.0}, weekly, mkt, ch, ex.FACTORS)
    assert fit["readings"]["rates"]["confirmed_5y"] is False
    frame5 = pd.concat({"FUND": weekly["FUND"], "__mkt__": mkt, **ch}, axis=1).dropna().iloc[-260:]
    frame5["__portfolio__"] = frame5["FUND"]
    five = ex._fit_on_frame(frame5, "__portfolio__", ex.FACTORS, 234)["readings"]["rates"]
    assert five["evidence"] == "clear" and five["impact"] > 0 > fit["readings"]["rates"]["impact"]


def test_too_short_a_history_shows_no_confirmation_either_way():
    weekly, mkt, ch = _long(n=200)
    fit = _fit3(weekly, mkt, ch)
    ex._confirm_long_window(fit, {"FUND": 1.0}, weekly, mkt, ch, ex.FACTORS)
    assert "confirmed_5y" not in fit["readings"]["rates"]


def test_the_engine_uses_both_on_every_report():
    src = inspect.getsource(ex.build_exposure_report)
    assert src.count("holm=True") == 2                      # the portfolio and each holding
    assert "_confirm_long_window(portfolio, weights, weekly_full, market_full, changes_full, active)" in src


def test_the_report_shows_the_badge_and_the_track_record(monkeypatch):
    weekly, mkt, ch = _long()
    fit = _fit3(weekly, mkt, ch)
    ex._confirm_long_window(fit, {"FUND": 1.0}, weekly, mkt, ch, ex.FACTORS)
    report = {"portfolio": {**fit, "market_beta_total": 1.0}, "contributions": {}, "top_exposures": ["rates"]}
    monkeypatch.setattr(ui, "_main_holding", lambda r, k: ("—", ""))
    monkeypatch.setattr(ui, "_top_name", lambda r, k: "")
    table = ui.exposure_table_html(report)
    assert table.count("5-yr confirmed") == 1 and "75%" in table
    assert "It is also Clear on five years of data." in ui.plain_english_html(report, {})
    assert xp.confirmed_note({"evidence": "clear"}) == ""
    assert "74%" in xp.TRACK_RECORD and "55%" in xp.TRACK_RECORD


def test_the_methodology_page_explains_both():
    src = (ROOT / "pages" / "63_Methodology.py").read_text(encoding="utf-8")
    assert "Holm's step-down" in src and "5-yr confirmed" in src and "75%" in src
