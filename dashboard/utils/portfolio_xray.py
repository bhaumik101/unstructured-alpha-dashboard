# utils/portfolio_xray.py
# Unstructured Alpha — Portfolio Macro X-Ray (Point 2)
#
# WHY THIS MODULE EXISTS: every score before this was per-ticker. But an
# investor doesn't hold one stock — they hold a book, and the question that
# actually keeps them up at night is a PORTFOLIO question: "is my whole
# portfolio secretly leaning the same way? which holding is most exposed right
# now? are two names I think are diversified actually the same macro bet?"
# The per-ticker Confluence Score can't answer that. This module aggregates
# the per-ticker macro reads into a portfolio-level exposure map.
#
# It answers, as CONTEXT (never as advice — no buy/sell, no sizing calls):
#   • Portfolio Macro Score (the book's aggregate macro backdrop)
#   • Which macro FACTORS the portfolio is concentrated in
#   • Primary tailwinds (factors currently supportive across holdings)
#   • Primary risks (factors that are both concentrated AND a headwind)
#   • The most macro-vulnerable and most macro-supported holding
#   • Hidden correlations — holdings in different sectors that nonetheless
#     share the same macro factor exposure (diversification that isn't real)
#   • Which holdings ride the same factor (shared-exposure groups)
#
# A "factor" here is a signal CATEGORY from utils.config (Macro & Liquidity,
# Financials & Credit, Energy & Oil, …) — the platform's own, already-used
# taxonomy, not an invented one. Exposure is measured only over the signals
# that are STATISTICALLY SIGNIFICANT for each holding (same honesty rule as the
# score itself), so a signal with no real relationship to a stock never inflates
# that stock's factor exposure.
#
# Pure functions, no Streamlit / no DB, so the aggregation math is unit-testable
# against ground truth. render_portfolio_xray_html() is the only presentation
# concern.

from __future__ import annotations

import math
from typing import Optional

from utils.config import SIGNALS, CATEGORIES  # noqa: F401 (kept for compatibility)
from utils import taxonomy

# A holding is meaningfully "exposed" to a factor when that factor drives at
# least this share of its (significant) macro read.
EXPOSURE_THRESHOLD = 0.12
# Direction bands on the 0-100 signal scale: >53 supportive, <47 challenging.
SUPPORT_BAND = 53.0
CHALLENGE_BAND = 47.0
# Two holdings are a "hidden correlation" when their factor-exposure vectors
# are this similar (cosine) despite sitting in different sectors.
SIMILARITY_THRESHOLD = 0.80


# ─────────────────────────────────────────────────────────────────────────────
# Config lookups
# ─────────────────────────────────────────────────────────────────────────────

def _factor_of(sig_id: str) -> str:
    # Real macro-factor family (Rates / Credit / Liquidity / …), NOT the sector
    # `category` tag. This is what makes "your largest shared exposure is real
    # rates" a true statement rather than a sector grouping.
    return taxonomy.factor_family_of(sig_id)


def factor_name(factor_id: str) -> str:
    return taxonomy.factor_family_name(factor_id)


# ─────────────────────────────────────────────────────────────────────────────
# Per-holding factor profile
# ─────────────────────────────────────────────────────────────────────────────

def holding_factor_profile(corr_info: dict, signal_scores: dict) -> dict:
    """
    Decompose ONE holding's macro read into factor exposure + direction.

    corr_info:     {sig_id: {"weight": float, "significant": bool, ...}}
    signal_scores: {sig_id: {"score": float, "status": str}}

    Only significant signals count. Returns:
        {
          factor_id: {
            "exposure":  float,   # 0..1, share of the holding's significant weight
            "direction": float|None,  # weight-avg signal score in this factor (0-100)
            "n":         int,     # number of significant signals in this factor
          }, ...
        }
    Exposure across factors sums to ~1 (0 if the holding has no significant signals).
    """
    from collections import defaultdict
    w_by_factor: dict[str, float] = defaultdict(float)
    ws_by_factor: dict[str, float] = defaultdict(float)   # weight*score accumulator
    n_by_factor: dict[str, int] = defaultdict(int)
    w_total = 0.0

    for sid, ci in (corr_info or {}).items():
        if not ci.get("significant"):
            continue
        w = float(ci.get("weight", 0.0) or 0.0)
        if w <= 0:
            continue
        f = _factor_of(sid)
        sc = float((signal_scores.get(sid) or {}).get("score", 50) or 50)
        w_by_factor[f] += w
        ws_by_factor[f] += w * sc
        n_by_factor[f] += 1
        w_total += w

    profile: dict[str, dict] = {}
    if w_total <= 0:
        return profile
    for f, w in w_by_factor.items():
        profile[f] = {
            "exposure": round(w / w_total, 4),
            "direction": round(ws_by_factor[f] / w, 1) if w > 0 else None,
            "n": n_by_factor[f],
        }
    return profile


def _cosine(a: dict, b: dict) -> float:
    """Cosine similarity of two {factor: exposure} vectors."""
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio aggregation
# ─────────────────────────────────────────────────────────────────────────────

def build_portfolio_xray(holdings: list, prior_portfolio_score: Optional[float] = None) -> dict:
    """
    Aggregate per-holding macro reads into the Portfolio Macro X-Ray payload.

    holdings: list of dicts, one per position:
        {
          "ticker": str,
          "score": float,                 # the holding's Confluence Score 0-100
          "corr_info": {sig: {weight, significant, ...}},
          "signal_scores": {sig: {score, status}},
          "sector": str (optional),       # used for hidden-correlation detection
        }
    prior_portfolio_score: optional earlier portfolio score, for the over-time delta.

    Frames everything as exposure / concentration / context — never advice.
    """
    holdings = [h for h in (holdings or []) if h.get("ticker")]
    n = len(holdings)
    if n == 0:
        return {"n_holdings": 0, "portfolio_score": None, "empty": True}

    # Per-holding profiles + score.
    profiles: dict[str, dict] = {}
    scores: dict[str, float] = {}
    sectors: dict[str, str] = {}
    for h in holdings:
        t = h["ticker"].upper().strip()
        profiles[t] = holding_factor_profile(h.get("corr_info", {}), h.get("signal_scores", {}))
        scores[t] = float(h.get("score", 50) or 50)
        sectors[t] = h.get("sector") or ""

    portfolio_score = round(sum(scores.values()) / n, 1)

    # ── Factor-level aggregation ────────────────────────────────────────────
    all_factors = set()
    for p in profiles.values():
        all_factors |= set(p.keys())

    factor_rows = []
    for f in all_factors:
        exposures = [profiles[t].get(f, {}).get("exposure", 0.0) for t in profiles]
        exposed_tickers = [t for t in profiles if profiles[t].get(f, {}).get("exposure", 0.0) >= EXPOSURE_THRESHOLD]
        # direction averaged over the holdings actually exposed to this factor
        dirs = [profiles[t][f]["direction"] for t in exposed_tickers
                if profiles[t].get(f, {}).get("direction") is not None]
        avg_dir = round(sum(dirs) / len(dirs), 1) if dirs else None
        pct_exposed = round(100.0 * len(exposed_tickers) / n)
        avg_exposure = round(sum(exposures) / n, 3)

        if avg_dir is not None and avg_dir >= SUPPORT_BAND:
            kind = "tailwind"
        elif avg_dir is not None and avg_dir <= CHALLENGE_BAND:
            kind = "risk"
        else:
            kind = "neutral"

        factor_rows.append({
            "factor": f,
            "name": factor_name(f),
            "pct_holdings": pct_exposed,
            "n_exposed": len(exposed_tickers),
            "avg_exposure": avg_exposure,
            "avg_direction": avg_dir,
            "kind": kind,
            "exposed_tickers": sorted(exposed_tickers),
        })

    # Tailwinds: supportive factors, ranked by breadth × strength.
    tailwinds = sorted(
        [r for r in factor_rows if r["kind"] == "tailwind"],
        key=lambda r: (r["pct_holdings"] * ((r["avg_direction"] or 50) - 50)),
        reverse=True,
    )
    # Risks: a factor is a portfolio risk if it's a shared headwind, OR if it's
    # heavily concentrated (a lot of the book leans on the same factor at once).
    risks = sorted(
        [r for r in factor_rows
         if r["kind"] == "risk" or (r["pct_holdings"] >= 60 and r["kind"] != "tailwind")],
        key=lambda r: (r["pct_holdings"], -(r["avg_direction"] or 50)),
        reverse=True,
    )

    # Most concentrated factor (highest share of holdings exposed).
    concentration = sorted(factor_rows, key=lambda r: (r["pct_holdings"], r["avg_exposure"]), reverse=True)
    top_concentration = concentration[0] if concentration else None

    # ── Most vulnerable / most supported holding ────────────────────────────
    most_vulnerable_t = min(scores, key=lambda t: scores[t])
    most_supported_t = max(scores, key=lambda t: scores[t])

    def _dominant_factor(t, prefer_challenging: bool):
        """The factor with the largest exposure for holding t (optionally the
        largest challenging one)."""
        p = profiles.get(t, {})
        if not p:
            return None
        items = list(p.items())
        if prefer_challenging:
            chall = [(f, d) for f, d in items if (d.get("direction") is not None and d["direction"] < 50)]
            if chall:
                f, d = max(chall, key=lambda kv: kv[1]["exposure"])
                return factor_name(f)
        f, d = max(items, key=lambda kv: kv[1]["exposure"])
        return factor_name(f)

    most_vulnerable = {
        "ticker": most_vulnerable_t, "score": scores[most_vulnerable_t],
        "driver": _dominant_factor(most_vulnerable_t, prefer_challenging=True),
    }
    most_supported = {
        "ticker": most_supported_t, "score": scores[most_supported_t],
        "driver": _dominant_factor(most_supported_t, prefer_challenging=False),
    }

    # ── Hidden correlations: similar macro profile, different sector ─────────
    tickers = sorted(profiles.keys())
    hidden = []
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            a, b = tickers[i], tickers[j]
            ea = {f: d["exposure"] for f, d in profiles[a].items()}
            eb = {f: d["exposure"] for f, d in profiles[b].items()}
            sim = _cosine(ea, eb)
            if sim >= SIMILARITY_THRESHOLD and sectors[a] and sectors[b] and sectors[a] != sectors[b]:
                # the factor they most share
                shared = None
                common = set(ea) & set(eb)
                if common:
                    shared = factor_name(max(common, key=lambda f: min(ea[f], eb[f])))
                hidden.append({
                    "pair": [a, b], "similarity": round(sim, 2),
                    "sectors": [sectors[a], sectors[b]], "shared_factor": shared,
                })
    hidden.sort(key=lambda h: h["similarity"], reverse=True)

    # ── Exposure-over-time delta (optional) ─────────────────────────────────
    score_delta = None
    if prior_portfolio_score is not None:
        score_delta = round(portfolio_score - float(prior_portfolio_score), 1)

    return {
        "empty": False,
        "n_holdings": n,
        "portfolio_score": portfolio_score,
        "score_delta": score_delta,
        "band": _portfolio_band(portfolio_score),
        "factors": sorted(factor_rows, key=lambda r: r["pct_holdings"], reverse=True),
        "tailwinds": tailwinds,
        "risks": risks,
        "top_concentration": top_concentration,
        "most_vulnerable": most_vulnerable,
        "most_supported": most_supported,
        "hidden_correlations": hidden,
        "holdings": [{"ticker": t, "score": scores[t], "sector": sectors[t]} for t in tickers],
    }


def _portfolio_band(score: float) -> dict:
    s = float(score)
    if s >= 60:
        return {"label": "Supportive macro backdrop", "color": "#00C853", "tone": "supportive"}
    if s >= 45:
        return {"label": "Mixed macro backdrop", "color": "#8892AA", "tone": "mixed"}
    return {"label": "Challenging macro backdrop", "color": "#FF4444", "tone": "challenging"}


# ─────────────────────────────────────────────────────────────────────────────
# Presentation
# ─────────────────────────────────────────────────────────────────────────────

def _pct(x) -> str:
    return f"{int(round(x))}%"


def render_portfolio_xray_html(payload: dict) -> str:
    """Render the X-Ray payload as a self-contained HTML block for st.html()."""
    if payload.get("empty") or not payload.get("n_holdings"):
        return (
            '<div style="background:#0F1320;border:1px solid #232942;border-radius:12px;'
            'padding:20px;font-family:Inter,sans-serif;color:#8892AA;">'
            'Add a few holdings to see your portfolio\'s macro exposure map.</div>'
        )

    band = payload["band"]
    score = payload["portfolio_score"]
    accent = band["color"]
    n = payload["n_holdings"]

    delta_html = ""
    if payload.get("score_delta") is not None:
        d = payload["score_delta"]
        dc = "#00C853" if d > 0 else ("#FF4444" if d < 0 else "#8892AA")
        arrow = "▲" if d > 0 else ("▼" if d < 0 else "→")
        di = int(d) if float(d).is_integer() else d
        delta_html = (f'<span style="color:{dc};font-weight:600;font-size:0.82rem;margin-left:10px;">'
                      f'{arrow} {"+" if d >= 0 else ""}{di} vs. prior</span>')

    header = (
        f'<div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;">'
        f'<span style="font-size:2.4rem;font-weight:800;color:{accent};line-height:1;">{score:g}</span>'
        f'<span style="font-size:1.05rem;font-weight:700;color:#E8EEFF;">Portfolio Macro Score</span>'
        f'{delta_html}</div>'
        f'<div style="font-size:0.82rem;color:#8892AA;margin-top:4px;">'
        f'{band["label"]} · across {n} holding{"s" if n != 1 else ""} · equal-weighted, context only</div>'
    )

    def _chips(rows, tone_color):
        if not rows:
            return '<div style="color:#6B7280;font-size:0.82rem;">None stand out right now.</div>'
        out = []
        for r in rows[:4]:
            detail = f'{_pct(r["pct_holdings"])} of holdings'
            if r.get("avg_direction") is not None:
                detail += f' · avg {r["avg_direction"]:g}/100'
            out.append(
                f'<div style="padding:8px 0;border-bottom:1px solid #1E2436;">'
                f'<span style="color:{tone_color};font-weight:600;font-size:0.86rem;">{r["name"]}</span>'
                f'<span style="color:#8892AA;font-size:0.78rem;"> — {detail}</span>'
                f'<div style="color:#6B7280;font-size:0.72rem;margin-top:2px;">'
                f'{", ".join(r["exposed_tickers"][:8])}</div></div>'
            )
        return "".join(out)

    tailwinds = (
        '<div style="flex:1;min-width:240px;">'
        '<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;color:#00C853;font-weight:700;margin-bottom:6px;">Primary tailwinds</div>'
        f'{_chips(payload["tailwinds"], "#00C853")}</div>'
    )
    risks = (
        '<div style="flex:1;min-width:240px;">'
        '<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;color:#FF6B6B;font-weight:700;margin-bottom:6px;">Primary risks &amp; concentration</div>'
        f'{_chips(payload["risks"], "#FF6B6B")}</div>'
    )

    # Most vulnerable / supported
    mv, ms = payload["most_vulnerable"], payload["most_supported"]
    exposure_cards = (
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:16px;">'
        f'<div style="flex:1;min-width:200px;background:#161A2B;border:1px solid #262C42;border-radius:8px;padding:10px 12px;">'
        f'<div style="font-size:0.64rem;text-transform:uppercase;letter-spacing:0.05em;color:#8892AA;font-weight:700;">Most macro-vulnerable</div>'
        f'<div style="font-size:0.95rem;color:#FF6B6B;font-weight:700;margin-top:2px;">{mv["ticker"]} · {mv["score"]:g}</div>'
        f'<div style="font-size:0.72rem;color:#6B7280;margin-top:2px;">most exposed to {mv["driver"] or "mixed factors"}</div></div>'
        f'<div style="flex:1;min-width:200px;background:#161A2B;border:1px solid #262C42;border-radius:8px;padding:10px 12px;">'
        f'<div style="font-size:0.64rem;text-transform:uppercase;letter-spacing:0.05em;color:#8892AA;font-weight:700;">Most macro-supported</div>'
        f'<div style="font-size:0.95rem;color:#00C853;font-weight:700;margin-top:2px;">{ms["ticker"]} · {ms["score"]:g}</div>'
        f'<div style="font-size:0.72rem;color:#6B7280;margin-top:2px;">carried by {ms["driver"] or "mixed factors"}</div></div>'
        '</div>'
    )

    # Hidden correlations
    hidden_html = ""
    if payload["hidden_correlations"]:
        rows = "".join(
            f'<div style="font-size:0.8rem;color:#C3CBE0;padding:4px 0;">'
            f'<b>{h["pair"][0]}</b> &amp; <b>{h["pair"][1]}</b> '
            f'<span style="color:#8892AA;">— {h["sectors"][0]} vs {h["sectors"][1]}, '
            f'but {int(h["similarity"]*100)}% shared macro exposure'
            + (f' ({h["shared_factor"]})' if h.get("shared_factor") else '')
            + '</span></div>'
            for h in payload["hidden_correlations"][:4]
        )
        hidden_html = (
            '<div style="margin-top:16px;">'
            '<div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;color:#8892AA;font-weight:700;margin-bottom:4px;">Hidden correlations</div>'
            '<div style="font-size:0.72rem;color:#6B7280;margin-bottom:6px;">Different sectors, same macro bet — diversification that may not be real.</div>'
            f'{rows}</div>'
        )

    return (
        f'<div style="background:#0F1320;border:1px solid #232942;border-left:3px solid {accent};'
        f'border-radius:12px;padding:18px 20px;font-family:Inter,-apple-system,sans-serif;">'
        f'{header}'
        f'<div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:16px;">{tailwinds}{risks}</div>'
        f'{exposure_cards}{hidden_html}'
        f'<div style="font-size:0.7rem;color:#4A5568;margin-top:14px;border-top:1px solid #1E2436;padding-top:8px;">'
        f'Exposure = share of each holding\'s statistically-significant macro signals in a factor. '
        f'Context and concentration only — not advice, not a recommendation to buy, sell, or size any position.</div>'
        f'</div>'
    )
