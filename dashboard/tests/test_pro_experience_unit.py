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
    """A referral's extra trial week must be earned, not claimed in a URL."""
    src = (ROOT / "utils" / "referral.py").read_text(encoding="utf-8")
    assert '_UPGRADE_PATH = "/upgrade-to-pro"' in src
    page = _page("29_Upgrade.py")
    assert "is_valid_referral_code(" in page, "the code in ?ref= must be verified"
    assert 'has_recorded_referral(user["email"])' in page, (
        "a recorded referral must stay valid after navigation drops ?ref="
    )
    assert "trial_days = 14 if referred else 7" in page


def test_checkout_has_distributed_abuse_policy():
    assert POLICIES["checkout"] == (5, 900)
    assert 'limit_action(f"u{user[\'id\']}", "checkout")' in _page("29_Upgrade.py")


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


def test_the_upgrade_page_sells_the_product_that_exists():
    """This page used to sell the one the 2026-09-20 redesign withdrew.

    Found by walking the funnel as a customer: the marketing site's paid CTA,
    "See Investor Pro", landed on 1,069 lines about 47 registered signals,
    Confluence Scores and alerts "validated against forward returns" — at the
    exact moment someone decides whether to pay. It also promised a Signal
    Backtester, a Pro API and a 7 AM digest, none of which exist, and carried a
    block headed "WHAT PRO MEMBERS SAW AT 7 AM TODAY".
    """
    # Comments are stripped first: the file's own header explains what was
    # removed and why, and naming those claims in order to ban them is the
    # opposite of making them.
    src = "\n".join(line for line in _page("29_Upgrade.py").splitlines()
                    if not line.lstrip().startswith("#"))
    retired = ("Confluence Score", "registered signals", "47 signals", "signal flips",
               "Signal Backtester", "Pro API", "morning digest", "Discord", "Slack",
               "WHAT PRO MEMBERS SAW", "What Pro members say", "Bloomberg")
    present = [phrase for phrase in retired if phrase.lower() in src.lower()]
    assert not present, f"the upgrade page still sells the retired product: {present}"

    # And what it does promise has to match the one other place we quote it.
    assert "IN DEVELOPMENT" in src, "features that do not exist yet must say so"
    assert str(product_metrics.PRO_PRICE_MONTHLY) not in src or "PRO_PRICE_MONTHLY" in src, (
        "the price must come from product_metrics, not a literal that can drift"
    )


def test_the_pro_feature_list_describes_features_that_exist():
    """PRO_FEATURES is rendered to prospects on this page and in every Pro
    gate. It named fifteen features, of which most went with the signal
    product and several were never built."""
    from utils.billing import PRO_FEATURES

    joined = " ".join(PRO_FEATURES).lower()
    for gone in ("fama-french", "signal backtester", "options flow", "ai research assistant",
                 "decision cockpit", "catalyst command center", "thesis journal",
                 "morning digest", "watchlist"):
        assert gone not in joined, f"PRO_FEATURES still advertises {gone!r}"
    assert any("holdings" in f.lower() for f in PRO_FEATURES)
    assert any(f.lower().startswith("in development") for f in PRO_FEATURES)


def test_deep_dive_only_loads_optional_score_for_optional_views():
    src = _page("3_Ticker_Deep_Dive.py")
    assert '_include_optional_score = section in {"Insider & Short Interest", "13F & Federal Contracts"}' in src
    assert "include_optional=_include_optional_score" in src


def test_the_sign_in_panel_is_readable_on_the_light_theme():
    """It renders in a BaseWeb portal OUTSIDE .stApp, so every themed rule in
    the app misses it: the panel kept the dark skin's near-black background
    while its text took the light theme's ink. Measured on production — the
    "Log In" and "Create Account" tab labels came out #2c3149 on #0b0d12,
    1.5:1, on the first surface anyone touches to make an account.
    """
    src = (ROOT / "utils" / "auth_ui.py").read_text(encoding="utf-8")
    assert "_AUTH_CSS" in src and "st.markdown(_AUTH_CSS" in src

    block = src[src.index('_AUTH_CSS = """'):src.index('</style>"""')]
    assert ".stApp" not in block, (
        "a .stApp-scoped selector cannot reach the portal the panel renders in"
    )
    for needed in ('[data-testid="stPopoverBody"]', '[data-testid="stTab"] p',
                   'aria-selected="true"'):
        assert needed in block, needed
    # Both themes, or one of them is left broken.
    assert 'html[data-ua-theme="light"]' in block
    assert 'html:not([data-ua-theme="light"])' in block
