"""The track record as a public page on www (seo/main.py /evidence).

The in-app page needs a live session, so the study an adviser most needs to
see could not be linked, indexed or opened by a compliance reviewer. This page
must show the published numbers against their reference lines, say when a run
was partial, say plainly when nothing is published (and not be indexed then),
and never read as a forecast.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

RESULT = {
    "available": True, "n_stocks": 494, "universe": 503, "stopped": None, "n_pairs": 61234,
    "computed_at": "2026-10-04T03:12:16+00:00", "then_weeks": 156, "next_weeks": 52,
    "origins": ["2019-09-13", "2025-09-12"], "shrinkage_slope": 0.61,
    "by_label": {"clear": {"n": 4000, "same_direction": 0.83, "consistent": 0.71},
                 "tentative": {"n": 3000, "same_direction": 0.66, "consistent": 0.74},
                 "indistinct": {"n": 50000, "same_direction": 0.52, "consistent": 0.88}},
    "by_factor": {"oil": {"n": 2100, "same_direction": 0.9, "consistent": 0.7}},
}


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import seo.main as M
    from utils import db

    engine = create_engine(f"sqlite:///{tmp_path / 'e.db'}")
    db.metadata.create_all(engine, tables=[db.research_results, db.stock_measurements,
                                           db.stock_exposures])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    monkeypatch.setattr(M, "_get_engine", lambda: (engine, None, None))
    monkeypatch.setattr(M, "_exposure_cache", {})
    return TestClient(M.app)


def test_nothing_published_says_so_and_is_not_indexed(client):
    r = client.get("/evidence")
    assert r.status_code == 200
    assert "has not been published yet" in r.text and 'content="noindex' in r.text
    assert "/evidence</loc>" not in client.get("/sitemap.xml").text


def test_the_published_run_is_shown_against_its_reference_lines(client):
    from utils import track_record as tr

    assert tr.save(dict(RESULT))
    r = client.get("/evidence")
    text = r.text
    assert r.status_code == 200 and "noindex" not in text
    assert "494 of 503 S&amp;P 500 companies" in text
    assert "83%" in text and "52%" in text           # Clear vs indistinct, same direction
    assert "a coin flip is 50%" in text and "about 90%" in text
    assert 'href="/forces/oil"' in text and "90%" in text
    assert "it is not a forecast" in text
    assert "stopped at its time limit" not in text
    assert "/evidence</loc>" in client.get("/sitemap.xml").text


def test_a_partial_run_says_so(client):
    from utils import track_record as tr

    assert tr.save(dict(RESULT, stopped="deadline", n_stocks=120))
    text = client.get("/evidence").text
    assert "stopped at its time limit" in text and "120 of 503" in text


def test_a_run_with_nothing_to_publish_is_not_advertised(client):
    from utils import track_record as tr

    assert tr.save({"available": False, "n_pairs": 0, "by_label": {}, "by_factor": {}, "origins": []})
    assert 'content="noindex' in client.get("/evidence").text
    assert "/evidence</loc>" not in client.get("/sitemap.xml").text
