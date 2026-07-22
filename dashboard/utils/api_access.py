"""Secure one-time Pro API key issuance, authentication, and revocation."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from utils.db import api_keys, engine, users


MAX_ACTIVE_KEYS = 3
KEY_PREFIX = "ua_live_"
_NAME_SPACE_RE = re.compile(r"\s+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digest(raw_key: str) -> str:
    return hashlib.sha256(str(raw_key).encode("utf-8")).hexdigest()


def _normalize_name(value: object) -> str:
    name = _NAME_SPACE_RE.sub(" ", str(value or "").strip())
    if not 2 <= len(name) <= 64:
        raise ValueError("Key name must be between 2 and 64 characters.")
    return name


def list_api_keys(user_id: int) -> list[dict]:
    """Return display-safe metadata; key hashes are never returned to callers."""
    with engine.begin() as conn:
        rows = conn.execute(
            select(
                api_keys.c.id,
                api_keys.c.name,
                api_keys.c.key_prefix,
                api_keys.c.created_at,
                api_keys.c.last_used_at,
                api_keys.c.revoked_at,
            )
            .where(api_keys.c.user_id == int(user_id))
            .order_by(api_keys.c.created_at.desc())
        ).mappings().all()
    return [dict(row) for row in rows]


def create_api_key(user_id: int, name: str) -> dict:
    """Issue a high-entropy key once for an active Pro member."""
    user_id = int(user_id)
    clean_name = _normalize_name(name)
    raw_key = KEY_PREFIX + secrets.token_urlsafe(32)
    now = _now()
    with engine.begin() as conn:
        tier = conn.execute(
            select(users.c.subscription_tier).where(users.c.id == user_id)
        ).scalar_one_or_none()
        if str(tier or "free").lower() != "pro":
            raise PermissionError("Pro membership is required for API access.")
        active_count = conn.execute(
            select(func.count()).select_from(api_keys).where(
                api_keys.c.user_id == user_id,
                api_keys.c.revoked_at.is_(None),
            )
        ).scalar_one()
        if active_count >= MAX_ACTIVE_KEYS:
            raise ValueError(f"You can have up to {MAX_ACTIVE_KEYS} active API keys.")
        duplicate = conn.execute(
            select(api_keys.c.id).where(
                api_keys.c.user_id == user_id,
                func.lower(api_keys.c.name) == clean_name.lower(),
            )
        ).first()
        if duplicate:
            raise ValueError("Use a unique name or revoke the existing key first.")
        result = conn.execute(
            api_keys.insert().values(
                user_id=user_id,
                name=clean_name,
                key_prefix=raw_key[:16],
                key_hash=_digest(raw_key),
                created_at=now,
            )
        )
        key_id = int(result.inserted_primary_key[0])
    return {
        "id": key_id,
        "name": clean_name,
        "key_prefix": raw_key[:16],
        "raw_key": raw_key,
        "created_at": now,
    }


def revoke_api_key(user_id: int, key_id: int) -> bool:
    """Revoke one credential only when it belongs to the requesting member."""
    with engine.begin() as conn:
        result = conn.execute(
            api_keys.update()
            .where(
                api_keys.c.id == int(key_id),
                api_keys.c.user_id == int(user_id),
                api_keys.c.revoked_at.is_(None),
            )
            .values(revoked_at=_now())
        )
    return bool(result.rowcount)


def authenticate_api_key(raw_key: str) -> dict | None:
    """Resolve an active key for an active Pro account; never raises."""
    key = str(raw_key or "").strip()
    if not key.startswith(KEY_PREFIX) or len(key) < 35:
        return None
    try:
        with engine.begin() as conn:
            row = conn.execute(
                select(
                    api_keys.c.id,
                    api_keys.c.user_id,
                    api_keys.c.name,
                    api_keys.c.key_prefix,
                    api_keys.c.last_used_at,
                    users.c.subscription_tier,
                    users.c.email_verified,
                )
                .join(users, users.c.id == api_keys.c.user_id)
                .where(
                    api_keys.c.key_hash == _digest(key),
                    api_keys.c.revoked_at.is_(None),
                )
            ).mappings().first()
            if not row:
                return None
            if str(row["subscription_tier"] or "free").lower() != "pro":
                return None
            if not bool(row["email_verified"]):
                return None

            # Keep useful audit metadata without turning every API hit into a
            # write. At most one last-used update per key every 15 minutes.
            should_touch = True
            if row.get("last_used_at"):
                try:
                    last_used = datetime.fromisoformat(str(row["last_used_at"]))
                    if last_used.tzinfo is None:
                        last_used = last_used.replace(tzinfo=timezone.utc)
                    should_touch = datetime.now(timezone.utc) - last_used >= timedelta(minutes=15)
                except ValueError:
                    pass
            if should_touch:
                conn.execute(
                    api_keys.update().where(api_keys.c.id == row["id"]).values(last_used_at=_now())
                )
        return {
            "key_id": int(row["id"]),
            "user_id": int(row["user_id"]),
            "name": row["name"],
            "key_prefix": row["key_prefix"],
        }
    except Exception:
        return None
