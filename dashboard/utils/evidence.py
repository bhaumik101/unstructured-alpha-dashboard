# utils/evidence.py
# Unstructured Alpha — did the exposure show up in real weeks? (the proof)
#
# A regression slope is an abstraction. This module answers the question a
# reader actually has -- "did this matter for my money?" -- from the same
# weekly data the report already holds (report["series"]):
#
#   * The big weeks. For each force, the weeks it moved most. In each, the
#     portfolio's move beyond the stock market and the other forces (what is
#     left after the joint fit's market and other-force terms) is compared
#     with the direction the reading implies. Shown
#     as a count ("lagged in 7 of the 8 biggest dollar jumps") and the average
#     dollar gap, so the reader sees the evidence instead of trusting a t-stat.
#
#   * Out of sample. The same reading is re-estimated on the earlier weeks
#     only, then tested on the later weeks it never saw: in the big weeks of
#     the later period, how often did the portfolio's beyond-market move point
#     the way the earlier estimate said? A coin flip scores 50%.
#
# RULES
#   * Past weeks only; nothing here is a forecast. The out-of-sample score
#     says how well a past estimate described later weeks, nothing more.
#   * A week with missing data is dropped, never filled.
#   * Too few weeks means no verdict: the panel says so instead of a number.

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence

import numpy as np

BIG_WEEKS = 8           # how many of a force's largest weeks to show
TEST_FRACTION = 1 / 3   # the later share of weeks held out for the out-of-sample test
MIN_TRAIN = 70          # weeks needed to estimate before testing
MIN_TEST_BIG = 6        # big weeks needed in the held-out period to score it
BIG_Z = 1.0             # a "big" week: the force moved more than one typical week


def _arr(xs: Sequence) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in xs], dtype=float)


def _ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    A = np.column_stack([np.ones(len(y)), X])
    return np.linalg.lstsq(A, y, rcond=None)[0]


def _frame(series: Mapping, keys: Sequence[str]):
    """Aligned arrays (portfolio, market, forces), complete weeks only."""
    y, m = _arr(series["portfolio"]), _arr(series["market"])
    F = np.column_stack([_arr(series["core"][k]) for k in keys]) if keys else np.empty((len(y), 0))
    ok = np.isfinite(y) & np.isfinite(m) & np.all(np.isfinite(F), axis=1)
    weeks = [w for w, keep in zip(series["weeks"], ok) if keep]
    return weeks, y[ok], m[ok], F[ok]


def big_weeks(series: Mapping, key: str, impact: float, keys: Sequence[str],
              n: int = BIG_WEEKS) -> Optional[dict]:
    """The force's `n` largest weeks (by size of move, either direction), with the
    portfolio's move beyond the market in each and whether it went the way the
    reading implies. The market adjustment uses the full-period beta from a joint
    fit, the same model as the report."""
    if key not in keys:
        return None
    weeks, y, m, F = _frame(series, keys)
    if len(y) < 30:
        return None
    j = list(keys).index(key)
    b = _ols(y, np.column_stack([m, F]))
    # The portfolio's move beyond the stock market and the other forces: the
    # same thing the reading measures. Big credit weeks are often big rate
    # weeks too; leaving the rate effect in would judge one force by another.
    others = [i for i in range(F.shape[1]) if i != j]
    beyond = y - b[0] - b[1] * m - (F[:, others] @ b[2:][others] if others else 0.0)
    f = F[:, j]
    sd = float(np.nanstd(f)) or 1.0
    top = np.argsort(-np.abs(f))[:n]
    top = top[np.argsort([weeks[i] for i in top])]    # in date order
    rows = []
    for i in top:
        implied = np.sign(impact * f[i])
        rows.append({"week": weeks[i], "move": round(float(f[i]), 3), "z": round(float(f[i] / sd), 1),
                     "beyond": round(float(beyond[i]), 3),
                     "agrees": bool(implied != 0 and np.sign(beyond[i]) == implied)})
    agree = sum(r["agrees"] for r in rows)
    # Average beyond-market move, signed so that "the way the reading implies" is positive.
    signed = [r["beyond"] * np.sign(impact * r["move"]) for r in rows]
    return {"rows": rows, "agree": agree, "n": len(rows),
            "avg_beyond_signed": round(float(np.mean(signed)), 3), "typical_move_sd": round(sd, 3)}


def out_of_sample(series: Mapping, key: str, keys: Sequence[str]) -> Optional[dict]:
    """Estimate on the earlier weeks, test on the later ones. Returns the earlier
    estimate, and in the later period's big weeks for this force how often the
    beyond-market move pointed the way that estimate said (hit rate), plus the
    correlation between what the earlier estimate implied and what happened."""
    if key not in keys:
        return None
    weeks, y, m, F = _frame(series, keys)
    n = len(y)
    cut = int(round(n * (1 - TEST_FRACTION)))
    if cut < MIN_TRAIN or n - cut < 26:
        return None
    j = list(keys).index(key)
    b = _ols(y[:cut], np.column_stack([m[:cut], F[:cut]]))
    slope = float(b[2 + j])
    yt, mt, Ft = y[cut:], m[cut:], F[cut:]
    others = [i for i in range(F.shape[1]) if i != j]
    # What happened beyond the market and the other forces, using only earlier-period coefficients.
    beyond = yt - b[0] - b[1] * mt - (Ft[:, others] @ b[2:][others] if others else 0.0)
    f = Ft[:, j]
    sd = float(np.std(F[:cut, j])) or 1.0
    big = np.abs(f) > BIG_Z * sd
    implied = slope * f
    if big.sum() < MIN_TEST_BIG:
        return {"available": False, "reason": "too few big weeks in the later period",
                "train_weeks": cut, "test_weeks": n - cut}
    hits = int(np.sum(np.sign(beyond[big]) == np.sign(implied[big])))
    corr = float(np.corrcoef(implied, beyond)[0, 1]) if np.std(implied) > 0 else 0.0
    return {"available": True, "train_from": weeks[0], "train_to": weeks[cut - 1],
            "test_from": weeks[cut], "test_to": weeks[-1], "train_weeks": cut, "test_weeks": n - cut,
            "slope_train": round(slope, 4), "big_weeks": int(big.sum()), "hits": hits,
            "hit_rate": round(hits / int(big.sum()), 3), "corr": round(corr, 3)}


def evidence(report: Mapping) -> Dict[str, dict]:
    """Per Clear or Tentative core reading: its big weeks and its out-of-sample test."""
    series = report.get("series") or {}
    readings = (report.get("portfolio") or {}).get("readings") or {}
    keys = [k for k in (series.get("core") or {}) if k in readings]
    out = {}
    for k in keys:
        r = readings[k]
        if r.get("evidence") not in ("clear", "tentative"):
            continue
        try:
            out[k] = {"big": big_weeks(series, k, r["impact"], keys), "oos": out_of_sample(series, k, keys)}
        except Exception:
            continue                                   # a failed check is left out, never estimated
    return out
