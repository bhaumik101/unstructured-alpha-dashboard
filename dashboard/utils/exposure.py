# utils/exposure.py
# Unstructured Alpha — portfolio exposure to economic forces
#
# WHAT THIS MEASURES
# ------------------
# How a portfolio's weekly returns have moved alongside weekly changes in five
# economic forces — interest rates, inflation expectations, the U.S. dollar,
# oil, and credit spreads — after accounting for the overall stock market.
# Economic growth is measured separately, on monthly data, and is always
# labelled limited evidence.
#
# WHAT IT DOES NOT MEASURE
# ------------------------
# The future. Every number here is a historical sensitivity: "when rates rose,
# this portfolio has typically moved X%". Relationships change, and this module
# never phrases a result as what will happen. docs/NOWCAST_RESULTS.md records
# why: every predictive configuration tested on this data failed.
#
# DESIGN CHOICES, EACH MADE BEFORE LOOKING AT ANY PORTFOLIO RESULT
# ----------------------------------------------------------------
# * Weekly, not daily, returns. FRED rates and oil settle at different times of
#   day than equity closes; a weekly Friday-to-Friday change removes most of
#   that asynchronous noise.
# * Three years (156 weeks), minimum two (104). Long enough to hold a cycle of
#   rate moves, short enough to describe the portfolio as it behaves now.
# * The stock market (SPY) is always in the regression. Without it, "rate
#   exposure" is mostly general market exposure in disguise, because rates and
#   stocks move together in many weeks.
# * Newey-West standard errors (4 lags), because weekly returns are not quite
#   independent and ordinary errors would overstate certainty.
# * Evidence labels are Bonferroni-corrected across the five factors. "Clear"
#   needs |t| >= 2.576 (a 1% two-sided test, i.e. 5% shared across five), so
#   testing five things at once cannot manufacture a finding.
# * The Baa corporate spread (BAA10Y), not the high-yield OAS: FRED licenses
#   only ~3 years of the ICE high-yield series, which cannot fill a 3-year
#   window reliably. BAA10Y has decades of daily history.
# * A failed data series is EXCLUDED and named, never filled in.
# * MORE FORCES (EXTRA_FACTORS) are a second layer, not part of the core model.
#   Each is fitted on its own: returns ~ market + the five core forces + that
#   one force, on the same weeks. So an extra reading means "beyond what the
#   market and the core five already explain", the core readings are exactly
#   what they were before any extra existed, and stored history stays
#   comparable. The extras' Bonferroni bar is shared across every force tested,
#   core and extra: an extra always needs more than a core force to be called
#   Clear, and adding forces makes each one harder, never easier.
#
# The engine is pure: data arrives through injected fetchers, so every claim
# in it is tested on synthetic data where the true exposure is known.

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Mapping, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Factor:
    """One economic force, with the size of move used to express exposure."""
    key: str
    label: str
    series_id: str
    transform: str        # "diff" = change in percentage points; "pct" = percent change
    shock: float          # the move a reading is expressed per, in `transform` units
    shock_phrase: str     # plain English for that move
    why: str              # why an investor would care, one sentence
    group: str = "core"   # "core", or the EXTRA_GROUPS key it is listed under


FACTORS: tuple[Factor, ...] = (
    Factor("rates", "Interest rates", "DGS10", "diff", 0.25,
           "the 10-year Treasury yield rose 0.25 percentage points",
           "Rising rates lower the value of bonds and of companies valued on distant profits."),
    Factor("inflation", "Inflation expectations", "T10YIE", "diff", 0.25,
           "10-year inflation expectations rose 0.25 percentage points",
           "Inflation erodes fixed payments and changes which businesses keep their margins."),
    Factor("dollar", "U.S. dollar", "DTWEXBGS", "pct", 2.0,
           "the trade-weighted U.S. dollar rose 2%",
           "A stronger dollar shrinks the value of overseas revenue and foreign assets."),
    Factor("oil", "Oil and energy", "DCOILWTICO", "pct", 10.0,
           "the price of oil rose 10%",
           "Oil is a revenue source for producers and a cost for nearly everyone else."),
    Factor("credit", "Credit spreads", "BAA10Y", "diff", 0.25,
           "corporate credit spreads widened 0.25 percentage points",
           "Wider spreads mean lenders demand more to fund companies, often during stress."),
)

GROWTH_FACTOR = Factor(
    "growth", "Economic growth", "INDPRO", "pct", 1.0,
    "U.S. industrial production grew 1%",
    "Growth drives company earnings, but it is only published monthly, so evidence is thin.",
)

# ── more forces: a second layer, measured beyond the core five ──────────────
# Groups are added one at a time, each after its own review. Order is display
# order. A new force must say in `why` what it measures beyond the core: most
# of these move with a core force, and the reading is only the part that
# doesn't.
EXTRA_GROUPS: Dict[str, str] = {
    "markets": "Markets and rates",
}

EXTRA_FACTORS: tuple[Factor, ...] = (
    Factor("short_rates", "Short-term rates", "DGS2", "diff", 0.25,
           "the 2-year Treasury yield rose 0.25 percentage points",
           "The 2-year yield tracks where the Federal Reserve is expected to set rates. "
           "Measured with the 10-year yield held fixed, it is the front of the yield curve "
           "moving on its own.", group="markets"),
    Factor("volatility", "Market volatility", "VIXCLS", "diff", 5.0,
           "market volatility (the VIX) rose 5 points",
           "The VIX measures how much the stock market is expected to swing. Measured beyond "
           "the market's own move, it is how a holding behaves when fear rises.",
           group="markets"),
    Factor("mortgage", "Mortgage rates", "MORTGAGE30US", "diff", 0.25,
           "the 30-year mortgage rate rose 0.25 percentage points",
           "Mortgage rates set the cost of buying a home. Measured with the 10-year yield "
           "held fixed, it is the extra that lenders charge homebuyers moving on its own.",
           group="markets"),
)

MARKET_TICKER = "SPY"

WINDOW_WEEKS = 156
MIN_WEEKS = 104
RECENT_WEEKS = 52          # "what changed": the latest year...
MIN_RECENT_WEEKS = 40
EARLIER_WEEKS = 104        # ...against the two years before it (no overlap)
RECENT_MOVE_WEEKS = 4      # "what happened lately": the last four weeks
# "How it has moved": the sensitivity re-measured over a rolling year, stepped
# monthly. A year is short enough to show drift and long enough that a single
# point is not mostly noise; each point still carries its own 90% range, and
# the evidence bar is the same Bonferroni one the headline reading uses.
ROLLING_WEEKS = 52
ROLLING_STEP = 4
MIN_ROLLING_WEEKS = 40
NEWEY_WEST_LAGS = 4
GROWTH_WINDOW_MONTHS = 36
GROWTH_MIN_MONTHS = 24
# Raised from 25 on 2026-09-24: see utils/guards.MAX_EXPOSURE_HOLDINGS for the
# timing that justifies it. Env-overridable, so a smaller box can lower it
# without a deploy.
from utils.guards import MAX_EXPOSURE_HOLDINGS as MAX_HOLDINGS  # noqa: E402
VIF_WARN = 5.0

# Written out rather than computed, so a page that only renders a report does
# not import scipy (~390ms per process) for two numbers that never change.
# tests/test_exposure.py asserts they still equal scipy's values exactly.
Z90 = 1.644853626951472          # normal 95th percentile: the 90% range
CLEAR_T = 2.5758293035489004  # 5% shared across the five factors (Bonferroni)


def _bonferroni_t(n_tests: int, alpha: float = 0.05) -> float:
    """Two-sided |t| bar with alpha shared across n_tests. Stdlib, not scipy."""
    from statistics import NormalDist
    return NormalDist().inv_cdf(1.0 - alpha / (2.0 * max(1, n_tests)))


# The extras' bar: 5% shared across EVERY force tested, core and extra. So an
# extra always needs more than a core force to be called Clear, and the bar
# tightens as groups are added -- more forces tested must not mean more
# findings by chance. The core keeps its own five-force bar (CLEAR_T), so its
# readings and stored history are unchanged.
EXTRA_CLEAR_T = _bonferroni_t(len(FACTORS) + len(EXTRA_FACTORS))
CORE_CONTROL = "the stock market and the five core forces"

EVIDENCE_LABELS = {
    "clear": "Clear",
    "tentative": "Tentative",
    "indistinct": "Not distinguishable from zero",
    "not_enough_data": "Not enough data",
}

EVIDENCE_EXPLAINED = {
    "clear": "Strong enough to hold up even after allowing for testing five factors at once.",
    "tentative": "Suggestive, but could plausibly be noise. Worth watching, not relying on.",
    "indistinct": "The measured relationship is within the range of random noise.",
    "not_enough_data": "Not enough price history to measure this reliably.",
}

SAMPLE_PORTFOLIOS: Dict[str, List[dict]] = {
    "Balanced ETF portfolio": [
        {"ticker": "VTI", "weight_pct": 40}, {"ticker": "VXUS", "weight_pct": 20},
        {"ticker": "BND", "weight_pct": 30}, {"ticker": "TIP", "weight_pct": 5},
        {"ticker": "GLD", "weight_pct": 5},
    ],
    "Retirement income": [
        {"ticker": "SCHD", "weight_pct": 25}, {"ticker": "VIG", "weight_pct": 15},
        {"ticker": "BND", "weight_pct": 25}, {"ticker": "TLT", "weight_pct": 10},
        {"ticker": "XLU", "weight_pct": 15}, {"ticker": "VNQ", "weight_pct": 10},
    ],
    "Concentrated growth stocks": [
        {"ticker": "NVDA", "weight_pct": 20}, {"ticker": "MSFT", "weight_pct": 20},
        {"ticker": "AMZN", "weight_pct": 15}, {"ticker": "GOOGL", "weight_pct": 15},
        {"ticker": "META", "weight_pct": 15}, {"ticker": "TSLA", "weight_pct": 15},
    ],
}


# ── transforms ──────────────────────────────────────────────────────────────

def _clean(series: Optional[pd.Series]) -> pd.Series:
    if series is None or len(series) == 0:
        # Keep a DatetimeIndex even when empty, so date filters stay valid.
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    s = pd.to_numeric(pd.Series(series), errors="coerce")
    idx = pd.DatetimeIndex(pd.to_datetime(s.index))
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    s.index = idx
    return s[np.isfinite(s)].sort_index()


def _resample_last(s: pd.Series, rule: str) -> pd.Series:
    if s.empty:
        return s
    try:
        return s.resample(rule).last().dropna()
    except ValueError:  # pandas < 2.2 spells month-end "M"
        return s.resample("M" if rule == "ME" else rule).last().dropna()


def _pct(s: pd.Series) -> pd.Series:
    s = s[s > 0]
    out = s.pct_change() * 100.0
    return out.replace([np.inf, -np.inf], np.nan).dropna()


def to_weekly_returns(prices: Optional[pd.Series]) -> pd.Series:
    """Friday-to-Friday percent returns from a daily price series."""
    return _pct(_resample_last(_clean(prices), "W-FRI"))


def to_monthly_returns(prices: Optional[pd.Series]) -> pd.Series:
    return _pct(_resample_last(_clean(prices), "ME"))


def to_changes(levels: Optional[pd.Series], transform: str, rule: str = "W-FRI") -> pd.Series:
    """Weekly (or monthly) change in an economic series.

    Percent transforms drop non-positive levels first: WTI settled at -$37 on
    2020-04-20, and a percent change through a negative price is meaningless,
    not a large number.
    """
    s = _resample_last(_clean(levels), rule)
    if transform == "pct":
        return _pct(s)
    return s.diff().dropna()


# ── the regression ──────────────────────────────────────────────────────────

def _ols_newey_west(y: np.ndarray, X: np.ndarray, lags: int = NEWEY_WEST_LAGS):
    n, k = X.shape
    if n <= k:
        raise ValueError("more regressors than observations")
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ (X.T @ y)
    resid = y - X @ beta
    u = X * resid[:, None]
    s = u.T @ u
    for lag in range(1, min(lags, n - 1) + 1):
        w = 1.0 - lag / (lags + 1.0)
        g = u[lag:].T @ u[:-lag]
        s += w * (g + g.T)
    cov = xtx_inv @ s @ xtx_inv * (n / (n - k))
    se = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float(resid @ resid) / ss_tot if ss_tot > 0 else float("nan")
    return beta, se, r2


def _vifs(values: np.ndarray) -> np.ndarray:
    """Variance inflation factor per column: how much of it the others explain."""
    if values.shape[1] < 2:
        return np.ones(values.shape[1])
    corr = np.corrcoef(values, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0)
    return np.clip(np.diag(np.linalg.pinv(corr)), 1.0, None)


def evidence_for(t: float, n_obs: int, min_obs: int = MIN_WEEKS,
                 clear_t: float = CLEAR_T) -> str:
    if n_obs < min_obs or t is None or not math.isfinite(t):
        return "not_enough_data"
    if abs(t) >= clear_t:
        return "clear"
    if abs(t) >= Z90:
        return "tentative"
    return "indistinct"


def lower_label(label: str) -> str:
    """Lower-case a factor label for use mid-sentence, keeping "U.S." intact."""
    return label if label.startswith("U.S.") else label[:1].lower() + label[1:]


def _fmt(x: float) -> str:
    """Signed percent with a true minus sign; never prints a negative zero."""
    digits = 1 if abs(x) >= 0.95 else 2
    if round(x, digits) == 0:
        return f"{0:.{digits}f}%"
    return f"{'+' if x > 0 else '−'}{abs(x):.{digits}f}%"


def _sentence(f: Factor, impact: float, low: float, high: float, evidence: str,
              subject: str = "this portfolio", period: str = "weeks",
              control: str = "the overall stock market") -> str:
    if evidence == "not_enough_data":
        return f"There isn't enough history to measure exposure to {lower_label(f.label)}."
    if evidence == "indistinct":
        return (f"No measurable link to {lower_label(f.label)}: in {period} when {f.shock_phrase}, "
                f"{subject}'s typical move of {_fmt(impact)} sat inside its range of "
                f"uncertainty ({_fmt(low)} to {_fmt(high)}).")
    text = (f"In {period} when {f.shock_phrase}, {subject} has typically moved {_fmt(impact)} "
            f"(90% range {_fmt(low)} to {_fmt(high)}), after accounting for {control}.")
    if evidence == "tentative":
        text += " The evidence is tentative."
    return text


def _fit_on_frame(frame: pd.DataFrame, ycol: str, factors: Iterable[Factor],
                  min_obs: int, clear_t: float = CLEAR_T,
                  subject: str = "this portfolio", period: str = "weeks",
                  control: str = "the overall stock market") -> dict:
    by_key = {f.key: f for f in factors}
    keys = [k for k in by_key if k in frame.columns]
    n = int(len(frame))
    base = {"available": False, "n_obs": n, "readings": {}}
    if not keys:
        return {**base, "reason": "no economic data series were available"}
    if n < min_obs:
        return {**base, "reason": f"only {n} aligned observations; {min_obs} are needed"}

    cols = ["__mkt__"] + keys
    values = frame[cols].to_numpy(dtype=float)
    X = np.column_stack([np.ones(n), values])
    y = frame[ycol].to_numpy(dtype=float)
    beta, se, r2 = _ols_newey_west(y, X)
    vif = _vifs(values)
    corr = frame[keys].corr() if len(keys) > 1 else None

    readings: Dict[str, dict] = {}
    for i, key in enumerate(keys):
        f = by_key[key]
        b, s = float(beta[i + 2]), float(se[i + 2])
        t = b / s if s > 0 else float("nan")
        impact = b * f.shock
        se_impact = s * abs(f.shock)
        low, high = impact - Z90 * se_impact, impact + Z90 * se_impact
        ev = evidence_for(t, n, min_obs, clear_t)
        factor_vif = float(vif[i + 1])
        partner = None
        if factor_vif > VIF_WARN and corr is not None:
            partner = by_key[corr[key].drop(key).abs().idxmax()].label
        readings[key] = {
            "key": key, "label": f.label, "why": f.why, "shock_phrase": f.shock_phrase,
            "impact": impact, "low": low, "high": high, "se_impact": se_impact,
            "t": t, "n_obs": n, "evidence": ev, "evidence_label": EVIDENCE_LABELS[ev],
            "vif": factor_vif, "hard_to_separate_from": partner,
            "sentence": _sentence(f, impact, low, high, ev, subject, period, control),
        }

    return {
        "available": True, "n_obs": n,
        "start": str(frame.index[0].date()), "end": str(frame.index[-1].date()),
        "r2": r2, "market_beta": float(beta[1]), "readings": readings,
    }


def _align(y: pd.Series, market: pd.Series, changes: Mapping[str, pd.Series]) -> pd.DataFrame:
    parts = {"__y__": y, "__mkt__": market, **{k: v for k, v in changes.items()}}
    return pd.concat(parts, axis=1).dropna()


def fit_exposure(returns: pd.Series, market: pd.Series, factor_changes: Mapping[str, pd.Series],
                 *, factors: Iterable[Factor] = FACTORS, window: int = WINDOW_WEEKS,
                 min_obs: int = MIN_WEEKS, clear_t: float = CLEAR_T) -> dict:
    """Exposure of one weekly return series to each factor, market-controlled."""
    frame = _align(returns, market, factor_changes).iloc[-window:]
    return _fit_on_frame(frame, "__y__", factors, min_obs, clear_t)


def fit_extras(frame: pd.DataFrame, ycol: str, core: Iterable[Factor],
               extra_changes: Mapping[str, pd.Series], subject: str = "this portfolio",
               extras: Iterable[Factor] = None) -> Dict[str, dict]:
    """One reading per extra force, each beyond the market and the core forces.

    `frame` is the core model's frame (already aligned, no gaps). Each extra is
    joined onto it and fitted in its own regression, so one extra never
    changes another's reading, and the core readings are untouched.
    """
    core = tuple(core)
    out: Dict[str, dict] = {}
    for f in (EXTRA_FACTORS if extras is None else extras):
        ch = extra_changes.get(f.key)
        if ch is None or ch.empty:
            continue
        fx = frame.join(ch.rename(f.key), how="inner").dropna()
        fit = _fit_on_frame(fx, ycol, core + (f,), MIN_WEEKS, EXTRA_CLEAR_T, subject,
                            control=CORE_CONTROL)
        reading = fit["readings"].get(f.key)
        if reading:
            out[f.key] = dict(reading, group=f.group)
    return out


# ── the report ──────────────────────────────────────────────────────────────

def normalize_positions(holdings: Iterable[dict], max_holdings: int = MAX_HOLDINGS):
    """Clean user holdings into positive weights summing to 100. Returns (positions, notes)."""
    notes: List[str] = []
    merged: Dict[str, Optional[float]] = {}
    duplicates, skipped = set(), []
    for row in holdings or []:
        ticker = str((row or {}).get("ticker") or "").upper().strip().lstrip("$")
        if not ticker:
            continue
        raw = row.get("weight_pct", row.get("weight"))
        try:
            weight = float(str(raw).rstrip("%")) if raw not in (None, "") else None
        except ValueError:
            weight = None
        if weight is not None and (not math.isfinite(weight) or weight <= 0):
            skipped.append(ticker)
            continue
        if ticker in merged:
            duplicates.add(ticker)
            prior = merged[ticker]
            merged[ticker] = (prior or 0) + (weight or 0) if (prior or weight) else None
        else:
            merged[ticker] = weight

    if skipped:
        notes.append(f"Skipped {', '.join(skipped)}: zero or negative weights "
                     f"(short positions) aren't supported yet.")
    if duplicates:
        notes.append(f"Combined repeated entries for {', '.join(sorted(duplicates))}.")
    if not merged:
        return [], notes

    specified = [w for w in merged.values() if w]
    if not specified:
        notes.append("No weights were given, so every holding counts equally.")
    fill = (sum(specified) / len(specified)) if specified else 1.0
    positions = [{"ticker": t, "weight": (w or fill)} for t, w in merged.items()]
    if len(positions) > max_holdings:
        positions = sorted(positions, key=lambda p: -p["weight"])[:max_holdings]
        notes.append(f"Only the {max_holdings} largest holdings are measured.")
    total = sum(p["weight"] for p in positions)
    return [{"ticker": p["ticker"], "weight_pct": 100.0 * p["weight"] / total}
            for p in positions], notes


def _error(message: str, **extra) -> dict:
    return {"status": "error", "message": message, **extra}


def _shifts(recent: dict, earlier: dict) -> List[dict]:
    """Recent year vs the two years before. Non-overlapping, so errors combine."""
    out = []
    if not (recent.get("available") and earlier.get("available")):
        return out
    for key, now in recent["readings"].items():
        then = earlier["readings"].get(key)
        if not then:
            continue
        diff = now["impact"] - then["impact"]
        se = math.hypot(now["se_impact"], then["se_impact"])
        significant = se > 0 and abs(diff) >= Z90 * se
        if significant:
            direction = "stronger" if abs(now["impact"]) > abs(then["impact"]) else "weaker"
            sentence = (f"{now['label']} sensitivity has been {direction} over the past year: "
                        f"{_fmt(now['impact'])} versus {_fmt(then['impact'])} in the two years "
                        f"before. The difference is larger than the combined uncertainty.")
        else:
            sentence = (f"No measurable change in {lower_label(now['label'])} sensitivity between "
                        f"the past year and the two years before.")
        out.append({"key": key, "label": now["label"], "recent": now["impact"],
                    "earlier": then["impact"], "difference": diff, "se": se,
                    "significant": significant, "sentence": sentence})
    return out


def _recent_moves(frame: pd.DataFrame, fit: dict, factors: Iterable[Factor]) -> dict:
    """What moved in the last few weeks, and how much of the portfolio's move
    lines up with its measured sensitivities. Backward-looking attribution."""
    tail = frame.iloc[-RECENT_MOVE_WEEKS:]
    if tail.empty or not fit.get("available"):
        return {"available": False}
    by_key = {f.key: f for f in factors}
    growth = float(np.prod(1 + tail["__portfolio__"] / 100.0) - 1) * 100.0
    rows = []
    for key, r in fit["readings"].items():
        f = by_key[key]
        if f.transform == "pct":
            move = float(np.prod(1 + tail[key] / 100.0) - 1) * 100.0
            move_text = f"{move:+.1f}%"
        else:
            move = float(tail[key].sum())
            move_text = f"{move:+.2f} percentage points"
        per_unit = r["impact"] / f.shock
        attributed = per_unit * move
        attributed_se = r["se_impact"] / abs(f.shock) * abs(move)
        rows.append({"key": key, "label": r["label"], "move": move, "move_text": move_text,
                     "attributed": attributed, "attributed_se": attributed_se,
                     "counts": r["evidence"] in ("clear", "tentative")})
    return {"available": True, "weeks": int(len(tail)),
            "start": str(tail.index[0].date()), "end": str(tail.index[-1].date()),
            "portfolio_return": growth, "moves": rows}


def _rolling(frame: pd.DataFrame, factors: Iterable[Factor]) -> Dict[str, List[dict]]:
    """Each factor's sensitivity, re-measured over a rolling year.

    The headline reading answers "what is this portfolio exposed to"; this
    answers "how has that been moving", which is the other half of what the
    product says it does. Every point is a full fit with its own range and
    evidence label -- a rolling line drawn without its uncertainty would make
    a year of noise look like a trend.
    """
    factors = tuple(factors)
    n = len(frame)
    out: Dict[str, List[dict]] = {f.key: [] for f in factors if f.key in frame.columns}
    if n < ROLLING_WEEKS or not out:
        return {}
    ends = list(range(ROLLING_WEEKS, n + 1, ROLLING_STEP))
    if ends[-1] != n:
        ends.append(n)                     # the last point is always "now"
    for end in ends:
        window = frame.iloc[end - ROLLING_WEEKS:end]
        fit = _fit_on_frame(window, "__portfolio__", factors, MIN_ROLLING_WEEKS)
        if not fit.get("available"):
            continue
        for key, reading in fit["readings"].items():
            out[key].append({
                "end": fit["end"], "impact": reading["impact"],
                "low": reading["low"], "high": reading["high"],
                "evidence": reading["evidence"],
            })
    return {k: v for k, v in out.items() if v}


def _factor_paths(levels: Mapping[str, Optional[pd.Series]], index: pd.Index) -> Dict[str, dict]:
    """What each economic series itself did over the same weeks.

    Plotted beside the sensitivities so a reader can see the force as well as
    the response to it: "rates rose 1.8 points over these three years, and
    this portfolio fell when they did". Weekly last values, trimmed to the
    measured window, and never filled -- a gap in a published series stays a
    gap rather than becoming a straight line through data that does not exist.
    """
    if index is None or len(index) == 0:
        return {}
    start, end = pd.Timestamp(index[0]), pd.Timestamp(index[-1])
    out: Dict[str, dict] = {}
    for key, raw in (levels or {}).items():
        series = _resample_last(_clean(raw), "W-FRI")
        series = series[(series.index >= start) & (series.index <= end)].dropna()
        if len(series) < 8:
            continue
        out[key] = {
            "dates": [str(d.date()) for d in series.index],
            "values": [float(v) for v in series.to_numpy()],
            "first": float(series.iloc[0]), "last": float(series.iloc[-1]),
        }
    return out


def _growth_reading(daily: Mapping[str, pd.Series], weights: Mapping[str, float],
                    market_daily: pd.Series, levels: Optional[pd.Series]) -> dict:
    f = GROWTH_FACTOR
    monthly = {t: to_monthly_returns(daily[t]) for t in weights}
    frame = pd.concat({**monthly, "__mkt__": to_monthly_returns(market_daily),
                       f.key: to_changes(levels, f.transform, "ME")}, axis=1).dropna()
    frame = frame.iloc[-GROWTH_WINDOW_MONTHS:]
    if frame.empty:
        return {"available": False, "reason": "monthly growth data was unavailable",
                "limited": True}
    frame["__portfolio__"] = sum(frame[t] * w for t, w in weights.items())
    fit = _fit_on_frame(frame, "__portfolio__", (f,), GROWTH_MIN_MONTHS, CLEAR_T, period="months")
    n = fit["n_obs"]
    df = max(1, n - 3)
    from scipy import stats  # deferred: only the growth reading needs it
    t_crit = float(stats.t.ppf(0.975, df))
    min_r = t_crit / math.sqrt(t_crit ** 2 + df)
    fit["limited"] = True
    fit["note"] = (f"Growth is published monthly, so this rests on {n} observations. With that "
                   f"few, only strong relationships (correlation above about {min_r:.2f}) can be "
                   f"told apart from noise. Treat it as limited evidence.")
    return fit


def build_exposure_report(
    holdings: Iterable[dict],
    prices_fetcher: Callable[[List[str], str, str], Mapping[str, pd.Series]],
    series_fetcher: Callable[[str, str, str], pd.Series],
    *,
    end: Optional[date] = None,
    max_holdings: int = MAX_HOLDINGS,
) -> dict:
    """The full exposure report for a portfolio. Never raises; never estimates.

    prices_fetcher(tickers, start, end) -> {ticker: daily close series}
    series_fetcher(series_id, start, end) -> daily/monthly level series
    """
    positions, notes = normalize_positions(holdings, max_holdings)
    if not positions:
        return _error("Add at least one holding with a ticker symbol.", notes=notes)

    end_d = end or datetime.now(timezone.utc).date()
    start_d = end_d - timedelta(weeks=WINDOW_WEEKS + 10)
    start_g = end_d - timedelta(days=31 * (GROWTH_WINDOW_MONTHS + 3))
    s, e = str(min(start_d, start_g)), str(end_d)

    tickers = [p["ticker"] for p in positions]
    try:
        daily = dict(prices_fetcher(sorted(set(tickers) | {MARKET_TICKER}), s, e) or {})
    except Exception:
        daily = {}
    market_daily = _clean(daily.get(MARKET_TICKER))
    market_w = to_weekly_returns(market_daily)
    market_w = market_w[market_w.index >= pd.Timestamp(start_d)]
    if len(market_w) < MIN_WEEKS:
        return _error("Market price data is unavailable right now, so exposure can't be "
                      "measured. Nothing has been estimated in its place; please try again "
                      "shortly.", retryable=True, notes=notes)

    weekly: Dict[str, pd.Series] = {}
    excluded: List[dict] = []
    for p in positions:
        w = to_weekly_returns(daily.get(p["ticker"]))
        w = w[w.index >= pd.Timestamp(start_d)]
        if len(w) < MIN_WEEKS:
            reason = ("no price data was found for this symbol" if w.empty else
                      f"only {len(w)} weeks of price history; {MIN_WEEKS} are needed")
            excluded.append({"ticker": p["ticker"], "weight_pct": p["weight_pct"], "reason": reason})
        else:
            weekly[p["ticker"]] = w
    if not weekly:
        return _error("None of these holdings has at least two years of weekly price "
                      "history, so exposure can't be measured.", excluded=excluded, notes=notes)

    changes: Dict[str, pd.Series] = {}
    unavailable: List[str] = []
    levels_raw: Dict[str, Optional[pd.Series]] = {}
    for f in FACTORS:
        try:
            levels_raw[f.key] = series_fetcher(f.series_id, s, e)
            ch = to_changes(levels_raw[f.key], f.transform)
        except Exception:
            ch = pd.Series(dtype=float)
        ch = ch[ch.index >= pd.Timestamp(start_d)] if not ch.empty else ch
        if len(ch) < MIN_WEEKS:
            unavailable.append(f.label)
        else:
            changes[f.key] = ch
    active = tuple(f for f in FACTORS if f.key in changes)
    if not active:
        return _error("Economic data is unavailable right now. Nothing has been estimated "
                      "in its place; please try again shortly.", retryable=True, notes=notes)

    included = {p["ticker"]: p["weight_pct"] for p in positions if p["ticker"] in weekly}
    total = sum(included.values())
    weights = {t: w / total for t, w in included.items()}
    frame = pd.concat({**weekly, "__mkt__": market_w, **changes}, axis=1).dropna()
    frame["__portfolio__"] = sum(frame[t] * w for t, w in weights.items())

    now = frame.iloc[-WINDOW_WEEKS:]
    portfolio = _fit_on_frame(now, "__portfolio__", active, MIN_WEEKS)
    if not portfolio["available"]:
        return _error(f"Exposure couldn't be measured: {portfolio['reason']}.",
                      excluded=excluded, notes=notes)

    # Holdings are fitted on exactly the same weeks and regressors as the
    # portfolio, so weight x holding impact sums to the portfolio impact.
    holding_fits = {t: _fit_on_frame(now, t, active, MIN_WEEKS, subject=t) for t in weights}
    contributions: Dict[str, List[dict]] = {}
    for key, reading in portfolio["readings"].items():
        rows = []
        for t, w in weights.items():
            hr = holding_fits[t]["readings"].get(key)
            if not hr:
                continue
            contribution = w * hr["impact"]
            rows.append({"ticker": t, "weight_pct": 100.0 * w, "impact": hr["impact"],
                         "evidence": hr["evidence"], "contribution": contribution,
                         "share": (contribution / reading["impact"]) if reading["impact"] else None})
        contributions[key] = sorted(rows, key=lambda r: -abs(r["contribution"]))

    recent = _fit_on_frame(now.iloc[-RECENT_WEEKS:], "__portfolio__", active, MIN_RECENT_WEEKS)
    earlier = _fit_on_frame(now.iloc[:-RECENT_WEEKS].iloc[-EARLIER_WEEKS:], "__portfolio__",
                            active, MIN_RECENT_WEEKS)

    rank = {"clear": 0, "tentative": 1}
    top = sorted((r for r in portfolio["readings"].values() if r["evidence"] in rank),
                 key=lambda r: (rank[r["evidence"]], -abs(r["t"])))

    extra_changes: Dict[str, pd.Series] = {}
    extra_unavailable: List[str] = []
    for f in EXTRA_FACTORS:
        try:
            ch = to_changes(series_fetcher(f.series_id, s, e), f.transform)
        except Exception:
            ch = pd.Series(dtype=float)
        ch = ch[ch.index >= pd.Timestamp(start_d)] if not ch.empty else ch
        if len(ch) < MIN_WEEKS:
            extra_unavailable.append(f.label)   # excluded and named, never filled in
        else:
            extra_changes[f.key] = ch
    extras = fit_extras(now, "__portfolio__", active, extra_changes)

    try:
        growth_levels = series_fetcher(GROWTH_FACTOR.series_id, s, e)
    except Exception:
        growth_levels = None
    growth = _growth_reading(daily, weights, market_daily, growth_levels)

    excluded_weight = sum(x["weight_pct"] for x in excluded)
    if excluded:
        notes.append(f"{len(excluded)} holding(s), {excluded_weight:.0f}% of the portfolio, "
                     f"couldn't be measured and are left out; the remaining weights were "
                     f"rescaled to 100%.")
    if unavailable:
        notes.append(f"Data for {', '.join(unavailable)} was unavailable, so "
                     f"{'it is' if len(unavailable) == 1 else 'they are'} not shown. Nothing "
                     f"was estimated in its place.")

    return {
        "status": "ok",
        "as_of": portfolio["end"],
        "positions": [{"ticker": t, "weight_pct": 100.0 * w} for t, w in weights.items()],
        "excluded": excluded,
        "excluded_weight_pct": excluded_weight,
        "unavailable_factors": unavailable,
        "portfolio": portfolio,
        "top_exposures": [r["key"] for r in top],
        "contributions": contributions,
        "shifts": _shifts(recent, earlier),
        "recent_moves": _recent_moves(now, portfolio, active),
        "rolling": _rolling(now, active),
        "factor_paths": _factor_paths({k: v for k, v in levels_raw.items() if k in changes},
                                      now.index),
        "growth": growth,
        "extras": {"readings": extras, "unavailable": extra_unavailable,
                   "clear_t": EXTRA_CLEAR_T, "n_forces": len(EXTRA_FACTORS),
                   "control": CORE_CONTROL},
        "notes": notes,
        "method": {
            "window_weeks": WINDOW_WEEKS, "min_weeks": MIN_WEEKS, "clear_t": CLEAR_T,
            "rolling_weeks": ROLLING_WEEKS, "rolling_step": ROLLING_STEP,
            "range": "90%", "market_control": MARKET_TICKER, "standard_errors": "Newey-West, 4 lags",
            "factors": [{"label": f.label, "series_id": f.series_id} for f in FACTORS],
            "extra_factors": [{"label": f.label, "series_id": f.series_id, "group": f.group}
                              for f in EXTRA_FACTORS],
            "extra_clear_t": EXTRA_CLEAR_T,
        },
    }


FRED_PUBLIC_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}&coed={end}"


def parse_fred_csv(text: str) -> pd.Series:
    """FRED's public graph CSV: a date column and a value column, '.' for missing."""
    frame = pd.read_csv(io.StringIO(text or ""))
    if frame.shape[1] < 2 or frame.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    values = pd.to_numeric(frame.iloc[:, 1], errors="coerce")
    values.index = pd.to_datetime(frame.iloc[:, 0], errors="coerce")
    return _clean(values[values.index.notna()])


def fetch_fred_public(series_id: str, start: str, end: str) -> pd.Series:
    """The same FRED series from the keyless public download.

    Used only when the API route has no key or returns nothing. It is the same
    published data (latest vintage, exactly what fetch_fred returns), not an
    estimate, so falling back to it does not weaken the report.
    """
    import requests

    resp = requests.get(FRED_PUBLIC_CSV.format(series_id=series_id, start=start, end=end), timeout=30)
    resp.raise_for_status()
    return parse_fred_csv(resp.text)


def build_live_report(holdings: Iterable[dict], max_holdings: int = MAX_HOLDINGS) -> dict:
    """Production adapter: the app's cached fetchers, same engine."""
    from utils.fetchers import _get_fred_key, fetch_fred, fetch_prices_batch

    def _prices(tickers, start, end):
        return fetch_prices_batch(tuple(tickers), start, end)

    def _series(series_id, start, end):
        key = _get_fred_key()
        series = fetch_fred(series_id, start, end, api_key=key) if key else None
        if series is None or len(series) == 0:
            series = fetch_fred_public(series_id, start, end)
        return series

    return build_exposure_report(holdings, _prices, _series, max_holdings=max_holdings)
