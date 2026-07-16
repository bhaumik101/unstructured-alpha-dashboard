"""
cron/keep_warm.py — Keep the Render web service warm.

Free/low-tier Render web services spin down after ~15 min of inactivity; the
next visitor then hits a cold container, which is what produces the transient
"Page not found — Running the app's main page" flash on shared deep-links
(Streamlit re-runs before pages finish registering). A lightweight GET every
few minutes keeps the container alive so real visitors always land on a warm
app.

Scheduled from render.yaml (every 10 minutes). Best-effort: never raises, so a
transient network blip can't mark the cron run as failed.

Env:
  APP_URL — public base URL of the web service.
            Defaults to https://app.unstructuredalpha.com
"""

import os
import sys
import time
from datetime import datetime, timezone

import requests

APP_URL = os.getenv("APP_URL", "https://app.unstructuredalpha.com").rstrip("/")

# A couple of representative deep-links, so we exercise the router (not just the
# root) and keep the MPA page registry warm too.
PATHS = ["/", "/signal-dashboard", "/ticker-deep-dive"]


def _ping(path: str) -> tuple[int | None, float]:
    url = f"{APP_URL}{path}"
    t0 = time.monotonic()
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": "UA-keep-warm/1.0"})
        return r.status_code, time.monotonic() - t0
    except Exception as exc:  # noqa: BLE001 — best-effort, never fail the run
        print(f"[keep_warm] {url} -> error: {exc}", file=sys.stderr)
        return None, time.monotonic() - t0


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    ok = 0
    for p in PATHS:
        code, secs = _ping(p)
        if code and 200 <= code < 500:  # 2xx/3xx/4xx all mean the app answered
            ok += 1
        print(f"[keep_warm] {stamp} {p} -> {code} in {secs:.1f}s")
    print(f"[keep_warm] {ok}/{len(PATHS)} endpoints responsive")


if __name__ == "__main__":
    main()
