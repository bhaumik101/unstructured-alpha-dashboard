"""Inline SVG charts must go through st.markdown, never st.html.

Shipped as a live regression in #158: the per-card sparkline on Signal
Dashboard was emitted with `st.html(ua_charts.line_chart(...))`. st.html
sanitises against an allowlist that drops <svg>, so the chart rendered as
nothing at all.

It was hard to see because the failure is silent and partial. The caption that
prints immediately AFTER the sparkline still appeared, so the section looked
populated -- measured on the deployed page, the expander body carried 15,674
characters of HTML and zero <svg> elements. Only counting `.ua-chart` in the
live DOM surfaced it.

Every other ua_charts caller in the app already used st.markdown with
unsafe_allow_html. This pins that.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_CHART_FNS = ("line_chart", "bar_h", "bar_v")


def _sources():
    for path in list(_ROOT.glob("pages/*.py")) + list(_ROOT.glob("utils/*.py")):
        if path.name == "ua_charts.py":
            continue
        yield path, path.read_text(encoding="utf-8")


def test_no_chart_helper_output_goes_through_st_html():
    bad = []
    for path, src in _sources():
        for m in re.finditer(r"st\.html\(\s*(?:[\w_]+\.)?(" + "|".join(_CHART_FNS) + r")\(", src):
            line = src[: m.start()].count("\n") + 1
            bad.append(f"{path.name}:{line} st.html({m.group(1)}(...))")
    assert not bad, (
        "st.html drops <svg>; these charts render as nothing:\n" + "\n".join(bad)
    )


def test_chart_helpers_called_inline_pass_unsafe_allow_html():
    """A bare st.markdown(svg) escapes the markup instead of rendering it.

    Deliberately narrow: this only matches a chart helper invoked DIRECTLY as
    the first argument, which is the shape the #158 bug took. Proximity
    heuristics were tried first and produced false positives on both
    `st.markdown("### 3. Weekly ...")` in Admin and a Home block that assigns
    `_svg = _uac.bar_v(...)` and renders it several lines later. A test that
    cries wolf gets deleted, so it is better to catch one shape reliably.
    """
    call = re.compile(
        r"st\.markdown\(\s*(?:[\w_]+\.)?(" + "|".join(_CHART_FNS) + r")\(",
    )
    bad = []
    for path, src in _sources():
        for m in call.finditer(src):
            depth, i = 0, m.start() + len("st.markdown")
            while i < len(src):                      # walk to the matching paren
                if src[i] == "(":
                    depth += 1
                elif src[i] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            if "unsafe_allow_html=True" not in src[m.start() : i]:
                bad.append(f"{path.name}:{src[: m.start()].count(chr(10)) + 1}")
    assert not bad, (
        "these render chart SVG through st.markdown without "
        "unsafe_allow_html=True, so the markup is escaped:\n" + "\n".join(bad)
    )
