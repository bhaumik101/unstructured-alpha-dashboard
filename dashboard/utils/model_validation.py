# utils/model_validation.py
# Unstructured Alpha — Model Validation Center engine (Point 9)
#
# WHY THIS MODULE EXISTS: trust in a signal product is earned by showing your
# work — including where the work is weak. This module assembles, for EVERY
# signal, a transparent validation record from the platform's own config +
# (optionally) the real out-of-sample reliability pass in
# utils.validation_status.validate_all_macro_signals(). It deliberately does
# NOT flatten every signal to "validated": a tier-3 experimental gauge with 90
# days of history and a tier-1 core indicator formally in the Conference Board
# Leading Economic Indicators are shown as what they are — different weights,
# different confidence, different known limitations.
#
# Everything here is grounded: source, update frequency, lead-time, relative
# model weight, and category come straight from utils.config.SIGNALS; the
# confidence/validation labels derive transparently from tier + PCS, upgraded to
# the measured reliability score when the (expensive) validation pass has run.
# No field is invented, and none pretends more certainty than the inputs support.
#
# Pure functions (no Streamlit / no DB / no network) so the labelling logic is
# unit-testable against ground truth. The page (pages/11_Model_Validation.py)
# renders these records with st.dataframe + the small HTML helpers below.

from __future__ import annotations

from typing import Optional

from utils.config import SIGNALS, CATEGORIES

# tier → relative-weight label. Tiers come from config (24 tier-1, 22 tier-2,
# 1 tier-3 today) and already govern how much each signal counts.
_TIER = {
    1: {"weight": "Core",          "rank": 0},
    2: {"weight": "Supporting",    "rank": 1},
    3: {"weight": "Experimental",  "rank": 2},
}


def _tier_info(tier) -> dict:
    return _TIER.get(tier, _TIER[2])


def confidence_from(tier, pcs, reliability: Optional[dict] = None) -> tuple[str, str]:
    """
    (label, color). Prefer the MEASURED reliability score (0-100 from the
    out-of-sample validation pass) when available; otherwise derive a
    transparent, conservative label from tier + PCS (predictive-confidence
    score, 0-10). Never returns High without evidence for it.
    """
    if reliability and isinstance(reliability.get("score"), (int, float)) and reliability.get("score", 0) > 0:
        s = float(reliability["score"])
        if s >= 70:
            return ("High", "#00C853")
        if s >= 45:
            return ("Moderate", "#FF9800")
        return ("Limited", "#FF4444")
    p = float(pcs or 0)
    if tier == 1 and p >= 7:
        return ("Moderate", "#FF9800")   # tier-1 without a measured pass caps at Moderate — honest
    if tier == 3 or p < 4:
        return ("Limited", "#FF4444")
    return ("Moderate", "#FF9800") if (tier == 1 or p >= 6) else ("Limited", "#FF4444")


def validation_status_from(tier, reliability: Optional[dict] = None) -> str:
    if reliability and reliability.get("label") and not str(reliability["label"]).startswith("Insufficient"):
        return str(reliability["label"])
    if tier == 3:
        return "Experimental — insufficient history across regimes"
    return "Backtested (same-sample) — not yet out-of-sample validated"


def known_limitation(cfg: dict, tier) -> str:
    freq = (cfg.get("frequency") or "").lower()
    bits = []
    if freq in ("monthly", "quarterly"):
        bits.append(f"{freq} data — coarse, few observations per year")
    if tier == 3:
        bits.append("insufficient history across multiple market regimes")
    bits.append("lead-time varies by ticker and regime — not a guarantee")
    return "; ".join(bits)


def signal_validation_record(sig_id: str, cfg: dict, reliability: Optional[dict] = None) -> dict:
    """Assemble one signal's full transparency record (grounded in config)."""
    tier = cfg.get("tier", 2)
    pcs = cfg.get("pcs", 5)
    conf, conf_color = confidence_from(tier, pcs, reliability)
    cat = cfg.get("category", "macro")
    return {
        "id": sig_id,
        "name": cfg.get("name", sig_id),
        "category": cat,
        "category_name": (CATEGORIES.get(cat) or {}).get("name", cat.replace("_", " ").title()),
        "source": (cfg.get("source") or "").upper(),
        "source_url": cfg.get("source_url"),
        "series_id": cfg.get("series_id"),
        "frequency": cfg.get("frequency", ""),
        "lag_weeks": cfg.get("lag_weeks"),
        "weight_label": _tier_info(tier)["weight"],
        "tier": tier,
        "pcs": pcs,
        "confidence": conf,
        "confidence_color": conf_color,
        "validation_status": validation_status_from(tier, reliability),
        "experimental": (tier == 3) or (conf == "Limited"),
        "known_limitation": known_limitation(cfg, tier),
        "reliability_score": (reliability or {}).get("score"),
    }


def build_validation_table(signals: Optional[dict] = None,
                           reliabilities: Optional[dict] = None) -> list[dict]:
    """
    One record per signal, sorted Core → Supporting → Experimental, then by PCS.

    reliabilities: the dict returned by validate_all_macro_signals()
        ({sig_id: {"validation","pooled","reliability"}}), or None. When
        present, each signal's measured reliability upgrades its confidence.
    """
    signals = signals if signals is not None else SIGNALS
    reliabilities = reliabilities or {}
    recs = []
    for sid, cfg in signals.items():
        rel = None
        entry = reliabilities.get(sid)
        if isinstance(entry, dict):
            rel = entry.get("reliability") if "reliability" in entry else entry
        recs.append(signal_validation_record(sid, cfg, rel))
    recs.sort(key=lambda r: (_tier_info(r["tier"])["rank"], -(r["pcs"] or 0), r["name"]))
    return recs


def validation_summary(records: list[dict]) -> dict:
    """Honest headline counts — makes 'not all signals are equal' concrete."""
    n = len(records)
    return {
        "total": n,
        "core": sum(1 for r in records if r["weight_label"] == "Core"),
        "supporting": sum(1 for r in records if r["weight_label"] == "Supporting"),
        "experimental": sum(1 for r in records if r["experimental"]),
        "high_confidence": sum(1 for r in records if r["confidence"] == "High"),
        "moderate_confidence": sum(1 for r in records if r["confidence"] == "Moderate"),
        "limited_confidence": sum(1 for r in records if r["confidence"] == "Limited"),
        "measured": sum(1 for r in records if r.get("reliability_score")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Small render helpers (the page does the per-signal table with st.dataframe)
# ─────────────────────────────────────────────────────────────────────────────

def render_summary_html(summary: dict) -> str:
    s = summary
    def chip(label, val, color):
        return (f'<div style="background:#161A2B;border:1px solid #262C42;border-radius:8px;'
                f'padding:10px 14px;min-width:96px;">'
                f'<div style="font-size:var(--ua-text-xl);font-weight:800;color:{color};line-height:1;">{val}</div>'
                f'<div style="font-size:0.62rem;color:var(--ua-ink-mut);text-transform:uppercase;letter-spacing:0.05em;margin-top:3px;">{label}</div>'
                f'</div>')
    return (
        '<div style="background:var(--ua-panel);border:1px solid var(--ua-panel-line);border-radius:12px;'
        'padding:18px 20px;font-family:Inter,-apple-system,sans-serif;">'
        '<div style="font-size:1.05rem;font-weight:800;color:var(--ua-ink);">Model Validation Center</div>'
        '<div style="font-size:0.82rem;color:var(--ua-ink-mut);margin-top:4px;max-width:680px;line-height:1.6;">'
        'Every signal, shown as what it actually is — its data source, update cadence, relative weight, '
        'confidence, validation status, and known limitations. We do <b>not</b> pretend every signal is '
        'equally strong. Transparency is the point.</div>'
        '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;">'
        f'{chip("Signals", s["total"], "#E8EEFF")}'
        f'{chip("Core", s["core"], "#00C853")}'
        f'{chip("Supporting", s["supporting"], "#00C8E0")}'
        f'{chip("Experimental", s["experimental"], "#FF9800")}'
        f'{chip("Limited conf.", s["limited_confidence"], "#FF6B6B")}'
        '</div></div>'
    )


def render_composites_html(composites: list[dict]) -> str:
    """Render the honest composite-model status (Confluence/Supercycle etc.)."""
    if not composites:
        return ""
    rows = []
    for c in composites:
        status = c.get("status", "")
        color = "#FF9800" if "NOT" in status.upper() else "#00C8E0"
        rows.append(
            f'<div style="border-left:3px solid {color};padding:10px 0 10px 14px;margin-top:12px;">'
            f'<div style="font-size:0.9rem;font-weight:700;color:var(--ua-ink);">{c.get("category","")}</div>'
            f'<div style="font-size:0.74rem;color:{color};font-weight:600;margin:2px 0 4px;">{status}</div>'
            f'<div style="font-size:0.76rem;color:var(--ua-ink-mut);line-height:1.6;">{c.get("detail","")}</div>'
            f'<div style="font-size:0.66rem;color:#4A5568;margin-top:4px;">Source: {c.get("source","")}</div>'
            f'</div>'
        )
    return (
        '<div style="background:var(--ua-panel);border:1px solid var(--ua-panel-line);border-radius:12px;'
        'padding:18px 20px;font-family:Inter,-apple-system,sans-serif;">'
        '<div style="font-size:0.95rem;font-weight:800;color:var(--ua-ink);">Composite models — validation status</div>'
        '<div style="font-size:0.76rem;color:var(--ua-ink-mut);margin-top:2px;">The scores built ON TOP of the signals, '
        'and exactly how far each one has (and hasn\'t) been validated.</div>'
        f'{"".join(rows)}</div>'
    )
