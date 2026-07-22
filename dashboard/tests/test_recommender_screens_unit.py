"""Tests for private, bounded Stock Recommender saved screens."""

import pytest
from sqlalchemy import delete

from utils import db
from utils.recommender_screens import (
    MAX_SAVED_SCREENS,
    delete_screen,
    list_saved_screens,
    normalize_screen_config,
    save_screen,
)


_USERS = (9401, 9402)
_SECTORS = {"Technology", "Energy", "Financials"}


@pytest.fixture(autouse=True)
def _clean_screens():
    db.init_db()
    with db.engine.begin() as conn:
        conn.execute(delete(db.saved_recommender_screens).where(
            db.saved_recommender_screens.c.user_id.in_(_USERS)
        ))
    yield
    with db.engine.begin() as conn:
        conn.execute(delete(db.saved_recommender_screens).where(
            db.saved_recommender_screens.c.user_id.in_(_USERS)
        ))


def _config(**overrides):
    return {
        "time_horizon": "Long-term (3+ mo)",
        "n_show": 9,
        "n_enrich": 12,
        "min_signals": 3,
        "sectors": ["Technology", "Energy"],
        **overrides,
    }


def test_save_update_and_list_screen_round_trip():
    first = save_screen(9401, "Long-term leaders", _config(), allowed_sectors=_SECTORS)
    updated = save_screen(9401, "long-term leaders", _config(n_show=6), allowed_sectors=_SECTORS)

    assert updated["id"] == first["id"]
    screens = list_saved_screens(9401, allowed_sectors=_SECTORS)
    assert len(screens) == 1
    assert screens[0]["name"] == "Long-term leaders"
    assert screens[0]["config"]["n_show"] == 6


def test_screens_are_private_and_delete_is_user_scoped():
    screen = save_screen(9401, "Energy setup", _config(sectors=["Energy"]), allowed_sectors=_SECTORS)
    assert list_saved_screens(9402, allowed_sectors=_SECTORS) == []
    assert delete_screen(9402, screen["id"]) is False
    assert delete_screen(9401, screen["id"]) is True
    assert list_saved_screens(9401, allowed_sectors=_SECTORS) == []


def test_config_rejects_out_of_bounds_and_drops_unknown_sectors():
    clean = normalize_screen_config(_config(sectors=["Technology", "Unknown", "Technology"]), allowed_sectors=_SECTORS)
    assert clean["sectors"] == ["Technology"]
    with pytest.raises(ValueError):
        normalize_screen_config(_config(n_enrich=200), allowed_sectors=_SECTORS)


def test_per_user_limit_does_not_block_updating_existing_screen():
    for index in range(MAX_SAVED_SCREENS):
        save_screen(9401, f"Screen {index}", _config(n_show=3 + index % 10), allowed_sectors=_SECTORS)
    save_screen(9401, "screen 0", _config(n_show=15), allowed_sectors=_SECTORS)
    with pytest.raises(ValueError, match="up to"):
        save_screen(9401, "One too many", _config(), allowed_sectors=_SECTORS)
