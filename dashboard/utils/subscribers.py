# utils/subscribers.py
# Unstructured Alpha — the weekly public email's subscriber list
#
# An address and nothing else: no account, no portfolio. Signed up from the
# public pages (seo/main.py /api/subscribe), confirmed by a link (double
# opt-in), unsubscribed by a link in every email.
#
# RULES
#   * Nothing but the confirmation is ever sent to an address until its owner
#     clicks the link in it.
#   * The public endpoint answers the same way whatever happened, so it cannot
#     be used to learn whether an address is on the list.
#   * Abuse limits: one confirmation per address per COOLDOWN, and at most
#     DAILY_CAP confirmations a day across everyone.
#   * Unsubscribing is one click and final until the person signs up again.

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional, Tuple

from sqlalchemy import func, insert, select, update

COOLDOWN = timedelta(minutes=10)
DAILY_CAP = 100
_EMAIL = re.compile(r"[^@\s<>\"',;]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9-]{1,63})+")
_SOURCE = re.compile(r"[A-Za-z0-9 _-]{1,40}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalise(email: str) -> Optional[str]:
    e = str(email or "").strip().lower()
    return e if len(e) <= 254 and _EMAIL.fullmatch(e) else None


def _table():
    from utils import db
    return db.engine, db.public_subscribers


def subscribe(email: str, source: str = "", send: Optional[Callable[[str, str], bool]] = None,
              now: Optional[datetime] = None) -> str:
    """Record a sign-up and send its confirmation. Returns what happened, for
    logs and tests only (never shown to the visitor): "sent", "already",
    "cooldown", "capped", "invalid" or "failed". send(email, token) -> bool."""
    e = normalise(email)
    if not e:
        return "invalid"
    now = now or _now()
    src = source if _SOURCE.fullmatch(source or "") else ""
    engine, t = _table()
    with engine.begin() as conn:
        row = conn.execute(select(t).where(t.c.email == e)).mappings().first()
        if row and row["status"] == "confirmed":
            return "already"
        if row and row["status"] == "pending" and row["confirm_sent_at"]:
            if now - datetime.fromisoformat(row["confirm_sent_at"]) < COOLDOWN:
                return "cooldown"
        day = (now - timedelta(days=1)).isoformat()
        sent_today = conn.execute(select(func.count()).select_from(t)
                                  .where(t.c.confirm_sent_at >= day)).scalar() or 0
        if sent_today >= DAILY_CAP:
            return "capped"
        token = secrets.token_urlsafe(24)
        values = {"status": "pending", "token": token, "confirm_sent_at": now.isoformat(),
                  "confirmed_at": None, "unsubscribed_at": None}
        if row:
            conn.execute(update(t).where(t.c.id == row["id"]).values(**values))
        else:
            conn.execute(insert(t).values(email=e, source=src, created_at=now.isoformat(), **values))
    if send is None:
        return "sent"
    try:
        return "sent" if send(e, token) else "failed"
    except Exception:
        return "failed"


def confirm(token: str, now: Optional[datetime] = None) -> bool:
    """True if the token belongs to an address that is now confirmed."""
    if not token or len(token) > 64:
        return False
    engine, t = _table()
    with engine.begin() as conn:
        row = conn.execute(select(t).where(t.c.token == token)).mappings().first()
        if not row or row["status"] == "unsubscribed":
            return False
        if row["status"] == "pending":
            conn.execute(update(t).where(t.c.id == row["id"])
                         .values(status="confirmed", confirmed_at=(now or _now()).isoformat()))
    return True


def unsubscribe(token: str, now: Optional[datetime] = None) -> bool:
    """True if the token belongs to an address that is now off the list."""
    if not token or len(token) > 64:
        return False
    engine, t = _table()
    with engine.begin() as conn:
        row = conn.execute(select(t).where(t.c.token == token)).mappings().first()
        if not row:
            return False
        if row["status"] != "unsubscribed":
            conn.execute(update(t).where(t.c.id == row["id"])
                         .values(status="unsubscribed", unsubscribed_at=(now or _now()).isoformat()))
    return True


def due(week: str) -> List[Tuple[str, str]]:
    """(email, token) of every confirmed address not yet sent this data week."""
    engine, t = _table()
    with engine.connect() as conn:
        rows = conn.execute(select(t.c.email, t.c.token, t.c.last_sent_week)
                            .where(t.c.status == "confirmed").order_by(t.c.id)).all()
    return [(r[0], r[1]) for r in rows if r[2] != week]


def mark_sent(email: str, week: str) -> None:
    engine, t = _table()
    with engine.begin() as conn:
        conn.execute(update(t).where(t.c.email == email).values(last_sent_week=week))


def counts() -> dict:
    engine, t = _table()
    with engine.connect() as conn:
        rows = conn.execute(select(t.c.status, func.count()).group_by(t.c.status)).all()
    return {r[0]: r[1] for r in rows}
