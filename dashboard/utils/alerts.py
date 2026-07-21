# utils/alerts.py
# Unstructured Alpha — Alert Evaluation Engine
#
# Compares each watched ticker's CURRENT state (Confluence Score, price,
# 52-week high/low, and the three differentiator-signal statuses) against
# the LAST-SEEN snapshot stored in utils/alerts_db, and turns meaningful
# deltas into alert records.
#
# Deliberately evaluates threshold CROSSINGS, not levels: if a ticker's
# score is 70 (bullish) on every check for a month, that should fire once
# (when it first crossed 65), not every single time someone reopens the
# Alerts page. Re-alerting on every check a condition merely continues to
# be true would make the feed useless noise within a day.
#
# Execution model: Streamlit has no built-in background scheduler -- this
# runs synchronously when called (e.g. when the Alerts page loads, or from
# a manual "check now" button), not on a timer while the app is closed.
# True push delivery (email) requires an actual scheduled job outside the
# Streamlit process; this module is the trigger logic that job would call,
# but the scheduler itself is explicitly out of scope for this pass (see
# pages/alerts page docstring for the current state of that gap).

import threading
from datetime import datetime

from utils import alerts_db
from utils.score_cache import get_full_ticker_score
from utils.ticker_score import compute_full_ticker_score

_ORIGINAL_COMPUTE_FULL_TICKER_SCORE = compute_full_ticker_score


def _pct_change(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / abs(old) * 100.0


def evaluate_ticker(user_id: int, ticker: str, thresholds: dict,
                    profile: dict | None = None) -> list[dict]:
    """
    Evaluate one watched ticker against ITS OWNER'S stored last-seen state.
    Returns the list of newly-created alert dicts (already persisted) --
    empty if nothing crossed a threshold this check, including the very
    first check for a ticker (nothing to compare against yet).

    The canonical full result is shared by ticker/model/freshness key. Only
    the per-user last-seen snapshot and threshold comparison are user-scoped.
    """
    ticker = ticker.upper().strip()
    new_alerts = []

    # Existing unit tests (and callers embedding this module) replace the local
    # scorer deliberately. Preserve that injection seam; production uses the
    # shared cache.
    if compute_full_ticker_score is _ORIGINAL_COMPUTE_FULL_TICKER_SCORE:
        full = get_full_ticker_score(ticker).result
    else:
        full = compute_full_ticker_score(ticker)
    current_score = full["confluence"]["overall_score"]

    # Alert on the score the user actually SEES. Showing a personalised
    # "Your Score" on Deep Dive while alerting off the generic Confluence Score
    # is incoherent — a long-horizon investor would get pinged by short-lead
    # signals they've explicitly told us to down-weight. When the user has set a
    # non-default risk profile, their score becomes the alerting basis.
    #
    # Pure post-processing of `full` — no extra fetch. Fully defensive: any
    # problem falls back to the canonical score.
    #
    # NOTE: alert_state stores the last-seen score, so changing your profile can
    # produce one transitional alert as the basis shifts. That's a one-off and
    # preferable to alerting on a number the user isn't looking at.
    if profile:
        try:
            from utils.risk_profile import compute_personal_score, is_default
            if not is_default(profile):
                _ps = compute_personal_score(full, profile)
                if _ps.get("ok") and _ps.get("score") is not None:
                    current_score = float(_ps["score"])
        except Exception:
            pass
    price_series = full["price_series"].dropna()
    current_price = float(price_series.iloc[-1]) if not price_series.empty else None
    high_52w = float(price_series.tail(252).max()) if len(price_series) >= 2 else current_price
    low_52w = float(price_series.tail(252).min()) if len(price_series) >= 2 else current_price

    insider_status = full["insider_score"].get("status") if full["has_insider_signal"] else "no_data"
    short_interest_status = full["short_interest_score"].get("status") if full["has_short_interest_signal"] else "no_data"
    thirteenf_status = full["thirteenf_score"].get("status") if full["has_13f_signal"] else "no_data"

    prior = alerts_db.get_alert_state(user_id, ticker)

    if prior is not None:
        bull_threshold = thresholds.get("score_bull_threshold", alerts_db.DEFAULT_SCORE_BULL_THRESHOLD)
        bear_threshold = thresholds.get("score_bear_threshold", alerts_db.DEFAULT_SCORE_BEAR_THRESHOLD)
        price_move_threshold = thresholds.get("price_move_pct_threshold", alerts_db.DEFAULT_PRICE_MOVE_PCT_THRESHOLD)

        prior_score = prior.get("last_score")
        if prior_score is not None:
            crossed_bullish = prior_score < bull_threshold <= current_score
            crossed_bearish = prior_score > bear_threshold >= current_score
            if crossed_bullish:
                msg = f"Confluence Score crossed into bullish territory: {prior_score:.0f} -> {current_score:.0f}"
                new_alerts.append(_record(user_id, ticker, "score_threshold", msg, "bullish"))
            elif crossed_bearish:
                msg = f"Confluence Score crossed into bearish territory: {prior_score:.0f} -> {current_score:.0f}"
                new_alerts.append(_record(user_id, ticker, "score_threshold", msg, "bearish"))

        prior_price = prior.get("last_price")
        if prior_price and current_price is not None:
            pct = _pct_change(current_price, prior_price)
            if abs(pct) >= price_move_threshold:
                direction = "bullish" if pct > 0 else "bearish"
                msg = f"Price moved {pct:+.1f}% since last check (${prior_price:.2f} -> ${current_price:.2f})"
                new_alerts.append(_record(user_id, ticker, "price_move", msg, direction))

        prior_high = prior.get("last_52w_high")
        if prior_high and current_price is not None and current_price > prior_high:
            msg = f"New 52-week high: ${current_price:.2f} (previous: ${prior_high:.2f})"
            new_alerts.append(_record(user_id, ticker, "price_move", msg, "bullish"))

        prior_low = prior.get("last_52w_low")
        if prior_low and current_price is not None and current_price < prior_low:
            msg = f"New 52-week low: ${current_price:.2f} (previous: ${prior_low:.2f})"
            new_alerts.append(_record(user_id, ticker, "price_move", msg, "bearish"))

        prior_insider = prior.get("last_insider_status")
        if prior_insider and prior_insider != "no_data" and insider_status not in (prior_insider, "no_data"):
            new_alerts.append(_record(
                user_id, ticker, "insider",
                f"Insider activity signal changed: {prior_insider} -> {insider_status}",
                insider_status if insider_status in ("bullish", "bearish") else None,
            ))

        prior_si = prior.get("last_short_interest_status")
        if prior_si and prior_si != "no_data" and short_interest_status not in (prior_si, "no_data"):
            new_alerts.append(_record(
                user_id, ticker, "short_interest",
                f"Short interest signal changed: {prior_si} -> {short_interest_status}",
                short_interest_status if short_interest_status in ("bullish", "bearish") else None,
            ))

        prior_13f = prior.get("last_13f_status")
        if prior_13f and prior_13f != "no_data" and thirteenf_status not in (prior_13f, "no_data"):
            new_alerts.append(_record(
                user_id, ticker, "13f",
                f"13F institutional positioning changed: {prior_13f} -> {thirteenf_status}",
                thirteenf_status if thirteenf_status in ("bullish", "bearish") else None,
            ))

    alerts_db.set_alert_state(
        user_id, ticker,
        last_score=current_score,
        last_price=current_price,
        last_52w_high=max(high_52w, current_price) if current_price is not None else high_52w,
        last_52w_low=min(low_52w, current_price) if current_price is not None else low_52w,
        last_insider_status=insider_status,
        last_short_interest_status=short_interest_status,
        last_13f_status=thirteenf_status,
    )

    # Fire webhook asynchronously so a slow or unreachable endpoint doesn't
    # block the page load that triggered this evaluation. daemon=True means
    # the thread won't prevent the Streamlit worker from shutting down.
    if new_alerts:
        try:
            from utils import webhook as _wh
            threading.Thread(
                target=_wh.fire_alerts_for_user,
                args=(user_id, list(new_alerts)),
                daemon=True,
            ).start()
        except Exception:
            pass  # webhook delivery is best-effort; cron will retry

    return new_alerts


def _record(user_id: int, ticker: str, alert_type: str, message: str, direction: str | None) -> dict:
    alert_id = alerts_db.create_alert(user_id, ticker, alert_type, message, direction=direction)
    return {"id": alert_id, "ticker": ticker, "alert_type": alert_type, "message": message, "direction": direction}


def evaluate_watchlist(user_id: int) -> list[dict]:
    """
    Evaluate every ticker on THIS USER's watchlist. Returns all newly-
    created alerts across that watchlist (already persisted to the alerts
    table) -- call this from the Alerts page or a manual refresh action,
    not on every page in the app, since it re-runs the full scoring
    pipeline (multiple network fetches) per watched ticker.
    """
    all_new_alerts = []

    # Load the user's risk profile ONCE for the whole sweep — it's per-user, not
    # per-ticker, so alerts fire on the same score this user sees in the app.
    try:
        from utils.risk_profile import get_profile
        profile = get_profile(user_id)
    except Exception:
        profile = None

    for row in alerts_db.get_watchlist(user_id):
        thresholds = {
            "score_bull_threshold": row["score_bull_threshold"],
            "score_bear_threshold": row["score_bear_threshold"],
            "price_move_pct_threshold": row["price_move_pct_threshold"],
        }
        try:
            all_new_alerts.extend(
                evaluate_ticker(user_id, row["ticker"], thresholds, profile=profile))
        except Exception:
            # One ticker's data hiccup (network, bad ticker, etc.) must not
            # block evaluating the rest of the watchlist.
            continue
    return all_new_alerts
