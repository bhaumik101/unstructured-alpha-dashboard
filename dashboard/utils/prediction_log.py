"""
utils/prediction_log.py
=======================
Auditable prediction logging and auto-resolution.

Every convergence event and score crossing is logged here with a timestamp
and entry price. When the 4w/8w/12w forward windows expire, resolve_pending()
automatically fills in actual returns and marks predictions correct/incorrect.

The resulting track record is the most credibility-building feature on the
site: a public, machine-generated, auditable log of every prediction made,
with real outcomes attached. Nobody else offers this for free.

Honesty constraints enforced in this module:
- Predictions only logged ONCE per (ticker, event_date, event_type) via
  the unique constraint — no retroactive backdating.
- Resolutions only written when the forward date is in the past and price
  data is actually available — never estimated or interpolated.
- "correct" is defined simply and conservatively:
    - bull prediction: correct if return_Nw > 0
    - bear prediction: correct if return_Nw < 0
  No cherry-picking of thresholds after the fact.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from utils import db
from utils.db import prediction_log, system_notifications, upsert_stmt


# ── Logging ───────────────────────────────────────────────────────────────────

def log_prediction(
    ticker: str,
    event_type: str,              # "convergence" | "score_cross_bull" | "score_cross_bear"
    direction: str,               # "bull" | "bear"
    score: float,
    price: float | None,
    signal_count: int = 0,
    signals_triggered: list[str] | None = None,   # e.g. ["crude_inventories", "gas_storage"]
) -> bool:
    """
    Log one prediction. Returns True if a new row was inserted, False if
    this (ticker, today, event_type) already existed (idempotent).

    Caller is responsible for fetching the current price — this module
    doesn't import yfinance to keep it fast and avoid circular imports.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()
    signals_str = ",".join(signals_triggered) if signals_triggered else None

    try:
        stmt = upsert_stmt(prediction_log, ["ticker", "event_date", "event_type"]).values(
            ticker=ticker.upper(),
            event_type=event_type,
            direction=direction,
            score_at_event=round(score, 1),
            signal_count=signal_count,
            price_at_event=price,
            price_source=("observed" if price is not None else None),
            event_date=today,
            status="pending",
            signals_triggered=signals_str,
            created_at=now_iso,
        )
        # ON CONFLICT DO NOTHING — don't overwrite an existing prediction
        if db.IS_SQLITE:
            from sqlalchemy.dialects.sqlite import insert as _si
            stmt = _si(prediction_log).values(
                ticker=ticker.upper(),
                event_type=event_type,
                direction=direction,
                score_at_event=round(score, 1),
                signal_count=signal_count,
                price_at_event=price,
                price_source=("observed" if price is not None else None),
                event_date=today,
                status="pending",
                signals_triggered=signals_str,
                created_at=now_iso,
            ).on_conflict_do_nothing(
                index_elements=["ticker", "event_date", "event_type"]
            )
        else:
            from sqlalchemy.dialects.postgresql import insert as _pi
            stmt = _pi(prediction_log).values(
                ticker=ticker.upper(),
                event_type=event_type,
                direction=direction,
                score_at_event=round(score, 1),
                signal_count=signal_count,
                price_at_event=price,
                price_source=("observed" if price is not None else None),
                event_date=today,
                status="pending",
                signals_triggered=signals_str,
                created_at=now_iso,
            ).on_conflict_do_nothing(
                index_elements=["ticker", "event_date", "event_type"]
            )
        with db.engine.begin() as conn:
            result = conn.execute(stmt)
            inserted = result.rowcount > 0

        # Also post a system notification for convergence events
        if inserted and event_type == "convergence":
            _post_notification(
                notif_type="convergence",
                title=f"⚡ Convergence: {ticker.upper()} ({direction.upper()})",
                body=f"{signal_count} macro signals aligned {direction} for {ticker.upper()}. "
                     f"Score: {score:.0f}/100. Prediction logged for 4w/8w/12w resolution.",
                ticker=ticker.upper(),
                direction=direction,
            )
        return inserted
    except Exception:
        return False


def _post_notification(
    notif_type: str,
    title: str,
    body: str,
    ticker: str | None = None,
    direction: str | None = None,
) -> None:
    """Insert a system notification. Best-effort — never raises."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        with db.engine.begin() as conn:
            conn.execute(
                system_notifications.insert().values(
                    notif_type=notif_type,
                    title=title,
                    body=body,
                    ticker=ticker,
                    direction=direction,
                    created_at=now_iso,
                )
            )
    except Exception:
        pass


# ── Resolution ────────────────────────────────────────────────────────────────

def backfill_missing_entry_prices(limit: int = 50) -> int:
    """Fill price_at_event for calls whose live price fetch failed. Returns count.

    A call is logged the moment a score crosses its threshold, and the entry
    price is fetched live at that instant. That fetch has a bare except, so a
    yfinance blip leaves price_at_event NULL -- and resolve_pending requires it,
    so the row can never resolve. It stays "pending" indefinitely, looking
    exactly like a call that is still maturing. Some rows sat that way for over
    a month.

    The recovered price is the official close on event_date, which is NOT the
    same evidence as the intraday price the call was actually made at: the close
    is a different point in the same day, so the measured return starts from a
    slightly different place. The row is therefore marked
    price_source="backfilled" so Track Record can disclose it rather than
    presenting a reconstructed entry as an observed one.

    That distinction is the whole product. Completing the record is worth doing;
    completing it in a way that cannot be told apart from live data is not.
    """
    import pandas as pd
    import yfinance as yf

    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(prediction_log)
                .where(prediction_log.c.status == "pending")
                .where(prediction_log.c.price_at_event.is_(None))
                .order_by(prediction_log.c.event_date)
                .limit(limit)
            ).mappings().all()
    except Exception as exc:
        print(f"[backfill] could not read rows needing an entry price: {exc}", flush=True)
        return 0

    if not rows:
        return 0

    tickers = sorted({r["ticker"] for r in rows})
    try:
        px = yf.download(
            tickers, period="2y", auto_adjust=True, progress=False, group_by="ticker"
        )
    except Exception as exc:
        print(f"[backfill] price download failed for {tickers}: {exc}", flush=True)
        return 0

    filled = 0
    for row in rows:
        ticker = row["ticker"]
        try:
            closes = (px["Close"] if len(tickers) == 1 else px["Close"][ticker]).squeeze()
            closes = closes.dropna()
            if closes.empty:
                continue

            # The close ON event_date, or the last close before it. Never after:
            # using a later price would let the entry drift toward a known
            # outcome, which would flatter the track record.
            event_dt = pd.Timestamp(row["event_date"])
            eligible = closes[closes.index <= event_dt]
            if eligible.empty:
                print(
                    f"[backfill] {ticker} has no close on or before "
                    f"{row['event_date']} — leaving unresolved",
                    flush=True,
                )
                continue

            entry = float(eligible.iloc[-1])
            if entry <= 0:
                continue

            with db.engine.begin() as conn:
                conn.execute(
                    prediction_log.update()
                    .where(prediction_log.c.id == row["id"])
                    .values(price_at_event=entry, price_source="backfilled")
                )
            filled += 1
        except Exception as exc:
            print(f"[backfill] {ticker} {row['event_date']}: {exc}", flush=True)
            continue

    if filled:
        print(
            f"[backfill] reconstructed entry price for {filled} call(s) from the "
            "close on their event date; marked price_source=backfilled",
            flush=True,
        )
    return filled


def resolve_pending(max_resolve: int = 20) -> int:
    """
    Check all pending predictions whose event_date is ≥4 weeks ago and
    attempt to fill in actual forward returns. Returns number resolved.

    Runs on every TDD page load (cheap — most of the time there are 0-5
    pending rows, and the yfinance fetch only happens for those).
    max_resolve caps worst-case work per call.
    """
    import yfinance as yf
    import pandas as pd

    four_weeks_ago = (datetime.now(timezone.utc) - timedelta(weeks=4)).strftime("%Y-%m-%d")

    # Recover rows the live price fetch had failed on, before selecting work.
    # Without this they can never resolve: the query below requires
    # price_at_event, so a NULL row sits in "pending" forever, indistinguishable
    # from a call that is still legitimately maturing. That is what "past 30 days
    # and still unresolved" was.
    backfill_missing_entry_prices(limit=max_resolve)

    try:
        with db.engine.begin() as conn:
            pending = conn.execute(
                select(prediction_log)
                .where(prediction_log.c.status == "pending")
                .where(prediction_log.c.event_date <= four_weeks_ago)
                .where(prediction_log.c.price_at_event.isnot(None))
                .order_by(prediction_log.c.event_date)
                .limit(max_resolve)
            ).mappings().all()
    except Exception as exc:
        # A resolver that returns 0 on failure is indistinguishable from one
        # that had nothing to do. Say which.
        print(f"[resolve] could not read pending predictions: {exc}", flush=True)
        return 0

    if not pending:
        return 0

    # Batch fetch: unique tickers only
    tickers_needed = list({row["ticker"] for row in pending})
    try:
        px_data = yf.download(
            tickers_needed, period="2y", auto_adjust=True, progress=False, group_by="ticker"
        )
    except Exception:
        return 0

    resolved_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for row in pending:
        ticker = row["ticker"]
        entry_price = row["price_at_event"]
        event_dt = pd.Timestamp(row["event_date"])
        direction = row["direction"]

        try:
            # Extract price series for this ticker
            if len(tickers_needed) == 1:
                closes = px_data["Close"].squeeze()
            else:
                closes = px_data["Close"][ticker].squeeze()

            closes = closes.dropna()

            updates: dict = {}
            all_resolved = True

            for weeks, col_p, col_r, col_c in [
                (4,  "price_4w",  "return_4w",  "correct_4w"),
                (8,  "price_8w",  "return_8w",  "correct_8w"),
                (12, "price_12w", "return_12w", "correct_12w"),
            ]:
                fwd_dt = event_dt + pd.Timedelta(weeks=weeks)
                if fwd_dt > closes.index[-1]:
                    all_resolved = False   # window not yet expired
                    continue
                fwd_price = float(closes.asof(fwd_dt))
                ret = (fwd_price / entry_price - 1) * 100
                correct = 1 if (direction == "bull" and ret > 0) or \
                               (direction == "bear" and ret < 0) else 0
                updates[col_p] = round(fwd_price, 4)
                updates[col_r] = round(ret, 2)
                updates[col_c] = correct

            if updates:
                updates["status"] = "resolved" if all_resolved else "pending"
                with db.engine.begin() as conn:
                    conn.execute(
                        update(prediction_log)
                        .where(prediction_log.c.id == row["id"])
                        .values(**updates)
                    )
                if all_resolved:
                    resolved_count += 1
                    # Post resolution notification
                    best_ret = updates.get("return_12w") or updates.get("return_8w") or updates.get("return_4w")
                    if best_ret is not None:
                        _post_notification(
                            notif_type="prediction_resolved",
                            title=f"📊 Prediction resolved: {ticker} {direction.upper()}",
                            body=f"Called on {row['event_date']}. "
                                 f"12w return: {best_ret:+.1f}% "
                                 f"({'✓ correct' if updates.get('correct_12w') == 1 else '✗ incorrect'}).",
                            ticker=ticker,
                            direction=direction,
                        )
        except Exception:
            continue

    return resolved_count


# ── Track Record ──────────────────────────────────────────────────────────────

def get_track_record() -> dict:
    """
    Aggregate accuracy stats across all resolved predictions.

    Returns:
        {
            "total":        int,
            "resolved":     int,
            "pending":      int,
            "accuracy_4w":  float | None,   # % correct at 4-week horizon
            "accuracy_8w":  float | None,
            "accuracy_12w": float | None,
            "median_ret_4w":  float | None,
            "median_ret_8w":  float | None,
            "median_ret_12w": float | None,
            "by_type":      dict,           # event_type → {accuracy, count}
            "recent":       list[dict],     # last 10 resolved predictions
        }
    """
    try:
        with db.engine.begin() as conn:
            all_rows = conn.execute(
                select(prediction_log)
                .order_by(prediction_log.c.event_date.desc())
            ).mappings().all()
    except Exception:
        return _empty_track_record()

    rows = [dict(r) for r in all_rows]
    if not rows:
        return _empty_track_record()

    total    = len(rows)
    resolved = [r for r in rows if r["status"] == "resolved"]
    pending  = [r for r in rows if r["status"] == "pending"]

    def _accuracy(field: str) -> float | None:
        vals = [r[field] for r in resolved if r.get(field) is not None]
        return round(100 * sum(vals) / len(vals), 1) if vals else None

    def _median_ret(field: str) -> float | None:
        import statistics
        vals = [r[field] for r in resolved if r.get(field) is not None]
        return round(statistics.median(vals), 2) if vals else None

    # By event type
    by_type: dict[str, dict] = {}
    for r in resolved:
        et = r["event_type"]
        if et not in by_type:
            by_type[et] = {"correct_12w": [], "count": 0}
        by_type[et]["count"] += 1
        if r.get("correct_12w") is not None:
            by_type[et]["correct_12w"].append(r["correct_12w"])
    for et, d in by_type.items():
        vals = d.pop("correct_12w")
        d["accuracy_12w"] = round(100 * sum(vals) / len(vals), 1) if vals else None

    return {
        "total":          total,
        "resolved":       len(resolved),
        "pending":        len(pending),
        "accuracy_4w":    _accuracy("correct_4w"),
        "accuracy_8w":    _accuracy("correct_8w"),
        "accuracy_12w":   _accuracy("correct_12w"),
        "median_ret_4w":  _median_ret("return_4w"),
        "median_ret_8w":  _median_ret("return_8w"),
        "median_ret_12w": _median_ret("return_12w"),
        "by_type":        by_type,
        "recent":         resolved[:10],
    }


def _empty_track_record() -> dict:
    return {
        "total": 0, "resolved": 0, "pending": 0,
        "accuracy_4w": None, "accuracy_8w": None, "accuracy_12w": None,
        "median_ret_4w": None, "median_ret_8w": None, "median_ret_12w": None,
        "by_type": {}, "recent": [],
    }


# ── Notification helpers ──────────────────────────────────────────────────────

def get_unread_notification_count(user_id: int | None) -> int:
    """
    Return count of system_notifications the user hasn't read yet.
    For anonymous users, returns total unread in last 7 days.
    """
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    try:
        with db.engine.begin() as conn:
            total = conn.execute(
                select(db.system_notifications)
                .where(db.system_notifications.c.created_at >= cutoff)
            ).rowcount
            if user_id is None:
                # Just count recent notifications for anonymous visitors
                rows = conn.execute(
                    select(db.system_notifications.c.id)
                    .where(db.system_notifications.c.created_at >= cutoff)
                ).fetchall()
                return len(rows)
            cleared_through = conn.execute(
                select(db.notification_clear_state.c.cleared_through_id)
                .where(db.notification_clear_state.c.user_id == user_id)
            ).scalar() or 0
            read_ids = conn.execute(
                select(db.notification_reads.c.notification_id)
                .where(db.notification_reads.c.user_id == user_id)
            ).scalars().all()
            all_ids = conn.execute(
                select(db.system_notifications.c.id)
                .where(db.system_notifications.c.created_at >= cutoff)
                .where(db.system_notifications.c.id > cleared_through)
            ).scalars().all()
        return len(set(all_ids) - set(read_ids))
    except Exception:
        return 0


def get_predictions_feed(
    limit: int = 100,
    direction_filter: str = "all",   # "all" | "bull" | "bear"
    status_filter: str = "all",      # "all" | "pending" | "resolved"
) -> list[dict]:
    """
    Return prediction log rows for the public feed, newest-first.

    Used by BOTH public track-record surfaces -- the card view in
    pages/30_Track_Record_Live.py and the table in the Signal Research Center
    (pages/51_Signal_Research.py). They render the same rows differently, and
    they have already drifted once: the table shipped without the entry price
    the card view showed. Change one, check the other.
    """
    try:
        q = (
            select(prediction_log)
            .order_by(prediction_log.c.event_date.desc())
            .limit(limit)
        )
        if direction_filter != "all":
            q = q.where(prediction_log.c.direction == direction_filter)
        if status_filter != "all":
            q = q.where(prediction_log.c.status == status_filter)
        with db.engine.begin() as conn:
            rows = conn.execute(q).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_signal_accuracy_stats() -> list[dict]:
    """
    Break down prediction accuracy by individual signal.

    Only considers rows where signals_triggered is not NULL and status='resolved'.
    Parses the comma-separated signal IDs, then aggregates correct/total per signal
    at each horizon (4w / 8w / 12w).

    Returns a list of dicts sorted by 12w accuracy descending:
        [
            {
                "signal_id":    str,
                "signal_name":  str,         # human-readable name from SIGNALS config
                "predictions":  int,         # total resolved predictions this signal appeared in
                "accuracy_4w":  float|None,  # % correct at 4-week horizon
                "accuracy_8w":  float|None,
                "accuracy_12w": float|None,
            },
            ...
        ]
    """
    from utils.config import SIGNALS

    try:
        with db.engine.begin() as conn:
            rows = conn.execute(
                select(prediction_log)
                .where(prediction_log.c.status == "resolved")
                .where(prediction_log.c.signals_triggered.isnot(None))
            ).mappings().all()
    except Exception:
        return []

    # Accumulate per signal: {sig_id: {correct_4w: [], correct_8w: [], correct_12w: []}}
    buckets: dict[str, dict[str, list[int]]] = {}

    for row in rows:
        sig_ids = [s.strip() for s in (row["signals_triggered"] or "").split(",") if s.strip()]
        for sig_id in sig_ids:
            if sig_id not in buckets:
                buckets[sig_id] = {"c4": [], "c8": [], "c12": []}
            if row.get("correct_4w") is not None:
                buckets[sig_id]["c4"].append(int(row["correct_4w"]))
            if row.get("correct_8w") is not None:
                buckets[sig_id]["c8"].append(int(row["correct_8w"]))
            if row.get("correct_12w") is not None:
                buckets[sig_id]["c12"].append(int(row["correct_12w"]))

    # Each signal now carries sample size, a Wilson 95% interval, an evidence
    # tier, and a real "does this beat a coin flip?" test — see utils/accuracy.
    #
    # This replaced a raw `100 * correct / total` sorted by accuracy descending,
    # which put `3 of 3 = 100.0%` at the TOP of the leaderboard, above a signal
    # that was 61% across 200 predictions. Publishing that unqualified is how a
    # precision-positioned product loses its credibility: the number is real but
    # it is indistinguishable from luck, and a user could bet money on it.
    from utils.accuracy import summarize, rank_key

    results = []
    for sig_id, d in buckets.items():
        counts = max(len(d["c4"]), len(d["c8"]), len(d["c12"]))
        s4, s8, s12 = summarize(d["c4"]), summarize(d["c8"]), summarize(d["c12"])
        results.append({
            "signal_id":    sig_id,
            "signal_name":  SIGNALS.get(sig_id, {}).get("name", sig_id),
            "predictions":  counts,
            # Headline rates stay None below the reportable sample size, so a
            # caller literally cannot render a confident number we can't defend.
            "accuracy_4w":  s4["rate"],
            "accuracy_8w":  s8["rate"],
            "accuracy_12w": s12["rate"],
            # Full statistical context for honest display.
            "stats_4w":     s4,
            "stats_8w":     s8,
            "stats_12w":    s12,
            "sample_12w":   s12["n"],
            "ci_low_12w":   s12["ci_low"],
            "ci_high_12w":  s12["ci_high"],
            "tier":         s12["tier"],
            "tier_label":   s12["tier_label"],
            "beats_chance": s12["beats_chance"],
            "verdict":      s12["verdict"],
        })

    # Rank by EVIDENCE (beats-chance, then conservative lower bound, then n),
    # not by raw percentage — otherwise small-sample flukes lead the board.
    results.sort(key=lambda r: rank_key(r["stats_12w"]))
    return results


def get_recent_notifications(limit: int = 20, user_id: int | None = None) -> list[dict]:
    """Return recent feed items not cleared by the requesting user."""
    try:
        with db.engine.begin() as conn:
            query = (
                select(db.system_notifications)
                .order_by(db.system_notifications.c.id.desc())
                .limit(limit)
            )
            if user_id is not None:
                cleared_through = conn.execute(
                    select(db.notification_clear_state.c.cleared_through_id)
                    .where(db.notification_clear_state.c.user_id == user_id)
                ).scalar() or 0
                query = query.where(db.system_notifications.c.id > cleared_through)
            rows = conn.execute(query).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []


def clear_notifications(user_id: int) -> bool:
    """Hide all current feed items for one user while preserving future ones."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        with db.engine.begin() as conn:
            latest_id = conn.execute(
                select(db.system_notifications.c.id)
                .order_by(db.system_notifications.c.id.desc())
                .limit(1)
            ).scalar() or 0
            stmt = db.upsert_stmt(db.notification_clear_state, ["user_id"]).values(
                user_id=user_id,
                cleared_through_id=latest_id,
                cleared_at=now_iso,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id"],
                set_={"cleared_through_id": latest_id, "cleared_at": now_iso},
            )
            conn.execute(stmt)
        return True
    except Exception:
        return False


def mark_all_read(user_id: int) -> None:
    """Mark all current notifications as read for this user."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        with db.engine.begin() as conn:
            cleared_through = conn.execute(
                select(db.notification_clear_state.c.cleared_through_id)
                .where(db.notification_clear_state.c.user_id == user_id)
            ).scalar() or 0
            all_ids = conn.execute(
                select(db.system_notifications.c.id)
                .where(db.system_notifications.c.id > cleared_through)
            ).scalars().all()
            existing = set(conn.execute(
                select(db.notification_reads.c.notification_id)
                .where(db.notification_reads.c.user_id == user_id)
            ).scalars().all())
            for nid in all_ids:
                if nid not in existing:
                    conn.execute(
                        db.notification_reads.insert().values(
                            user_id=user_id,
                            notification_id=nid,
                            read_at=now_iso,
                        )
                    )
    except Exception:
        pass


def get_resolver_health() -> dict:
    """
    Diagnostic snapshot for the prediction resolver — used by the Track Record
    Live page to surface how the nightly cron is performing.

    Returns:
        {
            "pending_total":          int,   -- all pending predictions
            "overdue_pending":        int,   -- pending where event_date ≤ 4 weeks ago
                                               (should have been resolved already)
            "last_resolved_date":     str | None,  -- event_date of most recently
                                                      resolved prediction (best proxy
                                                      for "when did resolver last run"
                                                      since there's no resolved_at col)
            "recently_resolved_7d":   int,   -- resolved rows with event_date in last 7 days
                                               (quick proxy for resolver activity)
        }

    Never raises. Returns zero-filled dict on any DB error.
    """
    four_weeks_ago = (datetime.now(timezone.utc) - timedelta(weeks=4)).strftime("%Y-%m-%d")
    seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        with db.engine.begin() as conn:
            rows = conn.execute(select(db.prediction_log)).mappings().all()
        rows = [dict(r) for r in rows]
    except Exception:
        return {"pending_total": 0, "overdue_pending": 0,
                "last_resolved_date": None, "recently_resolved_7d": 0}

    pending  = [r for r in rows if r["status"] == "pending"]
    resolved = [r for r in rows if r["status"] == "resolved"]

    overdue = [r for r in pending if r["event_date"] <= four_weeks_ago]

    last_resolved_date = None
    if resolved:
        last_resolved_date = max(r["event_date"] for r in resolved)

    recently_resolved = [r for r in resolved if r["event_date"] >= seven_days_ago]

    return {
        "pending_total":        len(pending),
        "overdue_pending":      len(overdue),
        "last_resolved_date":   last_resolved_date,
        "recently_resolved_7d": len(recently_resolved),
    }
