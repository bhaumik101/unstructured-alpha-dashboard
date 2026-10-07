"""How each force held up out of sample, shown beside its reading.

The first real track-record run (2026-10-04) found Clear/Tentative readings
on rates kept their direction a year later 72% of the time and on oil 55%,
against a 50% coin flip. The report now says so next to each reading -- from
the published study only: no run, or too few readings, means no line.
"""

from __future__ import annotations

from utils import report_ui as ui
from utils import track_record as tr

from tests.test_report_ui import report  # noqa: F401  (the shared report fixture)

STUDY = {"available": True, "by_factor": {
    "rates": {"n": 2282, "same_direction": 0.72, "consistent": 0.70},
    "oil": {"n": 1922, "same_direction": 0.55, "consistent": 0.64},
    "credit": {"n": 12, "same_direction": 0.9, "consistent": 0.9},     # too few
}}


def test_only_published_forces_with_enough_readings_get_a_figure():
    held = tr.persistence(STUDY)
    assert held == {"rates": {"rate": 0.72, "n": 2282}, "oil": {"rate": 0.55, "n": 1922}}
    assert tr.persistence(None) == {} and tr.persistence({"available": False}) == {}


def test_the_line_is_for_clear_and_tentative_readings_only():
    held = tr.persistence(STUDY)
    assert "55%" in tr.persistence_short("oil", "clear", held)
    assert "coin flip: 50%" in tr.persistence_short("oil", "tentative", held)
    assert tr.persistence_short("oil", "indistinct", held) is None
    assert tr.persistence_short("credit", "clear", held) is None


def test_the_report_shows_it_beside_the_reading_and_in_the_detail(report):
    held = {k: {"rate": 0.61, "n": 999} for k in report["portfolio"]["readings"]}
    table = ui.exposure_table_html(report, held)
    shown = [k for k, r in report["portfolio"]["readings"].items()
             if r["evidence"] in ("clear", "tentative")]
    assert shown and table.count("Held its direction a year later 61%") == len(shown)
    detail = ui.factor_detail_html(report, shown[0], held)
    assert "kept their direction the following year 61% of the time" in detail
    assert "999 readings" in detail and tr.EVIDENCE_URL in detail


def test_no_study_means_no_line(report):
    assert "Held its direction" not in ui.exposure_table_html(report)
    key = next(iter(report["portfolio"]["readings"]))
    assert "Out of sample" not in ui.factor_detail_html(report, key)


def test_the_public_stock_page_shows_it_for_readings_that_held_up():
    from tests.test_exposure_pages import _rec
    from utils import exposure_pages as ep

    rec = _rec(oil=(2.0, "clear"), rates=(0.1, "indistinct"))
    held = tr.persistence(STUDY)
    html = ep.stock_page_html("XOM", rec, [rec], [], "https://www.x", "https://app.x", held)
    assert html.count("Held its direction a year later") == 1     # oil only, not the weak rates
    assert "55%" in html and 'href="/evidence"' in html
    bare = ep.stock_page_html("XOM", rec, [rec], [], "https://www.x", "https://app.x")
    bare = bare.split('<main id="main">')[1].split("</main>")[0]   # the site footer links /evidence everywhere
    assert "Held its direction" not in bare and 'href="/evidence"' not in bare
