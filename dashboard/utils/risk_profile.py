"""
utils/risk_profile.py — per-user risk profile + personalized ("Your Score").

WHAT THIS IS
------------
Three dials the user sets once, stored on their account:

  tolerance : conservative | balanced | aggressive
      How much weight price momentum / alt-data get versus slow macro signals.
  horizon   : short | medium | long | all
      Which signals count, by each signal's `lag_weeks` (how far ahead it leads).
  emphasis  : macro | balanced | full
      Whether the differentiator data (insider, 13F, short interest) participates.

DESIGN RULE — the canonical Confluence Score is NEVER changed.
`compute_personal_score()` returns a SEPARATE number ("Your Score") alongside it.
The headline score has to stay comparable across users, snapshots, and alerts;
a score that means something different per viewer would undermine the whole
precision positioning. This is additive context, not a redefinition.

The math reuses the SAME tested `compute_confluence()` the rest of the app uses —
it only changes WHICH signals go in and how the components are blended.
"""
from __future__ import annotations

import json
from typing import Any

# ── Vocabulary ────────────────────────────────────────────────────────────────
TOLERANCES = ("conservative", "balanced", "aggressive")
HORIZONS = ("short", "medium", "long", "all")
EMPHASES = ("macro", "balanced", "full")

DEFAULT_PROFILE: dict[str, str] = {
    "tolerance": "balanced",
    "horizon": "all",
    "emphasis": "balanced",
}

# lag_weeks band per horizon (matches the Stock Recommender's horizon filter)
HORIZON_BANDS: dict[str, tuple[int, int]] = {
    "short":  (0, 3),
    "medium": (3, 9),
    "long":   (9, 999),
    "all":    (0, 999),
}
HORIZON_LABELS: dict[str, str] = {
    "short":  "Short-term (1–2 wks)",
    "medium": "Medium-term (1–2 mo)",
    "long":   "Long-term (3+ mo)",
    "all":    "All horizons",
}
TOLERANCE_LABELS: dict[str, str] = {
    "conservative": "Conservative",
    "balanced":     "Balanced",
    "aggressive":   "Aggressive",
}
EMPHASIS_LABELS: dict[str, str] = {
    "macro":    "Macro only",
    "balanced": "Macro + momentum",
    "full":     "Everything (incl. insider/13F/short interest)",
}

# Share of the score given to the macro composite, by tolerance. The remainder
# goes to momentum (and, per emphasis, to the alt-data composite).
# Conservative leans on slow macro; aggressive gives price action more say.
_MACRO_SHARE: dict[str, float] = {
    "conservative": 0.90,
    "balanced":     0.80,   # matches the canonical 80/20 blend
    "aggressive":   0.65,
}
# Share carved out for the differentiator/alt-data composite, by emphasis.
_ALT_SHARE: dict[str, float] = {
    "macro":    0.00,
    "balanced": 0.10,
    "full":     0.20,
}


# ── Validation ────────────────────────────────────────────────────────────────
def normalize(profile: Any) -> dict[str, str]:
    """Coerce anything into a valid profile dict. Never raises."""
    p = dict(DEFAULT_PROFILE)
    if isinstance(profile, str):
        try:
            profile = json.loads(profile)
        except Exception:
            profile = None
    if isinstance(profile, dict):
        t = str(profile.get("tolerance", "")).lower()
        h = str(profile.get("horizon", "")).lower()
        e = str(profile.get("emphasis", "")).lower()
        if t in TOLERANCES:
            p["tolerance"] = t
        if h in HORIZONS:
            p["horizon"] = h
        if e in EMPHASES:
            p["emphasis"] = e
    return p


def is_default(profile: Any) -> bool:
    return normalize(profile) == DEFAULT_PROFILE


# ── Persistence (users.risk_profile TEXT, JSON-encoded) ───────────────────────
def get_profile(user_id: int | None) -> dict[str, str]:
    """Load a user's saved profile. Falls back to the default. Never raises."""
    if not user_id:
        return dict(DEFAULT_PROFILE)
    try:
        from sqlalchemy import select
        from utils.db import engine, users
        with engine.begin() as conn:
            row = conn.execute(
                select(users.c.risk_profile).where(users.c.id == user_id)
            ).fetchone()
        return normalize(row[0] if row else None)
    except Exception:
        return dict(DEFAULT_PROFILE)


def save_profile(user_id: int | None, profile: Any) -> bool:
    """Persist a profile. Returns True on success. Never raises."""
    if not user_id:
        return False
    try:
        from sqlalchemy import update
        from utils.db import engine, users
        payload = json.dumps(normalize(profile), separators=(",", ":"))
        with engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == user_id)
                         .values(risk_profile=payload))
        return True
    except Exception:
        return False


# ── Personalized score ────────────────────────────────────────────────────────
def _alt_composite(full: dict) -> float | None:
    """Average of whichever differentiator scores are actually available."""
    parts: list[float] = []
    for score_key, flag_key in (
        ("insider_score",         "has_insider_signal"),
        ("short_interest_score",  "has_short_interest_signal"),
        ("thirteenf_score",       "has_13f_signal"),
    ):
        try:
            if full.get(flag_key):
                v = (full.get(score_key) or {}).get("score")
                if v is not None:
                    parts.append(float(v))
        except Exception:
            continue
    if not parts:
        return None
    return sum(parts) / len(parts)


def compute_personal_score(full: dict, profile: Any) -> dict:
    """
    Build "Your Score" for one ticker from an existing compute_full_ticker_score()
    result. Pure post-processing — no refetch, no provider calls.

    Returns a dict with the score, its components, how many signals survived the
    horizon filter, the delta vs the canonical Confluence Score, and a
    plain-English explanation. Never raises; degrades to the canonical score.
    """
    p = normalize(profile)
    canonical = None
    try:
        canonical = float((full.get("confluence") or {}).get("overall_score"))
    except Exception:
        canonical = None

    out: dict = {
        "profile": p,
        "horizon_label": HORIZON_LABELS[p["horizon"]],
        "tolerance_label": TOLERANCE_LABELS[p["tolerance"]],
        "emphasis_label": EMPHASIS_LABELS[p["emphasis"]],
        "canonical": canonical,
        "score": canonical,
        "n_signals": 0,
        "n_total": 0,
        "horizon_applied": False,
        "delta": 0.0,
        "explanation": "",
        "ok": False,
    }

    try:
        from utils.analysis import compute_confluence
        from utils.config import SIGNALS

        sig_scores = full.get("signal_scores") or {}
        usable = {sid: sv for sid, sv in sig_scores.items()
                  if isinstance(sv, dict) and not sv.get("error")}
        out["n_total"] = len(usable)
        if not usable:
            out["explanation"] = "No usable signals for this ticker — showing the standard score."
            return out

        lo, hi = HORIZON_BANDS[p["horizon"]]
        kept = {sid: sv for sid, sv in usable.items()
                if lo <= float(SIGNALS.get(sid, {}).get("lag_weeks", 4) or 4) <= hi}
        if kept:
            out["horizon_applied"] = p["horizon"] != "all"
        else:
            kept = usable  # horizon too narrow — fall back rather than show nothing

        # Weight each signal by its measured correlation when statistically
        # significant, else by its configured priority (same rule the app uses).
        corr = full.get("corr_info") or {}
        weights: dict[str, float] = {}
        for sid in kept:
            ci = corr.get(sid) or {}
            if ci.get("significant") and ci.get("weight"):
                weights[sid] = float(ci["weight"])
            else:
                weights[sid] = float(SIGNALS.get(sid, {}).get("pcs", 5) or 5) / 10.0

        conf = compute_confluence(kept, weights=weights)
        macro = float(conf.get("overall_score", 50.0))
        mom = float(full.get("momentum_score") or 50.0)
        alt = _alt_composite(full) if p["emphasis"] != "macro" else None

        macro_share = _MACRO_SHARE[p["tolerance"]]
        alt_share = _ALT_SHARE[p["emphasis"]] if alt is not None else 0.0
        # Momentum takes whatever macro and alt don't.
        mom_share = max(0.0, 1.0 - macro_share - alt_share)

        score = macro * macro_share + mom * mom_share + (alt or 0.0) * alt_share
        score = round(max(0.0, min(100.0, score)), 1)

        out.update({
            "score": score,
            "macro": round(macro, 1),
            "momentum": round(mom, 1),
            "alt": (round(alt, 1) if alt is not None else None),
            "macro_share": macro_share,
            "mom_share": round(mom_share, 2),
            "alt_share": alt_share,
            "n_signals": len(kept),
            "conviction": conf.get("conviction"),
            "case": conf.get("case"),
            "ok": True,
        })
        if canonical is not None:
            out["delta"] = round(score - canonical, 1)

        bits = [
            f"{len(kept)} of {len(usable)} signals match your {HORIZON_LABELS[p['horizon']].lower()} window"
            if out["horizon_applied"] else f"all {len(kept)} relevant signals included",
            f"macro weighted {int(macro_share*100)}%",
            f"momentum {int(mom_share*100)}%",
        ]
        if alt_share:
            bits.append(f"insider/13F/short interest {int(alt_share*100)}%")
        out["explanation"] = " · ".join(bits) + "."
        return out
    except Exception:
        out["explanation"] = "Could not personalize — showing the standard score."
        return out


def compute_personal_score_from_components(components: Any, profile: Any) -> dict:
    """Personalize a stored component snapshot without fetching live data.

    Component snapshots already contain the measured signal weights, scores,
    momentum, and optional positioning evidence used by the canonical score.
    Rehydrating that shape lets the Today page reuse ``compute_personal_score``
    exactly, while avoiding a network-heavy full ticker recomputation.
    """
    if not isinstance(components, dict):
        return compute_personal_score({}, profile)

    signal_scores: dict[str, dict] = {}
    corr_info: dict[str, dict] = {}
    for signal in components.get("signals") or []:
        if not isinstance(signal, dict) or not signal.get("id"):
            continue
        sid = str(signal["id"])
        signal_scores[sid] = {"score": signal.get("score", 50.0)}
        corr_info[sid] = {
            "weight": signal.get("weight", 0.0),
            "significant": bool(signal.get("significant")),
        }

    full: dict = {
        "confluence": {"overall_score": components.get("final_score")},
        "signal_scores": signal_scores,
        "corr_info": corr_info,
        "momentum_score": components.get("momentum_score", 50.0),
    }
    optional_map = {
        "insider": ("has_insider_signal", "insider_score"),
        "short_interest": ("has_short_interest_signal", "short_interest_score"),
        "thirteenf": ("has_13f_signal", "thirteenf_score"),
    }
    for item in components.get("components") or []:
        if not isinstance(item, dict):
            continue
        mapped = optional_map.get(str(item.get("id", "")))
        if mapped and item.get("score") is not None:
            flag_key, score_key = mapped
            full[flag_key] = True
            full[score_key] = {"score": item["score"]}
    return compute_personal_score(full, profile)
