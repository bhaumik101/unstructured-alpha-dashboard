"""
utils/earnings_awareness.py — "this score is about to be swamped by earnings".

WHY THIS EXISTS
---------------
The Confluence Score reads a macro backdrop that moves over weeks. An earnings
print moves a stock 5–10% in a single session for reasons the macro signals know
nothing about. So a 72 the day before a report is not wrong, it's simply about to
be irrelevant — and a user acting on it is taking an event risk we never told them
about.

Showing the score without that context is a quiet failure of duty: the number
looks equally confident on a calm Tuesday and the night before a print.

This adds a plain warning, not a prediction. We deliberately do NOT forecast the
earnings outcome or adjust the score for it — we just surface the date and let
the user decide. Adjusting the score would mean silently mixing an event model
into a macro model.

Built on utils.fetchers.fetch_earnings_dates (yfinance, cached 6h, returns [] on
failure). Everything here degrades to "no warning" rather than a wrong warning.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

# Windows that change how much weight a macro score deserves.
IMMINENT_DAYS = 3     # inside this, the print dominates almost everything
NEAR_DAYS = 10        # worth knowing before you act
DEFAULT_LOOKAHEAD = 21

RISK_NONE = "none"
RISK_NEAR = "near"
RISK_IMMINENT = "imminent"
RISK_TODAY = "today"


def _today() -> date:
    return datetime.now(timezone.utc).date()


def next_earnings(ticker: str, lookahead_days: int = DEFAULT_LOOKAHEAD) -> dict | None:
    """
    The next UNREPORTED earnings date within `lookahead_days`, or None.

    Returns {date, days_until, risk, label, is_estimate} — `is_estimate` matters
    because yfinance's forward dates are frequently provisional, and presenting a
    provisional date as fact is its own small dishonesty.
    """
    try:
        from utils.fetchers import fetch_earnings_dates
        rows = fetch_earnings_dates(ticker) or []
    except Exception:
        return None

    today = _today()
    upcoming = []
    for r in rows:
        try:
            if r.get("reported"):
                continue                     # already happened
            d = r.get("date")
            if d is None:
                continue
            if hasattr(d, "date") and not isinstance(d, date):
                d = d.date()
            delta = (d - today).days
            if 0 <= delta <= lookahead_days:
                upcoming.append((delta, d))
        except Exception:
            continue

    if not upcoming:
        return None

    days_until, d = min(upcoming, key=lambda x: x[0])
    return {
        "date": d,
        "days_until": days_until,
        "risk": classify_risk(days_until),
        "label": risk_label(days_until),
        # yfinance forward dates are provisional until the company confirms.
        "is_estimate": True,
    }


def classify_risk(days_until: int | None) -> str:
    if days_until is None or days_until < 0:
        return RISK_NONE
    if days_until == 0:
        return RISK_TODAY
    if days_until <= IMMINENT_DAYS:
        return RISK_IMMINENT
    if days_until <= NEAR_DAYS:
        return RISK_NEAR
    return RISK_NONE


def risk_label(days_until: int | None) -> str:
    """Short human phrase. Plain, not alarmist — this is context, not a signal."""
    risk = classify_risk(days_until)
    if risk == RISK_TODAY:
        return "Reports today"
    if risk == RISK_IMMINENT:
        return f"Reports in {days_until}d" if days_until != 1 else "Reports tomorrow"
    if risk == RISK_NEAR:
        return f"Reports in {days_until}d"
    return ""


def caveat_text(days_until: int | None) -> str:
    """One sentence explaining WHY the score deserves less weight right now."""
    risk = classify_risk(days_until)
    if risk in (RISK_TODAY, RISK_IMMINENT):
        return ("An earnings print typically moves the stock far more than the macro "
                "backdrop does — this score carries less weight until it's out.")
    if risk == RISK_NEAR:
        return ("Earnings are close enough that a print could override the macro "
                "setup before it plays out.")
    return ""


def badge_html(info: dict | None) -> str:
    """
    Compact inline badge. Returns "" when there's nothing to say, so callers can
    drop it straight into a template without branching.
    """
    if not info:
        return ""
    risk = info.get("risk", RISK_NONE)
    if risk == RISK_NONE:
        return ""
    color = {"today": "#FF4444", "imminent": "#FF4444", "near": "#F59E0B"}.get(risk, "#8892AA")
    d = info.get("date")
    when = d.strftime("%b %-d") if hasattr(d, "strftime") else str(d or "")
    est = " (est.)" if info.get("is_estimate") else ""
    return (
        f'<span title="Expected {when}{est}" '
        f'style="display:inline-block;font-size:0.58rem;font-weight:700;color:{color};'
        f'background:{color}18;border:1px solid {color}55;border-radius:10px;'
        f'padding:2px 8px;margin-left:8px;white-space:nowrap;">'
        f'⚠ {info.get("label", "")}{est}</span>'
    )
