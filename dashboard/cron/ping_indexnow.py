#!/usr/bin/env python3
"""After the weekly re-measure, tell search engines every public page changed.

Runs in the weekly-universe group (cron/run_group.py) after measure_library,
so the pages it announces already carry the new week. Reads our own public
sitemap rather than the database: what is announced is exactly what is
served. See utils/indexnow.py for the protocol and its rules.
"""

from __future__ import annotations

from utils import indexnow


def main(fetch=None, post=None) -> int:
    if fetch is None:
        import requests

        def fetch(url):
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.text
    try:
        urls = indexnow.urls_from_sitemap(fetch(indexnow.SITEMAP))
    except Exception as exc:
        print(f"[indexnow] could not read the sitemap: {type(exc).__name__}", flush=True)
        return 1
    if not urls:
        print("[indexnow] the sitemap listed no pages on our host; nothing sent", flush=True)
        return 1
    try:
        status = indexnow.submit(urls, post=post)
    except Exception as exc:
        print(f"[indexnow] submit failed: {type(exc).__name__}", flush=True)
        return 1
    ok = status in (200, 202)
    print(f"[indexnow] submitted {len(urls)} urls status={status}{'' if ok else ' (refused)'}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
