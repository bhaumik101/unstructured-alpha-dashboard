"""The market adjustment checked against the Fama-French factors
(exposure.ff_check, utils/famafrench.py, cron/refresh_famafrench.py,
report_ui.ff_check_html).

  * Betas are compared on the same weeks, so a gap is about the market measure.
  * Tilts: a portfolio built to load on SMB / HML reads that loading.
  * The library's lag is stated; with too few overlapping weeks nothing shows.
"""

from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine

from utils import db
from utils import exposure as ex
from utils import famafrench as ff
from utils import report_ui as ui


def _world(smb_load: float, hml_load: float, beta: float = 0.9, weeks: int = 150, seed: int = 4):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-11-03", periods=weeks, freq="W-FRI")
    mkt_rf = rng.normal(0.15, 2.0, weeks)
    rf = np.full(weeks, 0.08)
    # like the real factors, SMB moves partly with the market: leaving the market
    # out of the tilt fit would push some of the beta into the size loading
    smb = 0.25 * mkt_rf + rng.normal(0, 1.0, weeks)
    hml = rng.normal(0, 1.0, weeks)
    spy = mkt_rf + rf + rng.normal(0, 0.2, weeks)                  # SPY tracks the market closely
    port = rf + beta * mkt_rf + smb_load * smb + hml_load * hml + rng.normal(0, 0.3, weeks)
    now = pd.DataFrame({"__portfolio__": port, "__mkt__": spy}, index=idx)
    table = pd.DataFrame({"Mkt-RF": mkt_rf, "SMB": smb, "HML": hml, "RF": rf}, index=idx)
    return now, table


def test_tilts_are_read_and_betas_compared_on_the_same_weeks():
    now, table = _world(smb_load=0.6, hml_load=-0.5)
    extras = {"size": {"impact": 0.4, "evidence": "clear"}, "value": {"impact": 0.3, "evidence": "clear"}}
    c = ex.ff_check(now, table, extras)
    assert c["available"] and c["n_obs"] == 150
    assert c["smb"]["evidence"] == "clear" and abs(c["smb"]["impact"] - 0.6) < 0.1
    assert c["hml"]["evidence"] == "clear" and abs(c["hml"]["impact"] + 0.5) < 0.1
    assert c["size_vs_product"] == "same" and c["value_vs_product"] == "opposite"
    # the plain beta includes what SMB carries with the market: 0.9 + 0.6 * 0.25
    assert c["beta_agrees"] and abs(c["beta_ff"] - (0.9 + 0.6 * 0.25)) < 0.1


def test_a_market_proxy_that_drifts_is_called_a_difference():
    now, table = _world(0.0, 0.0)
    now["__mkt__"] = now["__mkt__"] * 1.4                            # a proxy that moves 40% more than the market
    c = ex.ff_check(now, table, None)
    assert not c["beta_agrees"]
    assert "Market beta differs" in ui.ff_check_html({"ff_check": c})


def test_the_beta_tolerance_is_0_05_or_5_percent():
    assert ex.BETA_AGREE == 0.05 and ex.BETA_AGREE_REL == 0.05
    now, table = _world(0.0, 0.0, beta=1.5)
    # a proxy that moves 4% less than the market: its beta reads ~4% higher, a gap of
    # ~0.06 -- over 0.05 but within 5% of 1.5, so it agrees only under the relative rule
    now["__mkt__"] = (table["Mkt-RF"] + table["RF"]) / 1.04
    c = ex.ff_check(now, table, None)
    gap = abs(c["beta_spy"] - c["beta_ff"])
    assert 0.05 < gap < 0.05 * abs(c["beta_ff"]) and c["beta_agrees"]


def test_too_few_overlapping_weeks_show_nothing():
    now, table = _world(0.0, 0.0)
    c = ex.ff_check(now, table.iloc[:40], None)
    assert not c["available"] and "weeks overlap" in c["reason"]
    assert ex.ff_check(now, None, None)["available"] is False
    assert ui.ff_check_html({"ff_check": c}) == ""


def test_the_strip_states_the_lag_and_credits_the_source():
    import re
    now, table = _world(-0.6, 0.0)
    html = ui.ff_check_html({"ff_check": ex.ff_check(now, table, {"size": {"impact": -0.3, "evidence": "clear"}})})
    assert "Market adjustment checks out" in html and "leans to large companies" in html
    assert "published a month or two late" in html and "Fama and French" in html
    assert "Matches the report&#x27;s own reading" in html or "Matches the report's own reading" in html
    from tests.test_exposure import _BANNED
    assert not _BANNED.search(re.sub(r"<[^>]+>", " ", html).replace("it is not a forecast", ""))


def _zip(lines: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("F-F_Research_Data_Factors_weekly.csv", lines)
    return buf.getvalue()


def test_the_library_file_is_parsed_and_the_bundle_loads():
    text = ("This file was created...\n\n,Mkt-RF,SMB,HML,RF\n20131227,  1.00, 0.10, -0.20, 0.00\n"
            "20260918,   -0.22,   -0.16,   -1.98,    0.08\n20260925,    1.02,   -1.18,   -0.78,    0.08\n\nCopyright\n")
    f = ff.parse_zip(_zip(text))
    assert list(f.index.strftime("%Y-%m-%d")) == ["2026-09-18", "2026-09-25"]       # 2013 dropped, footer ignored
    assert f.loc["2026-09-25", "SMB"] == -1.18
    ff._cache = None
    w = ff.weekly()
    assert len(w) > 600 and list(w.columns) == list(ff.COLUMNS)


@pytest.fixture
def store(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ff.db'}")
    db.metadata.create_all(engine, tables=[db.ff_weekly])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    monkeypatch.setattr(ff, "_cache", None)
    monkeypatch.setattr(ff, "_bundled", lambda: {"2026-09-18": [0.1, 0.2, 0.3, 0.08]})
    yield
    ff._cache = None


def test_the_weekly_refresh_stores_and_revised_weeks_win(store, monkeypatch):
    from cron import refresh_famafrench as job
    frame = pd.DataFrame({"Mkt-RF": [-0.22, 1.02], "SMB": [-0.16, -1.18], "HML": [-1.98, -0.78], "RF": [0.08, 0.08]},
                         index=pd.to_datetime(["2026-09-18", "2026-09-25"]))
    monkeypatch.setattr(ff, "parse_zip", lambda data, since="2014-01-01": frame)

    class _R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(job.urllib.request, "urlopen", lambda req, timeout=0: _R(b"zip"))
    assert job.main() == 0
    ff._cache = None
    w = ff.weekly()
    assert w.loc["2026-09-18", "Mkt-RF"] == -0.22                    # the revised week replaces the bundle's
    assert len(w) == 2

    def boom(req, timeout=0):
        raise OSError("down")
    monkeypatch.setattr(job.urllib.request, "urlopen", boom)
    assert job.main() == 1


def test_the_job_runs_weekly_before_track_record():
    from cron.run_group import GROUPS
    g = GROUPS["weekly-universe"]
    assert g.index("cron.measure_library") < g.index("cron.refresh_famafrench") < g.index("cron.track_record")
