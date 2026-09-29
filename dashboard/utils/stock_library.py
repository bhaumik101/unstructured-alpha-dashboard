# utils/stock_library.py
# Unstructured Alpha — every single stock the engine has measured, kept
#
# WHY
# ---
# A single company is measured by the same engine as a portfolio: the stock as
# a one-holding, 100% portfolio. That result used to live only in report_cache,
# which expires after six hours and is pruned on write. This keeps it: one row
# per stock per data week in stock_measurements, and one per economic force in
# stock_exposures. A stock's history grows each week it is viewed, and the main
# page can rank what has been measured ("most rate-sensitive") from the
# database instead of re-measuring anything.
#
# RULES
# -----
#   * Only a one-stock report is recorded. A portfolio's exposure is not a
#     company's, and must never be filed under one of its holdings.
#   * Only what the engine measured is stored. A force whose series failed that
#     week has no row; nothing is filled in (see CLAUDE.md, signal integrity).
#   * Recording never raises: the report is already in the visitor's hands, and
#     a database hiccup must not take the page down with it.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import and_, func, select

from utils import db
from utils.db import stock_exposures, stock_measurements

# Evidence labels that stand up. "indistinct" readings are stored -- they are
# the honest answer for that force -- but never ranked or headlined.
STANDS_UP = ("clear", "tentative")


def single_ticker(report: dict) -> Optional[str]:
    """The ticker if this report is one stock at 100%, else None."""
    positions = (report or {}).get("positions") or []
    if len(positions) != 1 or (report or {}).get("excluded"):
        return None
    only = positions[0]
    if abs(float(only.get("weight_pct") or 0) - 100.0) > 0.01:
        return None
    return str(only.get("ticker") or "").upper() or None


def record(report: dict, name: str = "") -> bool:
    """File a one-stock report in the library. True if rows were written.

    Idempotent per (ticker, data week): viewing the same stock twice in a week
    updates that week's rows rather than adding new ones.
    """
    try:
        if (report or {}).get("status") != "ok":
            return False
        ticker = single_ticker(report)
        as_of = str(report.get("as_of") or "")[:10]
        readings = ((report.get("portfolio") or {}).get("readings")) or {}
        if not ticker or len(as_of) != 10 or not readings:
            return False

        pf = report["portfolio"]
        head = {
            "ticker": ticker, "as_of": as_of, "name": (name or "")[:160] or None,
            "market_beta": _num(pf.get("market_beta")), "r2": _num(pf.get("r2")),
            "n_obs": int(pf["n_obs"]) if pf.get("n_obs") is not None else None,
            "window_weeks": int((report.get("method") or {}).get("window_weeks") or 0) or None,
            "measured_at": datetime.now(timezone.utc).isoformat(),
        }
        rows = []
        for key, r in readings.items():
            impact, low, high = _num(r.get("impact")), _num(r.get("low")), _num(r.get("high"))
            if impact is None or low is None or high is None:
                continue   # not measured is not stored; never a synthesized zero
            rows.append({"ticker": ticker, "as_of": as_of, "factor": key, "impact": impact,
                         "low": low, "high": high, "t": _num(r.get("t")),
                         "evidence": str(r.get("evidence") or "")[:24]})
        if not rows:
            return False

        with db.engine.begin() as conn:
            stmt = db.upsert_stmt(stock_measurements, ["ticker", "as_of"]).values(**head)
            conn.execute(stmt.on_conflict_do_update(
                index_elements=["ticker", "as_of"],
                set_={k: v for k, v in head.items() if k not in ("ticker", "as_of")
                      and (k != "name" or v)}))
            for row in rows:
                stmt = db.upsert_stmt(stock_exposures, ["ticker", "as_of", "factor"]).values(**row)
                conn.execute(stmt.on_conflict_do_update(
                    index_elements=["ticker", "as_of", "factor"],
                    set_={k: row[k] for k in ("impact", "low", "high", "t", "evidence")}))
        return True
    except Exception:
        return False


def history(ticker: str, limit: int = 26) -> List[dict]:
    """Every stored week for one stock, newest first, each with its exposures."""
    ticker = str(ticker or "").upper()
    try:
        with db.engine.begin() as conn:
            heads = conn.execute(
                select(stock_measurements).where(stock_measurements.c.ticker == ticker)
                .order_by(stock_measurements.c.as_of.desc()).limit(limit)
            ).mappings().all()
            if not heads:
                return []
            weeks = [h["as_of"] for h in heads]
            exp = conn.execute(
                select(stock_exposures).where(and_(stock_exposures.c.ticker == ticker,
                                                   stock_exposures.c.as_of.in_(weeks)))
            ).mappings().all()
    except Exception:
        return []
    by_week: Dict[str, Dict[str, dict]] = {}
    for e in exp:
        by_week.setdefault(e["as_of"], {})[e["factor"]] = dict(e)
    return [dict(h, exposures=by_week.get(h["as_of"], {})) for h in heads]


def latest(limit: int = 500) -> List[dict]:
    """The newest week of every stock in the library, most recently measured first."""
    try:
        newest = (select(stock_measurements.c.ticker,
                         func.max(stock_measurements.c.as_of).label("as_of"))
                  .group_by(stock_measurements.c.ticker).subquery())
        with db.engine.begin() as conn:
            heads = conn.execute(
                select(stock_measurements).join(
                    newest, and_(stock_measurements.c.ticker == newest.c.ticker,
                                 stock_measurements.c.as_of == newest.c.as_of))
                .order_by(stock_measurements.c.measured_at.desc()).limit(limit)
            ).mappings().all()
            if not heads:
                return []
            exp = conn.execute(
                select(stock_exposures).join(
                    newest, and_(stock_exposures.c.ticker == newest.c.ticker,
                                 stock_exposures.c.as_of == newest.c.as_of))
            ).mappings().all()
    except Exception:
        return []
    by_ticker: Dict[str, Dict[str, dict]] = {}
    for e in exp:
        by_ticker.setdefault(e["ticker"], {})[e["factor"]] = dict(e)
    return [dict(h, exposures=by_ticker.get(h["ticker"], {})) for h in heads]


def count() -> int:
    """How many distinct stocks are on record. 0 when the database is unavailable."""
    try:
        with db.engine.begin() as conn:
            return int(conn.execute(
                select(func.count(func.distinct(stock_measurements.c.ticker)))).scalar() or 0)
    except Exception:
        return 0


def ranked(factor: str, n: int = 5, stocks: Optional[List[dict]] = None) -> Dict[str, List[dict]]:
    """The stocks most exposed to one force, each way, among readings that stand up.

    {"up": [...], "down": [...]} -- moved up with the force, moved down with it.
    Readings indistinguishable from zero are left out: ranking noise would
    present it as a finding.
    """
    pool = latest() if stocks is None else stocks
    rows = []
    for s in pool:
        e = (s.get("exposures") or {}).get(factor)
        if e and e.get("evidence") in STANDS_UP:
            rows.append(dict(e, name=s.get("name")))
    up = sorted((r for r in rows if r["impact"] > 0), key=lambda r: -r["impact"])[:n]
    down = sorted((r for r in rows if r["impact"] < 0), key=lambda r: r["impact"])[:n]
    return {"up": up, "down": down}


def _num(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None
