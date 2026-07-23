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


# Admin allowlist — single source of truth for who counts as an admin.
# (Previously hard-coded only inside pages/38_Admin.py.)
ADMIN_EMAILS = {"bpgiri2005@gmail.com"}


def is_admin(user: dict | None) -> bool:
    """True if the given session user is an admin. Email-based allowlist."""
    if not user:
        return False
    return (user.get("email") or "").strip().lower() in {e.lower() for e in ADMIN_EMAILS}


def effective_is_pro(user: dict | None) -> bool:
    """
    Non-blocking Pro check for chrome (header/footer badges).

    IMPORTANT: the session `user` dict only carries {"id", "email"} — it does
    NOT contain subscription_tier. So the tier must be read from the DB via
    get_user_tier() (cached per session under the same `_tier_{id}` key that
    require_pro() uses), NOT from user.get("subscription_tier"). Admins are
    always treated as Pro.
    """
    if not user or not user.get("id"):
        return False
    if is_admin(user):
        return True
    cache_key = f"_tier_{user['id']}"
    if cache_key not in st.session_state:
        try:
            st.session_state[cache_key] = get_user_tier(user["id"])
        except Exception:
            return False
    return st.session_state.get(cache_key) == "pro"


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
    trial_days: int = 7,
) -> str:
    """
    Create a Stripe Checkout Session for the Pro subscription and return the
    hosted checkout URL. The caller redirects the user there.

    plan:       "monthly" ($20/mo) or "annual" ($192/yr)
    trial_days: free trial length in days (default 7; pass 14 for referred users)
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
            "trial_period_days": trial_days,
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

        # If this user was referred, mark their referral as converted and
        # trigger the referrer's 1-month-free reward (best-effort).
        try:
            from utils.db import engine as _engine, users as _users
            from sqlalchemy import select as _select
            with _engine.connect() as _conn:
                _row = _conn.execute(
                    _select(_users.c.email).where(_users.c.id == user_id)
                ).fetchone()
            if _row:
                from utils.referral import mark_referral_converted
                mark_referral_converted(_row[0], referee_user_id=user_id)
        except Exception as exc:
            logger.warning("mark_referral_converted failed for user %s: %s", user_id, exc)

        # Activate the member's saved briefing preference and record trial end.
        # Legacy accounts with no saved preference retain the historical Pro
        # default (morning email on); setup users who chose in-app remain off.
        # trial_end_at lets the day-6 reminder cron identify who to email.
        try:
            from sqlalchemy import select as sa_select, update as sa_update
            from utils.db import engine, users

            with engine.connect() as conn:
                saved_preference = conn.execute(
                    sa_select(users.c.digest_preference).where(users.c.id == user_id)
                ).scalar_one_or_none()
            extra: dict = {
                "digest_opted_in": saved_preference != "in_app",
                "digest_preference": saved_preference or "morning_email",
            }
            if sub and sub.get("trial_end"):
                extra["trial_end_at"] = datetime.fromtimestamp(
                    sub["trial_end"], tz=timezone.utc
                ).isoformat()

            with engine.begin() as conn:
                conn.execute(
                    sa_update(users).where(users.c.id == user_id).values(**extra)
                )
        except Exception as exc:
            logger.warning("Post-checkout extras failed for user %s: %s", user_id, exc)

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
        # No Stripe subscription on record. Could be an admin-granted Pro
        # account (no Stripe sub exists) or a checkout where the sub_id
        # wasn't stored. Trust the DB tier rather than hard-coding "free".
        return get_user_tier(user_id)

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
    "Portfolio Fit Lab — simulate a candidate's score, factor, and concentration impact",
    "Options Flow — live unusual options activity feed",
    "AI Research Assistant — answers grounded in current live signals",
    "Ticker Deep Dive Pro — correlation, filings, contracts, and sentiment",
    "Decision Queue — daily evidence triage across holdings, catalysts, and theses",
    "Catalyst Command Center — verified events, portfolio exposure, and private review plans",
    "Thesis Journal — private decisions, invalidation rules, and outcomes",
    "Unlimited watchlist tickers (Free: 5)",
    "Morning digest email with top signal moves",
]

# Contextual Pro (Phase 16): each gated page names the SPECIFIC value it unlocks,
# so the gate reads like "here's what you're missing" instead of a generic pitch.
_PAGE_BENEFIT = {
    "Portfolio Intelligence":  "Save weighted holdings and monitor macro exposure, scenario risk, and concentration across your real portfolio.",
    "Portfolio Fit Lab":       "Test how a candidate or resized position changes portfolio-level macro concentration before editing your saved holdings.",
    "Portfolio Suite":         "See risk decomposition, factor exposure, and macro concentration across your whole portfolio in one view.",
    "Options Flow":            "Track live unusual options activity — large, aggressive trades as they print.",
    "Stock Recommender":       "Get ranked equity ideas screened by the macro signals currently in your favor.",
    "Factor Exposure":         "Run a Fama-French factor regression on any ticker to see its true style and macro sensitivities.",
    "Portfolio Analyzer":      "Decompose risk and macro exposure across your full portfolio — not one ticker at a time.",
    "Export Report":           "Export a clean, one-click PDF research report for any equity.",
    "Signal Backtester":       "Build and backtest custom signal combinations against historical price moves.",
    "Signal Portfolio Backtest": "Backtest a signal-driven portfolio and compare it against the benchmark.",
    "AI Research Assistant":     "Use a live signal-aware research copilot grounded in the platform's current real-data state.",
    "Ticker Deep Dive Pro":      "Unlock lead-lag correlation, insider and short-interest evidence, 13F and federal-contract intelligence, and earnings sentiment.",
    "Decision Queue":            "See which holdings need review now, why they moved up the queue, and which source workflow to open next.",
    "Catalyst Command Center":    "Rank verified macro and company events by affected portfolio weight, then save private pre/post-event plans.",
    "Thesis Journal":            "Turn live research into a private decision record with catalysts, risks, invalidation rules, and outcome reviews.",
}

_PRO_GATE_CSS = """
<style>
.pro-gate {
    background: #101522;
    border: 1px solid #2B354B;
    border-radius: 8px;
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


def require_pro(page_name: str = "this page", benefit: str | None = None) -> None:
    """
    Check that the current logged-in user has a Pro subscription.
    If not logged in: shows login prompt + st.stop().
    If logged in but free tier: shows upgrade CTA + st.stop().
    If Pro: returns silently so the page can continue.

    Call this at the TOP of any Pro-gated page, before rendering any content.

    benefit: one sentence naming the specific value of THIS page. If omitted,
             falls back to _PAGE_BENEFIT[page_name], then to a generic line.
    """
    from utils.auth_ui import get_cookies, try_restore_session

    cookies = get_cookies()
    user = try_restore_session(cookies)
    benefit = benefit or _PAGE_BENEFIT.get(page_name)

    if not user:
        st.markdown(_PRO_GATE_CSS, unsafe_allow_html=True)
        _lead = benefit or f"Create a free account, then upgrade to Pro to unlock {page_name}."
        st.html(
            '<div class="pro-gate">'
            '<div class="pro-badge">Pro Feature</div>'
            f'<h2>Sign in to access {page_name}</h2>'
            f'<p>{_lead}</p>'
            '</div>'
        )

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
        # Once per session, re-verify live Stripe subscription status so lapsed
        # subscriptions get downgraded automatically without a manual trigger.
        sync_key = f"_sync_done_{user['id']}"
        if not st.session_state.get(sync_key):
            st.session_state[sync_key] = True  # set before the call to prevent loops
            try:
                live_tier = check_and_sync_subscription(user["id"])
                st.session_state[cache_key] = live_tier
                if live_tier != "pro":
                    # Subscription lapsed — fall through to upgrade gate below
                    pass
                else:
                    return  # ✅ confirmed Pro
            except Exception as exc:
                logger.warning("Subscription sync failed for user %s: %s", user["id"], exc)
                return  # fail open — don't lock out user on transient Stripe error
        else:
            return  # ✅ already synced this session

    # Free user — show a CONTEXTUAL upgrade gate: name the specific value of THIS
    # page, and quote the price from the single source of truth (no more $15/$16 drift).
    from utils.product_metrics import PRO_PRICE_MONTHLY, PRO_PRICE_ANNUAL_PER_MONTH

    _lead = benefit or "This is a Pro tool."
    st.markdown(_PRO_GATE_CSS, unsafe_allow_html=True)
    st.html(
        '<div class="pro-gate">'
        '<div class="pro-badge">Pro Feature</div>'
        f'<h2>Unlock {page_name}</h2>'
        f'<p>{_lead}</p>'
        f'<p style="font-size:0.82rem;color:#6B7280;">Pro — '
        f'${PRO_PRICE_ANNUAL_PER_MONTH}/mo billed annually · '
        f'${PRO_PRICE_MONTHLY}/mo month-to-month · 7-day free trial, cancel anytime.</p>'
        '</div>'
    )

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button(f"Unlock {page_name} with Pro →", type="primary", use_container_width=True, key="pro_gate_upgrade_btn"):
            st.switch_page("pages/29_Upgrade.py")

    with st.expander("What's included in Pro?"):
        for feat in PRO_FEATURES:
            st.markdown(f"✓ {feat}")

    st.stop()
