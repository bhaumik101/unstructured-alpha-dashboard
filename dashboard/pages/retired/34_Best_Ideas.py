# pages/34_Best_Ideas.py
# Unstructured Alpha — The Machine's Best Ideas
#
# Public page. Shows the machine's highest-conviction bullish calls right now:
# tickers with score ≥ 65 (bullish threshold) AND positive score velocity
# (the score is rising, not just sitting at a high level). Ranked by a
# combined rank_score = score + min(velocity_pts_per_day × 3, 12).
#
# Free: top 5 tickers with score, velocity, 7d delta, sector, Deep Dive button.
# Pro: all qualifying tickers + AI one-liner rationale per ticker.
#
# Acquisition surface: designed to be shared. "The machine currently likes
# these 5 tickers most — here's why" is shareable content that drives signups
# and referrals. Updated hourly (cache TTL).

import streamlit as st

st.set_page_config(
    page_title="Best Ideas — UA",
    layout="wide",
    initial_sidebar_state="expanded",
)

import os
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from utils.header import render_header, render_page_header, render_sidebar_base
from utils.top_tickers import get_top_tickers
from utils.score_history import get_batch_velocity_stats
from utils.db import engine, score_snapshots
from utils.theme import inject_premium_css
from utils.signals_cache import get_all_signal_scores

render_header("Best Ideas")
render_sidebar_base()
inject_premium_css()

render_page_header(
    "The Machine's Best Ideas",
    "High-conviction bullish calls with positive score momentum — ranked by the 28-signal engine.",
    icon="🎯",
)

FREE_LIMIT = 5       # rows visible without Pro
SCORE_FLOOR = 62.0   # slightly below 65 so near-threshold tickers appear
RANK_VEL_CAP = 12.0  # max velocity bonus added to rank score


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False, max_entries=1)
def _load_candidates() -> list[dict]:
    """
    1. Get all tickers from the scoring engine.
    2. Filter to score ≥ SCORE_FLOOR.
    3. Batch-fetch velocity for all candidates in one SQL query.
    4. Rank by rank_score = score + min(max(velocity×3, 0), RANK_VEL_CAP).
    5. Keep only tickers with positive velocity (rising).
    """
    signal_scores = get_all_signal_scores()
    result = get_top_tickers(signal_scores_hash=len(signal_scores))
    all_rows = result.get("all", [])

    # Filter to score ≥ floor
    candidates = [r for r in all_rows if float(r.get("score", 0)) >= SCORE_FLOOR]
    if not candidates:
        return []

    tickers = [r["ticker"] for r in candidates]
    vel_map = get_batch_velocity_stats(tickers)

    # Annotate + filter + rank
    enriched = []
    for row in candidates:
        t = row["ticker"]
        vd = vel_map.get(t)
        vel = vd["velocity"] if vd else 0.0
        if vel <= 0:
            continue  # only include rising tickers
        vel_bonus = min(max(vel * 3, 0), RANK_VEL_CAP)
        enriched.append({
            **row,
            "velocity":    vel,
            "vel_pct":     vd["percentile"] if vd else 0.0,
            "vel_dir":     "up",
            "rank_score":  round(float(row["score"]) + vel_bonus, 2),
        })

    enriched.sort(key=lambda x: -x["rank_score"])
    return enriched


@st.cache_data(ttl=3600, show_spinner=False, max_entries=1)
def _load_7d_deltas(ticker_tuple: tuple) -> dict[str, float]:
    if not ticker_tuple:
        return {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                select(
                    score_snapshots.c.ticker,
                    score_snapshots.c.score,
                    score_snapshots.c.snapshot_date,
                )
                .where(score_snapshots.c.ticker.in_(list(ticker_tuple)))
                .where(score_snapshots.c.snapshot_date >= cutoff)
                .order_by(score_snapshots.c.ticker, score_snapshots.c.snapshot_date)
            ).fetchall()
    except Exception:
        return {}

    from collections import defaultdict
    by_ticker: dict[str, list] = defaultdict(list)
    for r in rows:
        by_ticker[r[0]].append((r[2], float(r[1])))

    deltas: dict[str, float] = {}
    for ticker, entries in by_ticker.items():
        entries.sort()
        if len(entries) >= 2:
            deltas[ticker] = round(entries[-1][1] - entries[0][1], 1)
    return deltas


# ── AI rationale (Pro only, cached) ──────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False, max_entries=15)
def _generate_rationale(
    _ticker: str, _name: str, _score: float, _case: str,
    _vel: float, _sector: str, _conviction: str,
) -> str | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        vel_sign = "+" if _vel >= 0 else ""
        prompt = (
            f"Ticker: {_ticker} ({_name})\n"
            f"Sector: {_sector}\n"
            f"Confluence Score: {_score:.0f}/100 ({_case})\n"
            f"Score velocity: {vel_sign}{_vel:.1f} pts/day (rising)\n"
            f"Conviction: {_conviction}\n\n"
            f"Write ONE sentence (max 25 words) explaining why this ticker "
            f"currently ranks highly on a macro signal composite. Be specific, "
            f"data-grounded, no hype. Start with the ticker symbol."
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            system="You are a terse quantitative analyst. One sentence, specific, no fluff.",
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception:
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_pill(score: float, case: str) -> str:
    if case == "BULL":
        bg, fg, border = "#0D2B1A", "#00D566", "rgba(0,213,102,0.35)"
    elif case == "BEAR":
        bg, fg, border = "#2B0D15", "#FF4D6A", "rgba(255,77,106,0.35)"
    else:
        bg, fg, border = "#1A1E2B", "#F59E0B", "rgba(245,158,11,0.35)"
    return (
        f'<span style="background:{bg};color:{fg};border:1px solid {border};'
        f'border-radius:6px;padding:3px 10px;font-size:0.95rem;font-weight:800;">'
        f'{score:.0f}</span>'
    )


def _vel_badge(vel: float) -> str:
    color = "#00D566" if vel > 0 else "#FF4D6A"
    sign  = "+" if vel > 0 else ""
    return (
        f'<span style="color:{color};font-weight:700;font-size:0.82rem;">'
        f'▲ {sign}{vel:.1f}<span style="font-size:0.68rem;color:#8892AA;"> pts/d</span></span>'
    )


def _delta_badge(delta: float | None) -> str:
    if delta is None:
        return '<span style="color:#4A5280;font-size:0.75rem;">—</span>'
    color = "#00D566" if delta >= 0 else "#FF4D6A"
    arrow = "▲" if delta >= 0 else "▼"
    sign  = "+" if delta >= 0 else ""
    return (
        f'<span style="color:{color};font-size:0.78rem;font-weight:700;">'
        f'{arrow} {sign}{delta:.1f}</span>'
    )


# ── Tier check ────────────────────────────────────────────────────────────────

_user = st.session_state.get("user")
_is_pro = False
if _user:
    _tier_key = f"_tier_{_user['id']}"
    if _tier_key not in st.session_state:
        try:
            from utils.billing import get_user_tier
            st.session_state[_tier_key] = get_user_tier(_user["id"])
        except Exception:
            st.session_state[_tier_key] = "free"
    _is_pro = st.session_state.get(_tier_key) == "pro"


# ── Load + render ─────────────────────────────────────────────────────────────

with st.spinner("Scanning signal universe…"):
    candidates = _load_candidates()

if not candidates:
    st.info(
        "No tickers currently meet the high-conviction + rising criteria. "
        "Check back after the next signal refresh (~1 hour)."
    )
    st.stop()

display_rows = candidates if _is_pro else candidates[:FREE_LIMIT]
ticker_tuple = tuple(r["ticker"] for r in display_rows)
deltas = _load_7d_deltas(ticker_tuple)

refreshed_at = datetime.now(timezone.utc).strftime("%H:%M UTC")

# Meta strip
st.markdown(
    f'<div style="display:flex;gap:24px;align-items:center;margin-bottom:20px;flex-wrap:wrap;">'
    f'<span style="font-size:0.75rem;color:#6B7A95;">🕐 Updated {refreshed_at}</span>'
    f'<span style="font-size:0.75rem;color:#6B7A95;">🎯 {len(candidates)} qualifying ticker{"s" if len(candidates)!=1 else ""}</span>'
    f'<span style="font-size:0.75rem;color:#6B7A95;">Criteria: score ≥ 65 · velocity > 0 · ranked by score + momentum</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# Table header
h_cols = st.columns([0.4, 2.6, 2.0, 1.2, 1.1, 1.1, 1.3, 1.5])
for col, label in zip(h_cols, ["#", "TICKER", "SECTOR", "SCORE", "VEL", "7D Δ", "RANK", " "]):
    with col:
        st.markdown(
            f'<span style="font-size:0.68rem;color:#4A5280;">{label}</span>',
            unsafe_allow_html=True,
        )
st.markdown(
    '<hr style="border:none;border-top:1px solid #1E2535;margin:4px 0 8px;">',
    unsafe_allow_html=True,
)

for i, row in enumerate(display_rows, 1):
    ticker  = row["ticker"]
    delta   = deltas.get(ticker)
    cols    = st.columns([0.4, 2.6, 2.0, 1.2, 1.1, 1.1, 1.3, 1.5])

    with cols[0]:
        st.markdown(
            f'<span style="font-size:0.82rem;color:#F59E0B;font-weight:700;">{i}</span>',
            unsafe_allow_html=True,
        )
    with cols[1]:
        name_short = row["name"][:24] + "…" if len(row["name"]) > 26 else row["name"]
        st.markdown(
            f'<div style="font-size:0.95rem;font-weight:700;color:#E8EEFF;">{ticker}</div>'
            f'<div style="font-size:0.72rem;color:#6B7A95;">{name_short}</div>',
            unsafe_allow_html=True,
        )
    with cols[2]:
        st.markdown(
            f'<span style="font-size:0.78rem;color:#8892AA;">{row.get("sector","")}</span>',
            unsafe_allow_html=True,
        )
    with cols[3]:
        st.markdown(_score_pill(row["score"], row["case"]), unsafe_allow_html=True)
    with cols[4]:
        st.markdown(_vel_badge(row["velocity"]), unsafe_allow_html=True)
    with cols[5]:
        st.markdown(_delta_badge(delta), unsafe_allow_html=True)
    with cols[6]:
        rs = row["rank_score"]
        st.markdown(
            f'<span style="font-size:0.88rem;color:#F59E0B;font-weight:700;">{rs:.0f}</span>',
            unsafe_allow_html=True,
        )
    with cols[7]:
        if st.button("Deep Dive →", key=f"bi_dd_{ticker}", use_container_width=True):
            st.query_params["ticker"] = ticker
            st.switch_page("pages/3_Ticker_Deep_Dive.py")

    # Pro AI rationale inline
    if _is_pro:
        rationale = _generate_rationale(
            ticker, row.get("name", ticker),
            float(row["score"]), row.get("case", "BULL"),
            row["velocity"], row.get("sector", ""),
            row.get("conviction", ""),
        )
        if rationale:
            st.markdown(
                f'<div style="margin:-4px 0 8px 0;padding:6px 12px;'
                f'background:rgba(124,58,237,0.05);border-left:3px solid rgba(124,58,237,0.30);'
                f'border-radius:4px;font-size:0.78rem;color:#9AA3C0;line-height:1.55;">'
                f'✦ {rationale}</div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        '<hr style="border:none;border-top:1px solid #12151E;margin:2px 0;">',
        unsafe_allow_html=True,
    )


# ── Pro gate (if free user) ───────────────────────────────────────────────────

if not _is_pro and len(candidates) > FREE_LIMIT:
    hidden = len(candidates) - FREE_LIMIT
    st.markdown(
        f"""
        <div style="text-align:center;padding:28px 20px;background:rgba(124,58,237,0.05);
                    border:1px solid rgba(124,58,237,0.20);border-radius:10px;margin-top:12px;">
          <div style="font-size:1.05rem;font-weight:700;color:#E8EEFF;margin-bottom:6px;">
            🔒 {hidden} more qualifying ticker{"s" if hidden!=1 else ""} + AI rationale
          </div>
          <div style="font-size:0.82rem;color:#6B7A95;margin-bottom:16px;">
            Pro members see the full ranked list, AI one-liner reasoning per ticker,<br>
            and real-time updates as scores change.
          </div>
          <a href="/Upgrade" target="_self"
             style="display:inline-block;background:linear-gradient(135deg,#7C3AED,#5B21B6);
                    color:#FFFFFF;padding:10px 28px;border-radius:8px;
                    text-decoration:none;font-size:0.90rem;font-weight:700;">
            Upgrade to Pro →
          </a>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown(
    '<div style="font-size:0.72rem;color:#4A5280;text-align:center;line-height:1.8;">'
    'Rank score = Confluence Score + velocity bonus (capped at +12). '
    'Only tickers with positive score momentum (rising over last 5 sessions) appear here. '
    'Not financial advice. Updated hourly. '
    '<a href="/About" style="color:#6B7A95;">Methodology →</a>'
    '</div>',
    unsafe_allow_html=True,
)
