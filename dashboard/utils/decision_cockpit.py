"""Pure assembly and presentation helpers for the personalized daily cockpit.

The cockpit composes persisted portfolio scores, the existing Decision Queue,
private thesis state, and freshness metadata. It never fetches market data,
recalculates a score, or substitutes a synthetic value.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
from typing import Any, Iterable


CURRENT_DAYS = 2
STALE_DAYS = 7


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _guided_reason(item: dict) -> str:
    trigger = ((item.get("triggers") or [{}])[0]).get("kind")
    messages = {
        "earnings": "A company update is close enough to overwhelm the slower-moving macro backdrop.",
        "score_move": "The recorded backdrop changed enough this week to deserve a fresh review.",
        "thesis_conflict": "Your saved thesis and the latest recorded evidence now point in opposite directions.",
        "thesis_due": "The review date you set for this thesis has arrived.",
        "concentration": "This position is large enough to have an outsized effect on the portfolio.",
        "coverage_gap": "This holding has no trustworthy recorded full score yet, so the system will not estimate one.",
        "stale_evidence": "The latest recorded evidence is too old to treat as current.",
    }
    if trigger in messages:
        return messages[trigger]
    status = str(item.get("status_label") or item.get("status") or "")
    if status == "Changed":
        return "A relevant signal changed and this holding is directly exposed to it."
    if status == "Strong backdrop":
        return "The latest recorded score is outside the neutral range."
    if status == "Profile divergence":
        return "Your investing preferences produce a meaningfully different read from the standard score."
    return "No urgent exception is recorded, but this is one of the portfolio's highest-priority names to monitor."


def _freshness(evidence: Iterable[dict], *, today: date) -> dict:
    current = aging = stale = unavailable = 0
    dates: list[date] = []
    for row in evidence or []:
        snapshot = row.get("snapshot") or {}
        snapshot_day = _as_date(snapshot.get("snapshot_date"))
        score_kind = snapshot.get("score_kind")
        has_full_score = snapshot.get("score") is not None and score_kind in (None, "full")
        if not snapshot_day or not has_full_score:
            unavailable += 1
            continue
        dates.append(snapshot_day)
        age = max(0, (today - snapshot_day).days)
        if age <= CURRENT_DAYS:
            current += 1
        elif age <= STALE_DAYS:
            aging += 1
        else:
            stale += 1

    total = current + aging + stale + unavailable
    if total == 0 or unavailable == total:
        state, label = "unavailable", "Evidence unavailable"
    elif stale or unavailable:
        state, label = "partial", "Partial recorded coverage"
    elif aging:
        state, label = "aging", "Recorded evidence is aging"
    else:
        state, label = "current", "Current recorded evidence"
    return {
        "state": state,
        "label": label,
        "current": current,
        "aging": aging,
        "stale": stale,
        "unavailable": unavailable,
        "total": total,
        "newest": max(dates).isoformat() if dates else None,
        "oldest": min(dates).isoformat() if dates else None,
    }


def _queue_attention(item: dict) -> dict:
    triggers = [dict(row) for row in (item.get("triggers") or [])]
    return {
        "origin": "queue",
        "ticker": str(item.get("ticker") or "").upper(),
        "severity": str(item.get("severity") or "review"),
        "priority": float(item.get("priority") or 0),
        "headline": str(item.get("headline") or "Review recorded evidence"),
        "guided_reason": _guided_reason(item),
        "professional_reason": str(item.get("why_now") or ""),
        "next_action": str(item.get("next_action") or "Review the source evidence"),
        "route": str(item.get("route") or "ticker"),
        "score": item.get("score"),
        "weight_pct": float(item.get("weight_pct") or 0),
        "snapshot_date": item.get("snapshot_date"),
        "triggers": triggers,
        "evidence_hash": item.get("evidence_hash"),
        "status": item.get("status") or "open",
    }


def _brief_attention(item: dict) -> dict:
    normalized = {
        "origin": "priority",
        "ticker": str(item.get("ticker") or "").upper(),
        "severity": "monitor",
        "priority": float(item.get("priority_score") or 0),
        "headline": str(item.get("status") or "Monitor"),
        "professional_reason": str(item.get("reason") or ""),
        "next_action": "Review the latest ticker evidence",
        "route": "ticker",
        "score": item.get("personal_score"),
        "weight_pct": float(item.get("weight_pct") or 0),
        "snapshot_date": item.get("snapshot_date"),
        "triggers": [],
        "evidence_hash": None,
        "status": "monitor",
        "status_label": item.get("status"),
    }
    normalized["guided_reason"] = _guided_reason(normalized)
    return normalized


def build_decision_cockpit(
    evidence: list[dict],
    *,
    priority_brief: dict,
    queue_items: Iterable[dict] = (),
    theses: Iterable[dict] = (),
    today: date | None = None,
) -> dict:
    """Compose one bounded daily workflow from existing recorded evidence."""
    day = today or datetime.now(timezone.utc).date()
    queue = [dict(row) for row in queue_items or []]
    open_queue = [row for row in queue if row.get("status") == "open"]
    watching = [row for row in queue if row.get("status") in {"watching", "snoozed"}]

    attention = [_queue_attention(row) for row in open_queue]
    seen = {row["ticker"] for row in attention}
    for row in priority_brief.get("priorities") or []:
        ticker = str(row.get("ticker") or "").upper()
        if ticker and ticker not in seen:
            attention.append(_brief_attention(row))
            seen.add(ticker)
        if len(attention) >= 3:
            break
    attention.sort(key=lambda row: (-row["priority"], row["ticker"]))

    priorities = list(priority_brief.get("priorities") or [])
    # Only rank rows that actually carry a score. Defaulting a missing score to
    # 0 (for max) and 100 (for min) silently ranks unscored holdings as both the
    # worst and the best, which is how an unscored name could surface as
    # "most challenged" without any evidence behind it.
    _scored = [row for row in priorities if row.get("personal_score") is not None]
    strongest = max(_scored, key=lambda row: row.get("personal_score"), default=None)
    challenged = min(_scored, key=lambda row: row.get("personal_score"), default=None)
    # With a single scored holding, max and min are the same row, so the UI would
    # show one ticker as simultaneously the strongest and the most challenged.
    # A contrast needs two sides; below that, report only the strongest.
    if len(_scored) < 2:
        challenged = None
    largest = max(
        evidence or [],
        key=lambda row: float(row.get("weight_pct") or 0),
        default=None,
    )

    active_theses = [
        dict(row) for row in theses or []
        if str(row.get("status") or "").lower() == "active"
    ]
    trigger_kinds = {
        trigger.get("kind")
        for row in open_queue
        for trigger in (row.get("triggers") or [])
    }
    freshness = _freshness(evidence, today=day)
    urgent = sum(row.get("severity") == "urgent" for row in open_queue)

    if urgent:
        headline = f"{urgent} urgent review item{'s' if urgent != 1 else ''}"
    elif open_queue:
        headline = f"{len(open_queue)} item{'s' if len(open_queue) != 1 else ''} need review"
    elif attention:
        headline = "No urgent exceptions — monitor the leading priorities"
    else:
        headline = "Add holdings to activate your daily cockpit"

    return {
        "headline": headline,
        "attention": attention[:3],
        "queue": {
            "open": len(open_queue),
            "urgent": urgent,
            "watching": len(watching),
            "completed": sum(row.get("status") == "done" for row in queue),
        },
        "portfolio": {
            "source": priority_brief.get("source") or "portfolio",
            "weighted_score": priority_brief.get("weighted_personal_score"),
            "covered_weight_pct": min(float(priority_brief.get("scored_weight_pct") or 0), 100.0),
            "n_scored": int(priority_brief.get("n_evidence") or 0),
            # `or` would treat a genuine 0 as missing and substitute the
            # evidence count, reporting holdings the brief says it doesn't have.
            "n_total": int(
                priority_brief["n_total"]
                if priority_brief.get("n_total") is not None
                else len(evidence or [])
            ),
            "material_changes": int(priority_brief.get("material_changes") or 0),
            "strongest": strongest,
            "challenged": challenged,
            "largest": {
                "ticker": str(largest.get("ticker") or "").upper(),
                "weight_pct": float(largest.get("weight_pct") or 0),
            } if largest else None,
        },
        "theses": {
            "active": len(active_theses),
            "conflicts": int("thesis_conflict" in trigger_kinds),
            "due": int("thesis_due" in trigger_kinds),
        },
        "freshness": freshness,
        "as_of": freshness.get("newest"),
        "no_synthetic": True,
    }


def render_cockpit_summary_html(payload: dict, *, mode: str = "Guided") -> str:
    """Render the bounded cockpit hero; all user-derived strings are escaped."""
    queue = payload.get("queue") or {}
    portfolio = payload.get("portfolio") or {}
    freshness = payload.get("freshness") or {}
    score = portfolio.get("weighted_score")
    score_text = f"{float(score):.0f}" if score is not None else "—"
    coverage = float(portfolio.get("covered_weight_pct") or 0)
    mode_copy = (
        "Start with the exceptions. Open the evidence only when something requires a decision."
        if mode == "Guided"
        else "Priority combines recorded score movement, event risk, thesis conflicts, evidence age, and portfolio weight."
    )
    return (
        '<div style="background:linear-gradient(145deg,var(--ua-panel),var(--ua-bg-card));'
        'border:1px solid var(--ua-panel-line);border-left:3px solid var(--ua-royal);'
        'border-radius:14px;padding:20px 22px;margin-bottom:14px;">'
        '<div style="font-size:.62rem;color:var(--ua-royal);font-weight:800;'
        'letter-spacing:.13em;text-transform:uppercase;">Personalized decision cockpit</div>'
        f'<div style="font-size:1.42rem;color:var(--ua-ink);font-weight:780;margin-top:5px;">'
        f'{escape(str(payload.get("headline") or ""))}</div>'
        f'<div style="font-size:.78rem;color:var(--ua-ink-mut);line-height:1.55;margin-top:7px;">'
        f'{escape(mode_copy)}</div>'
        '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:15px;">'
        f'<span class="ua-pill">Needs review&nbsp; {int(queue.get("open") or 0)}</span>'
        f'<span class="ua-pill">Weighted score&nbsp; {score_text}</span>'
        f'<span class="ua-pill">Coverage&nbsp; {coverage:.0f}%</span>'
        f'<span class="ua-pill">{escape(str(freshness.get("label") or "Evidence unavailable"))}</span>'
        '</div></div>'
    )


def render_attention_card_html(item: dict, rank: int, *, mode: str = "Guided") -> str:
    """Render one priority card with novice copy or professional evidence copy."""
    severity = str(item.get("severity") or "review")
    accent = {
        "urgent": "var(--ua-red)",
        "high": "var(--ua-amber)",
        "review": "var(--ua-cyan)",
        "monitor": "var(--ua-royal)",
    }.get(severity, "var(--ua-royal)")
    reason = (
        item.get("guided_reason")
        if mode == "Guided"
        else item.get("professional_reason")
    )
    score = item.get("score")
    score_text = f"{float(score):.0f}" if score is not None else "N/A"
    evidence_line = (
        f"Recorded {item.get('snapshot_date') or 'unavailable'}"
        f" · {float(item.get('weight_pct') or 0):.1f}% portfolio weight"
    )
    return (
        f'<div style="background:var(--ua-panel);border:1px solid var(--ua-panel-line);'
        f'border-top:2px solid {accent};border-radius:11px;padding:16px 17px;height:100%;">'
        '<div style="display:flex;justify-content:space-between;gap:12px;">'
        f'<div><div style="font-size:.60rem;color:{accent};font-weight:800;'
        f'letter-spacing:.11em;text-transform:uppercase;">Priority {int(rank)} · {escape(severity)}</div>'
        f'<div style="font-size:1.08rem;color:var(--ua-ink);font-weight:760;margin-top:5px;">'
        f'{escape(str(item.get("ticker") or ""))} · {escape(str(item.get("headline") or ""))}</div></div>'
        f'<div style="font-size:1.35rem;color:var(--ua-ink);font-weight:780;">{score_text}</div></div>'
        f'<div style="font-size:.79rem;color:var(--ua-ink-soft);line-height:1.55;margin-top:11px;">'
        f'{escape(str(reason or ""))}</div>'
        f'<div style="font-size:.66rem;color:var(--ua-ink-mut);border-top:1px solid var(--ua-hair);'
        f'margin-top:12px;padding-top:9px;">{escape(evidence_line)}</div></div>'
    )


def render_portfolio_impact_html(payload: dict, *, mode: str = "Guided") -> str:
    portfolio = payload.get("portfolio") or {}
    strongest = portfolio.get("strongest") or {}
    challenged = portfolio.get("challenged") or {}
    largest = portfolio.get("largest") or {}
    if mode == "Guided":
        intro = "These are the holdings most likely to shape how the portfolio feels if the backdrop strengthens or weakens."
    else:
        intro = "Personalized score extremes and saved weights are shown directly; unavailable holdings are excluded from aggregation."

    def _holding(row: dict, fallback: str) -> str:
        if not row:
            return fallback
        return f'{row.get("ticker", "—")} · {float(row.get("personal_score") or 0):.0f}/100'

    largest_text = (
        f'{largest.get("ticker")} · {float(largest.get("weight_pct") or 0):.1f}%'
        if largest else "Not saved"
    )
    return (
        '<div style="background:var(--ua-panel);border:1px solid var(--ua-panel-line);'
        'border-radius:12px;padding:18px 20px;">'
        '<div style="font-size:.64rem;color:var(--ua-ink-label);font-weight:800;'
        'letter-spacing:.11em;text-transform:uppercase;">Portfolio impact</div>'
        f'<div style="font-size:.78rem;color:var(--ua-ink-mut);line-height:1.5;margin:6px 0 14px;">'
        f'{escape(intro)}</div>'
        '<div class="ua-cockpit-grid">'
        f'<div class="ua-cockpit-kpi"><span>Most supported</span><b>{escape(_holding(strongest, "Unavailable"))}</b></div>'
        f'<div class="ua-cockpit-kpi"><span>Most challenged</span><b>{escape(_holding(challenged, "Unavailable"))}</b></div>'
        f'<div class="ua-cockpit-kpi"><span>Largest position</span><b>{escape(largest_text)}</b></div>'
        '</div></div>'
    )
