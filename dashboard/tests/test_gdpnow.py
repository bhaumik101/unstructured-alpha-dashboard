"""The Atlanta Fed's GDPNow estimate, shown as context on "What changed"."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd
import pytest

from utils import gdpnow as g
from utils import report_ui as ui

ROOT = Path(__file__).resolve().parent.parent


def _alfred(vintages: dict) -> str:
    """ALFRED's CSV shape: one column per vintage, named GDPNOW_YYYYMMDD."""
    quarters = sorted({q for col in vintages.values() for q in col})
    head = "observation_date," + ",".join(f"GDPNOW_{d.replace('-', '')}" for d in vintages)
    rows = [q + "," + ",".join("" if col.get(q) is None else str(col[q]) for col in vintages.values())
            for q in quarters]
    return "\n".join([head, *rows]) + "\n"


def test_alfred_columns_become_vintage_dates():
    frame = g.parse_alfred(_alfred({"2026-11-17": {"2026-07-01": 3.27, "2026-10-01": 3.38},
                                    "2026-11-18": {"2026-07-01": 3.27, "2026-10-01": 3.21}}))
    assert list(frame.columns) == [pd.Timestamp("2026-11-17"), pd.Timestamp("2026-11-18")]
    assert frame.loc[pd.Timestamp("2026-10-01"), pd.Timestamp("2026-11-18")] == 3.21


def _vintages(days: dict) -> pd.DataFrame:
    return g.parse_alfred(_alfred(days))


def test_the_path_keeps_only_updates_and_dates_the_latest_exactly():
    v = _vintages({
        "2026-10-24": {"2026-07-01": 3.5},                       # before Q4 existed
        "2026-10-31": {"2026-07-01": 3.27, "2026-10-01": 3.22},
        "2026-11-07": {"2026-07-01": 3.27, "2026-10-01": 3.44},
        "2026-11-17": {"2026-07-01": 3.27, "2026-10-01": 3.38},
        "2026-11-18": {"2026-07-01": 3.27, "2026-10-01": 3.21},
        "2026-11-19": {"2026-07-01": 3.27, "2026-10-01": 3.21},  # no change: not an update
        "2026-11-20": {"2026-07-01": 3.27, "2026-10-01": 3.21},
    })
    est = g.estimate_path(v)
    assert est["quarter"] == "2026-10-01" and est["label"] == "Oct–Dec 2026" and est["short"] == "Q4 2026"
    assert [p["value"] for p in est["path"]] == [3.22, 3.44, 3.38, 3.21]
    assert est["value"] == 3.21
    assert est["updated"] == "2026-11-18"          # the vintage before it is the day before
    assert est["checked"] == "2026-11-20"


def test_an_update_after_a_gap_is_not_given_a_date_it_cannot_prove():
    v = _vintages({"2026-11-01": {"2026-10-01": 3.0}, "2026-11-08": {"2026-10-01": 3.4}})
    est = g.estimate_path(v)
    assert est["value"] == 3.4 and est["updated"] is None   # it changed somewhere in Nov 2-8


def test_a_vintage_alfred_does_not_have_yet_is_ignored():
    v = _vintages({"2026-11-18": {"2026-10-01": 3.2}, "2026-11-19": {"2026-10-01": 3.21},
                   "2026-11-25": {"2026-10-01": None}})
    est = g.estimate_path(v)
    assert est and est["value"] == 3.21 and est["updated"] == "2026-11-19"


def test_the_record_pairs_completed_quarters_and_leaves_out_the_current_one():
    q = pd.to_datetime(["2025-10-01", "2026-01-01", "2026-04-01", "2026-07-01", "2026-10-01"])
    final = pd.Series([4.24, 1.24, 1.54, 3.27, 3.21], q)
    bea = pd.Series([0.2, 2.5, 2.2, 3.4], q[:4])
    t = g.track_record(final, bea, before="2026-10-01", n=3)
    assert [r["short"] for r in t["rows"]] == ["Q1 2026", "Q2 2026", "Q3 2026"]
    assert t["mean_miss"] == pytest.approx((1.26 + 0.66 + 0.13) / 3, abs=0.01)
    full = g.track_record(final, bea, before="2026-10-01")
    assert full["n"] == 4 and all(r["quarter"] < "2026-10-01" for r in full["rows"])
    # Even if BEA already has a figure, the quarter still being estimated is not scored.
    bea_ahead = pd.concat([bea, pd.Series([1.0], q[4:])])
    assert g.track_record(final, bea_ahead, before="2026-10-01")["n"] == 4


def test_vintage_requests_stay_within_alfreds_limit_and_cover_the_last_days():
    batches = g.vintage_dates(dt.date(2026, 11, 25))
    assert all(len(b) <= g.MAX_VINTAGES for b in batches)
    recent = batches[-1]
    assert recent[-1] == dt.date(2026, 11, 25)
    assert all((b - a).days == 1 for a, b in zip(recent, recent[1:]))


def _fake_get(fail_bea: bool = False, fail_all: bool = False):
    def get(url: str) -> str:
        if fail_all:
            raise ConnectionError("down")
        if "alfredgraph" in url:
            dates = url.split("vintage_date=")[1].split(",")
            return _alfred({d: ({"2026-07-01": 3.27, "2026-10-01": 3.21} if d >= "2026-11-01" else {"2026-07-01": 3.6})
                            for d in dates})
        if g.BEA_SERIES in url:
            if fail_bea:
                raise ConnectionError("bea down")
            return "observation_date,X\n2026-04-01,2.2\n2026-07-01,3.4\n"
        return "observation_date,GDPNOW\n2026-04-01,1.54\n2026-07-01,3.27\n2026-10-01,3.21\n"
    return get


def test_context_is_built_from_the_downloads():
    c = g.build_context(_fake_get(), today=dt.date(2026, 11, 25))
    assert c["available"] and c["value"] == 3.21 and c["short"] == "Q4 2026"
    assert [r["short"] for r in c["track"]["rows"]] == ["Q2 2026", "Q3 2026"]


def test_a_failed_download_shows_nothing_and_a_failed_record_is_left_out():
    down = g.build_context(_fake_get(fail_all=True), today=dt.date(2026, 11, 25))
    assert down["available"] is False and "failed" in down["reason"]
    assert ui.gdpnow_html(down) == ""
    no_bea = g.build_context(_fake_get(fail_bea=True), today=dt.date(2026, 11, 25))
    assert no_bea["available"] and no_bea["track"] == {}
    assert "Their record" not in ui.gdpnow_html(no_bea)


def test_a_failure_is_retried_after_minutes_not_hours(monkeypatch):
    calls = []
    monkeypatch.setattr(g, "build_context", lambda: calls.append(1) or {"available": False, "reason": "x"})
    monkeypatch.setattr(g, "_cache", None)
    g.context()
    monkeypatch.setattr(g, "_cache_at", g._cache_at - g._TTL_FAIL - 1)
    g.context()
    assert len(calls) == 2


_BANNED = re.compile(r"\b(will|predict\w*|forecast\w*|expect(?!ations)\w*|should|buy|sell|recommend\w*)\b", re.I)


def test_the_panel_labels_it_as_theirs_and_context_only():
    c = g.build_context(_fake_get(), today=dt.date(2026, 11, 25))
    html = ui.gdpnow_html(c)
    assert "Their estimate, not ours" in html and "+3.2%" in html
    assert "does not feed any reading" in html
    assert "GDPNow, final estimate" in html and "BEA, current figure" in html     # a legend, not colour alone
    text = re.sub(r"<[^>]+>", " ", html).replace("not an official forecast", "")
    assert not _BANNED.search(text), _BANNED.search(text)


def test_it_is_context_never_a_signal():
    for path in (ROOT / "utils").glob("*.py"):
        if path.name in ("gdpnow.py", "report_ui.py"):
            continue
        assert "gdpnow" not in path.read_text(encoding="utf-8").lower(), path.name
    page = (ROOT / "pages" / "61_What_Changed.py").read_text(encoding="utf-8")
    assert "gdpnow.context()" in page and "ui.gdpnow_html(" in page
