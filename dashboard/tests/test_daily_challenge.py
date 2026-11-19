"""The landing's "Today's challenge" reads the same progress the tool pages write.

What must hold:
  * its streak is the tool pages' streak, on the same store and the same day
    (app/progress.ts against utils/progress.py, run side by side in Node);
  * today's plays are read; a corrupt or empty store is a newcomer;
  * the landing renders it, after the live movers.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from utils.progress import progress_js

WEB = Path(__file__).resolve().parents[1] / "unstructured-alpha-web"

STORES = [
    None,
    "{bad",
    {"d": {}, "l": {"learn": 1}},
    {"d": {"2026-11-19": {"quiz": [7, 10]}, "2026-11-18": {"guess": [3, 5]}, "2026-11-17": {"quiz": [5, 10]}}, "l": {}},
    {"d": {"2026-11-18": {"quiz": [7, 10]}, "2026-11-17": {"quiz": [7, 10]}}, "l": {"quiz": 1}},   # not yet today
    {"d": {"2026-11-19": {"quiz": [9, 10], "guess": [5, 5]}, "2026-11-16": {"quiz": [1, 10]}}, "l": {}},  # a gap
]


@pytest.mark.skipif(not shutil.which("node"), reason="needs node")
def test_the_landing_streak_matches_the_tool_pages(tmp_path):
    raws = [s if isinstance(s, str) or s is None else json.dumps(s) for s in STORES]
    runner = tmp_path / "run.ts"
    runner.write_text(
        f"import {{ summarize }} from '{(WEB / 'app' / 'progress.ts').as_posix()}';\n"
        "const now = new Date(2026, 10, 19, 12);\n"
        f"const raws = {json.dumps(raws)};\n"
        "const out = raws.map(r => { const s = summarize(r, now); return [s.streak, s.today, s.any]; });\n"
        "let store: Record<string, string> = {};\n"
        "(globalThis as any).window = globalThis;\n"
        "(globalThis as any).localStorage = {getItem: (k: string) => k in store ? store[k] : null, setItem: (k: string, v: string) => { store[k] = v; }};\n"
        f"eval({json.dumps(progress_js())});\n"
        "const U = (globalThis as any).UAP; U._clock(() => new Date(now.getTime()));\n"
        "const theirs = raws.map(r => { store = r === null ? {} : {ua_progress_v1: r}; return U.summary().streak; });\n"
        "console.log(JSON.stringify({out, theirs}));\n")
    r = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", str(runner)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode and "experimental-strip-types" in r.stderr:
        pytest.skip("this node cannot run TypeScript directly")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert [o[0] for o in got["out"]] == got["theirs"] == [0, 0, 0, 3, 2, 1]
    assert got["out"][3][1] == {"quiz": [7, 10]} and got["out"][4][1] == {}
    assert [o[2] for o in got["out"]] == [False, False, True, True, True, True]


def test_the_landing_renders_it_after_the_live_movers():
    page = (WEB / "app" / "page.tsx").read_text()
    assert "import DailyChallenge from './DailyChallenge';" in page
    assert page.index("<LiveMovers />") < page.index("<DailyChallenge />")
    comp = (WEB / "app" / "DailyChallenge.tsx").read_text()
    assert "useSyncExternalStore(subscribe, snapshot, () => null)" in comp   # invitation on the server
    assert 'href: \'/quiz\'' in comp and 'href: \'/guess\'' in comp
