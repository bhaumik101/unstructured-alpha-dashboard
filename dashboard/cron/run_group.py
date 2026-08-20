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
    # Both watchdogs in one service. They answer complementary questions -- is
    # the data still arriving, and is what we publish still reachable where we
    # publish it -- and each signals failure by returning non-zero, which the
    # loop above now honours.
    "health": (
        "cron.check_data_freshness",
        "cron.check_public_surfaces",
    ),
}


def run_group(name: str) -> int:
    failures: list[str] = []
    for module_name in GROUPS[name]:
        label = module_name.rsplit(".", 1)[-1]
        print(f"[cron-group] starting group={name} job={label}", flush=True)
        try:
            rc = importlib.import_module(module_name).main()
            # A job may report failure by RETURNING non-zero rather than
            # raising -- cron/check_data_freshness.py does exactly that, and so
            # does check_public_surfaces. Ignoring the return value meant a
            # grouped watchdog could report a stalled pipeline and the group
            # would still exit 0, which is the failure the watchdog exists to
            # prevent. Harmless until now only because every previously grouped
            # job returns None.
            if isinstance(rc, int) and rc != 0:
                failures.append(label)
                print(
                    f"[cron-group] failed group={name} job={label} exit={rc}",
                    file=sys.stderr, flush=True,
                )
            else:
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
