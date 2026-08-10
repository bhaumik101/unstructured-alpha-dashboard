"""Every cron module must be reachable by something that actually runs it.

Dead scheduled code is expensive here because it looks like coverage. Someone
reasoning about whether alerts get delivered finds send_watchlist_alerts.py,
concludes it is handled, and is wrong.

Three modules were orphaned as of 2026-08-09 — fire_webhooks, keep_warm and
send_watchlist_alerts — 262 lines with no Render service and no run_group entry.
The webhook and watchlist sweeps were consolidated into send_threshold_alerts;
keep_warm became pointless when the web service moved to Standard, which does
not sleep.

The mirror test matters just as much. An earlier version of this cleanup (PR
#108, closed) would have deleted SIX modules, but three of them —
grow_universe, tweet_best_ideas, tweet_signal_flips — had been wired up in the
meantime. Merging it would have deleted live, scheduled crons. Drift runs in
both directions, so both directions are asserted.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_CRON_DIR = _ROOT / "cron"


def _modules_on_disk() -> set[str]:
    return {
        p.stem
        for p in _CRON_DIR.glob("*.py")
        if p.stem not in {"__init__", "run_group"}
    }


def _modules_with_a_service() -> set[str]:
    blueprint = yaml.safe_load((_ROOT / "render.yaml").read_text(encoding="utf-8"))
    found: set[str] = set()
    for service in blueprint.get("services") or []:
        found.update(
            re.findall(r"cron\.([a-z0-9_]+)", str(service.get("startCommand", "")))
        )
    return found


def _modules_in_a_group() -> set[str]:
    run_group = _CRON_DIR / "run_group.py"
    if not run_group.exists():
        return set()
    return set(re.findall(r"cron\.([a-z0-9_]+)", run_group.read_text(encoding="utf-8")))


def test_every_cron_module_is_reachable():
    """No module may sit on disk with nothing scheduled to run it."""
    orphans = sorted(_modules_on_disk() - (_modules_with_a_service() | _modules_in_a_group()))
    assert not orphans, (
        "cron modules with no Render service and no run_group entry — they can "
        f"never execute, but read as working features: {orphans}. Either wire "
        "them to a service/group or delete them."
    )


def test_every_scheduled_module_actually_exists():
    """A service must not point at a module that is gone.

    Removing a file while a service still invokes it produces a cron that fails
    on every run — and a failing cron is easy to never look at.
    """
    scheduled = _modules_with_a_service() | _modules_in_a_group()
    missing = sorted(scheduled - (_modules_on_disk() | {"run_group"}))
    assert not missing, f"scheduled modules that do not exist on disk: {missing}"


def test_no_comment_advertises_a_deleted_cron():
    """Comments must not describe an architecture that no longer exists.

    utils/webhook.py, utils/alerts_db.py, utils/email.py and
    cron/send_score_moved.py all referenced these as live. A stale comment is
    worse than none: it is confidently wrong, and it is what makes dead code
    read as coverage.
    """
    deleted = ["fire_webhooks", "keep_warm", "send_watchlist_alerts"]
    offenders: list[str] = []
    searchable = list(_ROOT.glob("utils/*.py")) + list(_CRON_DIR.glob("*.py"))
    for path in searchable:
        text = path.read_text(encoding="utf-8")
        for name in deleted:
            if name in text:
                offenders.append(f"{path.relative_to(_ROOT)} -> {name}")
    assert not offenders, (
        "references to deleted cron modules remain: " + "; ".join(offenders)
    )


def test_the_freshness_watchdog_is_scheduled():
    """The watchdog is worthless if nothing runs it.

    It exists because score_snapshots silently stopped advancing for ten days
    while the site looked healthy. A watchdog that is itself unscheduled would
    reproduce exactly that failure.
    """
    assert "check_data_freshness" in _modules_with_a_service(), (
        "cron/check_data_freshness.py has no Render service"
    )
