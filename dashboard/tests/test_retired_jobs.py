"""The retired macro-signal jobs exit before touching the database.

They kept waking Neon many times a day until it refused every connection for
five days (2026-10-27: "exceeded the quota"). Each entry point's first
statement exits; nothing it imports runs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from utils.retired_jobs import RETIRED

ROOT = Path(__file__).resolve().parent.parent


def _first_statement(src: str) -> str:
    """Source of the first statement after the module docstring and `from __future__`."""
    import ast
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant):
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
        return ast.get_source_segment(src, node).splitlines()[0]
    return ""


def test_every_retired_job_exits_before_its_first_import():
    for job in RETIRED:
        src = (ROOT / "cron" / f"{job}.py").read_text(encoding="utf-8")
        assert _first_statement(src).startswith('if __name__ == "__main__":'), job
        assert f'exit_if_retired("{job}")' in src, job


def test_the_current_product_jobs_are_not_retired():
    for job in ("measure_library", "send_exposure_weekly", "grow_universe", "track_record"):
        assert job not in RETIRED


@pytest.mark.slow     # spawns interpreters
def test_a_retired_job_exits_zero_without_reaching_the_database():
    env = {**os.environ, "DATABASE_URL": "postgresql://nobody:x@127.0.0.1:1/none"}
    env.pop("UA_RUN_RETIRED", None)
    for job in sorted(RETIRED):
        r = subprocess.run([sys.executable, "-m", f"cron.{job}"], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0 and "retired" in r.stdout, (job, r.stdout[-300:], r.stderr[-300:])
