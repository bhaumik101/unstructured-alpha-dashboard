"""Tests for the zoom-aware price chart.

The headline case is the window-slicing bug the old chart shipped with: period
constants were calendar days but were applied positionally, so "1Y" selected 370
*bars*. On a ~252-session year that is ~17.6 months. These tests build a series
on a realistic weekday calendar and assert the returned span matches the label.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from utils.price_chart import (
    DEFAULT_PERIOD,
    PERIODS,
    ChartPayload,
    build_html,
    build_payload,
    slice_period,
    window_start,
    window_stats,
)


@pytest.fixture
def series() -> pd.Series:
    """Six years of weekday closes ending on a fixed date.

    Business-day frequency approximates a trading calendar closely enough for
    span assertions (it omits holidays, which only makes the test stricter).
    """
    idx = pd.bdate_range(end="2026-07-17", periods=6 * 252)
    rng = np.random.default_rng(7)
    walk = 50 + np.cumsum(rng.normal(0.05, 1.0, len(idx)))
    return pd.Series(np.abs(walk) + 5.0, index=idx)


# ── The bug ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "period,expected_days,tol",
    [
        ("1M", 31, 4),
        ("3M", 92, 5),
        ("6M", 183, 6),
        ("1Y", 365, 5),
        ("2Y", 730, 6),
        ("5Y", 1826, 8),
    ],
)
def test_window_spans_match_their_labels(series, period, expected_days, tol):
    """The visible span must equal the advertised calendar period.

    Under the old positional slicing, "1Y" returned 370 bars spanning ~536 days
    — this assertion fails by ~170 days against that implementation.
    """
    view = slice_period(series, period)
    span = (view.index[-1] - view.index[0]).days
    assert abs(span - expected_days) <= tol, (
        f"{period} spans {span} days, expected ~{expected_days}"
    )


def test_one_year_is_not_confused_with_370_bars(series):
    """Pin the exact confusion, so a revert is unmistakable."""
    view = slice_period(series, "1Y")
    assert 240 <= len(view) <= 262, (
        f"1Y should hold roughly one year of sessions, got {len(view)} bars; "
        "370 bars would mean calendar days were applied as row counts again"
    )


def test_ytd_starts_on_january_first(series):
    view = slice_period(series, "YTD")
    assert view.index[0].year == series.index[-1].year
    assert view.index[0].month == 1


def test_all_returns_everything(series):
    assert slice_period(series, "ALL").equals(series)


def test_unknown_period_is_rejected(series):
    with pytest.raises(KeyError):
        window_start(series.index[-1], "17M")


def test_window_shorter_than_history_degrades_to_full_series():
    """A newly listed name has no 1Y of data; show what exists, not nothing."""
    idx = pd.bdate_range(end="2026-07-17", periods=6)
    s = pd.Series(range(6), index=idx, dtype=float)
    assert len(slice_period(s, "1Y")) == 6


def test_empty_series_is_safe():
    assert slice_period(pd.Series(dtype=float), "1Y").empty


# ── Window statistics ─────────────────────────────────────────────────────────

def test_window_stats_describe_the_window_not_a_fixed_lookback():
    s = pd.Series([10.0, 20.0, 5.0, 15.0], index=pd.bdate_range("2026-01-01", periods=4))
    st = window_stats(s)
    assert st["first"] == 10.0
    assert st["last"] == 15.0
    assert st["high"] == 20.0
    assert st["low"] == 5.0
    assert st["change"] == pytest.approx(5.0)
    assert st["change_pct"] == pytest.approx(50.0)
    assert st["n"] == 4


def test_window_stats_on_empty():
    st = window_stats(pd.Series(dtype=float))
    assert st["n"] == 0 and st["last"] is None


# ── Payload ───────────────────────────────────────────────────────────────────

def test_payload_is_json_safe_with_nan(series):
    """NaN must become null, not crash json.dumps or plot as zero.

    Rolling means are NaN for their first N-1 rows; if those leaked through as
    0.0 the MA would dive to the bottom of the chart.
    """
    p = build_payload("CCJ", series, "2Y")
    blob = p.to_json()  # allow_nan=False -> raises if a NaN survived
    parsed = json.loads(blob)
    assert None not in parsed["close"], "close prices should have no gaps here"
    assert len(parsed["dates"]) == len(parsed["close"])


def test_moving_averages_are_trimmed_not_recomputed(series):
    """The first visible MA point must be a true 200-day average.

    Computing the MA on the trimmed window instead would make the first point an
    average of one bar, producing a hook at the left edge.
    """
    p = build_payload("CCJ", series, "1Y")
    assert p.ma200, "200-day MA expected on a 1Y window"
    full_ma = series.rolling(200).mean()
    view_idx = slice_period(series, "1Y").index
    expected_first = float(full_ma.reindex(view_idx).iloc[0])
    assert p.ma200[0] == pytest.approx(expected_first)


def test_short_windows_suppress_the_200_day_ma(series):
    """A 200-day MA across one month is a flat line carrying no information."""
    assert not build_payload("CCJ", series, "1M").ma200


def test_long_windows_include_both_mas(series):
    p = build_payload("CCJ", series, "2Y")
    assert p.ma50 and p.ma200


def test_sparse_score_history_is_dropped(series):
    """One or two snapshots on a multi-year axis read as a broken series."""
    hist = [{"snapshot_date": "2026-07-16", "score": 55.0}]
    assert not build_payload("CCJ", series, "1Y", score_history=hist).score_dates


def test_score_history_outside_the_window_is_dropped(series):
    hist = [{"snapshot_date": f"2019-0{m}-01", "score": 50.0} for m in (1, 2, 3)]
    assert not build_payload("CCJ", series, "1Y", score_history=hist).score_dates


def test_score_history_inside_the_window_is_kept(series):
    hist = [{"snapshot_date": d, "score": v}
            for d, v in [("2026-05-01", 40.0), ("2026-06-01", 55.0), ("2026-07-01", 61.0)]]
    p = build_payload("CCJ", series, "1Y", score_history=hist)
    assert p.score_dates == ["2026-05-01", "2026-06-01", "2026-07-01"]
    assert p.score_values == [40.0, 55.0, 61.0]


def test_malformed_score_rows_are_skipped(series):
    hist = [
        {"snapshot_date": "2026-05-01", "score": 40.0},
        {"snapshot_date": "not-a-date", "score": 1.0},
        {"score": 2.0},
        {"snapshot_date": "2026-06-01", "score": "oops"},
        {"snapshot_date": "2026-06-15", "score": 58.0},
    ]
    p = build_payload("CCJ", series, "1Y", score_history=hist)
    assert p.score_dates == ["2026-05-01", "2026-06-15"]


@pytest.mark.parametrize(
    "reported,surprise,expected_colour",
    [
        (False, None, "#F59E0B"),
        (True, None, "#6B7FBF"),
        (True, 12.0, "#00D566"),
        (True, -8.0, "#FF4444"),
    ],
)
def test_earnings_marker_colours(series, reported, surprise, expected_colour):
    e = [{"date": "2026-06-01", "reported": reported, "surprise_pct": surprise}]
    p = build_payload("CCJ", series, "1Y", earnings=e)
    assert p.earnings[0]["color"] == expected_colour


def test_earnings_outside_the_window_are_dropped(series):
    e = [{"date": "2019-01-01", "reported": True, "surprise_pct": 5.0}]
    assert not build_payload("CCJ", series, "1Y", earnings=e).earnings


def test_upcoming_earnings_just_past_the_window_are_kept(series):
    """The next print is context even though it is right of the last bar."""
    e = [{"date": "2026-08-10", "reported": False, "surprise_pct": None}]
    assert build_payload("CCJ", series, "1Y", earnings=e).earnings


def test_empty_series_yields_empty_payload():
    p = build_payload("CCJ", pd.Series(dtype=float), "1Y")
    assert p.dates == [] and p.close == []
    json.loads(p.to_json())


# ── HTML ──────────────────────────────────────────────────────────────────────

def test_html_embeds_payload_and_is_self_contained(series):
    html = build_html(build_payload("CCJ", series, "1Y"))
    assert "plotly" in html.lower()
    assert "plotly_relayout" in html, "zoom handler missing — y would not refit"
    assert "CCJ" in html


def test_html_hides_score_axis_when_there_is_no_score_history(series):
    html = build_html(build_payload("CCJ", series, "1Y"))
    assert "visible: false" in html


def test_html_shows_score_axis_when_history_exists(series):
    hist = [{"snapshot_date": d, "score": 50.0}
            for d in ("2026-05-01", "2026-06-01", "2026-07-01")]
    html = build_html(build_payload("CCJ", series, "1Y", score_history=hist))
    assert "visible: true" in html


def test_html_uses_linear_not_spline(series):
    """Splining daily closes draws prices that never traded."""
    html = build_html(build_payload("CCJ", series, "1Y"))
    assert "shape: 'linear'" in html
    # Check the trace configuration, not the whole document: the word "spline"
    # legitimately appears in the comment explaining why it is not used.
    code = "\n".join(
        ln for ln in html.splitlines() if not ln.strip().startswith("//")
    )
    assert "shape: 'spline'" not in code
    assert "smoothing" not in code


def test_html_escapes_nothing_dangerous_from_ticker(series):
    """Ticker text reaches the page via JSON, so quotes must not break out."""
    html = build_html(build_payload('X");alert(1)//', series, "1Y"))
    assert 'alert(1)' not in html.split('var D = ')[1].split('\n')[0].replace('\\"', '') \
        or '\\"' in html
    # The important invariant: the payload line is valid JSON.
    blob = html.split("var D = ")[1].split(";\n")[0]
    json.loads(blob)


def test_every_declared_period_builds(series):
    for period in PERIODS:
        html = build_html(build_payload("CCJ", series, period))
        assert "ua-chart" in html


def test_default_period_is_declared():
    assert DEFAULT_PERIOD in PERIODS
