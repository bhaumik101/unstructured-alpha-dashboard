"""The Conviction Curve — a lead-time term structure of macro conviction.

Standard confluence collapses every signal to "bullish today". But each signal
carries a researched LEAD TIME (config lag_weeks): the weeks by which its reading
has historically preceded price. Filing each signal's CURRENT reading into the
future week it has historically influenced, then aggregating, produces a forward
profile — "macro support builds through ~week 6, then fades" — i.e. a WHEN, not
just an IF. This is the object described in the Conviction Curve working paper.

Honesty is load-bearing here, so it is built into the code, not just the label:
- Sign-restricted (Campbell-Thompson): a signal votes only in the direction its
  reading implies; a neutral reading contributes ~0.
- De-correlated confidence (reuses utils.signal_independence): a horizon bucket
  filled by three signals that all proxy risk appetite is ONE independent read,
  not three — so each bucket reports effective independent signals, and a bucket
  backed by correlated signals is flagged low-confidence.
- It is a RESEARCH PREVIEW. Per the paper, this cannot be marketed as validated
  until point-in-time vintages and a purged walk-forward exist. `DISCLAIMER`
  below must travel with every rendering. It is directional context, never a
  forecast or a trade trigger.
"""

from __future__ import annotations

from dataclasses import dataclass, field

try:
    from utils.config import SIGNALS
except Exception:  # pragma: no cover
    SIGNALS = {}

DISCLAIMER = (
    "Research preview — directional macro context, not a validated forecast. "
    "Each signal's current reading is projected to its historical lead time; "
    "this is not yet out-of-sample tested and must not be used as a trade trigger."
)

# Horizon buckets (weeks), aligned to the real lead-time distribution of the
# signal library (mode ~4w, spread 0-52w). Each is (label, lo_inclusive, hi_inclusive).
BUCKETS: list[tuple[str, int, int]] = [
    ("~1 wk", 0, 1),
    ("2-3 wk", 2, 3),
    ("4-5 wk", 4, 5),
    ("6-8 wk", 6, 8),
    ("9-13 wk", 9, 13),
    ("14 wk+", 14, 10_000),
]


def _bucket_index(lead_weeks) -> int:
    try:
        w = float(lead_weeks)
    except (TypeError, ValueError):
        return 2  # default to the modal ~4-5wk bucket for unknown leads
    for i, (_lbl, lo, hi) in enumerate(BUCKETS):
        if lo <= w <= hi:
            return i
    return len(BUCKETS) - 1


def _signed_strength(sd: dict) -> float:
    """Signal's directional vote in [-1, 1]. Sign-restricted: driven by the
    reading's distance from neutral (50), so a ~neutral reading contributes ~0."""
    try:
        score = float(sd.get("score", 50))
    except (TypeError, ValueError):
        return 0.0
    s = (score - 50.0) / 50.0
    return max(-1.0, min(1.0, s))


def _direction(conv: float) -> str:
    if conv >= 0.15:
        return "bullish"
    if conv <= -0.15:
        return "bearish"
    return "neutral"


@dataclass(frozen=True)
class CurvePoint:
    label: str
    weeks_lo: int
    weeks_hi: int
    conviction: float          # mean signed strength in [-1, 1]
    direction: str             # bullish | bearish | neutral
    n_signals: int
    effective_signals: float   # de-correlated independent count
    signals: tuple = field(default=())


@dataclass(frozen=True)
class ConvictionCurve:
    points: tuple
    peak_label: str | None
    peak_direction: str | None
    trend: str                 # "front-loaded" | "building" | "flat"
    disclaimer: str = DISCLAIMER

    @property
    def has_signal(self) -> bool:
        return any(p.n_signals > 0 for p in self.points)


def conviction_curve(signal_scores: dict, sig_ids=None) -> ConvictionCurve:
    """Build the forward conviction curve for a ticker.

    signal_scores: {sig_id -> {"score": float, "status": ...}} (as compute_full
    ticker score produces). sig_ids: the signals relevant to this ticker; if
    None, uses every scored signal. Errored signals are excluded.
    """
    from utils.signal_independence import effective_signal_count

    scores = signal_scores or {}
    ids = list(sig_ids) if sig_ids is not None else list(scores.keys())

    buckets: list[list[tuple[str, float]]] = [[] for _ in BUCKETS]
    for sid in ids:
        sd = scores.get(sid)
        if not isinstance(sd, dict) or sd.get("error"):
            continue
        lead = SIGNALS.get(sid, {}).get("lag_weeks", 4)
        buckets[_bucket_index(lead)].append((sid, _signed_strength(sd)))

    points: list[CurvePoint] = []
    for (label, lo, hi), members in zip(BUCKETS, buckets):
        n = len(members)
        if n == 0:
            points.append(CurvePoint(label, lo, hi, 0.0, "neutral", 0, 0.0, ()))
            continue
        conv = sum(s for _, s in members) / n
        eff = effective_signal_count([sid for sid, _ in members])
        points.append(CurvePoint(
            label, lo, hi, round(conv, 3), _direction(conv),
            n, round(eff, 2), tuple(sid for sid, _ in members),
        ))

    # Peak = horizon with the strongest EVIDENCE-WEIGHTED directional lean, so a
    # bucket driven by one lone correlated signal can't be called the peak.
    scored = [p for p in points if p.n_signals > 0]
    peak = max(
        scored,
        key=lambda p: abs(p.conviction) * min(p.effective_signals, 3.0),
        default=None,
    )

    # Trend: is macro support front-loaded (near-term, already peaking) or still
    # building further out? Compare evidence-weighted near vs far conviction.
    def _weighted(ps):
        num = sum(p.conviction * p.effective_signals for p in ps)
        den = sum(p.effective_signals for p in ps)
        return num / den if den else 0.0

    near = _weighted(points[:3])   # <= ~5 weeks
    far = _weighted(points[3:])    # 6 weeks +
    if abs(near) < 0.1 and abs(far) < 0.1:
        trend = "flat"
    elif abs(near) >= abs(far) + 0.08:
        trend = "front-loaded"
    elif abs(far) >= abs(near) + 0.08:
        trend = "building"
    else:
        trend = "flat"

    return ConvictionCurve(
        points=tuple(points),
        peak_label=peak.label if peak else None,
        peak_direction=peak.direction if peak else None,
        trend=trend,
    )


def summary_sentence(curve: ConvictionCurve) -> str:
    """One honest plain-English line for the UI."""
    if not curve.has_signal:
        return "No macro signals map to this ticker's horizon buckets yet."
    if curve.peak_label is None or curve.peak_direction == "neutral":
        return "Macro support is mixed across horizons — no clear directional peak."
    trend_txt = {
        "front-loaded": "concentrated near-term and likely fading further out",
        "building": "still building at longer horizons",
        "flat": "roughly steady across horizons",
    }[curve.trend]
    return (
        f"Macro support reads strongest {curve.peak_direction} around "
        f"{curve.peak_label}, {trend_txt}."
    )
