"""Single-stock pages get the plain-English answer, the proof and the stock track record."""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

from tests.test_evidence import _report
from utils import evidence as ev
from utils import explain as xp
from utils import report_ui as ui

ROOT = Path(__file__).resolve().parent.parent


def _stock_report(extras=None):
    rep = _report({})
    rep["contributions"] = {"dollar": [{"ticker": "XOM", "share": 1.0}]}
    if extras is not None:
        rep["extras"] = {"readings": extras}
    return rep


_VALUE = {"value": {"label": "Value vs growth", "impact": 0.93, "t": 6.1, "evidence": "clear",
                    "shock_phrase": "value stocks beat growth stocks by 1 percentage point"},
          "size": {"label": "Small vs large companies", "impact": 0.2, "t": 2.9, "evidence": "clear",
                   "shock_phrase": "small companies beat large ones by 1 percentage point"},
          "gold": {"label": "Gold", "impact": 0.1, "t": 1.0, "evidence": "indistinct", "shock_phrase": "gold rose 10%"}}


def test_the_summary_names_the_stock_not_a_mix_and_drops_mostly_through():
    rep = _stock_report()
    html = ui.plain_english_html(rep, ev.evidence(rep), stock="XOM")
    assert "this mix" not in html and "mostly through" not in html
    assert re.search(r"If you had .*? in XOM", html)
    assert "In a week the U.S. stock market rose 1%, XOM typically" in html


def test_a_portfolio_summary_is_unchanged():
    rep = _report({})
    html = ui.plain_english_html(rep, ev.evidence(rep))
    assert "this mix" in html and "mostly through VXUS" in html


def test_the_clearest_other_force_is_shown_with_its_tested_record():
    rep = _stock_report(_VALUE)
    html = ui.plain_english_html(rep, ev.evidence(rep), stock="XOM")
    assert "the clearest is <b>value vs growth</b>" in html            # the larger |t| of the two Clear ones
    assert "held up on new weeks 82% of the time in our tests" in html and "small vs large" not in html.lower()
    assert "Among the other forces" not in ui.plain_english_html(_stock_report({}), {}, stock="XOM")


def test_the_proof_panel_names_the_stock_and_cites_the_stock_record():
    rep = _stock_report()
    html = ui.proof_html(rep, ev.evidence(rep), stock="XOM")
    assert "XOM went the way this reading says" in html and "this mix" not in html
    assert "XOM&#39;s move beyond the stock market" in html
    assert escape(xp.TRACK_RECORD_STOCKS) in html and escape(xp.TRACK_RECORD) not in html
    assert "71%" in xp.TRACK_RECORD_STOCKS and "70 single stocks" in xp.TRACK_RECORD_STOCKS


_BANNED = re.compile(r"\b(will|predict\w*|forecast\w*|expect(?!ations)\w*|should|buy|sell|recommend\w*)\b", re.I)


def test_nothing_on_the_stock_summary_forecasts_or_advises():
    rep = _stock_report(_VALUE)
    for html in (ui.plain_english_html(rep, ev.evidence(rep), stock="XOM"),
                 ui.proof_html(rep, ev.evidence(rep), stock="XOM")):
        text = re.sub(r"(?:is|are) not a forecast", "", re.sub(r"<[^>]+>", " ", html))
        assert not _BANNED.search(text), _BANNED.search(text)


def test_the_stock_page_shows_all_three():
    page = (ROOT / "pages" / "69_Stock.py").read_text(encoding="utf-8")
    assert "ui.plain_english_html(report, _proof, stock=ticker)" in page
    assert "ui.proof_html(report, _proof, stock=ticker)" in page
    assert "_xp.glossary_html(" in page
    assert page.index("plain_english_html") < page.index("exposure_table_html")   # the answer comes first


def test_a_proven_force_is_preferred_and_an_untested_one_says_so():
    extras = {"gold": {"label": "Gold", "impact": 0.3, "t": 9.0, "evidence": "clear", "shock_phrase": "gold rose 10%"},
              "size": {"label": "Small vs large companies", "impact": 0.2, "t": 3.0, "evidence": "clear",
                       "shock_phrase": "small companies beat large ones by 1 percentage point"}}
    html = ui.plain_english_html(_stock_report(extras), {}, stock="XOM")
    assert "the clearest is <b>small vs large companies</b>" in html            # proven (71%) beats a larger t
    only_gold = ui.plain_english_html(_stock_report({"gold": extras["gold"]}), {}, stock="XOM")
    assert "not yet tested enough on new weeks" in only_gold
    passed = dict(extras["gold"], oos={"passed": True, "hits": 9, "big_weeks": 11})
    assert "passed its own test on new weeks: 9 of 11" in xp.extra_verdict("gold", passed)
    assert xp.extra_proven("value") and not xp.extra_proven("euro")        # euro: too few weeks to count
