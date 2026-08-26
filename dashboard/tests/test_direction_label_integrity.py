"""A direction the readers do not recognise corrupts the track record silently.

The schema stores "bull"/"bear". utils.convergence emits events labelled
"bullish"/"bearish" and its two write paths disagreed: render_convergence_events
converted them, log_all_convergence_events -- the scheduled job that logs EVERY
detected event -- passed them through raw.

Nothing validated the value, and every reader compares with ==, so a "bullish"
row failed all three at once:

    _dir_sym         "▲ BULL" if d == "bull" else "▼ BEAR"    -> rendered BEAR
    resolve_pending  (d=="bull" and ret>0) or (d=="bear" and ret<0)
                                                              -> ALWAYS incorrect
    _signed_return   ret if d == "bull" else -ret              -> P&L sign flipped

Observed in production on 2026-08-25: six bullish uranium convergence calls
(URA 67, BWXT 74, UUUU 72, UEC 71, CCJ 71, LEU 67) displayed as bear calls on
the Signal Call Log, every one of which would have scored as wrong when its
4-week window closed.

Nothing had resolved yet when this was found, so no outcome was actually
recorded against a mislabelled row.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import utils.prediction_log as pl  # noqa: E402


# ── normalisation ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", ["bull", "bullish", "BULLISH", " Bull ", "long", "up"])
def test_bullish_labels_normalise_to_bull(raw):
    assert pl.normalize_direction(raw) == "bull"


@pytest.mark.parametrize("raw", ["bear", "bearish", "BEARISH", " Bear ", "short", "down"])
def test_bearish_labels_normalise_to_bear(raw):
    assert pl.normalize_direction(raw) == "bear"


@pytest.mark.parametrize("raw", [None, "", "sideways", "neutral", "???", 5])
def test_an_unrecognised_direction_is_none_not_a_guess(raw):
    """Defaulting to bull would invent a long position on the track record."""
    assert pl.normalize_direction(raw) is None


# ── the readers tolerate rows written before the fix ─────────────────────────

def test_signed_return_reads_a_legacy_bullish_row_as_a_long():
    """The bug that inverted P&L: a winning long counted as a loss."""
    row = {"direction": "bullish", "return_4w": 6.0}
    assert pl._signed_return(row, "return_4w") == 6.0, (
        "a 'bullish' row was treated as a short, flipping the sign of its P&L"
    )


def test_signed_return_still_inverts_a_genuine_bear_call():
    row = {"direction": "bearish", "return_4w": -8.0}
    assert pl._signed_return(row, "return_4w") == 8.0, (
        "a correct short must count as a gain"
    )


# ── the writer refuses what it cannot store ──────────────────────────────────

def test_log_prediction_normalises_before_writing(monkeypatch):
    captured = {}

    class _Conn:
        def execute(self, stmt, *a, **k):
            captured["stmt"] = stmt
            return None
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Engine:
        def begin(self): return _Conn()

    monkeypatch.setattr(pl.db, "engine", _Engine())
    monkeypatch.setattr(pl, "_post_notification", lambda **k: None, raising=False)
    pl.log_prediction(ticker="URA", event_type="convergence",
                      direction="bullish", score=67.0, price=46.07)

    params = captured["stmt"].compile().params
    assert params["direction"] == "bull", (
        f"log_prediction stored {params['direction']!r}; the readers only "
        "understand 'bull'/'bear'"
    )


def test_log_prediction_refuses_an_unrecognised_direction(monkeypatch):
    class _Engine:
        def begin(self):  # pragma: no cover - must never be reached
            raise AssertionError("attempted to write an unrecognised direction")
    monkeypatch.setattr(pl.db, "engine", _Engine())
    assert pl.log_prediction(ticker="X", event_type="convergence",
                             direction="sideways", score=50.0, price=1.0) is False


# ── the writer that caused it ────────────────────────────────────────────────

def test_the_scheduled_logger_converts_the_event_label():
    """log_all_convergence_events passed 'bullish' straight through."""
    source = (_ROOT / "utils" / "convergence.py").read_text(encoding="utf-8")
    assert 'direction=ev["direction"],' not in source, (
        "the scheduled convergence logger is passing the raw 'bullish'/"
        "'bearish' event label into log_prediction again"
    )


def test_both_convergence_write_paths_agree():
    source = (_ROOT / "utils" / "convergence.py").read_text(encoding="utf-8")
    assert source.count('"bull" if ') == 2, (
        "the two convergence write paths must convert the event label the same "
        "way; they disagreed once and the scheduled one was wrong"
    )


# ── repair ───────────────────────────────────────────────────────────────────

def test_repair_rewrites_only_non_canonical_rows(monkeypatch):
    rows = [
        {"id": 1, "direction": "bullish"},
        {"id": 2, "direction": "bull"},
        {"id": 3, "direction": "bearish"},
        {"id": 4, "direction": "sideways"},
    ]
    updated: list = []

    class _Res:
        def mappings(self): return self
        def all(self): return rows
    class _Conn:
        def execute(self, stmt, *a, **k):
            if getattr(stmt, "is_update", False) or "Update" in type(stmt).__name__:
                updated.append(stmt.compile().params.get("direction"))
                return None
            return _Res()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Engine:
        def begin(self): return _Conn()

    monkeypatch.setattr(pl.db, "engine", _Engine())
    fixed = pl.repair_direction_labels()

    assert fixed == 2, f"expected 2 repairs, got {fixed}"
    assert sorted(updated) == ["bear", "bull"]


def test_the_resolver_cron_repairs_before_it_resolves():
    """Order matters: resolving first would score the bad rows wrong."""
    source = (_ROOT / "cron" / "resolve_predictions.py").read_text(encoding="utf-8")
    assert "repair_direction_labels" in source
    assert source.index("repair_direction_labels(") < source.index("resolve_pending("), (
        "the repair must run before resolution, or mislabelled rows are scored "
        "incorrect before they are fixed"
    )


# ── the display path, which is what the user actually sees ───────────────────
# The first fix normalised resolve_pending and _signed_return but NOT the page's
# _dir_sym/_dir_color, so a "bullish" row still rendered as BEAR on the live
# Signal Call Log. Fixing the readers that score a call while leaving the reader
# that DISPLAYS it is the worst split: the number is right and the label is not.

def test_the_feed_normalises_direction_on_the_way_out(monkeypatch):
    rows = [
        {"id": 1, "direction": "bullish", "status": "pending", "ticker": "URA"},
        {"id": 2, "direction": "bear", "status": "pending", "ticker": "HD"},
    ]

    class _Res:
        def mappings(self): return self
        def all(self): return rows
    class _Conn:
        def execute(self, *a, **k): return _Res()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Engine:
        def begin(self): return _Conn()

    monkeypatch.setattr(pl.db, "engine", _Engine())
    feed = pl.get_predictions_feed()
    assert [r["direction"] for r in feed] == ["bull", "bear"], (
        "the feed handed a raw 'bullish' to the page, which renders anything "
        "that is not exactly 'bull' as BEAR"
    )


def test_the_page_normalises_before_choosing_a_label():
    """A source guard: the display helpers must not compare the raw value."""
    page = (_ROOT / "pages" / "30_Track_Record_Live.py").read_text(encoding="utf-8")
    assert 'return "▲ BULL" if direction == "bull" else "▼ BEAR"' not in page, (
        "_dir_sym is comparing the raw direction again; legacy 'bullish' rows "
        "will render as BEAR"
    )
    assert "_norm_dir(direction)" in page


def test_a_bull_filter_still_matches_legacy_rows():
    """Filtering on the canonical value alone dropped every legacy bull row."""
    src = (_ROOT / "utils" / "prediction_log.py").read_text(encoding="utf-8")
    feed = src[src.index("def get_predictions_feed("):]
    assert "_BULL_LABELS" in feed and "in_(aliases)" in feed, (
        "the direction filter matches only the canonical label, so a 'Bull' "
        "filter hides every row written before the repair"
    )


# ── the repair has to be observable, or "check the log" verifies nothing ─────
# 2026-08-26. repair_direction_labels() printed only when it changed a row, and
# so did its caller. A clean table and a repair that never executed therefore
# produced byte-identical logs: silence. #209 shipped 2026-08-25 12:58 UTC, after
# that week's Monday 02:00 UTC resolver run, so the first scheduled run to carry
# the repair had not happened yet -- and would have been unverifiable when it did.

def test_the_resolver_reports_the_repair_count_even_when_it_is_zero():
    source = (_ROOT / "cron" / "resolve_predictions.py").read_text(encoding="utf-8")
    call = source.index("repaired = repair_direction_labels()")
    tail = source[call:call + 400]
    assert 'print(f"[resolve] repaired {repaired}' in tail, (
        "the resolver must report the repair count unconditionally"
    )
    guarded = tail.index("print(") > tail.index("if repaired:") if "if repaired:" in tail else False
    assert not guarded, (
        "the repair count print must not sit behind `if repaired:` -- a zero has "
        "to be distinguishable from the step never running"
    )


def _fake_engine(monkeypatch, rows, updated):
    class _Res:
        def mappings(self): return self
        def all(self): return rows
    class _Conn:
        def execute(self, stmt, *a, **k):
            if "Update" in type(stmt).__name__:
                updated.append(stmt.compile().params.get("direction"))
                return None
            return _Res()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    class _Engine:
        def begin(self): return _Conn()
    monkeypatch.setattr(pl.db, "engine", _Engine())


def test_repair_warns_loudly_when_the_row_cap_truncates_the_scan(monkeypatch, capsys):
    """Rows past `limit` are never examined -- that must not happen silently."""
    rows = [{"id": i, "direction": "bull"} for i in range(5)]
    _fake_engine(monkeypatch, rows, [])
    pl.repair_direction_labels(limit=5)
    out = capsys.readouterr().out
    assert "WARNING" in out and "not checked" in out, (
        f"hitting the cap must warn that rows were skipped; got {out!r}"
    )


def test_repair_is_quiet_when_the_scan_is_complete(monkeypatch, capsys):
    rows = [{"id": i, "direction": "bull"} for i in range(3)]
    _fake_engine(monkeypatch, rows, [])
    assert pl.repair_direction_labels(limit=500) == 0
    assert capsys.readouterr().out == "", "a complete, clean scan should not warn"


def test_repair_scans_in_a_deterministic_order():
    """Without ORDER BY, which rows the cap keeps is up to the database."""
    source = (_ROOT / "utils" / "prediction_log.py").read_text(encoding="utf-8")
    body = source[source.index("def repair_direction_labels"):]
    body = body[:body.index("def resolve_pending")]
    assert "order_by" in body, (
        "the capped select must be ordered, or the rows it examines are "
        "nondeterministic and a mislabelled row can hide behind the cap"
    )
