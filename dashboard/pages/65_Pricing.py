"""Pricing — early-access tiers. Unbuilt features are labelled as in development.

Investor Pro uses the existing live Stripe price. The Advisor tier is a
hand-sold pilot, so it has no checkout.
"""

from __future__ import annotations

import os

import streamlit as st

st.set_page_config(page_title="Pricing — Unstructured Alpha", layout="wide")

from utils import report_ui as ui  # noqa: E402
from utils.app_theme import product_page_header  # noqa: E402
from utils.header import render_header  # noqa: E402

APP_BASE = os.environ.get("APP_BASE_URL", "https://app.unstructuredalpha.com").rstrip("/")
PILOT_EMAIL = "support@unstructuredalpha.com"

render_header("Pricing")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)
try:
    from utils.instrumentation import record, record_once
    record_once("pricing_viewed")
except Exception:
    def record(*_a, **_k):
        return None

product_page_header("Pricing",
                    "Early-access pricing. Prices are being tested with early users and may change.",
                    eyebrow="Plans")


def _tier(name: str, price: str, sub: str, now: list[str], later: list[str],
          *, badge: str = "") -> str:
    """One pricing card. `badge` turns it navy, as on the landing page.

    The landing page features the Advisor pilot, because advisers are the
    customer this product is being built for. The two pages must feature the
    same one or they are selling different things.
    """
    items = "".join(f"<li>{i}</li>" for i in now)
    later_html = ""
    if later:
        later_items = "".join(f"<li>{i}</li>" for i in later)
        later_html = (f'<div class="uar-sub uar-tier-kicker">IN DEVELOPMENT</div>'
                      f'<ul class="uar-tier-list uar-tier-later">{later_items}</ul>')
    badge_html = f'<div class="uar-tier-badge">{badge}</div>' if badge else ""
    feature = " uar-tier-feature" if badge else ""
    return (f'<div class="uar"><div class="uar-card uar-tier{feature}">{badge_html}<div class="uar-body">'
            f'<div class="uar-tier-name">{name}</div>'
            f'<div class="uar-tier-price">{price}</div>'
            f'<div class="uar-sub">{sub}</div>'
            f'<ul class="uar-tier-list">{items}</ul>{later_html}'
            f'</div></div></div>')


free_col, pro_col, adv_col = st.columns(3)
with free_col:
    st.markdown(_tier("Free", "$0", "No card needed", [
        "Exposure report for one portfolio, up to 15 holdings",
        "Holdings behind each exposure",
        "Range and evidence label on every number",
        "Save one portfolio with a free account",
        "Public methodology and research record",
    ], []), unsafe_allow_html=True)
    if st.button("Open the exposure report", key="price_free", width="stretch"):
        st.switch_page("pages/60_Exposure_Report.py")

with pro_col:
    st.markdown(_tier("Investor Pro", "$20 / month", "7-day free trial · cancel anytime", [
        "Measure up to 25 holdings per portfolio",
        "Everything in Free",
    ], [
        "Weekly &ldquo;what changed&rdquo; email",
        "Exposure threshold alerts",
        "PDF export and multiple portfolios",
    ]), unsafe_allow_html=True)
    user = st.session_state.get("user")
    try:
        from utils.billing import effective_is_pro
        already_pro = bool(effective_is_pro(user))
    except Exception:
        already_pro = False
    if already_pro:
        st.success("You're on Investor Pro.")
    elif not user:
        st.info("Sign in or create a free account (top right) to start Investor Pro.")
    elif st.button("Start Investor Pro", type="primary", key="price_pro", width="stretch"):
        try:
            from utils.ratelimit import guard
            allowed, _ = guard("checkout")
        except Exception:
            allowed = True
        if not allowed:
            st.warning("Please wait a few minutes before trying checkout again.")
        else:
            try:
                from utils.billing import create_checkout_session
                url = create_checkout_session(
                    user_id=int(user["id"]),
                    user_email=user.get("email", ""),
                    success_url=f"{APP_BASE}/upgrade-to-pro?stripe_session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{APP_BASE}/pricing?stripe_cancel=1",
                )
                record("pricing_checkout_started")
                st.link_button("Continue to secure checkout", url, type="primary")
            except Exception:
                st.error("Checkout isn't available right now. Nothing was charged; please try again later.")

with adv_col:
    st.markdown(_tier("Advisor pilot", "$149 / month", "Small pilot · first month free", [
        "Reports for multiple client portfolios",
        "Client-ready explanations for review meetings",
        "Built with you: tell us what your clients ask",
    ], [], badge="For advisers"), unsafe_allow_html=True)
    st.link_button("Ask about the pilot", f"mailto:{PILOT_EMAIL}?subject=Advisor%20pilot", width="stretch")

st.caption("Unstructured Alpha is an educational and informational tool, not investment advice.")
ui.render_report_footer()
