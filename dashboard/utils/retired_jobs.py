# utils/retired_jobs.py
# Unstructured Alpha — scheduled jobs of the retired macro-signal product
#
# The product is now exposure measurement; these jobs belong to the earlier
# Confluence Score / signal product. They kept waking the Neon database many
# times a day, and on 2026-10-27 Neon refused every connection for five days:
# "Your account or project has exceeded the quota". Each entry point below
# calls exit_if_retired() before importing anything else, so a run exits in
# under a second without touching the database -- whatever render.yaml says,
# since a Blueprint change may never sync to Render. Set UA_RUN_RETIRED=1 on
# a job to run it anyway.

from __future__ import annotations

import os
import sys

RETIRED = frozenset({
    "send_threshold_alerts",    # every 2 hours
    "signal_flip_alerts",       # every 6 hours
    "score_universe",           # score-core daily, score-rest Mon/Wed/Fri
    "tweet_best_ideas",
    "tweet_signal_flips",
    "send_weekly_brief",
    "send_brief_subscribers",
})


def exit_if_retired(job: str) -> None:
    if job in RETIRED and os.getenv("UA_RUN_RETIRED") != "1":
        print(f"[{job}] retired with the macro-signal product; exiting without touching the "
              "database (set UA_RUN_RETIRED=1 to run it).", flush=True)
        sys.exit(0)
