"""The weekly look-through refresh (cron/refresh_lookthrough.py).

  * It downloads a filing only when the fund's latest filing is new; a fund
    whose filing is unchanged costs one feed request and writes nothing.
  * A newer stored filing wins over the bundled snapshot in the report.
  * A failed fund keeps what it had; the job fails only if every fund failed.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from utils import db
from utils import lookthrough as lt
from utils import nport


@pytest.fixture
def store(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'lt.db'}")
    db.metadata.create_all(engine, tables=[db.fund_lookthrough])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    monkeypatch.setattr(lt, "_snap", None)
    monkeypatch.setattr(lt, "_bundled", lambda: {"built": "x", "funds": {
        "AAA": {"holdings": 10, "filed": "2026-08-28", "period": "2026-06-30", "source": "https://www.sec.gov/old"},
        "BBB": {"holdings": 20, "filed": "2026-08-28", "period": "2026-06-30", "source": "https://www.sec.gov/b"}}})
    monkeypatch.setattr(nport, "series_map", lambda: {"AAA": [1, "S1", "C1", "AAA"], "BBB": [2, "S2", "C2", "BBB"]})
    monkeypatch.setattr(nport, "fund_tickers", lambda: ["AAA", "BBB"])
    yield engine
    lt._snap = None


def test_only_new_filings_are_downloaded_and_stored(store, monkeypatch):
    from cron import refresh_lookthrough as job
    downloads = []
    feed = {"S1": ("2026-11-20", "https://www.sec.gov/new"), "S2": ("2026-08-28", "https://www.sec.gov/b")}
    monkeypatch.setattr(nport, "latest_filing", lambda s: feed[s])

    def fake_get(url, timeout=90):
        downloads.append(url)
        return b'<x xmlns="http://www.sec.gov/edgar/nport"><repPdDate>2026-09-30</repPdDate><invstOrSecs>' \
               b'<invstOrSec><name>A</name><pctVal>100</pctVal><assetCat>EC</assetCat><issuerCat>CORP</issuerCat>' \
               b'<invCountry>US</invCountry><curCd>USD</curCd></invstOrSec></invstOrSecs></x>'
    monkeypatch.setattr(nport, "get", fake_get)
    assert job.main() == 0
    assert downloads == ["https://www.sec.gov/primary_doc.xml"]          # AAA only; BBB unchanged
    lt._snap = None
    funds = lt.snapshot()["funds"]
    assert funds["AAA"]["source"] == "https://www.sec.gov/new" and funds["AAA"]["period"] == "2026-09-30"
    assert funds["BBB"]["source"] == "https://www.sec.gov/b"               # the bundled one still serves


def test_an_older_stored_row_never_beats_a_newer_bundle(store):
    from cron import refresh_lookthrough as job
    job._store("BBB", {"holdings": 5, "filed": "2026-05-01", "period": "2026-03-31", "source": "https://www.sec.gov/older"})
    lt._snap = None
    assert lt.snapshot()["funds"]["BBB"]["source"] == "https://www.sec.gov/b"


def test_failures_keep_what_was_there_and_only_total_failure_fails(store, monkeypatch):
    from cron import refresh_lookthrough as job

    def boom(series):
        raise OSError("SEC unreachable")
    monkeypatch.setattr(nport, "latest_filing", boom)
    assert job.main() == 1                                                  # every fund failed
    lt._snap = None
    assert lt.snapshot()["funds"]["AAA"]["source"] == "https://www.sec.gov/old"
    monkeypatch.setattr(nport, "latest_filing",
                        lambda s: boom(s) if s == "S1" else ("2026-08-28", "https://www.sec.gov/b"))
    assert job.main() == 0                                                  # one failure among successes


def test_the_job_runs_weekly_in_the_universe_group():
    from cron.run_group import GROUPS
    g = GROUPS["weekly-universe"]
    assert "cron.refresh_lookthrough" in g
    assert g.index("cron.measure_library") < g.index("cron.refresh_lookthrough") < g.index("cron.track_record")
