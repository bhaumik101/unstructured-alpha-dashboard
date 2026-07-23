"""Persisted-evidence Portfolio Fit simulation with no price forecasting."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timezone
from typing import Iterable

from sqlalchemy import or_, select

from utils.db import engine, score_components, score_snapshots


MAX_EVIDENCE_AGE_DAYS = 7
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")


def _as_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _unavailable(ticker: str, weight: float, reason: str) -> dict:
    return {
        "ticker": ticker,
        "weight": weight,
        "ok": False,
        "reason": reason,
    }


def load_fit_records(
    holdings: Iterable[dict],
    candidate: str,
    *,
    as_of: date | None = None,
) -> tuple[list[dict], dict]:
    """Load latest matching full-score/component evidence for a fit simulation."""
    day = as_of or datetime.now(timezone.utc).date()
    positions = [dict(row) for row in (holdings or [])]
    symbol = str(candidate or "").upper().strip().lstrip("$")
    if not _TICKER_RE.fullmatch(symbol):
        return [], _unavailable(symbol, 0, "The candidate ticker format is invalid.")
    tickers = {str(row.get("ticker", "")).upper().strip() for row in positions}
    if symbol:
        tickers.add(symbol)
    tickers.discard("")
    if not tickers:
        return [], _unavailable(symbol, 0, "No ticker was provided.")

    with engine.begin() as conn:
        snapshots = conn.execute(
            select(score_snapshots)
            .where(
                score_snapshots.c.ticker.in_(tickers),
                or_(
                    score_snapshots.c.score_kind == "full",
                    score_snapshots.c.score_kind.is_(None),
                ),
            )
            .order_by(
                score_snapshots.c.ticker,
                score_snapshots.c.snapshot_date.desc(),
                score_snapshots.c.id.desc(),
            )
        ).mappings().all()
        components = conn.execute(
            select(score_components)
            .where(score_components.c.ticker.in_(tickers))
            .order_by(
                score_components.c.ticker,
                score_components.c.snapshot_date.desc(),
                score_components.c.id.desc(),
            )
        ).mappings().all()

    component_by_key = {
        (str(row["ticker"]).upper(), str(row["snapshot_date"])): dict(row)
        for row in components
    }
    snapshot_by_ticker: dict[str, dict] = {}
    for row in snapshots:
        ticker = str(row["ticker"]).upper()
        key = (ticker, str(row["snapshot_date"]))
        if ticker not in snapshot_by_ticker and key in component_by_key:
            snapshot_by_ticker[ticker] = dict(row)

    try:
        from utils.config import TICKERS
    except Exception:
        TICKERS = {}

    def build(ticker: str, weight: float) -> dict:
        snapshot = snapshot_by_ticker.get(ticker)
        if not snapshot:
            return _unavailable(ticker, weight, "No matching full-score component snapshot is available.")
        snapshot_day = _as_date(snapshot.get("snapshot_date"))
        if not snapshot_day or (day - snapshot_day).days > MAX_EVIDENCE_AGE_DAYS:
            return _unavailable(ticker, weight, f"The latest full-score evidence is stale ({snapshot.get('snapshot_date')}).")
        component_row = component_by_key[(ticker, str(snapshot["snapshot_date"]))]
        try:
            payload = json.loads(component_row["components_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return _unavailable(ticker, weight, "The component evidence could not be verified.")
        if not (payload.get("coverage") or {}).get("generates_score", True):
            return _unavailable(ticker, weight, "The snapshot has insufficient signal coverage.")
        final_score = payload.get("final_score")
        if final_score is None or abs(float(final_score) - float(snapshot["score"])) > 0.5:
            return _unavailable(ticker, weight, "The score and component evidence do not reconcile.")

        signals = payload.get("signals") or []
        corr_info = {
            str(row.get("id")): {
                "weight": float(row.get("weight") or 0),
                "significant": bool(row.get("significant")),
            }
            for row in signals
            if row.get("id")
        }
        signal_scores = {
            str(row.get("id")): {"score": float(row.get("score") or 50)}
            for row in signals
            if row.get("id")
        }
        if not any(row.get("significant") for row in corr_info.values()):
            return _unavailable(ticker, weight, "No statistically significant factor evidence is available.")
        return {
            "ticker": ticker,
            "weight": weight,
            "score": float(snapshot["score"]),
            "corr_info": corr_info,
            "signal_scores": signal_scores,
            "sector": (TICKERS.get(ticker, {}) or {}).get("sector", ""),
            "snapshot_date": snapshot["snapshot_date"],
            "model_version": component_row.get("model_version"),
            "signal_registry_version": component_row.get("signal_registry_version"),
            "ok": True,
        }

    current = [
        build(
            str(row.get("ticker", "")).upper().strip(),
            max(0.0, float(row.get("weight_pct", row.get("weight", 0)) or 0)),
        )
        for row in positions
        if str(row.get("ticker", "")).strip()
    ]
    current_candidate = next((row for row in current if row["ticker"] == symbol and row["ok"]), None)
    candidate_record = dict(current_candidate) if current_candidate else build(symbol, 0)
    return current, candidate_record


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(key, 0) * b.get(key, 0) for key in keys)
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def simulate_portfolio_fit(
    current_records: Iterable[dict],
    candidate_record: dict,
    proposed_weight: float,
) -> dict:
    """Compare the saved portfolio with a pro-rata-funded candidate weight."""
    from utils.portfolio_xray import build_portfolio_xray, factor_name, holding_factor_profile

    target = max(1.0, min(float(proposed_weight), 50.0))
    all_current = [dict(row) for row in (current_records or [])]
    valid_current = [row for row in all_current if row.get("ok")]
    unavailable = [row for row in all_current if not row.get("ok")]
    if not valid_current:
        return {"state": "portfolio_unavailable", "unavailable": unavailable}
    if not candidate_record or not candidate_record.get("ok"):
        return {
            "state": "candidate_unavailable",
            "candidate": candidate_record,
            "unavailable": unavailable,
        }

    comparable = valid_current + [candidate_record]
    model_versions = {str(row.get("model_version") or "legacy") for row in comparable}
    registry_versions = {
        str(row.get("signal_registry_version") or "legacy") for row in comparable
    }
    if len(model_versions) > 1 or len(registry_versions) > 1:
        return {
            "state": "evidence_incompatible",
            "reason": (
                "The portfolio and candidate snapshots were produced by different score or "
                "signal-registry versions. Refresh their Ticker Deep Dives before comparing them."
            ),
            "model_versions": sorted(model_versions),
            "signal_registry_versions": sorted(registry_versions),
            "unavailable": unavailable,
        }

    before = build_portfolio_xray(valid_current)
    symbol = str(candidate_record["ticker"]).upper()
    other_positions = [row for row in valid_current if str(row["ticker"]).upper() != symbol]
    other_total = sum(max(0.0, float(row.get("weight") or 0)) for row in other_positions)
    if not other_positions or other_total <= 0:
        return {"state": "portfolio_unavailable", "unavailable": unavailable}

    after_inputs = []
    for row in other_positions:
        adjusted = dict(row)
        adjusted["weight"] = (100.0 - target) * float(row.get("weight") or 0) / other_total
        after_inputs.append(adjusted)
    candidate_after = dict(candidate_record)
    candidate_after["weight"] = target
    after_inputs.append(candidate_after)
    after = build_portfolio_xray(after_inputs)

    before_factors = {row["factor"]: row for row in before.get("factors", [])}
    after_factors = {row["factor"]: row for row in after.get("factors", [])}
    shifts = []
    for factor in set(before_factors) | set(after_factors):
        before_pct = float((before_factors.get(factor) or {}).get("pct_portfolio", 0) or 0)
        after_pct = float((after_factors.get(factor) or {}).get("pct_portfolio", 0) or 0)
        shifts.append({
            "factor": factor,
            "name": factor_name(factor),
            "before_pct": before_pct,
            "after_pct": after_pct,
            "delta_pct": round(after_pct - before_pct, 1),
        })
    shifts.sort(key=lambda row: (-abs(row["delta_pct"]), row["name"]))

    candidate_profile = holding_factor_profile(
        candidate_record.get("corr_info", {}), candidate_record.get("signal_scores", {})
    )
    candidate_vector = {factor: row["exposure"] for factor, row in candidate_profile.items()}
    portfolio_vector = {
        factor: float(row.get("avg_exposure") or 0) for factor, row in before_factors.items()
    }
    overlap = round(_cosine(candidate_vector, portfolio_vector), 2)
    new_factors = [
        factor_name(factor)
        for factor, row in candidate_profile.items()
        if row.get("exposure", 0) >= 0.12 and factor not in before_factors
    ]
    shared_factors = sorted(
        [
            {
                "name": factor_name(factor),
                "candidate_exposure": round(float(row.get("exposure") or 0) * 100, 1),
                "portfolio_pct": float((before_factors.get(factor) or {}).get("pct_portfolio", 0) or 0),
            }
            for factor, row in candidate_profile.items()
            if factor in before_factors and row.get("exposure", 0) >= 0.12
        ],
        key=lambda row: (-row["candidate_exposure"], row["name"]),
    )

    before_top = before.get("top_concentration") or {}
    after_top = after.get("top_concentration") or {}
    concentration_delta = round(
        float(after_top.get("pct_portfolio") or 0) - float(before_top.get("pct_portfolio") or 0), 1
    )
    if new_factors and overlap < 0.55:
        fit_label = "Adds differentiated macro exposure"
        fit_tone = "differentiated"
    elif overlap >= 0.80 or concentration_delta >= 10:
        fit_label = "Reinforces existing macro concentration"
        fit_tone = "reinforces"
    else:
        fit_label = "Mixed portfolio fit"
        fit_tone = "mixed"

    raw_total = sum(max(0.0, float(row.get("weight") or 0)) for row in all_current) or 100.0
    covered_total = sum(max(0.0, float(row.get("weight") or 0)) for row in valid_current)
    return {
        "state": "ready",
        "candidate": symbol,
        "target_weight": target,
        "before": before,
        "after": after,
        "score_delta": round(float(after["portfolio_score"]) - float(before["portfolio_score"]), 1),
        "overlap_similarity": overlap,
        "new_factors": sorted(new_factors),
        "shared_factors": shared_factors,
        "factor_shifts": shifts,
        "concentration_delta": concentration_delta,
        "fit_label": fit_label,
        "fit_tone": fit_tone,
        "coverage_pct": round(100.0 * covered_total / raw_total, 1),
        "unavailable": unavailable,
        "assumption": (
            f"{symbol} is modeled at {target:.1f}% by reducing every other scored holding pro rata. "
            "Taxes, transaction costs, price impact, and expected returns are not modeled."
        ),
    }
