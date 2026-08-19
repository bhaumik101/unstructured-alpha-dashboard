"""The weekly brief has a public page again.

#162 found the subscriber email promising "Continue reading -> full brief at
stocks.unstructuredalpha.com" when that host had no DNS record and /brief
existed only in seo/app.py, an undeployed copy of this service (deleted in
#168). The email was made self-contained instead, and the promise removed.

This restores the destination properly, in the service that actually runs:
/brief renders the newest note, /brief/{id} renders one from the archive, and
both are in the sitemap so the long tail is indexable.

WHY ESCAPING MATTERS HERE AND NOT ON THE OTHER PAGES
----------------------------------------------------
Every other route interpolates values from utils/config.py -- a static registry
in the repo. The brief body is model-written prose stored in macro_narratives,
so it is the one thing on these pages that is neither authored nor reviewed by
hand before it renders.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import seo.main as _M  # noqa: E402

_LATEST = {
    "id": 42, "note_date": "2026-08-16", "regime": "RISK-ON",
    "headline": "Labor Market Resilience Offsets Credit Spread Widening",
    "body": (
        "Opening paragraph sets the regime and composite score.\n\n"
        "Second paragraph covers the bullish signals.\n\n"
        "Third covers the bearish offsets.\n\n"
        "Bottom Line: risk-on bias holds; a credit spread breakout would flip it."
    ),
    "bull_count": 31, "bear_count": 16,
}
_OLDER = dict(_LATEST, id=41, note_date="2026-08-09", headline="The Week Before")


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(_M, "_get_engine", lambda: (None, None, None))
    monkeypatch.setattr(_M, "_brief_rows", lambda engine, limit=12: [_LATEST, _OLDER])
    return TestClient(_M.app)


def test_brief_serves_the_latest_note_in_full(client):
    html = client.get("/brief").text
    for para in _LATEST["body"].split("\n\n"):
        assert para.strip() in html, f"paragraph missing from the page: {para[:40]}"


def test_the_bottom_line_is_the_one_that_gets_emphasis(client):
    """It is the actionable paragraph, and it is always last."""
    html = client.get("/brief").text
    assert "border-left:3px solid" in html, (
        "the closing Bottom Line paragraph is not distinguished from the body"
    )


def test_an_archive_note_is_reachable_by_id(client):
    html = client.get("/brief/41").text
    assert "The Week Before" in html
    assert "Opening paragraph sets the regime" in html


def test_an_unknown_note_is_a_404_not_a_blank_page(client):
    assert client.get("/brief/999").status_code == 404


def test_model_written_prose_is_escaped(client, monkeypatch):
    hostile = dict(_LATEST, body="Innocent lede.\n\n<script>alert(1)</script>")
    monkeypatch.setattr(_M, "_brief_rows", lambda engine, limit=12: [hostile])
    html = client.get("/brief").text
    assert "<script>alert(1)</script>" not in html, "brief body is not escaped"
    assert "&lt;script&gt;" in html


def test_the_page_canonicalises_to_the_specific_note(client):
    """/brief and /brief/42 are the same content; only one should be indexed."""
    canon = re.search(r'rel="canonical" href="([^"]+)"', client.get("/brief").text)
    assert canon, "no canonical on /brief"
    assert canon.group(1).endswith("/brief/42"), (
        f"/brief canonicalises to {canon.group(1)}, so it competes with the "
        "per-note URL for the same content"
    )


def test_the_brief_is_in_the_sitemap(client, monkeypatch):
    monkeypatch.setattr(_M, "_get_config", lambda: ({"AAPL": {}}, {"s1": {"name": "S"}}))
    xml = client.get("/sitemap.xml").text
    assert "/brief</loc>" in xml, "the brief index is not in the sitemap"
    assert len(re.findall(r"/brief/\d+</loc>", xml)) == 2, (
        "archived briefs are not listed, so only the newest is discoverable"
    )


def test_no_published_note_is_a_503_not_a_crash(client, monkeypatch):
    monkeypatch.setattr(_M, "_brief_rows", lambda engine, limit=12: [])
    r = client.get("/brief")
    assert r.status_code == 503
    assert "No brief published yet" in r.text
