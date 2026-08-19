# utils/share_watchlist.py
# Unstructured Alpha — Public Shareable Watchlist
#
# Handles the read-only public watchlist share link feature.
# Each user gets a unique 12-char alphanumeric slug that maps to their
# watchlist. The slug is generated lazily on first "Share" request and
# stored in users.watchlist_share_slug.
#
# Public URL form: /Share_Watchlist?id=<slug>
# The public view shows: ticker names, current Confluence Scores, score
# status (bull/bear/neutral), and a 30-day sparkline. No personal data
# exposed (no email, no alert thresholds, no account info).
#
# The share slug can be "revoked" (regenerated) from the Watchlist page,
# which invalidates all existing links and generates a new slug.

import os
import random
import string
from datetime import datetime, timezone

from sqlalchemy import select, update

from utils.db import engine, users, watchlist


# ── Slug generation ───────────────────────────────────────────────────────────

_SLUG_CHARS = string.ascii_letters + string.digits  # 62-char alphabet
_SLUG_LEN   = 12                                      # 62^12 ≈ 3.2 × 10^21


def _generate_slug() -> str:
    return "".join(random.choices(_SLUG_CHARS, k=_SLUG_LEN))


def get_or_create_slug(user_id: int) -> str:
    """
    Return the existing share slug for this user, or create one if none exists.
    """
    with engine.begin() as conn:
        row = conn.execute(
            select(users.c.watchlist_share_slug).where(users.c.id == user_id)
        ).scalar()
        if row:
            return row
        # Create new slug, loop on the (astronomically rare) collision
        for _ in range(5):
            slug = _generate_slug()
            existing = conn.execute(
                select(users.c.id).where(users.c.watchlist_share_slug == slug)
            ).scalar()
            if not existing:
                conn.execute(
                    update(users).where(users.c.id == user_id).values(
                        watchlist_share_slug=slug
                    )
                )
                return slug
        raise RuntimeError("Could not generate a unique slug after 5 attempts")


def revoke_slug(user_id: int) -> str:
    """
    Regenerate the share slug — invalidates all existing share links.
    Returns the new slug.
    """
    for _ in range(5):
        slug = _generate_slug()
        with engine.begin() as conn:
            existing = conn.execute(
                select(users.c.id).where(users.c.watchlist_share_slug == slug)
            ).scalar()
            if not existing:
                conn.execute(
                    update(users).where(users.c.id == user_id).values(
                        watchlist_share_slug=slug
                    )
                )
                return slug
    raise RuntimeError("Could not regenerate unique slug after 5 attempts")


def get_user_by_slug(slug: str) -> dict | None:
    """
    Return {id, email} for the user whose watchlist_share_slug == slug,
    or None if no match.
    """
    with engine.begin() as conn:
        row = conn.execute(
            select(users.c.id, users.c.email, users.c.display_name)
            .where(users.c.watchlist_share_slug == slug)
        ).fetchone()
    if row is None:
        return None
    return {"id": row[0], "email": row[1], "display_name": row[2]}


def get_watchlist_for_user(user_id: int) -> list[str]:
    """
    Return list of tickers for a user's watchlist, newest-added first.
    """
    with engine.begin() as conn:
        rows = conn.execute(
            select(watchlist.c.ticker)
            .where(watchlist.c.user_id == user_id)
            .order_by(watchlist.c.added_at.desc())
        ).fetchall()
    return [r[0].upper() for r in rows]


def build_share_url(slug: str) -> str:
    """
    Build the full public URL for this slug.

    The slug must match app.py's url_path for pages/35_Share_Watchlist.py. This
    pair silently drifted once already: the page was retired while this builder
    kept emitting /Share_Watchlist, and the Watchlist page went on telling users
    to "copy and share freely" for links that resolved to nothing.
    tests/test_shared_links_have_a_real_host.py now asserts the two agree.
    """
    base = (
        os.environ.get("APP_BASE_URL")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or "http://localhost:8501"
    ).rstrip("/")
    return f"{base}/share-watchlist?id={slug}"
