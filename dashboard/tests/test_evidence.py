"""The week-by-week proof (utils/evidence.py) and how the report shows it."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from utils import evidence as ev
from utils import report_ui as ui

ROOT = Path(__file__).resolve().parent.parent
KEYS = ["rates", "dollar"]


def _series(n=156, b_dollar=-0.8, flip_at=None, seed=1, gaps=(), force_gaps=(), start_at=None):
    rng = np.random.default_rng(seed)
    m = rng.normal(0.2, 2.0, n)
    rates = rng.normal(0, 0.1, n)
    dollar = rng.normal(0, 1.0, n) + 0.2 * m             # the dollar co-moves with stocks a little
    b = np.full(n, b_dollar)
    if flip_at is not None:
        b[flip_at:] = -b_dollar                          # the exposure reverses in the later weeks
    if start_at is not None:
        b[:start_at] = 0.0                               # no exposure at all until the later weeks
    y = 1.0 * m + b * dollar + rng.normal(0, 0.35, n)
    col = lambda a: [None if i in gaps else float(v) for i, v in enumerate(a)]  # noqa: E731
    weeks = [f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)]       # sortable labels
    return {"weeks": weeks, "portfolio": col(y), "market": col(m),
            "core": {"rates": col(rates),
                     "dollar": [None if i in force_gaps else v for i, v in enumerate(col(dollar))]}}


def test_big_weeks_are_the_largest_moves_in_date_order_and_mostly_agree():
    s = _series()
    out = ev.big_weeks(s, "dollar", impact=-0.8, keys=KEYS)
    dollar = np.array(s["core"]["dollar"])
    expected = sorted(np.argsort(-np.abs(dollar))[:ev.BIG_WEEKS])
    assert [r["week"] for r in out["rows"]] == [s["weeks"][i] for i in expected]
    assert out["n"] == 8 and out["agree"] >= 7
    assert out["avg_beyond_signed"] > 0                 # signed so "the way the reading says" is positive


def test_a_persistent_exposure_holds_up_on_weeks_it_never_saw():
    o = ev.out_of_sample(_series(), "dollar", KEYS)
    assert o["available"] and o["hit_rate"] >= 0.8 and o["corr"] > 0.5
    assert o["train_weeks"] == 104 and o["test_weeks"] == 52
    assert o["slope_train"] < 0


def test_an_exposure_that_reversed_fails_the_new_weeks_test():
    o = ev.out_of_sample(_series(flip_at=104), "dollar", KEYS)
    assert o["available"] and o["hit_rate"] <= 0.3 and o["corr"] < 0


def test_the_estimate_only_sees_the_earlier_weeks():
    # No exposure for two years, a strong one after: an honest earlier-weeks
    # estimate is about zero. A fit that peeked at the later weeks would not be.
    o = ev.out_of_sample(_series(b_dollar=-1.5, start_at=104), "dollar", KEYS)
    assert abs(o["slope_train"]) < 0.15


def test_too_little_data_gives_no_verdict():
    assert ev.out_of_sample(_series(n=90), "dollar", KEYS) is None
    assert ev.big_weeks(_series(n=20), "dollar", -0.8, KEYS) is None


def test_weeks_with_missing_data_are_dropped_not_filled():
    s = _series(gaps={3, 50}, force_gaps={140})          # a gap in one force drops that week too
    o = ev.out_of_sample(s, "dollar", KEYS)
    assert o["train_weeks"] + o["test_weeks"] == 153
    assert ev.big_weeks(s, "dollar", -0.8, KEYS)["n"] == 8


def _report(evidence_by_key, series=None):
    readings = {
        "dollar": {"label": "U.S. dollar", "impact": -0.56, "low": -0.7, "high": -0.4, "evidence": "clear",
                   "shock_phrase": "the trade-weighted U.S. dollar rose 2%", "t": 4.0},
        "rates": {"label": "Interest rates", "impact": 0.01, "low": -0.1, "high": 0.1,
                  "evidence": evidence_by_key.get("rates", "indistinct"),
                  "shock_phrase": "the 10-year Treasury yield rose 0.25 percentage points", "t": 0.1},
    }
    return {"portfolio": {"readings": readings, "n_obs": 156, "start": "2023-12-01", "end": "2026-11-20",
                          "market_beta_total": 1.02},
            "top_exposures": ["dollar"], "contributions": {"dollar": [{"ticker": "VXUS", "share": 1.09}]},
            "series": series or _series()}


def test_only_clear_and_tentative_readings_are_tested():
    out = ev.evidence(_report({}))
    assert set(out) == {"dollar"}
    assert out["dollar"]["big"]["n"] == 8 and out["dollar"]["oos"]["available"]


@pytest.mark.parametrize("rate,tone,pill", [
    (0.82, "ok", "Held up on weeks it had never seen"),
    (0.6, "mid", "Partly held up on new weeks"),
    (0.5, "warn", "Did not hold up on new weeks"),
])
def test_the_verdict_follows_the_new_weeks_score(rate, tone, pill):
    assert ui._oos_verdict({"available": True, "hit_rate": rate}) == (tone, pill)
    assert ui._oos_verdict(None)[1] == "Too few weeks to test yet"


def test_the_proof_card_shows_the_weeks_the_count_and_the_test():
    rep = _report({})
    html = ui.proof_html(rep, ev.evidence(rep))
    assert "Did it show up in real weeks?" in html
    assert html.count('class="upf-bar ') == 8
    assert re.search(r"In the <b>8 weeks</b> the U\.S\. dollar moved most, this mix went the way this reading says <b>\d times</b>", html)
    assert "weeks the estimate had never seen" in html and 'data-mode="abs"' in html
    assert ui.proof_html(rep, {}) == ""


def test_the_plain_english_summary_warns_when_a_reading_failed_on_new_weeks():
    rep = _report({}, series=_series(flip_at=104))
    html = ui.plain_english_html(rep, ev.evidence(rep))
    assert "did not hold up on later weeks" in html and "treat it with caution" in html
    good = _report({})
    html = ui.plain_english_html(good, ev.evidence(good))
    assert "held up on weeks the estimate had never seen" in html
    assert "the clearest link is" in html and "the U.S. dollar" in html
    assert 'data-mode="verb"' in html and 'class="uusd-in"' in html


_BANNED = re.compile(r"\b(will|predict\w*|forecast\w*|expect(?!ations)\w*|should|buy|sell|recommend\w*)\b", re.I)


def test_nothing_in_the_proof_or_summary_forecasts_or_advises():
    rep = _report({})
    proof = ev.evidence(rep)
    for html in (ui.plain_english_html(rep, proof), ui.proof_html(rep, proof)):
        text = re.sub(r"(?:is|are) not a forecast", "", re.sub(r"<[^>]+>", " ", html))
        assert not _BANNED.search(text), _BANNED.search(text)


def test_the_report_page_computes_the_proof_once_and_shows_both():
    page = (ROOT / "pages" / "60_Exposure_Report.py").read_text(encoding="utf-8")
    assert page.count("_ev.evidence(report)") == 1
    assert "ui.plain_english_html(report, _proof)" in page and "ui.proof_html(report, _proof)" in page
    assert page.index("plain_english_html") < page.index("summary_tiles_html")    # the answer comes first


def test_big_weeks_judge_a_force_net_of_the_other_forces():
    # Credit-spread blowouts are often big rate weeks too. A long-bond fund
    # loses on wider spreads but gains far more on the falling rates that come
    # with them; judged on the market alone, the credit reading would look
    # backwards in exactly its biggest weeks.
    rng = np.random.default_rng(7)
    n = 156
    m = rng.normal(0.2, 2.0, n)
    credit = rng.normal(0, 0.1, n)
    rates = -1.5 * credit + rng.normal(0, 0.05, n)       # spreads widen while yields fall
    y = 0.3 * m - 9.0 * rates - 1.2 * credit + rng.normal(0, 0.15, n)
    s = {"weeks": [f"w{i:03d}" for i in range(n)], "portfolio": list(y), "market": list(m),
         "core": {"rates": list(rates), "credit": list(credit)}}
    out = ev.big_weeks(s, "credit", impact=-1.2, keys=["rates", "credit"])
    assert out["agree"] >= 7
