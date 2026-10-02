# utils/scenario.py
# Unstructured Alpha — scenario lab: "if these forces moved this much, what
# would this portfolio's history suggest?"
#
# WHAT IT DOES
# ------------
# Takes the weekly data a report already holds (report["series"]) and refits
# ONE joint regression: returns on the stock market, the five core forces, and
# every extra force the scenario moves. The scenario's estimated move is the
# sum of (coefficient x move) over the levers, and its 90% range comes from the
# full Newey-West covariance of those coefficients -- so correlated estimates
# (the 10-year and the 2-year, say) are not treated as independent.
#
# Each holding is refitted on exactly the same weeks and regressors, so the
# holdings' weighted contributions add up to the portfolio figure.
#
# WHAT IT IS NOT
# --------------
# A forecast. It is a conditional statement about the past: "in the last three
# years, weeks shaped like this went with moves like that". Every lever left at
# zero is held where it was. A scenario move is a cumulative move, applied
# through weekly sensitivities -- the standard assumption that they add up over
# a few months. A move larger than any 13-week move in the data is flagged as
# extrapolation: the estimate then assumes the sensitivity keeps scaling in a
# straight line beyond anything observed. Presets are hypothetical and say so.

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from utils import exposure as ex

MARKET = "market"
EXTRAPOLATION_WEEKS = 13   # "a few months": the yardstick a scenario move is compared to


@dataclass(frozen=True)
class Lever:
    key: str
    label: str
    group: str        # "market", "core", or an EXTRA_GROUPS key
    unit: str         # "%", "pp" (percentage points) or "pts" (index points: the VIX)
    sign: float       # the series' change per unit of the lever (the yen is quoted inverted)
    verb: str         # "rises", for "the 10-year yield rises 0.25 pp"


def _lever_for(f: ex.Factor) -> Lever:
    unit = "%" if f.transform == "pct" else "pts" if f.series_id == "VIXCLS" else "pp"
    return Lever(f.key, f.label, f.group, unit, 1.0 if f.shock > 0 else -1.0, "rises")


LEVERS: Dict[str, Lever] = {
    MARKET: Lever(MARKET, "Stock market (S&P 500)", "market", "%", 1.0, "moves"),
    **{f.key: _lever_for(f) for f in ex.FACTORS},
    **{f.key: _lever_for(f) for f in ex.EXTRA_FACTORS},
}
GROUP_TITLES = {"market": "The stock market", "core": "The core five", **ex.EXTRA_GROUPS}


@dataclass(frozen=True)
class Preset:
    key: str
    title: str
    blurb: str
    moves: Mapping[str, float]


# Hypothetical, round-number moves, each roughly the size of moves markets have
# made over a few months. They are illustrations to start from, not history and
# not predictions; the page says so.
PRESETS: tuple = (
    Preset("rates_up", "Rates up sharply",
           "Long and short Treasury yields rise a full point; mortgage rates follow.",
           {"rates": 1.0, "short_rates": 1.0, "mortgage": 1.0}),
    Preset("risk_off", "Risk-off selloff",
           "Stocks fall 15%, volatility jumps, credit spreads widen, gold and the dollar firm.",
           {MARKET: -15.0, "volatility": 15.0, "credit": 1.0, "gold": 5.0, "dollar": 3.0}),
    Preset("oil_spike", "Oil price spike",
           "Oil rises 30% and inflation expectations rise with it.",
           {"oil": 30.0, "inflation": 0.3, "natgas": 20.0}),
    Preset("growth_scare", "Growth scare",
           "Stocks fall 10%, yields fall, credit widens, oil and copper drop.",
           {MARKET: -10.0, "rates": -0.75, "credit": 0.75, "oil": -20.0, "copper": -10.0}),
    Preset("strong_dollar", "Strong dollar",
           "The dollar rises 5%; the euro and emerging markets fall behind.",
           {"dollar": 5.0, "euro": -5.0, "emerging": -5.0}),
)
PRESET_BY_KEY = {p.key: p for p in PRESETS}


def available(report: dict) -> bool:
    s = (report or {}).get("series") or {}
    return bool(s.get("weeks")) and bool(s.get("portfolio"))


def available_levers(report: dict) -> List[Lever]:
    s = report.get("series") or {}
    have = {MARKET} | set(s.get("core") or {}) | set(s.get("extras") or {})
    return [lv for k, lv in LEVERS.items() if k in have]


def _frame(report: dict, extra_keys: List[str]) -> pd.DataFrame:
    s = report["series"]
    cols = {"__portfolio__": s["portfolio"], MARKET: s["market"], **s["core"],
            **{k: s["extras"][k] for k in extra_keys},
            **{f"__h__{t}": v for t, v in s["holdings"].items()}}
    frame = pd.DataFrame(cols, index=pd.to_datetime(s["weeks"]), dtype=float)
    # Rebuilt from the holdings rather than read from the stored (rounded)
    # portfolio column, so holdings add up to the portfolio exactly.
    frame["__portfolio__"] = sum(frame[f"__h__{t}"] * w for t, w in s["weights"].items())
    return frame.dropna()   # a week a moved extra lacks is dropped, never filled


def _fit(frame: pd.DataFrame, ycol: str, regressors: List[str]):
    X = np.column_stack([np.ones(len(frame))] + [frame[c].to_numpy(dtype=float) for c in regressors])
    beta, cov, _ = ex.ols_newey_west_cov(frame[ycol].to_numpy(dtype=float), X)
    return beta[1:], cov[1:, 1:]


def run(report: dict, moves: Mapping[str, float]) -> dict:
    """The scenario's estimated move for the portfolio and each holding.

    moves: {lever key: amount in the lever's unit}. Zero or missing = held fixed.
    """
    if not available(report):
        return {"available": False, "reason": "This report was measured before scenarios "
                "existed; measure it again to use the scenario lab."}
    s = report["series"]
    core_keys = list(s["core"])
    moved = {k: float(v) for k, v in moves.items() if v}
    unknown = [k for k in moved if k not in LEVERS or k not in (MARKET, *core_keys, *s["extras"])]
    for k in unknown:
        moved.pop(k)
    extra_keys = [k for k in moved if k in s["extras"]]
    regressors = [MARKET] + core_keys + extra_keys
    frame = _frame(report, extra_keys)
    if len(frame) < ex.MIN_RECENT_WEEKS or len(frame) <= len(regressors) + 1:
        return {"available": False, "reason": f"only {len(frame)} weeks line up for these "
                "forces, too few to estimate them together."}

    # The move in each regressor's own units: the lever amount, signed for
    # series quoted the other way round (yen per dollar).
    shock = np.array([moved.get(k, 0.0) * LEVERS[k].sign for k in regressors])
    beta, cov = _fit(frame, "__portfolio__", regressors)
    impact = float(beta @ shock)
    se = float(math.sqrt(max(shock @ cov @ shock, 0.0)))

    contributions = []
    for i, k in enumerate(regressors):
        if not shock[i]:
            continue
        c_se = abs(shock[i]) * math.sqrt(max(cov[i, i], 0.0))
        # The largest 13-week move in the data, summed from weekly changes.
        largest = float(frame[k].rolling(EXTRAPOLATION_WEEKS).sum().abs().max())
        contributions.append({
            "key": k, "label": LEVERS[k].label, "amount": moved[k], "unit": LEVERS[k].unit,
            "impact": float(beta[i] * shock[i]), "low": float(beta[i] * shock[i] - ex.Z90 * c_se),
            "high": float(beta[i] * shock[i] + ex.Z90 * c_se),
            "extrapolated": abs(shock[i]) > largest, "largest_13w": largest,
        })
    contributions.sort(key=lambda c: -abs(c["impact"]))

    holdings = []
    for t, w in s["weights"].items():
        b_h, cov_h = _fit(frame, f"__h__{t}", regressors)
        h_impact = float(b_h @ shock)
        h_se = float(math.sqrt(max(shock @ cov_h @ shock, 0.0)))
        holdings.append({"ticker": t, "weight_pct": 100.0 * w, "impact": h_impact,
                         "low": h_impact - ex.Z90 * h_se, "high": h_impact + ex.Z90 * h_se,
                         "contribution": w * h_impact,
                         # The contribution's own range: the holding's, scaled by its weight.
                         "c_low": w * (h_impact - ex.Z90 * h_se),
                         "c_high": w * (h_impact + ex.Z90 * h_se)})
    holdings.sort(key=lambda h: h["contribution"])

    return {
        "available": True, "impact": impact, "se": se,
        "low": impact - ex.Z90 * se, "high": impact + ex.Z90 * se,
        "contributions": contributions, "holdings": holdings,
        "n_obs": int(len(frame)), "start": str(frame.index[0].date()),
        "end": str(frame.index[-1].date()),
        "extrapolated": any(c["extrapolated"] for c in contributions),
        "ignored": unknown, "moved": moved,
    }


def format_amount(v: float, unit: str) -> str:
    """Signed, with a true minus sign to match every other figure on the page."""
    text = (f"{v:+.0f}%" if unit == "%" else f"{v:+.0f} pts" if unit == "pts" else f"{v:+.2f} pp")
    return text.replace("-", "−")


# Slider bounds and step per kind of lever: (low, high, step).
def lever_range(lv: Lever) -> tuple:
    if lv.key == MARKET:
        return (-40.0, 40.0, 1.0)
    if lv.unit == "pts":
        return (-20.0, 40.0, 1.0)
    if lv.unit == "%":
        return (-50.0, 50.0, 1.0)
    if lv.group in ("styles", "global"):   # gaps between two funds' returns
        return (-20.0, 20.0, 1.0)
    return (-3.0, 3.0, 0.25)


def describe_moves(moved: Mapping[str, float]) -> str:
    """'the stock market moves −15%, credit spreads rise 1.00 pp' — for screen readers and copy."""
    parts = []
    for k, v in moved.items():
        lv = LEVERS[k]
        amount = format_amount(v, lv.unit)
        parts.append(f"{ex.lower_label(lv.label)} {amount}")
    return ", ".join(parts) if parts else "nothing moved"
