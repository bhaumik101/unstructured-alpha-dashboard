# utils/track_record.py
# Unstructured Alpha — does a reading hold up a year later?
#
# THE QUESTION
# ------------
# Every exposure the product shows is measured on the last three years. An
# adviser's fair question is whether that means anything for the next one. This
# answers it the only honest way: out of sample, on many stocks and many start
# dates, published whatever it shows.
#
# THE TEST
# --------
# For each stock and each origin date T:
#   * measure the core exposures on the 156 weeks ending at T ("then");
#   * measure them again on the 52 weeks after T ("next"), which the first
#     measurement never saw.
# Then, grouped by the evidence label the first measurement carried:
#   * same direction -- how often "next" has the same sign as "then". For
#     readings labelled "not distinguishable from zero" this should sit near a
#     coin flip; the question is how far above it Clear and Tentative sit;
#   * consistent -- how often the two agree within their combined 90%
#     uncertainty: |next - then| <= 1.645 * sqrt(se_then^2 + se_next^2). If a
#     relationship were perfectly stable this would be about 90%; lower means
#     it drifted;
#   * shrinkage -- the slope of "next" on "then" across all readings. 1 means
#     readings carry over at full size; below 1 means they shrink out of sample
#     (the usual fate of any estimate selected for being large).
#
# The engine is pure: prices and series come in as daily series, so the study
# runs on synthetic data in the tests and on real data in cron/track_record.py.

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Dict, Iterable, List, Mapping, Optional

import numpy as np
import pandas as pd

from utils import exposure as ex

THEN_WEEKS = ex.WINDOW_WEEKS     # 156: the product's own window
NEXT_WEEKS = 52                  # the year after
NEXT_MIN_WEEKS = ex.MIN_RECENT_WEEKS
LABELS = ("clear", "tentative", "indistinct")


def weekly_changes(levels: Mapping[str, pd.Series]) -> Dict[str, pd.Series]:
    out = {}
    for f in ex.FACTORS:
        s = levels.get(f.series_id)
        if s is not None and len(s):
            out[f.key] = ex.to_changes(s, f.transform)
    return out


def _fit(y: pd.Series, mkt: pd.Series, changes: Mapping[str, pd.Series], min_obs: int,
         window: int) -> dict:
    return ex.fit_exposure(y, mkt, changes, window=window, min_obs=min_obs)


def pairs_for_stock(weekly: pd.Series, market: pd.Series, changes: Mapping[str, pd.Series],
                    origins: Iterable[pd.Timestamp]) -> List[dict]:
    """(then, next) reading pairs for one stock, one per origin and force."""
    rows = []
    for t in origins:
        then = _fit(weekly[weekly.index <= t], market[market.index <= t],
                    {k: v[v.index <= t] for k, v in changes.items()}, ex.MIN_WEEKS, THEN_WEEKS)
        end = t + pd.Timedelta(weeks=NEXT_WEEKS)
        win = lambda s: s[(s.index > t) & (s.index <= end)]  # noqa: E731
        nxt = _fit(win(weekly), win(market), {k: win(v) for k, v in changes.items()},
                   NEXT_MIN_WEEKS, NEXT_WEEKS)
        if not then["available"] or not nxt["available"]:
            continue
        for key, a in then["readings"].items():
            b = nxt["readings"].get(key)
            if not b or a["evidence"] not in LABELS:
                continue
            rows.append({"origin": str(t.date()), "factor": key, "evidence": a["evidence"],
                         "then": a["impact"], "then_se": a["se_impact"],
                         "next": b["impact"], "next_se": b["se_impact"]})
    return rows


def summarize(pairs: List[dict]) -> dict:
    """The published numbers, from every (then, next) pair."""
    def stats(rows: List[dict]) -> Optional[dict]:
        if not rows:
            return None
        same = sum(1 for r in rows if r["then"] * r["next"] > 0)
        consistent = sum(1 for r in rows
                         if abs(r["next"] - r["then"]) <= ex.Z90 * math.hypot(r["then_se"], r["next_se"]))
        return {"n": len(rows), "same_direction": same / len(rows), "consistent": consistent / len(rows)}

    by_label = {lab: stats([r for r in pairs if r["evidence"] == lab]) for lab in LABELS}
    by_factor = {}
    for f in ex.FACTORS:
        rows = [r for r in pairs if r["factor"] == f.key and r["evidence"] in ("clear", "tentative")]
        by_factor[f.key] = stats(rows)
    x = np.array([r["then"] for r in pairs])
    y = np.array([r["next"] for r in pairs])
    slope = float((x @ y) / (x @ x)) if len(x) >= 10 and (x @ x) > 0 else None
    return {
        "n_pairs": len(pairs),
        "n_stocks": len({r.get("ticker") for r in pairs}),
        "origins": sorted({r["origin"] for r in pairs}),
        "by_label": by_label,
        "by_factor": by_factor,
        "shrinkage_slope": slope,
    }


def origins_between(first: date, last: date, step_weeks: int = 26) -> List[pd.Timestamp]:
    """Origin dates every step_weeks, on Fridays, from first to last."""
    t = pd.Timestamp(first) + pd.offsets.Week(weekday=4)
    out = []
    while t.date() <= last:
        out.append(t)
        t = t + pd.Timedelta(weeks=step_weeks)
    return out


def study_pairs(daily_prices: Mapping[str, pd.Series], levels: Mapping[str, pd.Series],
                end: date, step_weeks: int = 26) -> List[dict]:
    """Every (then, next) pair from daily prices (with the market) and FRED levels.

    Origins run from three years after the market data starts to one year
    before `end`, so every "then" has its full window and every "next" its
    full year.
    """
    market = ex.to_weekly_returns(daily_prices.get(ex.MARKET_TICKER))
    changes = weekly_changes(levels)
    if market.empty or not changes:
        return []
    first = market.index[0].date() + timedelta(weeks=THEN_WEEKS)
    last = end - timedelta(weeks=NEXT_WEEKS)
    origins = origins_between(first, last, step_weeks)
    pairs: List[dict] = []
    for ticker, prices in daily_prices.items():
        if ticker == ex.MARKET_TICKER:
            continue
        weekly = ex.to_weekly_returns(prices)
        if len(weekly) < THEN_WEEKS:
            continue
        for row in pairs_for_stock(weekly, market, changes, origins):
            pairs.append(dict(row, ticker=ticker))
    return pairs


def run_study(daily_prices: Mapping[str, pd.Series], levels: Mapping[str, pd.Series],
              end: date, step_weeks: int = 26) -> dict:
    pairs = study_pairs(daily_prices, levels, end, step_weeks)
    out = summarize(pairs)
    out.update(available=bool(pairs), end=str(end), step_weeks=step_weeks,
               then_weeks=THEN_WEEKS, next_weeks=NEXT_WEEKS)
    return out


# ── storage ─────────────────────────────────────────────────────────────────
STUDY = "exposure_persistence_v1"


def save(result: dict) -> bool:
    """Add this run to the record. Never raises; never overwrites a past run."""
    import json
    from datetime import datetime, timezone

    from utils import db
    try:
        with db.engine.begin() as conn:
            conn.execute(db.research_results.insert().values(
                study=STUDY, computed_at=datetime.now(timezone.utc).isoformat(),
                payload=json.dumps(result, default=str)))
        return True
    except Exception:
        return False


def latest() -> Optional[dict]:
    """The newest published run, with its computed_at, or None."""
    import json

    from sqlalchemy import select

    from utils import db
    try:
        with db.engine.begin() as conn:
            row = conn.execute(
                select(db.research_results.c.payload, db.research_results.c.computed_at)
                .where(db.research_results.c.study == STUDY)
                .order_by(db.research_results.c.computed_at.desc()).limit(1)).first()
        if not row:
            return None
        return dict(json.loads(row[0]), computed_at=row[1])
    except Exception:
        return None


# ── the study, beside each reading ──────────────────────────────────────────
# A reading labelled Clear on oil and one labelled Clear on rates do not hold up
# equally well: in the first published run (2026-10-04, 494 companies) rates
# readings kept their direction a year later 72% of the time and oil 55%,
# against a 50% coin flip. The report shows that next to each reading, from the
# newest published run. No run, or too few readings for a force, means no line
# -- never an estimated one.

MIN_FORCE_READINGS = 30
EVIDENCE_URL = "https://www.unstructuredalpha.com/evidence"


def persistence(result: Optional[dict]) -> Dict[str, dict]:
    """{force key: {"rate", "n"}} for each core force the published study covers."""
    if not result or not result.get("available"):
        return {}
    out = {}
    for f in ex.FACTORS:
        st = (result.get("by_factor") or {}).get(f.key) or {}
        if st.get("same_direction") is not None and st.get("n", 0) >= MIN_FORCE_READINGS:
            out[f.key] = {"rate": float(st["same_direction"]), "n": int(st["n"])}
    return out


def persistence_short(key: str, evidence: str, held: Mapping[str, dict]) -> Optional[str]:
    """One line for a table row, or None. Only Clear and Tentative readings."""
    p = held.get(key)
    if not p or evidence not in ("clear", "tentative"):
        return None
    return f"Held its direction a year later {100 * p['rate']:.0f}% of the time (coin flip: 50%)"


def persistence_sentence(key: str, evidence: str, held: Mapping[str, dict]) -> Optional[str]:
    p = held.get(key)
    if not p or evidence not in ("clear", "tentative"):
        return None
    f = {x.key: x for x in ex.FACTORS}[key]
    return (f"Out of sample, {ex.lower_label(f.label)} readings labelled Clear or Tentative kept "
            f"their direction the following year {100 * p['rate']:.0f}% of the time, across "
            f"{p['n']:,} readings on S&P 500 companies. A coin flip would be 50%.")
