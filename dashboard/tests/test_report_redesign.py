"""The report leads with the answer (2026-11 redesign).

What these pin, each a promise of the brief rather than a pixel:
  * findings come before account and upgrade copy, and before the diagram;
  * the marketing banner is gone once a report is on screen;
  * one shared scale; evidence carried by fill as well as by the chip, and an
    uncertain reading is never labelled as a zero;
  * the history charts say they are a shorter window than the headline;
  * the loading state is a skeleton with no figures in it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_exposure import _report
from utils import report_charts as charts
from utils import report_ui as ui

PAGE = (Path(__file__).resolve().parent.parent / "pages" / "60_Exposure_Report.py").read_text(encoding="utf-8")


@pytest.fixture
def report():
    return _report()


@pytest.fixture
def mixed(report):
    """The fixture with what it lacks: a Tentative reading, and a holding that
    pushes against a held-up one (an offset that must not be drawn as a flow)."""
    import copy
    r = copy.deepcopy(report)
    r["portfolio"]["readings"]["dollar"]["evidence"] = "tentative"
    r["contributions"]["rates"].append({"ticker": "GLD", "weight_pct": 5.0, "impact": 0.6, "evidence": "clear",
                                        "contribution": 0.03, "share": -0.02})
    return r


def _at(text: str) -> int:
    i = PAGE.find(text)
    assert i >= 0, text
    return i


def test_the_findings_come_first():
    take, table = _at("ui.takeaway_html(report)"), _at("ui.exposure_table_html(report, _held)")
    assert take < table
    # Account and upgrade copy, and the diagram, follow the findings.
    assert table < _at("Want to hear when this changes?") and table < _at("Investor Pro: get an email")
    assert table < _at("ui.exposure_map_html(report)")
    assert 'st.expander("See the exposures as a diagram")' in PAGE
    # Holdings detail before history.
    assert _at('"## Which holdings drive each exposure"') < _at('"## How these exposures have moved"')


def test_the_banner_only_introduces_an_empty_page():
    head = PAGE[_at("if editing:\n    product_page_header("):]
    assert head.index("product_page_header(") < 40
    assert 'type="primary"' in PAGE[_at('st.button("Change holdings"'):][:120]


def test_one_scale_and_evidence_in_the_fill(report):
    html = ui.exposure_table_html(report)
    scales = set(re.findall(r"One shared scale, ±([0-9.]+)%", html))
    assert len(scales) == 1
    assert html.count('class="uar-xaxis"') == 1
    assert 'class="uar-fill uar-fill-zero"' in ui.exposure_bar(-0.1, -0.3, 0.1, 1.0, "indistinct")
    assert 'class="uar-fill uar-fill-tent"' in ui.exposure_bar(0.2, 0.05, 0.4, 1.0, "tentative")
    assert 'class="uar-fill"' in ui.exposure_bar(0.5, 0.4, 0.6, 1.0, "clear")


def test_an_uncertain_reading_keeps_its_full_name():
    cell = ui._evidence_cell("indistinct")
    assert 'title="Not distinguishable from zero"' in cell
    assert '<span class="uar-sr">Not distinguishable from zero</span>' in cell
    assert ">Zero<" not in cell and ">0<" not in cell


def test_the_takeaway_names_the_holding_and_never_forecasts(report):
    from tests.test_exposure import _BANNED

    html = ui.takeaway_html(report)
    text = re.sub(r"<[^>]+>", " ", html)
    assert "sensitive to" in text.lower()
    assert not _BANNED.search(text)
    rows = report["contributions"]
    lead = next((k for k in ui.ordered_keys(report) if report["portfolio"]["readings"][k]["evidence"] == "clear"
                 and rows.get(k) and (rows[k][0].get("share") or 0) >= 0.5), None)
    if lead:
        from utils import holding_names as hn
        assert f'{hn.with_name(rows[lead][0]["ticker"])} carries' in text   # spelled out for a beginner


def test_history_says_it_is_a_shorter_window(report):
    note = ui.window_note_html(report)
    assert "Rolling 52-week estimates" in note and "156 weeks" in note and "even in sign" in note
    html = charts.rolling_charts_html(report, ui.ordered_keys(report))
    if html:
        assert "latest 52-wk" in html and "3-yr headline" in html


def test_the_workspace_header_carries_the_window_and_date(report):
    html = ui.workspace_header_html("Client — a very long portfolio name " * 3, report)
    assert "data through" in html and "weeks," in html and "holding" in html


def test_the_loading_state_is_a_skeleton_without_figures():
    html = ui.report_skeleton_html("Measuring three years of weekly returns.")
    assert html.count('class="uar-sk-row"') == 5 and 'role="status"' in html
    assert not re.search(r"\d+%", html)


def test_the_flow_draws_only_contributions_that_add_to_a_held_up_reading(mixed):
    report = mixed
    svg = ui.flow_svg(report)
    readings = report["portfolio"]["readings"]
    drawn = re.findall(r"<title>([^<]+?) → ([^<:]+?): ([0-9.]+) points", svg)
    assert drawn, "nothing drawn"
    labels = {r["label"]: k for k, r in readings.items()}
    for named, label, v in drawn:
        ticker = named.split(" ")[0]                     # "TLT (iShares 20+ Year Treasury Bond ETF)"
        key = labels[label.replace("&amp;", "&")]
        assert readings[key]["evidence"] in ("clear", "tentative")
        c = next(c for c in report["contributions"][key] if c["ticker"] == ticker)
        assert c["contribution"] * readings[key]["impact"] > 0          # same direction only
        assert abs(abs(c["contribution"]) - float(v)) < 0.006
    assert "<title>GLD " not in svg                                       # the offset is not a flow


def test_the_tiles_restate_the_report_and_nothing_else(mixed):
    report = mixed
    html = ui.summary_tiles_html(report)
    readings = report["portfolio"]["readings"]
    order = ui.ordered_keys(report)
    held = sum(readings[k]["evidence"] in ("clear", "tentative") for k in order)
    assert f"{held} of {len(order)}" in html
    assert readings[order[0]]["label"] in html and ui.fmt_pct(readings[order[0]]["impact"]) in html
    assert html.count('class="uar-mk ') == len(order)
    assert held == 3 and "1 Tentative" in html                            # Tentative counts as held up


def test_a_stock_page_shows_where_it_sits_and_never_clips_itself():
    from utils.exposure_pages import universe_map_html
    me = {"ticker": "AAA", "exposures": {"rates": {"impact": -9.0, "low": -10, "high": -8, "evidence": "clear"},
                                          "oil": {"impact": 0.4, "low": 0.1, "high": 0.7, "evidence": "tentative"}}}
    others = [{"ticker": f"T{i}", "exposures": {"rates": {"impact": (i % 7) - 3, "evidence": "indistinct"},
                                                 "oil": {"impact": (i % 5) - 2, "evidence": "indistinct"}}}
              for i in range(80)]
    html = universe_map_html("AAA", me, others)
    assert "Where AAA sits among 81 stocks" in html
    # AAA's -9% reading widens the axis instead of being pinned to the edge.
    assert "−9.0% with interest rates" not in html and "+9.0% with interest rates" in html
    assert universe_map_html("AAA", me, others[:10]) == ""          # too few to draw
