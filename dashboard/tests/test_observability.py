"""Tests for utils.observability — JSON logging + correlation ids."""
import json
import logging

from utils import observability as obs


def _capture(func):
    """Configure logging to a buffer, run func, return parsed JSON lines."""
    import io
    obs.configure_logging(force=True)
    root = logging.getLogger()
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(obs._JsonFormatter())
    h.addFilter(obs._CorrelationFilter())
    root.addHandler(h)
    try:
        func()
    finally:
        root.removeHandler(h)
    return [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]


def test_log_line_is_json_with_core_fields():
    rows = _capture(lambda: logging.getLogger("t").warning("hello"))
    assert rows and rows[-1]["msg"] == "hello"
    for key in ("ts", "level", "logger", "msg", "cid"):
        assert key in rows[-1]
    assert rows[-1]["level"] == "WARNING"


def test_correlation_id_is_stamped():
    obs.set_correlation_id("abc123def456")
    rows = _capture(lambda: logging.getLogger("t").error("boom"))
    assert rows[-1]["cid"] == "abc123def456"


def test_set_correlation_id_generates_when_none():
    cid = obs.set_correlation_id()
    assert len(cid) == 12 and obs.get_correlation_id() == cid


def test_log_event_merges_structured_fields():
    obs.set_correlation_id("evt000000000")
    rows = _capture(lambda: obs.log_event("rate_limit_block", action="export", n=5))
    row = rows[-1]
    assert row["event"] == "rate_limit_block"
    assert row["action"] == "export"
    assert row["n"] == 5
    assert row["cid"] == "evt000000000"


def test_non_serialisable_extra_is_stringified():
    class Weird:
        def __repr__(self):
            return "<weird>"

    rows = _capture(lambda: obs.log_event("x", obj=Weird()))
    assert rows[-1]["obj"] == "<weird>"


def test_log_event_never_raises():
    # Passing a self-referential structure must not blow up the caller.
    d = {}
    d["self"] = d
    obs.log_event("x", loop=d)  # should silently degrade
