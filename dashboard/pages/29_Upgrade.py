# pages/29_Upgrade.py
# Unstructured Alpha — Pro Upgrade / Pricing Page
#
# High-conversion pricing page with:
#   - Annual / Monthly toggle (annual highlighted as best value)
#   - 7-day free trial, cancel anytime
#   - Social proof, feature comparison, objection-handling FAQ
#
# Flow states handled:
#   1. ?stripe_session_id=xxx  — returning from Stripe Checkout → verify + upgrade
#   2. User already Pro        — show current plan + Manage Subscription portal
#   3. Free / anonymous        — show pricing page with upgrade CTA

import os

import streamlit as st

from utils.theme import BG_PAGE, BG_CARD, TEXT_PRIMARY, PURPLE, CYAN, GREEN, AMBER, inject_all_css
from utils.product_metrics import ACTIVE_SIGNAL_COUNT, ACTIVE_SOURCE_COUNT

st.set_page_config(
    page_title="Upgrade to Pro — Unstructured Alpha",
    page_icon="",
    layout="centered",
)

from utils.header import render_header, render_footer
from utils.auth_ui import get_cookies, try_restore_session
from utils.billing import (
    get_user_tier, create_checkout_session, handle_checkout_success,
    create_portal_session, get_stripe_ids, check_and_sync_subscription,
    PRO_FEATURES,
)

render_header()
inject_all_css()

# ── Base URL ──────────────────────────────────────────────────────────────────
def _base_url() -> str:
    return os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8501").rstrip("/")

def _page_url(path: str = "/upgrade-to-pro") -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{_base_url()}{normalized}"


# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
/* ── Reset / global ── */
.upgrade-wrap {{ max-width: 860px; margin: 0 auto; }}

/* ── Hero ── */
.hero-eyebrow {{
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.18em;
    text-transform: uppercase; color: {CYAN}; text-align: center;
    margin-bottom: 10px;
}}
.hero-headline {{
    font-size: clamp(1.8rem, 4vw, 2.6rem); font-weight: 900;
    color: {TEXT_PRIMARY}; text-align: center; line-height: 1.15;
    margin-bottom: 12px;
}}
.hero-sub {{
    font-size: 1.0rem; color: #8892B0; text-align: center;
    max-width: 520px; margin: 0 auto 32px;
}}

/* ── Toggle ── */
.toggle-wrap {{
    display: flex; align-items: center; justify-content: center;
    gap: 12px; margin-bottom: 28px;
}}
.toggle-label {{ font-size: 0.9rem; color: #8892B0; font-weight: 500; }}
.toggle-label.active {{ color: {TEXT_PRIMARY}; font-weight: 700; }}
.savings-pill {{
    background: #10261E;
    color: #34D399; font-size: 0.72rem; font-weight: 700;
    padding: 3px 10px; border-radius: 20px; letter-spacing: 0.06em;
    border: 1px solid rgba(52,211,153,0.35);
}}

/* ── Pricing cards ── */
.card-wrap {{
    background: {BG_CARD};
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px; padding: 32px 28px; position: relative;
    transition: transform 0.2s;
}}
.card-wrap.featured {{
    border-color: {PURPLE};
    box-shadow: 0 8px 24px rgba(0,0,0,0.28);
}}
.popular-ribbon {{
    position: absolute; top: -13px; left: 50%; transform: translateX(-50%);
    background: {PURPLE};
    color: #fff; font-size: 0.65rem; font-weight: 800;
    letter-spacing: 0.14em; text-transform: uppercase;
    padding: 4px 18px; border-radius: 20px; white-space: nowrap;
}}
.card-tier {{
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.14em;
    text-transform: uppercase; margin-bottom: 8px;
}}
.card-tier.free  {{ color: #4A5063; }}
.card-tier.pro   {{ color: {PURPLE}; }}
.card-price-big  {{
    font-size: 3rem; font-weight: 900; color: {TEXT_PRIMARY};
    line-height: 1; display: flex; align-items: flex-end; gap: 4px;
}}
.card-price-big .per {{ font-size: 1rem; font-weight: 400; color: #8892B0; margin-bottom: 5px; }}
.card-price-sub  {{ font-size: 0.78rem; color: #4A5063; margin: 6px 0 20px; }}
.card-price-sub.billed-annual {{ color: #34D399; font-weight: 600; }}
.card-divider {{ border: none; border-top: 1px solid rgba(255,255,255,0.06); margin: 20px 0; }}
.feat-item {{
    display: flex; align-items: flex-start; gap: 10px;
    font-size: 0.875rem; color: #B8C0D4; margin-bottom: 11px; line-height: 1.4;
}}
.feat-icon-yes {{ color: {GREEN}; font-size: 0.95rem; flex-shrink: 0; margin-top: 1px; }}
.feat-icon-no  {{ color: #2D3348; font-size: 0.95rem; flex-shrink: 0; margin-top: 1px; }}
.feat-item.locked {{ color: #3A3F52; }}

/* ── Value prop strip ── */
.value-strip {{
    background: rgba(124,58,237,0.07);
    border: 1px solid rgba(124,58,237,0.18);
    border-radius: 12px; padding: 20px 28px;
    display: flex; flex-wrap: wrap; gap: 20px;
    justify-content: space-between; margin: 32px 0;
}}
.value-item {{ text-align: center; flex: 1; min-width: 120px; }}
.value-num  {{ font-size: 1.6rem; font-weight: 800; color: {CYAN}; }}
.value-label {{ font-size: 0.75rem; color: #8892B0; margin-top: 2px; }}

/* ── Trial banner ── */
.trial-bar {{
    background: linear-gradient(90deg, rgba(245,158,11,0.1), rgba(245,158,11,0.05));
    border: 1px solid rgba(245,158,11,0.25);
    border-radius: 8px; padding: 12px 20px;
    display: flex; align-items: center; gap: 12px;
    font-size: 0.85rem; color: {AMBER}; margin-bottom: 24px;
}}

/* ── Testimonials ── */
.testimonial-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 32px 0;
}}
.testimonial {{
    background: {BG_CARD}; border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px; padding: 20px;
}}
.testi-text {{
    font-size: 0.875rem; color: #B8C0D4; line-height: 1.6;
    font-style: italic; margin-bottom: 14px;
}}
.testi-author {{
    font-size: 0.75rem; font-weight: 700; color: {TEXT_PRIMARY};
}}
.testi-role {{ font-size: 0.72rem; color: #4A5063; }}
.stars {{ color: #F59E0B; letter-spacing: 1px; font-size: 0.85rem; margin-bottom: 10px; }}

/* ── Comparison table ── */
.comp-table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
.comp-table th {{
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; color: #4A5063;
    padding: 10px 16px; text-align: left;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}}
.comp-table td {{
    padding: 10px 16px; font-size: 0.875rem; color: #B8C0D4;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    vertical-align: middle;
}}
.comp-table tr:last-child td {{ border-bottom: none; }}
.comp-yes {{ color: {GREEN}; font-weight: 700; }}
.comp-no  {{ color: #2D3348; }}
.comp-pro-col {{ color: {TEXT_PRIMARY}; font-weight: 600; }}

/* ── CTA button area ── */
.cta-area {{ text-align: center; margin: 24px 0 8px; }}
.secure-note {{
    text-align: center; font-size: 0.72rem; color: #3A3F52;
    margin-top: 10px; display: flex; justify-content: center;
    align-items: center; gap: 16px;
}}
.secure-note span {{ display: flex; align-items: center; gap: 4px; }}

/* ── FAQ ── */
.faq-q {{
    font-size: 0.92rem; font-weight: 600; color: {TEXT_PRIMARY};
    margin-bottom: 4px;
}}
.faq-a {{ font-size: 0.875rem; color: #8892B0; line-height: 1.65; }}

/* ── Success / Pro status ── */
.success-box {{
    background: rgba(0,213,102,0.07);
    border: 1px solid rgba(0,213,102,0.25);
    border-radius: 14px; padding: 32px; text-align: center;
    margin-bottom: 28px;
}}
.pro-status-box {{
    background: linear-gradient(135deg, rgba(124,58,237,0.1), rgba(0,200,224,0.05));
    border: 1px solid rgba(124,58,237,0.3);
    border-radius: 14px; padding: 28px 32px; margin-bottom: 28px;
}}
</style>
""", unsafe_allow_html=True)

# ── Auth ──────────────────────────────────────────────────────────────────────
cookies = get_cookies()
user    = try_restore_session(cookies)

# ── State 1: Returning from Stripe Checkout ───────────────────────────────────
params = st.query_params
stripe_session_id = params.get("stripe_session_id", "")

# Referral eligibility must be verified, not inferred from an arbitrary query
# string. A recorded referral remains eligible if navigation removed ?ref=.
from utils.referral import is_valid_referral_code, has_recorded_referral
_ref_code = params.get("ref", "")
_is_referred = is_valid_referral_code(_ref_code)
if user and not _is_referred:
    _is_referred = has_recorded_referral(user["email"])
_trial_days = 14 if _is_referred else 7


def _create_limited_checkout(current_user: dict, selected_plan: str, trial_days: int) -> str:
    """Create at most a small number of Stripe sessions per user/window."""
    from utils.ratelimit import limit_action
    allowed, retry_after = limit_action(f"u{current_user['id']}", "checkout")
    if not allowed:
        raise RuntimeError(
            f"Too many checkout attempts. Please wait about {retry_after // 60 + 1} minutes and try again."
        )
    return create_checkout_session(
        user_id=current_user["id"],
        user_email=current_user["email"],
        success_url=_page_url() + "?stripe_session_id={CHECKOUT_SESSION_ID}",
        cancel_url=_page_url() + "?stripe_cancel=1",
        plan=selected_plan,
        trial_days=trial_days,
    )

if stripe_session_id:
    if not user:
        st.error("Session expired. Please log in again.")
        st.stop()

    already_processed = st.session_state.get(f"_stripe_done_{stripe_session_id}", False)
    if not already_processed:
        with st.spinner("Verifying your payment with Stripe…"):
            result = handle_checkout_success(stripe_session_id, user["id"])
        st.session_state[f"_stripe_done_{stripe_session_id}"] = True
        st.session_state.pop(f"_tier_{user['id']}", None)
        # Send Pro onboarding guide email (fire-and-forget, never blocks UI)
        if result.get("ok"):
            try:
                from utils.email import send_pro_welcome_email
                send_pro_welcome_email(user["email"])
            except Exception as _e:
                print(f"[upgrade] Pro welcome email failed: {_e}", flush=True)
    else:
        result = {"ok": True, "tier": get_user_tier(user["id"]), "error": ""}

    if result["ok"]:
        st.markdown(f"""
        <div class="success-box">
            <div style="font-size:3rem;margin-bottom:14px;"></div>
            <div style="font-size:1.6rem;font-weight:900;
                        background:linear-gradient(135deg,#00D566,{CYAN});
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                        background-clip:text;margin-bottom:10px;">
                Welcome to Pro.
            </div>
            <div style="font-size:0.95rem;color:#8892B0;max-width:480px;margin:0 auto 20px;line-height:1.6;">
                All 47 signals and every Pro feature are active on your account right now.
                Your <strong style="color:#E8EEFF;">morning digest</strong> email arrives
                tomorrow at 7 AM ET — you're already opted in.
            </div>
            <div style="display:flex;justify-content:center;gap:24px;flex-wrap:wrap;
                        font-size:0.8rem;color:#4A5063;margin-bottom:4px;">
                <span>✓ Morning digest — enabled</span>
                <span>✓ Unlimited watchlist</span>
                <span>✓ Factor Exposure</span>
                <span>✓ Signal Backtester</span>
            </div>
        </div>
        <div style="font-size:0.88rem;font-weight:700;color:#8892B0;
                    text-align:center;margin:0 0 16px;letter-spacing:0.06em;
                    text-transform:uppercase;">
            Start here →
        </div>
        """, unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
            <div style="background:{BG_CARD};border:1px solid rgba(255,255,255,0.08);
                        border-radius:10px;padding:16px;text-align:center;height:110px;
                        display:flex;flex-direction:column;justify-content:center;">
                <div style="font-size:1.5rem;margin-bottom:6px;"></div>
                <div style="font-size:0.8rem;font-weight:700;color:#E8EEFF;">Today's Brief</div>
                <div style="font-size:0.72rem;color:#4A5063;margin-top:4px;">
                    See what signals flipped overnight
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Open Today's Brief", use_container_width=True, type="primary", key="cta_brief"):
                st.switch_page("pages/2_Today_Digest.py")
        with col2:
            st.markdown(f"""
            <div style="background:{BG_CARD};border:1px solid rgba(124,58,237,0.3);
                        border-radius:10px;padding:16px;text-align:center;height:110px;
                        display:flex;flex-direction:column;justify-content:center;">
                <div style="font-size:1.5rem;margin-bottom:6px;"></div>
                <div style="font-size:0.8rem;font-weight:700;color:#E8EEFF;">Ticker Deep Dive</div>
                <div style="font-size:0.72rem;color:#4A5063;margin-top:4px;">
                    Run any ticker through all 47 signals
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Open Deep Dive", use_container_width=True, key="cta_tdd"):
                st.switch_page("pages/3_Ticker_Deep_Dive.py")
        with col3:
            st.markdown(f"""
            <div style="background:{BG_CARD};border:1px solid rgba(0,200,224,0.2);
                        border-radius:10px;padding:16px;text-align:center;height:110px;
                        display:flex;flex-direction:column;justify-content:center;">
                <div style="font-size:1.5rem;margin-bottom:6px;"></div>
                <div style="font-size:0.8rem;font-weight:700;color:#E8EEFF;">Factor Exposure</div>
                <div style="font-size:0.72rem;color:#4A5063;margin-top:4px;">
                    Pro-only Fama-French regression
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Open Factor Exposure", use_container_width=True, key="cta_factor"):
                st.switch_page("pages/27_Factor_Exposure.py")

        st.query_params.clear()
    else:
        st.error(f"Payment verification failed: {result['error']}. Contact support at bpgiri2005@gmail.com.")
        if st.button("Try again"):
            st.query_params.clear()
            st.rerun()
    st.stop()

# ── State 2: Already Pro ──────────────────────────────────────────────────────
current_tier = "free"
if user:
    cache_key = f"_tier_{user['id']}"
    if cache_key not in st.session_state:
        st.session_state[cache_key] = get_user_tier(user["id"])
    current_tier = st.session_state[cache_key]

    if current_tier == "pro":
        customer_id, sub_id = get_stripe_ids(user["id"])
        st.markdown(f"""
        <div class="pro-status-box">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
                <span style="font-size:1.8rem;"></span>
                <div>
                    <div style="font-size:1.15rem;font-weight:800;color:{TEXT_PRIMARY};">
                        You're on Pro
                        <span style="font-size:0.68rem;font-weight:700;padding:3px 10px;border-radius:20px;
                               background:linear-gradient(90deg,{PURPLE},{CYAN});color:#fff;
                               letter-spacing:0.1em;margin-left:8px;vertical-align:middle;">ACTIVE</span>
                    </div>
                    <div style="font-size:0.85rem;color:#8892B0;margin-top:4px;">
                        All Pro features are unlocked. Thank you for your support.
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        col1, col2 = st.columns([1, 1])
        with col1:
            if customer_id and st.button("Manage Subscription ↗", use_container_width=True, type="primary"):
                try:
                    portal_url = create_portal_session(customer_id, return_url=_page_url())
                    st.markdown(f"""
                    <script>window.open("{portal_url}", "_blank");</script>
                    <div style="font-size:0.85rem;color:{CYAN};">
                        Opening Stripe portal…&nbsp;<a href="{portal_url}" target="_blank">Click here</a> if it didn't open.
                    </div>
                    """, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Could not open portal: {e}")
        with col2:
            if st.button("Re-sync subscription status", use_container_width=True):
                with st.spinner("Checking Stripe…"):
                    live_tier = check_and_sync_subscription(user["id"])
                    st.session_state[cache_key] = live_tier
                if live_tier == "pro":
                    st.success("✓ Subscription confirmed active.")
                else:
                    st.warning("Subscription no longer active — downgraded to Free.")
                    st.rerun()

        st.markdown("### Your Pro workspace")
        _p1, _p2, _p3, _p4 = st.columns(4)
        if _p1.button("Deep Research", use_container_width=True, key="pro_deep"):
            st.switch_page("pages/3_Ticker_Deep_Dive.py")
        if _p2.button("Signal Backtests", use_container_width=True, key="pro_backtest"):
            st.switch_page("pages/35_Signal_Strategy.py")
        if _p3.button("Portfolio Intelligence", use_container_width=True, key="pro_portfolio"):
            st.switch_page("pages/44_Portfolio_Suite.py")
        if _p4.button("AI Assistant", use_container_width=True, key="pro_ai"):
            st.switch_page("pages/9_AI_Assistant.py")

        # ── Referral section (Pro users only) ────────────────────────────────
        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        try:
            from utils.referral import get_referral_stats
            _ref_stats = get_referral_stats(user["id"])
            _ref_link  = _ref_stats["link"]
            _ref_code_display = _ref_stats["code"]
            _ref_referred  = _ref_stats["total_referred"]
            _ref_converted = _ref_stats["total_converted"]
            _ref_earned    = _ref_stats["months_earned"]

            st.markdown(f"""
            <div style="background:linear-gradient(135deg,rgba(124,58,237,0.10),rgba(0,200,224,0.05));
                        border:1px solid rgba(124,58,237,0.28);border-radius:14px;
                        padding:24px 28px;font-family:Inter,sans-serif;">
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
                    <span style="font-size:1.4rem;"></span>
                    <span style="font-size:1.0rem;font-weight:800;color:#E8EEFF;">
                        Refer a friend — earn a free month
                    </span>
                </div>
                <div style="font-size:0.82rem;color:#8892B0;margin-bottom:16px;line-height:1.6;">
                    Share your link. When a friend signs up and goes Pro,
                    <strong style="color:#E8EEFF;">you get one free month</strong> added to your subscription.
                    They get a <strong style="color:#00D566;">14-day free trial</strong> instead of 7.
                </div>
                <div style="background:rgba(0,0,0,0.25);border:1px solid rgba(255,255,255,0.08);
                            border-radius:8px;padding:10px 14px;font-family:monospace;
                            font-size:0.80rem;color:#A78BFA;word-break:break-all;margin-bottom:12px;">
                    {_ref_link}
                </div>
                <div style="display:flex;gap:20px;flex-wrap:wrap;margin-top:4px;">
                    <div style="text-align:center;">
                        <div style="font-size:1.4rem;font-weight:900;color:#E8EEFF;">
                            {_ref_referred}
                        </div>
                        <div style="font-size:0.70rem;color:#4A5063;font-weight:600;
                                    letter-spacing:0.07em;text-transform:uppercase;">Referred</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:1.4rem;font-weight:900;color:#00D566;">
                            {_ref_converted}
                        </div>
                        <div style="font-size:0.70rem;color:#4A5063;font-weight:600;
                                    letter-spacing:0.07em;text-transform:uppercase;">Converted</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:1.4rem;font-weight:900;color:#A78BFA;">
                            {_ref_earned}
                        </div>
                        <div style="font-size:0.70rem;color:#4A5063;font-weight:600;
                                    letter-spacing:0.07em;text-transform:uppercase;">Months earned</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Copy-link button (uses Streamlit's clipboard mechanism via st.code)
            st.code(_ref_link, language=None)
            st.caption("Use the copy control to copy your referral link.")

        except Exception as _ref_err:
            pass  # never block the Pro dashboard over a referral lookup error

        st.stop()

# ── State 3: Pricing Page ─────────────────────────────────────────────────────

# Plan toggle in session_state
if "upgrade_plan" not in st.session_state:
    st.session_state.upgrade_plan = "annual"   # default to annual (best value)

# ── Hero section ──────────────────────────────────────────────────────────────
st.markdown("""
<div style="height:8px"></div>
<div class="hero-eyebrow">Unstructured Alpha Pro</div>
<div class="hero-headline">Never miss when the macro<br>around your holdings turns.</div>
<div class="hero-sub">
    Free shows you the macro backdrop right now. Pro watches it for you —
    continuously monitoring every holding and alerting you the moment a
    Confluence Score materially moves or a signal flips, so a shift in the
    backdrop around one of your stocks never slips by while you're not looking.
</div>
""", unsafe_allow_html=True)

# ── Stats strip ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="value-strip" style="position:relative;">
    <div class="value-item ua-kpi-animate">
        <div class="value-num">{ACTIVE_SIGNAL_COUNT}</div>
        <div class="value-label">Registered signals</div>
    </div>
    <div class="value-item ua-kpi-animate">
        <div class="value-num" style="color:{GREEN};">{_trial_days}</div>
        <div class="value-label">Day free trial</div>
    </div>
    <div class="value-item ua-kpi-animate">
        <div class="value-num" style="color:{CYAN};">{ACTIVE_SOURCE_COUNT}</div>
        <div class="value-label">Source families</div>
    </div>
    <div class="value-item ua-kpi-animate">
        <div class="value-num" style="color:{GREEN};">$0</div>
        <div class="value-label">Due today</div>
    </div>
</div>
<div style="display:flex;justify-content:center;gap:16px;margin-top:12px;flex-wrap:wrap;">
    <div class="ua-guarantee">
        48-hour money-back guarantee
    </div>
    <div class="ua-guarantee" style="color:#00C8E0;background:rgba(0,200,224,0.06);
         border-color:rgba(0,200,224,0.22);">
         Payments secured by Stripe
    </div>
    <div class="ua-guarantee" style="color:#A78BFA;background:rgba(124,58,237,0.06);
         border-color:rgba(124,58,237,0.22);">
        No long-term commitment
    </div>
</div>
""", unsafe_allow_html=True)

# ── "Why not just use Bloomberg/Reddit" objection block ──────────────────────
st.markdown(f"""
<div style="background:rgba(18,21,30,0.72);border:1px solid rgba(255,255,255,0.07);
            border-radius:14px;padding:22px 28px;margin:8px 0 28px;
            font-family:Inter,sans-serif;">
  <div style="font-size:0.65rem;font-weight:700;letter-spacing:0.16em;color:#6B7FBF;
              text-transform:uppercase;margin-bottom:14px;">
    How this is different from what you already use
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;flex-wrap:wrap;">
    <div>
      <div style="font-size:0.78rem;font-weight:700;color:#E8EEFF;margin-bottom:5px;">vs. Bloomberg Terminal</div>
      <div style="font-size:0.74rem;color:#8892AA;line-height:1.55;">
        Bloomberg shows you the same data every other institutional player sees.
        Unstructured Alpha aggregates <em>signals from that data</em> — pre-scored,
        correlated to specific tickers, validated against forward returns.
        In a focused research workflow built for individual investors and small teams.
      </div>
    </div>
    <div>
      <div style="font-size:0.78rem;font-weight:700;color:#E8EEFF;margin-bottom:5px;">vs. Reddit / StockTwits</div>
      <div style="font-size:0.74rem;color:#8892AA;line-height:1.55;">
        Those surfaces amplify narrative. This surface shows primary-source data:
        what insiders are filing with the SEC, what the FOMC minutes say, how
        EIA crude inventory draws compare to the 52-week trend. No sentiment noise.
      </div>
    </div>
    <div>
      <div style="font-size:0.78rem;font-weight:700;color:#E8EEFF;margin-bottom:5px;">vs. any stock screener</div>
      <div style="font-size:0.74rem;color:#8892AA;line-height:1.55;">
        Screeners filter on price and fundamentals — things already priced in.
        The Confluence Score measures how macro and alternative evidence align
        with a ticker, with validation results and methodology visible in-product.
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Billing toggle ────────────────────────────────────────────────────────────
col_l, col_m, col_r = st.columns([1.2, 1.2, 1.2])
with col_l:
    if st.button(
        "Monthly — $20/mo",
        use_container_width=True,
        type="secondary" if st.session_state.upgrade_plan == "annual" else "primary",
        key="toggle_monthly",
    ):
        st.session_state.upgrade_plan = "monthly"
        st.rerun()
with col_m:
    if st.button(
        "  Annual  —  Save 20% ($192/yr)  ✦ BEST VALUE",
        use_container_width=True,
        type="primary" if st.session_state.upgrade_plan == "annual" else "secondary",
        key="toggle_annual",
    ):
        st.session_state.upgrade_plan = "annual"
        st.rerun()
with col_r:
    st.markdown("""
    <div style="padding-top:10px;font-size:0.78rem;color:#34D399;font-weight:700;">
        ✦ Annual saves $48/year<br>
        <span style="color:#4A5063;font-weight:400;">(billed $192 once · 2 months free)</span>
    </div>
    """, unsafe_allow_html=True)

plan = st.session_state.upgrade_plan
monthly_price  = "$20" if plan == "monthly" else "$16"
billing_note   = "per month, billed monthly" if plan == "monthly" else "per month · $192 billed annually"
billed_class   = "" if plan == "monthly" else "billed-annual"

# ── Pricing cards ──────────────────────────────────────────────────────────────
st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
col_free, col_pro = st.columns(2, gap="large")

FREE_FEATS = [
    ("Signal Dashboard — 47 macro signals scored 0–100", True),
    ("Today's Brief — daily regime + signal flip summary", True),
    ("Ticker Deep Dive — confluence score for any stock", True),
    ("Congress Trade Tracker — recent legislator filings", True),
    ("Watchlist — track up to 5 tickers with live scores", True),
    ("Morning email digest — personalized signal brief", False),
    ("Factor Exposure — Fama-French regression per ticker", False),
    ("Signal Backtester — test custom signal combos", False),
    ("Portfolio Intelligence — weighted exposure and executive review", False),
    ("Unlimited watchlist tickers", False),
]

PRO_FEATS = [
    "Continuous watchlist monitoring — we watch the macro around your holdings when you're not there",
    "Alerts when a Confluence Score materially moves or a signal flips — email + Discord + Slack",
    "Portfolio macro-exposure shifts, flagged as they happen",
    "Portfolio Review — cached executive read of concentration, coverage, and personalized score risk",
    "Portfolio Fit Lab — simulate candidate impact before changing your actual holdings",
    "Decision Queue — evidence-ranked daily triage across holdings, catalysts, and theses",
    "Catalyst Command Center — rank verified events by affected portfolio weight and save review plans",
    "Read-only Pro API — integrate persisted score snapshots into your own research workflow",
    "Personalized 7 AM morning digest on your holdings",
    "Score history + 30-day sparklines + factor exposure",
    "Signal Backtester — long/short returns for any signal combo",
    "Unlimited watchlist tickers",
    "Everything in Free · priority support",
]

with col_free:
    feat_rows = "".join([
        f'<div class="feat-item {"" if ok else "locked"}">'
        f'<span class="feat-icon-{"yes" if ok else "no"}">{"✓" if ok else "✗"}</span>'
        f'<span>{feat}</span></div>'
        for feat, ok in FREE_FEATS
    ])
    current_badge = '<div style="margin-top:16px;font-size:0.8rem;color:#4A5063;text-align:center;">← Your current plan</div>' if user else ""
    st.markdown(f"""
    <div class="card-wrap">
        <div class="card-tier free">Free</div>
        <div style="display:flex;align-items:flex-end;gap:4px;margin-bottom:4px;">
            <div style="font-size:3rem;font-weight:900;color:{TEXT_PRIMARY};line-height:1;">$0</div>
            <div style="font-size:1rem;color:#8892B0;margin-bottom:6px;">/month</div>
        </div>
        <div class="card-price-sub">Forever free. No card needed.</div>
        <hr class="card-divider">
        {feat_rows}
        {current_badge}
    </div>
    """, unsafe_allow_html=True)

with col_pro:
    feat_rows_pro = "".join([
        f'<div class="feat-item"><span class="feat-icon-yes">✓</span><span>{feat}</span></div>'
        for feat in PRO_FEATS
    ])
    st.markdown(f"""
    <div class="card-wrap featured">
        <div class="popular-ribbon">✦ MOST POPULAR</div>
        <div class="card-tier pro">Pro</div>
        <div style="display:flex;align-items:flex-end;gap:4px;margin-bottom:4px;">
            <div style="font-size:3rem;font-weight:900;color:{TEXT_PRIMARY};line-height:1;">{monthly_price}</div>
            <div style="font-size:1rem;color:#8892B0;margin-bottom:6px;">/month</div>
        </div>
        <div class="card-price-sub {billed_class}">{billing_note}</div>
        <hr class="card-divider" style="border-color:rgba(124,58,237,0.2);">
        {feat_rows_pro}
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ── CTA ────────────────────────────────────────────────────────────────────────
trial_copy = f"{_trial_days}-day free trial included — $0 charged today"
btn_label  = f"  Start {_trial_days}-Day Free Trial  →  then {monthly_price}/mo" + (" · $192/yr" if plan == "annual" else "")

st.markdown(f"""
<div class="trial-bar">
    <span style="font-size:1.1rem;"></span>
    <span><strong>{trial_copy}</strong> · Cancel any time before day {_trial_days} at no charge.</span>
</div>
""", unsafe_allow_html=True)

if not user:
    _, col, _ = st.columns([0.4, 1.4, 0.4])
    with col:
        st.markdown("""
        <div style="text-align:center;font-size:0.9rem;color:#8892B0;margin-bottom:12px;">
            Create a free account first — it takes 30 seconds.
        </div>
        """, unsafe_allow_html=True)
        if st.button("Create Free Account to Start Trial →", use_container_width=True, type="primary"):
            st.switch_page("pages/home_page.py")
        st.markdown("""
        <div class="secure-note">
            <span>Secured by Stripe</span>
            <span>Cancel anytime</span>
            <span>No spam</span>
        </div>
        """, unsafe_allow_html=True)
else:
    _, col, _ = st.columns([0.4, 1.4, 0.4])
    with col:
        checkout_disabled = False
        btn_display = btn_label

        try:
            from utils.billing import get_stripe_price_id as _check_pid
            _check_pid(plan)
        except RuntimeError:
            checkout_disabled = True
            btn_display = "Stripe not configured yet"

        if st.button(btn_display, type="primary", use_container_width=True, disabled=checkout_disabled):
            try:
                checkout_url = _create_limited_checkout(user, plan, _trial_days)
                st.markdown(
                    f'<meta http-equiv="refresh" content="0; url={checkout_url}">',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'Redirecting to Stripe Checkout… <a href="{checkout_url}">Click here</a> if not redirected.',
                    unsafe_allow_html=True,
                )
            except RuntimeError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Could not create checkout session: {e}")

        st.markdown("""
        <div class="secure-note">
            <span>Secured by Stripe</span>
            <span>Cancel anytime</span>
            <span>Refund within 48h if unsatisfied</span>
        </div>
        """, unsafe_allow_html=True)

# ── Cancel return ─────────────────────────────────────────────────────────────
if params.get("stripe_cancel"):
    st.info("No worries — you weren't charged. The trial is here whenever you're ready.")
    st.query_params.clear()

# ── LOSS AVERSION: "What Pro saw this morning" ──────────────────────────────
st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
st.markdown(f"""
<div style="background:rgba(124,58,237,0.06);border:1px solid rgba(124,58,237,0.20);
            border-radius:16px;padding:26px 30px;font-family:Inter,sans-serif;
            position:relative;overflow:hidden;">
    <div style="position:absolute;top:0;left:0;right:0;height:1px;
                background:linear-gradient(90deg,transparent,rgba(124,58,237,0.5),
                rgba(0,200,224,0.4),transparent);"></div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;">
        <span class="ua-pulse-dot" style="background:{PURPLE};"></span>
        <span style="font-size:0.60rem;letter-spacing:0.16em;font-weight:700;color:{PURPLE};">
            WHAT PRO MEMBERS SAW AT 7 AM TODAY
        </span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px;">
        <div style="background:rgba(255,68,68,0.07);border:1px solid rgba(255,68,68,0.20);
                    border-radius:10px;padding:14px 16px;border-left:3px solid #FF4444;">
            <div style="font-size:0.58rem;color:#FF4444;font-weight:700;letter-spacing:0.12em;
                        margin-bottom:4px;"> BEARISH FLIP</div>
            <div style="font-size:0.88rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">HY Credit Spreads</div>
            <div style="font-size:0.74rem;color:#8892AA;line-height:1.5;">Widened 8 bps overnight —
            score dropped below 40 for first time in 23 days</div>
        </div>
        <div style="background:rgba(0,213,102,0.06);border:1px solid rgba(0,213,102,0.18);
                    border-radius:10px;padding:14px 16px;border-left:3px solid #00D566;">
            <div style="font-size:0.58rem;color:#00D566;font-weight:700;letter-spacing:0.12em;
                        margin-bottom:4px;"> BULLISH SIGNAL</div>
            <div style="font-size:0.88rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">EIA Crude Draw Streak</div>
            <div style="font-size:0.74rem;color:#8892AA;line-height:1.5;">7th consecutive weekly draw.
            XOM, CVX flagged as macro tailwind names.</div>
        </div>
    </div>
    <div style="font-size:0.78rem;color:#6B7FBF;line-height:1.6;border-top:1px solid rgba(255,255,255,0.06);
                padding-top:14px;">
        Pro members received this at 7 AM ET with signal-by-signal changes, portfolio impact, and
        the week's top convergence events.
        <span style="color:{PURPLE};font-weight:700;">You didn't get it today.</span>
        <span style="color:#E8EEFF;"> The trial is free — the brief starts tomorrow morning.</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Verifiable Pro workflow ───────────────────────────────────────────────────
st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
st.markdown(f"""
<div style="font-size:1.2rem;font-weight:800;color:{TEXT_PRIMARY};text-align:center;
            margin-bottom:22px;letter-spacing:-0.3px;">
    A complete research workflow, not a collection of claims
</div>
<div class="testimonial-grid">
    <div class="ua-testi">
        <div class="ua-testi-stars">DISCOVER</div>
        <div class="ua-testi-quote">
            Rank ideas using {ACTIVE_SIGNAL_COUNT} registered signals, alternative-data
            evidence, unusual options activity, and macro-aware stock screening.
        </div>
    </div>
    <div class="ua-testi">
        <div class="ua-testi-stars">INVESTIGATE</div>
        <div class="ua-testi-quote">
            Use Deep Correlation, SEC insider filings, FINRA short interest, curated 13F
            holdings, federal awards, and earnings sentiment from {ACTIVE_SOURCE_COUNT} source families.
        </div>
    </div>
    <div class="ua-testi">
        <div class="ua-testi-stars">TEST</div>
        <div class="ua-testi-quote">
            Validate hypotheses with configurable, point-in-time signal backtests,
            transaction costs, benchmark comparisons, and public model-validation evidence.
        </div>
    </div>
    <div class="ua-testi">
        <div class="ua-testi-stars">MONITOR</div>
        <div class="ua-testi-quote">
            Track portfolio factor exposure, watchlists, morning signal changes, and
            exportable research reports while the AI assistant retains live signal context.
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Feature comparison table ──────────────────────────────────────────────────
st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
st.markdown(f"""
<div style="font-size:1.15rem;font-weight:800;color:{TEXT_PRIMARY};text-align:center;margin-bottom:20px;">
    Complete feature comparison
</div>
<table class="comp-table">
<thead>
<tr>
    <th style="width:55%">Feature</th>
    <th style="width:20%;text-align:center;">Free</th>
    <th style="width:25%;text-align:center;color:{PURPLE};">Pro</th>
</tr>
</thead>
<tbody>
<tr>
    <td>Signal Dashboard — {ACTIVE_SIGNAL_COUNT} macroeconomic signals</td>
    <td style="text-align:center;" class="comp-yes">✓</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Ticker Deep Dive — any stock, any signal</td>
    <td style="text-align:center;" class="comp-yes">✓</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Deep Correlation, insider, 13F, contracts, and earnings sentiment</td>
    <td style="text-align:center;" class="comp-no">—</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Market Heatmap — sector confluence map</td>
    <td style="text-align:center;" class="comp-yes">✓</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Congress Trade Tracker</td>
    <td style="text-align:center;" class="comp-yes">✓</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Today's Brief / Weekly Research Note</td>
    <td style="text-align:center;" class="comp-yes">✓</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Watchlist</td>
    <td style="text-align:center;color:#8892B0;">5 tickers</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">Unlimited</td>
</tr>
<tr>
    <td>Thesis Journal — decisions, invalidation rules, and outcomes</td>
    <td style="text-align:center;" class="comp-no">—</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Decision Queue — daily evidence and catalyst triage</td>
    <td style="text-align:center;" class="comp-no">—</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Catalyst Command Center — verified dates, weighted exposure, and private event plans</td>
    <td style="text-align:center;color:#8892B0;">Macro calendar</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">Personalized</td>
</tr>
<tr>
    <td>Portfolio Fit Lab — pre-trade factor and concentration simulation</td>
    <td style="text-align:center;" class="comp-no">—</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Morning intelligence digest (email)</td>
    <td style="text-align:center;" class="comp-no">✗</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Factor Exposure — Fama-French regression</td>
    <td style="text-align:center;" class="comp-no">✗</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Signal Backtester — custom combinations</td>
    <td style="text-align:center;" class="comp-no">✗</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>AI Research Assistant — grounded in current live signals</td>
    <td style="text-align:center;" class="comp-no">—</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Read-only score API — hashed keys and rate-limited access</td>
    <td style="text-align:center;" class="comp-no">✗</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Portfolio Intelligence — exposure map + executive review</td>
    <td style="text-align:center;" class="comp-no">✗</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Options Flow — unusual activity feed</td>
    <td style="text-align:center;" class="comp-no">✗</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Priority support</td>
    <td style="text-align:center;" class="comp-no">✗</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
</tbody>
</table>
""", unsafe_allow_html=True)

# ── Second CTA ────────────────────────────────────────────────────────────────
st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)
_, col, _ = st.columns([0.5, 1.2, 0.5])
with col:
    if st.button(
        f"Start {_trial_days}-Day Free Trial — {monthly_price}/mo after",
        type="primary",
        use_container_width=True,
        key="bottom_cta_btn",
    ):
        if not user:
            st.switch_page("pages/home_page.py")
        else:
            try:
                checkout_url = _create_limited_checkout(user, plan, _trial_days)
                st.markdown(
                    f'<meta http-equiv="refresh" content="0; url={checkout_url}">',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'Redirecting… <a href="{checkout_url}">Click here</a> if not redirected.',
                    unsafe_allow_html=True,
                )
            except Exception as e:
                st.error(str(e))

st.markdown("""
<div style="text-align:center;font-size:0.78rem;color:#2D3348;margin-top:12px;">
    Built for repeatable research: discover, investigate, test, monitor, and export in one workspace.
</div>
""", unsafe_allow_html=True)

# ── FAQ ────────────────────────────────────────────────────────────────────────
st.markdown("<div style='height:44px'></div>", unsafe_allow_html=True)
st.markdown(f"""
<div style="font-size:1.15rem;font-weight:800;color:{TEXT_PRIMARY};text-align:center;margin-bottom:20px;">
    Questions? We've got answers.
</div>
""", unsafe_allow_html=True)

faqs = [
    (
        f"What happens after the {_trial_days}-day free trial?",
        f"You'll be charged {monthly_price}/month (or $192/year if on annual) starting on day {_trial_days + 1}. "
        "Cancel any time before that — zero charge. No dark patterns, no 'turn off 5 things to cancel.'"
    ),
    (
        "Can I switch from monthly to annual later?",
        "Yes. Open the Stripe Customer Portal (Manage Subscription on this page) and switch plans. "
        "The difference is prorated automatically."
    ),
    (
        "What if I'm not satisfied?",
        "Email us within 48 hours of your first charge and we'll issue a full refund, no questions asked. "
        "After that, you can cancel and keep access until the end of your billing period."
    ),
    (
        "Is my payment secure?",
        "All payments are processed by Stripe — the same infrastructure used by Amazon, Google, and Shopify. "
        "We never see or store your card number."
    ),
    (
        "Is this investment advice?",
        "No. Unstructured Alpha is an independent research and data tool. Everything here is "
        "educational and informational only. Nothing constitutes a buy or sell recommendation."
    ),
    (
        "Where does the data come from?",
        "FRED (Federal Reserve), EIA (Energy Information Administration), SEC EDGAR (insider trades, "
        "13F filings, congressional trades), FINRA (short interest), yfinance (price data), "
        "and Google Trends. All public, verified sources."
    ),
]

for q, a in faqs:
    with st.expander(q):
        st.markdown(f'<div class="faq-a">{a}</div>', unsafe_allow_html=True)

st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
render_footer()
