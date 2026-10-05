"""GET /status on the SEO service: where the weekly pipelines actually are.

Added after the library sat at 152 of ~500 companies, a week old, and the only
way to tell from outside Render was opening stock pages one by one. It must
count what is really in the database, report the track record honestly
(including a run cut short, or none at all), and expose no readings.
"""

from __future__ import annotations

import copy

import pytest
from sqlalchemy import create_engine


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import seo.main as M
    from tests.test_extra_forces import _one
    from utils import db
    from utils import stock_library as lib

    engine = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    db.metadata.create_all(engine, tables=[db.stock_measurements, db.stock_exposures,
                                           db.research_results])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    monkeypatch.setattr(M, "_get_engine", lambda: (engine, None, None))
    base = _one("BANK")

    def as_ticker(t):
        r = copy.deepcopy(base)
        r["positions"] = [{"ticker": t, "weight_pct": 100.0}]
        return r

    assert lib.record(as_ticker("AAPL"), "Apple Inc.")
    assert lib.record(as_ticker("NOTINDEX"), "Viewed Co")
    return TestClient(M.app)


def test_it_counts_the_library_against_the_index(client):
    from cron.measure_library import load_constituents

    r = client.get("/status")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    lib = r.json()["library"]
    assert lib["stocks"] == 2
    assert lib["index_measured"] == 1                 # AAPL; the viewed stock is not in the index
    assert lib["index_size"] == len(load_constituents())
    assert lib["newest_measured_at"] and lib["data_through"]


def test_no_track_record_is_said_plainly(client):
    assert client.get("/status").json()["track_record"] == {"published": False}


def test_a_partial_track_record_says_so(client):
    from utils import track_record as tr

    assert tr.save({"available": True, "n_stocks": 120, "universe": 503, "stopped": "deadline",
                    "by_label": {}, "by_factor": {}, "n_pairs": 10, "origins": []})
    t = client.get("/status").json()["track_record"]
    assert t["published"] is True and t["stocks"] == 120 and t["universe"] == 503
    assert t["stopped"] == "deadline" and t["computed_at"]


def test_it_exposes_counts_and_dates_not_readings(client):
    text = client.get("/status").text
    assert "impact" not in text and "exposures" not in text and "AAPL" not in text
