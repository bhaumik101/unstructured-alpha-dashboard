"""What every button state resolves to today, pinned against the BUILT stylesheet.

The button surface is declared across two source files and 38 rule blocks in the
generated CSS. Reading either file answers nothing: the same selector is
declared in utils/header.py and utils/theme.py, they are concatenated at build
time by scripts/inject_boot_splash.build_global_css(), and !important plus
source order decide the winner.

So this tests the OUTPUT, and it exists to make a consolidation provable rather
than hopeful. The values below are a characterisation of current production
behaviour, captured from the built stylesheet. Any restructuring of the button
CSS must leave them identical -- if a value here changes, the refactor changed
what a user sees, whatever the diff looked like.

WHY @media IS NOT FLATTENED
---------------------------
`@media (prefers-reduced-motion: reduce)` sets `transition: none !important` on
buttons. Resolve the cascade without media context and that looks like the
winner for every button in the app, and a "cleanup" deletes every transition
while its tests still pass. That mistake was made in this codebase in #150, and
made again in the first pass of this analysis before the resolver was written.
The default state and the reduced-motion state are resolved separately.

WHAT THIS IS NOT
----------------
Not a browser. It models specificity, !important, source order and @media as a
filter. That is enough to compare before/after of a refactor. It is not enough
to certify the design, which is what the post-deploy browser check is for.
"""

from __future__ import annotations

import re

import pytest

from tests.support.css_cascade import declarations_for, iter_rules, resolved_values

REDUCED_MOTION = "@media (prefers-reduced-motion: reduce)"


@pytest.fixture(scope="module")
def css() -> str:
    from scripts.inject_boot_splash import build_global_css
    return build_global_css()


def _exact(*selectors):
    want = set(selectors)
    return lambda s: s in want


def test_the_built_stylesheet_is_what_we_are_testing(css):
    """Guard against silently testing an empty or truncated build."""
    assert len(css) > 50_000, f"built stylesheet is only {len(css)} bytes"
    btn_rules = [
        s for _, group, _, _ in iter_rules(css)
        for s in group.split(",") if "stButton" in s
    ]
    assert len(btn_rules) >= 30, (
        f"only {len(btn_rules)} button selectors in the build; the concatenation "
        "may have dropped a source block"
    )


def test_base_button_resolves_to_the_expected_surface(css):
    v = resolved_values(css, _exact(".stButton > button"))
    assert v["background"] == "var(--ua-surface)"
    assert v["color"] == "var(--ua-text-mid)"
    assert v["border"] == "1px solid var(--ua-hair)"
    assert v["border-radius"] == "8px"
    assert v["min-height"] == "36px"
    assert v["font-weight"] == "600"
    assert v["cursor"] == "pointer"


def test_the_base_button_animates_by_default(css):
    """The reduced-motion rule must not leak into the default state."""
    v = resolved_values(css, _exact(".stButton > button"))
    assert "transition" in v, "buttons have no transition at all in the default state"
    assert v["transition"] != "none", (
        "the default state resolved to `transition: none` -- that value belongs "
        "to the reduced-motion query and has leaked into every button"
    )
    assert v.get("transform") != "none", (
        "the default state resolved to `transform: none`, which is the "
        "reduced-motion value"
    )


def test_reduced_motion_still_removes_motion(css):
    v = resolved_values(
        css, lambda s: s.startswith(".stButton > button"), media=(REDUCED_MOTION,)
    )
    assert v.get("transition") == "none", (
        "prefers-reduced-motion no longer disables button transitions"
    )
    assert v.get("transform") == "none"


@pytest.mark.parametrize(
    "state, selectors",
    [
        ("hover", (".stButton > button:hover",)),
        ("focus-visible", (".stButton > button:focus-visible",)),
        ("primary", ('.stButton > button[kind="primary"]',
                     '.stButton > button[data-testid="baseButton-primary"]')),
        ("primary hover", ('.stButton > button[kind="primary"]:hover',
                           '.stButton > button[data-testid="baseButton-primary"]:hover')),
        ("primary active", ('.stButton > button[kind="primary"]:active',
                            '.stButton > button[data-testid="baseButton-primary"]:active')),
        ("sidebar", ('section[data-testid="stSidebar"] .stButton > button',)),
        ("light base", ('html[data-ua-theme="light"] .stButton > button',)),
        ("light primary", ('html[data-ua-theme="light"] .stButton > button[kind="primary"]',)),
    ],
)
def test_every_state_still_declares_something(css, state, selectors):
    """A state that resolves to nothing has been consolidated out of existence."""
    v = resolved_values(css, _exact(*selectors))
    assert v, f"the {state} state resolves to no declarations at all"


def test_focus_is_visible_and_not_merely_outline_none(css):
    """Removing the outline without replacing it makes the app unkeyboardable."""
    v = resolved_values(css, _exact(".stButton > button:focus-visible"))
    if v.get("outline") in {"none", "0"}:
        assert "box-shadow" in v and v["box-shadow"] != "none", (
            "focus-visible removes the outline and provides no replacement ring"
        )


def test_primary_is_distinguishable_from_secondary(css):
    base = resolved_values(css, _exact(".stButton > button"))
    primary = resolved_values(
        css,
        _exact('.stButton > button[kind="primary"]',
               '.stButton > button[data-testid="baseButton-primary"]'),
    )
    assert primary.get("background") and primary["background"] != base.get("background"), (
        "primary and secondary buttons resolve to the same background"
    )


def test_no_button_rule_uses_transition_all(css):
    """`transition: all` animates layout properties and was removed once already."""
    offenders = []
    for stack, group, body, _ in iter_rules(css):
        if "stButton" not in group:
            continue
        for decl in body.split(";"):
            if re.match(r"\s*transition\s*:\s*all\b", decl):
                offenders.append(f"{' '.join(group.split())[:70]} -> {decl.strip()[:50]}")
    assert not offenders, "transition: all is back on a button rule:\n  " + "\n  ".join(offenders)


def test_important_is_not_load_bearing_by_accident(css):
    """Most button declarations are !important; that is the cascade this refactor
    has to preserve. Recorded so a consolidation that drops them is visible."""
    decls = declarations_for(css, lambda s: s.startswith(".stButton > button"))
    important = [d for d in decls.values() if d.important]
    assert len(important) >= 10, (
        f"only {len(important)} winning button declarations are !important; the "
        "cascade this stylesheet relies on has changed shape"
    )
