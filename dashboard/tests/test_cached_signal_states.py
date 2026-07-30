"""The chrome's snapshot read is cached, without breaking cron or the SSOT.

Global chrome (the regime bar) reads the persisted snapshot on every page and
every rerun. Uncached that is a Postgres round trip blocking paint on each
navigation -- and because the top nav performs full browser navigations, that
means every single click.

An earlier attempt cached it inside utils/score_history.py and was reverted.
That module is deliberately free of any streamlit import so cron/worker
processes can use it. These tests pin both properties: the read is cached, and
score_history stays importable without streamlit.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_score_history_stays_free_of_streamlit():
    """Cron and worker processes import this module; a streamlit dependency
    there is what got the previous attempt reverted."""
    # The import IS the invariant: @st.cache_data cannot function without it, so
    # asserting on the import is both necessary and sufficient. Grepping for the
    # decorator text instead gives a false positive -- the module docstring
    # legitimately discusses "@st.cache_data" in prose at line ~877.
    import ast

    tree = ast.parse((ROOT / "utils" / "score_history.py").read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    assert not any(name.split(".")[0] == "streamlit" for name in imported), (
        "score_history must stay importable by cron/worker processes"
    )


def test_cached_reader_exists_and_is_cached():
    from utils import signals_cache

    fn = signals_cache.get_cached_signal_states
    # st.cache_data wraps the function and exposes .clear() for invalidation.
    assert hasattr(fn, "clear"), "not wrapped by st.cache_data"
    assert signals_cache.LATEST_SIGNAL_STATES_TTL_SECONDS <= 300, (
        "TTL too long: a fresh snapshot must surface quickly"
    )


def test_repeated_reads_agree_so_chrome_and_hero_cannot_diverge():
    """The header bar, hero, narrative and data banner must describe ONE
    snapshot. Numbers disagreeing across surfaces shipped once and destroyed
    trust in the data; equal reads are what prevent it."""
    from utils import signals_cache

    first = signals_cache.get_cached_signal_states()
    second = signals_cache.get_cached_signal_states()
    assert first == second


def test_header_prefers_the_cached_reader():
    """render_header must go through the cached path, with the uncached direct
    read only as a fallback if signals_cache is unavailable."""
    src = (ROOT / "utils" / "header.py").read_text(encoding="utf-8")
    assert "get_cached_signal_states" in src

    cached_at = src.index("get_cached_signal_states")
    direct_at = src.index("get_latest_signal_states as _glss")
    assert cached_at < direct_at, "cached read should be attempted first"
