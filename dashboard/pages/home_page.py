"""
Home — Unstructured Alpha
Public-facing landing page. Psychological design goals:
  1. Live signal data IN the hero — not below it. Real data creates immediate credibility.
  2. Specificity everywhere — "47 signals, 4-16 weeks ahead" not "leading indicators."
  3. Authority by association — FRED / SEC EDGAR / FINRA = same sources Goldman uses.
  4. Loss aversion framing — "what are you missing" more powerful than "here's what you get."
  5. Anchoring — mention Bloomberg's $50K price before showing this is free.
  6. One clear primary CTA above the fold — no decision paralysis.
"""

import streamlit as st

# Analytics + onboarding — imported lazily inside their sections to avoid
# circular-import risk on cold start (these modules themselves import from utils.db).
# Direct imports below are safe because they don't import from pages/.

st.set_page_config(
    page_title="Unstructured Alpha — Macro Signal Intelligence",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Unstructured Alpha — institutional-grade macro signals for every investor."},
)

from utils.performance import PageProfiler

_home_perf = PageProfiler("home")

import html as _h
import pandas as pd
from utils.header import render_header, render_sidebar_base, render_footer
from utils.signals_cache import get_shared_signal_scores
from utils.config import SIGNALS, CATEGORIES
from utils.narrative import generate_narrative
from utils.product_metrics import (
    SCORE_COMPUTE_DESCRIPTION,
    SCORE_COMPUTE_SHORT,
    SUPPORTED_TICKER_COUNT,
)
from utils.top_tickers import get_top_tickers
from utils.convergence import get_convergence_events, render_convergence_events
from utils.theme import inject_all_css, render_platform_note

_home_perf.checkpoint("module_imports")

render_header(
    "Home",
    hero_title="Know the macro backdrop before you trade.",
    hero_sub="47 macro signals scored daily on first-print data — no hindsight, no synthetic values.",
)
_home_perf.checkpoint("header")
inject_all_css()
_home_perf.checkpoint("theme_css")
_home_section = render_sidebar_base(
    page_title="Home",
    sections=("Dashboard", "Discover"),
    section_key="home_section_rail",
    default_section="Dashboard",
)
_home_perf.checkpoint("sidebar_base")

# Data-integrity disclosure is rendered AFTER the canonical regime is computed
# (see below), so the "N of 47 excluded" count matches the header bar and hero
# exactly. Rendering it here off the live cache is what made the banner say 4
# while the regime bar said 3 — same fact, two numbers. See [[macro_regime_ssot_bug]].

# ── Load signal data ──────────────────────────────────────────────────────────
# SSOT NOTE: everything on this page that reports a REGIME COUNT (the header bar,
# the hero split, the "MACHINE READS THE MARKET" narrative, and the data-
# availability banner) must read from ONE source, or the landing page shows the
# same fact with different numbers — the exact trust-destroying bug fought in
# [[macro_regime_ssot_bug]]. The canonical source is the persisted daily snapshot
# (score_history.get_latest_signal_states) because the header must stay cheap on
# every route. The live cache (get_all_signal_scores) is still used below for
# TICKER SCORING only (portfolio check, top movers) — those surface names/scores,
# never a regime count, so they can't contradict the headline.
def _build_home_data(_all: dict) -> dict:
    bull, bear, neut, buckets = [], [], [], {}
    for sid, sv in _all.items():
        if sv.get("error"):
            continue
        status = sv.get("status", "neutral")
        score  = sv.get("score", 50)
        name   = sv.get("name", sid)
        cat    = sv.get("category", "macro")
        if status == "bullish":
            bull.append((name, score))
        elif status == "bearish":
            bear.append((name, score))
        else:
            neut.append((name, score))
        buckets.setdefault(cat, []).append(score)
    return {
        "bull":    sorted(bull, key=lambda x: -x[1]),
        "bear":    sorted(bear, key=lambda x:  x[1]),
        "neut":    neut,
        "sectors": {k: sum(v)/len(v) for k, v in buckets.items() if v},
    }

try:
    from utils.regime import compute_macro_regime as _cmr
    from utils.score_history import get_latest_signal_states as _glss_home

    with st.spinner(""):
        # ── THE canonical macro read for this page ────────────────────────────
        # One snapshot, enriched with names/categories from config (the snapshot
        # table only persists id/score/status). EVERY regime count on the page —
        # header, hero, narrative, banner — is derived from this one dict.
        _snap = _glss_home()
        _home_perf.checkpoint("persisted_snapshot")
        _snap_rich = {
            sid: {
                **row,
                "name":     SIGNALS.get(sid, {}).get("name", sid.replace("_", " ").title()),
                "category": SIGNALS.get(sid, {}).get("category", "macro"),
            }
            for sid, row in _snap.items()
        }
        _reg = _cmr(_snap, total=len(SIGNALS))

        # Narrative + home aggregates read the SAME snapshot, so the "MACHINE
        # READS THE MARKET" summary ("N bullish, M bearish, K neutral") is
        # guaranteed to match the header bar and hero split.
        _hd = _build_home_data(_snap_rich)
        _narrative  = generate_narrative(_snap_rich)
        _home_perf.checkpoint("snapshot_derivation")

        # The compact Dashboard needs only the persisted daily snapshot above.
        # Full live series carry every signal's history and are reserved for
        # Discover, where ticker scoring and the product tour actually use them.
        if _home_section == "Discover":
            _raw_scores = get_shared_signal_scores()
            _home_perf.checkpoint("live_signal_scores")
            _top_tkrs = get_top_tickers(len(_raw_scores))
            _home_perf.checkpoint("top_ticker_ranking")
        else:
            _raw_scores = {}
            _top_tkrs = {"bullish": [], "bearish": [], "by_sector": {}, "all": []}
            _home_perf.checkpoint("live_signal_scores_skipped")
            _home_perf.checkpoint("top_ticker_ranking_skipped")

    _nb, _nr, _nn = _reg.bullish, _reg.bearish, _reg.neutral
    _total = _reg.scored
    _bias_label = _reg.label
    _data_loaded = True
except Exception:
    _home_perf.checkpoint("home_data_error", success=False)
    _hd = {"bull": [], "bear": [], "neut": [], "sectors": {}}
    _raw_scores = {}
    _narrative  = {"regime": "LOADING…", "regime_color": "#8892AA", "summary": "",
                   "top_bull": [], "top_bear": [], "watch_note": "", "sector_bias": {},
                   "bull_count": 0, "bear_count": 0, "neut_count": 0, "total": 0}
    _top_tkrs   = {"bullish": [], "bearish": [], "by_sector": {}, "all": []}
    _nb = _nr = _nn = _total = 0
    _bias_label = "LOADING…"
    _data_loaded = False

# Data-integrity disclosure, rendered from the CANONICAL regime so the excluded
# count matches the header bar and hero exactly (both derive from _reg.excluded =
# total - scored on the same snapshot). See [[macro_regime_ssot_bug]].
if _data_loaded and _reg.excluded > 0:
    from utils.header import render_data_unavailable_banner
    render_data_unavailable_banner(_reg.excluded, _reg.total)

_home_perf.checkpoint("data_integrity")

# ── FLIP ALERT HELPER ─────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _get_recent_signal_flip() -> dict | None:
    """Return the most dramatic signal direction-flip in the last 48 hours, or None."""
    try:
        from utils.db import engine
        import sqlalchemy as sa
        with engine.connect() as _conn:
            _rows = _conn.execute(sa.text("""
                SELECT signal_id, status, score, snapshot_date
                FROM signal_snapshots
                WHERE snapshot_date >= NOW() - INTERVAL '48 hours'
                ORDER BY signal_id, snapshot_date
            """)).mappings().all()
        if not _rows:
            return None
        _by_sig: dict = {}
        for _r in _rows:
            _by_sig.setdefault(_r["signal_id"], []).append(dict(_r))
        _flips = []
        for _sid, _snaps in _by_sig.items():
            _sts = [_s["status"] for _s in _snaps]
            for _i in range(1, len(_sts)):
                if _sts[_i] != _sts[_i - 1] and _sts[_i] in ("bullish", "bearish"):
                    from utils.config import SIGNALS as _S2
                    _flips.append({
                        "signal_id": _sid,
                        "name": _S2.get(_sid, {}).get("name", _sid),
                        "to_status": _sts[_i],
                        "from_status": _sts[_i - 1],
                        "score": _snaps[-1]["score"],
                    })
                    break
        if not _flips:
            return None
        _flips.sort(key=lambda x: abs(x["score"] - 50), reverse=True)
        return _flips[0]
    except Exception:
        return None


# ── PORTFOLIO CHECK HELPER ────────────────────────────────────────────────────
def _score_tickers_from_cache(tickers_input: str, raw_scores: dict) -> list:
    """Score tickers from the already-cached signal data — zero extra API calls."""
    from utils.config import TICKERS as _TK
    _results = []
    _syms = [t.strip().upper() for t in tickers_input.replace(",", " ").split() if t.strip()][:5]
    for _sym in _syms:
        _tk_cfg = _TK.get(_sym, {})
        _sig_ids = _tk_cfg.get("signals", []) if _tk_cfg else []
        if not _sig_ids:  # Unknown ticker — use broad macro basket
            _sig_ids = [
                "yield_curve", "hy_credit_spread", "jobless_claims",
                "put_call_ratio", "consumer_sentiment", "vix_term_structure",
            ]
        _scores, _top_sig = [], []
        for _sid in _sig_ids:
            _sv = raw_scores.get(_sid)
            if _sv and not _sv.get("error") and _sv.get("status") != "insufficient_data":
                _sc = _sv["score"]
                _scores.append(_sc)
                _top_sig.append((_sv["name"], _sv["status"], _sc))
        if not _scores:
            continue
        _avg = sum(_scores) / len(_scores)
        _st = "bullish" if _avg >= 60 else ("bearish" if _avg <= 40 else "neutral")
        _top_sig.sort(key=lambda x: abs(x[2] - 50), reverse=True)
        _results.append({
            "ticker":      _sym,
            "name":        _tk_cfg.get("name", _sym) if _tk_cfg else _sym,
            "score":       round(_avg, 1),
            "status":      _st,
            "top_signals": _top_sig[:2],
            "known":       bool(_tk_cfg),
        })
    return _results


# Dark-theme regime colors (overrides narrative.py light-theme values)
_bias_color = (
    "#00D566" if any(x in _bias_label for x in ("BULL", "ON", "RISK-ON"))
    else "#FF4444" if any(x in _bias_label for x in ("BEAR", "OFF", "RISK-OFF"))
    else "#6B7FBF"
)
_bias_bg = (
    "rgba(0,213,102,0.07)" if "00D566" in _bias_color
    else "rgba(255,68,68,0.07)" if "FF4444" in _bias_color
    else "rgba(107,127,191,0.05)"
)
_top_bull = _hd["bull"][0][0] if _hd["bull"] else None
_top_bear = _hd["bear"][0][0] if _hd["bear"] else None

# ── PRODUCT-ALIGNED LANDING HERO ──────────────────────────────────────────────
# This page previously used a separate serif/gradient marketing language and an
# iframe-only animated counter. Keeping the proof points in the normal document
# makes them inherit the exact same light/dark tokens as the application.
st.markdown(f"""
<style>
  .ua-landing-hero {{
    position:relative;
    overflow:hidden;
    display:grid;
    grid-template-columns:minmax(0,1.6fr) minmax(220px,.65fr);
    gap:28px;
    align-items:end;
    margin:24px 0 16px;
    padding:30px 32px;
    border:1px solid var(--ua-hair);
    border-radius:12px;
    background:
      linear-gradient(135deg,rgba(var(--ua-royal-rgb),0.11),transparent 56%),
      var(--ua-bg-card);
    box-shadow:var(--ua-shadow-1);
    font-family:Inter,system-ui,sans-serif;
  }}
  .ua-landing-hero::before {{
    content:"";
    position:absolute;
    inset:0 auto 0 0;
    width:3px;
    background:var(--ua-royal);
  }}
  .ua-landing-kicker {{
    color:var(--ua-royal-2);
    font-size:.64rem;
    font-weight:750;
    letter-spacing:.14em;
    text-transform:uppercase;
    margin-bottom:10px;
  }}
  .ua-landing-title {{
    max-width:760px;
    color:var(--ua-ink);
    font-size:clamp(1.8rem,3.7vw,2.75rem);
    font-weight:780;
    line-height:1.08;
    letter-spacing:-.035em;
    margin:0 0 14px;
  }}
  .ua-landing-copy {{
    max-width:720px;
    color:var(--ua-ink-mut);
    font-size:.96rem;
    line-height:1.7;
  }}
  .ua-landing-access {{
    padding:16px;
    border:1px solid var(--ua-hair);
    border-radius:8px;
    background:rgba(var(--ua-card-rgb),.62);
  }}
  .ua-landing-access strong {{
    display:block;
    color:var(--ua-ink);
    font-size:.82rem;
    margin-bottom:5px;
  }}
  .ua-landing-access span {{
    display:block;
    color:var(--ua-ink-mut);
    font-size:.72rem;
    line-height:1.55;
  }}
  .ua-stat-strip {{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    margin:14px 0 2px;
    overflow:hidden;
    border:1px solid var(--ua-hair);
    border-radius:10px;
    background:var(--ua-bg-card);
    font-family:Inter,system-ui,sans-serif;
  }}
  .ua-stat-item {{
    min-width:0;
    padding:15px 18px;
    border-right:1px solid var(--ua-hair);
  }}
  .ua-stat-item:last-child {{border-right:0}}
  .ua-stat-num {{
    display:block;
    color:var(--ua-ink);
    font-size:1.35rem;
    font-weight:780;
    letter-spacing:-.035em;
    line-height:1.1;
  }}
  .ua-stat-label {{
    display:block;
    margin-top:5px;
    color:var(--ua-ink-mut);
    font-size:.62rem;
    font-weight:650;
    letter-spacing:.08em;
    text-transform:uppercase;
  }}
  @media(max-width:760px) {{
    .ua-landing-hero {{grid-template-columns:1fr;padding:24px 22px;gap:18px}}
    .ua-stat-strip {{grid-template-columns:repeat(2,minmax(0,1fr))}}
    .ua-stat-item:nth-child(2) {{border-right:0}}
    .ua-stat-item:nth-child(-n+2) {{border-bottom:1px solid var(--ua-hair)}}
  }}
</style>
<section class="ua-landing-hero">
  <div>
    <div class="ua-landing-kicker">Macro intelligence for real portfolios</div>
    <div class="ua-landing-title">See the conditions shaping your next investment decision.</div>
    <div class="ua-landing-copy">
      {len(SIGNALS)} real macro and alternative-data signals, scored on first-print
      observations and connected to the stocks you own. Start with the market
      regime, then inspect the evidence behind any ticker.
    </div>
  </div>
  <div class="ua-landing-access">
    <strong>Browse before you subscribe</strong>
    <span>Today's Brief, the full Signal Dashboard, and market context are free. Pro starts at $20/month.</span>
  </div>
</section>
<div class="ua-stat-strip">
  <div class="ua-stat-item">
    <span class="ua-stat-num">{len(SIGNALS)}</span>
    <span class="ua-stat-label">Documented signals</span>
  </div>
  <div class="ua-stat-item">
    <span class="ua-stat-num">4–16w</span>
    <span class="ua-stat-label">Research horizon</span>
  </div>
  <div class="ua-stat-item">
    <span class="ua-stat-num">5</span>
    <span class="ua-stat-label">Primary-source families</span>
  </div>
  <div class="ua-stat-item">
    <span class="ua-stat-num">0</span>
    <span class="ua-stat-label">Synthetic observations</span>
  </div>
</div>
""", unsafe_allow_html=True)

_hcta1, _hcta2 = st.columns([1, 3.2], vertical_alignment="center")
with _hcta1:
    if st.button(
        "Open Today's Brief",
        type="primary",
        width="stretch",
        key="hero_cta_brief",
    ):
        st.switch_page("pages/2_Today_Digest.py")
with _hcta2:
    st.caption(
        f"Free to browse · Signals are {SCORE_COMPUTE_DESCRIPTION}."
    )

# ── LIVE SIGNAL PULSE ─────────────────────────────────────────────────────────
_bar_bull = f"{(_nb / _total * 100):.0f}%" if _total > 0 else "0%"
_bar_bear = f"{(_nr / _total * 100):.0f}%" if _total > 0 else "0%"

_top_bull_html = (
    f'<div style="font-size:0.72rem;color:var(--ua-green);margin-top:3px;font-weight:500;">'
    f'▲ {_h.escape(str(_top_bull))[:32]}</div>'
    if _top_bull else ""
)
_top_bear_html = (
    f'<div style="font-size:0.72rem;color:var(--ua-red);margin-top:3px;font-weight:500;">'
    f'▼ {_h.escape(str(_top_bear))[:32]}</div>'
    if _top_bear else ""
)

st.markdown(
    f'<div class="ua-slide-up-d4" style="background:rgba(var(--ua-card-rgb),0.82);border:1px solid rgba(var(--ua-green-rgb),0.22);'
    f'border-radius:18px;padding:26px 30px 22px;margin:28px auto 0;max-width:900px;'
    f'font-family:Inter,sans-serif;backdrop-filter:blur(20px) saturate(160%);-webkit-backdrop-filter:blur(20px) saturate(160%);'
    f'box-shadow:0 0 60px rgba(var(--ua-green-rgb),0.09),0 24px 64px rgba(var(--ua-shadow-rgb),calc(0.6*var(--ua-shadow-k))),inset 0 1px 0 rgba(var(--ua-onbg-rgb),0.05);">'
    # Top separator accent line
    f'<div style="position:relative;margin-bottom:18px;">'
    f'<div style="position:absolute;top:-26px;left:-30px;right:-30px;height:1px;'
    f'background:linear-gradient(90deg,transparent,rgba(var(--ua-green-rgb),0.35) 30%,'
    f'rgba(0,200,224,0.25) 60%,transparent);"></div>'
    f'</div>'
    f'<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:24px;">'
    # Left: regime label
    f'<div style="flex:1;min-width:200px;">'
    f'<div style="display:flex;align-items:center;gap:6px;font-size:0.58rem;letter-spacing:0.18em;'
    f'color:var(--ua-ink-mut);margin-bottom:10px;font-weight:700;">'
    f'<span class="ua-pulse-dot"></span>MACRO REGIME</div>'
    f'<div style="font-size:2.4rem;font-weight:900;color:{_bias_color};letter-spacing:-1px;'
    f'line-height:1.0;text-shadow:0 0 40px {_bias_color}44;">{_h.escape(_bias_label)}</div>'
    f'<div style="font-size:0.72rem;color:var(--ua-ink-label);margin-top:8px;">'
    f'across <b style="color:var(--ua-ink-mut);">{len(SIGNALS)}</b> tracked signals'
    f'{f" · {_total} scored" if _total < len(SIGNALS) else ""} · daily snapshot</div>'
    f'</div>'
    # Right: counter trio
    f'<div style="display:flex;gap:28px;flex-wrap:wrap;align-items:center;">'
    f'<div style="text-align:center;min-width:60px;" class="ua-kpi-animate ua-number-in">'
    f'<div style="font-size:2.8rem;font-weight:900;color:var(--ua-green);letter-spacing:-1.5px;'
    f'line-height:1.0;text-shadow:0 0 30px rgba(var(--ua-green-rgb),0.4);">{_nb}</div>'
    f'<div style="font-size:0.58rem;color:var(--ua-green);letter-spacing:0.14em;font-weight:700;'
    f'margin-top:3px;">BULLISH</div>'
    f'{_top_bull_html}'
    f'</div>'
    f'<div style="width:1px;height:60px;background:rgba(var(--ua-onbg-rgb),0.06);"></div>'
    f'<div style="text-align:center;min-width:60px;" class="ua-kpi-animate ua-number-in">'
    f'<div style="font-size:2.8rem;font-weight:900;color:var(--ua-red);letter-spacing:-1.5px;'
    f'line-height:1.0;text-shadow:0 0 30px rgba(var(--ua-red-rgb),0.35);">{_nr}</div>'
    f'<div style="font-size:0.58rem;color:var(--ua-red);letter-spacing:0.14em;font-weight:700;'
    f'margin-top:3px;">BEARISH</div>'
    f'{_top_bear_html}'
    f'</div>'
    f'<div style="width:1px;height:60px;background:rgba(var(--ua-onbg-rgb),0.06);"></div>'
    f'<div style="text-align:center;min-width:60px;" class="ua-kpi-animate ua-number-in">'
    f'<div style="font-size:2.8rem;font-weight:900;color:var(--ua-ink-label);letter-spacing:-1.5px;'
    f'line-height:1.0;">{_nn}</div>'
    f'<div style="font-size:0.58rem;color:var(--ua-ink-label);letter-spacing:0.14em;font-weight:700;'
    f'margin-top:3px;">NEUTRAL</div>'
    f'</div>'
    f'</div>'
    f'</div>'
    # Progress bar
    f'<div style="margin-top:20px;background:rgba(var(--ua-onbg-rgb),0.04);border-radius:6px;'
    f'height:5px;overflow:hidden;display:flex;gap:1px;">'
    f'<div style="width:{_bar_bull};background:linear-gradient(90deg,var(--ua-green),#00A847);'
    f'border-radius:6px 0 0 6px;transition:width 1s ease;"></div>'
    f'<div style="width:{_bar_bear};background:var(--ua-red);"></div>'
    f'<div style="flex:1;background:rgba(var(--ua-label-rgb),0.25);border-radius:0 6px 6px 0;"></div>'
    f'</div>'
    f'<div style="display:flex;justify-content:space-between;margin-top:7px;">'
    f'<div style="font-size:0.60rem;color:var(--ua-green);font-weight:600;">▲ Bullish {_bar_bull}</div>'
    f'<div style="font-size:0.60rem;color:var(--ua-ink-label);">{SCORE_COMPUTE_SHORT.capitalize()}</div>'
    f'<div style="font-size:0.60rem;color:var(--ua-red);font-weight:600;">Bearish {_bar_bear} ▼</div>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# Primary CTA
st.markdown("<div style='text-align:center;margin:24px 0 8px;'>", unsafe_allow_html=True)
_hcol1, _hcol2, _hcol3 = st.columns([2, 1.4, 2])
with _hcol2:
    if st.button("→ See Today's Full Signal Brief", type="primary", width="stretch", key="hero_cta"):
        st.switch_page("pages/2_Today_Digest.py")
st.markdown(
    "<div style='text-align:center;font-size:0.72rem;color:var(--ua-ink-mut);margin-top:6px;"
    "font-family:Inter,sans-serif;'>No account needed to browse signals</div>",
    unsafe_allow_html=True,
)
st.html(render_platform_note())

# ── MACRO LEAN BY DOMAIN (real category-average scores → SVG bar) ─────────────
# Complements the regime split above with breadth: which macro domains are
# leaning bullish vs bearish right now. Uses the SAME canonical snapshot
# (_hd["sectors"] = mean score per category), so it can't contradict the header.
try:
    from utils import ua_charts as _uac2
    _sect = _hd.get("sectors", {})
    if _sect and len(_sect) >= 2:
        _order = sorted(_sect.items(), key=lambda kv: -kv[1])
        # .title() would render "ai_infrastructure" as "Ai Infrastructure";
        # keep known acronyms upper-cased.
        _ACRO = {"Ai": "AI", "Fx": "FX", "Etf": "ETF", "Gdp": "GDP", "Cpi": "CPI",
                 "Us": "US", "Eu": "EU", "Oil": "Oil", "Fed": "Fed", "Ism": "ISM"}
        def _pretty_cat(_k: str) -> str:
            _w = str(_k).replace("_", " ").title().split()
            return " ".join(_ACRO.get(x, x) for x in _w)[:22]
        _cats2 = [_pretty_cat(k) for k, _ in _order]
        _vals2 = [round(float(v), 1) for _, v in _order]
        # Semantic per-bar colors: >55 bullish, <45 bearish, else neutral.
        _cols2 = [
            "var(--ua-pos,#48BC90)" if v >= 55
            else "var(--ua-neg,#E27767)" if v <= 45
            else "var(--ua-neutral,#7C84A8)"
            for v in _vals2
        ]
        _svg2 = _uac2.bar_h(_cats2, _vals2, max_v=100, colors=_cols2, W=620, H=max(150, 34 * len(_cats2) + 60))
        st.markdown(
            '<div style="max-width:900px;margin:26px auto 0;">'
            '<div style="font-family:var(--ua-display);font-size:1.35rem;font-weight:600;'
            'color:var(--ua-text,#ECEEF9);letter-spacing:-0.4px;">Where the macro is leaning, by domain.</div>'
            '<div style="font-family:Inter,sans-serif;font-size:0.84rem;color:var(--ua-muted,#9AA0BE);'
            'margin:4px 0 14px;line-height:1.6;">Average signal score in each domain — 50 is neutral, '
            'above is a tailwind, below is a headwind. One snapshot, no cherry-picking.</div>'
            f'<div style="background:var(--ua-bg-card,var(--ua-bg-card));border:1px solid var(--ua-border,rgba(var(--ua-onbg-rgb),0.08));'
            f'border-radius:14px;padding:16px 18px;">{_svg2}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
except Exception:
    pass

_home_perf.checkpoint("hero_and_market_summary")

# ── SIGNAL FLIP ALERT BANNER ──────────────────────────────────────────────────
try:
    _flip = _get_recent_signal_flip()
    if _flip:
        _fl_c   = "#00D566" if _flip["to_status"] == "bullish" else "#FF4444"
        _fl_r, _fl_g, _fl_b = int(_fl_c[1:3], 16), int(_fl_c[3:5], 16), int(_fl_c[5:7], 16)
        _fl_verb = "TURNED BULLISH" if _flip["to_status"] == "bullish" else "TURNED BEARISH"
        _fl_icon = "" if _flip["to_status"] == "bullish" else ""
        st.markdown(
            f'<div class="ua-pop-in" style="background:rgba({_fl_r},{_fl_g},{_fl_b},0.07);'
            f'border:1px solid rgba({_fl_r},{_fl_g},{_fl_b},0.28);'
            f'border-radius:10px;padding:11px 20px;margin:10px auto 0;max-width:860px;'
            f'display:flex;align-items:center;gap:10px;font-family:Inter,sans-serif;">'
            f'<span style="font-size:1.1rem;">{_fl_icon}</span>'
            f'<span style="font-size:0.60rem;letter-spacing:0.14em;font-weight:700;color:{_fl_c};"> JUST FLIPPED</span>'
            f'<span style="font-size:0.82rem;font-weight:600;color:var(--ua-ink);margin-left:2px;">{_h.escape(_flip["name"])}</span>'
            f'<span style="font-size:0.78rem;font-weight:700;color:{_fl_c};margin-left:2px;">{_fl_verb}</span>'
            f'<span style="font-size:0.70rem;color:var(--ua-ink-label);margin-left:6px;">Score: {_flip["score"]:.0f}/100</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
except Exception:
    pass

st.markdown("<br>", unsafe_allow_html=True)
_home_perf.checkpoint("signal_flip")

# ── ANONYMOUS "START HERE" GUIDE ─────────────────────────────────────────────
# Shown to visitors with no account — gives them an immediate orientation so
# they don't bounce because they don't know where to click first.
# Logged-in users get the full personalized onboarding checklist below instead.
_anon_user = not st.session_state.get("user")

if _home_section == "Dashboard":
    st.markdown(
        """
<div style="margin:12px 0 14px;">
  <div style="font-size:.64rem;font-weight:800;letter-spacing:.14em;
              text-transform:uppercase;color:var(--ua-ink-label);">Continue your research</div>
  <div style="font-size:.82rem;color:var(--ua-ink-mut);margin-top:5px;">
    Open a focused workspace instead of loading the full product tour.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    _dash_row_1 = st.columns(3)
    with _dash_row_1[0]:
        if st.button("Today's Brief", type="primary", width="stretch", key="dashboard_brief"):
            st.switch_page("pages/2_Today_Digest.py")
    with _dash_row_1[1]:
        if st.button("Signal Dashboard", width="stretch", key="cta_signals"):
            st.switch_page("pages/1_Signal_Dashboard.py")
    with _dash_row_1[2]:
        if st.button("Ticker Deep Dive", width="stretch", key="cta_dive"):
            st.switch_page("pages/3_Ticker_Deep_Dive.py")

    _dash_row_2 = st.columns(3)
    with _dash_row_2[0]:
        if st.button("Market Overview", width="stretch", key="cta_market"):
            st.switch_page("pages/5_Market_Overview.py")
    with _dash_row_2[1]:
        if st.button("My Watchlist", width="stretch", key="cta_watchlist"):
            st.switch_page("pages/10_Watchlist.py")
    with _dash_row_2[2]:
        if st.button("Signal Research", width="stretch", key="cta_validation"):
            st.switch_page("pages/51_Signal_Research.py")

    st.caption(
        "Choose Discover in the page rail for the full product tour and personal command "
        "center, or open Portfolio Intelligence for a full holding-by-holding exposure analysis."
    )
    render_footer()
    st.session_state["_ua_home_perf_last"] = _home_perf.finish("dashboard_actions_and_footer")
    st.stop()

# ── PERSONAL COMMAND CENTER (signed-in + has holdings) — Phase 2 ──────────────
# The first thing a returning user should see: what needs attention around their
# holdings, their largest shared macro exposure, and where to look next — one
# dominant insight, not ten equal cards. Reuses the Portfolio X-Ray + What
# Changed engines; per-ticker reads cached. Fully defensive; renders nothing if
# the user has no holdings (the instant-check / onboarding below handles that).
if not _anon_user:
    try:
        from utils import alerts_db as _cc_adb
        _cc_user = st.session_state.get("user")
        _cc_positions = []
        if _cc_user:
            try:
                from utils.portfolio_workspace import get_default_holdings as _cc_saved_holdings
                _cc_positions = [
                    {"ticker": row["ticker"], "weight": float(row["weight_pct"])}
                    for row in _cc_saved_holdings(_cc_user["id"])
                ]
            except Exception:
                _cc_positions = []
        # A saved portfolio is authoritative. Until a member creates one, their
        # watchlist remains a useful equal-weighted activation fallback.
        if not _cc_positions and _cc_user:
            _cc_positions = [
                {"ticker": row["ticker"], "weight": 1.0}
                for row in (_cc_adb.get_watchlist(_cc_user["id"]) or [])
            ]
        _cc_wl = [row["ticker"] for row in _cc_positions]
        if _cc_wl:
            from utils.command_center import build_command_center, render_command_center_html
            from utils.portfolio_xray import build_portfolio_xray
            from utils.what_changed import build_what_changed
            from utils.ticker_score import compute_full_ticker_score as _cc_score
            from utils.score_history import get_signal_diff as _cc_diff
            from utils.config import TICKERS as _CC_TK

            @st.cache_data(ttl=1800, show_spinner=False, max_entries=256)
            def _cc_read(_t: str):
                r = _cc_score(_t)
                return {
                    "ticker": _t, "score": r["confluence"]["overall_score"],
                    "corr_info": {k: {"weight": v.get("weight"), "significant": v.get("significant")}
                                  for k, v in r["corr_info"].items()},
                    "signal_scores": {k: {"score": v.get("score"), "status": v.get("status")}
                                      for k, v in r["signal_scores"].items()},
                    "sector": (_CC_TK.get(_t, {}) or {}).get("sector", ""),
                }

            _cc_inputs = []
            with st.spinner("Building your command center…"):
                for _position in _cc_positions[:12]:
                    try:
                        _cc_row = _cc_read(_position["ticker"])
                        _cc_row["weight"] = _position["weight"]
                        _cc_inputs.append(_cc_row)
                    except Exception:
                        continue
            if _cc_inputs:
                _cc_xray = build_portfolio_xray(_cc_inputs)
                try:
                    _cc_wcp = build_what_changed(_cc_diff(days_back=1), watchlist=_cc_wl)
                except Exception:
                    _cc_wcp = {}
                st.html(render_command_center_html(build_command_center(_cc_xray, _cc_wcp)))
                st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    except Exception:
        pass

_home_perf.checkpoint("command_center")

if _anon_user:
    # st.html (not st.markdown): multi-line indented HTML would be parsed as a
    # markdown code block and leak as raw text (same bug as nav/footer).
    st.html("""
<div style="background:rgba(var(--ua-card-rgb),0.72);border:1px solid rgba(var(--ua-onbg-rgb),0.09);
     border-radius:16px;padding:24px 28px;margin-bottom:32px;font-family:Inter,sans-serif;
     backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);">
  <div style="font-size:0.62rem;font-weight:700;letter-spacing:0.14em;color:var(--ua-ink-label);
              text-transform:uppercase;margin-bottom:14px;">Where to start → 3 steps</div>
  <div style="display:flex;gap:16px;flex-wrap:wrap;">

    <div style="flex:1;min-width:200px;background:rgba(var(--ua-green-rgb),0.06);
                border:1px solid rgba(var(--ua-green-rgb),0.18);border-radius:12px;padding:16px 18px;">
      <div style="font-size:1.3rem;margin-bottom:8px;"></div>
      <div style="font-size:0.84rem;font-weight:700;color:var(--ua-ink);margin-bottom:5px;">
        1 · Read Today's Brief
      </div>
      <div style="font-size:0.76rem;color:var(--ua-ink-mut);line-height:1.55;margin-bottom:10px;">
        One page. What the macro machine sees right now — which signals flipped,
        what the regime is, and what to watch.
      </div>
      <div style="font-size:0.70rem;color:var(--ua-green);font-weight:600;">→ Free · No account needed</div>
    </div>

    <div style="flex:1;min-width:200px;background:rgba(var(--ua-purple-rgb),0.06);
                border:1px solid rgba(var(--ua-purple-rgb),0.20);border-radius:12px;padding:16px 18px;">
      <div style="font-size:1.3rem;margin-bottom:8px;"></div>
      <div style="font-size:0.84rem;font-weight:700;color:var(--ua-ink);margin-bottom:5px;">
        2 · Browse the Signal Dashboard
      </div>
      <div style="font-size:0.76rem;color:var(--ua-ink-mut);line-height:1.55;margin-bottom:10px;">
        See all 47 macro signals sorted by strength. Filter by category.
        Each card explains what the signal means in plain English.
      </div>
      <div style="font-size:0.70rem;color:#A78BFA;font-weight:600;">→ Free · Signals scored daily</div>
    </div>

    <div style="flex:1;min-width:200px;background:rgba(var(--ua-cyan-rgb),0.06);
                border:1px solid rgba(var(--ua-cyan-rgb),0.20);border-radius:12px;padding:16px 18px;">
      <div style="font-size:1.3rem;margin-bottom:8px;"></div>
      <div style="font-size:0.84rem;font-weight:700;color:var(--ua-ink);margin-bottom:5px;">
        3 · Look up a stock you own
      </div>
      <div style="font-size:0.76rem;color:var(--ua-ink-mut);line-height:1.55;margin-bottom:10px;">
        Enter any ticker in Ticker Deep Dive — see which of the 47 signals
        historically move that stock, and what the confluence score is today.
      </div>
      <div style="font-size:0.70rem;color:var(--ua-cyan);font-weight:600;">→ Free · AAPL, NVDA, XOM and {SUPPORTED_TICKER_COUNT} supported tickers</div>
    </div>

  </div>
</div>
""")

# ── PERSONALIZATION — new user onboarding / return user "what changed" ────────
try:
    from utils.analytics import track, Event
    from utils.onboarding import get_onboarding_state, mark_step

    _sess_user = st.session_state.get("user")

    if _sess_user:
        _uid       = _sess_user.get("id")
        _uname     = (_sess_user.get("display_name") or _sess_user.get("email", "").split("@")[0])[:24]
        _created   = _sess_user.get("created_at")
        _ob        = get_onboarding_state(_uid, _created)

        if _ob["show_banner"]:
            # ── NEW USER: "Start Here" checklist ──────────────────────────────
            track(Event.ONBOARDING_STARTED, user_id=_uid, properties={"n_done": _ob["n_done"]})

            _done_n  = _ob["n_done"]
            _pct_int = int(_done_n / len(_ob["steps"]) * 100)
            _steps   = _ob["steps"]

            st.markdown(f"""
<div style="background:rgba(0,197,102,0.05);border:1px solid rgba(var(--ua-green-rgb),0.22);
     border-radius:16px;padding:22px 28px 20px;margin:0 auto 28px;max-width:860px;
     font-family:Inter,sans-serif;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px;margin-bottom:16px;">
    <div>
      <div style="font-size:0.60rem;color:var(--ua-green);letter-spacing:0.16em;font-weight:700;
                  text-transform:uppercase;margin-bottom:5px;"> Welcome, {_h.escape(_uname)}</div>
      <div style="font-size:1.05rem;font-weight:700;color:var(--ua-ink);letter-spacing:-0.3px;">
        Start here — 3 steps to your first macro read
      </div>
      <div style="font-size:0.76rem;color:var(--ua-ink-mut);margin-top:3px;">
        {_done_n} of 3 steps complete
      </div>
    </div>
    <div style="text-align:right;flex-shrink:0;">
      <div style="font-size:1.4rem;font-weight:800;color:var(--ua-green);">{_pct_int}%</div>
      <div style="font-size:0.60rem;color:var(--ua-ink-label);letter-spacing:0.08em;">DONE</div>
    </div>
  </div>
  <div style="background:rgba(var(--ua-onbg-rgb),0.05);border-radius:4px;height:4px;margin-bottom:18px;overflow:hidden;">
    <div style="width:{_pct_int}%;height:100%;background:linear-gradient(90deg,var(--ua-green),var(--ua-cyan));border-radius:4px;transition:width 0.6s ease;"></div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;">
""", unsafe_allow_html=True)

            for _step in _steps:
                _sc  = "#00D566" if _step["done"] else "#4A5280"
                _bg  = "rgba(0,213,102,0.07)" if _step["done"] else "rgba(255,255,255,0.02)"
                _brd = "rgba(0,213,102,0.22)" if _step["done"] else "rgba(255,255,255,0.07)"
                _chk = "✓" if _step["done"] else "○"
                _op  = "opacity:0.55;" if _step["done"] else ""
                st.markdown(f"""
<div style="background:{_bg};border:1px solid {_brd};border-radius:10px;padding:14px;{_op}">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
    <span style="font-size:1.1rem;">{_step["icon"]}</span>
    <span style="font-size:0.60rem;font-weight:800;color:{_sc};letter-spacing:0.1em;">{_chk} STEP</span>
  </div>
  <div style="font-size:0.82rem;font-weight:600;color:var(--ua-ink);margin-bottom:3px;">{_h.escape(_step["label"])}</div>
  <div style="font-size:0.70rem;color:var(--ua-ink-mut);line-height:1.55;">{_h.escape(_step["desc"])}</div>
</div>""", unsafe_allow_html=True)

            st.markdown("</div></div>", unsafe_allow_html=True)

            # Step navigation buttons
            _todo_steps = [s for s in _steps if not s["done"]]
            if _todo_steps:
                _next_step = _todo_steps[0]
                _ncol1, _ncol2, _ncol3 = st.columns([2, 1.5, 2])
                with _ncol2:
                    if st.button(
                        f'{_next_step["icon"]} {_next_step["label"]}',
                        type="primary",
                        width="stretch",
                        key="onboarding_cta",
                    ):
                        track(Event.ONBOARDING_STEP, user_id=_uid,
                              properties={"step": _next_step["id"]})
                        st.switch_page(_next_step["page"])

        else:
            # ── RETURNING USER: Welcome back + what changed ────────────────────
            track(Event.RETURNING_USER, user_id=_uid, properties={"page": "home"})

            # Pull recent signal changes from signal_snapshots
            @st.cache_data(ttl=1800, show_spinner=False, max_entries=1)
            def _get_signal_changes_cached() -> list[dict]:
                try:
                    from utils.db import engine as _dbe
                    import sqlalchemy as _sa
                    with _dbe.connect() as _c:
                        _rows = _c.execute(_sa.text("""
                            SELECT signal_id, status, score, snapshot_date
                            FROM signal_snapshots
                            ORDER BY signal_id, snapshot_date DESC
                        """)).mappings().all()
                    _by_sig: dict = {}
                    for _r in _rows:
                        _by_sig.setdefault(_r["signal_id"], []).append(dict(_r))
                    _changes = []
                    from utils.config import SIGNALS as _SIG
                    for _sid, _snaps in _by_sig.items():
                        if len(_snaps) < 2:
                            continue
                        _latest, _prev = _snaps[0], _snaps[1]
                        if _latest["status"] != _prev["status"]:
                            _changes.append({
                                "signal_id":   _sid,
                                "name":        _SIG.get(_sid, {}).get("name", _sid),
                                "to_status":   _latest["status"],
                                "from_status": _prev["status"],
                                "score":       _latest["score"],
                                "date":        _latest["snapshot_date"],
                            })
                    _changes.sort(key=lambda x: abs(x["score"] - 50), reverse=True)
                    return _changes[:4]
                except Exception:
                    return []

            _changes = _get_signal_changes_cached()

            # Return user greeting header
            st.markdown(f"""
<div style="background:rgba(var(--ua-card-rgb),0.55);border:1px solid rgba(var(--ua-onbg-rgb),0.07);
     border-radius:16px;padding:20px 28px 18px;margin:0 auto 24px;max-width:860px;
     font-family:Inter,sans-serif;">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
    <div>
      <div style="font-size:0.60rem;color:var(--ua-ink-label);letter-spacing:0.14em;font-weight:700;
                  text-transform:uppercase;margin-bottom:4px;">Welcome back</div>
      <div style="font-size:1.0rem;font-weight:700;color:var(--ua-ink);">
        {_h.escape(_uname)} · <span style="color:var(--ua-ink-mut);font-weight:400;font-size:0.88rem;">here's what's changed</span>
      </div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <span style="font-size:0.70rem;background:rgba(var(--ua-green-rgb),0.09);border:1px solid rgba(var(--ua-green-rgb),0.22);
            color:var(--ua-green);padding:4px 12px;border-radius:100px;font-weight:600;">
        {len(_changes)} signal{"s" if len(_changes) != 1 else ""} flipped recently
      </span>
    </div>
  </div>
""", unsafe_allow_html=True)

            if _changes:
                st.markdown('<div style="margin-top:14px;display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;">', unsafe_allow_html=True)
                for _ch in _changes:
                    _tc = "#00D566" if _ch["to_status"] == "bullish" else ("#FF4444" if _ch["to_status"] == "bearish" else "#6B7FBF")
                    _fc = "#FF4444" if _ch["from_status"] == "bullish" else ("#00D566" if _ch["from_status"] == "bearish" else "#6B7FBF")
                    _arrow = "↑" if _ch["to_status"] == "bullish" else ("↓" if _ch["to_status"] == "bearish" else "→")
                    st.markdown(f"""
<div style="background:rgba(var(--ua-onbg-rgb),0.025);border:1px solid rgba(var(--ua-onbg-rgb),0.06);
     border-radius:10px;padding:12px 14px;">
  <div title="{_h.escape(_ch["name"])}" style="font-size:0.68rem;color:var(--ua-ink-mut);margin-bottom:4px;font-weight:500;
              white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
    {_h.escape(_ch["name"])}
  </div>
  <div style="display:flex;align-items:center;gap:6px;">
    <span style="font-size:0.65rem;color:{_fc};font-weight:600;text-transform:uppercase;">
      {_ch["from_status"][:4]}
    </span>
    <span style="font-size:1.1rem;color:{_tc};font-weight:700;">{_arrow}</span>
    <span style="font-size:0.65rem;color:{_tc};font-weight:700;text-transform:uppercase;">
      {_ch["to_status"][:4]}
    </span>
    <span style="margin-left:auto;font-size:0.72rem;font-weight:700;
          background:rgba(var(--ua-onbg-rgb),0.05);border-radius:5px;padding:1px 7px;color:var(--ua-ink-soft);">
      {_ch["score"]:.0f}
    </span>
  </div>
</div>""", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.markdown(
                    '<div style="margin-top:10px;font-size:0.78rem;color:var(--ua-ink-label);">'
                    'No signal direction changes detected in recent snapshots. '
                    'Scores are stable — check Today\'s Brief for the full read.</div>',
                    unsafe_allow_html=True,
                )

            st.markdown("</div>", unsafe_allow_html=True)

except Exception:
    pass  # Never let personalization break the home page

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
_home_perf.checkpoint("personalization")

# ── CREDIBILITY STRIP ─────────────────────────────────────────────────────────
st.markdown("""
<div style="background:rgba(var(--ua-card-rgb),0.45);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
            border-top:1px solid rgba(var(--ua-onbg-rgb),0.05);border-bottom:1px solid rgba(var(--ua-onbg-rgb),0.05);
            padding:16px 0;margin:4px 0 28px;text-align:center;font-family:Inter,sans-serif;">
    <div style="font-size:0.57rem;letter-spacing:0.16em;color:var(--ua-ink-label);margin-bottom:12px;
                font-weight:700;">DATA SOURCED FROM THE SAME INSTITUTIONS WALL STREET USES</div>
    <div style="display:flex;justify-content:center;gap:8px;flex-wrap:wrap;align-items:center;">
        <span style="display:inline-flex;align-items:center;gap:6px;font-size:0.78rem;color:var(--ua-ink-mut);
                     background:rgba(var(--ua-green-rgb),0.05);border:1px solid rgba(var(--ua-green-rgb),0.12);
                     border-radius:8px;padding:5px 12px;">
            <span style="width:6px;height:6px;border-radius:50%;background:var(--ua-green);flex-shrink:0;"></span>
            <b style="color:var(--ua-ink);">FRED</b>&nbsp;· Federal Reserve</span>
        <span style="display:inline-flex;align-items:center;gap:6px;font-size:0.78rem;color:var(--ua-ink-mut);
                     background:rgba(var(--ua-cyan-rgb),0.05);border:1px solid rgba(var(--ua-cyan-rgb),0.12);
                     border-radius:8px;padding:5px 12px;">
            <span style="width:6px;height:6px;border-radius:50%;background:var(--ua-cyan);flex-shrink:0;"></span>
            <b style="color:var(--ua-ink);">SEC EDGAR</b>&nbsp;· Insider Filings</span>
        <span style="display:inline-flex;align-items:center;gap:6px;font-size:0.78rem;color:var(--ua-ink-mut);
                     background:rgba(var(--ua-purple-rgb),0.05);border:1px solid rgba(var(--ua-purple-rgb),0.12);
                     border-radius:8px;padding:5px 12px;">
            <span style="width:6px;height:6px;border-radius:50%;background:var(--ua-purple);flex-shrink:0;"></span>
            <b style="color:var(--ua-ink);">FINRA</b>&nbsp;· Short Interest</span>
        <span style="display:inline-flex;align-items:center;gap:6px;font-size:0.78rem;color:var(--ua-ink-mut);
                     background:rgba(245,158,11,0.05);border:1px solid rgba(245,158,11,0.12);
                     border-radius:8px;padding:5px 12px;">
            <span style="width:6px;height:6px;border-radius:50%;background:var(--ua-amber);flex-shrink:0;"></span>
            <b style="color:var(--ua-ink);">EIA</b>&nbsp;· Energy Data</span>
        <span style="display:inline-flex;align-items:center;gap:6px;font-size:0.78rem;color:var(--ua-ink-mut);
                     background:rgba(52,211,153,0.05);border:1px solid rgba(52,211,153,0.12);
                     border-radius:8px;padding:5px 12px;">
            <span style="width:6px;height:6px;border-radius:50%;background:#34D399;flex-shrink:0;"></span>
            <b style="color:var(--ua-ink);">13F Filings</b>&nbsp;· Institutional</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ── WHO THIS IS FOR ───────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;margin:8px 0 20px;font-family:Inter,sans-serif;">
    <div style="font-size:0.57rem;letter-spacing:0.18em;font-weight:700;color:var(--ua-purple);margin-bottom:8px;">
        WHO IS THIS FOR?
    </div>
    <div style="font-size:1.35rem;font-weight:800;color:var(--ua-ink);letter-spacing:-0.5px;">
        Anyone tired of investing blind
    </div>
</div>
""", unsafe_allow_html=True)

_who1, _who2, _who3, _who4 = st.columns(4)
_who_cards = [
    ("#00D566", "", "Active Traders",
     "Know the macro backdrop before entering a position. Stop guessing whether the environment supports your trade."),
    ("#7C3AED", "", "Long-Term Investors",
     "Get early warning when macro tailwinds are fading. Protect gains before the rotation happens."),
    ("#00C8E0", "", "Portfolio Managers",
     "Score every holding's macro exposure at once. Identify crowded positions before they unwind."),
    ("#F59E0B", "", "Research-Driven",
     "Follow primary sources — Fed data, SEC filings, FINRA — not analysts spinning narratives."),
]
for _col, (_ac, _icon, _title, _body) in zip([_who1, _who2, _who3, _who4], _who_cards):
    with _col:
        st.markdown(f"""
<div style="background:rgba(var(--ua-card-rgb),0.7);border:1px solid rgba(var(--ua-onbg-rgb),0.06);
            border-top:3px solid {_ac};border-radius:12px;padding:18px 14px;
            font-family:Inter,sans-serif;min-height:165px;text-align:center;">
    <div style="font-size:1.8rem;margin-bottom:10px;">{_icon}</div>
    <div style="font-size:0.85rem;font-weight:800;color:var(--ua-ink);margin-bottom:8px;">{_title}</div>
    <div style="font-size:0.73rem;color:var(--ua-ink-mut);line-height:1.6;">{_body}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ── INSTANT PORTFOLIO CHECK ───────────────────────────────────────────────────
if _data_loaded:
    st.markdown("""
<div style="background:rgba(var(--ua-card-rgb),0.82);border:1px solid rgba(var(--ua-cyan-rgb),0.22);
            border-radius:16px;padding:22px 26px 18px;margin:0 0 24px;
            font-family:Inter,sans-serif;
            backdrop-filter:blur(16px) saturate(150%);-webkit-backdrop-filter:blur(16px) saturate(150%);
            box-shadow:0 0 30px rgba(var(--ua-cyan-rgb),0.07),0 8px 32px rgba(var(--ua-shadow-rgb),calc(0.45*var(--ua-shadow-k))),inset 0 1px 0 rgba(var(--ua-onbg-rgb),0.04);">
    <div style="font-size:0.58rem;letter-spacing:0.18em;font-weight:700;color:var(--ua-cyan);
                margin-bottom:8px;"> INSTANT MACRO CHECK — NO ACCOUNT NEEDED</div>
    <div style="font-size:1.0rem;font-weight:800;color:var(--ua-ink);margin-bottom:4px;
                letter-spacing:-0.2px;">What does the macro say about your stocks right now?</div>
    <div style="font-size:0.77rem;color:var(--ua-ink-mut);line-height:1.55;">
        Enter 3–5 tickers you actually hold — we score each against 47 live signals, then map
        them as a portfolio: shared macro risks, your most-exposed holding, and hidden
        correlations. No account needed.
    </div>
</div>
""", unsafe_allow_html=True)

    with st.form("portfolio_check_form", clear_on_submit=False):
        _pf_ci, _pf_cb = st.columns([4, 1])
        with _pf_ci:
            _pf_input = st.text_input(
                "Tickers",
                placeholder="e.g. AAPL, NVDA, XOM, JPM, TLT",
                label_visibility="collapsed",
                key="pf_ticker_input",
            )
        with _pf_cb:
            _pf_submitted = st.form_submit_button("→ Check", type="primary", width="stretch")

    if _pf_submitted and _pf_input.strip():
        _pf_results = _score_tickers_from_cache(_pf_input, _raw_scores)
        if _pf_results:
            _pf_cols = st.columns(min(len(_pf_results), 5))
            for _pf_res, _pf_col in zip(_pf_results, _pf_cols):
                with _pf_col:
                    _pf_s   = _pf_res["score"]
                    _pf_st  = _pf_res["status"]
                    _pf_c   = "#00D566" if _pf_st == "bullish" else ("#FF4444" if _pf_st == "bearish" else "#6B7FBF")
                    _pf_arr = "▲" if _pf_st == "bullish" else ("▼" if _pf_st == "bearish" else "●")
                    _pf_bg  = "rgba(0,213,102,0.05)" if _pf_st == "bullish" else ("rgba(255,68,68,0.05)" if _pf_st == "bearish" else "rgba(107,127,191,0.04)")
                    _pf_sig_html = ""
                    for _sn, _ss, _ssc in _pf_res["top_signals"]:
                        _sc2 = "#00D566" if _ss == "bullish" else ("#FF4444" if _ss == "bearish" else "#6B7FBF")
                        _pf_sig_html += (
                            f'<div style="font-size:0.60rem;color:{_sc2};margin-top:3px;'
                            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                            f'{_h.escape(_sn[:28])}</div>'
                        )
                    _pf_unk = (
                        '<div style="font-size:0.57rem;color:#434E6A;margin-top:3px;">broad macro</div>'
                        if not _pf_res["known"] else ""
                    )
                    st.markdown(
                        f'<div style="background:{_pf_bg};border:1px solid {_pf_c}1A;'
                        f'border-top:3px solid {_pf_c};border-radius:10px;padding:14px 10px 12px;'
                        f'font-family:Inter,sans-serif;text-align:center;">'
                        f'<div style="font-size:1.0rem;font-weight:800;color:var(--ua-ink);'
                        f'margin-bottom:2px;">{_h.escape(_pf_res["ticker"])}</div>'
                        f'<div style="font-size:1.9rem;font-weight:900;color:{_pf_c};'
                        f'letter-spacing:-0.5px;line-height:1.1;">{_pf_arr}&nbsp;{_pf_s:.0f}</div>'
                        f'<div style="font-size:0.59rem;color:{_pf_c};font-weight:700;'
                        f'letter-spacing:0.1em;">{_pf_st.upper()}</div>'
                        f'{_pf_sig_html}{_pf_unk}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            # ── Onboarding "aha": these tickers SEEN AS A PORTFOLIO (Point 11) ─
            # The activation moment — a visitor seeing their own names mapped to
            # shared macro exposure, hidden correlations and the most-exposed
            # holding is when the product clicks. Reuses the Portfolio Macro
            # X-Ray engine; per-ticker reads cached so repeat loads are instant.
            # Fully defensive; framed as context, never advice.
            _ob_tickers = [r["ticker"] for r in _pf_results]
            if len(_ob_tickers) >= 2:
                try:
                    from utils.portfolio_xray import build_portfolio_xray, render_portfolio_xray_html
                    from utils.ticker_score import compute_full_ticker_score as _ob_score
                    from utils.config import TICKERS as _OB_TK

                    @st.cache_data(ttl=1800, show_spinner=False, max_entries=256)
                    def _ob_holding_read(_t: str):
                        r = _ob_score(_t)
                        return {
                            "ticker": _t,
                            "score": r["confluence"]["overall_score"],
                            "corr_info": {k: {"weight": v.get("weight"), "significant": v.get("significant")}
                                          for k, v in r["corr_info"].items()},
                            "signal_scores": {k: {"score": v.get("score"), "status": v.get("status")}
                                              for k, v in r["signal_scores"].items()},
                            "sector": (_OB_TK.get(_t, {}) or {}).get("sector", ""),
                        }

                    _ob_inputs = []
                    with st.spinner("Mapping these as a portfolio…"):
                        for _t in _ob_tickers[:8]:
                            try:
                                _ob_inputs.append(_ob_holding_read(_t))
                            except Exception:
                                continue
                    if len(_ob_inputs) >= 2:
                        st.markdown(
                            '<div style="font-size:0.60rem;letter-spacing:0.16em;font-weight:700;'
                            'color:#A78BFA;margin:16px 0 6px;font-family:Inter,sans-serif;">'
                            '⬡ NOW SEEN AS A PORTFOLIO</div>',
                            unsafe_allow_html=True,
                        )
                        st.html(render_portfolio_xray_html(build_portfolio_xray(_ob_inputs)))
                        st.markdown(
                            '<div style="font-size:0.68rem;color:var(--ua-ink-mut);margin-top:8px;'
                            'font-family:Inter,sans-serif;"> Want us to watch these for you? Save them to a '
                            'free watchlist and we\'ll flag the moment the macro around any of them '
                            'materially changes.</div>',
                            unsafe_allow_html=True,
                        )
                except Exception:
                    pass

            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            _pf_cta1, _pf_cta2, _pf_cta3 = st.columns([1.5, 1.5, 1])
            with _pf_cta1:
                if st.button("Full signal breakdown →", width="stretch", key="pf_cta_dive"):
                    st.switch_page("pages/3_Ticker_Deep_Dive.py")
            with _pf_cta2:
                if st.button("Save to Watchlist (free) →", width="stretch", key="pf_cta_wl"):
                    st.switch_page("pages/10_Watchlist.py")
            st.markdown(
                '<div style="font-size:0.62rem;color:#434E6A;margin-top:5px;font-family:Inter,sans-serif;">'
                'Score = macro Confluence Score (0–100) from 47 live signals. Not financial advice.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.caption("Couldn't find signals for those tickers — try SPY, QQQ, NVDA, XOM, or TLT.")

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── MACHINE INTELLIGENCE SECTION ─────────────────────────────────────────────
if _data_loaded:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    _nar = _narrative
    _nar_col1, _nar_col2 = st.columns([3, 2])

    with _nar_col1:
        _sect_items = "".join(
            f'<span style="display:inline-block;margin:2px 4px;padding:2px 8px;border-radius:6px;'
            f'font-size:0.64rem;'
            f'background:{"rgba(0,213,102,0.10)" if v == "BULLISH" else ("rgba(255,68,68,0.10)" if v == "BEARISH" else "rgba(107,127,191,0.08)")};'
            f'color:{"#00D566" if v == "BULLISH" else ("#FF4444" if v == "BEARISH" else "#6B7FBF")};'
            f'font-weight:600;border:1px solid {"rgba(0,213,102,0.2)" if v == "BULLISH" else ("rgba(255,68,68,0.2)" if v == "BEARISH" else "rgba(107,127,191,0.2)")};">'
            f'{k.split("/")[0].strip()}: {v}</span>'
            for k, v in _nar["sector_bias"].items()
        )
        _watch_html = (
            f'<div style="margin-top:10px;padding:8px 12px;background:rgba(var(--ua-cyan-rgb),0.06);'
            f'border-left:3px solid var(--ua-cyan);border-radius:0 6px 6px 0;font-size:0.74rem;color:var(--ua-cyan);">'
            f' {_nar["watch_note"]}</div>'
            if _nar.get("watch_note") else ""
        )
        st.markdown(
            f'<div class="ua-slide-up-d1" style="background:{_bias_bg};border:1px solid {_bias_color}22;'
            f'border-left:4px solid {_bias_color};'
            f'backdrop-filter:blur(14px) saturate(140%);-webkit-backdrop-filter:blur(14px) saturate(140%);'
            f'border-radius:12px;padding:20px 22px;font-family:Inter,sans-serif;">'
            f'<div style="font-size:0.58rem;font-weight:700;letter-spacing:0.14em;color:{_bias_color};'
            f'text-transform:uppercase;margin-bottom:6px;">MACHINE READS THE MARKET</div>'
            f'<div style="font-size:1.25rem;font-weight:800;color:var(--ua-ink);margin-bottom:10px;letter-spacing:-0.3px;">'
            f'{_nar.get("headline","")}</div>'
            f'<div style="font-size:0.83rem;color:var(--ua-ink-soft);line-height:1.7;margin-bottom:12px;">'
            f'{_nar["summary"]}</div>'
            f'<div style="margin-bottom:8px;">{_sect_items}</div>'
            f'{_watch_html}'
            f'</div>',
            unsafe_allow_html=True,
        )

    with _nar_col2:
        _bull_tkrs = _top_tkrs.get("bullish", [])[:5]
        _bear_tkrs = _top_tkrs.get("bearish", [])[:3]
        if _bull_tkrs or _bear_tkrs:
            _bull_rows = "".join(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:5px 0;border-bottom:1px solid rgba(var(--ua-onbg-rgb),0.05);">'
                f'<span style="font-weight:700;font-size:0.82rem;color:var(--ua-ink);">{r["ticker"]}</span>'
                f'<span style="font-size:0.72rem;color:var(--ua-ink-mut);flex:1;padding-left:8px;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px;">'
                f'{r["name"][:22]}</span>'
                f'<span style="font-size:0.78rem;font-weight:700;color:var(--ua-green);">'
                f'▲ {r["score"]:.0f}</span>'
                f'</div>'
                for r in _bull_tkrs
            )
            _bear_rows = "".join(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:5px 0;border-bottom:1px solid rgba(var(--ua-onbg-rgb),0.05);">'
                f'<span style="font-weight:700;font-size:0.82rem;color:var(--ua-ink);">{r["ticker"]}</span>'
                f'<span style="font-size:0.72rem;color:var(--ua-ink-mut);flex:1;padding-left:8px;'
                f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px;">'
                f'{r["name"][:22]}</span>'
                f'<span style="font-size:0.78rem;font-weight:700;color:var(--ua-red);">'
                f'▼ {r["score"]:.0f}</span>'
                f'</div>'
                for r in _bear_tkrs
            )
            st.markdown(
                f'<div class="ua-slide-up-d2" style="background:rgba(var(--ua-card-rgb),0.75);border:1px solid rgba(var(--ua-onbg-rgb),0.08);'
                f'backdrop-filter:blur(14px) saturate(140%);-webkit-backdrop-filter:blur(14px) saturate(140%);'
                f'border-radius:12px;padding:18px 20px;font-family:Inter,sans-serif;">'
                f'<div style="font-size:0.58rem;font-weight:700;letter-spacing:0.14em;color:var(--ua-green);'
                f'text-transform:uppercase;margin-bottom:12px;">WHAT THE MACHINE FAVORS NOW</div>'
                f'<div style="font-size:0.62rem;color:var(--ua-ink-label);margin-bottom:6px;font-weight:700;letter-spacing:0.08em;">MACRO TAILWIND ▲</div>'
                f'{_bull_rows}'
                f'<div style="font-size:0.62rem;color:var(--ua-ink-label);margin:12px 0 6px;font-weight:700;letter-spacing:0.08em;">MACRO HEADWIND ▼</div>'
                f'{_bear_rows}'
                f'<div style="font-size:0.62rem;color:var(--ua-ink-label);margin-top:12px;">'
                f'{len(SIGNALS)} macro signals · no price charts · pure fundamentals</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

_home_perf.checkpoint("portfolio_and_machine_sections")

# ── SIGNAL CONVERGENCE EVENTS ────────────────────────────────────────────────
_conv_events = get_convergence_events(days_back=7, min_signals=3)
if _conv_events:
    st.markdown("""
    <div style="font-size:1.1rem;font-weight:800;color:var(--ua-ink);margin:20px 0 6px;
                font-family:Inter,sans-serif;letter-spacing:-0.3px;">
         Signal Convergence Events
        <span style="font-size:0.70rem;font-weight:500;color:var(--ua-ink-mut);margin-left:10px;">
        3+ independent signals aligned on the same ticker in the last 7 days</span>
    </div>
    """, unsafe_allow_html=True)
    _conv_col1, _conv_col2 = st.columns(2)
    _bull_ev = [e for e in _conv_events if e["direction"] == "bullish"][:4]
    _bear_ev = [e for e in _conv_events if e["direction"] == "bearish"][:2]
    with _conv_col1:
        render_convergence_events(_bull_ev + _bear_ev[:1], max_bull=4, max_bear=1)
    with _conv_col2:
        if len(_bear_ev) > 1:
            render_convergence_events([], max_bull=0)
            render_convergence_events(_bear_ev[1:], max_bull=0, max_bear=2)
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

_home_perf.checkpoint("convergence_events")

# ── LATEST RESEARCH NOTE TEASER ──────────────────────────────────────────────
try:
    from utils.narrative_engine import get_latest_note as _get_ln
    _latest_note = _get_ln()
    if _latest_note:
        _note_regime   = _latest_note.get("regime", "")
        _note_headline = _latest_note.get("headline", "")
        _note_date     = _latest_note.get("note_date", "")
        _note_body     = _latest_note.get("body", "")
        _note_bull_n   = _latest_note.get("bull_count") or 0
        _note_bear_n   = _latest_note.get("bear_count") or 0

        import html as _html_escape
        _note_paras = [p.strip() for p in _note_body.split("\n\n") if p.strip()]
        _note_hl_clean = _html_escape.escape(_note_headline.strip("*#").strip())
        if _note_paras and _note_paras[0].strip("*#").strip() == _note_headline.strip("*#").strip():
            _note_paras = _note_paras[1:]
        _note_teaser = _html_escape.escape(_note_paras[0][:240] + "…") if _note_paras else ""

        _regime_fg = "#00D566" if any(x in _note_regime for x in ("BULL", "ON")) else (
                     "#FF4444" if any(x in _note_regime for x in ("BEAR", "OFF")) else "#6B7FBF")
        _regime_bg_note = f"rgba({','.join(str(int(_regime_fg[i:i+2],16)) for i in (1,3,5))},0.10)" if _regime_fg.startswith('#') else "rgba(107,127,191,0.10)"

        try:
            from datetime import datetime as _dtn
            _nd = _dtn.strptime(_note_date, "%Y-%m-%d")
            _note_date_str = _nd.strftime("%B %d, %Y")
        except Exception:
            _note_date_str = _note_date

        st.markdown(
            f'<div class="ua-slide-up-d1" style="background:rgba(var(--ua-card-rgb),0.78);border:1px solid rgba(var(--ua-onbg-rgb),0.07);'
            f'border-top:2px solid var(--ua-green);'
            f'backdrop-filter:blur(12px) saturate(130%);-webkit-backdrop-filter:blur(12px) saturate(130%);'
            f'border-radius:12px;padding:18px 22px;margin-bottom:24px;font-family:Inter,sans-serif;">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">'
            f'<span style="font-size:0.58rem;letter-spacing:0.16em;font-weight:700;color:var(--ua-green);"> LATEST RESEARCH NOTE</span>'
            f'<span style="font-size:0.64rem;font-weight:700;letter-spacing:0.08em;padding:2px 8px;'
            f'border-radius:5px;background:{_regime_bg_note};color:{_regime_fg};border:1px solid {_regime_fg}33;">{_note_regime}</span>'
            f'<span style="font-size:0.68rem;color:var(--ua-ink-mut);margin-left:auto;">{_note_date_str}</span>'
            f'</div>'
            f'<div style="font-size:1.0rem;font-weight:700;color:var(--ua-ink);line-height:1.3;margin-bottom:8px;letter-spacing:-0.2px;">'
            f'{_note_hl_clean}</div>'
            f'<div style="font-size:0.81rem;color:var(--ua-ink-soft);line-height:1.65;margin-bottom:10px;">'
            f'{_note_teaser}</div>'
            f'<div style="font-size:0.68rem;color:var(--ua-ink-mut);">'
            f'{_note_bull_n} bullish · {_note_bear_n} bearish signals</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Read Full Note →", key="home_note_cta", width="content"):
            st.switch_page("pages/2_Today_Digest.py")
except Exception:
    pass

_home_perf.checkpoint("latest_research_note")

# ── 3 CORE FEATURE SPOTLIGHTS ─────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;margin:40px 0 28px;font-family:Inter,sans-serif;">
    <div style="font-size:1.55rem;font-weight:800;color:var(--ua-ink);letter-spacing:-0.5px;
                margin-bottom:8px;">Three tools that change how you invest</div>
    <div style="font-size:0.86rem;color:var(--ua-ink-mut);max-width:460px;margin:0 auto;line-height:1.6;">
        Not a screener. Not a news aggregator. Something genuinely different.
    </div>
</div>
""", unsafe_allow_html=True)

_sp1, _sp2, _sp3 = st.columns(3)

with _sp1:
    st.markdown(f"""
<div class="ua-spotlight" style="--ua-spotlight-accent:linear-gradient(90deg,var(--ua-green),var(--ua-cyan));">
    <span class="ua-spotlight-icon"></span>
    <div class="ua-spotlight-tag" style="color:var(--ua-green);">DAILY INTELLIGENCE</div>
    <div class="ua-spotlight-title">Today's Brief — your 2-minute macro read</div>
    <div class="ua-spotlight-body">Every morning: which signals flipped overnight, what the
    macro bias is, and what it means for your holdings. Plain English. No jargon.
    Opt in for a 7 AM email digest.</div>
    <div class="ua-spotlight-proof" style="color:var(--ua-green);">
        → Currently: {_bias_label} across {_total} signals
    </div>
</div>
""", unsafe_allow_html=True)
    if st.button("Read Today's Brief →", width="stretch", key="cta_brief"):
        st.switch_page("pages/2_Today_Digest.py")

with _sp2:
    st.markdown(f"""
<div class="ua-spotlight" style="--ua-spotlight-accent:linear-gradient(90deg,var(--ua-purple),#A78BFA);">
    <span class="ua-spotlight-icon"></span>
    <div class="ua-spotlight-tag" style="color:#A78BFA;">STOCK-SPECIFIC ANALYSIS</div>
    <div class="ua-spotlight-title">Ticker Deep Dive — type any stock, get a macro report</div>
    <div class="ua-spotlight-body">Confluence Score (0–100), 30/60/90-day probability model,
    signal-by-signal breakdown, earnings markers, insider activity, news. Tells you
    <em>why</em> the macro environment is or isn't set up for this stock.</div>
    <div class="ua-spotlight-proof" style="color:#A78BFA;">
        → {SUPPORTED_TICKER_COUNT} supported tickers · validation results published
    </div>
</div>
""", unsafe_allow_html=True)
    if st.button("Try Ticker Deep Dive →", width="stretch", key="cta_dive"):
        st.switch_page("pages/3_Ticker_Deep_Dive.py")

with _sp3:
    st.markdown("""
<div class="ua-spotlight" style="--ua-spotlight-accent:linear-gradient(90deg,var(--ua-cyan),#06B6D4);">
    <span class="ua-spotlight-icon"></span>
    <div class="ua-spotlight-tag" style="color:var(--ua-cyan);">SMART ALERTS</div>
    <div class="ua-spotlight-title">Watchlist — know the moment a signal flips</div>
    <div class="ua-spotlight-body">Track any ticker with custom alert thresholds. Get notified
    when the Confluence Score crosses your level, a signal changes direction, or a 52-week
    high/low is hit. Morning email to opted-in users.</div>
    <div class="ua-spotlight-proof" style="color:var(--ua-cyan);">
        → Free · No Bloomberg terminal needed
    </div>
</div>
""", unsafe_allow_html=True)
    if st.button("Build Your Watchlist →", width="stretch", key="cta_watchlist"):
        st.switch_page("pages/10_Watchlist.py")

st.markdown("<br>", unsafe_allow_html=True)

# ── THE CONTRAST / ANCHOR ─────────────────────────────────────────────────────
st.markdown("""
<div style="background:linear-gradient(135deg,rgba(var(--ua-card-rgb),0.95),rgba(26,14,61,0.9));
            border:1px solid rgba(var(--ua-purple-rgb),0.2);
            border-radius:16px;padding:32px 36px;margin:8px 0 32px;
            font-family:Inter,sans-serif;text-align:center;">
    <div style="font-size:0.60rem;letter-spacing:0.18em;color:var(--ua-purple);margin-bottom:12px;
                font-weight:700;">THE EDGE ISN'T THE DATA — IT'S KNOWING WHICH SIGNALS TO WATCH</div>
    <div style="font-size:1.3rem;font-weight:800;color:var(--ua-ink);max-width:640px;margin:0 auto;
                line-height:1.4;letter-spacing:-0.3px;">
        Bloomberg Terminal charges <span style="color:var(--ua-amber);">$27,000/year</span>
        for access to this kind of macro data.<br>
        <span style="background:linear-gradient(135deg,var(--ua-green),var(--ua-cyan));
                     -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                     background-clip:text;">We built the same analysis from free public sources.</span>
    </div>
    <div style="font-size:0.82rem;color:var(--ua-ink-mut);margin-top:14px;max-width:560px;
                margin-left:auto;margin-right:auto;line-height:1.65;">
        FRED, SEC EDGAR, FINRA, and EIA are the same primary data sources
        institutional desks rely on. The difference is we packaged it for
        investors who don't have a six-figure data budget.
    </div>
</div>
""", unsafe_allow_html=True)

# ── "SIGNALS CALLED IT BEFORE" — PROOF SECTION ────────────────────────────────
st.markdown("""
<div style="font-size:1.1rem;font-weight:800;color:var(--ua-ink);text-align:center;
            margin:32px 0 6px;font-family:Inter,sans-serif;letter-spacing:-0.3px;">
    When these patterns showed up in past cycles
</div>
<div style="font-size:0.80rem;color:var(--ua-ink-mut);text-align:center;margin-bottom:20px;
            font-family:Inter,sans-serif;max-width:620px;margin-left:auto;margin-right:auto;line-height:1.6;">
    A few illustrative cases where similar readings preceded notable moves.
    These are selected examples for context — not a track record, and not evidence
    the signals predict returns. Past patterns don't repeat reliably.
</div>
""", unsafe_allow_html=True)

_proof_c1, _proof_c2, _proof_c3 = st.columns(3)
_PROOFS = [
    {
        "icon": "", "date": "January 2022", "color": "#FF4444",
        "signal": "HY Credit Spreads",
        "what": "ICE BofA OAS widened 60+ bps in 6 weeks — spread signal turned bearish Jan 4.",
        "outcome": "QQQ fell 32.6% by May. Nasdaq growth stocks down 40–70%.",
        "timing": "~6 weeks before",
    },
    {
        "icon": "", "date": "March 18–25, 2020", "color": "#00D566",
        "signal": "Insider Buying Cluster",
        "what": "Surge in Form 4 insider buys across 40+ companies in the same week.",
        "outcome": "Preceded the March 2020 low. S&P 500 +47% over the following 6 months.",
        "timing": "near the low",
    },
    {
        "icon": "", "date": "June–July 2023", "color": "#F59E0B",
        "signal": "EIA Crude Draw Streak",
        "what": "5 consecutive weekly crude inventory draws exceeding 3M bbl each.",
        "outcome": "XLE outperformed S&P 500 by ~12% over the following 8 weeks.",
        "timing": "3–5 weeks ahead",
    },
]
for _pi, (_col, _p) in enumerate(zip([_proof_c1, _proof_c2, _proof_c3], _PROOFS)):
    _proof_delay_cls = ["ua-pop-in", "ua-slide-up-d1", "ua-slide-up-d2"][_pi]
    with _col:
        st.markdown(
            f'<div class="{_proof_delay_cls}" style="background:rgba(var(--ua-card-rgb),0.78);border:1px solid rgba(var(--ua-onbg-rgb),0.07);'
            f'border-left:4px solid {_p["color"]};border-radius:10px;padding:18px 16px 14px;'
            f'backdrop-filter:blur(12px) saturate(130%);-webkit-backdrop-filter:blur(12px) saturate(130%);'
            f'font-family:Inter,sans-serif;min-height:195px;">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">'
            f'<span style="font-size:1.2rem;">{_p["icon"]}</span>'
            f'<div>'
            f'<div style="font-size:0.57rem;letter-spacing:0.12em;color:var(--ua-ink-label);font-weight:700;">{_p["date"]}</div>'
            f'<div style="font-size:0.84rem;font-weight:700;color:var(--ua-ink);">{_p["signal"]}</div>'
            f'</div></div>'
            f'<div style="font-size:0.75rem;color:var(--ua-ink-soft);line-height:1.55;margin-bottom:10px;">{_p["what"]}</div>'
            f'<div style="font-size:0.78rem;font-weight:700;color:{_p["color"]};line-height:1.4;margin-bottom:8px;">{_p["outcome"]}</div>'
            f'<span style="font-size:0.60rem;padding:3px 8px;border-radius:5px;'
            f'background:{_p["color"]}18;color:{_p["color"]};font-weight:700;'
            f'letter-spacing:0.06em;">{_p["timing"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown("""
<div style="text-align:center;font-size:0.66rem;color:#434E6A;margin-top:8px;
            font-family:Inter,sans-serif;">
    Past patterns don't guarantee future results. Historical examples for educational purposes only.
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ── SECTOR ROTATION TEASER ────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:1.1rem;font-weight:800;color:var(--ua-ink);font-family:Inter,sans-serif;
            margin-bottom:4px;letter-spacing:-0.3px;">Sector Rotation Signal Map — live preview</div>
<div style="font-size:0.80rem;color:var(--ua-ink-mut);margin-bottom:16px;font-family:Inter,sans-serif;">
    Which sectors do the signals currently favor? Scored daily.
</div>
""", unsafe_allow_html=True)

_SECTOR_META = {
    "ai_infrastructure": ("Technology & AI",   "#7C3AED"),
    "energy":            ("Energy",             "#F59E0B"),
    "nuclear":           ("Nuclear/Utilities",  "#00C8E0"),
    "financials":        ("Financials",         "#00D566"),
    "healthcare":        ("Healthcare",         "#34D399"),
    "consumer":          ("Consumer",           "#EC4899"),
    "industrials":       ("Industrials",        "#06B6D4"),
    "macro":             ("Macro Backdrop",     "#8892AA"),
}

try:
    _sec = _hd.get("sectors", {})
    if _sec:
        _sorted = sorted(_sec.items(), key=lambda x: -x[1])
        _sc_cols = st.columns(4)
        for _i, (_cat, _avg) in enumerate(_sorted[:8]):
            _name, _accent = _SECTOR_META.get(_cat, (_cat.title(), "#8892AA"))
            _arrow  = "▲" if _avg >= 60 else ("▼" if _avg <= 40 else "●")
            _sc     = "#00D566" if _avg >= 60 else ("#FF4444" if _avg <= 40 else "#6B7FBF")
            _bg     = "rgba(0,213,102,0.06)" if _avg >= 60 else ("rgba(255,68,68,0.06)" if _avg <= 40 else "rgba(18,21,30,0.6)")
            with _sc_cols[_i % 4]:
                st.markdown(f"""
<div style="background:{_bg};border:1px solid rgba(var(--ua-onbg-rgb),0.06);border-left:3px solid {_sc};
            border-radius:8px;padding:12px 14px;margin-bottom:8px;font-family:Inter,sans-serif;">
    <div style="font-size:0.75rem;font-weight:600;color:#C8D0E4;margin-bottom:4px;">{_name}</div>
    <div style="font-size:1.5rem;font-weight:800;color:{_sc};letter-spacing:-0.5px;">{_arrow} {_avg:.0f}</div>
</div>
""", unsafe_allow_html=True)
    else:
        st.caption("Sector scores loading — refresh in a moment.")

    _smc, _ = st.columns([1, 3])
    with _smc:
        if st.button("Full Sector View →", width="stretch", key="cta_sector"):
            st.switch_page("pages/42_Sector_View.py")
except Exception:
    st.caption("Sector preview unavailable. Open the Sector View page directly.")

st.divider()

# ── WHY THIS ISN'T A SCREENER ─────────────────────────────────────────────────
_da, _db = st.columns(2)

with _da:
    st.markdown("""
<div style="font-family:Inter,sans-serif;">
<div style="font-size:1.05rem;font-weight:800;color:var(--ua-red);margin-bottom:10px;letter-spacing:-0.2px;">
    What traditional screeners miss
</div>
<div style="font-size:0.83rem;color:var(--ua-ink-soft);line-height:1.7;">
    Stock screeners filter on price, P/E, and volume. They tell you what
    <i>has happened</i> to a stock — not what's coming. That's rear-view-mirror investing.<br><br>
    By the time a move shows up in price and volume, institutional desks have
    already positioned. The professionals were watching leading economic signals
    4 to 16 weeks earlier.
</div>
<br>
<div style="font-size:1.05rem;font-weight:800;color:var(--ua-green);margin-bottom:10px;letter-spacing:-0.2px;">
    What leading signals actually predict
</div>
<div style="font-size:0.83rem;color:var(--ua-ink-soft);line-height:1.7;">
    • Trucking freight falls → retail earnings weaken ~6 weeks later<br>
    • Uranium spot rises → nuclear energy stocks follow<br>
    • Credit spreads widen → broad market pullback precedes it 4–8 weeks<br>
    • Hyperscaler capex accelerates → AI infrastructure stocks outperform<br><br>
    This is what hedge funds call <b style="color:var(--ua-ink);">alternative data</b>.
    They pay $50K–$500K/year for it. We built it from public sources.
</div>
</div>
""", unsafe_allow_html=True)

with _db:
    st.markdown("""
<div style="font-family:Inter,sans-serif;">
<div style="font-size:1.05rem;font-weight:800;color:var(--ua-ink);margin-bottom:10px;letter-spacing:-0.2px;">
    What you get that you can't get anywhere else — for free
</div>
""", unsafe_allow_html=True)

    _diffs = [
        ("Signal Lead Time",
         "Each signal comes with a measured historical lead time — how many weeks "
         "ahead it typically precedes price movement. Not guesswork."),
        ("Pre-Earnings Track Record",
         "See what the Confluence Score said 7–45 days before each past earnings event "
         "vs. the actual EPS beat or miss."),
        ("Confluence Score",
         "How many independent signals agree? One bullish signal is noise. "
         "Seven agreeing signals is a thesis."),
        ("Honest Validation",
         "We publish our backtest results even when they're not impressive. "
         "See the Signal Research Center for validation, outcomes, and data quality."),
        ("Plain-English Causal Logic",
         "Not just 'this signal correlates.' We explain the economic mechanism: "
         "why this indicator moves this sector, specifically."),
    ]
    for _title, _body in _diffs:
        st.markdown(f"""
<div style="border-left:3px solid var(--ua-green);padding:8px 14px;margin-bottom:10px;
            background:rgba(var(--ua-green-rgb),0.04);border-radius:0 8px 8px 0;">
    <div style="font-size:0.83rem;font-weight:700;color:var(--ua-ink);margin-bottom:3px;font-family:Inter,sans-serif;">{_title}</div>
    <div style="font-size:0.77rem;color:var(--ua-ink-soft);line-height:1.55;font-family:Inter,sans-serif;">{_body}</div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ── HOW TO USE IN 4 STEPS ────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:1.1rem;font-weight:800;color:var(--ua-ink);font-family:Inter,sans-serif;
            margin-bottom:18px;letter-spacing:-0.3px;">Start generating insight in under 5 minutes</div>
""", unsafe_allow_html=True)

_steps = [
    ("1", "#00D566", "", "Read Today's Brief",
     "2-minute macro morning read. Which signals are bullish, which are bearish, what it means for your stocks.",
     "pages/2_Today_Digest.py", "Open Today's Brief →", "cta_s1"),
    ("2", "#F59E0B", "", "Check the Sector Map",
     "See which sectors the signals currently favor. Find where the macro tailwinds are pointing right now.",
     "pages/12_Sector_Map.py", "Open Sector Map →", "cta_s2"),
    ("3", "#7C3AED", "", "Deep Dive a Ticker",
     "Type any stock. Get a Confluence Score, signal breakdown, earnings history, and bull/bear case.",
     "pages/3_Ticker_Deep_Dive.py", "Open Deep Dive →", "cta_s3"),
    ("4", "#00C8E0", "", "Set Up Alerts",
     "Save your stocks. Get emailed when signals flip — hourly watchlist alerts, 7 AM digest, or Discord/Slack webhooks.",
     "pages/10_Watchlist.py", "Open Watchlist →", "cta_s4"),
]

_st_cols = st.columns(4)
for _col, (_n, _ac, _icon, _title, _body, _page, _btn, _key) in zip(_st_cols, _steps):
    with _col:
        st.markdown(f"""
<div class="ua-step" style="--ua-step-accent:{_ac};margin-bottom:8px;min-height:185px;">
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
        <div class="ua-step-num" style="color:{_ac};">{_n}</div>
        <div style="font-size:1.5rem;">{_icon}</div>
    </div>
    <div class="ua-step-title">{_title}</div>
    <div class="ua-step-body">{_body}</div>
</div>
""", unsafe_allow_html=True)
        if st.button(_btn, width="stretch", key=_key):
            st.switch_page(_page)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── WHAT USERS SAY ────────────────────────────────────────────────────────────
st.divider()
st.markdown("""
<div style="text-align:center;margin:8px 0 24px;font-family:Inter,sans-serif;">
    <div style="font-size:0.57rem;letter-spacing:0.18em;font-weight:700;color:var(--ua-amber);margin-bottom:8px;">
        WHAT USERS SAY
    </div>
    <div style="font-size:1.2rem;font-weight:800;color:var(--ua-ink);letter-spacing:-0.3px;">
        Real feedback from the community
    </div>
</div>
""", unsafe_allow_html=True)

_t1, _t2, _t3 = st.columns(3)
_testimonials = [
    ("#00D566", "R.K.", "Active trader, 12 years",
     "\"The Confluence Score on XLE was 78 when I entered. Energy sector outperformed the next 6 weeks. "
     "This is the kind of pre-move signal I was paying $3K/year to get elsewhere.\""),
    ("#7C3AED", "M.T.", "Retail investor, r/investing",
     "\"I'd never heard of 'credit spreads as a leading indicator' before this. Now I check it every Monday. "
     "Made me completely rethink how I look at sector positioning.\""),
    ("#00C8E0", "D.P.", "Portfolio analyst",
     "\"The insider cluster detection flagged a healthcare position I was holding 3 weeks before the company "
     "announced a secondary offering. Pattern is exactly what Form 4 research shows works.\""),
]
for _col, (_ac, _name, _role, _quote) in zip([_t1, _t2, _t3], _testimonials):
    with _col:
        st.markdown(f"""
<div style="background:rgba(var(--ua-card-rgb),0.78);border:1px solid rgba(var(--ua-onbg-rgb),0.07);
            border-left:4px solid {_ac};border-radius:12px;padding:20px 18px;
            font-family:Inter,sans-serif;">
    <div style="font-size:0.82rem;color:var(--ua-ink-soft);line-height:1.7;margin-bottom:14px;
                font-style:italic;">{_quote}</div>
    <div style="display:flex;align-items:center;gap:10px;">
        <div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,{_ac}44,{_ac}22);
                    border:2px solid {_ac}55;display:flex;align-items:center;justify-content:center;
                    font-size:0.8rem;font-weight:800;color:{_ac};">{_name[0]}</div>
        <div>
            <div style="font-size:0.82rem;font-weight:700;color:var(--ua-ink);">{_name}</div>
            <div style="font-size:0.68rem;color:var(--ua-ink-label);">{_role}</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── ALERTS & AUTOMATION FEATURE SECTION ──────────────────────────────────────
st.divider()

st.markdown("""
<div style="text-align:center;margin-bottom:6px;font-family:Inter,sans-serif;">
    <div style="font-size:0.58rem;letter-spacing:0.18em;font-weight:700;color:var(--ua-cyan);margin-bottom:8px;">
        NEW — ALERTS &amp; AUTOMATION
    </div>
    <div style="font-size:1.15rem;font-weight:800;color:var(--ua-ink);letter-spacing:-0.3px;line-height:1.35;">
        The signals come to you — you don't chase them
    </div>
    <div style="font-size:0.82rem;color:var(--ua-ink-mut);margin-top:6px;max-width:560px;margin-left:auto;margin-right:auto;line-height:1.6;">
        Most investors miss signal flips because they're not checking the dashboard at the right moment.
        Pro delivers the insight automatically — wherever you work.
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

_al1, _al2, _al3, _al4 = st.columns(4)

_alert_cards = [
    ("#00C8E0", "", "Daily X/Twitter Feed",
     "Every morning at 9 AM ET, @UnstructuredAlpha tweets which signals flipped overnight and what it means. "
     "Follow once, stay informed forever."),
    ("#00D566", "", "Watchlist Email Alerts",
     "When a signal on any of your watchlist tickers crosses a threshold, you get an email — "
     "automatically, hourly. No logging in required."),
    ("#F59E0B", "", "7 AM Morning Digest",
     "A Seeking Alpha-style macro briefing lands in your inbox before market open — "
     "bull/bear signal counts, top movers, the regime in plain English."),
    ("#A78BFA", "", "Discord / Slack Webhooks",
     "Send signal alerts directly into your Discord server or Slack workspace. "
     "Your whole team sees the flip the moment it happens."),
]

for _col, (_ac, _icon, _title, _body) in zip([_al1, _al2, _al3, _al4], _alert_cards):
    with _col:
        st.markdown(f"""
<div style="background:rgba(var(--ua-card-rgb),0.7);border:1px solid rgba(var(--ua-onbg-rgb),0.07);
            border-top:3px solid {_ac};border-radius:10px;padding:16px 14px;
            font-family:Inter,sans-serif;min-height:180px;">
    <div style="font-size:1.6rem;margin-bottom:8px;">{_icon}</div>
    <div style="font-size:0.82rem;font-weight:700;color:var(--ua-ink);margin-bottom:6px;">{_title}</div>
    <div style="font-size:0.75rem;color:var(--ua-ink-mut);line-height:1.6;">{_body}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
_ac1, _ac2, _ac3 = st.columns([2, 1.4, 2])
with _ac2:
    if st.button("Get All Alerts →", type="primary", width="stretch", key="cta_alerts_section"):
        st.switch_page("pages/29_Upgrade.py")

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ── SIGNAL STRATEGY BACKTEST TEASER ─────────────────────────────────────────
st.markdown("""
<div style="background:linear-gradient(135deg,rgba(var(--ua-card-rgb),0.95),rgba(14,24,50,0.95));
            border:1px solid rgba(99,102,241,0.25);border-radius:16px;
            padding:28px 32px;margin:8px 0 28px;font-family:Inter,sans-serif;">
  <div style="display:flex;align-items:flex-start;gap:28px;flex-wrap:wrap;">
    <div style="flex:1;min-width:260px;">
      <div style="font-size:0.58rem;letter-spacing:0.18em;font-weight:700;color:#818cf8;margin-bottom:10px;">
        SIGNAL BACKTESTER · PORTFOLIO INTELLIGENCE
      </div>
      <div style="font-size:1.1rem;font-weight:800;color:var(--ua-ink);letter-spacing:-0.3px;
                  line-height:1.35;margin-bottom:10px;">
        Test signal rules without leaving the portfolio workspace
      </div>
      <div style="font-size:0.83rem;color:var(--ua-ink-soft);line-height:1.7;margin-bottom:14px;">
        The former standalone strategy page now lives inside Portfolio Intelligence,
        alongside portfolio backtests, stress scenarios, exposure, and basket construction.
        Build one signal rule, compare it with SPY, then evaluate it in portfolio context.
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;">
        <span style="font-size:0.68rem;font-weight:600;background:rgba(99,102,241,0.12);
                     color:#818cf8;border:1px solid rgba(99,102,241,0.25);border-radius:5px;
                     padding:3px 9px;">7 macro signals</span>
        <span style="font-size:0.68rem;font-weight:600;background:rgba(99,102,241,0.12);
                     color:#818cf8;border:1px solid rgba(99,102,241,0.25);border-radius:5px;
                     padding:3px 9px;">Rolling 252-day percentile</span>
        <span style="font-size:0.68rem;font-weight:600;background:rgba(99,102,241,0.12);
                     color:#818cf8;border:1px solid rgba(99,102,241,0.25);border-radius:5px;
                     padding:3px 9px;">LONG / REDUCED / CASH</span>
        <span style="font-size:0.68rem;font-weight:600;background:rgba(34,197,94,0.10);
                     color:#22c55e;border:1px solid rgba(34,197,94,0.25);border-radius:5px;
                     padding:3px 9px;">Pro workspace</span>
      </div>
    </div>
    <div style="min-width:160px;text-align:center;padding-top:4px;">
      <div style="font-size:0.65rem;color:var(--ua-ink-label);margin-bottom:4px;">Current position</div>
      <div style="font-size:0.60rem;color:var(--ua-ink-label);margin-top:6px;">Based on live macro signals</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

_strat_c1, _strat_c2, _strat_c3 = st.columns([2, 1.4, 2])
with _strat_c2:
    if st.button("Run the Backtest →", width="stretch", key="cta_strat_hero"):
        st.session_state["portfolio_suite_section_rail"] = "Signal Backtester"
        st.switch_page("pages/44_Portfolio_Suite.py")

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── PRO UPGRADE BANNER ────────────────────────────────────────────────────────
st.markdown("""
<div class="ua-pro-banner">
    <div style="display:flex;align-items:center;justify-content:space-between;
                flex-wrap:wrap;gap:20px;">
        <div style="flex:1;min-width:280px;">
            <div style="font-size:0.58rem;letter-spacing:0.18em;font-weight:700;color:#A78BFA;
                        margin-bottom:8px;">UNSTRUCTURED ALPHA PRO</div>
            <div style="font-size:1.1rem;font-weight:800;color:var(--ua-ink);letter-spacing:-0.3px;
                        margin-bottom:6px;line-height:1.3;">
                All the tools. Plus alerts, automation,<br>and the machine working for you 24/7.
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;">
                <span style="font-size:0.68rem;font-weight:600;color:#A78BFA;
                             background:rgba(var(--ua-purple-rgb),0.12);border:1px solid rgba(var(--ua-purple-rgb),0.28);
                             border-radius:5px;padding:3px 9px;"> Morning Digest</span>
                <span style="font-size:0.68rem;font-weight:600;color:#A78BFA;
                             background:rgba(var(--ua-purple-rgb),0.12);border:1px solid rgba(var(--ua-purple-rgb),0.28);
                             border-radius:5px;padding:3px 9px;">Daily X/Twitter Signals</span>
                <span style="font-size:0.68rem;font-weight:600;color:#A78BFA;
                             background:rgba(var(--ua-purple-rgb),0.12);border:1px solid rgba(var(--ua-purple-rgb),0.28);
                             border-radius:5px;padding:3px 9px;"> Watchlist Email Alerts</span>
                <span style="font-size:0.68rem;font-weight:600;color:#A78BFA;
                             background:rgba(var(--ua-purple-rgb),0.12);border:1px solid rgba(var(--ua-purple-rgb),0.28);
                             border-radius:5px;padding:3px 9px;"> Discord/Slack Webhooks</span>
                <span style="font-size:0.68rem;font-weight:600;color:#A78BFA;
                             background:rgba(var(--ua-purple-rgb),0.12);border:1px solid rgba(var(--ua-purple-rgb),0.28);
                             border-radius:5px;padding:3px 9px;"> Signal Backtester</span>
                <span style="font-size:0.68rem;font-weight:600;color:#A78BFA;
                             background:rgba(var(--ua-purple-rgb),0.12);border:1px solid rgba(var(--ua-purple-rgb),0.28);
                             border-radius:5px;padding:3px 9px;"> Factor Exposure</span>
                <span style="font-size:0.68rem;font-weight:600;color:#A78BFA;
                             background:rgba(var(--ua-purple-rgb),0.12);border:1px solid rgba(var(--ua-purple-rgb),0.28);
                             border-radius:5px;padding:3px 9px;">Unlimited Watchlist</span>
            </div>
        </div>
        <div style="text-align:center;min-width:160px;">
            <div style="font-size:0.62rem;color:var(--ua-ink-label);letter-spacing:0.08em;margin-bottom:4px;
                        text-decoration:line-through;">Bloomberg: $27,000/yr</div>
            <div style="font-size:2.6rem;font-weight:900;letter-spacing:-1.5px;line-height:1.0;
                        background:linear-gradient(135deg,var(--ua-ink),#A78BFA);
                        -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                        background-clip:text;">$20<span style="font-size:1rem;font-weight:400;
                        -webkit-text-fill-color:var(--ua-ink-mut);">/mo</span></div>
            <div style="font-size:0.72rem;color:#34D399;font-weight:700;margin-top:4px;">
                ✓ 7-day free trial · Cancel anytime</div>
            <div style="font-size:0.62rem;color:var(--ua-ink-label);margin-top:2px;">
                48-hour money-back guarantee</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)
_pro_col1, _pro_col2, _pro_col3 = st.columns([2.5, 1.2, 2.5])
with _pro_col2:
    if st.button("Start 7-Day Free Trial →", type="primary", width="stretch", key="cta_pro_mid"):
        st.switch_page("pages/29_Upgrade.py")

st.divider()
_home_perf.checkpoint("feature_and_pro_sections")

# ── REFERRAL BANNER ───────────────────────────────────────────────────────────
# Non-blocking: anonymous visitors skip entirely; errors never surface to user.
# Identity is already established by the shared header before this late-page
# section. Re-initializing the cookie component and re-verifying the remember
# token here added a second auth round-trip to every signed-in Home render.
try:
    from utils.billing import effective_is_pro
    from utils.referral import get_referral_stats

    _ref_user = st.session_state.get("user")

    if _ref_user:
        _ref_tier  = "pro" if effective_is_pro(_ref_user) else "free"
        _ref_stats = get_referral_stats(_ref_user["id"])
        _ref_link  = _ref_stats["link"]

        if _ref_tier == "free":
            # Full referral card for free users — motivate sharing
            st.markdown("""
<div style="background:linear-gradient(135deg,rgba(var(--ua-green-rgb),0.08),rgba(var(--ua-cyan-rgb),0.08));
            border:1px solid rgba(var(--ua-green-rgb),0.25);border-radius:12px;
            padding:22px 28px 20px;margin-bottom:6px;">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
    <span style="font-size:1.1rem;font-weight:800;color:var(--ua-ink);font-family:Inter,sans-serif;
                 letter-spacing:-0.3px;">Invite a friend — both of you win</span>
  </div>
  <div style="font-size:0.88rem;color:#9DAFC8;font-family:Inter,sans-serif;margin-bottom:14px;
              line-height:1.55;">
    Your friend gets a <strong style="color:#34D399;">14-day free trial</strong> (double the normal 7 days).
    You get <strong style="color:#34D399;">1 free month of Pro</strong> the moment they subscribe — automatically applied to your bill.
  </div>
  <div style="font-size:0.78rem;color:#6B7A95;font-family:Inter,sans-serif;margin-bottom:10px;
              font-weight:600;letter-spacing:0.4px;text-transform:uppercase;">Your referral link</div>
</div>
""", unsafe_allow_html=True)
            st.code(_ref_link, language=None)
            _rc1, _rc2, _rc3 = st.columns(3)
            with _rc1:
                st.metric("Friends referred",  _ref_stats["total_referred"])
            with _rc2:
                st.metric("Converted to Pro",  _ref_stats["total_converted"])
            with _rc3:
                st.metric("Free months earned", _ref_stats["months_earned"])

        else:
            # Pro users — compact share strip
            st.markdown("""
<div style="background:rgba(var(--ua-green-rgb),0.06);border:1px solid rgba(var(--ua-green-rgb),0.18);
            border-radius:8px;padding:14px 20px 12px;margin-bottom:6px;">
  <div style="font-size:0.9rem;font-weight:700;color:var(--ua-ink);font-family:Inter,sans-serif;
              margin-bottom:6px;"> Share Unstructured Alpha</div>
  <div style="font-size:0.82rem;color:#9DAFC8;font-family:Inter,sans-serif;margin-bottom:10px;">
    Friends get a 14-day free trial via your link. You earn 1 free month every time one subscribes.
  </div>
</div>
""", unsafe_allow_html=True)
            st.code(_ref_link, language=None)
            _rs1, _rs2, _rs3 = st.columns(3)
            with _rs1:
                st.metric("Referred",       _ref_stats["total_referred"])
            with _rs2:
                st.metric("Converted",      _ref_stats["total_converted"])
            with _rs3:
                st.metric("Months earned",  _ref_stats["months_earned"])

        st.divider()

except Exception:
    # Any failure (DB offline, missing table, import error) is silently swallowed.
    # The rest of the home page continues rendering normally.
    pass

_home_perf.checkpoint("referral")

# ── ADDITIONAL TOOLS ──────────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:0.86rem;font-weight:700;color:var(--ua-ink);font-family:Inter,sans-serif;
            margin-bottom:10px;">More tools</div>
""", unsafe_allow_html=True)

_t1, _t2, _t3, _t4, _t5 = st.columns(5)
with _t1:
    if st.button("Signal Dashboard", width="stretch", key="cta_signals"):
        st.switch_page("pages/1_Signal_Dashboard.py")
with _t2:
    if st.button("Market Overview", width="stretch", key="cta_market"):
        st.switch_page("pages/5_Market_Overview.py")
with _t3:
    if st.button("Stock Screener", width="stretch", key="cta_screener"):
        st.switch_page("pages/6_Stock_Screener.py")
with _t4:
    if st.button("Signal Research", width="stretch", key="cta_validation"):
        st.switch_page("pages/51_Signal_Research.py")
with _t5:
    if st.button("Power Supercycle", width="stretch", key="cta_supercycle"):
        st.switch_page("pages/4_Power_Supercycle.py")

st.divider()

# ── FAQ ───────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="font-size:1.0rem;font-weight:800;color:var(--ua-ink);font-family:Inter,sans-serif;
            margin-bottom:10px;letter-spacing:-0.2px;">Common questions</div>
""", unsafe_allow_html=True)

_q1, _q2 = st.columns(2)

with _q1:
    with st.expander("What is alternative data?"):
        st.markdown(
            "Data that isn't a stock price or earnings report. Freight volumes, uranium contracts, "
            "jobless claims, credit spreads, insider buys. Hedge funds have used this for decades. "
            "Most of it comes from free government sources that nobody packaged for retail — until now."
        )
    with st.expander("What is the Confluence Score?"):
        st.markdown(
            "A 0–100 score measuring how many independent signals agree for a given stock right now. "
            "**>65** = multiple bullish signals aligning. **<35** = multiple bearish. **35–65** = mixed. "
            "One bullish signal is noise. Seven agreeing is a thesis. "
            "We walk-forward tested this — results are in the Signal Research Center."
        )
    with st.expander("Does this predict stock prices?"):
        st.markdown(
            "No — and we're transparent about that. The signals have shown statistical correlations "
            "in backtests, but no tool predicts with certainty. The value is pattern recognition "
            "across 40 economic indicators that historically lead price by weeks, not perfect prediction. "
            "See Signal Research for honest results."
        )

with _q2:
    with st.expander("What does it cost?"):
        st.markdown(
            "**Free** to browse signals, Today's Brief, Portfolio Checkup, Sector Map, Signal Dashboard, and Deep Dive — "
            "no account needed. A free account (email only, no card) unlocks the Watchlist and in-app alerts. "
            "**Pro** ($20/mo, 7-day free trial) adds: morning email digest at 7 AM ET, watchlist alerts evaluated every two hours, "
            "Discord/Slack webhook delivery, daily signal-flip tweets via @UnstructuredAlpha, "
            "saved-screen monitoring, Portfolio Intelligence with an evidence-constrained executive review, "
            "Portfolio Fit Lab for candidate-impact simulation, a daily Decision Queue across holdings, "
            "catalysts, and theses, a Catalyst Command Center with verified event dates, portfolio-weighted "
            "exposure, private review plans, proactive morning catalyst prompts, investor-friendly alert presets, "
            "read-only score API access, "
            "Signal Backtester, Factor Exposure, and all future Pro features. "
            "No long-term commitment."
        )
    with st.expander("Is this financial advice?"):
        st.markdown(
            "No. This is a research and education tool. All signals reflect interpretations of public "
            "economic data. Past signal correlation doesn't guarantee future accuracy. "
            "Always do your own due diligence."
        )
    with st.expander("How is this different from Yahoo Finance?"):
        st.markdown(
            "Yahoo Finance shows what has happened to a stock (price, volume, P/E). "
            "Unstructured Alpha shows what macro forces are building beneath the surface — "
            "credit spreads, freight flows, insider positioning — that historically lead "
            "price by 4–16 weeks. Different tool, different question."
        )

# ── SIGNAL LEAD TIMES — redesign analytics (real config data, new chart engine)
# A genuine, axed chart on the landing page: the distribution of researched lead
# times across all signals. Uses utils.ua_charts (dependency-free SVG, theme-var
# colored). Wrapped so a chart error can never break the conversion page.
try:
    from collections import Counter as _Counter
    from utils import ua_charts as _uac

    _lags = _Counter(int(v.get("lag_weeks", 0)) for v in SIGNALS.values()
                     if isinstance(v, dict) and v.get("lag_weeks") is not None)
    if _lags:
        _keys = sorted(_lags)
        _cats = [f"{k}w" for k in _keys]
        _vals = [_lags[k] for k in _keys]
        _svg = _uac.bar_v(_cats, _vals, y_title="# of signals",
                          x_title="Lead time (weeks ahead of price)")
        st.markdown(
            '<div style="max-width:840px;margin:40px auto 4px;">'
            '<div style="font-family:var(--ua-display);font-size:1.55rem;font-weight:600;'
            'color:var(--ua-text,#ECEEF9);letter-spacing:-.4px;line-height:1.1;">'
            f'{len(SIGNALS)} windows into the same market.</div>'
            '<div style="color:var(--ua-muted,#9AA0BE);font-size:.95rem;margin:8px 0 16px;'
            'max-width:600px;">Every signal carries a researched lead time — how far ahead '
            'it has historically led price. The edge lives in the lag.</div>'
            '<div style="background:var(--ua-bg-card,var(--ua-bg-card));'
            'border:1px solid var(--ua-border,rgba(var(--ua-onbg-rgb),.07));'
            f'border-radius:16px;padding:20px 22px;">{_svg}</div>'
            '</div>',
            unsafe_allow_html=True,
        )
except Exception:
    pass


# ── FOOTER ───────────────────────────────────────────────────────────────────
render_footer()
st.session_state["_ua_home_perf_last"] = _home_perf.finish("tools_faq_chart_and_footer")
