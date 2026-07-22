"""Fast, evidence-backed priority brief assembled from persisted account data."""

from __future__ import annotations

import json
from html import escape
from typing import Any

from sqlalchemy import select

from utils import db
from utils.db import score_components, score_snapshots
from utils.risk_profile import compute_personal_score_from_components, normalize


def _load_evidence_for_positions(positions: list[dict], *, source: str) -> list[dict]:
    """Attach the latest honest score evidence to already-selected positions."""
    tickers = [str(row["ticker"]).upper() for row in positions]
    if not tickers:
        return []
    with db.engine.begin() as conn:
        snapshots = conn.execute(
            select(score_snapshots)
            .where(score_snapshots.c.ticker.in_(tickers))
            .order_by(score_snapshots.c.snapshot_date.desc())
        ).mappings().all()
        component_rows = conn.execute(
            select(score_components)
            .where(score_components.c.ticker.in_(tickers))
            .order_by(score_components.c.snapshot_date.desc())
        ).mappings().all()

    latest_snapshots: dict[str, dict] = {}
    for row in snapshots:
        latest_snapshots.setdefault(str(row["ticker"]), dict(row))
    latest_components: dict[str, dict] = {}
    for row in component_rows:
        ticker = str(row["ticker"])
        if ticker in latest_components:
            continue
        try:
            parsed = json.loads(row["components_json"])
            parsed["snapshot_date"] = row["snapshot_date"]
            latest_components[ticker] = parsed
        except Exception:
            continue

    return [
        {
            "ticker": ticker,
            "position": dict(positions[index]),
            "weight_pct": float(positions[index].get("weight_pct", 0) or 0),
            "source": source,
            "snapshot": latest_snapshots.get(ticker),
            "components": latest_components.get(ticker),
        }
        for index, ticker in enumerate(tickers)
    ]


def load_watchlist_evidence(user_id: int, limit: int = 25) -> list[dict]:
    """Backward-compatible equal-weighted evidence for watched securities."""
    try:
        from utils.alerts_db import get_watchlist

        watch_rows = (get_watchlist(user_id) or [])[: max(1, int(limit))]
        if not watch_rows:
            return []
        equal_weight = 100.0 / len(watch_rows)
        positions = [
            {**dict(row), "ticker": str(row["ticker"]).upper(), "weight_pct": equal_weight}
            for row in watch_rows
        ]
        return _load_evidence_for_positions(positions, source="watchlist")
    except Exception:
        return []


def load_portfolio_evidence(user_id: int, limit: int = 25) -> list[dict]:
    """Prefer the saved weighted portfolio; fall back to an equal-weight watchlist."""
    try:
        from utils.portfolio_workspace import get_default_holdings

        holdings = get_default_holdings(user_id)[: max(1, int(limit))]
        if holdings:
            return _load_evidence_for_positions(holdings, source="portfolio")
    except Exception:
        pass
    return load_watchlist_evidence(user_id, limit=limit)


def build_priority_brief(
    evidence: list[dict],
    profile: Any,
    what_changed: dict | None = None,
) -> dict:
    """Rank watched securities by material evidence, never by trading advice."""
    p = normalize(profile)
    changes = (what_changed or {}).get("changes") or []
    change_by_ticker: dict[str, list[dict]] = {}
    for change in changes:
        for ticker in change.get("watchlist_hits") or []:
            change_by_ticker.setdefault(str(ticker).upper(), []).append(change)

    priorities: list[dict] = []
    missing: list[str] = []
    for item in evidence or []:
        ticker = str(item.get("ticker", "")).upper().strip()
        if not ticker:
            continue
        snapshot = item.get("snapshot") or {}
        components = item.get("components") or {}
        canonical = snapshot.get("score")
        if canonical is None:
            canonical = components.get("final_score")
        if canonical is None:
            missing.append(ticker)
            continue
        canonical = float(canonical)

        personal = compute_personal_score_from_components(components, p) if components else {}
        personal_score = personal.get("score") if personal.get("ok") else canonical
        personal_score = float(personal_score)
        profile_delta = round(personal_score - canonical, 1)
        ticker_changes = change_by_ticker.get(ticker, [])
        weight_pct = max(0.0, float(item.get("weight_pct") or 0))
        weight_priority = min(weight_pct, 50.0) * 0.35

        if ticker_changes:
            lead = max(ticker_changes, key=lambda row: abs(float(row.get("delta") or 0)))
            status = "Changed"
            reason = lead.get("headline") or "A relevant macro signal changed"
            priority_score = 100 + abs(float(lead.get("delta") or 0)) + weight_priority
        elif abs(profile_delta) >= 5:
            status = "Profile divergence"
            direction = "higher" if profile_delta > 0 else "lower"
            reason = f"Your settings read {abs(profile_delta):.1f} points {direction} than the standard score"
            priority_score = 70 + abs(profile_delta) + weight_priority
        elif canonical >= 65 or canonical <= 35:
            status = "Strong backdrop"
            reason = "The latest recorded evidence sits outside the neutral range"
            priority_score = 50 + abs(canonical - 50) + weight_priority
        else:
            status = "Monitor"
            reason = "No material watchlist-specific change is recorded"
            priority_score = abs(canonical - 50) + weight_priority

        weighted_impact = round((personal_score - 50.0) * weight_pct / 100.0, 2)

        priorities.append({
            "ticker": ticker,
            "canonical_score": round(canonical, 1),
            "personal_score": round(personal_score, 1),
            "profile_delta": profile_delta,
            "case": str(snapshot.get("case") or "NEUTRAL").upper(),
            "snapshot_date": snapshot.get("snapshot_date") or components.get("snapshot_date"),
            "status": status,
            "reason": reason,
            "explanation": personal.get("explanation", ""),
            "priority_score": round(priority_score, 1),
            "weight_pct": round(weight_pct, 2),
            "weighted_impact": weighted_impact,
            "source": item.get("source", "watchlist"),
        })

    priorities.sort(key=lambda row: (-row["priority_score"], row["ticker"]))
    scored_weight = sum(row["weight_pct"] for row in priorities)
    weighted_personal_score = (
        sum(row["personal_score"] * row["weight_pct"] for row in priorities) / scored_weight
        if scored_weight > 0 else None
    )
    source = (evidence[0].get("source") if evidence else "portfolio") or "portfolio"
    return {
        "profile": p,
        "priorities": priorities,
        "top_priorities": priorities[:3],
        "remaining": priorities[3:],
        "missing": missing,
        "n_evidence": len(priorities),
        "n_total": len(evidence or []),
        "source": source,
        "scored_weight_pct": round(scored_weight, 1),
        "weighted_personal_score": round(weighted_personal_score, 1) if weighted_personal_score is not None else None,
        "material_changes": sum(1 for row in priorities if row["status"] == "Changed"),
    }


def render_priority_card_html(item: dict, rank: int) -> str:
    """Render one compact priority card with professional, muted contrast."""
    case = str(item.get("case") or "NEUTRAL").upper()
    accent = "#68A982" if case == "BULL" else ("#C77B7B" if case == "BEAR" else "#8F9AAD")
    delta = float(item.get("profile_delta") or 0)
    weight = float(item.get("weight_pct") or 0)
    delta_text = f"{delta:+.1f} vs standard" if abs(delta) >= 0.1 else "Aligned with standard"
    return (
        '<div style="background:#11161E;border:1px solid rgba(255,255,255,.09);'
        f'border-top:2px solid {accent};border-radius:10px;padding:16px 17px;height:100%;">'
        f'<div style="font-size:.62rem;color:#8F9AAD;letter-spacing:.10em;text-transform:uppercase;">Priority {rank}</div>'
        '<div style="display:flex;justify-content:space-between;align-items:flex-start;margin:8px 0 10px;">'
        f'<div><div style="font-size:1.08rem;color:#EDF1F7;font-weight:760;">{escape(str(item.get("ticker", "")))}</div>'
        f'<div style="font-size:.66rem;color:{accent};font-weight:700;margin-top:2px;">{escape(str(item.get("status", "")))}</div></div>'
        f'<div style="text-align:right;"><div style="font-size:1.45rem;color:#EDF1F7;font-weight:780;">{float(item.get("personal_score", 0)):.0f}</div>'
        '<div style="font-size:.60rem;color:#8F9AAD;">YOUR SCORE</div></div></div>'
        f'<div style="font-size:.78rem;color:#B4BDCA;line-height:1.52;min-height:38px;">{escape(str(item.get("reason", "")))}</div>'
        f'<div style="font-size:.66rem;color:#7F8999;border-top:1px solid rgba(255,255,255,.07);margin-top:12px;padding-top:9px;">'
        f'Standard {float(item.get("canonical_score", 0)):.0f} · {escape(delta_text)}'
        + (f' · {weight:.1f}% weight' if weight > 0 else '')
        + '</div></div>'
    )
