"""Return attribution: what drove a portfolio's past weeks.

What must hold:
  * the parts add up exactly to the total (summed weekly returns);
  * the market and every core force are counted, and what no force explains
    is its own line, never folded away;
  * a built-in driver shows up as the driver;
  * reports measured before the weekly data was kept fall back gracefully;
  * the waterfall is a labelled, ordered list and never reads as a forecast.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_extra_forces import END, _world  # noqa: E402
from utils import attribution as attr  # noqa: E402
from utils import attribution_ui as aui  # noqa: E402
from utils import exposure as ex  # noqa: E402


def _report(*holdings):
    pf, sf = _world()
    r = ex.build_exposure_report([{"ticker": t, "weight_pct": w} for t, w in holdings], pf, sf, end=END)
    assert r["status"] == "ok"
    return r


@pytest.fixture(scope="module")
def mix():
    return _report(("LONGONLY", 50), ("PLAIN", 50))


@pytest.mark.parametrize("weeks", attr.WINDOWS)
def test_the_parts_add_up_to_the_total(mix, weeks):
    a = attr.attribute(mix, weeks)
    assert a["weeks"] == weeks
    assert sum(l["contribution"] for l in a["lines"]) == pytest.approx(a["total"], abs=1e-9)


def test_market_every_core_force_and_the_unexplained_are_lines(mix):
    a = attr.attribute(mix, 26)
    keys = [l["key"] for l in a["lines"]]
    assert keys[0] == "market" and keys[-1] == "other"
    assert set(keys[1:-1]) == {f.key for f in ex.FACTORS}


def test_a_built_in_driver_is_the_driver():
    """LONGONLY moves with the 10-year yield, so beyond the market, rates
    should carry most of what the forces explain over a year."""
    a = attr.attribute(_report(("LONGONLY", 100)), 52)
    forces = [l for l in a["lines"] if l["kind"] == "force"]
    top = max(forces, key=lambda l: abs(l["contribution"]))
    assert top["key"] == "rates"


def test_the_market_line_is_beta_times_the_market(mix):
    a = attr.attribute(mix, 13)
    m = a["lines"][0]
    mkt = sum(mix["series"]["market"][-13:])
    assert m["contribution"] == pytest.approx(mix["portfolio"]["market_beta"] * mkt, rel=1e-6)


def test_a_report_without_weekly_data_falls_back(mix):
    old = {k: v for k, v in mix.items() if k != "series"}
    assert not attr.available(old) and attr.attribute(old, 13) is None


def test_the_waterfall_reads_as_sentences_and_not_a_forecast(mix):
    html = aui.waterfall_html(attr.attribute(mix, 26))
    assert '<ol class="atw-list" aria-label="Return attribution, largest first">' in html
    assert 'aria-label="Total:' in html and "Not explained by these forces" in html
    assert "it is not a test or a forecast" in html
    text = re.sub(r"<[^>]+>", " ", html).lower()
    for word in ("will rise", "will fall", "expected to", "buy ", "sell "):
        assert word not in text, word


def test_the_report_page_shows_attribution():
    src = (_ROOT / "pages" / "60_Exposure_Report.py").read_text(encoding="utf-8")
    assert 'st.markdown("## What drove returns")' in src
    assert "attr.attribute(report" in src
