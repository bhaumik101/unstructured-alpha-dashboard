"""Architecture checks for the persistent profile and identity experience."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILE = (ROOT / "pages" / "32_Profile.py").read_text(encoding="utf-8")
HEADER = (ROOT / "utils" / "header.py").read_text(encoding="utf-8")
AUTH = (ROOT / "utils" / "auth.py").read_text(encoding="utf-8")


def test_profile_uses_focused_side_sections_instead_of_one_long_page():
    assert 'sections=("Profile & Preferences", "Security", "API Access", "Plan & Referrals")' in PROFILE
    assert 'section_key="profile_section_rail"' in PROFILE
    assert "st.tabs(" not in PROFILE


def test_profile_exposes_functional_customization():
    assert 'with st.form("profile_identity_form")' in PROFILE
    assert 'with st.form("profile_research_preferences_form")' in PROFILE
    assert "save_risk_profile" in PROFILE
    assert "set_digest_optin" in PROFILE
    assert "Risk tolerance" in PROFILE
    assert "Primary time horizon" in PROFILE
    assert "Evidence emphasis" in PROFILE


def test_display_name_updates_the_live_authenticated_session():
    assert 'st.session_state["user"] = {**user, "display_name": saved_name}' in PROFILE
    assert '"display_name": display_name or None' in AUTH
    assert "users.c.display_name" in AUTH


def test_header_uses_display_name_as_the_signed_in_identity():
    assert '_identity_name = (_hdr_user.get("display_name") or "Account").strip()' in HEADER
    assert 'user.get("display_name") or user.get("email", "Account")' in HEADER
    assert "with st.popover(_identity_button" in HEADER
