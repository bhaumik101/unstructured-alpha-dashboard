"""Focused, persistent account setup for newly verified members."""

from html import escape

import streamlit as st

st.set_page_config(page_title="Personalize Your Research — UA", layout="centered")

from utils.account_setup import (  # noqa: E402
    INTEREST_TICKERS,
    MAX_STARTER_TICKERS,
    complete_account_setup,
    needs_account_setup,
    skip_account_setup,
)
from utils.analytics import Event, track  # noqa: E402
from utils.auth_ui import require_login  # noqa: E402
from utils.risk_profile import (  # noqa: E402
    EMPHASES,
    EMPHASIS_LABELS,
    HORIZONS,
    HORIZON_LABELS,
    TOLERANCES,
    TOLERANCE_LABELS,
)
from utils.theme import inject_premium_css  # noqa: E402


inject_premium_css()
user = require_login()
user_id = user["id"]

st.markdown(
    """
    <style>
    [data-testid="stSidebar"], [data-testid="stHeader"] {display:none !important;}
    .block-container {max-width:760px;padding-top:3.5rem;padding-bottom:3rem;}
    .ua-setup-brand {font-size:.72rem;font-weight:800;letter-spacing:.17em;color:#A7B0BF;
        text-transform:uppercase;margin-bottom:24px;}
    .ua-setup-brand span {color:#D7DEE9;}
    .ua-setup-kicker {font-size:.68rem;font-weight:750;letter-spacing:.12em;color:#9AA6B8;
        text-transform:uppercase;margin-bottom:8px;}
    .ua-setup-title {font-size:2rem;font-weight:760;line-height:1.15;color:#EDF1F7;
        letter-spacing:-.035em;margin-bottom:10px;}
    .ua-setup-copy {font-size:.92rem;line-height:1.65;color:#A7B0BF;max-width:620px;}
    .ua-progress {height:3px;background:#262D38;border-radius:8px;margin:26px 0 28px;overflow:hidden;}
    .ua-progress > div {height:100%;background:#9CA8B8;border-radius:8px;}
    .ua-value-card {background:#11161E;border:1px solid rgba(255,255,255,.09);
        border-radius:10px;padding:15px 17px;margin:12px 0 18px;color:#B7C0CD;
        font-size:.8rem;line-height:1.55;}
    .ua-complete {text-align:center;background:#11161E;border:1px solid rgba(255,255,255,.09);
        border-radius:12px;padding:34px 28px;margin-top:22px;}
    .ua-complete h2 {color:#EDF1F7;font-size:1.5rem;margin:0 0 8px;}
    .ua-complete p {color:#A7B0BF;font-size:.88rem;margin:0;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _go_to_brief() -> None:
    st.switch_page("pages/2_Today_Digest.py")


if not needs_account_setup(user_id):
    st.markdown(
        '<div class="ua-complete"><h2>Your research workspace is ready</h2>'
        '<p>Your account preferences are saved and can be changed anytime in My Profile.</p></div>',
        unsafe_allow_html=True,
    )
    if st.button("Open today's brief", type="primary", width="stretch"):
        _go_to_brief()
    st.stop()

step = int(st.session_state.get("_account_setup_step", 1))
step = min(3, max(1, step))
st.markdown('<div class="ua-setup-brand"><span>Unstructured</span> Alpha</div>', unsafe_allow_html=True)
st.markdown(f'<div class="ua-setup-kicker">Account setup · {step} of 3</div>', unsafe_allow_html=True)

titles = {
    1: ("Make the workspace yours", "Set the identity used throughout your signed-in experience."),
    2: ("Define how you invest", "These settings personalize Your Score without changing the canonical Confluence Score."),
    3: ("Choose what reaches you", "Seed your watchlist and set how you prefer to receive your intelligence briefing."),
}
title, subtitle = titles[step]
st.markdown(
    f'<div class="ua-setup-title">{escape(title)}</div>'
    f'<div class="ua-setup-copy">{escape(subtitle)}</div>'
    f'<div class="ua-progress"><div style="width:{step / 3 * 100:.0f}%"></div></div>',
    unsafe_allow_html=True,
)

if step == 1:
    default_name = st.session_state.get(
        "_setup_display_name",
        user.get("display_name") or user.get("email", "member").split("@", 1)[0],
    )
    with st.form("account_setup_identity"):
        display_name = st.text_input(
            "Display name",
            value=default_name,
            max_chars=48,
            help="This replaces your email in the signed-in interface.",
        )
        st.markdown(
            '<div class="ua-value-card">Your email remains private account information. '
            'Your display name is used only to make the product feel personal.</div>',
            unsafe_allow_html=True,
        )
        next_step = st.form_submit_button("Continue", type="primary", width="stretch")
    if next_step:
        normalized_name = " ".join(display_name.split())
        if not 2 <= len(normalized_name) <= 48:
            st.error("Enter a display name between 2 and 48 characters.")
        else:
            st.session_state["_setup_display_name"] = normalized_name
            st.session_state["_account_setup_step"] = 2
            track(Event.ONBOARDING_STARTED, user_id=user_id, properties={"flow": "account_setup"})
            st.rerun()

elif step == 2:
    with st.form("account_setup_research"):
        tolerance = st.selectbox(
            "Risk tolerance",
            list(TOLERANCES),
            index=list(TOLERANCES).index(st.session_state.get("_setup_tolerance", "balanced")),
            format_func=lambda value: TOLERANCE_LABELS[value],
        )
        horizon = st.selectbox(
            "Primary investing horizon",
            list(HORIZONS),
            index=list(HORIZONS).index(st.session_state.get("_setup_horizon", "all")),
            format_func=lambda value: HORIZON_LABELS[value],
        )
        emphasis = st.selectbox(
            "Evidence emphasis",
            list(EMPHASES),
            index=list(EMPHASES).index(st.session_state.get("_setup_emphasis", "balanced")),
            format_func=lambda value: EMPHASIS_LABELS[value],
        )
        prev_col, next_col = st.columns(2)
        back = prev_col.form_submit_button("Back", width="stretch")
        next_step = next_col.form_submit_button("Continue", type="primary", width="stretch")
    if back:
        st.session_state["_account_setup_step"] = 1
        st.rerun()
    if next_step:
        st.session_state["_setup_tolerance"] = tolerance
        st.session_state["_setup_horizon"] = horizon
        st.session_state["_setup_emphasis"] = emphasis
        st.session_state["_account_setup_step"] = 3
        track(Event.ONBOARDING_STEP, user_id=user_id, properties={"step": "research_preferences"})
        st.rerun()

else:
    with st.form("account_setup_interests"):
        tickers = st.multiselect(
            f"Starting watchlist · choose up to {MAX_STARTER_TICKERS}",
            list(INTEREST_TICKERS),
            default=st.session_state.get("_setup_tickers", ["SPY", "QQQ", "NVDA"]),
            max_selections=MAX_STARTER_TICKERS,
            help="You can add any supported ticker from My Watchlist after setup.",
        )
        digest_label = st.radio(
            "Preferred briefing",
            ("In-app intelligence feed", "Morning intelligence email · Pro"),
            index=0 if st.session_state.get("_setup_digest", "in_app") == "in_app" else 1,
            help="Free accounts can save the email preference now; delivery activates with Pro.",
        )
        st.caption("Morning email delivery is a Pro feature. In-app alerts remain available on Free.")
        prev_col, finish_col = st.columns(2)
        back = prev_col.form_submit_button("Back", width="stretch")
        finish = finish_col.form_submit_button("Finish setup", type="primary", width="stretch")
    if back:
        st.session_state["_setup_tickers"] = tickers
        st.session_state["_setup_digest"] = (
            "morning_email" if digest_label.startswith("Morning") else "in_app"
        )
        st.session_state["_account_setup_step"] = 2
        st.rerun()
    if finish:
        try:
            preference = "morning_email" if digest_label.startswith("Morning") else "in_app"
            result = complete_account_setup(
                user_id,
                display_name=st.session_state.get("_setup_display_name", ""),
                risk_profile={
                    "tolerance": st.session_state.get("_setup_tolerance", "balanced"),
                    "horizon": st.session_state.get("_setup_horizon", "all"),
                    "emphasis": st.session_state.get("_setup_emphasis", "balanced"),
                },
                interest_tickers=tickers,
                digest_preference=preference,
            )
            st.session_state["user"] = {**user, "display_name": result["display_name"]}
            st.session_state["selected_ticker"] = result["interest_tickers"][0]
            track(
                Event.ONBOARDING_COMPLETED,
                user_id=user_id,
                properties={
                    "flow": "account_setup",
                    "ticker_count": len(result["interest_tickers"]),
                    "digest_preference": result["digest_preference"],
                },
            )
            _go_to_brief()
        except ValueError as exc:
            st.error(str(exc))
        except Exception:
            st.error("We couldn't save your setup. Please try again.")

st.divider()
if st.button("Skip for now", width="stretch", key="skip_account_setup"):
    try:
        skip_account_setup(user_id)
        track(
            Event.ONBOARDING_COMPLETED,
            user_id=user_id,
            properties={"flow": "account_setup", "skipped": True},
        )
        _go_to_brief()
    except Exception:
        st.error("We couldn't close setup right now. Please try again.")
st.caption("You can change every preference later from My Profile.")
