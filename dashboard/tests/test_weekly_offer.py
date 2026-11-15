"""The weekly email is offered to the visitors who could use it.

Until 2026-11 it was a checkbox shown only to signed-in users who had already
opened a report -- invisible to every visitor without an account, i.e. nearly
everyone (7 accounts). It is now offered on /mylist and, signed out, under the
app's report; neither promises news every week.
"""

from __future__ import annotations

from pathlib import Path

from utils import list_page as lp

ROOT = Path(__file__).resolve().parent.parent


def test_my_list_offers_the_weekly_email_honestly():
    html = lp.list_page_html([], "https://www.x", "https://app.x")
    assert 'id="ls-weekly"' in html and "weekly summary of what changed" in html
    assert "Most weeks nothing measurable does" in html


def test_the_signed_out_report_offers_it_too():
    src = (ROOT / "pages" / "60_Exposure_Report.py").read_text(encoding="utf-8")
    i = src.index("Email me a weekly summary of what changed in this portfolio")
    tail = src[i:i + 2500]
    assert 'elif report.get("status") == "ok":' in tail and "free account saves this portfolio" in tail
