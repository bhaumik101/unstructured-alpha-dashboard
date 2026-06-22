# utils/email.py
# Unstructured Alpha — Verification Email Sending (Resend)
#
# Endpoint/payload shape verified live against Resend's published API
# reference before writing this, 2026-06-21:
#   POST https://api.resend.com/emails
#   Authorization: Bearer {api_key}
#   {"from": "...", "to": [...], "subject": "...", "html": "..."}
#   -> {"id": "..."}
# Plain requests.post, not Resend's Python SDK -- consistent with every
# other third-party integration in this codebase (FRED, EIA, SEC, FINRA all
# use requests directly), and avoids adding a dependency just to wrap one
# REST call this small.
#
# Configuration -- environment variable checked FIRST, st.secrets as a
# fallback (same priority order as FRED_API_KEY/EIA_API_KEY in
# utils/fetchers.py and DATABASE_URL in utils/db.py). This matters beyond
# consistency: st.secrets only exists at all under Streamlit Cloud's
# secrets.toml mechanism, so a host without that (Render, Railway, a plain
# VPS) needs the env var path to work, not just a fallback that happens to
# never get reached:
#   RESEND_API_KEY   -- required to actually send mail.
#   RESEND_FROM_EMAIL -- optional; defaults to Resend's own test sender
#     ("onboarding@resend.dev"), which only works for sending TO the email
#     address on the Resend account itself, not arbitrary recipients --
#     real signups need a verified sending domain configured in Resend and
#     that address set here.

import os

import requests
import streamlit as st

_RESEND_API_URL = "https://api.resend.com/emails"
_DEFAULT_FROM = "Unstructured Alpha <onboarding@resend.dev>"


class EmailSendError(Exception):
    """Raised when the verification email genuinely fails to send (bad/missing
    API key, Resend API error) -- distinct from AuthError, since this is an
    infrastructure failure, not a user input mistake."""


def _get_resend_config() -> tuple[str, str]:
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        try:
            api_key = st.secrets.get("RESEND_API_KEY", "")
        except Exception:
            api_key = ""

    from_email = os.environ.get("RESEND_FROM_EMAIL", "")
    if not from_email:
        try:
            from_email = st.secrets.get("RESEND_FROM_EMAIL", _DEFAULT_FROM)
        except Exception:
            from_email = _DEFAULT_FROM
    return api_key, from_email


def send_verification_email(to_email: str, code: str) -> None:
    """Send a 6-digit verification code to to_email. Raises EmailSendError
    if RESEND_API_KEY isn't configured or Resend's API rejects the request.

    TEMPORARY DIAGNOSTIC LOGGING (added 2026-06-22, remove once the "emails
    aren't arriving for arbitrary recipients" issue is confirmed fixed):
    Render's own stdout logs showed NOTHING for a real failed-to-arrive
    signup attempt -- neither a request log nor an exception -- which is
    only possible if this function is silently returning success without
    Resend ever actually receiving/logging the request, or if something
    upstream of this call never reaches it at all. print() output here
    shows up in Render's Logs tab directly, unlike anything raised purely
    inside Streamlit's own UI layer.
    """
    api_key, from_email = _get_resend_config()
    print(f"[email] send_verification_email called: to={to_email!r} from={from_email!r} "
          f"api_key_present={bool(api_key)} api_key_prefix={api_key[:6] if api_key else None!r}")
    if not api_key:
        print("[email] aborting: no RESEND_API_KEY configured")
        raise EmailSendError(
            "No RESEND_API_KEY configured -- add one in Streamlit secrets to send real verification emails."
        )

    html = f"""
    <div style="font-family: Georgia, serif; max-width: 480px;">
        <h2 style="color:#1C2B4A;">Verify your Unstructured Alpha account</h2>
        <p>Enter this code to finish creating your account:</p>
        <div style="font-size:2rem; font-weight:700; letter-spacing:0.2em; color:#B8860B; margin: 16px 0;">
            {code}
        </div>
        <p style="color:#8B7355; font-size:0.85rem;">This code expires in 15 minutes. If you didn't request this, you can ignore this email.</p>
    </div>
    """

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "Your Unstructured Alpha verification code",
                "html": html,
            },
            timeout=15,
        )
        print(f"[email] Resend API responded: status={resp.status_code} body={resp.text[:500]!r}")
        resp.raise_for_status()
        print(f"[email] send succeeded for to={to_email!r}")
    except requests.RequestException as e:
        print(f"[email] send FAILED for to={to_email!r}: {type(e).__name__}: {e}")
        raise EmailSendError(f"Failed to send verification email: {e}") from e
