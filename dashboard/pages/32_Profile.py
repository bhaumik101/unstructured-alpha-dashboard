# pages/32_Profile.py
# Unstructured Alpha — User Profile & Account Settings
#
# Central settings page for logged-in users:
#   - Display name (editable)
#   - Email address (read-only — changing requires re-verification; not
#     worth the complexity for this app's scale)
#   - Subscription plan + Manage/Upgrade button
#   - Change password (verifies current password, no email code required
#     since the user is already authenticated)
#   - Morning digest opt-in toggle
#   - Referral code + stats
#   - Member since date
#   - Log out

import streamlit as st

st.set_page_config(page_title="Profile — UA", layout="wide")

from utils.auth_ui import get_cookies, try_restore_session, logout
from utils.header import render_header, render_page_header, render_sidebar_base
from utils.auth import (
    get_full_profile, update_display_name, change_password,
    set_digest_optin, AuthError,
)

render_header("Profile")
render_sidebar_base()

cookies = get_cookies()
user = try_restore_session(cookies)

if not user:
    st.info("Sign in to view your profile.")
    from utils.auth_ui import render_auth_forms
    _, col, _ = st.columns([1, 2, 1])
    with col:
        render_auth_forms(cookies, key_prefix="profile_gate_")
    st.stop()

render_page_header(
    "Account",
    "Manage your profile, subscription, and preferences.",
    icon="",
)

profile = get_full_profile(user["id"])
if profile is None:
    st.error("Could not load profile. Try refreshing.")
    st.stop()

# ── Plan badge CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
.plan-badge-pro {
    display:inline-block;
    background:linear-gradient(90deg,#7C3AED,#00C8E0);
    color:#fff;
    font-size:0.72rem;font-weight:700;letter-spacing:0.08em;
    padding:3px 12px;border-radius:20px;text-transform:uppercase;
}
.plan-badge-free {
    display:inline-block;
    background:#1E2535;border:1px solid #2A3450;
    color:#8892AA;
    font-size:0.72rem;font-weight:700;letter-spacing:0.08em;
    padding:3px 12px;border-radius:20px;text-transform:uppercase;
}
.section-card {
    background:#12151E;border:1px solid #1E2535;border-radius:10px;
    padding:20px 24px;margin-bottom:20px;
}
.field-label {
    font-size:0.72rem;font-weight:700;color:#8892AA;
    letter-spacing:0.08em;text-transform:uppercase;margin-bottom:4px;
}
.field-value {
    font-size:0.95rem;color:#E8EEFF;
}
</style>
""", unsafe_allow_html=True)

# ── Layout: two columns ────────────────────────────────────────────────────────
left, right = st.columns([3, 2], gap="large")

# ═══════════════════════════════════════════════════════════════════════════════
# LEFT: Profile fields + password
# ═══════════════════════════════════════════════════════════════════════════════
with left:

    # ── Display name ──────────────────────────────────────────────────────────
    st.markdown("### Display Name")
    current_name = profile.get("display_name") or ""
    with st.form("display_name_form"):
        new_name = st.text_input(
            "Display name",
            value=current_name,
            max_chars=64,
            placeholder="How should we call you?",
            label_visibility="collapsed",
        )
        if st.form_submit_button("Save name", use_container_width=True):
            update_display_name(user["id"], new_name)
            st.success("Display name updated.")
            st.rerun()

    st.divider()

    # ── Email ─────────────────────────────────────────────────────────────────
    st.markdown("### Email")
    st.markdown(
        f'<div class="field-value">{profile["email"]}</div>',
        unsafe_allow_html=True,
    )
    st.caption("Email address can't be changed here. Contact support if you need to update it.")

    st.divider()

    # ── Change password ────────────────────────────────────────────────────────
    st.markdown("### Change Password")
    with st.form("change_password_form"):
        current_pw = st.text_input("Current password", type="password")
        new_pw     = st.text_input("New password (min 8 characters)", type="password")
        new_pw2    = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Update password", use_container_width=True):
            if not current_pw or not new_pw:
                st.error("Fill in all three fields.")
            elif new_pw != new_pw2:
                st.error("New passwords don't match.")
            else:
                try:
                    change_password(user["id"], current_pw, new_pw)
                    st.success("Password updated successfully.")
                except AuthError as e:
                    st.error(str(e))

    st.divider()

    # ── Notifications ─────────────────────────────────────────────────────────
    st.markdown("### Notifications")
    is_pro = (profile.get("subscription_tier") or "free") == "pro"
    current_digest = bool(profile.get("digest_opted_in"))

    if is_pro:
        new_digest = st.toggle(
            "Morning digest email (sent ~7 AM ET daily)",
            value=current_digest,
            key="digest_toggle",
        )
        if new_digest != current_digest:
            set_digest_optin(user["id"], new_digest)
            st.success("Preference saved.")
            st.rerun()
    else:
        st.markdown(
            '<span class="plan-badge-free">Pro Feature</span> '
            'Morning digest is available on the Pro plan.',
            unsafe_allow_html=True,
        )

# ═══════════════════════════════════════════════════════════════════════════════
# RIGHT: Plan, referral, account info, logout
# ═══════════════════════════════════════════════════════════════════════════════
with right:

    # ── Plan ──────────────────────────────────────────────────────────────────
    tier = (profile.get("subscription_tier") or "free").lower()
    tier_label = "Pro" if tier == "pro" else "Free"
    badge_class = "plan-badge-pro" if tier == "pro" else "plan-badge-free"

    st.markdown("### Subscription")
    st.markdown(
        f'<span class="{badge_class}">{tier_label}</span>',
        unsafe_allow_html=True,
    )
    st.write("")  # small spacer

    if tier == "pro":
        # Show trial end if still trialing
        trial_end = profile.get("trial_end_at")
        if trial_end:
            try:
                from datetime import datetime, timezone
                te = datetime.fromisoformat(trial_end)
                now = datetime.now(timezone.utc)
                if te > now:
                    days_left = (te - now).days + 1
                    st.caption(f"Trial ends in **{days_left} day(s)** — {te.strftime('%B %-d, %Y')}.")
            except Exception:
                pass

        # Manage subscription via Stripe portal
        customer_id = profile.get("stripe_customer_id") or ""
        if customer_id:
            try:
                from utils.billing import create_portal_session
                import os
                base = os.environ.get("RENDER_EXTERNAL_URL", "https://unstructuredalpha.com")
                portal_url = create_portal_session(customer_id, return_url=f"{base}/Profile")
                st.link_button("Manage Subscription →", portal_url, use_container_width=True)
            except Exception:
                st.caption("To manage billing, visit the Upgrade page.")
                if st.button("Upgrade page →", use_container_width=True, key="goto_upgrade"):
                    st.switch_page("pages/29_Upgrade.py")
        else:
            st.caption("Subscription managed outside Stripe (admin access).")
    else:
        if st.button("Upgrade to Pro", type="primary", use_container_width=True):
            st.switch_page("pages/29_Upgrade.py")
        st.caption("Unlock Factor Exposure, PDF reports, Signal Backtester, and more.")

    st.divider()

    # ── Referral ──────────────────────────────────────────────────────────────
    st.markdown("### Referral")
    try:
        from utils.referral import get_or_create_referral_code, get_referral_stats
        ref_code = get_or_create_referral_code(user["id"])
        import os
        base = os.environ.get("RENDER_EXTERNAL_URL", "https://unstructuredalpha.com")
        ref_url = f"{base}/?ref={ref_code}"

        st.text_input("Your referral link", value=ref_url, disabled=True, key="ref_link_display")
        st.caption("Anyone who signs up with your link gets a 14-day free trial. You get 1 month free when they convert to Pro.")

        stats = get_referral_stats(user["id"])
        pending   = stats.get("pending", 0)
        converted = stats.get("converted", 0)
        rewarded  = stats.get("rewarded", 0)

        c1, c2, c3 = st.columns(3)
        c1.metric("Pending", pending)
        c2.metric("Converted", converted)
        c3.metric("Rewarded", rewarded)
    except Exception:
        st.caption("Referral data unavailable.")

    st.divider()

    # ── Account info ──────────────────────────────────────────────────────────
    st.markdown("### Account")
    created_at = profile.get("created_at", "")
    if created_at:
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(created_at)
            st.caption(f"Member since **{dt.strftime('%B %-d, %Y')}**")
        except Exception:
            pass

    st.caption(f"User ID: `{user['id']}`")

    st.write("")
    if st.button("Log Out", use_container_width=True, key="profile_logout"):
        logout()
        st.rerun()
