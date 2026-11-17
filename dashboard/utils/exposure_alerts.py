# utils/exposure_alerts.py
# Unstructured Alpha — Investor Pro exposure alerts
#
# "Tell me when my portfolio's interest-rate reading falls below -1.0%."
# Checked by the weekly job (cron/send_exposure_weekly.py) after the weekly
# measurement. An alert fires when its reading CROSSES the line -- it was not
# past it at the last check and is now -- so one that stays across does not
# email every week. Setting an alert is consent to alert emails.
#
# RULES
#   * The figure compared is the portfolio's measured typical move for that
#     force, exactly as the report shows it; the email gives its 90% range and
#     evidence label beside it. Nothing is estimated for a missing reading: a
#     force with no reading this week is skipped and its state kept.
#   * Past, not forecast: an alert says a measured reading moved, never that
#     anything will happen or what to do about it.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Tuple

from sqlalchemy import delete, insert, select, update

from utils import db
from utils import exposure as ex

MAX_ALERTS = 10
DIRECTIONS = {"above": "rises above", "below": "falls below"}
FORCES = {f.key: f.label for f in ex.FACTORS}


def past(direction: str, threshold: float, impact: float) -> bool:
    return impact > threshold if direction == "above" else impact < threshold


def describe(alert: dict) -> str:
    """'interest rates falls below −1.0%' -- the alert in words."""
    from utils.report_ui import fmt_pct
    label = ex.lower_label(FORCES.get(alert["factor"], alert["factor"]))
    return f"{label} {DIRECTIONS[alert['direction']]} {fmt_pct(float(alert['threshold']))}"


def evaluate(alerts: List[dict], report: dict) -> Tuple[List[dict], Dict[int, bool]]:
    """(alerts that fired, each with its reading; the new state of every alert
    that had a reading). Pure: nothing is read or written."""
    readings = ((report or {}).get("portfolio") or {}).get("readings") or {}
    fired, states = [], {}
    for a in alerts:
        r = readings.get(a["factor"])
        if not r or r.get("impact") is None:
            continue
        now = past(a["direction"], float(a["threshold"]), float(r["impact"]))
        states[int(a["id"])] = now
        if now and not a.get("last_state"):
            fired.append(dict(a, reading=r))
    return fired, states


def list_alerts(user_id: int) -> List[dict]:
    try:
        with db.engine.begin() as conn:
            rows = conn.execute(select(db.exposure_alerts).where(db.exposure_alerts.c.user_id == int(user_id))
                                .order_by(db.exposure_alerts.c.id)).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []


def add_alert(user_id: int, factor: str, direction: str, threshold: float) -> Tuple[bool, str]:
    if factor not in FORCES or direction not in DIRECTIONS:
        return False, "Pick a force and a direction."
    try:
        threshold = round(float(threshold), 2)
    except (TypeError, ValueError):
        return False, "The threshold must be a number."
    if not -50 <= threshold <= 50:
        return False, "The threshold must be between −50% and +50%."
    if len(list_alerts(user_id)) >= MAX_ALERTS:
        return False, f"Up to {MAX_ALERTS} alerts."
    try:
        with db.engine.begin() as conn:
            conn.execute(insert(db.exposure_alerts).values(
                user_id=int(user_id), factor=factor, direction=direction, threshold=threshold,
                last_state=0, created_at=datetime.now(timezone.utc).isoformat()))
        return True, "Alert added."
    except Exception:
        return False, "Couldn't save the alert right now."


def delete_alert(user_id: int, alert_id: int) -> bool:
    try:
        with db.engine.begin() as conn:
            conn.execute(delete(db.exposure_alerts).where(db.exposure_alerts.c.id == int(alert_id))
                         .where(db.exposure_alerts.c.user_id == int(user_id)))
        return True
    except Exception:
        return False


def save_states(states: Dict[int, bool]) -> None:
    with db.engine.begin() as conn:
        for alert_id, now in states.items():
            conn.execute(update(db.exposure_alerts).where(db.exposure_alerts.c.id == int(alert_id))
                         .values(last_state=1 if now else 0))


def users_with_alerts() -> List[int]:
    try:
        with db.engine.begin() as conn:
            return [int(r[0]) for r in conn.execute(select(db.exposure_alerts.c.user_id).distinct())]
    except Exception:
        return []
