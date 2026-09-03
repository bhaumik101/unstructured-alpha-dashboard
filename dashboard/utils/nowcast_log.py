# utils/nowcast_log.py
# Unstructured Alpha — the forward nowcast record
#
# WHY THIS EXISTS
# ---------------
# docs/NOWCAST_RESULTS.md records four backtests against 2011-2026. Roughly ten
# configurations were searched over that history, so nothing further extracted
# from it is believable: the best result (factor model, skill +0.370,
# p = 0.113) is the best of ten tries, and a Bonferroni correction over ten
# needs p < 0.005.
#
# The history is spent. The only uncontaminated test left is out-of-time —
# publish an estimate before the number prints, then score it against what
# printed. Twelve monthly observations produce a clean answer.
#
# THE PROPERTY THIS MODULE EXISTS TO PROTECT
# ------------------------------------------
# One row per (target, month), inserted once, never updated. `predicted` is
# written at claim time and is immutable; scoring may only fill `actual` and
# `scored_at`. A nowcast that can be revised after the number prints is not a
# forecast, and the whole argument for the pivot is that this record cannot be
# edited into looking good.
#
# That is enforced here rather than trusted: log_nowcast() is INSERT ... ON
# CONFLICT DO NOTHING, and resolve_nowcasts() never touches the prediction
# columns.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import numpy as np
from sqlalchemy import select, update

from utils import db
from utils.db import nowcast_log


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_target_month(last_published: str) -> str:
    """The month to nowcast, given the last month the target has published.

    `last_published` is "YYYY-MM". Industrial Production for month M prints
    mid-M+1, so when the series ends at M-1 the open question is M — a month
    that has ended, whose high-frequency inputs are complete, and whose official
    number does not yet exist. That is the nowcast window.
    """
    year, month = (int(part) for part in str(last_published)[:7].split("-"))
    return f"{year + 1}-01" if month == 12 else f"{year}-{month + 1:02d}"


def log_nowcast(
    target_series: str,
    target_month: str,
    predicted: float,
    naive: float,
    estimator: str,
    n_features: int = 0,
    features_used: Optional[List[str]] = None,
) -> bool:
    """Record one nowcast. Returns True if a new row was written.

    INSERT-ONLY. A second call for the same (target, month) is a no-op and
    returns False — it does not overwrite, because the first estimate is the
    one that was made without knowing the answer. Re-running the cron, or
    running it twice in a month, must not be able to improve the record.
    """
    if predicted is None or naive is None:
        print(f"[nowcast] refusing to log {target_series} {target_month}: "
              f"predicted or naive is None", flush=True)
        return False

    values = {
        "target_series": target_series,
        "target_month": str(target_month)[:7],
        "predicted": float(predicted),
        "naive": float(naive),
        "estimator": estimator,
        "n_features": int(n_features),
        "features_used": ",".join(features_used or []) or None,
        "created_at": _now_iso(),
    }

    try:
        if db.IS_SQLITE:
            from sqlalchemy.dialects.sqlite import insert as _ins
        else:
            from sqlalchemy.dialects.postgresql import insert as _ins
        stmt = _ins(nowcast_log).values(**values).on_conflict_do_nothing(
            index_elements=["target_series", "target_month"]
        )
        with db.engine.begin() as conn:
            result = conn.execute(stmt)
        written = bool(getattr(result, "rowcount", 0))
        if not written:
            print(f"[nowcast] {target_series} {values['target_month']} already "
                  f"recorded — not overwriting", flush=True)
        return written
    except Exception as exc:
        print(f"[nowcast] could not record {target_series} {target_month}: "
              f"{type(exc).__name__}: {exc}", flush=True)
        return False


def resolve_nowcasts(fetch_actual: Callable[[str, str], Optional[float]]) -> int:
    """Fill `actual` for any logged month whose number has since published.

    `fetch_actual(target_series, target_month)` returns the published value or
    None if it is not out yet. Only `actual` and `scored_at` are written; the
    prediction columns are never touched, which is the point of the table.
    """
    try:
        with db.engine.begin() as conn:
            pending = conn.execute(
                select(nowcast_log).where(nowcast_log.c.actual.is_(None))
            ).mappings().all()
    except Exception as exc:
        print(f"[nowcast] could not read pending nowcasts: {exc}", flush=True)
        return 0

    if not pending:
        print("[nowcast] no unscored months", flush=True)
        return 0

    scored = 0
    for row in pending:
        try:
            actual = fetch_actual(row["target_series"], row["target_month"])
        except Exception as exc:
            print(f"[nowcast] {row['target_month']}: fetch failed "
                  f"({type(exc).__name__})", flush=True)
            continue
        if actual is None:
            continue
        try:
            with db.engine.begin() as conn:
                conn.execute(
                    update(nowcast_log)
                    .where(nowcast_log.c.id == row["id"])
                    .values(actual=float(actual), scored_at=_now_iso())
                )
            scored += 1
            err_m = abs(float(actual) - float(row["predicted"]))
            err_n = abs(float(actual) - float(row["naive"]))
            verdict = "model closer" if err_m < err_n else "naive closer"
            print(f"[nowcast] {row['target_month']} actual={actual:.3f} "
                  f"predicted={row['predicted']:.3f} naive={row['naive']:.3f} "
                  f"-> {verdict}", flush=True)
        except Exception as exc:
            print(f"[nowcast] could not score {row['target_month']}: {exc}", flush=True)

    print(f"[nowcast] scored {scored} of {len(pending)} unscored month(s)", flush=True)
    return scored


def get_forward_record(target_series: Optional[str] = None) -> dict:
    """The out-of-time scorecard. Empty until months accrue — never estimated.

    Deliberately reports `months_model_closer` beside RMSE, and refuses to
    report skill at all below `MIN_MONTHS_FOR_SKILL`. A skill score off three
    observations is what nearly shipped from the backtest as a 28% improvement;
    the forward record starts small by construction and must not repeat it.
    """
    MIN_MONTHS_FOR_SKILL = 12

    empty = {"n_logged": 0, "n_scored": 0, "rmse_model": None, "rmse_naive": None,
             "skill": None, "months_model_closer": None, "enough_to_judge": False,
             "note": "no nowcasts recorded yet"}
    try:
        with db.engine.begin() as conn:
            query = select(nowcast_log)
            if target_series:
                query = query.where(nowcast_log.c.target_series == target_series)
            rows = [dict(r) for r in conn.execute(query).mappings().all()]
    except Exception:
        return empty

    if not rows:
        return empty

    done = [r for r in rows if r.get("actual") is not None]
    if not done:
        return {**empty, "n_logged": len(rows),
                "note": f"{len(rows)} month(s) recorded, none published yet"}

    actual = np.array([float(r["actual"]) for r in done])
    pred = np.array([float(r["predicted"]) for r in done])
    naive = np.array([float(r["naive"]) for r in done])
    rmse_m = float(np.sqrt(np.mean((pred - actual) ** 2)))
    rmse_n = float(np.sqrt(np.mean((naive - actual) ** 2)))
    closer = float(np.mean(np.abs(pred - actual) < np.abs(naive - actual)))
    enough = len(done) >= MIN_MONTHS_FOR_SKILL

    return {
        "n_logged": len(rows),
        "n_scored": len(done),
        "rmse_model": round(rmse_m, 4),
        "rmse_naive": round(rmse_n, 4),
        # Withheld below the threshold on purpose. A ratio of two RMSEs over a
        # handful of months is dominated by whichever month was strangest.
        "skill": (round(1.0 - rmse_m / rmse_n, 4)
                  if enough and rmse_n > 0 else None),
        "months_model_closer": round(closer, 4),
        "enough_to_judge": enough,
        "note": ("" if enough else
                 f"{len(done)} of {MIN_MONTHS_FOR_SKILL} months needed before a "
                 f"skill score means anything"),
    }
