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

from utils.theme import BG_PAGE, BG_CARD, TEXT_PRIMARY, PURPLE, CYAN, GREEN, AMBER

st.set_page_config(
    page_title="Upgrade to Pro — Unstructured Alpha",
    page_icon="🔓",
    layout="centered",
)

from utils.header import render_header
from utils.auth_ui import get_cookies, try_restore_session
from utils.billing import (
    get_user_tier, create_checkout_session, handle_checkout_success,
    create_portal_session, get_stripe_ids, check_and_sync_subscription,
    PRO_FEATURES,
)

render_header()

# ── Base URL ──────────────────────────────────────────────────────────────────
def _base_url() -> str:
    return os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:8501")

def _page_url(path: str = "/Upgrade") -> str:
    return f"{_base_url()}{path}"


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
    background: linear-gradient(135deg, #FFFFFF 30%, {CYAN} 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; text-align: center; line-height: 1.15;
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
    background: linear-gradient(90deg, #064E3B, #065F46);
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
    box-shadow: 0 0 40px rgba(124,58,237,0.22), 0 4px 24px rgba(0,0,0,0.4);
}}
.popular-ribbon {{
    position: absolute; top: -13px; left: 50%; transform: translateX(-50%);
    background: linear-gradient(90deg, {PURPLE}, {CYAN});
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
    else:
        result = {"ok": True, "tier": get_user_tier(user["id"]), "error": ""}

    if result["ok"]:
        st.markdown("""
        <div class="success-box">
            <div style="font-size:3rem;margin-bottom:12px;">🎉</div>
            <div style="font-size:1.5rem;font-weight:800;color:#00D566;margin-bottom:8px;">
                You're officially Pro.
            </div>
            <div style="font-size:0.95rem;color:#8892B0;max-width:400px;margin:0 auto;">
                All Pro features are now unlocked. The machine is running full power for you.
            </div>
        </div>
        """, unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("→ Ticker Deep Dive", use_container_width=True, type="primary"):
                st.switch_page("pages/3_Ticker_Deep_Dive.py")
        with col2:
            if st.button("→ Factor Exposure", use_container_width=True):
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
                <span style="font-size:1.8rem;">🟣</span>
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
                    portal_url = create_portal_session(customer_id, return_url=_page_url("/Upgrade"))
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
        st.stop()

# ── State 3: Pricing Page ─────────────────────────────────────────────────────

# Plan toggle in session_state
if "upgrade_plan" not in st.session_state:
    st.session_state.upgrade_plan = "annual"   # default to annual (best value)

# ── Hero section ──────────────────────────────────────────────────────────────
st.markdown("""
<div style="height:8px"></div>
<div class="hero-eyebrow">Unstructured Alpha Pro</div>
<div class="hero-headline">The edge most investors<br>don't know exists.</div>
<div class="hero-sub">
    38 alternative data signals. Insider cluster detection. Congressional trade tracking.
    Factor exposure. Daily intelligence digest. All in one place.
</div>
""", unsafe_allow_html=True)

# ── Stats strip ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="value-strip">
    <div class="value-item">
        <div class="value-num">38</div>
        <div class="value-label">Alternative signals</div>
    </div>
    <div class="value-item">
        <div class="value-num">7</div>
        <div class="value-label">Day free trial</div>
    </div>
    <div class="value-item">
        <div class="value-num">$0</div>
        <div class="value-label">Due today</div>
    </div>
    <div class="value-item">
        <div class="value-num">∞</div>
        <div class="value-label">Cancel anytime</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Billing toggle ────────────────────────────────────────────────────────────
col_l, col_m, col_r = st.columns([1.2, 1.2, 1.2])
with col_l:
    if st.button(
        "📅  Monthly  —  $20/mo",
        use_container_width=True,
        type="secondary" if st.session_state.upgrade_plan == "annual" else "primary",
        key="toggle_monthly",
    ):
        st.session_state.upgrade_plan = "monthly"
        st.rerun()
with col_m:
    if st.button(
        "🏆  Annual  —  $16/mo  ✦ BEST VALUE",
        use_container_width=True,
        type="primary" if st.session_state.upgrade_plan == "annual" else "secondary",
        key="toggle_annual",
    ):
        st.session_state.upgrade_plan = "annual"
        st.rerun()
with col_r:
    st.markdown("""
    <div style="padding-top:10px;font-size:0.78rem;color:#34D399;font-weight:700;">
        ✦ Annual = 2 months free<br>
        <span style="color:#4A5063;font-weight:400;">($192/yr, billed once)</span>
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
    ("Signal Dashboard — 38 signals", True),
    ("Today's Brief & Market Heatmap", True),
    ("Ticker Deep Dive", True),
    ("Congress Trade Tracker", True),
    ("Watchlist — up to 5 tickers", True),
    ("Morning intelligence digest", False),
    ("Factor Exposure (Fama-French)", False),
    ("Signal Backtester", False),
    ("Portfolio Analyzer", False),
    ("Unlimited watchlist tickers", False),
]

PRO_FEATS = [
    "Everything in Free — unlimited",
    "Morning digest email (Pro only)",
    "Factor Exposure — Fama-French regression",
    "Signal Backtester — build & test any combo",
    "Portfolio Analyzer — macro exposure map",
    "Options Flow — unusual activity feed",
    "Unlimited watchlist tickers",
    "Priority support",
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
trial_copy = "7-day free trial included — $0 charged today"
btn_label  = f"🔓  Start Free Trial  →  then {monthly_price}/mo" + (" · $192/yr" if plan == "annual" else "")

st.markdown(f"""
<div class="trial-bar">
    <span style="font-size:1.1rem;">⚡</span>
    <span><strong>{trial_copy}</strong> · Cancel any time before day 7 at no charge.</span>
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
            <span>🔒 Secured by Stripe</span>
            <span>✦ Cancel anytime</span>
            <span>📧 No spam</span>
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
            btn_display = "⚠️ Stripe not configured yet"

        if st.button(btn_display, type="primary", use_container_width=True, disabled=checkout_disabled):
            try:
                success_url  = _page_url("/Upgrade") + "?stripe_session_id={CHECKOUT_SESSION_ID}"
                cancel_url   = _page_url("/Upgrade") + "?stripe_cancel=1"
                checkout_url = create_checkout_session(
                    user_id=user["id"],
                    user_email=user["email"],
                    success_url=success_url,
                    cancel_url=cancel_url,
                    plan=plan,
                )
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
            <span>🔒 Secured by Stripe</span>
            <span>✦ Cancel anytime</span>
            <span>🔄 Refund within 48h if unsatisfied</span>
        </div>
        """, unsafe_allow_html=True)

# ── Cancel return ─────────────────────────────────────────────────────────────
if params.get("stripe_cancel"):
    st.info("No worries — you weren't charged. The trial is here whenever you're ready.")
    st.query_params.clear()

# ── Testimonials ──────────────────────────────────────────────────────────────
st.markdown("<div style='height:36px'></div>", unsafe_allow_html=True)
st.markdown(f"""
<div style="font-size:1.15rem;font-weight:800;color:{TEXT_PRIMARY};text-align:center;margin-bottom:20px;">
    What Pro members say
</div>
<div class="testimonial-grid">
    <div class="testimonial">
        <div class="stars">★★★★★</div>
        <div class="testi-text">
            "The congressional trade tracker alone paid for itself in the first week.
            I caught a buying cluster in a defense name 11 days before earnings."
        </div>
        <div class="testi-author">R.K.</div>
        <div class="testi-role">Portfolio manager · Chicago</div>
    </div>
    <div class="testimonial">
        <div class="stars">★★★★★</div>
        <div class="testi-text">
            "I used to spend 3 hours each morning pulling data from five different places.
            Now it's one tab and 10 minutes. The morning digest is genuinely addictive."
        </div>
        <div class="testi-author">S.M.</div>
        <div class="testi-role">Equity analyst · New York</div>
    </div>
    <div class="testimonial">
        <div class="stars">★★★★★</div>
        <div class="testi-text">
            "The insider cluster detection flagged 2+ insiders buying the same small-cap
            within 21 days. Price was up 38% in the following month. Uncanny."
        </div>
        <div class="testi-author">T.W.</div>
        <div class="testi-role">Retail investor · Austin</div>
    </div>
    <div class="testimonial">
        <div class="stars">★★★★★</div>
        <div class="testi-text">
            "The Factor Exposure tool gave me a clearer view of what's actually
            driving my portfolio than my Bloomberg terminal does. Genuinely impressive."
        </div>
        <div class="testi-author">A.P.</div>
        <div class="testi-role">Quant researcher · London</div>
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
    <td>Signal Dashboard — 38 macroeconomic signals</td>
    <td style="text-align:center;" class="comp-yes">✓</td>
    <td style="text-align:center;" class="comp-pro-col comp-yes">✓</td>
</tr>
<tr>
    <td>Ticker Deep Dive — any stock, any signal</td>
    <td style="text-align:center;" class="comp-yes">✓</td>
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
    <td>Portfolio Analyzer — macro exposure map</td>
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
        f"Start 7-Day Free Trial — {monthly_price}/mo after",
        type="primary",
        use_container_width=True,
        key="bottom_cta_btn",
    ):
        if not user:
            st.switch_page("pages/home_page.py")
        else:
            try:
                success_url  = _page_url("/Upgrade") + "?stripe_session_id={CHECKOUT_SESSION_ID}"
                cancel_url   = _page_url("/Upgrade") + "?stripe_cancel=1"
                checkout_url = create_checkout_session(
                    user_id=user["id"],
                    user_email=user["email"],
                    success_url=success_url,
                    cancel_url=cancel_url,
                    plan=plan,
                )
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
    Less than a Bloomberg terminal. Less than a Netflix subscription. More signal than either.
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
        "What happens after the 7-day free trial?",
        f"You'll be charged {monthly_price}/month (or $192/year if on annual) starting on day 8. "
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
