"""Validated, user-scoped saved screens for the Stock Recommender."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import delete, func, select

from utils.db import engine, saved_recommender_screens, upsert_stmt


MAX_SAVED_SCREENS = 10
HORIZONS = (
    "Short-term (1–2 wks)",
    "Medium-term (1–2 mo)",
    "Long-term (3+ mo)",
    "All",
)
DEFAULT_CONFIG = {
    "time_horizon": "All",
    "n_show": 8,
    "n_enrich": 10,
    "min_signals": 2,
    "sectors": [],
}
_SPACE_RE = re.compile(r"\s+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_screen_name(value: object) -> str:
    """Return a compact display name or reject unsafe/ambiguous names."""
    name = _SPACE_RE.sub(" ", str(value or "").strip())
    if not 2 <= len(name) <= 64:
        raise ValueError("Screen name must be between 2 and 64 characters.")
    return name


def normalize_screen_config(config: dict, *, allowed_sectors: Iterable[str] | None = None) -> dict:
    """Clamp a persisted filter definition to the controls the page supports."""
    raw = dict(config or {})
    horizon = str(raw.get("time_horizon") or DEFAULT_CONFIG["time_horizon"])
    if horizon not in HORIZONS:
        raise ValueError("Unknown time horizon.")

    def _bounded_int(key: str, low: int, high: int) -> int:
        try:
            value = int(raw.get(key, DEFAULT_CONFIG[key]))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid {key.replace('_', ' ')}.") from exc
        if not low <= value <= high:
            raise ValueError(f"{key.replace('_', ' ').title()} must be between {low} and {high}.")
        return value

    sectors = raw.get("sectors") or []
    if not isinstance(sectors, (list, tuple)):
        raise ValueError("Sectors must be a list.")
    allowed = {str(item) for item in allowed_sectors} if allowed_sectors is not None else None
    clean_sectors: list[str] = []
    for value in sectors:
        sector = str(value or "").strip()
        if not sector or len(sector) > 64 or (allowed is not None and sector not in allowed):
            continue
        if sector not in clean_sectors:
            clean_sectors.append(sector)
    if len(clean_sectors) > 20:
        raise ValueError("A screen can include at most 20 sectors.")

    return {
        "time_horizon": horizon,
        "n_show": _bounded_int("n_show", 3, 15),
        "n_enrich": _bounded_int("n_enrich", 5, 20),
        "min_signals": _bounded_int("min_signals", 1, 8),
        "sectors": clean_sectors,
    }


def list_saved_screens(user_id: int, *, allowed_sectors: Iterable[str] | None = None) -> list[dict]:
    """Return only this user's valid screens, newest-updated first."""
    with engine.begin() as conn:
        rows = conn.execute(
            select(saved_recommender_screens)
            .where(saved_recommender_screens.c.user_id == int(user_id))
            .order_by(saved_recommender_screens.c.updated_at.desc(), saved_recommender_screens.c.id.desc())
            .limit(MAX_SAVED_SCREENS)
        ).mappings().all()
    screens: list[dict] = []
    for row in rows:
        try:
            config = normalize_screen_config(
                json.loads(row["config_json"]), allowed_sectors=allowed_sectors
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        screens.append({**dict(row), "config": config})
    return screens


def save_screen(
    user_id: int,
    name: str,
    config: dict,
    *,
    allowed_sectors: Iterable[str] | None = None,
) -> dict:
    """Create or update a named screen without exceeding the per-user cap."""
    user_id = int(user_id)
    clean_name = normalize_screen_name(name)
    clean_config = normalize_screen_config(config, allowed_sectors=allowed_sectors)
    now = _now()
    with engine.begin() as conn:
        existing = conn.execute(
            select(saved_recommender_screens.c.id).where(
                saved_recommender_screens.c.user_id == user_id,
                func.lower(saved_recommender_screens.c.name) == clean_name.lower(),
            )
        ).first()
        if not existing:
            count = conn.execute(
                select(func.count()).select_from(saved_recommender_screens).where(
                    saved_recommender_screens.c.user_id == user_id
                )
            ).scalar_one()
            if count >= MAX_SAVED_SCREENS:
                raise ValueError(f"You can save up to {MAX_SAVED_SCREENS} screens.")

        # Canonicalize case to an existing name so SQLite and Postgres behave
        # identically even though their default text comparison rules differ.
        persisted_name = clean_name
        if existing:
            persisted_name = conn.execute(
                select(saved_recommender_screens.c.name).where(
                    saved_recommender_screens.c.id == existing[0]
                )
            ).scalar_one()
        stmt = upsert_stmt(saved_recommender_screens, ["user_id", "name"]).values(
            user_id=user_id,
            name=persisted_name,
            config_json=json.dumps(clean_config, sort_keys=True, separators=(",", ":")),
            created_at=now,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "name"],
            set_={"config_json": stmt.excluded.config_json, "updated_at": now},
        )
        conn.execute(stmt)
        row = conn.execute(
            select(saved_recommender_screens).where(
                saved_recommender_screens.c.user_id == user_id,
                saved_recommender_screens.c.name == persisted_name,
            )
        ).mappings().one()
    return {**dict(row), "config": clean_config}


def delete_screen(user_id: int, screen_id: int) -> bool:
    """Delete a screen only when it belongs to the requesting user."""
    with engine.begin() as conn:
        result = conn.execute(
            delete(saved_recommender_screens).where(
                saved_recommender_screens.c.id == int(screen_id),
                saved_recommender_screens.c.user_id == int(user_id),
            )
        )
    return bool(result.rowcount)
