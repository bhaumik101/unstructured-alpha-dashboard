"""Regression tests for billing routes, Pro packaging, and provider-aware work."""

from pathlib import Path

from utils import product_metrics
from utils.ratelimit import POLICIES

ROOT = Path(__file__).resolve().parent.parent


def _page(name: str) -> str:
    return (ROOT / "pages" / name).read_text(encoding="utf-8")


def test_upgrade_uses_registered_route_for_all_stripe_returns():
    src = _page("29_Upgrade.py")
    assert 'def _page_url(path: str = "/upgrade-to-pro")' in src
    assert '_page_url("/Upgrade")' not in src
    assert 'success_url=_page_url() + "?stripe_session_id=' in src
    assert 'cancel_url=_page_url() + "?stripe_cancel=1"' in src


def test_referrals_use_registered_upgrade_route():
    src = (ROOT / "utils" / "referral.py").read_text(encoding="utf-8")
    assert '_UPGRADE_PATH = "/upgrade-to-pro"' in src
    assert 'is_valid_referral_code(_ref_code)' in _page("29_Upgrade.py")
    assert 'has_recorded_referral(user["email"])' in _page("29_Upgrade.py")


def test_checkout_has_distributed_abuse_policy():
    assert POLICIES["checkout"] == (5, 900)
    assert 'limit_action(f"u{current_user[\'id\']}", "checkout")' in _page("29_Upgrade.py")


def test_high_value_and_high_cost_pages_are_pro_gated():
    assert 'require_pro(' in _page("35_Signal_Strategy.py")
    assert 'require_pro(' in _page("9_AI_Assistant.py")
    deep = _page("3_Ticker_Deep_Dive.py")
    for section in ("Deep Correlation Scan", "Insider & Short Interest", "13F & Federal Contracts", "Earnings Sentiment"):
        assert section in deep
    assert 'require_pro("Ticker Deep Dive Pro")' in deep


def test_public_proof_surfaces_remain_public():
    for page in ("11_Model_Validation.py", "30_Track_Record_Live.py", "39_How_Signals_Work.py"):
        assert "require_pro(" not in _page(page)


def test_upgrade_marketing_is_registry_backed_and_has_no_fake_testimonials():
    src = _page("29_Upgrade.py")
    assert "ACTIVE_SIGNAL_COUNT" in src and "ACTIVE_SOURCE_COUNT" in src
    assert "What Pro members say" not in src
    assert "Bloomberg terminal does" not in src
    assert product_metrics.ACTIVE_SOURCE_COUNT == 13


def test_deep_dive_only_loads_optional_score_for_optional_views():
    src = _page("3_Ticker_Deep_Dive.py")
    assert '_include_optional_score = section in {"Insider & Short Interest", "13F & Federal Contracts"}' in src
    assert "include_optional=_include_optional_score" in src
