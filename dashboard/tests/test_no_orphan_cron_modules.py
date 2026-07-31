"""Every cron module must be reachable by something that actually runs it.

Six modules were found on 2026-07-31 with no Render service and no run_group
membership: fire_webhooks, grow_universe, keep_warm, send_watchlist_alerts,
tweet_best_ideas and tweet_signal_flips — 894 lines of code that could never
execute. Worse, other files still described them in comments as live parts of
the architecture, so reading the codebase gave a false picture of what runs.

Dead scheduled code is particularly costly here: it looks like coverage. Someone
reasoning about whether alerts get delivered would find send_watchlist_alerts.py,
conclude it was handled, and be wrong.
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
        found.update(re.findall(r"cron\.([a-z0-9_]+)", str(service.get("startCommand", ""))))
    return found


def _modules_in_a_group() -> set[str]:
    src = (_CRON_DIR / "run_group.py").read_text(encoding="utf-8")
    return set(re.findall(r"cron\.([a-z0-9_]+)", src))


def test_every_cron_module_is_reachable():
    """No module may sit on disk with nothing scheduled to run it."""
    on_disk = _modules_on_disk()
    reachable = _modules_with_a_service() | _modules_in_a_group()
    orphans = sorted(on_disk - reachable)

    assert not orphans, (
        "cron modules with no Render service and no run_group entry — they can "
        f"never execute, but read as working features: {orphans}. Either wire "
        "them to a service/group or delete them."
    )


def test_every_scheduled_module_actually_exists():
    """The mirror image: a service must not point at a module that is gone.

    This is the failure the deletions above could have caused — removing a file
    while a Render service still invokes it produces a cron that fails on every
    run, and cron failures are easy to never look at.
    """
    on_disk = _modules_on_disk() | {"run_group"}
    scheduled = _modules_with_a_service() | _modules_in_a_group()
    missing = sorted(scheduled - on_disk)

    assert not missing, (
        f"scheduled modules that do not exist on disk: {missing}"
    )


def test_deleted_modules_are_not_described_as_live_in_comments():
    """Comments must not advertise an architecture that no longer exists.

    utils/webhook.py, utils/alerts_db.py, utils/email.py and
    cron/send_score_moved.py all referenced deleted crons as though they were
    running. A stale comment is worse than no comment: it is confidently wrong.
    """
    deleted = [
        "cron/fire_webhooks.py",
        "cron/keep_warm.py",
        "cron/send_watchlist_alerts.py",
        "cron/tweet_best_ideas.py",
        "cron/tweet_signal_flips.py",
    ]
    offenders: list[str] = []
    for path in list(_ROOT.glob("utils/*.py")) + list(_CRON_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name in deleted:
            if name in text:
                offenders.append(f"{path.relative_to(_ROOT)} -> {name}")

    assert not offenders, (
        "references to deleted cron modules remain: " + "; ".join(offenders)
    )
