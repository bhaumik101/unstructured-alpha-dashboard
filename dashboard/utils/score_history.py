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

from sqlalchemy import select

from utils import db
from utils.db import score_snapshots, signal_snapshots, upsert_stmt
from utils.lead_time_research import get_sector_peers


def record_score_snapshot(ticker: str, score: float, case: str, conviction: str) -> None:
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

    stmt = upsert_stmt(score_snapshots, ["ticker", "snapshot_date"]).values(
        ticker=ticker, snapshot_date=today, score=score, case=case,
        conviction=conviction, created_at=now_iso,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker", "snapshot_date"],
        set_={"score": score, "case": case, "conviction": conviction, "created_at": now_iso},
    )
    with db.engine.begin() as conn:
        conn.execute(stmt)


def get_score_history(ticker: str, days: int = 180) -> list[dict]:
    """
    Return up to `days` worth of snapshot rows for `ticker`, oldest first
    -- exactly what's actually been recorded, no interpolation or
    backfilling of missing days. A ticker nobody has viewed recently (or
    ever) legitimately returns an empty or sparse list; callers must
    treat that as "not enough history yet," never synthesize a fake trend.
    """
    ticker = ticker.upper().strip()
    with db.engine.begin() as conn:
        rows = conn.execute(
            select(score_snapshots)
            .where(score_snapshots.c.ticker == ticker)
            .order_by(score_snapshots.c.snapshot_date.desc())
            .limit(days)
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


def get_signal_diff(days_back: int = 7) -> dict:
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
    from utils.signals_cache import get_all_signal_scores
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
                           "direction": "up" if delta > 0 else "down"})

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

def compute_sector_percentile(ticker: str, score: float, max_peers: int = 6) -> dict:
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
    peers = get_sector_peers(ticker, max_peers=max_peers)
    if not peers:
        return {"error": "No sector peers found for this ticker", "n_peers": 0}

    peer_scores = []
    for peer in peers:
        hist = get_score_history(peer, days=30)
        if hist:
            peer_scores.append({"ticker": peer, "score": hist[-1]["score"], "as_of": hist[-1]["snapshot_date"]})

    if not peer_scores:
        return {
            "error": "None of this ticker's sector peers have a recent recorded score yet",
            "n_peers": 0,
        }

    all_scores = [p["score"] for p in peer_scores] + [score]
    rank = sum(1 for s in all_scores if s <= score)
    percentile = round(100.0 * rank / len(all_scores), 1)
    sector_avg = round(sum(p["score"] for p in peer_scores) / len(peer_scores), 1)

    return {
        "error": None,
        "percentile": percentile,
        "n_peers": len(peer_scores),
        "peer_scores": peer_scores,
        "sector_avg": sector_avg,
    }
