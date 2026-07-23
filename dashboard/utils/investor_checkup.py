"""Fast, plain-English checkup built from recent persisted full-score evidence."""

from __future__ import annotations

from datetime import date, timedelta
import re
from typing import Iterable

from sqlalchemy import or_, select

from utils.db import engine, score_snapshots


FREE_TICKER_LIMIT = 5
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")


def normalize_checkup_tickers(value: str | Iterable[str], limit: int = FREE_TICKER_LIMIT) -> tuple[list[str], list[str]]:
    """Normalize, deduplicate, cap, and report invalid symbols without guessing."""
    raw_values = re.split(r"[,\s]+", value) if isinstance(value, str) else list(value or [])
    valid: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        ticker = str(raw or "").upper().strip().lstrip("$")
        if not ticker:
            continue
        if not _TICKER_RE.fullmatch(ticker):
            invalid.append(str(raw))
            continue
        if ticker not in seen:
            seen.add(ticker)
            valid.append(ticker)
    return valid[: max(1, int(limit))], invalid


def load_recent_score_evidence(
    tickers: Iterable[str], *, as_of: date | None = None, max_age_days: int = 14
) -> list[dict]:
    """Load current and comparison snapshots in one query; stale rows stay unavailable."""
    symbols = list(dict.fromkeys(str(value).upper() for value in tickers if str(value).strip()))
    if not symbols:
        return []
    day = as_of or date.today()
    history_cutoff = (day - timedelta(days=30)).isoformat()
    freshness_cutoff = (day - timedelta(days=max(1, int(max_age_days)))).isoformat()
    with engine.begin() as conn:
        rows = conn.execute(
            select(score_snapshots)
            .where(
                score_snapshots.c.ticker.in_(symbols),
                score_snapshots.c.snapshot_date >= history_cutoff,
                or_(
                    score_snapshots.c.score_kind == "full",
                    score_snapshots.c.score_kind.is_(None),
                ),
            )
            .order_by(score_snapshots.c.ticker, score_snapshots.c.snapshot_date.desc())
        ).mappings().all()

    history: dict[str, list[dict]] = {ticker: [] for ticker in symbols}
    for row in rows:
        history.setdefault(str(row["ticker"]).upper(), []).append(dict(row))

    result: list[dict] = []
    for ticker in symbols:
        ticker_rows = history.get(ticker) or []
        latest = ticker_rows[0] if ticker_rows else None
        fresh = bool(latest and str(latest.get("snapshot_date", "")) >= freshness_cutoff)
        prior = ticker_rows[-1] if len(ticker_rows) >= 2 else None
        score = float(latest["score"]) if fresh else None
        delta = round(score - float(prior["score"]), 1) if score is not None and prior else None
        result.append({
            "ticker": ticker,
            "available": score is not None,
            "score": score,
            "case": latest.get("case") if fresh and latest else None,
            "snapshot_date": latest.get("snapshot_date") if fresh and latest else None,
            "delta_30d": delta,
            "stale_snapshot_date": latest.get("snapshot_date") if latest and not fresh else None,
        })
    return result


def build_investor_checkup(evidence: Iterable[dict], earnings: dict[str, dict | None] | None = None) -> dict:
    """Create a deterministic, advice-free orientation for an equal-weighted ticker set."""
    rows = [dict(row) for row in (evidence or [])]
    earnings = earnings or {}
    covered = [row for row in rows if row.get("available") and row.get("score") is not None]
    supportive = [row for row in covered if float(row["score"]) >= 65]
    challenging = [row for row in covered if float(row["score"]) <= 35]
    mixed = [row for row in covered if 35 < float(row["score"]) < 65]
    average = round(sum(float(row["score"]) for row in covered) / len(covered), 1) if covered else None
    if average is None:
        headline = "Recorded score evidence is not available yet"
        explanation = "Open each ticker’s Deep Dive to build a current, real-data research record. Missing rows are not treated as neutral."
    elif average >= 60:
        headline = "The tracked set has a generally supportive macro backdrop"
        explanation = "More of the recorded evidence is above the middle of its historical range. Review each ticker before generalizing across the set."
    elif average <= 40:
        headline = "The tracked set has a generally challenging macro backdrop"
        explanation = "More of the recorded evidence is below the middle of its historical range. Use the ticker pages to identify the specific headwinds."
    else:
        headline = "The tracked set has a mixed macro backdrop"
        explanation = "The recorded evidence does not point strongly in one direction. Differences between tickers matter more than the group average."

    attention = sorted(
        covered,
        key=lambda row: (
            -abs(float(row.get("delta_30d") or 0)),
            -abs(float(row["score"]) - 50),
            row["ticker"],
        ),
    )
    upcoming = []
    for row in rows:
        info = earnings.get(row["ticker"])
        if not info:
            continue
        upcoming.append({"ticker": row["ticker"], **dict(info)})
    upcoming.sort(key=lambda row: (int(row.get("days_until", 999)), row["ticker"]))

    return {
        "headline": headline,
        "explanation": explanation,
        "ticker_count": len(rows),
        "covered_count": len(covered),
        "missing_count": len(rows) - len(covered),
        "average_score": average,
        "supportive_count": len(supportive),
        "mixed_count": len(mixed),
        "challenging_count": len(challenging),
        "evidence": rows,
        "attention": attention,
        "upcoming_earnings": upcoming,
    }
