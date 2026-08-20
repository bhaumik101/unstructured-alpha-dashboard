"""The check that asks the public internet, not the repo.

cron/check_data_freshness.py asks "is the data still arriving?". This is its
sibling for the other silent failure: "is what we publish still reachable on the
domain we publish it under?"

It exists because /brief shipped serving 200 on seo.unstructuredalpha.com and
404 on www. Every component was individually healthy -- the service was up,
/version reported the right commit, the unit tests passed -- and the failure
lived in the seam between them: the marketing site proxies a hand-written list
of paths, and a route added to the service is not added to that list.

The sitemap advertised the www URL to Google, and the subscriber email pointed
its "Read in browser" link at the same dead address.

Verified against production after the fix: /brief is one of the URLs this check
samples, so it would have caught the original break.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_SRC = (
    Path(__file__).resolve().parent.parent / "cron" / "check_public_surfaces.py"
).read_text(encoding="utf-8")


def test_it_checks_the_canonical_host_not_the_service_that_serves_it():
    """Checking seo.* would have passed while readers got a 404."""
    m = re.search(r'CANONICAL\s*=\s*os\.environ\.get\(\s*"([A-Z_]+)"\s*,\s*"([^"]+)"', _SRC)
    assert m, "CANONICAL is no longer resolved from an env var with a default"
    var, default = m.group(1), m.group(2)
    assert var == "SEO_BASE_URL"
    assert "www.unstructuredalpha.com" in default, (
        f"default host is {default!r}. Pointing this at the SEO service's own "
        "hostname makes it pass on exactly the bug it exists to catch."
    )


def test_a_missing_sitemap_fails_rather_than_reporting_nothing_wrong():
    """Zero checks and zero failures are not the same result."""
    fn = next(
        n for n in ast.walk(ast.parse(_SRC))
        if isinstance(n, ast.FunctionDef) and n.name == "main"
    )
    src = ast.get_source_segment(_SRC, fn) or ""
    i = src.index("sitemap_err")
    window = src[i: i + 400]
    assert "return 1" in window, (
        "an unreachable sitemap returns success, so a total outage would report "
        "'all reachable' having checked nothing"
    )


def test_every_distinct_path_shape_is_sampled():
    """New route types must be covered without editing this cron."""
    from cron.check_public_surfaces import _sample
    urls = (
        [f"https://x.test/ticker/T{i}" for i in range(50)]
        + [f"https://x.test/signal/s{i}" for i in range(50)]
        + ["https://x.test/brief", "https://x.test/brief/9"]
        + ["https://x.test/signals/report", "https://x.test/"]
    )
    sampled = _sample(urls)
    # Parse the path rather than indexing into the split URL — index math gets
    # the root URL wrong and fails on a sampler that is behaving correctly.
    from urllib.parse import urlparse
    heads = {urlparse(u).path.strip("/").split("/")[0] or "root" for u in sampled}
    for expected in ("ticker", "signal", "brief", "signals"):
        assert expected in heads, (
            f"no {expected!r} URL was sampled; a break in that route shape would "
            "go unnoticed"
        )


def test_sampling_is_bounded_so_the_check_stays_cheap():
    from cron.check_public_surfaces import _sample, _SAMPLE_PER_PATTERN
    urls = [f"https://x.test/ticker/T{i}" for i in range(400)]
    assert len(_sample(urls)) <= _SAMPLE_PER_PATTERN, (
        "sampling is unbounded; this would fetch every ticker page every morning"
    )


def test_failure_exits_non_zero_so_render_surfaces_it():
    assert re.search(r"return 1", _SRC), "the check can no longer fail"
    assert "sys.exit(main())" in _SRC, (
        "main()'s return code is not propagated, so Render records success "
        "regardless of what the check found"
    )


def test_run_group_honours_a_non_zero_return_not_only_exceptions():
    """Grouping the watchdogs is only safe because of this.

    run_group() called module.main() and treated ONLY a raised exception as
    failure. Both health jobs report failure by RETURNING non-zero -- so
    grouping them without this change would have let a stalled pipeline or a
    404 on the canonical host exit 0, silently, which is the exact failure the
    watchdogs exist to prevent.

    Harmless before now only because every previously grouped job returns None.
    """
    import sys as _sys
    import types as _types
    import cron.run_group as rg

    mod = _types.ModuleType("cron._probe_fail")
    mod.main = lambda: 1
    _sys.modules["cron._probe_fail"] = mod
    rg.GROUPS["_probe_fail"] = ("cron._probe_fail",)
    try:
        assert rg.run_group("_probe_fail") == 1, (
            "a grouped job returning 1 did not fail the group"
        )
    finally:
        rg.GROUPS.pop("_probe_fail", None)
        _sys.modules.pop("cron._probe_fail", None)


def test_a_grouped_job_returning_none_still_counts_as_success():
    """Every pre-existing grouped job returns None; none may start failing."""
    import sys as _sys
    import types as _types
    import cron.run_group as rg

    mod = _types.ModuleType("cron._probe_ok")
    mod.main = lambda: None
    _sys.modules["cron._probe_ok"] = mod
    rg.GROUPS["_probe_ok"] = ("cron._probe_ok",)
    try:
        assert rg.run_group("_probe_ok") == 0
    finally:
        rg.GROUPS.pop("_probe_ok", None)
        _sys.modules.pop("cron._probe_ok", None)
