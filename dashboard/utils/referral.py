"""
utils/referral.py
=================
Referral Program — code generation, signup tracking, and reward application.

Reward structure:
  Referee  — 14-day free trial at Stripe checkout (trial_days=14 passed to
              billing.create_checkout_session when ?ref= is present in URL)
  Referrer — 1 free month via Stripe coupon (percent_off=100, duration=once)
              applied automatically when their referee converts to paid Pro.

Usage:
  # At signup (utils/auth.py):
  record_referral_signup(referee_email, ref_code)

  # After Pro checkout success (utils/billing.py):
  mark_referral_converted(referee_email, referee_user_id=user_id)

  # For the Pro user referral UI (pages/29_Upgrade.py):
  stats = get_referral_stats(user_id)
"""

import os
import secrets
import string
from datetime import datetime, timezone

from sqlalchemy import select, update

from utils.db import engine, users, referrals

# Base URL used to build referral links. Matches the Render external URL in
# production; falls back to localhost so local dev links are still usable.
_BASE_URL = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8501").rstrip("/")
_UPGRADE_PATH = "/upgrade-to-pro"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_code() -> str:
    """Generate a URL-safe 8-char alphanumeric referral code (uppercase)."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


# ── Code management ───────────────────────────────────────────────────────────

def get_or_create_referral_code(user_id: int) -> str:
    """
    Return the user's existing referral code, or generate and persist a fresh
    unique one. Idempotent — safe to call on every page render.

    Uses a retry loop to handle the (extremely unlikely) collision case where
    the random 8-char code already exists for another user.
    """
    with engine.begin() as conn:
        row = conn.execute(
            select(users.c.referral_code).where(users.c.id == user_id)
        ).fetchone()
        if row and row[0]:
            return row[0]

        # Generate unique code — retry on collision (astronomically rare)
        for _ in range(10):
            code = _generate_code()
            clash = conn.execute(
                select(users.c.id).where(users.c.referral_code == code)
            ).fetchone()
            if not clash:
                conn.execute(
                    update(users)
                    .where(users.c.id == user_id)
                    .values(referral_code=code)
                )
                return code

    raise RuntimeError("Could not generate a unique referral code after 10 attempts.")


def get_referral_stats(user_id: int) -> dict:
    """
    Return a dict with everything the referral UI needs:
    {
        "code":             str,   # 8-char code
        "link":             str,   # full referral URL
        "total_referred":   int,   # signups via this user's link
        "total_converted":  int,   # of those who went Pro
        "months_earned":    int,   # rewards already applied
    }
    """
    code = get_or_create_referral_code(user_id)
    link = f"{_BASE_URL}{_UPGRADE_PATH}?ref={code}"

    try:
        with engine.connect() as conn:
            rows = conn.execute(
                select(referrals.c.status)
                .where(referrals.c.referrer_id == user_id)
            ).fetchall()
    except Exception:
        rows = []

    statuses = [r[0] for r in rows]
    return {
        "code":            code,
        "link":            link,
        "total_referred":  len(statuses),
        "total_converted": sum(1 for s in statuses if s in ("converted", "rewarded")),
        "months_earned":   sum(1 for s in statuses if s == "rewarded"),
    }


def is_valid_referral_code(code: str) -> bool:
    """Return whether ``code`` belongs to a real referrer."""
    normalized = (code or "").strip().upper()
    if not normalized:
        return False
    try:
        with engine.connect() as conn:
            return conn.execute(
                select(users.c.id).where(users.c.referral_code == normalized)
            ).fetchone() is not None
    except Exception:
        return False


def has_recorded_referral(referee_email: str) -> bool:
    """Return whether an account was created through a valid referral."""
    normalized = (referee_email or "").strip().lower()
    if not normalized:
        return False
    try:
        with engine.connect() as conn:
            return conn.execute(
                select(referrals.c.id).where(referrals.c.referee_email == normalized)
            ).fetchone() is not None
    except Exception:
        return False


# ── Signup tracking ───────────────────────────────────────────────────────────

def record_referral_signup(referee_email: str, code: str) -> bool:
    """
    Record that a new account was created using a referral code.

    Returns True if the referral was recorded, False if:
      - the code doesn't belong to any user
      - this email already has a referral row (idempotent)

    Called from utils/auth.py signup() when ?ref= is present.
    """
    referee_email = referee_email.strip().lower()
    code = code.strip().upper()
    if not code:
        return False

    try:
        with engine.begin() as conn:
            # Resolve code → referrer_id
            referrer_row = conn.execute(
                select(users.c.id).where(users.c.referral_code == code)
            ).fetchone()
            if not referrer_row:
                return False

            # Idempotent — one row per referee email
            existing = conn.execute(
                select(referrals.c.id)
                .where(referrals.c.referee_email == referee_email)
            ).fetchone()
            if existing:
                return False

            conn.execute(
                referrals.insert().values(
                    referrer_id=referrer_row[0],
                    referee_email=referee_email,
                    status="pending",
                    created_at=_now_iso(),
                )
            )
        # Transaction committed. Now send the welcome email best-effort —
        # wrapped in its own try/except so an email failure never prevents
        # the referral from being recorded or the signup from completing.
        try:
            from utils.email import send_referral_welcome_email
            send_referral_welcome_email(referee_email)
        except Exception:
            pass
        return True
    except Exception:
        return False


# ── Conversion + reward ───────────────────────────────────────────────────────

def mark_referral_converted(
    referee_email: str,
    referee_user_id: int | None = None,
) -> None:
    """
    Mark the referral row as converted and trigger the referrer reward.

    Called from utils/billing.handle_checkout_success() immediately after a
    referee upgrades to Pro. Best-effort — never raises; failures are silently
    swallowed so they can't block the checkout success flow.
    """
    referee_email = referee_email.strip().lower()

    referrer_id: int | None = None
    try:
        with engine.begin() as conn:
            row = conn.execute(
                select(referrals.c.id, referrals.c.referrer_id, referrals.c.status)
                .where(referrals.c.referee_email == referee_email)
            ).fetchone()
            if not row:
                return  # no referral on record — direct signup

            ref_row_id, referrer_id, status = row
            if status in ("converted", "rewarded"):
                return  # already processed

            vals: dict = {"status": "converted", "converted_at": _now_iso()}
            if referee_user_id is not None:
                vals["referee_id"] = referee_user_id

            conn.execute(
                update(referrals)
                .where(referrals.c.id == ref_row_id)
                .values(**vals)
            )
    except Exception:
        return

    # Apply the reward to the referrer (best-effort, doesn't block the caller)
    if referrer_id is not None:
        try:
            _apply_referrer_stripe_reward(referrer_id)
        except Exception:
            pass


def _apply_referrer_stripe_reward(referrer_id: int) -> bool:
    """
    Apply a 1-free-month Stripe coupon to the referrer's active subscription.

    Uses a shared reusable coupon (ua_referral_1mo_free: 100% off, once).
    Creates the coupon if it doesn't exist yet. Returns True on success.
    """
    import stripe  # lazy import — not installed locally by default

    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        return False
    stripe.api_key = key

    # Get referrer's stripe_subscription_id
    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(users.c.stripe_subscription_id)
                .where(users.c.id == referrer_id)
            ).fetchone()
    except Exception:
        return False

    if not row or not row[0]:
        # Referrer has no active subscription (free tier / admin grant) —
        # can't apply a coupon. Mark as rewarded anyway so we don't retry.
        _mark_referrer_rewarded(referrer_id)
        return False

    sub_id = row[0]
    _COUPON_ID = "ua_referral_1mo_free"

    # Get or create the reusable coupon
    try:
        stripe.Coupon.retrieve(_COUPON_ID)
    except Exception:
        try:
            stripe.Coupon.create(
                id=_COUPON_ID,
                percent_off=100,
                duration="once",
                name="Referral Reward — 1 Free Month",
            )
        except Exception:
            return False

    try:
        stripe.Subscription.modify(sub_id, coupon=_COUPON_ID)
        _mark_referrer_rewarded(referrer_id)
        return True
    except Exception:
        return False


def _mark_referrer_rewarded(referrer_id: int) -> None:
    """Mark the oldest converted-but-not-yet-rewarded referral as rewarded."""
    try:
        with engine.begin() as conn:
            row = conn.execute(
                select(referrals.c.id)
                .where(referrals.c.referrer_id == referrer_id)
                .where(referrals.c.status == "converted")
                .order_by(referrals.c.converted_at)
                .limit(1)
            ).fetchone()
            if row:
                conn.execute(
                    update(referrals)
                    .where(referrals.c.id == row[0])
                    .values(status="rewarded", rewarded_at=_now_iso())
                )
    except Exception:
        pass
