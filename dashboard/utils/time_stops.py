"""
utils/time_stops.py — how long a macro thesis should take, and when it's stale.

THE GAP THIS FILLS
------------------
A score of 72 says a case exists. It says nothing about *when* it should show up
in the price, or when you should conclude it didn't. Without that, a call can sit
open forever and be quietly re-justified — which is how conviction becomes
stubbornness. Every signal already carries `lag_weeks` (how far ahead it has
historically led price), so the horizon is derivable today.

WHAT IT IS — AND ISN'T
----------------------
This is an EXPECTED WINDOW derived from configured lead times, not a prediction
and not a stop-loss. `lag_weeks` is a research estimate of a signal's typical
lead, so the honest claim is "signals like these have historically led price by
about N weeks", never "this will resolve by <date>". We say the former.

The central estimate is the MEDIAN, not the mean: lead times run 1–52 weeks with
a couple of long-tail outliers, and one 52-week signal would otherwise drag a
4-week thesis out to a year.

Only the signals actually FORMING the case are counted (the bullish ones behind a
bull call, the bearish ones behind a bear call). Neutral signals aren't part of
the thesis, so including them would blur the window.
"""
from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta, timezone

DEFAULT_LAG_WEEKS = 4.0     # matches the modal signal lead time

# Decay bands, expressed as a fraction of the expected window elapsed.
MATURING_AT = 1.0    # past the expected window — should be showing up by now
DECAYED_AT = 1.5     # well past it — treat the original thesis as stale

STATUS_ACTIVE = "active"
STATUS_MATURING = "maturing"
STATUS_DECAYED = "decayed"

STATUS_LABELS = {
    STATUS_ACTIVE:   "Within expected window",
    STATUS_MATURING: "Past expected window",
    STATUS_DECAYED:  "Signal likely decayed",
}


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _lag_of(signal_id: str) -> float:
    try:
        from utils.config import SIGNALS
        v = SIGNALS.get(signal_id, {}).get("lag_weeks")
        return float(v) if v is not None else DEFAULT_LAG_WEEKS
    except Exception:
        return DEFAULT_LAG_WEEKS


def driving_signal_ids(confluence: dict | None, case: str | None = None) -> list[str]:
    """
    The signals actually forming the case — bullish ones behind a BULL call,
    bearish ones behind a BEAR call. Falls back to whichever side is larger when
    the case is neutral/unknown. Never raises.
    """
    try:
        conf = confluence or {}
        case = (case or conf.get("case") or "").upper()
        bulls = [s.get("id") for s in (conf.get("bull_signals") or []) if s.get("id")]
        bears = [s.get("id") for s in (conf.get("bear_signals") or []) if s.get("id")]
        if case.startswith("BULL"):
            return bulls
        if case.startswith("BEAR"):
            return bears
        return bulls if len(bulls) >= len(bears) else bears
    except Exception:
        return []


def thesis_horizon(signal_ids: list[str] | None, as_of: date | None = None) -> dict:
    """
    Expected window for a thesis built on these signals.

    Returns n, median_weeks, min/max_weeks, expected_by (date), and a label.
    With no signals it returns n=0 and no window rather than inventing one.
    """
    as_of = as_of or _today()
    ids = [s for s in (signal_ids or []) if s]
    if not ids:
        return {
            "n": 0, "median_weeks": None, "min_weeks": None, "max_weeks": None,
            "expected_by": None, "label": "", "note": "",
        }

    lags = [_lag_of(s) for s in ids]
    median_w = float(statistics.median(lags))
    expected_by = as_of + timedelta(weeks=median_w)

    return {
        "n": len(ids),
        "median_weeks": round(median_w, 1),
        "min_weeks": round(min(lags), 1),
        "max_weeks": round(max(lags), 1),
        "expected_by": expected_by,
        "label": f"~{median_w:.0f} weeks (around {expected_by.strftime('%b %-d')})",
        "note": (f"Based on the historical lead times of the {len(ids)} signal(s) "
                 f"forming this case — typically {min(lags):.0f}–{max(lags):.0f} weeks. "
                 "A guide to how long the setup needs, not a forecast or a stop."),
    }


def decay_status(event_date, horizon_weeks: float | None,
                 as_of: date | None = None) -> dict:
    """
    How far through its expected window an existing call is.

    Returns status/label/elapsed_weeks/pct_elapsed. Unknown inputs yield
    STATUS_ACTIVE with pct None — we never claim a call is stale on bad data.
    """
    as_of = as_of or _today()
    out = {
        "status": STATUS_ACTIVE, "label": STATUS_LABELS[STATUS_ACTIVE],
        "elapsed_weeks": None, "pct_elapsed": None, "horizon_weeks": horizon_weeks,
    }
    try:
        if isinstance(event_date, str):
            event_date = datetime.strptime(event_date[:10], "%Y-%m-%d").date()
        elif isinstance(event_date, datetime):
            event_date = event_date.date()
        if not isinstance(event_date, date) or not horizon_weeks or horizon_weeks <= 0:
            return out

        elapsed_weeks = max(0.0, (as_of - event_date).days / 7.0)
        pct = elapsed_weeks / float(horizon_weeks)

        if pct >= DECAYED_AT:
            status = STATUS_DECAYED
        elif pct >= MATURING_AT:
            status = STATUS_MATURING
        else:
            status = STATUS_ACTIVE

        out.update({
            "status": status,
            "label": STATUS_LABELS[status],
            "elapsed_weeks": round(elapsed_weeks, 1),
            "pct_elapsed": round(100 * pct, 0),
        })
        return out
    except Exception:
        return out


def horizon_html(horizon: dict | None) -> str:
    """Compact inline chip for the thesis window. '' when there's nothing to say."""
    if not horizon or not horizon.get("median_weeks"):
        return ""
    return (
        f'<span title="{horizon.get("note", "")}" '
        f'style="display:inline-block;font-size:0.58rem;font-weight:700;color:var(--ua-ink-label);'
        f'background:rgba(var(--ua-label-rgb),0.12);border:1px solid rgba(var(--ua-label-rgb),0.35);'
        f'border-radius:10px;padding:2px 8px;margin-left:8px;white-space:nowrap;">'
        f'⏱ Thesis window {horizon["label"]}</span>'
    )
