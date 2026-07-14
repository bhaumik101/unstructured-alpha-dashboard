# utils/score_explainer.py
# Unstructured Alpha — Confluence Score Transparency Layer
#
# WHY THIS MODULE EXISTS: the Confluence Score is the product's core
# differentiator, but before this module the number arrived on Ticker Deep
# Dive with almost no explanation of WHY it was 72 rather than 55, what moved
# it, how much to trust it, or what it deliberately does NOT claim. A score a
# user cannot interrogate is a score a user cannot build a workflow around.
#
# This module turns the raw output of utils.ticker_score.compute_full_ticker_score
# into a structured, honest explanation:
#
#   • a plain-English band label for the number
#   • how much it changed vs. N days ago (from real stored snapshots only)
#   • WHY it moved — per-signal attribution of the macro-backdrop change,
#     estimated as (signal's own score move) x (this ticker's weight on it)
#   • which signals currently AGREE, among the ones that actually drive it
#   • a CONFIDENCE read grounded in statistical significance + data depth
#   • which macro FACTOR categories the score is coming from
#   • the KNOWN LIMITATIONS, stated plainly, never hidden
#
# DESIGN PRINCIPLE — NO FAKE PRECISION. Every number here is either directly
# measured (a stored snapshot delta, a correlation coefficient, a count) or
# an explicitly-labelled ESTIMATE (attribution holds weights fixed while
# correlations actually drift). The module never manufactures a trend from
# sparse data and never implies the model is more certain than the underlying
# statistics support. This mirrors the deliberate honesty already baked into
# utils.analysis.compute_confluence (which documents that agreement != proven
# predictive accuracy).
#
# The pure functions below take plain dicts/lists and have NO Streamlit
# dependency, so they are unit-testable in isolation. render_explainer_html()
# is the only presentation concern and simply assembles their output into an
# HTML block the page can st.markdown().

from __future__ import annotations

from typing import Optional

from utils.config import SIGNALS, CATEGORIES  # noqa: F401 (CATEGORIES kept for compat)
from utils import taxonomy

# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────

def signal_name(sig_id: str) -> str:
    """Human-readable name for a signal id, falling back to a tidy id."""
    cfg = SIGNALS.get(sig_id) or {}
    return cfg.get("name") or sig_id.replace("_", " ").title()


def signal_category(sig_id: str) -> str:
    # Real macro-factor FAMILY (Rates / Credit / Liquidity / …), not the sector
    # `category` tag — so "where the score comes from" is a factor breakdown.
    return taxonomy.factor_family_of(sig_id)


def category_name(cat_id: str) -> str:
    return taxonomy.factor_family_name(cat_id)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Band label — turns the raw 0-100 number into plain English + tone
# ─────────────────────────────────────────────────────────────────────────────

# Tone colours are semantic, not decorative: supportive greens, challenging
# reds, neutral slate. Bands are intentionally coarse (5 buckets) so the label
# never implies the score is precise to the point.
_BANDS = [
    (65, "Supportive Macro Backdrop",       "#00C853", "supportive"),
    (55, "Mildly Supportive Backdrop",      "#8BC34A", "mildly supportive"),
    (45, "Mixed / Neutral Backdrop",        "#8892AA", "mixed"),
    (35, "Mildly Challenging Backdrop",     "#FF9800", "mildly challenging"),
    (0,  "Challenging Macro Backdrop",      "#FF4444", "challenging"),
]


def score_band(score: float) -> dict:
    """Return {label, color, tone} for a 0-100 confluence score."""
    s = float(score)
    for threshold, label, color, tone in _BANDS:
        if s >= threshold:
            return {"label": label, "color": color, "tone": tone}
    return {"label": "Challenging Macro Backdrop", "color": "#FF4444", "tone": "challenging"}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Change summary — how much the score moved vs. `days` ago
# ─────────────────────────────────────────────────────────────────────────────

def change_summary(score_history: list[dict], days: int = 7) -> dict:
    """
    Summarise the score change over roughly `days`, using ONLY real stored
    snapshots (see utils.score_history — history is organic/traffic-driven and
    legitimately sparse). Never interpolates or invents a trend.

    score_history: list of {snapshot_date, score, ...}, oldest-first
                   (exactly what get_score_history returns).

    Returns:
        {
          "available": bool,      # False when <2 usable snapshots
          "delta": float,         # to_score - from_score (0 if unavailable)
          "from_score": float|None,
          "to_score": float|None,
          "span_days": int|None,  # actual calendar span used
          "direction": "up"|"down"|"flat"|None,
          "sparse": bool,         # True when we had to reach beyond `days`
          "note": str,            # honest one-liner about the basis
        }
    """
    from datetime import date

    pts = [
        (h.get("snapshot_date"), float(h["score"]))
        for h in (score_history or [])
        if h.get("score") is not None and h.get("snapshot_date")
    ]
    if len(pts) < 2:
        return {
            "available": False, "delta": 0.0, "from_score": None, "to_score": None,
            "span_days": None, "direction": None, "sparse": False,
            "note": "First reading on record — no prior snapshot to compare against yet.",
        }

    to_date_s, to_score = pts[-1]
    try:
        to_date = date.fromisoformat(to_date_s)
    except Exception:
        to_date = None

    # Find the snapshot closest to `days` ago without going past the earliest.
    target = None
    if to_date is not None:
        best = None
        for ds, sc in pts[:-1]:
            try:
                d = date.fromisoformat(ds)
            except Exception:
                continue
            age = (to_date - d).days
            if age <= 0:
                continue
            # prefer the snapshot whose age is closest to `days`
            score_key = abs(age - days)
            if best is None or score_key < best[0]:
                best = (score_key, age, ds, sc)
        if best is not None:
            target = (best[2], best[3], best[1])  # (date, score, age_days)

    if target is None:
        # Fall back to the immediately-prior snapshot.
        from_date_s, from_score = pts[-2]
        span = None
        if to_date is not None:
            try:
                span = (to_date - date.fromisoformat(from_date_s)).days
            except Exception:
                span = None
    else:
        from_date_s, from_score, span = target

    delta = round(to_score - from_score, 1)
    direction = "up" if delta > 1.0 else ("down" if delta < -1.0 else "flat")
    sparse = span is not None and span > days + 3

    if span is None:
        note = f"vs. the previous recorded reading"
    elif sparse:
        note = f"vs. {span} days ago (nearest snapshot to a {days}-day comparison)"
    else:
        note = f"over the last {span} day{'s' if span != 1 else ''}"

    return {
        "available": True, "delta": delta,
        "from_score": round(from_score, 1), "to_score": round(to_score, 1),
        "span_days": span, "direction": direction, "sparse": sparse, "note": note,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Attribution — WHY it moved (estimated per-signal contribution to the change)
# ─────────────────────────────────────────────────────────────────────────────

def attribute_change(
    corr_info: dict,
    signal_trends: dict,
    top_n: int = 4,
    min_points: float = 0.3,
) -> dict:
    """
    Estimate how much each signal moved the MACRO-CONFLUENCE portion of the
    score over the trend window.

    The confluence is a weighted average: overall = Σ(w_i·s_i) / Σ(w_i).
    Holding weights fixed, Δoverall ≈ Σ(w_i·Δs_i) / Σ(w_i). So each signal's
    contribution to the change is  w_i·Δs_i / Σ(w_i).

    This is an ESTIMATE and is labelled as such wherever shown: weights
    themselves drift as correlations change, and price momentum / insider /
    short-interest / 13F blend legs move the final blended score too. It
    explains the macro backdrop shift, not the entire blended number.

    corr_info:      {sig_id: {"weight": float, ...}}  (from compute_full_ticker_score)
    signal_trends:  {sig_id: {"delta": float, "trend": str}}  (get_signal_trends)

    Returns:
        {
          "available": bool,
          "movers": [ {sig_id, name, category, signal_delta, contribution}, ... ],
          "covered": int,     # signals that had a usable trend delta
          "tested": int,      # signals in corr_info
        }
    """
    weights = {sid: float(ci.get("weight", 0.0)) for sid, ci in (corr_info or {}).items()}
    w_total = sum(w for w in weights.values() if w > 0)
    if w_total <= 0 or not signal_trends:
        return {"available": False, "movers": [], "covered": 0, "tested": len(weights)}

    contribs = []
    covered = 0
    for sid, w in weights.items():
        tr = signal_trends.get(sid)
        if not tr or tr.get("trend") == "new":
            continue
        d = float(tr.get("delta", 0.0) or 0.0)
        covered += 1
        contribution = (w * d) / w_total
        if abs(contribution) >= min_points:
            contribs.append({
                "sig_id": sid,
                "name": signal_name(sid),
                "category": signal_category(sid),
                "signal_delta": round(d, 1),
                "contribution": round(contribution, 1),
            })

    contribs.sort(key=lambda c: abs(c["contribution"]), reverse=True)
    return {
        "available": len(contribs) > 0,
        "movers": contribs[:top_n],
        "covered": covered,
        "tested": len(weights),
    }


def level_drivers(
    corr_info: dict,
    signal_scores: dict,
    top_n: int = 4,
    min_points: float = 0.5,
) -> dict:
    """
    Fallback / complementary view: WHY the score sits where it is right now,
    decomposing the current LEVEL rather than a change. Contribution of each
    signal to the deviation from neutral (50):  w_i·(s_i-50) / Σ(w_i).

    Used when there isn't enough snapshot history to attribute a change, and
    also useful on its own as "what's holding this score up / down today."
    """
    weights = {sid: float(ci.get("weight", 0.0)) for sid, ci in (corr_info or {}).items()}
    w_total = sum(w for w in weights.values() if w > 0)
    if w_total <= 0:
        return {"available": False, "drivers": []}

    drivers = []
    for sid, w in weights.items():
        sd = (signal_scores or {}).get(sid) or {}
        sc = float(sd.get("score", 50) or 50)
        contribution = (w * (sc - 50.0)) / w_total
        if abs(contribution) >= min_points:
            drivers.append({
                "sig_id": sid,
                "name": signal_name(sid),
                "category": signal_category(sid),
                "score": round(sc, 1),
                "contribution": round(contribution, 1),
            })
    drivers.sort(key=lambda c: abs(c["contribution"]), reverse=True)
    return {"available": len(drivers) > 0, "drivers": drivers[:top_n]}


# ─────────────────────────────────────────────────────────────────────────────
# 4. Agreement — among the signals that actually drive the score
# ─────────────────────────────────────────────────────────────────────────────

def agreement(signal_scores: dict, corr_info: dict) -> dict:
    """
    How many of the statistically-RELEVANT signals point the same direction.

    "Relevant" = signals whose correlation with THIS ticker is significant
    (corr_info significant=True). Restricting to significant signals is the
    honest denominator: a signal with no real relationship to the ticker
    shouldn't count toward "the signals agree." Direction per signal is read
    from its score band (>52.5 supportive, <47.5 challenging, else neutral).

    Returns:
        {
          "relevant": int,   # significant, directional signals
          "agree": int,      # how many point the majority direction
          "direction": "supportive"|"challenging"|"mixed"|None,
          "supportive": int,
          "challenging": int,
        }
    """
    sig_ids = [sid for sid, ci in (corr_info or {}).items() if ci.get("significant")]
    supportive = challenging = 0
    for sid in sig_ids:
        sd = (signal_scores or {}).get(sid) or {}
        sc = float(sd.get("score", 50) or 50)
        if sc > 52.5:
            supportive += 1
        elif sc < 47.5:
            challenging += 1
    relevant = supportive + challenging
    if relevant == 0:
        return {"relevant": 0, "agree": 0, "direction": None,
                "supportive": 0, "challenging": 0}
    if supportive > challenging:
        direction, agree = "supportive", supportive
    elif challenging > supportive:
        direction, agree = "challenging", challenging
    else:
        direction, agree = "mixed", supportive
    return {"relevant": relevant, "agree": agree, "direction": direction,
            "supportive": supportive, "challenging": challenging}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Confidence — grounded in significance + data depth, not vibes
# ─────────────────────────────────────────────────────────────────────────────

def confidence(corr_info: dict, score_history: Optional[list] = None) -> dict:
    """
    A data-quality read, NOT a claim about predictive accuracy.

    Inputs that raise confidence:
      • more signals with a statistically-significant correlation to the ticker
      • more of those signals having a real sample (n >= 20 observations)
      • some stored score history to contextualise the current reading

    Returns {level, color, reasons[]} where level ∈ {High, Moderate, Limited}.
    """
    ci = corr_info or {}
    tested = len(ci)
    n_sig = sum(1 for c in ci.values() if c.get("significant"))
    n_sample = sum(1 for c in ci.values() if int(c.get("n", 0) or 0) >= 20)
    hist_pts = len([h for h in (score_history or []) if h.get("score") is not None])

    reasons = []
    if n_sig >= 6 and n_sample >= 6:
        level, color = "High", "#00C853"
    elif n_sig >= 3:
        level, color = "Moderate", "#FF9800"
    else:
        level, color = "Limited", "#FF4444"

    reasons.append(
        f"{n_sig} of {tested} tested signals show a statistically significant "
        f"correlation with this ticker"
    )
    if n_sample < 6:
        reasons.append(
            f"only {n_sample} signal{'s' if n_sample != 1 else ''} had a full sample "
            f"(20+ observations) — the rest are down-weighted"
        )
    if hist_pts < 3:
        reasons.append("limited stored score history to compare against")

    return {"level": level, "color": color, "reasons": reasons,
            "n_significant": n_sig, "n_tested": tested, "n_sample": n_sample}


# ─────────────────────────────────────────────────────────────────────────────
# 6. Factor breakdown — which macro categories the score comes from
# ─────────────────────────────────────────────────────────────────────────────

def factor_breakdown(corr_info: dict, signal_scores: dict, top_n: int = 4) -> list[dict]:
    """
    Aggregate absolute signal contribution to the LEVEL by macro category, so
    the user can see "this score is mostly a Credit + Liquidity read" rather
    than a black box. Share is % of total absolute contribution.
    """
    weights = {sid: float(ci.get("weight", 0.0)) for sid, ci in (corr_info or {}).items()}
    w_total = sum(w for w in weights.values() if w > 0)
    if w_total <= 0:
        return []
    from collections import defaultdict
    by_cat: dict[str, float] = defaultdict(float)
    for sid, w in weights.items():
        sd = (signal_scores or {}).get(sid) or {}
        sc = float(sd.get("score", 50) or 50)
        by_cat[signal_category(sid)] += abs(w * (sc - 50.0)) / w_total
    total_abs = sum(by_cat.values())
    if total_abs <= 0:
        return []
    rows = [
        {"category": cat, "name": category_name(cat),
         "share": round(100.0 * val / total_abs, 0)}
        for cat, val in by_cat.items()
    ]
    rows.sort(key=lambda r: r["share"], reverse=True)
    return rows[:top_n]


# ─────────────────────────────────────────────────────────────────────────────
# 7. Known limitations — always stated, never buried
# ─────────────────────────────────────────────────────────────────────────────

def known_limitations(
    change: dict,
    attribution: dict,
    conf: dict,
) -> list[str]:
    """Return the honest caveats that apply to THIS score, most-important first."""
    out = [
        # The core, always-true caveat — lifted straight from the honesty already
        # documented in compute_confluence().
        "Signal agreement reflects whether signals point the same way today — "
        "not validated predictive accuracy. Backtests found no significant "
        "relationship between this score and forward returns.",
    ]
    if conf and conf.get("level") == "Limited":
        out.append(
            "Confidence is Limited: few signals show a significant, well-sampled "
            "correlation with this ticker, so read the number as directional context."
        )
    if attribution and attribution.get("available"):
        out.append(
            "The “why it moved” figures are estimates: they hold correlation "
            "weights fixed while weights actually drift, and they explain the "
            "macro backdrop shift, not the full blended score."
        )
    if change and not change.get("available"):
        out.append(
            "No prior snapshot exists for this ticker yet — history accrues only "
            "for tickers people actually open, so the change view fills in over time."
        )
    elif change and change.get("sparse"):
        out.append(
            "Score history is sparse for this ticker, so the change is measured "
            "against the nearest available snapshot rather than an exact window."
        )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 8. Assemble everything into one payload
# ─────────────────────────────────────────────────────────────────────────────

def build_explainer(
    result: dict,
    score_history: Optional[list] = None,
    signal_trends: Optional[dict] = None,
    change_days: int = 7,
) -> dict:
    """
    Turn a compute_full_ticker_score() result (plus optional history/trends)
    into a fully-structured, serialisable explanation payload.

    result must contain: confluence{overall_score,...}, corr_info, signal_scores.
    score_history: get_score_history(ticker) output (may be empty).
    signal_trends: get_signal_trends(days_back=change_days) output (may be empty).
    """
    confl = result.get("confluence", {}) or {}
    score = float(confl.get("overall_score", 50.0))
    corr_info = result.get("corr_info", {}) or {}
    signal_scores = result.get("signal_scores", {}) or {}

    band = score_band(score)
    change = change_summary(score_history or [], days=change_days)
    attribution = attribute_change(corr_info, signal_trends or {})
    drivers = level_drivers(corr_info, signal_scores)
    agree = agreement(signal_scores, corr_info)
    conf = confidence(corr_info, score_history)
    factors = factor_breakdown(corr_info, signal_scores)
    limits = known_limitations(change, attribution, conf)

    return {
        "ticker": result.get("ticker"),
        "score": round(score, 1),
        "band": band,
        "change": change,
        "attribution": attribution,
        "drivers": drivers,
        "agreement": agree,
        "confidence": conf,
        "factors": factors,
        "limitations": limits,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. Presentation — the only Streamlit-facing concern
# ─────────────────────────────────────────────────────────────────────────────

def _arrow(direction: Optional[str]) -> str:
    return {"up": "▲", "down": "▼", "flat": "→"}.get(direction or "", "")


def _pt(x: float) -> str:
    """Signed points string, e.g. +5, -1, +8."""
    x = round(float(x), 1)
    xi = int(x) if float(x).is_integer() else x
    return f"+{xi}" if x >= 0 else f"{xi}"


def render_explainer_html(payload: dict) -> str:
    """
    Render the explainer payload as a single self-contained HTML block for
    st.markdown(..., unsafe_allow_html=True). Deliberately restrained styling:
    semantic colour, clear hierarchy, no glow/gradient decoration — the design
    should feel intelligent because the information is legible.
    """
    band = payload["band"]
    score = payload["score"]
    change = payload["change"]
    attribution = payload["attribution"]
    drivers = payload["drivers"]
    agree = payload["agreement"]
    conf = payload["confidence"]
    factors = payload["factors"]
    limits = payload["limitations"]

    accent = band["color"]

    # --- Header: score + band + change -------------------------------------
    if change["available"]:
        chg_color = "#00C853" if change["direction"] == "up" else (
            "#FF4444" if change["direction"] == "down" else "#8892AA")
        chg_html = (
            f'<span style="color:{chg_color};font-weight:600;">'
            f'{_arrow(change["direction"])} {_pt(change["delta"])} points</span>'
            f'<span style="color:#6B7280;"> {change["note"]}</span>'
        )
    else:
        chg_html = f'<span style="color:#6B7280;">{change["note"]}</span>'

    header = (
        f'<div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;">'
        f'<span style="font-size:2.4rem;font-weight:800;color:{accent};line-height:1;">{score:g}</span>'
        f'<span style="font-size:1.05rem;font-weight:700;color:#E8EEFF;">{band["label"]}</span>'
        f'</div>'
        f'<div style="font-size:0.82rem;margin-top:6px;">{chg_html}</div>'
    )

    # --- Why it moved (attribution) or why it's here (level drivers) --------
    if attribution["available"]:
        rows = "".join(
            f'<div style="display:flex;justify-content:space-between;gap:12px;'
            f'padding:3px 0;font-size:0.82rem;">'
            f'<span style="color:#C3CBE0;">{m["name"]}</span>'
            f'<span style="color:{"#00C853" if m["contribution"] >= 0 else "#FF4444"};'
            f'font-variant-numeric:tabular-nums;font-weight:600;">{_pt(m["contribution"])}</span>'
            f'</div>'
            for m in attribution["movers"]
        )
        why_title = "Why it moved"
        why_sub = "estimated contribution to the macro-backdrop change"
    else:
        rows = "".join(
            f'<div style="display:flex;justify-content:space-between;gap:12px;'
            f'padding:3px 0;font-size:0.82rem;">'
            f'<span style="color:#C3CBE0;">{d["name"]}</span>'
            f'<span style="color:{"#00C853" if d["contribution"] >= 0 else "#FF4444"};'
            f'font-variant-numeric:tabular-nums;font-weight:600;">{_pt(d["contribution"])}</span>'
            f'</div>'
            for d in drivers["drivers"]
        ) or '<div style="color:#6B7280;font-size:0.82rem;">Not enough signal data to break down yet.</div>'
        why_title = "Why it's here"
        why_sub = "biggest contributors to the current level (vs. neutral 50)"

    why = (
        f'<div style="margin-top:16px;">'
        f'<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;'
        f'color:#8892AA;font-weight:700;">{why_title}</div>'
        f'<div style="font-size:0.68rem;color:#6B7280;margin-bottom:6px;">{why_sub}</div>'
        f'{rows}</div>'
    )

    # --- Agreement + confidence chips --------------------------------------
    if agree["relevant"] > 0:
        agree_txt = (
            f'{agree["agree"]} of {agree["relevant"]} relevant signals point '
            f'{agree["direction"]}'
        )
    else:
        agree_txt = "No signals with a significant correlation yet"

    chips = (
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;">'
        f'<div style="background:#161A2B;border:1px solid #262C42;border-radius:8px;'
        f'padding:8px 12px;">'
        f'<div style="font-size:0.64rem;text-transform:uppercase;letter-spacing:0.05em;color:#8892AA;font-weight:700;">Signal agreement</div>'
        f'<div style="font-size:0.86rem;color:#E8EEFF;font-weight:600;margin-top:2px;">{agree_txt}</div>'
        f'</div>'
        f'<div style="background:#161A2B;border:1px solid #262C42;border-radius:8px;'
        f'padding:8px 12px;">'
        f'<div style="font-size:0.64rem;text-transform:uppercase;letter-spacing:0.05em;color:#8892AA;font-weight:700;">Confidence</div>'
        f'<div style="font-size:0.86rem;color:{conf["color"]};font-weight:700;margin-top:2px;">{conf["level"]}</div>'
        f'</div>'
        f'</div>'
    )

    # --- Factor mix ---------------------------------------------------------
    if factors:
        fac_rows = " · ".join(
            f'<span style="color:#C3CBE0;">{f["name"]}</span>'
            f'<span style="color:#6B7280;"> {f["share"]:g}%</span>'
            for f in factors
        )
        factor_html = (
            f'<div style="margin-top:16px;">'
            f'<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;'
            f'color:#8892AA;font-weight:700;margin-bottom:4px;">Where the score comes from</div>'
            f'<div style="font-size:0.82rem;">{fac_rows}</div>'
            f'</div>'
        )
    else:
        factor_html = ""

    # --- Confidence reasons + limitations (progressive disclosure) ----------
    conf_reasons = "".join(f"<li>{r}</li>" for r in conf["reasons"])
    limit_items = "".join(f"<li>{l}</li>" for l in limits)
    details = (
        f'<details style="margin-top:16px;">'
        f'<summary style="cursor:pointer;font-size:0.74rem;color:#8892AA;font-weight:600;">'
        f'How this score is built &amp; what it can\'t tell you</summary>'
        f'<div style="font-size:0.76rem;color:#8892AA;margin-top:8px;line-height:1.6;">'
        f'<div style="color:#C3CBE0;font-weight:600;margin-bottom:2px;">Confidence basis</div>'
        f'<ul style="margin:0 0 10px 18px;padding:0;">{conf_reasons}</ul>'
        f'<div style="color:#C3CBE0;font-weight:600;margin-bottom:2px;">Known limitations</div>'
        f'<ul style="margin:0 0 0 18px;padding:0;">{limit_items}</ul>'
        f'</div></details>'
    )

    return (
        f'<div style="background:#0F1320;border:1px solid #232942;border-left:3px solid {accent};'
        f'border-radius:12px;padding:18px 20px;font-family:Inter,-apple-system,sans-serif;">'
        f'{header}{why}{chips}{factor_html}{details}'
        f'</div>'
    )
