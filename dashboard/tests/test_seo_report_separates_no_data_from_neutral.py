"""The public SEO pages must not report "no data" as a neutral market reading.

A signal can be bullish, bearish or neutral -- or it can have no usable data.
Only the first three are readings. seo/main.py bucketed with a catch-all:

    neut_sigs = [... for sid, st in statuses.items()
                 if st not in ("bullish", "bearish") and sid in SIGNALS]

so `unavailable`, `no_data`, `insufficient_data` and signals with no snapshot row
at all were all published as neutral. Measured on the same fixture, before and
after:

    before   6 bullish, 6 bearish, 35 neutral signals
    after    6 bullish, 6 bearish, 12 neutral, 23 awaiting data of 47 signals

That number reaches Google. It is in the meta description, in the JSON-LD, and
in a "Neutral Signals (N)" table that lists each one BY NAME -- a public claim,
per signal, that the market is neutral on it, when the truth is that the scorer
could not read it.

The dashboard already holds the honest line: utils/regime.py derives
`excluded = total - scored` specifically "so the numbers ALWAYS reconcile to the
advertised SIGNAL_COUNT rather than silently dropping the signals that failed to
load this cycle". The public page reimplemented the same counting, incorrectly.
It now calls that function instead of having an opinion of its own.

The live shape matters for the fix: 44 of 47 signals had a snapshot row, so the
three that mattered were MISSING from `statuses` rather than carrying a non-
reading status. Bucketing over `statuses` would have skipped exactly those, so
the no-data list is keyed on the signal registry instead.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Imported at module scope, exactly as tests/test_track_api.py and
# tests/test_pro_api_unit.py do. Importing it lazily inside the fixture instead
# failed under -n auto with "cannot import name 'category_display' from
# 'utils.taxonomy' (unknown location)": by then sys.path state on that worker
# had drifted and utils/ resolved as a namespace package.
import seo.main as _M  # noqa: E402

_SRC = (_ROOT / "seo" / "main.py").read_text(encoding="utf-8")


# A synthetic registry, so these tests do not depend on the real signal set and
# do not mutate it. The earlier version patched seo.main attributes without
# restoring them and read utils.config.SIGNALS at call time: it passed alone and
# failed under -n auto, which is the signature of a test that owns global state
# it did not create.
_FIXTURE_SIGNALS = {
    f"sig_{i:02d}": {
        "name": f"Fixture Signal {i:02d}",
        "category": "macro",
        "description": "A fixture signal.",
        "lag_weeks": 4,
        "relevant_tickers": [],
    }
    for i in range(12)
}
_FIXTURE_IDS = list(_FIXTURE_SIGNALS)


@pytest.fixture
def render(monkeypatch):
    """Render a page against `statuses`, with every patch auto-restored."""
    from fastapi.testclient import TestClient

    M = _M
    monkeypatch.setattr(M, "_get_config", lambda: ({}, _FIXTURE_SIGNALS))
    monkeypatch.setattr(M, "ACTIVE_SIGNAL_COUNT", len(_FIXTURE_SIGNALS))
    monkeypatch.setattr(M, "_get_engine", lambda: (None, None, None))

    def _render(path: str, statuses: dict[str, str] | None = None, history=None):
        if statuses is not None:
            monkeypatch.setattr(M, "_latest_signal_statuses", lambda e, s: statuses)
        if history is not None:
            monkeypatch.setattr(M, "_signal_history_30d", lambda e, s, sid: history)
        return TestClient(M.app).get(path).text

    return _render


def _buckets(html: str):
    desc = re.search(r'<meta name="description" content="([^"]+)"', html)
    assert desc, "page has no meta description"
    return desc.group(1)


def test_no_catch_all_bucketing_survives_in_the_source():
    """The specific shape that caused this, so it cannot come back quietly."""
    # Comments stripped first: seo/main.py carries a comment quoting the old
    # catch-all to explain why it is gone, and a raw scan fails on the
    # explanation. Third time this file pattern has bitten -- a test that trips
    # over its own rationale is a test someone deletes.
    code = "\n".join(re.sub(r"#.*$", "", line) for line in _SRC.splitlines())
    offenders = [
        code[: m.start()].count("\n") + 1
        for m in re.finditer(r'not\s+in\s+\(\s*"bullish"\s*,\s*"bearish"\s*\)', code)
    ]
    assert not offenders, (
        "seo/main.py buckets statuses with a catch-all at line(s) "
        + ", ".join(map(str, offenders))
        + ' -- "everything that is not bullish or bearish" silently includes '
        "signals with no data. Use _is_reading()."
    )


def test_counts_reconcile_to_the_advertised_signal_total(render):
    """bullish + bearish + neutral + awaiting-data == the number we advertise."""
    # Production shape: most signals scored, a few with no snapshot row at all.
    statuses = {
        sid: ["bullish", "bearish", "neutral"][i % 3]
        for i, sid in enumerate(_FIXTURE_IDS[:-3])
    }
    desc = _buckets(render("/signals/report", statuses))
    nums = re.search(
        r"(\d+) bullish, (\d+) bearish, (\d+) neutral, (\d+) awaiting data "
        r"of (\d+) signals",
        desc,
    )
    assert nums, f"description does not state the four buckets: {desc}"
    bull, bear, neut, na, total = (int(g) for g in nums.groups())

    assert total == len(_FIXTURE_SIGNALS)
    assert bull + bear + neut + na == total, (
        f"{bull}+{bear}+{neut}+{na} != {total} — the page drops signals silently"
    )
    assert na == 3, f"expected the 3 unscored signals to be counted, got {na}"


def test_signals_with_no_row_are_named_rather_than_dropped(render):
    missing = _FIXTURE_IDS[-3:]
    statuses = {sid: "neutral" for sid in _FIXTURE_IDS[:-3]}
    html = render("/signals/report", statuses)

    assert "Awaiting Data" in html, "no section for signals that could not be read"
    absent = [sid for sid in missing if _FIXTURE_SIGNALS[sid]["name"] not in html]
    assert not absent, f"these signals vanished from the report entirely: {absent}"


@pytest.mark.parametrize("status", ["unavailable", "no_data", "insufficient_data"])
def test_a_non_reading_status_is_not_shown_as_neutral(render, status):
    statuses = {sid: "bullish" for sid in _FIXTURE_IDS}
    statuses[_FIXTURE_IDS[0]] = status
    desc = _buckets(render("/signals/report", statuses))
    m = re.search(r"(\d+) neutral, (\d+) awaiting data", desc)
    assert m, desc
    neut, na = int(m.group(1)), int(m.group(2))
    assert neut == 0, f"{status!r} was counted as a neutral reading"
    assert na >= 1, f"{status!r} was not counted as awaiting data"


def test_the_per_signal_page_does_not_invent_a_reading(render):
    """"<name> is currently neutral." was published for signals with no data."""
    html = render(
        f"/signal/{_FIXTURE_IDS[0]}",
        history=[{"status": "unavailable", "score": 0.0,
                  "snapshot_date": "2026-08-19"}],
    )
    desc = _buckets(html)

    assert "is currently neutral" not in desc, (
        "the page claims a neutral reading for a signal whose data is "
        f"unavailable: {desc[:120]}"
    )
    assert "no current reading" in desc, f"expected an honest lede, got: {desc[:120]}"
