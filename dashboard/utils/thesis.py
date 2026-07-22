"""Private per-user investment thesis and decision-journal storage."""

from datetime import datetime, timezone

from sqlalchemy import select

from utils.db import engine, investment_theses, upsert_stmt


VALID_STANCES = {"Bullish", "Bearish", "Neutral"}
VALID_STATUSES = {"active", "closed", "invalidated"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_thesis(user_id: int, ticker: str) -> dict | None:
    """Return only the requesting user's thesis for this ticker."""
    with engine.begin() as conn:
        row = conn.execute(
            select(investment_theses).where(
                investment_theses.c.user_id == int(user_id),
                investment_theses.c.ticker == ticker.upper().strip(),
            )
        ).mappings().first()
    return dict(row) if row else None


def save_thesis(
    *,
    user_id: int,
    ticker: str,
    stance: str,
    status: str,
    horizon_weeks: int,
    thesis: str,
    catalysts: str = "",
    risks: str = "",
    invalidation: str = "",
    outcome_notes: str = "",
    entry_price: float | None = None,
    entry_score: float | None = None,
) -> None:
    ticker = ticker.upper().strip()
    stance = stance.title()
    status = status.lower()
    thesis = thesis.strip()
    if stance not in VALID_STANCES:
        raise ValueError("Invalid thesis stance.")
    if status not in VALID_STATUSES:
        raise ValueError("Invalid thesis status.")
    if not thesis:
        raise ValueError("A thesis summary is required.")
    horizon_weeks = max(1, min(int(horizon_weeks), 260))
    now = _now()

    stmt = upsert_stmt(investment_theses, ["user_id", "ticker"]).values(
        user_id=int(user_id),
        ticker=ticker,
        stance=stance,
        status=status,
        horizon_weeks=horizon_weeks,
        entry_price=entry_price,
        entry_score=entry_score,
        thesis=thesis,
        catalysts=catalysts.strip(),
        risks=risks.strip(),
        invalidation=invalidation.strip(),
        outcome_notes=outcome_notes.strip(),
        created_at=now,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "ticker"],
        set_={
            "stance": stance,
            "status": status,
            "horizon_weeks": horizon_weeks,
            "entry_price": entry_price,
            "entry_score": entry_score,
            "thesis": thesis,
            "catalysts": catalysts.strip(),
            "risks": risks.strip(),
            "invalidation": invalidation.strip(),
            "outcome_notes": outcome_notes.strip(),
            "updated_at": now,
        },
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def list_user_theses(user_id: int, *, status: str | None = None) -> list[dict]:
    query = select(investment_theses).where(investment_theses.c.user_id == int(user_id))
    if status:
        normalized_status = status.lower()
        if normalized_status not in VALID_STATUSES:
            raise ValueError("Invalid thesis status filter.")
        query = query.where(investment_theses.c.status == normalized_status)
    query = query.order_by(investment_theses.c.updated_at.desc())
    with engine.begin() as conn:
        rows = conn.execute(query).mappings().all()
    return [dict(row) for row in rows]
