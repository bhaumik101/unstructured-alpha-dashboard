# utils/score_history.py
# Unstructured Alpha — Historical Score Snapshots
#
# WHY THIS MODULE EXISTS: every score on this site, before today, was a
# pure point-in-time computation -- nothing remembered what a ticker's
# score was yesterday or last month. That blocks three things the
# 2026-06-22 roadmap calls for: a Score History chart on Ticker Deep
# Dive, a future public track-record page, and alert deltas compared
# against a real stored value instead of whatever the last alert
# happened to see. This module is the foundation all three sit on.
#
# NOT user-scoped, deliberately: a ticker's Confluence Score at a given
# moment is the same number for every visitor, so utils/db.py's
# score_snapshots table is keyed by (ticker, day), not by user.
#
# NO BACKGROUND SCHEDULER: this is a Streamlit app with no cron. History
# accumulates only for tickers someone actually opens on Ticker Deep
# Dive, upserted at view time -- organic, traffic-driven coverage, not a
# guaranteed daily record across the whole signal universe. That's a
# real, honest limitation worth stating plainly wherever this data is
# displayed, not glossed over.

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select

from utils import db
from utils.db import score_snapshots, signal_snapshots, score_components, upsert_stmt
from utils.lead_time_research import get_sector_peers


def record_score_snapshot(ticker: str, score: float, case: str, conviction: str,
                          kind: str = "full") -> None:
    """
    Upsert today's score snapshot for `ticker`. Safe to call on every
    Ticker Deep Dive page view -- the unique (ticker, snapshot_date)
    constraint means a second visit later the same day OVERWRITES the
    same row with the latest score (intentional: today's most recent
    computation is the one worth keeping, not the first of the day),
    rather than creating duplicate rows.
    """
    ticker = ticker.upper().strip()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    # `kind` distinguishes the full Confluence Score from the cheaper bulk
    # macro+momentum score — they are different metrics and produce different
    # numbers for the same ticker, so callers must never conflate them.
    # A "full" row is authoritative: never let a bulk macro_momentum run
    # downgrade a full score that was already computed for the same day.
    stmt = upsert_stmt(score_snapshots, ["ticker", "snapshot_date"]).values(
        ticker=ticker, snapshot_date=today, score=score, case=case,
        conviction=conviction, created_at=now_iso, score_kind=kind,
    )
    update_set = {"score": score, "case": case, "conviction": conviction,
                  "created_at": now_iso, "score_kind": kind}
    if kind != "full":
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "snapshot_date"],
            set_=update_set,
            where=(score_snapshots.c.score_kind != "full"),
        )
    else:
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "snapshot_date"],
            set_=update_set,
        )
    with db.engine.begin() as conn:
        conn.execute(stmt)


def record_score_components(ticker: str, components: dict) -> None:
    """
    Upsert today's COMPONENT snapshot for `ticker` — the reconciling score
    breakdown from utils.score_components.build_components. Powers "Explain the
    Move". Same (ticker, snapshot_date) upsert semantics as record_score_snapshot:
    a later view the same day overwrites with the latest computation. Best-effort;
    any DB/JSON error is swallowed so a snapshot failure never breaks the page.
    """
    import json
    try:
        ticker = ticker.upper().strip()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_iso = datetime.now(timezone.utc).isoformat()
        blob = json.dumps(components, separators=(",", ":"))
        vals = dict(
            ticker=ticker, snapshot_date=today,
            model_version=components.get("model_version"),
            signal_registry_version=components.get("signal_registry_version"),
            final_score=float(components.get("final_score", 0.0) or 0.0),
            components_json=blob, created_at=now_iso,
        )
        stmt = upsert_stmt(score_components, ["ticker", "snapshot_date"]).values(**vals)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "snapshot_date"],
            set_={k: vals[k] for k in
                  ("model_version", "signal_registry_version", "final_score",
                   "components_json", "created_at")},
        )
        with db.engine.begin() as conn:
            conn.execute(stmt)
    except Exception:
        pass


def _parse_components_row(row) -> dict | None:
    import json
    if not row:
        return None
    try:
        c = json.loads(row["components_json"])
        c["snapshot_date"] = row["snapshot_date"]
        return c
    except Exception:
        return None


def get_signal_scores_asof(cutoff_date: str) -> dict:
    """
    Latest recorded percentile score per signal on/before `cutoff_date`, from
    signal_snapshots (global, not ticker-scoped). Used to RECONSTRUCT a prior
    component snapshot when no genuine one has accrued yet — so "Explain the Move"
    works on day 1 from real historical signal readings rather than returning an
    empty state. Returns {signal_id: score}.
    """
    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(signal_snapshots)
                .where(signal_snapshots.c.snapshot_date <= cutoff_date)
                .order_by(signal_snapshots.c.signal_id, signal_snapshots.c.snapshot_date.desc())
            ).mappings().all()
    except Exception:
        return {}
    out: dict[str, float] = {}
    for r in rows:
        sid = str(r["signal_id"])
        if sid not in out:  # desc-ordered → first seen is the latest on/before cutoff
            try:
                out[sid] = float(r["score"])
            except Exception:
                pass
    return out


def get_latest_components(ticker: str) -> dict | None:
    """Most recent component snapshot for `ticker`, or None."""
    ticker = ticker.upper().strip()
    try:
        with db.engine.begin() as conn:
            row = conn.execute(
                select(score_components)
                .where(score_components.c.ticker == ticker)
                .order_by(score_components.c.snapshot_date.desc())
                .limit(1)
            ).mappings().first()
        return _parse_components_row(row)
    except Exception:
        return None


def get_latest_signal_states() -> dict[str, dict]:
    """Latest persisted state for every signal in one database read.

    Used by global chrome such as the regime bar. It deliberately never calls
    a provider or computes signals: page headers must not turn every route into
    a hidden 47-source refresh. Returns an empty dict until snapshots accrue.
    """
    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(signal_snapshots)
                .order_by(signal_snapshots.c.snapshot_date.desc(), signal_snapshots.c.created_at.desc())
            ).mappings().all()
        latest: dict[str, dict] = {}
        for row in rows:
            signal_id = str(row["signal_id"])
            if signal_id not in latest:
                latest[signal_id] = dict(row)
        return latest
    except Exception:
        return {}


def get_components_on_or_before(ticker: str, cutoff_date: str) -> dict | None:
    """
    The component snapshot with the latest snapshot_date <= cutoff_date (i.e. the
    best available "Time A" for a comparison window). None if none exists yet.
    """
    ticker = ticker.upper().strip()
    try:
        with db.engine.begin() as conn:
            row = conn.execute(
                select(score_components)
                .where(score_components.c.ticker == ticker)
                .where(score_components.c.snapshot_date <= cutoff_date)
                .order_by(score_components.c.snapshot_date.desc())
                .limit(1)
            ).mappings().first()
        return _parse_components_row(row)
    except Exception:
        return None


def explain_move(ticker: str, days_back: int = 7, allow_reconstruction: bool = True) -> dict:
    """
    Orchestrate an "Explain the Move" attribution for `ticker` over the last
    `days_back` days. Fetches the latest component snapshot (Time B) and the best
    snapshot on/before the cutoff (Time A), then runs the pure attribution engine.
    Returns the engine's structured result; state == "no_comparison" when there
    isn't a usable prior snapshot yet (honest, never synthesized).

    allow_reconstruction: when True (default), if no genuine prior snapshot exists,
    reconstruct Time A from historical signal_snapshots (one broad scan). Hot
    surfaces that call this for many tickers per page load (digest, watchlist)
    should pass False to stay on the cheap genuine-snapshot path only.
    """
    from utils import score_attribution as sa

    b = get_latest_components(ticker)
    if not b:
        return {"state": "no_comparison",
                "reason": "No score snapshot has been recorded for this ticker yet."}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    a = get_components_on_or_before(ticker, cutoff)

    # No genuine prior component snapshot yet → RECONSTRUCT one from the real
    # historical per-signal scores in signal_snapshots (current weighting applied
    # to historical readings). This is what makes attribution work before genuine
    # component history has accrued. Honestly flagged reconstructed=True.
    if not a and allow_reconstruction:
        hist = get_signal_scores_asof(cutoff)
        a = sa.reconstruct_prior(b, hist, as_of_date=cutoff) if hist else None

    # If even reconstruction isn't possible, fall back to the OLDEST genuine
    # snapshot we have so a comparison is still possible (labeled by its real date).
    if not a:
        try:
            with db.engine.begin() as conn:
                row = conn.execute(
                    select(score_components)
                    .where(score_components.c.ticker == ticker.upper().strip())
                    .order_by(score_components.c.snapshot_date.asc())
                    .limit(1)
                ).mappings().first()
            a = _parse_components_row(row)
        except Exception:
            a = None
        if a and a.get("snapshot_date") == b.get("snapshot_date"):
            a = None  # only one snapshot exists → nothing to compare
    label = _window_label(days_back)
    return sa.attribute_move(a, b,
                             from_date=(a or {}).get("snapshot_date"),
                             to_date=b.get("snapshot_date"),
                             window_label=label)


def _window_label(days_back: int) -> str:
    return {1: "since yesterday", 7: "this week", 30: "this month"}.get(
        days_back, f"over {days_back} days")


def explain_move_smart(ticker: str) -> dict:
    """
    Pick the most relevant comparison window automatically: prefer 1D if today's
    move is already material, else 7D, else 30D — so the user doesn't have to
    discover that the meaningful change happened a week ago. Returns the same
    engine result, with the chosen window reflected in window_label / days_back.
    """
    MATERIAL = 3.0  # points — a move worth explaining
    best = None
    for days in (1, 7, 30):
        res = explain_move(ticker, days_back=days)
        if res.get("state") in ("ok", "insufficient_coverage"):
            res["days_back"] = days
            if abs(res.get("total_change", 0.0)) >= MATERIAL:
                return res
            best = best or res  # remember the first usable (small-move) window
    # No window had a material move; return the shortest usable comparison, or the
    # honest no_comparison state.
    return best or explain_move(ticker, days_back=7)


def get_score_history(ticker: str, days: int = 180, kind: str | None = None) -> list[dict]:
    """
    Return up to `days` worth of snapshot rows for `ticker`, oldest first
    -- exactly what's actually been recorded, no interpolation or
    backfilling of missing days. A ticker nobody has viewed recently (or
    ever) legitimately returns an empty or sparse list; callers must
    treat that as "not enough history yet," never synthesize a fake trend.
    """
    ticker = ticker.upper().strip()
    query = select(score_snapshots).where(score_snapshots.c.ticker == ticker)
    if kind == "full":
        query = query.where(
            or_(score_snapshots.c.score_kind == "full", score_snapshots.c.score_kind.is_(None))
        )
    elif kind:
        query = query.where(score_snapshots.c.score_kind == kind)
    with db.engine.begin() as conn:
        rows = conn.execute(
            query.order_by(score_snapshots.c.snapshot_date.desc()).limit(days)
        ).mappings().all()
    return [dict(r) for r in reversed(rows)]


def record_signal_snapshot(signal_id: str, score: float, status: str) -> None:
    """
    Upsert today's snapshot for a single signal. Safe to call on every
    Today's Brief page visit -- same upsert-on-conflict pattern as
    record_score_snapshot(), one row per (signal_id, day).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()
    stmt = upsert_stmt(signal_snapshots, ["signal_id", "snapshot_date"]).values(
        signal_id=signal_id, snapshot_date=today,
        score=score, status=status, created_at=now_iso,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["signal_id", "snapshot_date"],
        set_={"score": score, "status": status, "created_at": now_iso},
    )
    with db.engine.begin() as conn:
        conn.execute(stmt)


def record_all_signal_snapshots(scores: dict) -> None:
    """
    Batch-upsert today's snapshot for ALL signals in a single DB transaction.
    Replaces the old loop of 40 individual record_signal_snapshot() calls in
    Today's Brief — 40 connections → 1 connection, 40 round-trips → 1.

    `scores` is the dict returned by get_all_signal_scores() from
    utils.signals_cache: {sig_id: {score, status, error, ...}}.

    Best-effort — any DB error is silently swallowed so a snapshot failure
    never takes down the page.
    """
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "signal_id":     sig_id,
            "snapshot_date": today,
            "score":         float(sv.get("score", 50)),
            "status":        sv.get("status", "neutral"),
            "created_at":    now_iso,
        }
        for sig_id, sv in scores.items()
        if not sv.get("error", True)  # skip errored signals
    ]
    if not rows:
        return
    try:
        with db.engine.begin() as conn:
            for row in rows:
                stmt = upsert_stmt(signal_snapshots, ["signal_id", "snapshot_date"]).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["signal_id", "snapshot_date"],
                    set_={
                        "score":      row["score"],
                        "status":     row["status"],
                        "created_at": row["created_at"],
                    },
                )
                conn.execute(stmt)
    except Exception:
        pass


def get_signal_flips(days_back: int = 1) -> list[dict]:
    """
    Return signals whose status CHANGED between their most recent snapshot
    and the snapshot from `days_back` days ago. Used by Today's Brief to
    show "X signals flipped since yesterday."

    Only signals with at least 2 snapshots in the window are considered.
    Returns a list of dicts with signal_id, from_status, to_status, from_date, to_date.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(signal_snapshots)
                .where(signal_snapshots.c.snapshot_date >= cutoff)
                .order_by(signal_snapshots.c.signal_id, signal_snapshots.c.snapshot_date)
            ).mappings().all()
    except Exception:
        return []

    if not rows:
        return []

    from collections import defaultdict
    by_sig = defaultdict(list)
    for r in rows:
        by_sig[r["signal_id"]].append(dict(r))

    flips = []
    for sig_id, snaps in by_sig.items():
        if len(snaps) < 2:
            continue
        earliest = snaps[0]
        latest = snaps[-1]
        if earliest["status"] != latest["status"]:
            flips.append({
                "signal_id":   sig_id,
                "from_status": earliest["status"],
                "to_status":   latest["status"],
                "from_date":   earliest["snapshot_date"],
                "to_date":     latest["snapshot_date"],
                "to_score":    latest["score"],
            })
    return flips


def get_signal_trends(days_back: int = 7) -> dict[str, dict]:
    """
    Compare each signal's current snapshot to its snapshot from `days_back`
    days ago. Returns a dict keyed by signal_id:

        {signal_id: {"trend": "up"|"down"|"flat"|"new", "delta": float}}

    "new"  = no prior snapshot exists (signal is new or never seen before).
    "up"   = score increased by >2 points.
    "down" = score decreased by >2 points.
    "flat" = score changed by ≤2 points.

    Used by the Signal Dashboard to show ▲▼ trend indicators next to
    each signal score — tells users whether momentum is building or fading.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(signal_snapshots)
                .where(signal_snapshots.c.snapshot_date >= cutoff)
                .order_by(signal_snapshots.c.signal_id, signal_snapshots.c.snapshot_date)
            ).mappings().all()
    except Exception:
        return {}

    from collections import defaultdict
    by_sig: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_sig[str(r["signal_id"])].append(dict(r))

    result: dict[str, dict] = {}
    for sig_id, snaps in by_sig.items():
        if len(snaps) < 2:
            result[sig_id] = {"trend": "new", "delta": 0.0}
            continue
        earliest_score = float(snaps[0].get("score", 50) or 50)
        latest_score   = float(snaps[-1].get("score", 50) or 50)
        delta = latest_score - earliest_score
        if delta > 2:
            trend = "up"
        elif delta < -2:
            trend = "down"
        else:
            trend = "flat"
        result[sig_id] = {"trend": trend, "delta": round(delta, 1)}

    return result


def get_signal_streaks(days_back: int = 90) -> dict[str, dict]:
    """
    For each signal, count how many consecutive days it has held its
    CURRENT status (bullish/bearish/neutral) by scanning recent snapshots
    backwards from today.

    Returns:
        {signal_id: {"status": str, "days": int, "weeks": int, "label": str}}

    Where label is the human-readable fatigue indicator:
        "🟢 Fresh"      → ≤7 days in current status
        "📊 Established" → 8–21 days
        "⏳ Extended"   → 22–56 days
        "🔴 Exhausted"  → >56 days (8+ weeks, fading edge)

    Rationale: signals that just flipped carry the most forward-looking
    information. A signal bullish for 12 weeks has already been priced in
    by anyone watching. Fresh flips are where the real edge lives.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(signal_snapshots)
                .where(signal_snapshots.c.snapshot_date >= cutoff)
                .order_by(signal_snapshots.c.signal_id, signal_snapshots.c.snapshot_date.desc())
            ).mappings().all()
    except Exception:
        return {}

    from collections import defaultdict
    by_sig: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_sig[str(r["signal_id"])].append(dict(r))

    result: dict[str, dict] = {}
    for sig_id, snaps in by_sig.items():
        if not snaps:
            continue
        current_status = snaps[0].get("status", "neutral")
        # Walk backwards through snapshots (already desc-ordered) counting
        # consecutive days with the same status
        streak_days = 0
        for snap in snaps:
            if snap.get("status") == current_status:
                streak_days += 1
            else:
                break  # streak broken — stop counting
        # streak_days here is the number of snapshot records, not calendar days.
        # Each snapshot is one per day (from record_all_signal_snapshots), so
        # this approximates calendar days accurately for active signals.
        weeks = streak_days // 7
        if streak_days <= 7:
            label = "🟢 Fresh"
        elif streak_days <= 21:
            label = "📊 Established"
        elif streak_days <= 56:
            label = f"⏳ Extended {weeks}w"
        else:
            label = f"🔴 Exhausted {weeks}w"

        result[sig_id] = {
            "status": current_status,
            "days":   streak_days,
            "weeks":  weeks,
            "label":  label,
        }

    return result


def get_signal_diff(days_back: int = 7, persisted_only: bool = False) -> dict:
    """
    Compare current signal states to their states from `days_back` days ago.
    Returns a structured diff used by Today's Brief "What Changed" section.

    Returns:
        {
            "flipped_bullish": [{"signal_id", "name", "from_score", "to_score"}],
            "flipped_bearish": [{"signal_id", "name", "from_score", "to_score"}],
            "biggest_movers":  [{"signal_id", "name", "delta", "direction"}],
            "total_flips":     int,
            "regime_shift":    str | None,  # "RISK-ON → MIXED" if regime changed
        }
    """
    from utils.config import SIGNALS

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(signal_snapshots)
                .where(signal_snapshots.c.snapshot_date >= cutoff)
                .order_by(signal_snapshots.c.signal_id, signal_snapshots.c.snapshot_date)
            ).mappings().all()
    except Exception:
        return {"flipped_bullish": [], "flipped_bearish": [], "biggest_movers": [],
                "total_flips": 0, "regime_shift": None}

    from collections import defaultdict
    by_sig: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_sig[str(r["signal_id"])].append(dict(r))

    if persisted_only:
        current_scores = get_latest_signal_states()
    else:
        from utils.signals_cache import get_all_signal_scores
        current_scores = get_all_signal_scores()

    flipped_bull, flipped_bear, movers = [], [], []

    for sig_id, snaps in by_sig.items():
        if len(snaps) < 2:
            continue
        old_snap  = snaps[0]
        curr      = current_scores.get(sig_id, {})
        if curr.get("error"):
            continue
        old_status  = old_snap.get("status", "neutral")
        new_status  = curr.get("status", "neutral")
        old_score   = float(old_snap.get("score", 50) or 50)
        new_score   = float(curr.get("score", 50) or 50)
        delta       = new_score - old_score
        name        = curr.get("name") or SIGNALS.get(sig_id, {}).get("name", sig_id)

        if old_status != new_status:
            entry = {"signal_id": sig_id, "name": name,
                     "from_score": old_score, "to_score": new_score,
                     "from_status": old_status, "to_status": new_status}
            if new_status == "bullish":
                flipped_bull.append(entry)
            elif new_status == "bearish":
                flipped_bear.append(entry)

        if abs(delta) >= 5:
            movers.append({"signal_id": sig_id, "name": name, "delta": round(delta, 1),
                           "direction": "up" if delta > 0 else "down",
                           # from/to scores + category added so the "What Changed"
                           # engine (utils/what_changed.py) can render "41 → 57" and
                           # map the move to sectors without a second DB round-trip.
                           "from_score": round(old_score, 1), "to_score": round(new_score, 1),
                           "category": SIGNALS.get(sig_id, {}).get("category")})

    movers.sort(key=lambda x: -abs(x["delta"]))

    # Regime shift: compare bull% then vs now
    old_counts = defaultdict(int)
    for sig_id, snaps in by_sig.items():
        if snaps:
            old_counts[snaps[0].get("status", "neutral")] += 1
    old_total = max(1, sum(old_counts.values()))

    curr_bull  = sum(1 for v in current_scores.values()
                     if not v.get("error") and v.get("status") == "bullish")
    curr_bear  = sum(1 for v in current_scores.values()
                     if not v.get("error") and v.get("status") == "bearish")
    curr_total = max(1, curr_bull + curr_bear +
                     sum(1 for v in current_scores.values()
                         if not v.get("error") and v.get("status") == "neutral"))

    def _regime(bull, bear, total):
        bp = bull / total
        brp = bear / total
        if bp >= 0.58: return "RISK-ON"
        if brp >= 0.52: return "RISK-OFF"
        if bp >= 0.48: return "LEANING BULLISH"
        if brp >= 0.44: return "LEANING BEARISH"
        return "MIXED"

    old_regime = _regime(old_counts["bullish"], old_counts["bearish"], old_total)
    new_regime = _regime(curr_bull, curr_bear, curr_total)
    regime_shift = f"{old_regime} → {new_regime}" if old_regime != new_regime else None

    return {
        "flipped_bullish": sorted(flipped_bull, key=lambda x: -x["to_score"]),
        "flipped_bearish": sorted(flipped_bear, key=lambda x:  x["to_score"]),
        "biggest_movers":  movers[:5],
        "total_flips":     len(flipped_bull) + len(flipped_bear),
        "regime_shift":    regime_shift,
        "days_back":       days_back,
    }

def get_signals_near_threshold(margin: float = 5.0) -> dict:
    """
    Find signals within `margin` points of a status-change threshold.

    Thresholds (matching signal card color bands in the UI):
        Bearish flip: score ≤ 35  → watch for score approaching 35 from above
        Bullish flip: score ≥ 65  → watch for score approaching 65 from below

    Returns:
        {
            "near_bullish_flip": [  # currently neutral/bearish, approaching ≥65
                {signal_id, name, score, pts_away, trend, velocity_per_week, category}, ...
            ],
            "near_bearish_flip": [  # currently neutral/bullish, approaching ≤35
                {signal_id, name, score, pts_away, trend, velocity_per_week, category}, ...
            ],
        }

    Each entry is sorted by pts_away ascending (closest first), velocity
    used to estimate how many weeks until threshold.

    This is the single most actionable section on the site: by the time a
    signal HAS flipped, it's already news. This shows what's ABOUT to flip.
    """
    from utils.signals_cache import get_all_signal_scores
    from utils.config import SIGNALS

    BULL_THRESHOLD = 65.0
    BEAR_THRESHOLD = 35.0

    try:
        current = get_all_signal_scores()
        trends  = get_signal_trends(days_back=7)
    except Exception:
        return {"near_bullish_flip": [], "near_bearish_flip": []}

    near_bull, near_bear = [], []

    for sig_id, sv in current.items():
        if sv.get("error"):
            continue
        score   = float(sv.get("score", 50) or 50)
        status  = sv.get("status", "neutral")
        name    = sv.get("name") or SIGNALS.get(sig_id, {}).get("name", sig_id)
        category = sv.get("category") or SIGNALS.get(sig_id, {}).get("category", "")

        trend_data = trends.get(sig_id, {})
        delta_7d   = trend_data.get("delta", 0.0)           # pts change over 7 days
        velocity   = round(delta_7d, 1)                      # pts per week
        trend_dir  = trend_data.get("trend", "flat")

        # Near bullish flip: score is below 65 but within margin, and trending UP
        if status in ("neutral", "bearish") and (BULL_THRESHOLD - score) <= margin:
            pts_away = round(BULL_THRESHOLD - score, 1)
            # ETA: how many weeks at current velocity (None if flat/wrong direction)
            eta_weeks: float | None = None
            if velocity > 0 and pts_away > 0:
                eta_weeks = round(pts_away / velocity, 1)
            near_bull.append({
                "signal_id":        sig_id,
                "name":             name,
                "score":            round(score, 1),
                "pts_away":         pts_away,
                "trend":            trend_dir,
                "velocity_per_week": velocity,
                "eta_weeks":        eta_weeks,
                "category":         category,
                "current_status":   status,
            })

        # Near bearish flip: score is above 35 but within margin, and trending DOWN
        if status in ("neutral", "bullish") and (score - BEAR_THRESHOLD) <= margin:
            pts_away = round(score - BEAR_THRESHOLD, 1)
            eta_weeks = None
            if velocity < 0 and pts_away > 0:
                eta_weeks = round(pts_away / abs(velocity), 1)
            near_bear.append({
                "signal_id":        sig_id,
                "name":             name,
                "score":            round(score, 1),
                "pts_away":         pts_away,
                "trend":            trend_dir,
                "velocity_per_week": velocity,
                "eta_weeks":        eta_weeks,
                "category":         category,
                "current_status":   status,
            })

    # Sort by pts_away ascending (closest to flipping first)
    near_bull.sort(key=lambda x: x["pts_away"])
    near_bear.sort(key=lambda x: x["pts_away"])

    return {
        "near_bullish_flip": near_bull,
        "near_bearish_flip": near_bear,
    }


def compute_signal_correlation_matrix(days_back: int = 90) -> dict:
    """
    Compute pairwise Pearson correlations across all signal score histories.

    Returns:
        {
            "signals":        list[str],      # signal IDs in matrix order
            "names":          list[str],      # display names
            "matrix":         list[list[float]],   # n×n correlation matrix
            "effective_n":    float,          # "independent signal count" via eigenvalues
            "total_signals":  int,
            "days_used":      int,
            "sparse":         bool,           # True if <10 signals had enough history
        }

    "effective_n" is the Effective Number of Independent Signals from
    the eigenvalue decomposition of the correlation matrix. This is the
    number that answers: "how many truly independent data points are these
    N signals?" If 20 signals have effective_n=6, then 14 are redundant
    with the other 6 — bulk conviction is lower than raw count implies.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(signal_snapshots)
                .where(signal_snapshots.c.snapshot_date >= cutoff)
                .order_by(signal_snapshots.c.signal_id, signal_snapshots.c.snapshot_date)
            ).mappings().all()
    except Exception:
        return {"sparse": True, "signals": [], "names": [], "matrix": [],
                "effective_n": 0.0, "total_signals": 0, "days_used": days_back}

    if not rows:
        return {"sparse": True, "signals": [], "names": [], "matrix": [],
                "effective_n": 0.0, "total_signals": 0, "days_used": days_back}

    from collections import defaultdict
    from utils.config import SIGNALS
    from utils.signals_cache import get_all_signal_scores

    # Build date × signal pivot
    by_sig: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        by_sig[str(r["signal_id"])][r["snapshot_date"]] = float(r["score"])

    # Only keep signals with ≥14 data points (2+ weeks)
    sig_ids   = [s for s, d in by_sig.items() if len(d) >= 14]
    if len(sig_ids) < 3:
        return {"sparse": True, "signals": sig_ids, "names": [],
                "matrix": [], "effective_n": 0.0,
                "total_signals": len(sig_ids), "days_used": days_back}

    # Union of all dates
    all_dates = sorted({d for s in sig_ids for d in by_sig[s].keys()})

    # Build matrix: fill missing dates with NaN, then drop rows with >30% NaN
    import numpy as np

    n_sig  = len(sig_ids)
    n_date = len(all_dates)
    mat    = np.full((n_date, n_sig), np.nan)
    for j, sig in enumerate(sig_ids):
        for i, dt in enumerate(all_dates):
            if dt in by_sig[sig]:
                mat[i, j] = by_sig[sig][dt]

    # Drop date rows where >30% of signals are NaN
    valid_rows = np.sum(~np.isnan(mat), axis=1) >= (n_sig * 0.7)
    mat = mat[valid_rows]

    # Forward-fill NaN within each column (signal)
    for j in range(n_sig):
        col = mat[:, j]
        mask = np.isnan(col)
        idx  = np.where(~mask, np.arange(len(col)), 0)
        np.maximum.accumulate(idx, out=idx)
        col[mask] = col[idx[mask]]
        mat[:, j] = col

    # Drop columns still containing NaN after ffill
    valid_cols = ~np.any(np.isnan(mat), axis=0)
    mat      = mat[:, valid_cols]
    sig_ids  = [s for s, v in zip(sig_ids, valid_cols) if v]

    if mat.shape[1] < 3:
        return {"sparse": True, "signals": sig_ids, "names": [],
                "matrix": [], "effective_n": 0.0,
                "total_signals": len(sig_ids), "days_used": days_back}

    # Pearson correlation matrix
    corr = np.corrcoef(mat, rowvar=False)

    # Effective N: sum of eigenvalues ÷ max_eigenvalue
    eigvals = np.linalg.eigvalsh(corr)
    eigvals = np.maximum(eigvals, 0)  # clip tiny negatives from floating-point
    effective_n = round(float(np.sum(eigvals) / max(eigvals.max(), 1e-9)), 2)

    # Names lookup
    curr = get_all_signal_scores()
    names = []
    for sid in sig_ids:
        sv = curr.get(sid, {})
        names.append(sv.get("name") or SIGNALS.get(sid, {}).get("name", sid))

    return {
        "signals":       sig_ids,
        "names":         names,
        "matrix":        corr.round(3).tolist(),
        "effective_n":   effective_n,
        "total_signals": len(sig_ids),
        "days_used":     days_back,
        "sparse":        False,
    }


def get_high_confidence_snapshot_calls(
    min_score: float = 70.0,
    days_back: int = 180,
    min_days_ago: int = 35,
) -> list[dict]:
    """
    Pull historical score snapshot rows where the model expressed high
    confidence — score >= min_score (bullish) or score <= (100 - min_score)
    (bearish) — and the snapshot is old enough (>= min_days_ago) that a
    30-day forward window has already expired.

    Returns DB rows only — no price data. The caller (page) is responsible
    for fetching prices and computing returns, ideally cached via
    @st.cache_data to avoid repeated yfinance hits.

    These are RETROSPECTIVE lookups, not logged advance predictions.
    The distinction must be stated clearly in any UI that displays them:
    we are asking "what did the stock do 30 days after the model gave it a
    high score?" not "the model predicted this outcome in advance."
    """
    today = datetime.now(timezone.utc).date()
    cutoff_old  = (today - timedelta(days=min_days_ago)).isoformat()
    cutoff_new  = (today - timedelta(days=days_back)).isoformat()
    bear_thresh = round(100.0 - min_score, 1)

    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(score_snapshots)
                .where(score_snapshots.c.snapshot_date <= cutoff_old)
                .where(score_snapshots.c.snapshot_date >= cutoff_new)
                .where(
                    (score_snapshots.c.score >= min_score) |
                    (score_snapshots.c.score <= bear_thresh)
                )
                .order_by(score_snapshots.c.snapshot_date.desc())
                .limit(200)
            ).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_batch_velocity_stats(
    tickers: list[str],
    window_days: int = 5,
    history_days: int = 60,
) -> dict[str, dict | None]:
    """
    Batch version of get_score_velocity_stats — ONE SQL query for all tickers.

    Fetches the last `history_days` of score_snapshots for every ticker in
    `tickers`, then computes rolling-window velocity stats for each. Returns
    a dict keyed by ticker; value is the same shape as get_score_velocity_stats()
    or None if the ticker has insufficient data (< window_days + 3 records).

    Use this whenever you need velocity for 10+ tickers simultaneously:
    one round-trip is dramatically faster than N individual calls.
    """
    if not tickers:
        return {}

    from datetime import date as _date
    import numpy as _np

    cutoff = (datetime.now(timezone.utc) - timedelta(days=history_days)).strftime("%Y-%m-%d")

    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(score_snapshots)
                .where(score_snapshots.c.ticker.in_(tickers))
                .where(score_snapshots.c.snapshot_date >= cutoff)
                .order_by(score_snapshots.c.ticker, score_snapshots.c.snapshot_date)
            ).mappings().all()
    except Exception:
        return {t: None for t in tickers}

    # Group by ticker
    from collections import defaultdict
    by_ticker: dict[str, list[tuple]] = defaultdict(list)
    for r in rows:
        if r.get("score") is not None:
            by_ticker[r["ticker"]].append((r["snapshot_date"], float(r["score"])))

    def _velocity(window: list[tuple]) -> float | None:
        if len(window) < 2:
            return None
        t0 = _date.fromisoformat(window[0][0])
        t1 = _date.fromisoformat(window[-1][0])
        days_span = max((t1 - t0).days, 1)
        return (window[-1][1] - window[0][1]) / days_span

    result: dict[str, dict | None] = {}
    for ticker in tickers:
        entries = by_ticker.get(ticker, [])
        if len(entries) < window_days + 3:
            result[ticker] = None
            continue

        all_velocities: list[float] = []
        for i in range(len(entries) - window_days + 1):
            v = _velocity(entries[i : i + window_days])
            if v is not None:
                all_velocities.append(v)

        if len(all_velocities) < 4:
            result[ticker] = None
            continue

        current_vel = all_velocities[-1]
        baseline    = all_velocities[:-1]
        abs_current = abs(current_vel)
        abs_baseline = _np.abs(baseline)
        percentile = float(_np.mean(abs_baseline < abs_current) * 100)

        result[ticker] = {
            "velocity":    round(current_vel, 2),
            "percentile":  round(percentile, 1),
            "n_windows":   len(baseline),
            "direction":   "up" if current_vel >= 0 else "down",
            "window_days": window_days,
        }

    # Tickers with no snapshots at all → None
    for ticker in tickers:
        if ticker not in result:
            result[ticker] = None

    return result


def get_score_velocity_stats(ticker: str, window_days: int = 5) -> dict | None:
    """
    Compute the current score velocity (pts/day) over the last `window_days`
    snapshot records, then rank it against all historical rolling windows of
    the same length for this ticker.

    Returns:
        {
            "velocity":    float,   # pts/day (+ = rising, - = falling)
            "percentile":  float,   # 0–100 where absolute velocity ranks vs history
            "n_windows":   int,     # number of historical windows used for ranking
            "direction":   str,     # "up" | "down"
            "window_days": int,
        }

    Returns None if the ticker has fewer than `window_days` + 3 recorded
    snapshots (not enough baseline history to compute a meaningful percentile).

    Notes on design:
    - Velocity uses the actual calendar-day span between first and last snapshot
      in the window (so sparse history doesn't inflate the velocity number).
    - Percentile is on ABSOLUTE velocity: a -3 pt/day crash ranks the same as
      a +3 pt/day surge — both are unusual. The direction field separates them.
    - Historical baseline excludes the current window so the percentile is
      genuinely out-of-sample.
    """
    from datetime import date as _date

    history = get_score_history(ticker, days=180)
    # Need at least window_days for the current snapshot + 3 more for a baseline
    if len(history) < window_days + 3:
        return None

    # Keep only rows with a valid score
    entries = [
        (h["snapshot_date"], float(h["score"]))
        for h in history
        if h.get("score") is not None
    ]
    if len(entries) < window_days + 3:
        return None

    def _velocity(window: list[tuple]) -> float | None:
        if len(window) < 2:
            return None
        t0 = _date.fromisoformat(window[0][0])
        t1 = _date.fromisoformat(window[-1][0])
        days_span = max((t1 - t0).days, 1)
        return (window[-1][1] - window[0][1]) / days_span

    # All rolling windows (stride = 1)
    all_velocities: list[float] = []
    for i in range(len(entries) - window_days + 1):
        v = _velocity(entries[i : i + window_days])
        if v is not None:
            all_velocities.append(v)

    if len(all_velocities) < 4:  # need enough history for a meaningful percentile
        return None

    current_vel = all_velocities[-1]                # most recent window
    baseline    = all_velocities[:-1]               # exclude current from ranking

    # Percentile by absolute magnitude (unusual speed in either direction)
    import numpy as _np
    abs_current = abs(current_vel)
    abs_baseline = _np.abs(baseline)
    percentile = float(_np.mean(abs_baseline < abs_current) * 100)

    return {
        "velocity":    round(current_vel, 2),
        "percentile":  round(percentile, 1),
        "n_windows":   len(baseline),
        "direction":   "up" if current_vel >= 0 else "down",
        "window_days": window_days,
    }


def compute_sector_percentiles(
    positions: list[dict],
    max_peers: int = 6,
    max_age_days: int = 30,
) -> dict[str, dict]:
    """Build same-score-kind sector context for many tickers in one DB read."""
    normalized: list[dict] = []
    for item in positions or []:
        try:
            ticker = str(item.get("ticker", "")).upper().strip()
            score = float(item["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if ticker:
            normalized.append({
                "ticker": ticker,
                "score": score,
                "score_kind": str(item.get("score_kind") or "full"),
            })

    peer_map = {
        item["ticker"]: get_sector_peers(item["ticker"], max_peers=max_peers)
        for item in normalized
    }
    peer_tickers = sorted({peer for peers in peer_map.values() for peer in peers})
    latest: dict[tuple[str, str], dict] = {}
    if peer_tickers:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, int(max_age_days)))).strftime("%Y-%m-%d")
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(score_snapshots)
                .where(score_snapshots.c.ticker.in_(peer_tickers))
                .where(score_snapshots.c.snapshot_date >= cutoff)
                .order_by(score_snapshots.c.snapshot_date.desc())
            ).mappings().all()
        for row in rows:
            row_kind = str(row.get("score_kind") or "full")
            latest.setdefault((str(row["ticker"]), row_kind), dict(row))

    contexts: dict[str, dict] = {}
    for item in normalized:
        ticker = item["ticker"]
        peers = peer_map.get(ticker) or []
        if not peers:
            contexts[ticker] = {
                "error": "No sector peers found for this ticker",
                "n_peers": 0,
                "n_possible_peers": 0,
                "score_kind": item["score_kind"],
            }
            continue

        peer_scores = []
        for peer in peers:
            row = latest.get((peer, item["score_kind"]))
            if row:
                peer_scores.append({
                    "ticker": peer,
                    "score": float(row["score"]),
                    "as_of": row["snapshot_date"],
                    "score_kind": item["score_kind"],
                })
        if not peer_scores:
            contexts[ticker] = {
                "error": (
                    f"No same-type sector peer scores were recorded in the last "
                    f"{max(1, int(max_age_days))} days"
                ),
                "n_peers": 0,
                "n_possible_peers": len(peers),
                "score_kind": item["score_kind"],
            }
            continue

        scores = [row["score"] for row in peer_scores]
        score = item["score"]
        rank = 1 + sum(1 for peer_score in scores if peer_score > score)
        universe_size = len(scores) + 1
        percentile = (
            100.0 if universe_size == 1
            else 100.0 * (universe_size - rank) / (universe_size - 1)
        )
        sorted_scores = sorted(scores)
        middle = len(sorted_scores) // 2
        sector_median = (
            sorted_scores[middle]
            if len(sorted_scores) % 2
            else (sorted_scores[middle - 1] + sorted_scores[middle]) / 2.0
        )
        contexts[ticker] = {
            "error": None,
            "percentile": round(percentile, 1),
            "rank": rank,
            "universe_size": universe_size,
            "n_peers": len(peer_scores),
            "n_possible_peers": len(peers),
            "peer_scores": peer_scores,
            "sector_avg": round(sum(scores) / len(scores), 1),
            "sector_median": round(sector_median, 1),
            "delta_vs_median": round(score - sector_median, 1),
            "score_kind": item["score_kind"],
            "oldest_peer_as_of": min(row["as_of"] for row in peer_scores),
            "newest_peer_as_of": max(row["as_of"] for row in peer_scores),
        }
    return contexts


def compute_sector_percentile(
    ticker: str,
    score: float,
    max_peers: int = 6,
    score_kind: str = "full",
    max_age_days: int = 30,
) -> dict:
    """
    Where `score` (the ticker's CURRENT, just-computed score) ranks
    against its sector peers' most recently RECORDED scores.

    Deliberately built on the snapshot history above rather than live-
    scoring every peer on every page view: computing a peer's full
    Confluence Score means re-running its own signal/price/insider/13F
    fetch pipeline, and doing that for up to 6 peers on every single
    ticker view would multiply this page's real cost several times over
    for a "nice to have" comparison number. Reusing whatever's already
    been recorded is free (a few indexed DB reads) and ties naturally
    into the same organic, traffic-driven history this module already
    builds.

    Honest tradeoff this creates, stated plainly rather than hidden: a
    peer's score here is whatever it was AS OF that peer's last view, not
    a live number -- two peers compared "at the same time" may actually
    be several days or weeks apart. `peer_scores` always includes each
    peer's `as_of` date so a caller (or the UI) can show that, not just
    the number.
    """
    return compute_sector_percentiles(
        [{"ticker": ticker, "score": score, "score_kind": score_kind}],
        max_peers=max_peers,
        max_age_days=max_age_days,
    ).get(ticker.upper().strip(), {
        "error": "No sector peers found for this ticker",
        "n_peers": 0,
        "n_possible_peers": 0,
        "score_kind": score_kind,
    })
