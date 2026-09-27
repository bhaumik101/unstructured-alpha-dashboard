"""The database driver is the one we install, whatever SQLAlchemy defaults to.

On 2026-09-27 a routine deploy resolved SQLAlchemy 2.1, which reads a bare
``postgresql://`` URL as psycopg 3. We install psycopg2. Every page and every
cron died at import with ``ModuleNotFoundError: psycopg`` — no code of ours had
changed. These tests pin the driver to what requirements.txt ships.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.db import with_installed_driver  # noqa: E402


@pytest.mark.parametrize("url", [
    "postgresql://u:p@db.internal:5432/ua",
    "postgres://u:p@db.internal:5432/ua",
])
def test_a_bare_postgres_url_uses_psycopg2(url):
    pinned = with_installed_driver(url)
    assert pinned == "postgresql+psycopg2://u:p@db.internal:5432/ua"
    assert make_url(pinned).get_dialect().driver == "psycopg2"


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://u:p@h/ua",
    "postgresql+psycopg2://u:p@h/ua",
    "sqlite:///data/ua.db",
])
def test_a_url_that_names_its_driver_is_left_alone(url):
    assert with_installed_driver(url) == url


@pytest.mark.slow
def test_the_app_can_import_its_database_layer_against_postgres():
    """The production failure, reproduced: import utils.db in a fresh process
    with a Render-style URL. create_engine loads the DBAPI without connecting,
    so a missing driver fails here exactly as it did on Render."""
    env = {k: v for k, v in os.environ.items() if k != "UNSTRUCTURED_ALPHA_DATABASE_URL"}
    env["DATABASE_URL"] = "postgresql://u:p@127.0.0.1:1/ua"
    proc = subprocess.run(
        [sys.executable, "-c", "from utils import db; print(db.engine.dialect.driver)"],
        cwd=_ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().splitlines()[-1] == "psycopg2"
