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
#
# The engine is pure: data arrives through injected fetchers, so every claim
# in it is tested on synthetic data where the true exposure is known.

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Mapping, Optional

import numpy as np
import pandas as pd
from scipy import stats


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
    "U.S. industrial production grew 1% in a month",
    "Growth drives company earnings, but it is only published monthly, so evidence is thin.",
)

MARKET_TICKER = "SPY"

WINDOW_WEEKS = 156
MIN_WEEKS = 104
RECENT_WEEKS = 52          # "what changed": the latest year...
MIN_RECENT_WEEKS = 40
EARLIER_WEEKS = 104        # ...against the two years before it (no overlap)
RECENT_MOVE_WEEKS = 4      # "what happened lately": the last four weeks
NEWEY_WEST_LAGS = 4
GROWTH_WINDOW_MONTHS = 36
GROWTH_MIN_MONTHS = 24
MAX_HOLDINGS = 25
VIF_WARN = 5.0

Z90 = float(stats.norm.ppf(0.95))
CLEAR_T = float(stats.norm.ppf(1 - 0.05 / (2 * len(FACTORS))))

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


def _fmt(x: float) -> str:
    return f"{x:+.1f}%" if abs(x) >= 0.95 else f"{x:+.2f}%"


def _sentence(f: Factor, impact: float, low: float, high: float, evidence: str,
              subject: str = "this portfolio") -> str:
    if evidence == "not_enough_data":
        return f"There isn't enough history to measure exposure to {f.label.lower()}."
    if evidence == "indistinct":
        return (f"No measurable link to {f.label.lower()}: in weeks when {f.shock_phrase}, "
                f"{subject}'s typical move of {_fmt(impact)} sat inside its range of "
                f"uncertainty ({_fmt(low)} to {_fmt(high)}).")
    text = (f"In weeks when {f.shock_phrase}, {subject} has typically moved {_fmt(impact)} "
            f"(90% range {_fmt(low)} to {_fmt(high)}), after accounting for the overall "
            f"stock market.")
    if evidence == "tentative":
        text += " The evidence is tentative."
    return text


def _fit_on_frame(frame: pd.DataFrame, ycol: str, factors: Iterable[Factor],
                  min_obs: int, clear_t: float = CLEAR_T,
                  subject: str = "this portfolio") -> dict:
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
            "sentence": _sentence(f, impact, low, high, ev, subject),
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
            sentence = (f"No measurable change in {now['label'].lower()} sensitivity between "
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
    fit = _fit_on_frame(frame, "__portfolio__", (f,), GROWTH_MIN_MONTHS, CLEAR_T)
    n = fit["n_obs"]
    df = max(1, n - 3)
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
    for f in FACTORS:
        try:
            ch = to_changes(series_fetcher(f.series_id, s, e), f.transform)
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
        "growth": growth,
        "notes": notes,
        "method": {
            "window_weeks": WINDOW_WEEKS, "min_weeks": MIN_WEEKS, "clear_t": CLEAR_T,
            "range": "90%", "market_control": MARKET_TICKER, "standard_errors": "Newey-West, 4 lags",
            "factors": [{"label": f.label, "series_id": f.series_id} for f in FACTORS],
        },
    }


def build_live_report(holdings: Iterable[dict], max_holdings: int = MAX_HOLDINGS) -> dict:
    """Production adapter: the app's cached fetchers, same engine."""
    from utils.fetchers import _get_fred_key, fetch_fred, fetch_prices_batch

    def _prices(tickers, start, end):
        return fetch_prices_batch(tuple(tickers), start, end)

    def _series(series_id, start, end):
        return fetch_fred(series_id, start, end, api_key=_get_fred_key())

    return build_exposure_report(holdings, _prices, _series, max_holdings=max_holdings)
