# pages/29_Upgrade.py
# Unstructured Alpha — Investor Pro
#
# WHY THIS WAS REWRITTEN (2026-09-23)
# -----------------------------------
# Walking the funnel as a customer: the marketing site's paid-tier call to
# action, "See Investor Pro", landed here — on 1,069 lines selling the product
# the 2026-09-20 redesign withdrew. "Never miss when the macro around your
# holdings turns." "47 registered signals." "Alerts the moment a Confluence
# Score materially moves." "Validated against forward returns." Every one of
# those is a claim testing did not support, and this was the page a prospect
# reached at the moment they decided whether to pay.
#
# It also promised things that do not exist (Signal Backtester, Pro API,
# Catalyst Command Center, a 7 AM morning digest), quoted prices that disagree
# with /pricing, offered Discord and Slack alerts that were never built, and
# presented a block headed "WHAT PRO MEMBERS SAW AT 7 AM TODAY" with specific
# market claims — social proof for a product that is not being sold.
#
# The route has to stay: Pro gates, referral links and several emails point at
# it, and Stripe's own success_url comes back here. So it is now the honest
# Investor Pro page, and /pricing remains the full plan comparison.
#
# Three states, same as before, and all three had to be rewritten rather than
# trimmed — the success screen alone sent a paying customer to Today's Brief,
# Ticker Deep Dive and Factor Exposure, three pages that carry a "no longer
# maintained" notice.

import streamlit as st

st.set_page_config(page_title="Investor Pro — Unstructured Alpha", layout="wide")

from utils import report_ui as ui  # noqa: E402
from utils.app_theme import product_page_header  # noqa: E402
from utils.auth_ui import get_cookies, try_restore_session  # noqa: E402
from utils.billing import (  # noqa: E402
    check_and_sync_subscription, create_checkout_session, create_portal_session,
    get_stripe_ids, get_user_tier, handle_checkout_success,
)
from utils.header import render_header  # noqa: E402

SUPPORT_EMAIL = "support@unstructuredalpha.com"
REPORT_PAGE = "pages/60_Exposure_Report.py"

render_header("Investor Pro")
st.markdown(ui.REPORT_CSS, unsafe_allow_html=True)

try:
    from utils.instrumentation import record, record_once
except Exception:  # measurement must never break a billing page
    def record(*_a, **_k):
        return None

    def record_once(*_a, **_k):
        return None


def _page_url(path: str = "/upgrade-to-pro") -> str:
    import os

    base = os.environ.get("APP_BASE_URL", "https://app.unstructuredalpha.com").rstrip("/")
    return base + path


cookies = get_cookies()
user = try_restore_session(cookies)

# Fired once per session, not per rerun: Streamlit re-executes the script on
# every widget interaction, and counting those would inflate the top of the
# funnel against a checkout count that can only happen once.
if not st.session_state.get("_pro_page_tracked"):
    st.session_state["_pro_page_tracked"] = True
    try:
        from utils.analytics import Event as _Event, track as _track
        _track(_Event.PRICING_VIEWED, user_id=(user or {}).get("id"))
    except Exception:
        pass

product_page_header(
    "Investor Pro",
    "Everything in the free report, with room for a larger portfolio — and the "
    "features being built next.",
    eyebrow="Your plan",
)

params = st.query_params
stripe_session_id = params.get("stripe_session_id", "")


def _what_pro_is_html(heading: str = "What Investor Pro gives you today") -> str:
    """The truthful list, and the honest separation from what is not built yet.

    Splitting these was the point of the rewrite. The page it replaced ran one
    list of fifteen features, of which most did not exist.
    """
    return (
        '<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
        f'<div class="uar-title">{ui.escape(heading)}</div>'
        '<div class="uar-sub">The measurement is the same one the free report runs. '
        'Pro is about size and, shortly, about being told when something moves.</div>'
        '</div></div><div class="uar-body">'
        '<ul class="uar-tier-list">'
        f'<li>Up to {ui.PRO_MAX_HOLDINGS} holdings per portfolio, instead of {ui.FREE_MAX_HOLDINGS}</li>'
        '<li>Every holding measured on its own, and the holdings behind each exposure</li>'
        '<li>A 90% range and an evidence label on every number</li>'
        '<li>Saved portfolios, and the public methodology and research record</li>'
        '</ul>'
        '<div class="uar-sub uar-tier-kicker">IN DEVELOPMENT — NOT AVAILABLE YET</div>'
        '<ul class="uar-tier-list uar-tier-later">'
        '<li>A weekly &ldquo;what changed&rdquo; email, which says plainly when nothing did</li>'
        '<li>Alerts when an exposure crosses a threshold you set</li>'
        '<li>PDF export and more than one saved portfolio</li>'
        '</ul>'
        '<div class="uar-sub" style="margin-top:12px">Early-access pricing, and it may change. '
        'Nothing here forecasts markets or recommends a security.</div>'
        '</div></div></div>'
    )


# ── State 1: back from Stripe Checkout ──────────────────────────────────────
if stripe_session_id:
    if not user:
        st.error("Your session expired while you were at Stripe. Sign in again (top right) "
                 "and this page will show your plan. Nothing was lost — if the payment went "
                 f"through, it is on your account. Email {SUPPORT_EMAIL} if anything looks wrong.")
        st.stop()

    done_key = f"_stripe_done_{stripe_session_id}"
    if not st.session_state.get(done_key):
        with st.spinner("Confirming your payment with Stripe…"):
            result = handle_checkout_success(stripe_session_id, user["id"])
        st.session_state[done_key] = True
        st.session_state.pop(f"_tier_{user['id']}", None)
        if result.get("ok"):
            record("pro_checkout_completed")
            try:
                from utils.email import send_pro_welcome_email
                send_pro_welcome_email(user["email"])
            except Exception as exc:  # a failed email must not break the receipt
                print(f"[upgrade] Pro welcome email failed: {exc}", flush=True)
    else:
        result = {"ok": True, "tier": get_user_tier(user["id"]), "error": ""}

    if result["ok"]:
        st.success("You're on Investor Pro. Thank you.")
        st.markdown(_what_pro_is_html("What is active on your account now"),
                    unsafe_allow_html=True)
        if st.button("Open the exposure report", type="primary", key="pro_open_report"):
            st.switch_page(REPORT_PAGE)
        st.caption("Manage or cancel your subscription any time from this page.")
        st.query_params.clear()
    else:
        st.error(f"Stripe could not confirm that payment: {result.get('error', 'unknown error')}. "
                 f"Nothing has been changed on your account. Email {SUPPORT_EMAIL} and we will "
                 f"sort it out.")
        if st.button("Try again", key="pro_retry"):
            st.query_params.clear()
            st.rerun()
    ui.render_report_footer()
    st.stop()


# ── State 2: already on Pro ─────────────────────────────────────────────────
tier = "free"
if user:
    cache_key = f"_tier_{user['id']}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = get_user_tier(user["id"])
    tier = st.session_state[cache_key]

if user and tier == "pro":
    customer_id, _sub_id = get_stripe_ids(user["id"])
    st.markdown(
        '<div class="uar"><div class="uar-note uar-note-back">'
        '<b>You are on Investor Pro.</b> Thank you — this is a small product and '
        'early subscriptions are what pays for the next thing on the list.'
        '</div></div>', unsafe_allow_html=True)

    manage_col, sync_col, report_col = st.columns(3)
    if customer_id and manage_col.button("Manage subscription", width="stretch",
                                         key="pro_portal"):
        try:
            portal_url = create_portal_session(customer_id, return_url=_page_url())
            st.link_button("Continue to Stripe", portal_url, type="primary")
            st.caption("Cancel, change your card or download invoices at Stripe.")
        except Exception:
            st.error(f"Stripe's billing portal isn't responding. Nothing has changed on "
                     f"your subscription; try again shortly or email {SUPPORT_EMAIL}.")
    if sync_col.button("Re-check my plan", width="stretch", key="pro_resync"):
        with st.spinner("Asking Stripe…"):
            live = check_and_sync_subscription(user["id"])
        st.session_state[cache_key] = live
        if live == "pro":
            st.success("Confirmed active.")
        else:
            st.warning("Stripe reports no active subscription, so the account is back on Free.")
            st.rerun()
    if report_col.button("Open the exposure report", width="stretch", key="pro_report"):
        st.switch_page(REPORT_PAGE)

    st.markdown(_what_pro_is_html("What your plan includes"), unsafe_allow_html=True)

    # Referrals are real and they work, so they stay. The 14-day trial they
    # promise is honoured by the checkout below.
    try:
        from utils.referral import get_referral_stats
        stats = get_referral_stats(user["id"])
        st.markdown(
            '<div class="uar"><div class="uar-card"><div class="uar-head"><div>'
            '<div class="uar-title">Refer someone, get a free month</div>'
            '<div class="uar-sub">If they subscribe, a month is added to your plan and they '
            'start on a 14-day trial instead of 7.</div></div></div>'
            f'<div class="uar-body"><div class="uar-sub">Referred {stats["total_referred"]} · '
            f'subscribed {stats["total_converted"]} · months earned {stats["months_earned"]}'
            '</div></div></div></div>', unsafe_allow_html=True)
        st.code(stats["link"], language=None)
    except Exception:
        pass  # a referral lookup must never take the billing page down

    ui.render_report_footer()
    st.stop()


# ── State 3: not on Pro ─────────────────────────────────────────────────────
from utils.product_metrics import PRO_PRICE_MONTHLY  # noqa: E402

# A referral has to be verified rather than inferred from a query string, and a
# recorded referral stays valid after navigation drops ?ref=.
from utils.referral import has_recorded_referral, is_valid_referral_code  # noqa: E402

referred = is_valid_referral_code(params.get("ref", ""))
if user and not referred:
    referred = has_recorded_referral(user["email"])
trial_days = 14 if referred else 7

st.markdown(
    f'<div class="uar"><p class="uar-lead">Investor Pro is <b>${PRO_PRICE_MONTHLY} a month</b>, '
    f'with a {trial_days}-day free trial and no commitment. '
    f'{"Your referral gives you 14 days instead of 7. " if referred else ""}'
    'The free report stays free, and there is no card needed to use it.</p></div>',
    unsafe_allow_html=True)
st.markdown(_what_pro_is_html(), unsafe_allow_html=True)

if not user:
    st.info("Create a free account or sign in (top right) to start a trial. "
            "You can measure a portfolio without one.")
    if st.button("Open the free exposure report", key="pro_free_report"):
        st.switch_page(REPORT_PAGE)
elif st.button(f"Start the {trial_days}-day trial", type="primary", key="pro_start"):
    try:
        from utils.ratelimit import limit_action
        allowed, retry_after = limit_action(f"u{user['id']}", "checkout")
    except Exception:
        allowed, retry_after = True, 0
    if not allowed:
        st.warning(f"That's a lot of checkout attempts. Please wait about "
                   f"{retry_after // 60 + 1} minutes and try again.")
    else:
        try:
            url = create_checkout_session(
                user_id=user["id"],
                user_email=user["email"],
                success_url=_page_url() + "?stripe_session_id={CHECKOUT_SESSION_ID}",
                cancel_url=_page_url() + "?stripe_cancel=1",
                trial_days=trial_days,
            )
            record("pro_checkout_started", trial_days=trial_days, referred=bool(referred))
            st.link_button("Continue to secure checkout", url, type="primary")
            st.caption("Payment is handled by Stripe. We never see your card details.")
        except Exception:
            st.error(f"Checkout isn't available right now. Nothing was charged. "
                     f"Please try again shortly, or email {SUPPORT_EMAIL}.")

if params.get("stripe_cancel"):
    st.info("Checkout was cancelled and nothing was charged.")

st.caption("Comparing plans? The full comparison, including the adviser pilot, is on the "
           "pricing page.")
if st.button("See all plans", key="pro_all_plans"):
    st.switch_page("pages/65_Pricing.py")

ui.render_report_footer()
