"""Account identity, research preferences, security, billing, and referrals."""

from datetime import datetime, timezone
from html import escape
import os

import streamlit as st

st.set_page_config(page_title="My Profile — UA", layout="wide")

from utils.auth import (  # noqa: E402
    AuthError,
    change_password,
    get_full_profile,
    set_digest_optin,
    update_display_name,
)
from utils.auth_ui import (  # noqa: E402
    get_cookies,
    logout,
    render_auth_forms,
    try_restore_session,
)
from utils.header import (  # noqa: E402
    render_footer,
    render_header,
    render_page_header,
    render_sidebar_base,
)
from utils.risk_profile import (  # noqa: E402
    EMPHASES,
    EMPHASIS_LABELS,
    HORIZONS,
    HORIZON_LABELS,
    TOLERANCES,
    TOLERANCE_LABELS,
    get_profile as get_risk_profile,
    save_profile as save_risk_profile,
)
from utils.theme import inject_premium_css  # noqa: E402


render_header("My Profile")
section = render_sidebar_base(
    page_title="My Profile",
    sections=("Profile & Preferences", "Security", "API Access", "Plan & Referrals"),
    section_key="profile_section_rail",
)
inject_premium_css()

cookies = get_cookies()
user = try_restore_session(cookies)
if not user:
    render_page_header(
        "My Profile",
        "Sign in to manage your identity, preferences, and account.",
        icon="",
    )
    st.info("Sign in to view and customize your profile.")
    _, gate, _ = st.columns([1, 2, 1])
    with gate:
        render_auth_forms(cookies, key_prefix="profile_gate_")
    st.stop()

profile = get_full_profile(user["id"])
if profile is None:
    st.error("Could not load your profile. Refresh the page and try again.")
    st.stop()

display_name = (profile.get("display_name") or "").strip()
identity_name = display_name or profile["email"].split("@", 1)[0]
initials = "".join(part[0] for part in identity_name.split()[:2] if part).upper() or "UA"
tier = (profile.get("subscription_tier") or "free").lower()
tier_label = "Pro" if tier == "pro" else "Free"

st.markdown(
    """
    <style>
    .ua-profile-hero {
        display:flex;align-items:center;gap:16px;background:#11151C;
        border:1px solid rgba(255,255,255,.09);border-radius:10px;
        padding:18px 20px;margin:4px 0 20px;
    }
    .ua-profile-avatar {
        width:52px;height:52px;border-radius:10px;background:#202632;
        border:1px solid rgba(255,255,255,.12);display:flex;align-items:center;
        justify-content:center;color:#E7EAF0;font-size:1rem;font-weight:750;
        letter-spacing:.04em;flex:0 0 52px;
    }
    .ua-profile-name {color:#E7EAF0;font-size:1.02rem;font-weight:700;line-height:1.3;}
    .ua-profile-email {color:#8D97A8;font-size:.76rem;margin-top:2px;}
    .ua-profile-plan {
        margin-left:auto;color:#A7B0BF;background:#171C25;border:1px solid rgba(255,255,255,.10);
        border-radius:5px;padding:4px 9px;font-size:.62rem;font-weight:750;
        text-transform:uppercase;letter-spacing:.09em;
    }
    .ua-profile-note {
        color:#A7B0BF;font-size:.78rem;line-height:1.55;background:#11151C;
        border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:12px 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

render_page_header(
    "My Profile",
    "Manage how you appear, how research is personalized, and how your account is secured.",
    icon="",
)
st.markdown(
    f'<div class="ua-profile-hero">'
    f'<div class="ua-profile-avatar">{escape(initials)}</div>'
    f'<div><div class="ua-profile-name">{escape(identity_name)}</div>'
    f'<div class="ua-profile-email">{escape(profile["email"])}</div></div>'
    f'<div class="ua-profile-plan">{tier_label}</div>'
    f'</div>',
    unsafe_allow_html=True,
)


if section == "Profile & Preferences":
    identity_col, preference_col = st.columns([1, 1.15], gap="large")

    with identity_col:
        st.markdown("### Public identity")
        st.caption("This name replaces your email anywhere the product identifies you as signed in.")
        with st.form("profile_identity_form"):
            new_name = st.text_input(
                "Display name",
                value=display_name,
                max_chars=48,
                placeholder="Enter your preferred name",
                help="Use 2–48 characters. Your account email remains private account information.",
            )
            save_identity = st.form_submit_button(
                "Save display name",
                type="primary",
                use_container_width=True,
            )
        if save_identity:
            try:
                saved_name = update_display_name(user["id"], new_name)
                st.session_state["user"] = {**user, "display_name": saved_name}
                st.success("Display name saved across your account.")
                st.rerun()
            except AuthError as exc:
                st.error(str(exc))

        st.divider()
        st.markdown("### Email intelligence")
        current_digest = bool(profile.get("digest_opted_in"))
        if tier == "pro":
            digest_enabled = st.toggle(
                "Morning intelligence digest",
                value=current_digest,
                key="profile_digest_toggle",
                help="Receive the morning signal and watchlist briefing at approximately 7 AM ET.",
            )
            st.caption("Includes signal changes, data coverage, watchlist movement, and direct research links.")
            if digest_enabled != current_digest:
                set_digest_optin(user["id"], digest_enabled)
                st.success("Email preference saved.")
                st.rerun()
        else:
            st.markdown(
                '<div class="ua-profile-note">Morning intelligence email is included with Pro. '
                'Your in-app notification feed remains available on the Free plan.</div>',
                unsafe_allow_html=True,
            )

    with preference_col:
        st.markdown("### Research preferences")
        st.caption(
            "These settings power Your Score and alert relevance. The canonical Confluence Score remains unchanged."
        )
        risk_profile = get_risk_profile(user["id"])
        with st.form("profile_research_preferences_form"):
            risk_tolerance = st.selectbox(
                "Risk tolerance",
                list(TOLERANCES),
                index=list(TOLERANCES).index(risk_profile["tolerance"]),
                format_func=lambda value: TOLERANCE_LABELS[value],
                help="Conservative emphasizes slow macro evidence; aggressive gives price action more weight.",
            )
            time_horizon = st.selectbox(
                "Primary time horizon",
                list(HORIZONS),
                index=list(HORIZONS).index(risk_profile["horizon"]),
                format_func=lambda value: HORIZON_LABELS[value],
                help="Filters personalized evidence by how far ahead each signal historically leads.",
            )
            evidence_emphasis = st.selectbox(
                "Evidence emphasis",
                list(EMPHASES),
                index=list(EMPHASES).index(risk_profile["emphasis"]),
                format_func=lambda value: EMPHASIS_LABELS[value],
                help="Choose whether differentiated insider, 13F, and short-interest evidence participates.",
            )
            save_preferences = st.form_submit_button(
                "Save research preferences",
                use_container_width=True,
            )
        if save_preferences:
            updated_profile = {
                "tolerance": risk_tolerance,
                "horizon": time_horizon,
                "emphasis": evidence_emphasis,
            }
            if save_risk_profile(user["id"], updated_profile):
                st.session_state["_risk_profile"] = updated_profile
                st.success("Research preferences saved.")
                st.rerun()
            else:
                st.error("Could not save research preferences. Try again.")

        st.markdown(
            '<div class="ua-profile-note"><b>Where this applies</b><br>'
            'Ticker Deep Dive personalized scoring, watchlist alert relevance, and research explanations.</div>',
            unsafe_allow_html=True,
        )


elif section == "Security":
    account_col, password_col = st.columns(2, gap="large")

    with account_col:
        st.markdown("### Account email")
        st.text_input(
            "Verified email",
            value=profile["email"],
            disabled=True,
            help="Contact support if you need to move the account to another email address.",
        )
        st.caption("Used only for authentication, billing, and emails you have enabled.")

        st.divider()
        st.markdown("### Session security")
        st.markdown(
            '<div class="ua-profile-note">Logging out revokes this browser’s persistent sign-in token. '
            'Other devices remain signed in until their own token expires or they log out.</div>',
            unsafe_allow_html=True,
        )
        if st.button("Log out this device", key="profile_security_logout", use_container_width=True):
            logout()
            st.rerun()

    with password_col:
        st.markdown("### Change password")
        st.caption("Use at least 8 characters and avoid reusing a password from another service.")
        with st.form("profile_change_password_form"):
            current_password = st.text_input("Current password", type="password")
            new_password = st.text_input("New password", type="password")
            confirm_password = st.text_input("Confirm new password", type="password")
            save_password = st.form_submit_button(
                "Update password",
                type="primary",
                use_container_width=True,
            )
        if save_password:
            if not current_password or not new_password or not confirm_password:
                st.error("Complete all password fields.")
            elif new_password != confirm_password:
                st.error("The new passwords do not match.")
            else:
                try:
                    change_password(user["id"], current_password, new_password)
                    st.success("Password updated successfully.")
                except AuthError as exc:
                    st.error(str(exc))


elif section == "API Access":
    st.markdown("### Pro API access")
    st.caption(
        "Read the latest persisted Confluence Score snapshots from your own tools. "
        "The API never starts a live score calculation and never substitutes estimated data."
    )

    if tier != "pro":
        st.info("Read-only score API access is available with Pro.")
        if st.button("Upgrade to Pro", type="primary", key="profile_api_upgrade"):
            st.switch_page("pages/29_Upgrade.py")
    else:
        from utils.api_access import create_api_key, list_api_keys, revoke_api_key

        _new_raw_key = st.session_state.get("profile_new_api_key")
        if _new_raw_key:
            st.warning(
                "Copy this key now. It is shown only in this browser session and cannot be recovered later."
            )
            st.code(_new_raw_key, language=None)
            if st.button("I have copied the key", key="profile_api_key_copied"):
                st.session_state.pop("profile_new_api_key", None)
                st.rerun()

        api_left, api_right = st.columns([1, 1.15], gap="large")
        with api_left:
            st.markdown("#### Create a key")
            with st.form("profile_api_key_form"):
                _api_key_name = st.text_input(
                    "Key name",
                    placeholder="e.g. Research notebook",
                    max_chars=64,
                    help="Use a name that identifies the integration or device.",
                )
                _create_key = st.form_submit_button(
                    "Create API key", type="primary", use_container_width=True
                )
            if _create_key:
                try:
                    _created_key = create_api_key(user["id"], _api_key_name)
                    st.session_state["profile_new_api_key"] = _created_key["raw_key"]
                    st.rerun()
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))

            st.markdown("#### Request example")
            st.code(
                'curl "https://www.unstructuredalpha.com/api/v1/scores/AAPL" \\\n+  -H "Authorization: Bearer YOUR_API_KEY"',
                language="bash",
            )
            st.caption(
                "Batch endpoint: `/api/v1/scores?tickers=AAPL,MSFT,XOM` · up to 25 tickers · "
                "120 requests per key per hour."
            )

        with api_right:
            st.markdown("#### Active credentials")
            _api_keys = list_api_keys(user["id"])
            _active_keys = [row for row in _api_keys if not row.get("revoked_at")]
            if not _active_keys:
                st.info("No active API keys. Create one to connect an external research workflow.")
            for _key in _active_keys:
                with st.container(border=True):
                    _key_info, _key_action = st.columns([4, 1])
                    _key_info.markdown(f'**{escape(str(_key["name"]))}**')
                    _last_used = str(_key.get("last_used_at") or "Never")[:19].replace("T", " ")
                    _key_info.caption(
                        f'{_key["key_prefix"]}… · Last used: {_last_used}'
                    )
                    if _key_action.button(
                        "Revoke",
                        key=f'profile_revoke_api_{_key["id"]}',
                        use_container_width=True,
                    ):
                        if revoke_api_key(user["id"], _key["id"]):
                            st.success("API key revoked immediately.")
                            st.rerun()

            st.markdown(
                '<div class="ua-profile-note"><b>Security model</b><br>'
                'Keys are stored as irreversible hashes. Revocation is immediate. API responses contain '
                'persisted score snapshots only and do not expose account, billing, or portfolio data.</div>',
                unsafe_allow_html=True,
            )


elif section == "Plan & Referrals":
    plan_col, referral_col = st.columns([1, 1.15], gap="large")

    with plan_col:
        st.markdown("### Subscription")
        st.metric("Current plan", tier_label)
        if tier == "pro":
            trial_end = profile.get("trial_end_at")
            if trial_end:
                try:
                    trial_date = datetime.fromisoformat(trial_end)
                    if trial_date > datetime.now(timezone.utc):
                        days_left = (trial_date - datetime.now(timezone.utc)).days + 1
                        st.caption(f"Trial ends in {days_left} day(s) — {trial_date.strftime('%B %-d, %Y')}.")
                except Exception:
                    pass

            customer_id = profile.get("stripe_customer_id") or ""
            if customer_id:
                try:
                    from utils.billing import create_portal_session

                    base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://unstructuredalpha.com")
                    portal_url = create_portal_session(
                        customer_id,
                        return_url=f"{base_url}/my-profile",
                    )
                    st.link_button("Manage subscription", portal_url, use_container_width=True)
                except Exception:
                    st.caption("Billing management is temporarily unavailable. Try the Upgrade page.")
            else:
                st.caption("This Pro access is managed outside Stripe.")
        else:
            if st.button("Upgrade to Pro", type="primary", use_container_width=True):
                st.switch_page("pages/29_Upgrade.py")
            st.caption("Unlock personalized research, Thesis Journal, exports, alerts, and morning intelligence.")

        st.divider()
        st.markdown("### Account details")
        created_at = profile.get("created_at", "")
        if created_at:
            try:
                joined = datetime.fromisoformat(created_at).strftime("%B %-d, %Y")
                st.write(f"Member since {joined}")
            except Exception:
                pass
        st.caption(f"Account ID: {user['id']}")

    with referral_col:
        st.markdown("### Referral program")
        try:
            from utils.referral import get_or_create_referral_code, get_referral_stats

            referral_code = get_or_create_referral_code(user["id"])
            base_url = os.environ.get("RENDER_EXTERNAL_URL", "https://unstructuredalpha.com")
            referral_url = f"{base_url}/?ref={referral_code}"
            st.text_input(
                "Your referral link",
                value=referral_url,
                disabled=True,
                key="profile_referral_link",
            )
            st.caption(
                "New members receive a 14-day Pro trial. You receive one month of Pro when a referral converts."
            )
            referral_stats = get_referral_stats(user["id"])
            stat_cols = st.columns(3)
            stat_cols[0].metric("Pending", referral_stats.get("pending", 0))
            stat_cols[1].metric("Converted", referral_stats.get("converted", 0))
            stat_cols[2].metric("Rewarded", referral_stats.get("rewarded", 0))
        except Exception:
            st.info("Referral information is temporarily unavailable.")

render_footer("My Profile")
