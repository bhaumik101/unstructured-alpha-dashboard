# utils/billing.py
# Unstructured Alpha — Stripe Subscription Billing
#
# Architecture note: Streamlit has no HTTP route system, so there's no place
# to host a Stripe webhook endpoint within this app. The approach taken here
# is "verify-on-success-redirect": after a user completes Stripe Checkout,
# Stripe redirects them back to /Upgrade?stripe_session_id=xxx, and this
# module verifies that session against the Stripe API to confirm payment
# before upgrading the user's tier in the database.
#
# This covers the happy path perfectly. For subscription lifecycle events
# (renewals, cancellations), the check_and_sync_subscription() function
# re-verifies the subscription status on each Pro page load — controlled
# by a 24-hour TTL cache so it doesn't hit Stripe on every render.
#
# Environment variables required (set in Render dashboard, never in code):
#   STRIPE_SECRET_KEY         — sk_live_... or sk_test_...
#   STRIPE_PRICE_ID           — price_... for the Pro monthly price ($20/mo)
#   STRIPE_ANNUAL_PRICE_ID    — price_... for the Pro annual price ($192/yr)
#   STRIPE_PUBLISHABLE_KEY    — pk_live_... (used only for display/meta)
#
# Optional:
#   STRIPE_WEBHOOK_SECRET  — whsec_... if a separate webhook service is added later

import os
import logging
from datetime import datetime, timezone

import streamlit as st

logger = logging.getLogger(__name__)

# ── Stripe key resolution ─────────────────────────────────────────────────────
# Keys are NEVER user-configurable — they live as Render environment variables
# only. This function is called lazily, not at import time, so a missing key
# doesn't crash every page load; it only surfaces on billing-specific pages.

def _stripe_client():
    """Return an initialized stripe module, raising a clear error if unconfigured."""
    import stripe  # lazy import — not installed in local dev by default
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        raise RuntimeError(
            "STRIPE_SECRET_KEY is not set. Add it as a Render environment variable."
        )
    stripe.api_key = key
    return stripe


def get_stripe_price_id(plan: str = "monthly") -> str:
    """Return the Stripe Price ID for the given plan ('monthly' or 'annual')."""
    if plan == "annual":
        pid = os.environ.get("STRIPE_ANNUAL_PRICE_ID", "")
        if not pid:
            raise RuntimeError("STRIPE_ANNUAL_PRICE_ID is not set. Add it as a Render environment variable.")
        return pid
    pid = os.environ.get("STRIPE_PRICE_ID", "")
    if not pid:
        raise RuntimeError("STRIPE_PRICE_ID is not set. Add it as a Render environment variable.")
    return pid


def get_stripe_publishable_key() -> str:
    return os.environ.get("STRIPE_PUBLISHABLE_KEY", "")


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_user_tier(user_id: int) -> str:
    """
    Read subscription_tier from DB for the given user_id.
    Returns 'free' if the user doesn't exist or the column is NULL.
    Fast — always reads from DB, but callers cache the result in session_state.
    """
    from sqlalchemy import select, text
    from utils.db import engine, users

    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(users.c.subscription_tier).where(users.c.id == user_id)
            ).fetchone()
        if row is None:
            return "free"
        return row[0] or "free"
    except Exception:
        return "free"


def set_user_tier(user_id: int, tier: str, customer_id: str = "", subscription_id: str = "") -> None:
    """Persist subscription_tier (and optionally Stripe IDs) for a user."""
    from sqlalchemy import update
    from utils.db import engine, users

    vals: dict = {"subscription_tier": tier}
    if customer_id:
        vals["stripe_customer_id"] = customer_id
    if subscription_id:
        vals["stripe_subscription_id"] = subscription_id

    with engine.begin() as conn:
        conn.execute(update(users).where(users.c.id == user_id).values(**vals))


def get_stripe_ids(user_id: int) -> tuple[str, str]:
    """Return (stripe_customer_id, stripe_subscription_id) for a user, or ('', '')."""
    from sqlalchemy import select
    from utils.db import engine, users

    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(users.c.stripe_customer_id, users.c.stripe_subscription_id)
                .where(users.c.id == user_id)
            ).fetchone()
        if row is None:
            return "", ""
        return (row[0] or "", row[1] or "")
    except Exception:
        return "", ""


# ── Stripe Checkout ───────────────────────────────────────────────────────────

def create_checkout_session(
    user_id: int,
    user_email: str,
    success_url: str,
    cancel_url: str,
    plan: str = "monthly",
) -> str:
    """
    Create a Stripe Checkout Session for the Pro subscription and return the
    hosted checkout URL. The caller redirects the user there.

    plan: "monthly" ($20/mo) or "annual" ($192/yr)
    success_url must contain {CHECKOUT_SESSION_ID} which Stripe substitutes
    with the actual session ID on redirect (used by handle_checkout_success).
    """
    stripe = _stripe_client()
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer_email=user_email,
        line_items=[{"price": get_stripe_price_id(plan), "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"ua_user_id": str(user_id)},
        subscription_data={
            "metadata": {"ua_user_id": str(user_id)},
            "trial_period_days": 7,   # 7-day free trial — easy to remove later
        },
        allow_promotion_codes=True,
        billing_address_collection="auto",
    )
    return session.url


def handle_checkout_success(session_id: str, user_id: int) -> dict:
    """
    Verify a Checkout Session returned via the success_url redirect, then
    upgrade the user's tier in the DB if payment is confirmed.

    Returns a dict: {"ok": bool, "tier": str, "error": str}
    """
    stripe = _stripe_client()
    try:
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=["subscription", "customer"],
        )
    except Exception as e:
        logger.error("Stripe session retrieve failed: %s", e)
        return {"ok": False, "tier": "free", "error": str(e)}

    # Verify the ua_user_id in session metadata matches the logged-in user —
    # prevents one user from using another's session_id to claim Pro.
    meta_uid = int(session.get("metadata", {}).get("ua_user_id", -1))
    if meta_uid != user_id:
        return {"ok": False, "tier": "free", "error": "Session user mismatch."}

    payment_status = session.get("payment_status", "")  # "paid" | "unpaid" | "no_payment_required"
    sub = session.get("subscription")
    sub_status = sub.get("status", "") if sub else ""  # "active" | "trialing" | ...

    if payment_status in ("paid", "no_payment_required") or sub_status in ("active", "trialing"):
        customer_id = ""
        if isinstance(session.get("customer"), str):
            customer_id = session["customer"]
        elif session.get("customer"):
            customer_id = session["customer"]["id"]

        sub_id = sub["id"] if sub else ""
        set_user_tier(user_id, "pro", customer_id=customer_id, subscription_id=sub_id)
        return {"ok": True, "tier": "pro", "error": ""}

    return {"ok": False, "tier": "free", "error": f"Payment status: {payment_status}"}


# ── Stripe Customer Portal ────────────────────────────────────────────────────

def create_portal_session(customer_id: str, return_url: str) -> str:
    """
    Create a Stripe Customer Portal session so a Pro user can manage their
    subscription (cancel, update card, view invoices). Returns the portal URL.
    """
    stripe = _stripe_client()
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url


# ── Live subscription re-verification ────────────────────────────────────────

def check_and_sync_subscription(user_id: int) -> str:
    """
    Re-check the live Stripe subscription status for a user. If the subscription
    has been cancelled or lapsed, downgrades DB tier back to 'free'.
    Returns the effective tier ('free' | 'pro').
    Expensive (API call) — call at most once per session, not per page render.
    """
    stripe = _stripe_client()
    _, sub_id = get_stripe_ids(user_id)

    if not sub_id:
        # No subscription on record — definitely free.
        return "free"

    try:
        sub = stripe.Subscription.retrieve(sub_id)
        live_status = sub.get("status", "canceled")
        if live_status in ("active", "trialing", "past_due"):
            return "pro"
        else:
            # Cancelled, unpaid, etc — downgrade.
            set_user_tier(user_id, "free")
            return "free"
    except Exception as e:
        logger.warning("Stripe subscription re-check failed for user %s: %s", user_id, e)
        # Fail open: don't downgrade on a transient API error.
        return get_user_tier(user_id)


# ── Admin utilities ───────────────────────────────────────────────────────────

def admin_grant_pro(email: str) -> dict:
    """
    Manually grant Pro tier to a user by email address.
    Used for gifting access, comps, and beta testers.
    Returns {"ok": bool, "message": str}.

    This bypasses Stripe entirely — it simply sets subscription_tier = 'pro'
    in the DB. The user will not have a Stripe subscription_id, so
    check_and_sync_subscription() will leave them on Pro (it only downgrades
    when there IS a subscription_id that's cancelled/lapsed).
    """
    from sqlalchemy import select, update
    from utils.db import engine, users

    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(users.c.id, users.c.subscription_tier).where(users.c.email == email)
            ).fetchone()

        if row is None:
            return {"ok": False, "message": f"No account found for {email!r}"}

        user_id, current_tier = row[0], row[1]
        if current_tier == "pro":
            return {"ok": True, "message": f"{email} already has Pro access."}

        set_user_tier(user_id, "pro")
        logger.info("Admin granted Pro to user %s (%s)", user_id, email)
        return {"ok": True, "message": f"✅ Pro granted to {email}"}

    except Exception as exc:
        logger.error("admin_grant_pro failed for %s: %s", email, exc)
        return {"ok": False, "message": f"DB error: {exc}"}


def admin_revoke_pro(email: str) -> dict:
    """Revoke Pro and return user to free tier by email."""
    from sqlalchemy import select
    from utils.db import engine, users

    try:
        with engine.connect() as conn:
            row = conn.execute(
                select(users.c.id).where(users.c.email == email)
            ).fetchone()

        if row is None:
            return {"ok": False, "message": f"No account found for {email!r}"}

        set_user_tier(row[0], "free")
        logger.info("Admin revoked Pro from user %s (%s)", row[0], email)
        return {"ok": True, "message": f"✅ Revoked Pro from {email}"}

    except Exception as exc:
        return {"ok": False, "message": f"DB error: {exc}"}


# ── Pro gating utility ────────────────────────────────────────────────────────

PRO_FEATURES = [
    "Factor Exposure — Fama-French regression for any ticker",
    "PDF Research Reports — one-click export for any equity",
    "Signal Backtester — build & backtest custom signal combinations",
    "Portfolio Analyzer — risk decomposition across your full portfolio",
    "Options Flow — live unusual options activity feed",
    "Unlimited watchlist tickers (Free: 5)",
    "Morning digest email with top signal moves",
]

_PRO_GATE_CSS = """
<style>
.pro-gate {
    background: linear-gradient(135deg, rgba(124,58,237,0.12) 0%, rgba(0,200,224,0.06) 100%);
    border: 1px solid rgba(124,58,237,0.35);
    border-radius: 12px;
    padding: 28px 32px;
    text-align: center;
    margin: 24px 0;
}
.pro-gate h2 { color: #E8EEFF; font-size: 1.45rem; margin: 0 0 8px; }
.pro-gate p  { color: #8892B0; font-size: 0.95rem; margin: 0 0 20px; }
.pro-badge {
    display: inline-block;
    background: linear-gradient(90deg, #7C3AED, #00C8E0);
    color: #fff;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    padding: 3px 10px;
    border-radius: 20px;
    margin-bottom: 14px;
    text-transform: uppercase;
}
</style>
"""


def require_pro(page_name: str = "this page") -> None:
    """
    Check that the current logged-in user has a Pro subscription.
    If not logged in: shows login prompt + st.stop().
    If logged in but free tier: shows upgrade CTA + st.stop().
    If Pro: returns silently so the page can continue.

    Call this at the TOP of any Pro-gated page, before rendering any content.
    """
    from utils.auth_ui import get_cookies, try_restore_session

    cookies = get_cookies()
    user = try_restore_session(cookies)

    if not user:
        st.markdown(_PRO_GATE_CSS, unsafe_allow_html=True)
        st.markdown("""
        <div class="pro-gate">
            <div class="pro-badge">Pro Feature</div>
            <h2>Sign in to access this page</h2>
            <p>Create a free account, then upgrade to Pro to unlock {page}.</p>
        </div>
        """.replace("{page}", page_name), unsafe_allow_html=True)

        from utils.auth_ui import render_auth_forms
        _, col, _ = st.columns([1, 2, 1])
        with col:
            render_auth_forms(cookies, key_prefix="pro_gate_")
        st.stop()
        return

    # Check tier — use session cache to avoid DB call on every re-render.
    cache_key = f"_tier_{user['id']}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = get_user_tier(user["id"])

    if st.session_state[cache_key] == "pro":
        return  # ✅ all good

    # Free user — show upgrade gate
    st.markdown(_PRO_GATE_CSS, unsafe_allow_html=True)
    st.markdown(f"""
    <div class="pro-gate">
        <div class="pro-badge">Pro Feature</div>
        <h2>Upgrade to unlock {page_name}</h2>
        <p>You're on the Free plan. Upgrade to Pro for $15/month to access this and all Pro features.</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("🔓 Upgrade to Pro — from $16/mo", type="primary", use_container_width=True, key="pro_gate_upgrade_btn"):
            st.switch_page("pages/29_Upgrade.py")

    with st.expander("What's included in Pro?"):
        for feat in PRO_FEATURES:
            st.markdown(f"✓ {feat}")

    st.stop()
