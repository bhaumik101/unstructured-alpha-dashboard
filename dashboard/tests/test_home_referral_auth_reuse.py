"""The late Home referral card must reuse the established session identity."""

from __future__ import annotations

from pathlib import Path


_HOME = Path(__file__).resolve().parent.parent / "pages" / "home_page.py"


def _referral_section() -> str:
    source = _HOME.read_text(encoding="utf-8")
    return source.split("# ── REFERRAL BANNER", 1)[1].split(
        "# ── ADDITIONAL TOOLS",
        1,
    )[0]


def test_referral_section_reuses_existing_user_and_tier_cache():
    section = _referral_section()

    assert 'st.session_state.get("user")' in section
    assert "effective_is_pro(_ref_user)" in section
    assert "get_referral_stats(_ref_user[\"id\"])" in section


def test_referral_section_does_not_restore_auth_again():
    section = _referral_section()

    assert "get_cookies" not in section
    assert "try_restore_session" not in section
    assert "get_user_tier" not in section
