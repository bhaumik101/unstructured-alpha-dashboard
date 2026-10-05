"""Scenario lab: what a portfolio's past suggests for a set of moves.

What must hold:
  * an exposure built into the data is recovered for the move that matches it;
  * holdings' contributions add up to the portfolio figure;
  * the range uses the full covariance: correlated estimates are not treated
    as independent;
  * series quoted the other way round (the yen) are signed correctly;
  * moves beyond any week in the data are flagged as extrapolation;
  * a report measured before scenarios existed says so instead of guessing;
  * the page renders the result, and nothing reads as a forecast.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_extra_forces import END, _world  # noqa: E402
from utils import exposure as ex  # noqa: E402
from utils import scenario as sc  # noqa: E402
from utils import report_ui as ui  # noqa: E402
from utils import scenario_ui as sui  # noqa: E402


def _report(*holdings, seed=7):
    pf, sf = _world(seed=seed)
    r = ex.build_exposure_report([{"ticker": t, "weight_pct": w} for t, w in holdings], pf, sf, end=END)
    assert r["status"] == "ok"
    return r


@pytest.fixture(scope="module")
def mix():
    return _report(("BANK", 60), ("PLAIN", 40))


def test_a_built_in_exposure_is_recovered():
    out = sc.run(_report(("BANK", 100)), {"short_rates": 0.25})
    # BANK moves 30 per point of the 2-year beyond the 10-year: +7.5% per 0.25 pp.
    assert abs(out["impact"] - 7.5) < 3 * out["se"]
    assert out["low"] < out["impact"] < out["high"]


def test_holdings_add_up_to_the_portfolio(mix):
    out = sc.run(mix, {"market": -10, "credit": 0.5, "gold": 5})
    assert sum(h["contribution"] for h in out["holdings"]) == pytest.approx(out["impact"], abs=1e-9)
    assert {h["ticker"] for h in out["holdings"]} == {"BANK", "PLAIN"}


def test_contributions_add_up_to_the_total(mix):
    out = sc.run(mix, {"market": -10, "rates": 1.0, "short_rates": 1.0})
    assert sum(c["impact"] for c in out["contributions"]) == pytest.approx(out["impact"], abs=1e-9)


def test_the_range_uses_the_joint_covariance_not_independent_errors():
    """The 2-year moves with the 10-year, so their estimates are strongly
    (negatively) correlated. Adding their errors as if independent would
    overstate the range of a move in both."""
    out = sc.run(_report(("LONGONLY", 100)), {"rates": 1.0, "short_rates": 1.0})
    independent = math.sqrt(sum(((c["high"] - c["low"]) / (2 * ex.Z90)) ** 2
                                for c in out["contributions"]))
    assert out["se"] < 0.95 * independent


def test_the_yen_lever_means_the_yen_rising():
    out = sc.run(_report(("YENHEDGE", 100)), {"yen": 5})
    assert out["impact"] > 0 and out["contributions"][0]["low"] > 0


def test_a_move_beyond_any_week_in_the_data_is_flagged(mix):
    small = sc.run(mix, {"market": -5})
    big = sc.run(mix, {"market": -40})
    assert not small["extrapolated"] and big["extrapolated"]
    assert "Beyond anything in the data" in sui.headline_html(big)


def test_nothing_moved_and_unknown_levers(mix):
    out = sc.run(mix, {"astrology": 3, "market": -5})
    assert out["ignored"] == ["astrology"] and set(out["moved"]) == {"market"}


def test_a_report_without_weekly_data_says_so(mix):
    old = {k: v for k, v in mix.items() if k != "series"}
    out = sc.run(old, {"market": -5})
    assert not out["available"] and "measure it again" in out["reason"]


def test_every_preset_moves_only_real_levers_within_slider_bounds():
    for p in sc.PRESETS:
        for k, v in p.moves.items():
            assert k in sc.LEVERS, (p.key, k)
            lo, hi, _ = sc.lever_range(sc.LEVERS[k])
            assert lo <= v <= hi, (p.key, k, v)


def test_units_read_naturally():
    assert sc.LEVERS["volatility"].unit == "pts"
    assert sc.LEVERS["oil"].unit == "%" and sc.LEVERS["rates"].unit == "pp"
    assert sc.describe_moves({"market": -15, "credit": 1}) == "stock market (S&P 500) −15%, credit spreads +1.00 pp"


def test_the_panels_are_labelled_and_never_a_forecast(mix):
    out = sc.run(mix, {"market": -10, "oil": 30})
    html = sui.headline_html(out) + sui.contributions_html(out) + sui.holdings_html(out) + sui.method_html(out)
    assert 'role="list" aria-label="What each moved force contributed"' in html
    assert 'aria-label="Which holdings carry the move"' in html
    assert "it is not a forecast" in html
    text = re.sub(r"<[^>]+>", " ", html).lower().replace("recommendation to buy, sell or hold", "")
    for word in ("will fall", "will rise", "expect", "buy ", "sell "):
        assert word not in text, word


def test_the_weekly_data_rides_in_the_report(mix):
    s = mix["series"]
    n = len(s["weeks"])
    assert n == len(s["portfolio"]) == len(s["market"]) >= ex.MIN_WEEKS
    assert set(s["core"]) == {f.key for f in ex.FACTORS}
    assert set(s["holdings"]) == {"BANK", "PLAIN"}
    assert all(len(v) == n for v in s["extras"].values())


# ── the page ────────────────────────────────────────────────────────────────

def _page(monkeypatch, report, state=None):
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    from tests.conftest import DASHBOARD_ROOT
    from utils import report_ui as ui

    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    monkeypatch.setattr(ui, "get_report", lambda key, mh: report)
    at = AppTest.from_file(str(DASHBOARD_ROOT / "pages/70_Scenarios.py"), default_timeout=120)
    for k, v in (state or {}).items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, "\n".join(str(e) for e in at.exception)
    return at


def _text(at) -> str:
    return " ".join(m.value for m in at.markdown)


def test_the_page_invites_a_move_before_anything_is_moved(monkeypatch, mix):
    at = _page(monkeypatch, mix)
    assert "Pick a scenario or move a lever" in _text(at)
    assert len(at.slider) >= 1 + len(ex.FACTORS)


def test_the_page_shows_the_result_for_the_moves_made(monkeypatch, mix):
    at = _page(monkeypatch, mix, {"uar_holdings": [{"ticker": "BANK", "weight_pct": 60},
                                                   {"ticker": "PLAIN", "weight_pct": 40}],
                                  "scn_market": -10.0, "scn_rates": 1.0})
    text = _text(at)
    assert "Estimated move" in text and "What each force contributed" in text
    assert "Which holdings carry the move" in text


def test_a_preset_sets_the_levers(monkeypatch, mix):
    at = _page(monkeypatch, mix)
    at.button(key="scn_p_risk_off").click().run()
    assert at.session_state["scn_market"] == -15.0 and at.session_state["scn_credit"] == 1.0
    assert "Estimated move" in _text(at)


def test_a_holdings_range_is_on_the_same_scale_as_its_contribution(mix):
    out = sc.run(mix, {"market": -10})
    for h in out["holdings"]:
        assert h["c_low"] <= h["contribution"] <= h["c_high"]
        w = h["weight_pct"] / 100
        assert h["c_low"] == pytest.approx(w * h["low"]) and h["c_high"] == pytest.approx(w * h["high"])


def test_the_track_record_s_carry_over_sits_beside_the_estimate_not_in_it(mix):
    """The first published run found readings ~32% as large a year later. The
    scenario shows that next to its number and never shrinks the number."""
    out = sc.run(mix, {"market": -10, "oil": 30})
    plain = sui.headline_html(out)
    noted = sui.headline_html(out, 0.32)
    assert "32% as large the following year" in noted and "/evidence" in noted
    assert "uses the full measured size" in noted
    assert "as large the following year" not in plain
    big = ui.fmt_pct(out["impact"])
    assert big in plain and big in noted                 # the estimate itself is unchanged
    assert sui.carry_over_html(None) == "" and sui.carry_over_html(-0.2) == ""
