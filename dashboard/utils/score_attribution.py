# utils/score_attribution.py
# Unstructured Alpha — "Explain the Move" attribution engine
#
# THE PRIMITIVE: given a ticker's component snapshot at Time A and Time B (from
# utils.score_components.build_components, persisted via score_history), explain
# the change in its Confluence Score from ACTUAL model inputs — never a generated
# "likely drivers" list.
#
# Every driver (macro signal, price momentum, positioning signal) carries a
# contribution that sums to the final score. The change in the score is therefore
# exactly the sum of the changes in those contributions:
#     Δscore = Σ Δcontributionᵢ            (reconciles within rounding tolerance)
# We attribute Δscore across factor families, classify WHY each driver moved
# (market input vs weight vs coverage vs model change), rank by materiality, and
# refuse to show a clean explanation when the math doesn't reconcile.
#
# Pure & dependency-light: operates on the two component dicts. No DB, no config.

from __future__ import annotations

# If |Δscore − Σ Δcontribution| exceeds this, we do NOT show a clean attribution.
RECONCILE_TOLERANCE = 1.0

# Below this absolute contribution delta, a driver is "effectively unchanged".
_UNCHANGED_EPS = 0.15

# Materiality: share of the driver's directional movement bucket.
_PRIMARY_SHARE = 0.25
_MEANINGFUL_SHARE = 0.10

# Cause codes (see spec).
MARKET_INPUT_CHANGE = "MARKET_INPUT_CHANGE"
WEIGHT_CHANGE = "WEIGHT_CHANGE"
SIGNAL_ADDED = "SIGNAL_ADDED"
SIGNAL_REMOVED = "SIGNAL_REMOVED"
DATA_RECOVERY = "DATA_RECOVERY"
DATA_LOSS = "DATA_LOSS"
MODEL_VERSION_CHANGE = "MODEL_VERSION_CHANGE"

# Causes that reflect the MODEL changing rather than the market moving.
_MODEL_CAUSES = {WEIGHT_CHANGE, SIGNAL_ADDED, SIGNAL_REMOVED, MODEL_VERSION_CHANGE}


def reconstruct_prior(comp_b: dict, hist_scores: dict, as_of_date: str | None = None,
                      min_fraction: float = 0.25) -> dict | None:
    """
    Reconstruct an approximate 'Time A' component snapshot from the CURRENT snapshot
    (comp_b) plus REAL historical per-signal percentile scores (hist_scores, keyed
    by signal_id — e.g. from signal_snapshots). This is how "Explain the Move" works
    on day 1, before genuine component history has accrued:

      - Each macro signal's contribution is recomputed as
            score_history · norm_weight_current · (remaining·0.80)
        i.e. the CURRENT model weighting applied to the ACTUAL historical reading.
      - Momentum and positioning are held at current values (no historical
        decomposition exists), so they contribute ZERO to the attributed move —
        the attribution is honest that it explains the MACRO-signal movement only.

    The result is stamped reconstructed=True (same model_version as comp_b, so it
    does not false-trigger a model-change flag). Returns None when too few signals
    have a historical reading for the reconstruction to be meaningful.
    """
    signals_b = comp_b.get("signals") or []
    if not signals_b or not hist_scores:
        return None
    remaining = float(comp_b.get("remaining", 1.0) or 1.0)
    macro_weight = remaining * 0.80
    n_hist = 0
    new_signals = []
    for s in signals_b:
        hs = hist_scores.get(s["id"])
        if hs is None:
            score_a = float(s.get("score", 50.0)); available = False
        else:
            score_a = float(hs); available = True; n_hist += 1
        nw = float(s.get("norm_weight", 0.0) or 0.0)
        new_signals.append({**s, "score": round(score_a, 2),
                            "contribution": round(score_a * nw * macro_weight, 4),
                            "available": available})
    if n_hist < max(2, int(min_fraction * len(signals_b))):
        return None
    components_a = [dict(c) for c in (comp_b.get("components") or [])]  # held constant
    recon_total = round(sum(x["contribution"] for x in new_signals)
                        + sum(c["contribution"] for c in components_a), 2)
    out = dict(comp_b)
    out.update({
        "signals": new_signals, "components": components_a,
        "final_score": recon_total, "reconstructed_score": recon_total,
        "reconstructed": True, "snapshot_date": as_of_date,
    })
    return out


def _index_signals(comp: dict) -> dict:
    return {s["id"]: s for s in (comp.get("signals") or [])}


def _index_components(comp: dict) -> dict:
    return {c["id"]: c for c in (comp.get("components") or [])}


def _classify(a: dict | None, b: dict | None, model_changed: bool) -> str:
    """Classify why a single driver's contribution changed."""
    if a is None and b is not None:
        return SIGNAL_ADDED
    if a is not None and b is None:
        return SIGNAL_REMOVED
    av_a = bool(a.get("available", True)) if a else True
    av_b = bool(b.get("available", True)) if b else True
    if av_a and not av_b:
        return DATA_LOSS
    if (not av_a) and av_b:
        return DATA_RECOVERY
    # Both present & available: decide weight vs market input.
    nw_a = float(a.get("norm_weight", 0.0)); nw_b = float(b.get("norm_weight", 0.0))
    sc_a = float(a.get("score", 50.0)); sc_b = float(b.get("score", 50.0))
    score_moved = abs(sc_b - sc_a) >= 0.5
    weight_moved = abs(nw_b - nw_a) >= max(0.02, 0.15 * max(nw_a, 1e-9))
    if weight_moved and not score_moved:
        return WEIGHT_CHANGE
    if model_changed and weight_moved and not score_moved:
        return WEIGHT_CHANGE
    return MARKET_INPUT_CHANGE


def _materiality(share: float) -> str:
    if share >= _PRIMARY_SHARE:
        return "primary"
    if share >= _MEANINGFUL_SHARE:
        return "meaningful"
    return "minor"


def attribute_move(comp_a: dict | None, comp_b: dict | None,
                   from_date: str | None = None, to_date: str | None = None,
                   window_label: str | None = None) -> dict:
    """
    Attribute the Confluence Score change between two component snapshots.
    Returns a structured, JSON-serializable attribution. `state` is one of:
      ok | no_comparison | insufficient_coverage | unreconciled
    Callers must respect `state` and never render a clean explanation unless
    state == "ok".
    """
    if not comp_a or not comp_b:
        return {"state": "no_comparison",
                "reason": "No comparable score snapshot exists for this period yet."}

    score_from = float(comp_a.get("final_score", 0.0))
    score_to = float(comp_b.get("final_score", 0.0))
    total_change = round(score_to - score_from, 2)
    direction = "up" if total_change > _UNCHANGED_EPS else ("down" if total_change < -_UNCHANGED_EPS else "flat")

    model_from = comp_a.get("model_version"); model_to = comp_b.get("model_version")
    reg_from = comp_a.get("signal_registry_version"); reg_to = comp_b.get("signal_registry_version")
    model_changed = (model_from != model_to) or (reg_from != reg_to)

    # ── Build unified driver list: macro signals grouped by factor + momentum/positioning ──
    sig_a, sig_b = _index_signals(comp_a), _index_signals(comp_b)
    comp_a_c, comp_b_c = _index_components(comp_a), _index_components(comp_b)

    drivers = []  # each: id, name, factor, factor_name, c_from, c_to, delta, cause, meta
    for sid in sorted(set(sig_a) | set(sig_b)):
        a = sig_a.get(sid); b = sig_b.get(sid)
        c_from = float(a["contribution"]) if a else 0.0
        c_to = float(b["contribution"]) if b else 0.0
        ref = b or a
        drivers.append({
            "id": sid, "name": ref.get("name", sid),
            "factor": ref.get("factor", "other"), "factor_name": ref.get("factor_name", "Other"),
            "c_from": round(c_from, 3), "c_to": round(c_to, 3), "delta": round(c_to - c_from, 3),
            "cause": _classify(a, b, model_changed),
            "score_from": (a or {}).get("score"), "score_to": (b or {}).get("score"),
            "weight_from": (a or {}).get("norm_weight"), "weight_to": (b or {}).get("norm_weight"),
            "raw_from": (a or {}).get("raw_value"), "raw_to": (b or {}).get("raw_value"),
            "as_of": (b or {}).get("as_of") or (a or {}).get("as_of"),
            "kind": "signal",
        })
    # Momentum + positioning behave as their own single-signal "factors".
    for cid in sorted(set(comp_a_c) | set(comp_b_c)):
        a = comp_a_c.get(cid); b = comp_b_c.get(cid)
        c_from = float(a["contribution"]) if a else 0.0
        c_to = float(b["contribution"]) if b else 0.0
        ref = b or a
        kind = ref.get("kind", "component")
        fam = "momentum" if kind == "momentum" else "positioning"
        fam_name = "Price Momentum" if kind == "momentum" else "Positioning"
        drivers.append({
            "id": cid, "name": ref.get("label", cid), "factor": fam, "factor_name": fam_name,
            "c_from": round(c_from, 3), "c_to": round(c_to, 3), "delta": round(c_to - c_from, 3),
            "cause": _classify(a, b, model_changed) if kind != "momentum" else MARKET_INPUT_CHANGE,
            "score_from": (a or {}).get("score"), "score_to": (b or {}).get("score"),
            "weight_from": None, "weight_to": None, "kind": kind,
        })

    # ── Reconciliation gate ──
    sum_delta = round(sum(d["delta"] for d in drivers), 3)
    reconciliation_delta = round(total_change - sum_delta, 3)
    # Directional totals (movement buckets), computed from real deltas.
    neg_total = round(sum(d["delta"] for d in drivers if d["delta"] < 0), 3)
    pos_total = round(sum(d["delta"] for d in drivers if d["delta"] > 0), 3)

    # ── Factor aggregation ──
    from collections import defaultdict
    fac = defaultdict(lambda: {"delta": 0.0, "c_from": 0.0, "c_to": 0.0, "signals": [], "factor_name": ""})
    for d in drivers:
        f = fac[d["factor"]]
        f["delta"] += d["delta"]; f["c_from"] += d["c_from"]; f["c_to"] += d["c_to"]
        f["factor_name"] = d["factor_name"]
        f["signals"].append(d)
    factors = []
    for fkey, f in fac.items():
        fdelta = round(f["delta"], 3)
        bucket = neg_total if fdelta < 0 else pos_total
        share = abs(fdelta) / abs(bucket) if bucket else 0.0
        factors.append({
            "factor": fkey, "factor_name": f["factor_name"],
            "contribution_from": round(f["c_from"], 2), "contribution_to": round(f["c_to"], 2),
            "delta": fdelta, "share_of_direction": round(share, 4),
            "materiality": _materiality(share) if abs(fdelta) >= _UNCHANGED_EPS else "minor",
            "direction": "up" if fdelta > _UNCHANGED_EPS else ("down" if fdelta < -_UNCHANGED_EPS else "flat"),
            "signals": sorted(f["signals"], key=lambda s: s["delta"]),
        })
    factors.sort(key=lambda x: x["delta"])  # most negative first

    n_weakened = sum(1 for f in factors if f["direction"] == "down")
    n_improved = sum(1 for f in factors if f["direction"] == "up")
    n_unchanged = sum(1 for f in factors if f["direction"] == "flat")

    # ── Model vs market split (honesty when the model changed) ──
    model_points = round(sum(d["delta"] for d in drivers if d["cause"] in _MODEL_CAUSES), 2)
    market_points = round(sum(d["delta"] for d in drivers if d["cause"] not in _MODEL_CAUSES), 2)

    # ── Coverage-aware state (never dress up a 2-signal ticker as broad intel) ──
    cov = comp_b.get("coverage", {}) or {}
    n_available = int(cov.get("n_available", len(sig_b)))
    generates = cov.get("generates_score", True)

    out = {
        "ticker": comp_b.get("ticker", ""),
        "score_from": round(score_from, 1), "score_to": round(score_to, 1),
        "total_change": total_change, "direction": direction,
        "from_date": from_date, "to_date": to_date, "window_label": window_label,
        "model_changed": model_changed, "model_from": model_from, "model_to": model_to,
        "reconciliation_delta": reconciliation_delta,
        "neg_total": neg_total, "pos_total": pos_total,
        "factors": factors,
        "n_weakened": n_weakened, "n_improved": n_improved, "n_unchanged": n_unchanged,
        "model_points": model_points, "market_points": market_points,
        "coverage": {"n_available": n_available, "tier": cov.get("tier", "unknown"),
                     "generates_score": generates},
    }

    out["reconstructed"] = bool((comp_a or {}).get("reconstructed") or (comp_b or {}).get("reconstructed"))

    # ── Honest states, in priority order ──
    if abs(reconciliation_delta) > RECONCILE_TOLERANCE:
        out["state"] = "unreconciled"
        out["summary"] = summarize(out)
        return out
    if not generates or n_available <= 1:
        out["state"] = "insufficient_coverage"
        out["summary"] = summarize(out)
        return out

    out["state"] = "ok"
    out["summary"] = summarize(out)
    return out


def _fmt(v: float) -> str:
    """Signed, 1-decimal point display: +8.1 / -4.4 / 0.0."""
    return f"{v:+.1f}"


# Calm, non-neon palette (relies on +/- signs too, never color alone).
_NEG = "#D0524F"
_POS = "#4E9A6B"
_DIM = "#8892AA"
_INK = "#E8EEFF"

# Factor-level mechanism copy for "What actually changed? → Why it matters here".
# Deliberately FACTOR-level and honest (not fabricated ticker-specific claims):
# the model maps each ticker to these factor families and applies the family's
# sensitivity. If a ticker-specific mechanism is ever encoded, prefer that.
_FACTOR_MECHANISM = {
    "rates":       "The model applies interest-rate sensitivity to long-duration and rate-exposed holdings.",
    "liquidity":   "Liquidity conditions scale the model's risk-appetite read for this ticker's exposure.",
    "credit":      "Credit spreads gauge financial stress that flows through to this ticker's risk premium.",
    "growth":      "Growth/activity data drives the cyclical-demand component of this ticker's backdrop.",
    "labor":       "Labor-market strength feeds the consumer-demand and rate-path read for this ticker.",
    "consumer":    "Consumer-demand signals map to this ticker's revenue-cycle sensitivity.",
    "housing":     "Housing activity maps to this ticker's rate- and construction-linked exposure.",
    "inflation":   "Inflation expectations move the real-rate and margin backdrop for this ticker.",
    "energy":      "Energy prices/inventories map to this ticker's input-cost or revenue sensitivity.",
    "volatility":  "Volatility/positioning gauges the market's risk appetite around this ticker.",
    "capex_tech":  "Technology-capex signals map to this ticker's AI/hardware demand exposure.",
    "momentum":    "Price momentum contributes a trend component blended into the score.",
    "positioning": "Positioning signals (insider / short interest / 13F) adjust the score where available.",
}


def _signal_detail(s: dict) -> str:
    """Compact 'what actually changed' line for one signal under a primary driver:
    percentile X→Y · weight N% · raw X→Y · updated <date>. Skips missing pieces."""
    bits = []
    if s.get("score_from") is not None and s.get("score_to") is not None:
        bits.append(f'percentile {s["score_from"]:g}&rarr;{s["score_to"]:g}')
    w = s.get("weight_to")
    if w is not None:
        bits.append(f'weight {round(float(w) * 100):g}%')
    if s.get("raw_from") is not None and s.get("raw_to") is not None:
        bits.append(f'raw {s["raw_from"]:g}&rarr;{s["raw_to"]:g}')
    elif s.get("raw_to") is not None:
        bits.append(f'raw {s["raw_to"]:g}')
    if s.get("as_of"):
        bits.append(f'updated {s["as_of"]}')
    return " &middot; ".join(bits)


def _driver_row(name: str, delta: float, sub: str = "", indent: bool = False) -> str:
    color = _NEG if delta < -_UNCHANGED_EPS else (_POS if delta > _UNCHANGED_EPS else _DIM)
    pad = "padding-left:16px;" if indent else ""
    size = "0.8rem" if indent else "0.92rem"
    weight = "500" if indent else "650"
    sub_html = (f'<div style="font-size:0.72rem;color:{_DIM};margin-top:1px;">{sub}</div>'
                if sub else "")
    return (
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
        f'gap:10px;{pad}padding-top:6px;padding-bottom:6px;'
        f'border-bottom:1px solid rgba(255,255,255,0.04);">'
        f'<div style="min-width:0;"><div style="font-size:{size};font-weight:{weight};'
        f'color:{_INK};">{name}</div>{sub_html}</div>'
        f'<div style="font-size:{size};font-weight:700;color:{color};'
        f'font-variant-numeric:tabular-nums;white-space:nowrap;">{_fmt(delta)}</div>'
        f'</div>'
    )


def render_attribution_html(attr: dict, show_signals: bool = True) -> str:
    """
    Reusable, mobile-first HTML for an attribution result (use with st.html).
    Renders factor-level contributions by default, with the underlying signals
    nested under each MATERIAL factor (progressive disclosure), a reconciliation
    footer, and the deterministic bottom-line summary. Honest states render a calm
    safe message instead of a fake explanation.
    """
    state = attr.get("state")
    if state == "no_comparison":
        return (
            f'<div style="border:1px solid rgba(255,255,255,0.08);border-radius:10px;'
            f'padding:16px 18px;font-family:Inter,sans-serif;color:{_DIM};font-size:0.85rem;">'
            f'{attr.get("reason", "No comparable score snapshot exists for this period yet.")}'
            f' As this ticker is viewed over time, its history builds and this becomes available.</div>'
        )
    if state == "unreconciled":
        return (
            f'<div style="border:1px solid rgba(255,255,255,0.08);border-radius:10px;'
            f'padding:16px 18px;font-family:Inter,sans-serif;color:{_DIM};font-size:0.85rem;">'
            f'A detailed move attribution is not available for this comparison.</div>'
        )

    tkr = attr.get("ticker", "")
    sf, st_, chg = attr.get("score_from"), attr.get("score_to"), attr.get("total_change", 0.0)
    win = (attr.get("window_label") or "").upper()
    chg_color = _NEG if chg < 0 else (_POS if chg > 0 else _DIM)

    head = (
        f'<div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-bottom:4px;">'
        f'<div style="font-size:1.05rem;font-weight:800;color:{_INK};">{tkr}</div>'
        f'<div style="font-size:1.05rem;font-weight:700;color:{_INK};'
        f'font-variant-numeric:tabular-nums;">{sf:g} &rarr; {st_:g}</div>'
        f'<div style="font-size:1.05rem;font-weight:800;color:{chg_color};">{_fmt(chg)}</div>'
        f'<div style="font-size:0.62rem;letter-spacing:0.12em;color:{_DIM};'
        f'font-weight:700;">{win}</div></div>'
    )

    banner = ""
    if attr.get("model_changed"):
        mp = attr.get("model_points", 0.0)
        banner = (
            f'<div style="background:rgba(124,58,237,0.10);border:1px solid rgba(124,58,237,0.30);'
            f'border-radius:8px;padding:9px 12px;margin:8px 0;font-size:0.75rem;color:#B79CFF;">'
            f'Model methodology changed during this period — about {abs(mp):.0f} of the '
            f'{abs(chg):.0f} points reflect a scoring update, not the market.</div>'
        )
    if attr.get("reconstructed"):
        banner += (
            f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);'
            f'border-radius:8px;padding:9px 12px;margin:8px 0;font-size:0.72rem;color:{_DIM};">'
            f'Reconstructed from historical signal readings using the current model weighting. '
            f'Momentum &amp; positioning are held at current values, so this explains the '
            f'macro-signal movement only.</div>'
        )

    if state == "insufficient_coverage":
        n = attr.get("coverage", {}).get("n_available", 0)
        body = (
            f'<div style="font-size:0.8rem;color:{_DIM};margin:6px 0 4px;">Limited attribution — '
            f'this score currently uses {n} available macro input{"s" if n != 1 else ""}.</div>'
        )
        rows = "".join(_driver_row(f["factor_name"], f["delta"]) for f in attr.get("factors", [])
                       if abs(f["delta"]) >= _UNCHANGED_EPS)
        summ = (f'<div style="font-size:0.8rem;color:{_INK};margin-top:12px;line-height:1.55;">'
                f'{attr.get("summary", "")}</div>')
        return (f'<div style="font-family:Inter,sans-serif;border:1px solid rgba(255,255,255,0.06);'
                f'border-radius:12px;padding:16px 18px;">{head}{banner}{body}{rows}{summ}</div>')

    # ── Factor list (material first), with nested signals under material factors ──
    rows = []
    minor_delta = 0.0
    minor_n = 0
    for f in attr.get("factors", []):
        if f["materiality"] == "minor" or abs(f["delta"]) < _UNCHANGED_EPS:
            if abs(f["delta"]) >= 0.05:
                minor_delta += f["delta"]; minor_n += 1
            continue
        sub = f'contribution {f["contribution_from"]:g} &rarr; {f["contribution_to"]:g}'
        rows.append(_driver_row(f["factor_name"], f["delta"], sub))
        if show_signals and f["materiality"] == "primary":
            _shown = 0
            for s in f["signals"]:
                if abs(s["delta"]) < _UNCHANGED_EPS:
                    continue
                rows.append(_driver_row(s["name"], s["delta"], _signal_detail(s), indent=True))
                _shown += 1
            # "Why it matters here" — honest factor-level mechanism for the driver.
            mech = _FACTOR_MECHANISM.get(f["factor"])
            if _shown and mech:
                rows.append(
                    f'<div style="padding-left:16px;font-size:0.7rem;color:{_DIM};'
                    f'line-height:1.5;margin:1px 0 6px;"><span style="color:#B79CFF;'
                    f'font-weight:600;">Why it matters:</span> {mech}</div>'
                )
    if minor_n:
        rows.append(_driver_row(f"{minor_n} other factor{'s' if minor_n != 1 else ''}", minor_delta,
                                "combined, immaterial individually"))
    rows_html = "".join(rows)

    # ── Reconciliation footer: start → drivers → end ──
    recon = (
        f'<div style="display:flex;justify-content:space-between;font-size:0.78rem;'
        f'color:{_DIM};margin-top:10px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.10);">'
        f'<span>Starting score</span><span style="font-variant-numeric:tabular-nums;">{sf:g}</span></div>'
        f'<div style="display:flex;justify-content:space-between;font-size:0.82rem;'
        f'color:{_INK};font-weight:700;"><span>Ending score</span>'
        f'<span style="font-variant-numeric:tabular-nums;">{st_:g}</span></div>'
    )

    summ = (
        f'<div style="font-size:0.82rem;color:{_INK};margin-top:12px;line-height:1.6;">'
        f'{attr.get("summary", "")}</div>'
        f'<div style="font-size:0.7rem;color:{_DIM};margin-top:8px;">This is macro context, '
        f'not a price forecast.</div>'
    )

    return (
        f'<div style="font-family:Inter,sans-serif;border:1px solid rgba(255,255,255,0.06);'
        f'border-radius:12px;padding:16px 18px;">'
        f'{head}{banner}'
        f'<div style="font-size:0.6rem;letter-spacing:0.1em;color:{_DIM};font-weight:700;'
        f'text-transform:uppercase;margin:10px 0 2px;">What drove the move</div>'
        f'{rows_html}{recon}{summ}</div>'
    )


def summarize(attr: dict) -> str:
    """
    Deterministic one/two-sentence summary built ONLY from structured attribution
    numbers — no LLM. Reads naturally while staying honest about what moved.
    """
    if attr.get("state") == "no_comparison":
        return "No comparable score snapshot exists for this period yet."
    if attr.get("state") == "unreconciled":
        return "A detailed move attribution is not available for this comparison."

    tkr = attr.get("ticker", "This ticker")
    chg = attr.get("total_change", 0.0)
    dirn = attr.get("direction")
    factors = attr.get("factors", [])
    downs = [f for f in factors if f["direction"] == "down"]
    ups = [f for f in factors if f["direction"] == "up"]

    if dirn == "flat":
        return f"{tkr}'s Confluence Score was effectively unchanged over this period."

    if attr.get("state") == "insufficient_coverage":
        n = attr.get("coverage", {}).get("n_available", 0)
        lead = downs[0] if downs else (ups[0] if ups else None)
        base = (f"{tkr}'s score {'fell' if chg < 0 else 'rose'} {abs(chg):.0f} points, but coverage is "
                f"limited — it currently uses {n} available macro input{'s' if n != 1 else ''}.")
        if lead:
            base += f" {lead['factor_name']} accounted for {_fmt(lead['delta'])} points."
        return base + " This movement reflects a narrow set of macro factors."

    verb = "weakened" if chg < 0 else "strengthened"
    lead_bucket = downs if chg < 0 else ups
    lead_bucket = sorted(lead_bucket, key=lambda f: abs(f["delta"]), reverse=True)
    parts = [f"{tkr}'s macro backdrop {verb} {abs(chg):.0f} points."]

    if lead_bucket:
        top = lead_bucket[:2]
        names = " and ".join(f["factor_name"].lower() for f in top)
        bucket_total = attr["neg_total"] if chg < 0 else attr["pos_total"]
        top_sum = sum(f["delta"] for f in top)
        if bucket_total:
            pct = round(100 * abs(top_sum) / abs(bucket_total))
            parts.append(f"{names.capitalize()} drove {pct}% of the "
                         f"{'deterioration' if chg < 0 else 'improvement'}.")
    offsets = ups if chg < 0 else downs
    if offsets:
        off_sum = sum(f["delta"] for f in offsets)
        strongest = max(offsets, key=lambda f: abs(f["delta"]))
        parts.append(f"{strongest['factor_name']} moved the other way but only offset "
                     f"{abs(off_sum):.0f} point{'s' if abs(round(off_sum)) != 1 else ''}.")
    if attr.get("reconstructed"):
        parts.append("Based on historical signal readings with the current model weighting; "
                     "momentum and positioning are held at current values.")
    if attr.get("model_changed"):
        parts.append("Note: the scoring methodology changed during this period, so part of the "
                     "move reflects a model update, not the market.")
    return " ".join(parts)
