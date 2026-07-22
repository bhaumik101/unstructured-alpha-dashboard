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
    assert combined["schedule"] == "0 */2 * * *"
    assert combined["startCommand"] == "python -m cron.send_threshold_alerts"


def test_low_frequency_jobs_are_grouped():
    crons = _cron_services()
    assert crons["unstructured-alpha-lifecycle"]["startCommand"].endswith(
        "run_group lifecycle"
    )
    assert crons["unstructured-alpha-watchlist-insights"]["startCommand"].endswith(
        "run_group watchlist-insights"
    )
    assert len(crons) == 13


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
