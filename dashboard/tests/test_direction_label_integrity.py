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
