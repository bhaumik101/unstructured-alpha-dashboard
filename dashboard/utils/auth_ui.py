# utils/auth_ui.py
# Unstructured Alpha — Login/Signup/Email-Verification UI
#
# Per explicit user request, this app no longer gates every page behind a
# forced login wall. Most pages are browsable by anyone; only the
# Watchlist page (inherently per-account) still calls require_login() to
# require one. Everywhere else, app.py calls the non-blocking
# try_restore_session() so a returning logged-in user is still recognized
# (via the "remember me" cookie or an already-active tab session), without
# ever forcing an anonymous visitor through a gate. The top-right account
# widget (render_account_widget(), called from utils/header.py on every
# page) is how an anonymous visitor signs in or creates an account
# voluntarily, from anywhere in the app -- not a forced first step.
#
# st.session_state["user"] is the source of truth for "who's logged in"
# WITHIN the current browser tab session -- but that alone resets on
# every browser restart, which is the exact "log in over and over" problem
# the "remember me" cookie below fixes. Streamlit itself still has no
# built-in cookie API (st.login()/st.user are OIDC-only, delegating to an
# external identity provider like Google -- a different mechanism
# entirely from this app's own email+password accounts, not a drop-in fit
# here), so this uses the third-party streamlit-cookies-manager-v2
# component instead. st.session_state["pending_verification_email"]
# tracks an account that exists but hasn't entered its emailed code yet --
# set right after signup, or when login() reports EmailNotVerifiedError.
#
# Cookie component lifecycle, the part that's easy to get wrong: the
# CookieManager's underlying browser component needs one render round-trip
# before cookies.ready() is True. try_restore_session() returns None if
# not ready yet rather than blocking the page -- a deliberate tradeoff:
# someone with a valid remember-me cookie might see one render pass as
# "not logged in" before the cookie data arrives and the very next rerun
# (e.g. the header widget) picks them up correctly. That's a strictly
# better tradeoff than the old behavior of st.stop()-ing every single page
# load until the cookie component responds, now that pages aren't gated.

import streamlit as st
from streamlit_cookies_manager import CookieManager

from utils.auth import (
    signup, login, verify_email, resend_verification_code, AuthError, EmailNotVerifiedError,
    issue_remember_token, verify_remember_token, revoke_remember_token,
)
from utils.email import EmailSendError

_REMEMBER_COOKIE_NAME = "ua_remember_token"


_COOKIES_SESSION_KEY = "_cookies_this_run"


def init_cookies_for_this_run() -> CookieManager:
    """
    Construct the CookieManager EXACTLY ONCE per script run and cache it in
    session_state for everything else in that same run to read. Caught
    live, not assumed: constructing CookieManager() more than once in a
    single run raises StreamlitDuplicateElementKey (its __init__ registers
    a Streamlit component under a fixed internal key, and Streamlit
    doesn't allow two elements with the same key in one run) -- this bit
    the very first version of the top-right account widget, which called
    get_cookies() independently from both app.py and utils/header.py.
    app.py calls this exactly once, unconditionally, at the very top of
    every run (before pg.run() executes whichever page was selected) --
    that ordering is what guarantees there's always a fresh instance ready
    by the time any page's render_header() needs one.
    """
    cookies = CookieManager()
    st.session_state[_COOKIES_SESSION_KEY] = cookies
    return cookies


def get_cookies() -> CookieManager:
    """
    Read the single CookieManager instance app.py already constructed for
    this run. Every call site EXCEPT app.py's own top-level code should
    use this, not init_cookies_for_this_run() -- calling the constructor
    again mid-run is exactly the bug this split was built to avoid.
    """
    return st.session_state[_COOKIES_SESSION_KEY]


def try_restore_session(cookies: CookieManager) -> dict | None:
    """
    Non-blocking session check -- NEVER renders anything, NEVER calls
    st.stop(). Returns the logged-in user dict if there is one (already
    in this tab's session_state, or recoverable from a valid "remember
    me" cookie), else None. Callers that need to require login should use
    require_login() instead; this is for the common case of "recognize a
    returning user if there is one, but don't force anyone."
    """
    if "user" in st.session_state:
        return st.session_state["user"]

    if not cookies.ready():
        return None

    remember_token = cookies.get(_REMEMBER_COOKIE_NAME)
    if not remember_token:
        return None

    remembered_user = verify_remember_token(remember_token)
    if remembered_user:
        st.session_state["user"] = remembered_user
        st.session_state["_remember_token"] = remember_token
        return remembered_user

    # Stale, expired, or already-revoked -- clear it so this same dead
    # cookie isn't re-checked (and re-found invalid) on every page load.
    del cookies[_REMEMBER_COOKIE_NAME]
    cookies.save()
    return None


def _render_verification_form(cookies: CookieManager, key_prefix: str = "") -> None:
    email = st.session_state["pending_verification_email"]

    # A message queued by the signup handler before routing here (e.g. "the
    # account was created but the email failed to send") -- queued instead
    # of shown directly via st.error() there, because that call immediately
    # follows an st.rerun(): Streamlit reruns restart script execution from
    # scratch, so anything rendered in the OLD run (including an error
    # message) is gone before the user ever sees it. This was caught live,
    # not assumed -- a real first version of this silently swallowed the
    # "email failed to send" warning behind the rerun.
    pending_message = st.session_state.pop("pending_verification_message", None)
    if pending_message:
        st.warning(pending_message)

    st.info(f"We emailed a 6-digit code to **{email}**. Enter it below to finish setting up your account.")

    with st.form(f"{key_prefix}verify_form"):
        code = st.text_input("Verification code", max_chars=6, key=f"{key_prefix}verify_code")
        submitted = st.form_submit_button("Verify", type="primary", use_container_width=True)
    if submitted:
        if not code:
            st.error("Enter the 6-digit code from your email.")
        else:
            try:
                user = verify_email(email, code)
                st.session_state["user"] = user
                # Auto-remember right after verification, no checkbox shown
                # here -- the device that just typed in the emailed code is,
                # by construction, the account owner's own device, so
                # defaulting to "remember this device" is the helpful
                # choice rather than logging them out again moments later.
                token = issue_remember_token(user["id"])
                cookies[_REMEMBER_COOKIE_NAME] = token
                cookies.save()
                st.session_state["_remember_token"] = token
                st.session_state.pop("pending_verification_email", None)
                st.rerun()
            except AuthError as e:
                st.error(str(e))

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Resend code", use_container_width=True, key=f"{key_prefix}resend_code"):
            try:
                resend_verification_code(email)
                st.success("A new code is on its way.")
            except (AuthError, EmailSendError) as e:
                st.error(str(e))
    with col2:
        if st.button("Use a different email", use_container_width=True, key=f"{key_prefix}diff_email"):
            st.session_state.pop("pending_verification_email", None)
            st.rerun()


def render_auth_forms(cookies: CookieManager, key_prefix: str = "") -> None:
    """
    Renders the Log In / Create Account tabs (or, mid-verification, the
    code-entry form) -- WITHOUT calling st.stop() or assuming it owns the
    whole page. Shared by require_login()'s full-page gate (Watchlist) and
    utils.header's top-right popover widget (every other page), so the
    actual form logic exists exactly once. `key_prefix` keeps widget keys
    unique between those two call sites in case both somehow render in the
    same script run.
    """
    if "pending_verification_email" in st.session_state:
        _render_verification_form(cookies, key_prefix)
        return

    tab_login, tab_signup = st.tabs(["Log In", "Create Account"])

    with tab_login:
        with st.form(f"{key_prefix}login_form"):
            email = st.text_input("Email", key=f"{key_prefix}login_email")
            password = st.text_input("Password", type="password", key=f"{key_prefix}login_password")
            remember_me = st.checkbox(
                "Remember me on this device", value=True, key=f"{key_prefix}login_remember_me",
            )
            submitted = st.form_submit_button("Log In", type="primary", use_container_width=True)
        if submitted:
            if not email or not password:
                st.error("Enter both your email and password.")
            else:
                try:
                    user = login(email, password)
                    st.session_state["user"] = user
                    if remember_me:
                        token = issue_remember_token(user["id"])
                        cookies[_REMEMBER_COOKIE_NAME] = token
                        cookies.save()
                        st.session_state["_remember_token"] = token
                    st.rerun()
                except EmailNotVerifiedError:
                    st.session_state["pending_verification_email"] = email.strip().lower()
                    st.rerun()
                except AuthError as e:
                    st.error(str(e))

    with tab_signup:
        with st.form(f"{key_prefix}signup_form"):
            email = st.text_input("Email", key=f"{key_prefix}signup_email")
            password = st.text_input("Password (min 8 characters)", type="password", key=f"{key_prefix}signup_password")
            password2 = st.text_input("Confirm password", type="password", key=f"{key_prefix}signup_password2")
            submitted = st.form_submit_button("Create Account", type="primary", use_container_width=True)
        if submitted:
            if not email or not password:
                st.error("Enter both an email and a password.")
            elif password != password2:
                st.error("Passwords don't match.")
            else:
                try:
                    signup(email, password)
                    st.session_state["pending_verification_email"] = email.strip().lower()
                    st.rerun()
                except EmailSendError as e:
                    # Account was created (signup() only raises this AFTER
                    # the insert succeeds), but the user can't verify yet --
                    # route them to the same screen so "Resend code" can
                    # retry once email sending is actually working. The
                    # warning is QUEUED (read by _render_verification_form
                    # on the next run), not shown directly here -- this
                    # st.rerun() would wipe out an st.error() called
                    # immediately before it, since a rerun restarts script
                    # execution from scratch.
                    st.session_state["pending_verification_email"] = email.strip().lower()
                    st.session_state["pending_verification_message"] = (
                        "Account created, but we couldn't email your verification code right now "
                        f"({e}). This usually means our sending domain is still being verified -- "
                        "try \"Resend code\" again in a little while, or let us know if it keeps failing."
                    )
                    st.rerun()
                except AuthError as e:
                    st.error(str(e))

    st.caption(
        "\"Remember me\" keeps you logged in on this device for 30 days. "
        "Uncheck it on a shared or public computer."
    )


def require_login() -> dict:
    """
    Returns the logged-in user dict ({"id", "email"}) if already
    authenticated. Otherwise renders a full-page login/signup gate (or the
    email-verification step, if mid-signup) and calls st.stop() -- this
    function never returns None; it either returns a real, verified user
    or halts the script. Used ONLY by pages that inherently require an
    account (currently just Watchlist) -- every other page uses the
    non-blocking try_restore_session() instead, since this app no longer
    forces a login wall on first visit.
    """
    cookies = get_cookies()
    user = try_restore_session(cookies)
    if user:
        return user

    if not cookies.ready():
        st.stop()

    st.markdown("""
    <div style="text-align:center; margin-top:40px; margin-bottom:20px;">
        <div style="font-size:2.2rem;font-weight:700;color:#1C2B4A;font-family:Georgia,serif;">
            UNSTRUCTURED <span style="color:#B8860B;">ALPHA</span>
        </div>
        <div style="font-size:0.9rem;color:#8B7355;font-style:italic;font-family:Georgia,serif;">
            Sign in to use your watchlist
        </div>
    </div>
    """, unsafe_allow_html=True)

    _, center, _ = st.columns([1, 2, 1])
    with center:
        render_auth_forms(cookies, key_prefix="gate_")

    st.stop()


def render_account_widget() -> None:
    """
    Persistent, non-blocking sign-in affordance for the top-right of the
    main content area (NOT a full-page gate) -- shows "Logged in as
    {email}" + Log Out for an authenticated visitor, or a compact "Sign
    In / Create Account" popover for an anonymous one. Called from
    utils.header.render_header() on every page, so it's available
    everywhere without any page needing to opt in individually.
    """
    cookies = get_cookies()
    user = try_restore_session(cookies)

    _, widget_col = st.columns([5, 1.4])
    with widget_col:
        if user:
            with st.popover(f"{user['email'].split('@')[0]}", use_container_width=True):
                st.caption(f"Logged in as **{user['email']}**")
                if st.button("Log Out", key="topright_logout", use_container_width=True):
                    logout()
                    st.rerun()
        else:
            with st.popover("Sign In", use_container_width=True):
                render_auth_forms(cookies, key_prefix="widget_")


def logout() -> None:
    """
    Clear the current session's login, and revoke + clear any "remember
    me" cookie too -- so logging out actually ends the persistent session,
    not just the in-tab one. The DB-side revoke always runs regardless of
    cookie-component readiness (it's a plain DB call with no browser
    round-trip dependency); the browser-side cookie deletion is
    best-effort if the component isn't ready, since the token is already
    dead server-side either way. Caller is responsible for st.rerun().
    """
    token = st.session_state.pop("_remember_token", None)
    if token:
        revoke_remember_token(token)
        cookies = get_cookies()
        if cookies.ready():
            del cookies[_REMEMBER_COOKIE_NAME]
            cookies.save()
    st.session_state.pop("user", None)
