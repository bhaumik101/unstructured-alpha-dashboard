"""Regression coverage for the Render cron cost and reliability pass."""

from pathlib import Path

import yaml


DASHBOARD = Path(__file__).resolve().parent.parent


def _cron_services() -> dict[str, dict]:
    blueprint = yaml.safe_load((DASHBOARD / "render.yaml").read_text())
    return {
        service["name"]: service
        for service in blueprint["services"]
        if service.get("type") == "cron"
    }


def test_paid_standard_web_service_has_no_keep_warm_cron():
    crons = _cron_services()
    assert "unstructured-alpha-keep-warm" not in crons


def test_duplicate_threshold_sweeps_are_replaced_by_one_dispatcher():
    crons = _cron_services()
    assert "unstructured-alpha-webhooks" not in crons
    assert "unstructured-alpha-watchlist-alerts" not in crons
    combined = crons["unstructured-alpha-threshold-alerts"]
    # Cut from every 2h to every 8h on 2026-07-31. Macro source series are
    # daily/weekly/monthly, so 9 of the 12 daily runs re-read identical data --
    # the same reasoning already applied to the sibling signal-flip cron. Still
    # a single dispatcher, which is what this test actually guards; only the
    # cadence changed. Worst-case alert latency ~8h, deliberately not lower
    # because 346 alerts are configured and this is a paid feature.
    assert combined["schedule"] == "0 */8 * * *"
    assert combined["startCommand"] == "python -m cron.send_threshold_alerts"


def test_low_frequency_jobs_are_grouped():
    crons = _cron_services()
    assert crons["unstructured-alpha-lifecycle"]["startCommand"].endswith(
        "run_group lifecycle"
    )
    assert crons["unstructured-alpha-watchlist-insights"]["startCommand"].endswith(
        "run_group watchlist-insights"
    )
    # 13 -> 11 on 2026-07-31. Removed both X crons (posting to X needs a paid
    # API tier; on the free tier they returned 402 and published nothing for
    # weeks while appearing active) and grow-universe (the universe already held
    # 5,273 tickers against 7 users, and enlarging it made the scorer even less
    # able to finish inside its deadline). Added the data-freshness monitor.
    #
    # Exact equality is deliberate: adding a cron should be a conscious decision
    # that updates this number, not something that drifts in unnoticed.
    assert len(crons) == 11
    assert "unstructured-alpha-tweet-flips" not in crons
    assert "unstructured-alpha-tweet-best-ideas" not in crons
    assert "unstructured-alpha-grow-universe" not in crons


def test_data_freshness_monitor_exists_and_runs_after_the_scorers():
    """Nothing noticed score_snapshots going stale for ten days.

    The Screener and every ticker Confluence Score served 2026-07-21 data until
    2026-07-31 while the site looked healthy. For a product whose claim is data
    integrity, silently serving stale scores is worse than being down.
    """
    crons = _cron_services()
    monitor = crons["unstructured-alpha-data-freshness"]
    assert monitor["startCommand"].endswith("cron.check_data_freshness")
    # Must run after score-core (04:10) and score-rest (05:40), or it would
    # report staleness that the day's own run was about to clear.
    assert monitor["schedule"] == "0 6 * * *"


def test_rest_scorer_has_safe_memory_headroom_and_reduced_cadence():
    rest = _cron_services()["unstructured-alpha-score-rest"]
    env = {row["key"]: row.get("value") for row in rest["envVars"]}
    assert rest["schedule"] == "40 5 * * 1,3,5"
    assert "--budget 600" in rest["startCommand"]
    assert "--deadline-min 25" in rest["startCommand"]
    assert int(env["SCORE_MAX_RSS_MB"]) <= 390


def test_threshold_dispatcher_evaluates_each_user_once(monkeypatch):
    from cron import send_threshold_alerts as dispatcher

    evaluated: list[int] = []
    screens_evaluated: list[int] = []
    emailed: list[str] = []
    webhook_users: list[int] = []
    monkeypatch.setattr(dispatcher, "init_db", lambda: None)
    monkeypatch.setattr(
        dispatcher,
        "get_all_watchlist_users",
        lambda: [{"id": 1, "email": "one@example.com"},
                 {"id": 2, "email": "two@example.com"}],
    )
    monkeypatch.setattr(dispatcher, "get_all_webhook_users", lambda: [{"id": 2}])
    monkeypatch.setattr(
        dispatcher,
        "get_enabled_screen_users",
        lambda: [{"id": 2, "email": "two@example.com"},
                 {"id": 3, "email": "three@example.com"}],
    )

    def evaluate(user_id):
        evaluated.append(user_id)
        return [{"ticker": "AAPL"}]

    monkeypatch.setattr(dispatcher, "evaluate_watchlist", evaluate)

    def evaluate_screens(user_id, *, rankings_by_horizon):
        screens_evaluated.append(user_id)
        rankings_by_horizon.setdefault("All", [])
        return [{"ticker": "NVDA"}]

    monkeypatch.setattr(dispatcher, "evaluate_saved_screens", evaluate_screens)
    monkeypatch.setattr(
        dispatcher, "send_watchlist_alert_email", lambda email, alerts: emailed.append(email)
    )

    def fire(user_id, alerts):
        webhook_users.append(user_id)
        return 1

    monkeypatch.setattr(dispatcher, "fire_alerts_for_user", fire)
    dispatcher.main()

    assert evaluated == [1, 2]
    assert screens_evaluated == [2, 3]
    assert emailed == ["one@example.com", "two@example.com", "three@example.com"]
    assert webhook_users == [2]
