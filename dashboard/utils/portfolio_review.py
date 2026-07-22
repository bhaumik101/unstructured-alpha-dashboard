"""Cached, evidence-constrained executive reviews for saved portfolios."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from html import escape
from typing import Any, Callable

from sqlalchemy import select

from utils.db import engine, portfolio_reviews, upsert_stmt
from utils.personalized_brief import build_priority_brief
from utils.ratelimit import limit_action


REVIEW_VERSION = "portfolio-review-v1"
MODEL = "claude-haiku-4-5-20251001"
MAX_HOLDINGS = 25


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_review_input(evidence: list[dict], profile: Any) -> dict:
    """Reduce persisted portfolio evidence to a stable, bounded review payload."""
    bounded = list(evidence or [])[:MAX_HOLDINGS]
    brief = build_priority_brief(bounded, profile)
    holdings = sorted(
        [
            {
                "ticker": row["ticker"],
                "weight_pct": round(float(row.get("weight_pct") or 0), 2),
                "your_score": round(float(row["personal_score"]), 1),
                "standard_score": round(float(row["canonical_score"]), 1),
                "profile_delta": round(float(row.get("profile_delta") or 0), 1),
                "case": row.get("case") or "NEUTRAL",
                "as_of": row.get("snapshot_date"),
                "status": row.get("status") or "Monitor",
            }
            for row in brief["priorities"]
        ],
        key=lambda row: row["ticker"],
    )
    weights = sorted((row["weight_pct"] for row in holdings), reverse=True)
    strongest = max(holdings, key=lambda row: row["your_score"]) if holdings else None
    weakest = min(holdings, key=lambda row: row["your_score"]) if holdings else None
    payload = {
        "version": REVIEW_VERSION,
        "profile": brief["profile"],
        "holdings": holdings,
        "summary": {
            "weighted_your_score": brief["weighted_personal_score"],
            "scored_weight_pct": brief["scored_weight_pct"],
            "largest_weight_pct": weights[0] if weights else 0.0,
            "top_three_weight_pct": round(sum(weights[:3]), 1),
            "strongest": strongest,
            "weakest": weakest,
            "missing": sorted(brief["missing"]),
            "n_scored": brief["n_evidence"],
            "n_total": brief["n_total"],
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload["input_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def _deterministic_review(payload: dict) -> dict:
    """Always-available review whose claims are direct transformations of evidence."""
    summary = payload["summary"]
    weighted = summary.get("weighted_your_score")
    if weighted is None:
        stance, headline = "Insufficient coverage", "Portfolio review needs recorded score evidence"
    elif weighted >= 60:
        stance, headline = "Supportive", "Portfolio evidence currently leans supportive"
    elif weighted <= 40:
        stance, headline = "Challenging", "Portfolio evidence currently leans challenging"
    else:
        stance, headline = "Mixed", "Portfolio evidence is mixed across current holdings"

    observations: list[str] = []
    if weighted is not None:
        observations.append(
            f"The weighted Your Score is {weighted:.1f}/100 across "
            f"{summary['scored_weight_pct']:.1f}% of portfolio weight with recorded evidence."
        )
    strongest = summary.get("strongest")
    weakest = summary.get("weakest")
    if strongest:
        observations.append(
            f"{strongest['ticker']} has the strongest current personalized backdrop at "
            f"{strongest['your_score']:.1f}/100 and represents {strongest['weight_pct']:.1f}% of the portfolio."
        )
    if weakest and (not strongest or weakest["ticker"] != strongest["ticker"]):
        observations.append(
            f"{weakest['ticker']} has the weakest current personalized backdrop at "
            f"{weakest['your_score']:.1f}/100 and represents {weakest['weight_pct']:.1f}% of the portfolio."
        )

    risks: list[str] = []
    largest = float(summary.get("largest_weight_pct") or 0)
    top_three = float(summary.get("top_three_weight_pct") or 0)
    if largest >= 35:
        risks.append(f"Single-position concentration is elevated: the largest holding is {largest:.1f}%.")
    if top_three >= 70 and summary.get("n_total", 0) > 3:
        risks.append(f"The three largest positions account for {top_three:.1f}% of portfolio weight.")
    if summary.get("missing"):
        risks.append(
            "No trustworthy recorded score is available for " + ", ".join(summary["missing"])
            + "; those positions are excluded from the weighted read."
        )
    if weakest and weakest["your_score"] <= 35:
        risks.append(
            f"{weakest['ticker']} is below the 35-point challenging threshold on Your Score."
        )
    if not risks:
        risks.append("No concentration or score-threshold exception is detected in the recorded evidence.")

    next_checks: list[str] = []
    if weakest:
        next_checks.append(f"Review the current evidence and invalidation conditions for {weakest['ticker']}.")
    if strongest and strongest.get("profile_delta"):
        next_checks.append(
            f"Compare the personalized and standard score drivers for {strongest['ticker']}."
        )
    if summary.get("missing"):
        next_checks.append("Open the missing holdings in Ticker Deep Dive to establish real score evidence.")
    if not next_checks:
        next_checks.append("Revisit the review when holdings, profile settings, or recorded scores change.")

    return {
        "headline": headline,
        "stance": stance,
        "executive_summary": " ".join(observations[:2]),
        "observations": observations,
        "risk_flags": risks,
        "next_checks": next_checks[:3],
        "model_synthesis": None,
    }


def _anthropic_synthesis(payload: dict, deterministic: dict) -> tuple[str, str, int, int]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    import anthropic

    prompt = (
        "Write one concise institutional portfolio-review paragraph using only the supplied facts. "
        "Do not add forecasts, recommendations, prices, returns, sectors, correlations, or facts not "
        "present below. Frame output as research context, not advice. Use 70-120 words.\n\n"
        + json.dumps({"evidence": payload, "verified_review": deterministic}, sort_keys=True)
    )
    response = anthropic.Anthropic(api_key=api_key).messages.create(
        model=MODEL,
        max_tokens=220,
        system=(
            "You are a precise institutional portfolio analyst. Never invent evidence and never "
            "give trading, sizing, or allocation instructions."
        ),
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    if not 80 <= len(text) <= 1200:
        raise ValueError("Model synthesis failed length validation")
    return text, MODEL, int(response.usage.input_tokens), int(response.usage.output_tokens)


def get_cached_review(user_id: int, input_hash: str) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(portfolio_reviews).where(
                portfolio_reviews.c.user_id == int(user_id),
                portfolio_reviews.c.input_hash == str(input_hash),
            )
        ).mappings().first()
    if not row:
        return None
    try:
        review = json.loads(row["review_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return {**review, "cache_hit": True, "model": row["model"], "updated_at": row["updated_at"]}


def generate_portfolio_review(
    user_id: int,
    payload: dict,
    *,
    synthesis: Callable[[dict, dict], tuple[str, str, int, int]] | None = None,
) -> dict:
    """Return a cached review or generate once for a materially new input hash."""
    cached = get_cached_review(user_id, payload["input_hash"])
    if cached:
        return cached
    allowed, retry_after = limit_action(f"u{int(user_id)}", "portfolio_review")
    if not allowed:
        return {"status": "limited", "retry_after": retry_after}

    review = _deterministic_review(payload)
    model = "deterministic-v1"
    input_tokens = output_tokens = 0
    try:
        narrative, model, input_tokens, output_tokens = (synthesis or _anthropic_synthesis)(
            payload, review
        )
        review["model_synthesis"] = narrative
    except Exception:
        # Evidence review remains useful and fully honest without model access.
        pass
    review.update({
        "status": "ready",
        "input_hash": payload["input_hash"],
        "evidence_summary": payload["summary"],
    })
    now = _now()
    stmt = upsert_stmt(portfolio_reviews, ["user_id"]).values(
        user_id=int(user_id),
        input_hash=payload["input_hash"],
        review_json=json.dumps(review, sort_keys=True, separators=(",", ":")),
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        created_at=now,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=["user_id"],
        set_={
            "input_hash": payload["input_hash"],
            "review_json": json.dumps(review, sort_keys=True, separators=(",", ":")),
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "updated_at": now,
        },
    )
    with engine.begin() as conn:
        conn.execute(stmt)
    return {**review, "cache_hit": False, "model": model, "updated_at": now}


def render_portfolio_review_html(review: dict) -> str:
    """Professional, muted review surface; every external string is escaped."""
    stance = str(review.get("stance") or "Mixed")
    accent = "#68A982" if stance == "Supportive" else ("#C77B7B" if stance == "Challenging" else "#8E9BB8")

    def _list(items: list[str]) -> str:
        return "".join(
            '<div style="display:flex;gap:9px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,.06);">'
            f'<span style="color:{accent};font-size:.72rem;">—</span>'
            f'<span style="color:#B7C0CE;font-size:.78rem;line-height:1.5;">{escape(str(item))}</span></div>'
            for item in items
        )

    synthesis = review.get("model_synthesis")
    synthesis_html = (
        '<div style="margin-top:14px;padding:13px 15px;background:rgba(255,255,255,.025);'
        'border:1px solid rgba(255,255,255,.07);border-radius:8px;">'
        '<div style="font-size:.60rem;color:#8E9BB8;letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px;">Model synthesis</div>'
        f'<div style="font-size:.80rem;color:#C1C9D6;line-height:1.6;">{escape(str(synthesis))}</div></div>'
        if synthesis else ""
    )
    return (
        f'<div style="background:#0F141C;border:1px solid rgba(255,255,255,.09);border-top:2px solid {accent};'
        'border-radius:12px;padding:20px 21px;">'
        f'<div style="font-size:.62rem;color:{accent};font-weight:700;letter-spacing:.11em;text-transform:uppercase;">{escape(stance)} evidence</div>'
        f'<div style="font-size:1.18rem;color:#EDF1F7;font-weight:760;margin:7px 0 8px;">{escape(str(review.get("headline", "Portfolio review")))}</div>'
        f'<div style="font-size:.84rem;color:#B8C1CF;line-height:1.6;">{escape(str(review.get("executive_summary", "")))}</div>'
        f'{synthesis_html}'
        '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:16px;margin-top:18px;">'
        '<div><div style="font-size:.62rem;color:#8E9BB8;letter-spacing:.1em;text-transform:uppercase;">Risk flags</div>'
        f'{_list(review.get("risk_flags") or [])}</div>'
        '<div><div style="font-size:.62rem;color:#8E9BB8;letter-spacing:.1em;text-transform:uppercase;">Next research checks</div>'
        f'{_list(review.get("next_checks") or [])}</div></div></div>'
    )
