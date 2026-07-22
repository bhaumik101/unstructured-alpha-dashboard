#!/usr/bin/env python3
"""Run compatible low-frequency maintenance tasks in one Render invocation.

Render bills and boots cron jobs independently.  These tasks already share the
same schedule and environment, so separate services paid the startup cost four
times while doing mostly small database checks.  Grouping them keeps every
task's existing idempotency and failure isolation while using one process.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from utils.memory import release_memory


GROUPS = {
    "lifecycle": (
        "cron.send_trial_reminder",
        "cron.send_onboarding_day3",
        "cron.send_onboarding_day7",
        "cron.send_reengagement",
    ),
    "watchlist-insights": (
        "cron.send_score_moved",
        "cron.send_velocity_alerts",
    ),
}


def run_group(name: str) -> int:
    failures: list[str] = []
    for module_name in GROUPS[name]:
        label = module_name.rsplit(".", 1)[-1]
        print(f"[cron-group] starting group={name} job={label}", flush=True)
        try:
            importlib.import_module(module_name).main()
            print(f"[cron-group] completed group={name} job={label}", flush=True)
        except Exception as exc:
            failures.append(label)
            print(
                f"[cron-group] failed group={name} job={label} "
                f"error={str(exc)[:180]}",
                file=sys.stderr,
                flush=True,
            )
        finally:
            release_memory()

    if failures:
        print(f"[cron-group] group={name} failures={','.join(failures)}", flush=True)
        return 1
    print(f"[cron-group] group={name} all_jobs_completed", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("group", choices=sorted(GROUPS))
    args = parser.parse_args()
    return run_group(args.group)


if __name__ == "__main__":
    raise SystemExit(main())
