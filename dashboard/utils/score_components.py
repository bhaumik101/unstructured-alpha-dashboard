# utils/score_components.py
# Unstructured Alpha — Confluence Score component decomposition
#
# Turns the rich dict returned by utils.ticker_score.compute_full_ticker_score
# into a flat, self-reconciling breakdown of WHERE the final Confluence Score
# came from: one contribution per macro signal (grouped by factor family), plus
# price momentum and any active positioning signals. The sum of every
# contribution equals the final score — that exact reconciliation is what lets
# "Explain the Move" attribute a before/after change to specific drivers.
#
# The scoring math this mirrors (see compute_full_ticker_score):
#     macro_score = Σ(sᵢ·wᵢ) / Σwᵢ            # correlation-weighted signal blend
#     remaining   = 1 − 0.12·n_optional
#     final       = macro_score·(remaining·0.80)      # macro
#                 + momentum ·(remaining·0.20)        # momentum
#                 + Σ(optionalⱼ·0.12)                 # positioning
# so each macro signal's contribution to the FINAL score is
#     cᵢ = sᵢ · (wᵢ/Σwᵢ) · (remaining·0.80)
# and Σcᵢ + momentum_contrib + Σoptional_contrib == final (within rounding).
#
# Pure: depends only on taxonomy (factor family), coverage (tier), model_version,
# and — best-effort, with graceful fallback — config for display names.

from __future__ import annotations

# Constants mirrored from compute_full_ticker_score. If those change, bump
# MODEL_VERSION in utils.model_version so historical comparisons flag it.
_MACRO_SPLIT = 0.80
_MOM_SPLIT = 0.20
_OPTIONAL_SLICE = 0.12


def _signal_name(sid: str) -> str:
    try:
        from utils.config import SIGNALS
        return SIGNALS.get(sid, {}).get("name", sid)
    except Exception:
        return sid


def _factor(sid: str) -> tuple[str, str]:
    try:
        from utils import taxonomy
        fam = taxonomy.factor_family_of(sid)
        return fam, taxonomy.factor_family_name(fam)
    except Exception:
        return "other", "Other"


def build_components(result: dict) -> dict:
    """
    Decompose a compute_full_ticker_score() result into a reconciling component
    snapshot. Returns a JSON-serializable dict:

        {
          "ticker": str,
          "final_score": float,            # the displayed Confluence Score
          "reconstructed_score": float,    # Σ contributions (≈ final_score)
          "macro_score": float, "momentum_score": float,
          "n_optional": int, "remaining": float,
          "signals": [ {id,name,score,weight,norm_weight,contribution,
                        factor,factor_name,significant,available,r} ],
          "components": [ {kind,id,label,score,contribution} ],  # momentum + optionals
          "coverage": {n_available,n_significant,tier,generates_score},
          "model_version": str, "signal_registry_version": str, "calculated_at": str,
        }

    `available` marks whether a macro signal had usable correlation data for this
    ticker at snapshot time (n>0); it flips drive DATA_LOSS / DATA_RECOVERY
    classification in the attribution engine.
    """
    from datetime import datetime, timezone

    ticker = str(result.get("ticker", "")).upper()
    signal_scores = result.get("signal_scores", {}) or {}
    corr_info = result.get("corr_info", {}) or {}
    relevant = result.get("relevant_sig_ids") or list(signal_scores.keys())

    # ── Optional (positioning) signals: fixed 12% slice each when active ──
    def _opt(flag_key, score_key, cid, label):
        if not result.get(flag_key):
            return None
        sd = result.get(score_key, {}) or {}
        sc = sd.get("score")
        if sc is None:
            return None
        return {"kind": "optional", "id": cid, "label": label, "score": float(sc)}

    optionals = [o for o in (
        _opt("has_contract_signal", "contract_velocity", "contracts", "Federal Contracts"),
        _opt("has_insider_signal", "insider_score", "insider", "Insider Activity"),
        _opt("has_short_interest_signal", "short_interest_score", "short_interest", "Short Interest"),
        _opt("has_13f_signal", "thirteenf_score", "thirteenf", "13F Positioning"),
    ) if o is not None]
    n_optional = len(optionals)
    remaining = 1.0 - _OPTIONAL_SLICE * n_optional
    macro_weight = remaining * _MACRO_SPLIT
    mom_weight = remaining * _MOM_SPLIT

    # ── Macro signals: weighted blend → per-signal contribution ──
    included = [sid for sid in relevant if sid in signal_scores]
    w_total = 0.0
    for sid in included:
        w_total += float(corr_info.get(sid, {}).get("weight", 0.0) or 0.0)
    w_total = w_total or 1.0  # guard: never divide by zero

    signals = []
    macro_score = 0.0
    n_significant = 0
    for sid in included:
        ci = corr_info.get(sid, {}) or {}
        s = float(signal_scores.get(sid, {}).get("score", 50) or 50)
        w = float(ci.get("weight", 0.0) or 0.0)
        nw = w / w_total
        contribution = s * nw * macro_weight
        macro_score += s * nw
        fam, fam_name = _factor(sid)
        sig_significant = bool(ci.get("significant", False))
        n_significant += 1 if sig_significant else 0
        # Raw series value + freshness date — powers the "What actually changed?"
        # per-signal detail (the raw series moved from X to Y, last updated <date>).
        raw_value, as_of = None, None
        try:
            _raw = (result.get("signal_data") or {}).get(sid)
            if _raw is not None:
                _rd = _raw.dropna()
                if len(_rd):
                    raw_value = round(float(_rd.iloc[-1]), 4)
                    as_of = str(_rd.index[-1])[:10]
        except Exception:
            pass
        signals.append({
            "id": sid,
            "name": _signal_name(sid),
            "score": round(s, 2),
            "weight": round(w, 4),
            "norm_weight": round(nw, 4),
            "contribution": round(contribution, 4),
            "factor": fam,
            "factor_name": fam_name,
            "significant": sig_significant,
            "available": int(ci.get("n", 0) or 0) > 0,
            "r": round(float(ci.get("r", 0.0) or 0.0), 4),
            "raw_value": raw_value,
            "as_of": as_of,
        })

    # ── Momentum + optional contributions ──
    mom_score = float(result.get("momentum_score", 50.0) or 50.0)
    components = [{
        "kind": "momentum", "id": "momentum", "label": "Price Momentum",
        "score": round(mom_score, 2), "contribution": round(mom_score * mom_weight, 4),
    }]
    for o in optionals:
        components.append({
            "kind": "optional", "id": o["id"], "label": o["label"],
            "score": round(o["score"], 2),
            "contribution": round(o["score"] * _OPTIONAL_SLICE, 4),
        })

    reconstructed = sum(s["contribution"] for s in signals) + sum(c["contribution"] for c in components)

    # Final displayed score (already blended inside compute_full_ticker_score).
    final_score = float((result.get("confluence", {}) or {}).get("overall_score", round(reconstructed, 1)))

    # ── Coverage (honest state for low-coverage tickers) ──
    n_available = sum(1 for s in signals if s["available"])
    coverage = {"n_available": n_available, "n_significant": n_significant,
                "tier": "unknown", "generates_score": True}
    try:
        from utils.coverage import coverage_tier
        ct = coverage_tier(n_significant)
        coverage["tier"] = ct.get("tier", "unknown")
        coverage["generates_score"] = ct.get("generates_score", True)
    except Exception:
        pass

    from utils.model_version import MODEL_VERSION, signal_registry_version
    return {
        "ticker": ticker,
        "final_score": round(final_score, 2),
        "reconstructed_score": round(reconstructed, 2),
        "macro_score": round(macro_score, 2),
        "momentum_score": round(mom_score, 2),
        "n_optional": n_optional,
        "remaining": round(remaining, 4),
        "signals": signals,
        "components": components,
        "coverage": coverage,
        "model_version": MODEL_VERSION,
        "signal_registry_version": signal_registry_version(),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }
