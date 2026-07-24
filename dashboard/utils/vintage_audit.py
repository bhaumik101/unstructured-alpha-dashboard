"""Revision-bias audit for FRED-backed signals.

Motivation. The live scoring engine at time T only ever saw the data vintage
available at T. But fetch_fred() returns the LATEST revision of every series, so
any backtest or lead-time validation that reconstructs history from it is quietly
using numbers the model could not have known — classic revision / look-ahead
bias (Croushore & Stark; the "real-time data" literature). This module quantifies
exactly how large that bias is, per series, by comparing:

  - latest-revised   : fetch_fred(series, d, d)            (what we read today)
  - first-print       : fetch_fred_asof(series, d, d, d')  (what was known then)

The point is honesty, not alarm: some FRED series (market rates, spreads) are
never revised and will correctly show ~0 revision; others (industrial production,
payrolls, inventories) revise materially. Turning "we might have look-ahead bias"
into "here is the measured revision per series" is itself a data-trust artifact,
and the fetch_fred_asof primitive it validates is the input a point-in-time
backtest should consume.

Nothing here fabricates data: when a provider read is unavailable, the affected
comparison is dropped and reported as such, never imputed.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

# Below this absolute percentage a difference is treated as numerical noise
# (float formatting, rounding), not a genuine data revision.
REVISION_EPS_PCT = 0.05


def revision_stats(latest: pd.Series, vintage: pd.Series,
                   eps_pct: float = REVISION_EPS_PCT) -> dict:
    """Pure divergence statistics between latest-revised and first-print values.

    Aligns the two series on their common dates and computes, over those points,
    how far the revised value drifted from what was first published. Signed
    percentage revision is (latest - vintage) / vintage * 100; dates where the
    vintage value is zero are skipped (percentage undefined) but still counted in
    ``n_common`` so the caller can see coverage.

    Returns a dict that is always safe to consume:
        available        : bool   — were there any comparable points at all
        n_common         : int    — dates present in BOTH series
        n_compared       : int    — dates with a well-defined pct revision
        mean_abs_pct     : float  — average |revision| (headline magnitude)
        median_abs_pct   : float
        max_abs_pct      : float
        mean_signed_pct  : float  — sign shows systematic up/down revision
        share_revised    : float  — fraction of points revised beyond eps_pct
        is_revised       : bool   — any point exceeded eps_pct
    """
    empty = {
        "available": False, "n_common": 0, "n_compared": 0,
        "mean_abs_pct": 0.0, "median_abs_pct": 0.0, "max_abs_pct": 0.0,
        "mean_signed_pct": 0.0, "share_revised": 0.0, "is_revised": False,
    }
    if latest is None or vintage is None:
        return empty
    if not isinstance(latest, pd.Series) or not isinstance(vintage, pd.Series):
        return empty
    if latest.empty or vintage.empty:
        return empty

    common = latest.index.intersection(vintage.index)
    n_common = int(len(common))
    if n_common == 0:
        return empty

    lv = pd.to_numeric(latest.reindex(common), errors="coerce")
    vv = pd.to_numeric(vintage.reindex(common), errors="coerce")
    mask = lv.notna() & vv.notna() & (vv != 0)
    lv, vv = lv[mask], vv[mask]
    n_compared = int(len(lv))
    if n_compared == 0:
        out = dict(empty)
        out.update({"available": True, "n_common": n_common})
        return out

    signed_pct = (lv - vv) / vv * 100.0
    abs_pct = signed_pct.abs()
    revised = abs_pct > eps_pct

    return {
        "available": True,
        "n_common": n_common,
        "n_compared": n_compared,
        "mean_abs_pct": round(float(abs_pct.mean()), 4),
        "median_abs_pct": round(float(abs_pct.median()), 4),
        "max_abs_pct": round(float(abs_pct.max()), 4),
        "mean_signed_pct": round(float(signed_pct.mean()), 4),
        "share_revised": round(float(revised.mean()), 4),
        "is_revised": bool(revised.any()),
    }


def fred_backed_signals(signals: Optional[dict] = None) -> dict:
    """{signal_id -> fred series_id} for every FRED-sourced signal in config.

    These are exactly the signals whose historical inputs are subject to
    revision and therefore need point-in-time vintages for an honest backtest.
    """
    if signals is None:
        from utils.config import SIGNALS as signals
    out = {}
    for sid, cfg in signals.items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("source") == "fred" and cfg.get("series_id"):
            out[sid] = cfg["series_id"]
    return out


def audit_series_asof(series_id: str, start: str, end: str, as_of: str,
                      api_key: str = "") -> dict:
    """Measure revision bias for one FRED series over [start, end].

    Compares today's latest-revised values against the vintage that was in
    effect on ``as_of``. Returns revision_stats() enriched with the series id and
    an ``error`` key when either read was unavailable (never fabricated).
    """
    from utils.fetchers import fetch_fred, fetch_fred_asof, is_unavailable

    latest = fetch_fred(series_id, start, end, api_key=api_key)
    vintage = fetch_fred_asof(series_id, start, end, as_of, api_key=api_key)

    if is_unavailable(latest) or is_unavailable(vintage):
        stats = revision_stats(pd.Series(dtype=float), pd.Series(dtype=float))
        stats.update({
            "series_id": series_id,
            "as_of": as_of,
            "error": "unavailable",
        })
        return stats

    stats = revision_stats(latest, vintage)
    stats.update({"series_id": series_id, "as_of": as_of, "error": None})
    return stats


def audit_series_first_print(series_id: str, start: str, end: str,
                             api_key: str = "") -> dict:
    """Measure revision bias for one FRED series across a whole window by
    comparing every observation's FIRST print to its latest-revised value.

    Unlike audit_series_asof (one vintage date), this uses fetch_fred_first_print
    (ALFRED initial-release), so the statistics describe how much the series is
    revised per observation over [start, end] — the honest, marketable magnitude.
    Returns revision_stats() enriched with series_id and an ``error`` key when a
    read was unavailable (never fabricated).
    """
    from utils.fetchers import fetch_fred, fetch_fred_first_print, is_unavailable

    latest = fetch_fred(series_id, start, end, api_key=api_key)
    first_print = fetch_fred_first_print(series_id, start, end, api_key=api_key)

    if is_unavailable(latest) or is_unavailable(first_print):
        stats = revision_stats(pd.Series(dtype=float), pd.Series(dtype=float))
        stats.update({"series_id": series_id, "error": "unavailable"})
        return stats

    stats = revision_stats(latest, first_print)
    stats.update({"series_id": series_id, "error": None})
    return stats


def audit_all_fred_signals(start: str, end: str, api_key: str = "",
                           signals: Optional[dict] = None) -> dict:
    """Revision-bias profile across every FRED-backed signal.

    Runs audit_series_first_print for each revision-prone signal and rolls the
    results into an honest summary. Signals whose data is unavailable are counted
    as ``n_unavailable`` and excluded from magnitude stats — never imputed.

    Returns:
        {
          "per_signal": [ {signal_id, series_id, ...revision_stats..., error} ],
          "summary": {
            "n_signals"      : FRED-backed signals considered
            "n_measured"     : signals with a well-defined revision measurement
            "n_unavailable"  : signals whose data could not be read
            "n_revised"      : measured signals revised beyond the noise floor
            "mean_abs_pct"   : average |revision| across measured signals
            "max_abs_pct"    : largest single-signal mean |revision|
            "worst_series"   : series_id of that largest, or None
          }
        }

    `signals` maps signal_id -> config (defaults to the live SIGNALS). When no
    API key is present, everything is reported unavailable rather than zero
    revision — absence of data is not evidence of no revision.
    """
    if signals is None:
        from utils.config import SIGNALS as signals

    fred_map = fred_backed_signals(signals)  # {signal_id: series_id}
    per_signal: list = []
    measured: list = []

    for sig_id, series_id in fred_map.items():
        stats = audit_series_first_print(series_id, start, end, api_key=api_key)
        stats["signal_id"] = sig_id
        stats["signal_name"] = (signals.get(sig_id, {}) or {}).get("name", sig_id)
        per_signal.append(stats)
        if not stats.get("error") and stats.get("available") and stats.get("n_compared", 0) > 0:
            measured.append(stats)

    n_signals = len(fred_map)
    n_measured = len(measured)
    n_unavailable = sum(1 for s in per_signal if s.get("error") == "unavailable")
    n_revised = sum(1 for s in measured if s.get("is_revised"))
    mean_abs = round(sum(s["mean_abs_pct"] for s in measured) / n_measured, 4) if n_measured else 0.0
    worst = max(measured, key=lambda s: s["mean_abs_pct"], default=None)

    return {
        "per_signal": sorted(per_signal, key=lambda s: s.get("mean_abs_pct", 0.0), reverse=True),
        "summary": {
            "n_signals": n_signals,
            "n_measured": n_measured,
            "n_unavailable": n_unavailable,
            "n_revised": n_revised,
            "mean_abs_pct": mean_abs,
            "max_abs_pct": worst["mean_abs_pct"] if worst else 0.0,
            "worst_series": worst["series_id"] if worst else None,
            "worst_signal_name": worst.get("signal_name") if worst else None,
        },
    }
