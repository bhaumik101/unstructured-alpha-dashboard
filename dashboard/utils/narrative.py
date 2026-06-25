"""
utils/narrative.py
==================
Auto-generates a plain-English macro narrative from the current signal state.
No external AI calls — pure deterministic logic from the signal data.

The goal: make the site feel like it has a brain that reads the data and
tells you what it means, not just displays numbers.

Output example:
  headline: "Macro environment: RISK-ON"
  summary:  "22 of 38 signals are bullish. The strongest tailwind is
             Hyperscaler Capex (94/100), signaling accelerating AI
             infrastructure spending 4–12 weeks ahead. Main risk: the
             Yield Curve is in inversion territory (32/100), which has
             historically preceded credit tightening."
  sectors:  {"Technology & AI": "BULLISH", "Energy": "BULLISH", ...}
  watch:    "Watch credit spreads — currently neutral but approaching
             the threshold that has historically preceded broad market
             pullbacks."
"""

from __future__ import annotations

# ── Signal → human-readable category + lead-time copy ────────────────────────
_SIG_META: dict[str, dict] = {
    "hyperscaler_capex":    {"sector": "Technology & AI",   "lead": "4–12 weeks",  "meaning": "AI infrastructure spending"},
    "semiconductor_demand": {"sector": "Technology & AI",   "lead": "4–8 weeks",   "meaning": "chip demand cycle"},
    "uranium_spot":         {"sector": "Nuclear / Energy",  "lead": "4–16 weeks",  "meaning": "uranium supply/demand"},
    "nuclear_capacity":     {"sector": "Nuclear / Energy",  "lead": "8–16 weeks",  "meaning": "nuclear fleet utilization"},
    "power_demand":         {"sector": "Utilities",         "lead": "4–8 weeks",   "meaning": "electricity consumption growth"},
    "crude_inventories":    {"sector": "Energy",            "lead": "2–6 weeks",   "meaning": "crude supply balance"},
    "natural_gas_storage":  {"sector": "Energy",            "lead": "2–4 weeks",   "meaning": "natural gas supply"},
    "rig_count":            {"sector": "Energy",            "lead": "8–16 weeks",  "meaning": "drilling activity"},
    "trucking_index":       {"sector": "Industrials",       "lead": "4–8 weeks",   "meaning": "freight / consumer demand"},
    "rail_traffic":         {"sector": "Industrials",       "lead": "4–8 weeks",   "meaning": "industrial freight volumes"},
    "ism_manufacturing":    {"sector": "Industrials",       "lead": "4–8 weeks",   "meaning": "factory activity"},
    "yield_curve":          {"sector": "Macro / Rates",     "lead": "12–24 weeks", "meaning": "recession probability"},
    "hy_spread":            {"sector": "Credit",            "lead": "4–8 weeks",   "meaning": "credit stress / risk appetite"},
    "ig_spread":            {"sector": "Credit",            "lead": "4–8 weeks",   "meaning": "investment-grade credit conditions"},
    "vix":                  {"sector": "Volatility",        "lead": "1–4 weeks",   "meaning": "market fear / complacency"},
    "m2_money_supply":      {"sector": "Macro / Rates",     "lead": "8–16 weeks",  "meaning": "monetary liquidity"},
    "jobless_claims":       {"sector": "Labour",            "lead": "4–8 weeks",   "meaning": "labour market health"},
    "jolt_openings":        {"sector": "Labour",            "lead": "4–8 weeks",   "meaning": "hiring demand"},
    "insider_buying":       {"sector": "Sentiment",         "lead": "4–12 weeks",  "meaning": "executive confidence"},
    "short_interest":       {"sector": "Sentiment",         "lead": "2–6 weeks",   "meaning": "bearish positioning"},
    "gasoline_demand":      {"sector": "Consumer",          "lead": "2–6 weeks",   "meaning": "consumer mobility"},
    "retail_sales":         {"sector": "Consumer",          "lead": "4–8 weeks",   "meaning": "consumer spending"},
    "bank_lending":         {"sector": "Financials",        "lead": "4–8 weeks",   "meaning": "credit availability"},
}

_REGIME_THRESHOLDS = {
    "RISK-ON":      (0.58, "#1B5E20"),   # >58% bullish
    "RISK-OFF":     (0.00, "#7B1010"),   # <42% bullish (handled below)
    "TRANSITIONING": (0.00, "#8B7355"), # default
}

_SECTOR_DESCRIPTIONS: dict[str, str] = {
    "Technology & AI":  "AI infrastructure and semiconductor cycle",
    "Nuclear / Energy": "uranium and nuclear power buildout",
    "Energy":           "oil & gas supply/demand",
    "Industrials":      "freight and manufacturing activity",
    "Macro / Rates":    "monetary conditions and rate environment",
    "Credit":           "credit spreads and risk appetite",
    "Consumer":         "consumer spending and mobility",
    "Labour":           "employment market health",
    "Volatility":       "market stress levels",
    "Financials":       "bank lending and credit availability",
    "Sentiment":        "insider and short-seller positioning",
    "Utilities":        "power demand growth",
}


def generate_narrative(signal_scores: dict) -> dict:
    """
    Take the output of get_all_signal_scores() and return a structured
    narrative dict:

    {
        "headline":     str,          # e.g. "Macro environment: RISK-ON"
        "regime":       str,          # RISK-ON / RISK-OFF / TRANSITIONING
        "regime_color": str,          # hex color
        "summary":      str,          # 2-3 sentence plain-English call
        "top_bull":     list[dict],   # top 3 bullish signals with context
        "top_bear":     list[dict],   # top 2 bearish signals with context
        "sector_bias":  dict,         # sector → BULLISH/BEARISH/NEUTRAL
        "watch_note":   str,          # "watch X because Y" sentence
        "bull_count":   int,
        "bear_count":   int,
        "neut_count":   int,
        "total":        int,
    }
    """
    valid = {sid: v for sid, v in signal_scores.items() if not v.get("error")}
    if not valid:
        return _empty_narrative()

    bull_sigs = [(sid, v) for sid, v in valid.items() if v.get("status") == "bullish"]
    bear_sigs = [(sid, v) for sid, v in valid.items() if v.get("status") == "bearish"]
    neut_sigs = [(sid, v) for sid, v in valid.items() if v.get("status") == "neutral"]

    nb, nr, nn = len(bull_sigs), len(bear_sigs), len(neut_sigs)
    total = max(1, nb + nr + nn)
    bull_pct = nb / total
    bear_pct = nr / total

    # Regime
    if bull_pct >= 0.58:
        regime, regime_color = "RISK-ON", "#1B5E20"
    elif bear_pct >= 0.52:
        regime, regime_color = "RISK-OFF", "#7B1010"
    elif bull_pct >= 0.48:
        regime, regime_color = "LEANING BULLISH", "#2E6B35"
    elif bear_pct >= 0.44:
        regime, regime_color = "LEANING BEARISH", "#8B2020"
    else:
        regime, regime_color = "MIXED SIGNALS", "#8B7355"

    # Top signals
    top_bull = sorted(bull_sigs, key=lambda x: -x[1].get("score", 50))[:3]
    top_bear = sorted(bear_sigs, key=lambda x:  x[1].get("score", 50))[:2]
    # Most extreme neutral (closest to 60 or 40 — the edge of a flip)
    near_flip = sorted(
        neut_sigs,
        key=lambda x: -abs(x[1].get("score", 50) - 50)
    )[:1]

    def _enrich(pairs: list[tuple]) -> list[dict]:
        out = []
        for sid, v in pairs:
            meta = _SIG_META.get(sid, {})
            out.append({
                "id":      sid,
                "name":    v.get("name", sid.replace("_", " ").title()),
                "score":   v.get("score", 50),
                "status":  v.get("status", "neutral"),
                "sector":  meta.get("sector", "Macro"),
                "lead":    meta.get("lead", "4–12 weeks"),
                "meaning": meta.get("meaning", ""),
            })
        return out

    top_bull_rich = _enrich(top_bull)
    top_bear_rich = _enrich(top_bear)
    near_flip_rich = _enrich(near_flip)

    # Sector bias aggregation
    sector_scores: dict[str, list[float]] = {}
    for sid, v in valid.items():
        sector = _SIG_META.get(sid, {}).get("sector", "Other")
        score  = v.get("score", 50)
        sector_scores.setdefault(sector, []).append(score)

    sector_bias: dict[str, str] = {}
    for sector, scores in sector_scores.items():
        avg = sum(scores) / len(scores)
        if avg >= 60:
            sector_bias[sector] = "BULLISH"
        elif avg <= 40:
            sector_bias[sector] = "BEARISH"
        else:
            sector_bias[sector] = "NEUTRAL"

    # Build summary sentences
    sentences: list[str] = []

    # Sentence 1: overall count + regime
    if regime in ("RISK-ON", "LEANING BULLISH"):
        sentences.append(
            f"{nb} of {nb + nr + nn} signals are green — the macro backdrop is "
            f"{'broadly' if bull_pct >= 0.65 else 'moderately'} constructive for risk assets."
        )
    elif regime in ("RISK-OFF", "LEANING BEARISH"):
        sentences.append(
            f"{nr} of {nb + nr + nn} signals are red — the macro data currently "
            f"{'strongly argues' if bear_pct >= 0.65 else 'leans'} against risk-taking."
        )
    else:
        sentences.append(
            f"Signals are divided: {nb} bullish, {nr} bearish, {nn} neutral. "
            f"No clear directional read — the data is genuinely mixed right now."
        )

    # Sentence 2: strongest signal
    if top_bull_rich:
        s = top_bull_rich[0]
        if s["meaning"]:
            sentences.append(
                f"Strongest tailwind: <b>{s['name']}</b> ({s['score']:.0f}/100) — "
                f"{s['meaning']} is accelerating, a signal that has historically "
                f"led {s['sector']} stocks by {s['lead']}."
            )
        else:
            sentences.append(
                f"Strongest bullish signal: <b>{s['name']}</b> at {s['score']:.0f}/100."
            )

    # Sentence 3: main risk or near-flip
    if top_bear_rich:
        s = top_bear_rich[0]
        if s["meaning"]:
            sentences.append(
                f"Main risk: <b>{s['name']}</b> ({s['score']:.0f}/100) — "
                f"{s['meaning']} is deteriorating, a pattern that has preceded "
                f"weakness in {s['sector']} by {s['lead']}."
            )
        else:
            sentences.append(
                f"Main bearish signal: <b>{s['name']}</b> at {s['score']:.0f}/100."
            )
    elif near_flip_rich:
        s = near_flip_rich[0]
        direction = "flipping bullish" if s["score"] > 50 else "flipping bearish"
        sentences.append(
            f"One to watch: <b>{s['name']}</b> ({s['score']:.0f}/100) is "
            f"approaching the threshold for {direction}."
        )

    summary = " ".join(sentences)

    # Watch note — the signal closest to flipping direction
    watch_note = ""
    if near_flip_rich:
        s = near_flip_rich[0]
        direction = "bullish" if s["score"] > 50 else "bearish"
        watch_note = (
            f"Watch <b>{s['name']}</b> — currently neutral at {s['score']:.0f}/100 "
            f"but approaching the {direction} threshold. A flip here would shift "
            f"the {s['sector']} signal alignment."
        )
    elif top_bear_rich and bull_pct >= 0.55:
        s = top_bear_rich[0]
        watch_note = (
            f"Despite the bullish overall read, <b>{s['name']}</b> ({s['score']:.0f}/100) "
            f"is the lone dissenting signal. Worth monitoring for any deterioration."
        )

    return {
        "headline":     f"Macro environment: {regime}",
        "regime":       regime,
        "regime_color": regime_color,
        "summary":      summary,
        "top_bull":     top_bull_rich,
        "top_bear":     top_bear_rich,
        "sector_bias":  sector_bias,
        "watch_note":   watch_note,
        "bull_count":   nb,
        "bear_count":   nr,
        "neut_count":   nn,
        "total":        nb + nr + nn,
    }


def _empty_narrative() -> dict:
    return {
        "headline":     "Macro environment: Loading…",
        "regime":       "LOADING",
        "regime_color": "#8B7355",
        "summary":      "Signal data is loading. Refresh in a moment.",
        "top_bull":     [],
        "top_bear":     [],
        "sector_bias":  {},
        "watch_note":   "",
        "bull_count":   0,
        "bear_count":   0,
        "neut_count":   0,
        "total":        0,
    }
