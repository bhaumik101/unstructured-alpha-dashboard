"""The report's charts: how exposures have moved, what the forces did, and who
carries each exposure.

The product says it shows "how those exposures are changing". Until these
charts, it showed that as one before-and-after sentence per force. How a
sensitivity moved is a shape, and a shape reads faster as a picture.

The tests below mostly pin the one way a chart like this lies without meaning
to: drawing a rolling estimate without its uncertainty, so a year of noise
looks like a trend. The 90% range is drawn, the evidence at each point is
marked, and the words under the chart say what it does not show.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_exposure import _BANNED, _report  # noqa: E402
from utils import exposure as ex  # noqa: E402
from utils import report_charts as charts  # noqa: E402
from utils import report_ui as ui  # noqa: E402


@pytest.fixture(scope="module")
def report():
    r = _report()
    assert r["status"] == "ok"
    return r


def _visible(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


# ── the engine side ─────────────────────────────────────────────────────────

def test_the_rolling_sensitivity_is_measured_for_every_force(report):
    rolling = report["rolling"]
    assert set(rolling) == set(report["portfolio"]["readings"])
    for points in rolling.values():
        assert len(points) >= 20, "a rolling year stepped monthly over three years"
        for p in points:
            assert p["low"] <= p["impact"] <= p["high"], "every point carries its own range"
            assert p["evidence"] in ex.EVIDENCE_LABELS


def test_the_last_rolling_point_is_now(report):
    """The final window always ends on the report's last week, so the line
    finishes where the reader is standing rather than a few weeks short."""
    for points in report["rolling"].values():
        assert points[-1]["end"] == report["as_of"]


def test_each_rolling_point_uses_the_same_evidence_bar_as_the_headline():
    """A looser bar on the chart than on the table would let the chart show
    "clear" dots the table would not have called clear."""
    source = (_ROOT / "utils" / "exposure.py").read_text(encoding="utf-8")
    block = source[source.index("def _rolling("):source.index("def _factor_paths(")]
    assert "_fit_on_frame(window" in block
    assert "clear_t" not in block, "the rolling fit must not pass its own, looser threshold"


def test_too_short_a_history_draws_no_rolling_chart_rather_than_a_misleading_one():
    import pandas as pd

    frame = pd.DataFrame({"__portfolio__": [0.0] * 30})
    assert ex._rolling(frame, ex.FACTORS) == {}


def test_the_factor_paths_are_the_published_series_over_the_same_weeks(report):
    paths = report["factor_paths"]
    assert paths, "the report should carry what each force did"
    for key, path in paths.items():
        assert len(path["dates"]) == len(path["values"]) >= 100
        assert path["first"] == path["values"][0] and path["last"] == path["values"][-1]
        assert path["dates"][0] >= report["portfolio"]["start"]
        assert path["dates"][-1] <= report["as_of"]


def test_a_gap_in_a_published_series_stays_a_gap():
    import numpy as np
    import pandas as pd

    idx = pd.bdate_range("2025-01-01", periods=400)
    values = pd.Series(np.linspace(3, 4, len(idx)), index=idx)
    values.iloc[100:180] = np.nan
    weeks = pd.date_range(idx[0], idx[-1], freq="W-FRI")
    out = ex._factor_paths({"rates": values}, weeks)
    assert len(out["rates"]["values"]) < len(weeks), "missing weeks must not be filled in"


# ── the charts ──────────────────────────────────────────────────────────────

def test_the_rolling_chart_draws_the_range_not_just_the_line(report):
    html = charts.rolling_charts_html(report, ui.ordered_keys(report))
    panels = html.count('class="uac-panel"')
    assert panels == len(report["rolling"])
    assert html.count('fill-opacity="0.16"') == panels, "each panel shades its 90% range"
    assert html.count('class="uac-zero"') == panels, "each panel marks zero"


def test_the_rolling_chart_says_what_it_does_not_show(report):
    html = charts.rolling_charts_html(report, ui.ordered_keys(report))
    text = _visible(html)
    assert "could be noise" in text
    assert "does not show where it goes next" in text
    assert not _BANNED.search(text), _BANNED.search(text).group(0)


def test_every_chart_can_be_read_without_seeing_it(report):
    """A chart that only exists visually is not accessible. Each SVG says in
    words what it shows."""
    order = ui.ordered_keys(report)
    for html in (charts.rolling_charts_html(report, order),
                 charts.factor_paths_html(report, order),
                 charts.contribution_bars_svg(report, order[0])):
        svgs = re.findall(r"<svg[^>]*>", html)
        assert svgs
        for svg in svgs:
            assert 'role="img"' in svg and 'aria-label="' in svg


def test_the_dots_follow_the_evidence():
    """Filled where clear, open where tentative, none where it could be noise —
    so a stretch of line with no dots on it reads as what it is.

    Built from a synthetic series that has all three kinds on purpose. The
    first version used the fixture's first factor, which happens to be clear
    at every point, so a mutation that also drew dots for noise still passed.
    """
    kinds = ["clear", "tentative", "indistinct", "indistinct", "clear", "tentative", "indistinct"]
    points = [{"end": f"2026-0{i + 1}-01", "impact": 0.1 * i, "low": 0.1 * i - 0.5,
               "high": 0.1 * i + 0.5, "evidence": kind} for i, kind in enumerate(kinds)]
    key = "rates"
    svg = charts.rolling_panel_svg(key, "Test", points)
    clear = sum(p["evidence"] == "clear" for p in points)
    tentative = sum(p["evidence"] == "tentative" for p in points)
    assert svg.count("<circle") == clear + tentative
    assert svg.count('fill="var(--uar-surface)"') == tentative


def test_the_force_cards_say_what_moved_in_the_right_unit(report):
    html = charts.factor_paths_html(report, ui.ordered_keys(report))
    text = _visible(html)
    if "rates" in report["factor_paths"]:
        assert "pts" in text, "a change in a yield is percentage points, not percent"
    if "oil" in report["factor_paths"]:
        assert "$" in text
    assert "not what this portfolio did" in text


def test_the_contribution_bars_add_up_to_the_reading_they_split(report):
    key = ui.ordered_keys(report)[0]
    rows = report["contributions"][key]
    assert sum(r["contribution"] for r in rows) == pytest.approx(
        report["portfolio"]["readings"][key]["impact"], abs=1e-6)
    svg = charts.contribution_bars_svg(report, key)
    for row in rows[:12]:
        assert row["ticker"] in svg
    assert "work against the rest" in svg


def test_a_holding_that_could_be_noise_is_drawn_pale_not_hidden(report):
    key = ui.ordered_keys(report)[0]
    rows = report["contributions"][key]
    svg = charts.contribution_bars_svg(report, key)
    pale = sum(r["evidence"] not in ("clear", "tentative") for r in rows[:12])
    assert svg.count('fill-opacity="0.28"') == pale


def test_charts_disappear_rather_than_break_on_an_old_cached_report():
    """A report cached before these fields existed has no "rolling" key. The
    section should vanish, not raise."""
    old = {"portfolio": {"readings": {"rates": {"label": "Interest rates", "impact": -1.0,
                                                "evidence": "clear", "shock_phrase": "x"}}},
           "contributions": {}}
    assert charts.rolling_charts_html(old, ["rates"]) == ""
    assert charts.factor_paths_html(old, ["rates"]) == ""
    assert charts.contribution_bars_svg(old, "rates") == ""


def test_a_cached_report_from_older_code_is_not_served_to_newer_code():
    """Bumping the schema is what makes the new sections appear straight after
    a deploy, instead of up to six hours later for anyone already measured."""
    from utils import report_cache

    assert report_cache.REPORT_SCHEMA >= 2
    source = (_ROOT / "utils" / "report_cache.py").read_text(encoding="utf-8")
    assert '"schema": REPORT_SCHEMA' in source


def test_the_charts_use_the_type_scale_not_fresh_literals():
    literals = re.findall(r"font-size:\s*[0-9.]+(?:rem|px|em)", charts.CHART_CSS)
    assert not literals, literals


def test_the_what_changed_page_no_longer_says_the_email_does_not_exist():
    """It said "a weekly email ... isn't available yet" while the email was
    built, live, and opted into from the report."""
    page = (_ROOT / "pages" / "61_What_Changed.py").read_text(encoding="utf-8")
    assert "isn&#39;t available yet" not in page and "isn't available yet" not in page
    assert "weekly summary" in page


def test_proper_nouns_survive_the_chart_subtitle(report):
    """str.capitalize() lowercases the rest of the string: the first version
    printed "the 10-year treasury yield" and "the trade-weighted u.s. dollar"."""
    html = charts.rolling_charts_html(report, ui.ordered_keys(report))
    assert "treasury" not in html and "u.s." not in html
    if "rates" in report["rolling"]:
        assert "Treasury" in html
