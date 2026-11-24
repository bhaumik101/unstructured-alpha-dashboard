"""Interest rates split by the NY Fed's ACM model (exposure.rates_split,
utils/acm.py, cron/refresh_acm.py, report_ui.rates_split_html).

  * The split re-runs the headline's weekly fit with interest rates swapped
    for its two parts; a portfolio built to answer one part reads that part.
  * Missing data means the split is not shown, never filled.
  * Stored rows from the weekly refresh win over the bundled snapshot.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine

from utils import acm, db
from utils import exposure as ex
from utils import report_ui as ui


def _now(k_exp: float, k_tp: float, weeks: int = 156, seed: int = 3):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2023-11-03", periods=weeks * 5 + 10)
    exp_lvl = pd.Series(np.cumsum(rng.normal(0, 0.03, len(days))), index=days) + 4.0
    tp_lvl = pd.Series(np.cumsum(rng.normal(0, 0.04, len(days))), index=days) + 0.7
    d_exp, d_tp = ex.to_changes(exp_lvl, "diff"), ex.to_changes(tp_lvl, "diff")
    idx = d_exp.index
    mkt = pd.Series(rng.normal(0.1, 2.0, len(idx)), index=idx)
    others = {k: pd.Series(rng.normal(0, 1, len(idx)), index=idx) for k in ("inflation", "dollar", "oil", "credit")}
    port = 0.5 * mkt + k_exp * d_exp / 0.25 + k_tp * d_tp / 0.25 + pd.Series(rng.normal(0, 0.15, len(idx)), index=idx)
    frame = pd.DataFrame({"__portfolio__": port, "__mkt__": mkt, "rates": d_exp + d_tp, **others}).dropna()
    return frame, exp_lvl, tp_lvl


def test_a_term_premium_portfolio_reads_the_term_premium():
    now, e, t = _now(k_exp=0.0, k_tp=-0.6)
    out = ex.rates_split(now, ex.FACTORS, e, t, {"impact": -0.3, "evidence": "clear"})
    assert out["available"] and out["n_obs"] >= ex.MIN_WEEKS
    assert out["term_premium"]["evidence"] == "clear" and out["term_premium"]["impact"] < 0
    assert abs(out["term_premium"]["impact"] + 0.6) < 0.15
    assert out["expected"]["evidence"] not in ("clear", "tentative")
    # rates itself is swapped out, not kept beside its parts (that fit would be singular)
    assert out["term_premium"]["hard_to_separate_from"] is None and out["term_premium"]["vif"] < 5
    html = ui.rates_split_html({"rates_split": out, "portfolio": {"readings": {"rates": dict(
        out["term_premium"], label="Interest rates")}}})
    assert "comes through the term premium" in html


def test_an_expected_path_portfolio_reads_the_expected_path():
    now, e, t = _now(k_exp=-0.5, k_tp=0.0)
    out = ex.rates_split(now, ex.FACTORS, e, t, None)
    assert out["expected"]["evidence"] == "clear" and out["term_premium"]["evidence"] not in ("clear", "tentative")
    assert "comes through the expected path" in ui.rates_split_html({"rates_split": out, "portfolio": {"readings": {}}})


def test_the_other_forces_are_held_fixed_as_in_the_headline():
    # the portfolio answers the dollar only; the dollar moves with the term premium.
    # Holding the dollar fixed, the term premium must read as no link.
    now, e, t = _now(k_exp=0.0, k_tp=0.0, seed=11)
    d_tp = ex.to_changes(t, "diff").reindex(now.index)
    rng = np.random.default_rng(5)
    now["dollar"] = d_tp / 0.04 + rng.normal(0, 0.6, len(now))
    now["__portfolio__"] = 0.5 * now["__mkt__"] - 0.8 * now["dollar"] + rng.normal(0, 0.15, len(now))
    out = ex.rates_split(now, ex.FACTORS, e, t, None)
    assert out["term_premium"]["evidence"] not in ("clear", "tentative")


def test_missing_data_is_not_shown_never_filled():
    now, e, t = _now(k_exp=-0.5, k_tp=-0.5)
    assert ex.rates_split(now, ex.FACTORS, None, t, None)["available"] is False
    assert ex.rates_split(now.drop(columns=["rates"]), ex.FACTORS, e, t, None)["available"] is False
    assert ui.rates_split_html({"rates_split": {"available": False}}) == ""


def test_the_bundle_holds_the_identity_and_the_report_carries_it():
    acm._cache = None
    d = acm.daily()
    assert len(d) > 2000 and list(d.columns) == list(acm.COLUMNS)
    assert float((d.ACMY10 - d.ACMTP10 - d.ACMRNY10).abs().max()) < 1e-5   # the two parts add up to the yield
    import inspect
    src = inspect.getsource(ex.build_exposure_report)
    assert '"rates_split": split' in src and 'acm.series("ACMRNY10")' in src


@pytest.fixture
def store(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'acm.db'}")
    db.metadata.create_all(engine, tables=[db.acm_daily])
    monkeypatch.setattr(db, "engine", engine)
    monkeypatch.setattr(db, "IS_SQLITE", True)
    monkeypatch.setattr(acm, "_cache", None)
    monkeypatch.setattr(acm, "_bundled", lambda: {"2026-11-20": [4.0, 0.7, 3.3], "2026-11-21": [4.1, 0.8, 3.3]})
    yield engine
    acm._cache = None


def test_the_weekly_refresh_stores_new_days_and_they_win(store, monkeypatch):
    from cron import refresh_acm as job
    frame = pd.DataFrame({"ACMY10": [4.2, 4.3], "ACMTP10": [0.9, 1.0], "ACMRNY10": [3.3, 3.3]},
                         index=pd.to_datetime(["2026-11-21", "2026-11-24"]))
    monkeypatch.setattr(acm, "parse_xls", lambda data, since="2014-01-01": frame)

    class _Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(job.urllib.request, "urlopen", lambda req, timeout=0: _Resp(b"xls"))
    assert job.main() == 0
    acm._cache = None
    d = acm.daily()
    assert d.loc["2026-11-21", "ACMTP10"] == 0.9                 # the stored row beats the bundle
    assert d.loc["2026-11-20", "ACMTP10"] == 0.7                 # the bundle still serves older days
    assert str(d.index[-1].date()) == "2026-11-24"


def test_a_failed_download_fails_the_job_and_keeps_what_was_there(store, monkeypatch):
    from cron import refresh_acm as job

    def boom(req, timeout=0):
        raise OSError("NY Fed unreachable")
    monkeypatch.setattr(job.urllib.request, "urlopen", boom)
    assert job.main() == 1
    acm._cache = None
    assert len(acm.daily()) == 2


def test_the_job_runs_weekly_before_track_record():
    from cron.run_group import GROUPS
    g = GROUPS["weekly-universe"]
    assert g.index("cron.measure_library") < g.index("cron.refresh_acm") < g.index("cron.track_record")
