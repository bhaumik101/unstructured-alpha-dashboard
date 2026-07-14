# utils/coverage.py
# Unstructured Alpha — Coverage Tiers + Confidence Methodology
#
# The second audit's hardest requirement: a Confluence Score built on ONE
# relevant signal must never look as trustworthy as one built on twelve, and a
# thin-coverage ticker must get an HONEST state, not a "—/100 Unknown" box.
#
# This module is the single, documented methodology for:
#   • COVERAGE — how many genuinely-relevant, well-sampled signals underpin a
#     score, bucketed into explicit tiers. Below the "Limited" floor NO
#     Confluence Score is generated; the caller shows an honest limited-coverage
#     state instead.
#   • CONFIDENCE — a defensible, coverage-DOMINATED read combining coverage,
#     data freshness, signal agreement and (optionally) measured validation.
#     Confidence is deliberately capped by coverage: you cannot earn "High"
#     confidence from a handful of signals no matter how fresh or agreeing they
#     are. This is the whole point.
#
# Nothing here invents certainty. Every output traces to a counted input.
# Pure functions, unit-tested against ground truth.

from __future__ import annotations

from typing import Optional

# ── Coverage tiers ───────────────────────────────────────────────────────────
# Thresholds are on the count of RELEVANT, well-sampled signals actually driving
# the score (statistically significant with a real sample). Below 2 there isn't
# enough to honestly compute a composite.
_TIERS = [
    ("full",         "Full Macro Coverage",    10, True,
     "High interpretability — many relevant macro signals available."),
    ("moderate",     "Moderate Coverage",       5, True,
     "Directional macro context available."),
    ("limited",      "Limited Coverage",        2, True,
     "Only a few relevant signals — use as directional context, with caution."),
    ("insufficient", "Insufficient Coverage",   0, False,
     "Too few relevant signals to compute a Confluence Score."),
]


def coverage_tier(n_relevant: int) -> dict:
    """
    Bucket a relevant-signal count into an explicit coverage tier.

    Returns {id, label, note, min_signals, generates_score, n_relevant}.
    `generates_score` is False for 'insufficient' — the caller must NOT render a
    normal 0-100 score in that case; show the honest limited-coverage state.
    """
    n = int(n_relevant or 0)
    for tid, label, floor, gen, note in _TIERS:
        if n >= floor:
            return {"id": tid, "label": label, "note": note, "min_signals": floor,
                    "generates_score": gen, "n_relevant": n}
    # (unreachable — the last tier has floor 0)
    return {"id": "insufficient", "label": "Insufficient Coverage", "note": _TIERS[-1][4],
            "min_signals": 0, "generates_score": False, "n_relevant": n}


# ── Confidence methodology ───────────────────────────────────────────────────

def assess_confidence(
    n_significant: int,
    n_available: int,
    n_expected: int,
    n_stale: int = 0,
    agreement_ratio: float = 0.0,
    validation_score: Optional[float] = None,
) -> dict:
    """
    A defensible confidence read. Inputs (all counted, none invented):
      n_significant : relevant signals with a statistically significant link
      n_available   : relevant signals that returned usable, non-stale data
      n_expected    : relevant signals we would expect for this ticker
      n_stale       : relevant signals whose source data is stale
      agreement_ratio : 0..1, share of significant signals pointing one way
      validation_score: 0..100 measured out-of-sample reliability, if available

    Returns {level, score, color, reasons[], components{...}}.

    METHODOLOGY — confidence is COVERAGE-DOMINATED and then HARD-CAPPED by
    coverage so a thin score can never present as strong:
      score = 100 * (0.50*coverage + 0.25*freshness + 0.15*agreement + 0.10*validation)
      then level is capped: High needs >=8 significant, Moderate needs >=4,
      2-3 -> Limited, <=1 -> Insufficient (no score).
    """
    n_sig = max(0, int(n_significant or 0))
    n_av = max(0, int(n_available or 0))
    n_exp = max(1, int(n_expected or 1))
    n_st = max(0, int(n_stale or 0))
    agree = min(1.0, max(0.0, float(agreement_ratio or 0.0)))

    coverage = min(1.0, n_sig / 10.0)                       # saturates at 10 signals
    freshness = 1.0 - min(1.0, n_st / max(1, n_av))         # fewer stale = fresher
    val = None
    if validation_score is not None:
        val = min(1.0, max(0.0, float(validation_score) / 100.0))

    if val is not None:
        score01 = 0.50 * coverage + 0.25 * freshness + 0.15 * agree + 0.10 * val
    else:
        # redistribute validation's weight into coverage when unmeasured
        score01 = 0.60 * coverage + 0.25 * freshness + 0.15 * agree
    score = round(100 * score01)

    # Coverage HARD CAP — the non-negotiable rule.
    if n_sig <= 1:
        level, color = "Insufficient", "#FF4444"
    else:
        if n_sig >= 8:
            cap = "High"
        elif n_sig >= 4:
            cap = "Moderate"
        else:
            cap = "Limited"
        by_score = "High" if score >= 66 else ("Moderate" if score >= 40 else "Limited")
        order = {"Limited": 0, "Moderate": 1, "High": 2}
        level = by_score if order[by_score] <= order[cap] else cap
        color = {"High": "#00C853", "Moderate": "#FF9800", "Limited": "#FF6B6B"}[level]

    reasons = []
    reasons.append(f"{n_sig} of {n_exp} expected signals are statistically relevant")
    if n_st > 0:
        reasons.append(f"{n_st} relevant signal{'s' if n_st != 1 else ''} currently stale")
    if n_sig < 8 and level != "Insufficient":
        reasons.append("coverage caps confidence — more relevant signals are needed for High")
    if validation_score is not None:
        reasons.append(f"measured out-of-sample reliability factored in ({round(validation_score)}/100)")

    return {
        "level": level,
        "score": score if level != "Insufficient" else None,
        "color": color,
        "reasons": reasons,
        "components": {
            "coverage": round(coverage, 2),
            "freshness": round(freshness, 2),
            "agreement": round(agree, 2),
            "validation": round(val, 2) if val is not None else None,
        },
    }
