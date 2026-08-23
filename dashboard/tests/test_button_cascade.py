"""What every button state resolves to today, pinned against the BUILT stylesheet.

The button surface is declared across two source files and 47 rule blocks in the
generated CSS, spanning 60 distinct button selectors and eight widgets -- button,
download_button, form_submit_button, link_button, popover, segmented_control,
pills, and the sidebar variants of several. (Counted over the built stylesheet:
blocks whose selector group mentions a button, excluding the two Plotly
rangeselector `.button` rules, which are SVG chart controls, not DOM buttons.) Reading either file answers nothing: the same selector is
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


# ── Streamlit's internal attribute renamed under us ──────────────────────────

def test_no_rule_depends_on_the_obsolete_baseButton_testid(css):
    """data-testid="baseButton-*" matches nothing in production.

    Verified in the browser on 2026-08-21 across two pages: zero elements match
    [data-testid^="baseButton-"], and every button carries stBaseButton-*
    instead. Streamlit renamed an internal test identifier, and the stylesheet
    was keyed to it.

    The damage was not just dead rules. The secondary group included
    `.stButton > button:not([data-testid="baseButton-primary"])`, and an
    exclusion referencing a non-existent attribute excludes NOTHING -- so it
    matched primary buttons too, at equal specificity and later in the cascade.
    Every primary button was painted with the secondary surface.
    """
    assert "baseButton-" not in css, (
        "a rule is keyed to data-testid=\"baseButton-*\", which Streamlit no "
        "longer emits. Key off [kind] instead -- it is the semantic attribute, "
        "not an internal identifier, and it is what survived the rename."
    )


def test_primary_and_secondary_resolve_to_different_surfaces(css):
    """The defect this PR fixes, stated as the invariant it broke."""
    primary = resolved_values(
        css, _exact(".stButton > button", '.stButton > button[kind="primary"]')
    )
    secondary = resolved_values(
        css, _exact(".stButton > button", '.stButton > button:not([kind="primary"])')
    )
    assert primary.get("background") != secondary.get("background"), (
        "primary and secondary buttons resolve to the same background — the app "
        "has no visually distinct primary action"
    )


def test_the_secondary_exclusion_uses_an_attribute_that_exists(css):
    """A :not() on a missing attribute silently matches everything."""
    exclusions = re.findall(r":not\(\[([a-zA-Z-]+)=", css)
    unknown = sorted({a for a in exclusions if a not in {"kind", "aria-checked",
                                                         "aria-pressed", "disabled",
                                                         "data-baseweb", "tabindex",
                                                         "data-testid", "type", "hidden",
                                                         "aria-selected", "open", "class",
                                                         "style", "role", "id", "name",
                                                         "value", "href", "target", "rel",
                                                         "aria-expanded", "data-ua-theme"}})
    assert not unknown, f"exclusion keyed on unexpected attribute(s): {unknown}"


# ── Selectors checked against a real Streamlit DOM ───────────────────────────
# Captured 2026-08-23 from Streamlit 1.51 (requirements.txt pins >=1.38,<2) by
# rendering one page containing every button widget the stylesheet targets --
# form_submit_button, button, download_button, link_button, popover,
# segmented_control, pills, radio -- and counting querySelectorAll matches.
#
# Reading the stylesheet cannot tell you a selector is dead. #194 shipped a
# stylesheet keyed to data-testid="baseButton-*" after Streamlit renamed it, and
# every primary button was painted with the secondary surface for as long as it
# took someone to check the DOM. These are the selectors that check found
# matching NOTHING, kept here so the next reader does not have to re-derive it.

_DEAD_SELECTORS = {
    '[data-testid="stFormSubmitButton"] button[key="global_ticker_submit"]':
        "`key` is a reserved React prop -- React never forwards it to the DOM, "
        "so `button[key]` matched 0 of 5 buttons. Streamlit exposes the widget "
        "key as the `.st-key-<key>` CLASS on the element container instead, and "
        "the sibling selector in this same rule already uses it.",
    '[data-testid="stPopover"] > button':
        "the trigger is a GRANDCHILD: stPopover > div[aria-haspopup] > button. "
        "The child combinator matches nothing. The light-theme rules for the "
        "same control use a descendant combinator and do apply.",
    '[data-testid="stButtonGroup"] button[aria-checked="true"]':
        "segmented_control/pills mark selection with kind=\'segmented_controlActive\' "
        "and kind=\'pillsActive\'. aria-checked was null on all 4 group buttons.",
    '[data-testid="stButtonGroup"] button[aria-pressed="true"]':
        "same as aria-checked -- aria-pressed was null on all 4 group buttons.",
    '[data-testid="stButtonGroup"] label:has(input:checked)':
        "the only labels inside stButtonGroup are the stWidgetLabel captions "
        "(\'Seg\', \'Pills\'), which contain no input. The :has() form does work "
        "for st.radio, which is not what this rule is scoped to.",
}


def test_the_dead_selector_registry_is_current(css):
    """Every selector recorded as dead is still in the stylesheet.

    Fixing one means deleting it here in the same commit. Without this the
    registry rots into a list of claims about CSS that no longer exists.
    """
    stale = [s for s in _DEAD_SELECTORS if s not in css]
    assert not stale, (
        "these selectors are recorded as dead but are no longer in the built "
        "stylesheet -- drop them from _DEAD_SELECTORS:\n  " + "\n  ".join(stale)
    )


def test_the_ticker_submit_sizing_never_reaches_the_button(css):
    """Characterises a live defect. Fixing it means updating this test.

    utils/header.py styles the global ticker search submit through a two-selector
    group: `.st-key-global_ticker_submit button` (live) and
    `[data-testid="stFormSubmitButton"] button[key="global_ticker_submit"]`
    (dead -- see _DEAD_SELECTORS). Only the dead half carries enough specificity
    to win.

    Live selector      (0,1,1) at source order 192
    .stFormSubmitButton > button (0,1,1) at source order 518  <- wins on order

    So six of the seven declarations lose to the generic form-submit rule. The
    button renders as a royal-gradient primary 36px tall, not the flat grey 42px
    the block asks for. `min-width: 138px` survives only because nothing else
    declares it -- which is why the label-wrapping symptom the comment describes
    stayed fixed while the rest of the intent quietly did not apply.
    """
    declared = resolved_values(css, _exact(*_STATES["ticker_submit_as_declared"]))
    rendered = resolved_values(css, _exact(*_STATES["ticker_submit_as_rendered"]))

    assert declared["min-width"] == rendered["min-width"] == "138px", (
        "min-width is uncontested and should apply under both readings"
    )
    lost = sorted(p for p in declared if declared[p] != rendered.get(p))
    assert lost == ["background", "border", "box-shadow", "color", "min-height",
                    "padding"], f"the set of out-voted declarations moved: {lost}"
    assert rendered["min-height"] == "36px" and declared["min-height"] == "42px"


def test_the_dark_theme_popover_trigger_is_unstyled(css):
    """Characterises a live defect. Fixing it means updating this test.

    The only dark-theme rule for the popover trigger uses a child combinator
    against a grandchild, so nothing in the dark theme reaches that button. The
    light theme styles the same control through a descendant combinator and
    works. A control that is themed in one mode and bare in the other is the
    kind of asymmetry a stylesheet read cannot surface.
    """
    declared = resolved_values(css, _exact(*_STATES["popover_as_declared"]))
    rendered = resolved_values(css, _exact(*_STATES["popover_as_rendered"]))
    light = resolved_values(css, _exact(*_STATES["light_popover"]))

    assert declared, "the dark popover rule vanished; update _DEAD_SELECTORS"
    assert rendered == {}, (
        "the dark-theme popover trigger now resolves to something -- if that is "
        "the fix, drop the selector from _DEAD_SELECTORS and update this test"
    )
    assert light, "the light theme lost its popover styling"


def test_button_group_selection_is_keyed_to_attributes_that_are_never_emitted(css):
    """Characterises a live defect. Fixing it means updating this test.

    Both themes style the selected segment via [aria-checked] / [aria-pressed].
    Streamlit signals selection with kind="segmented_controlActive" and
    kind="pillsActive"; the aria attributes are null. So the selected pill and
    the unselected pill resolve to the same surface, and the control has no
    visible selection state of our making -- the same failure mode as #194,
    where an exclusion on a missing attribute excluded nothing.
    """
    for base_state, sel_state in (("group", "group_checked"),
                                  ("group", "group_pressed"),
                                  ("light_group", "light_group_checked")):
        base = resolved_values(css, _exact(*_STATES[base_state]))
        selected = resolved_values(css, _exact(*_STATES[sel_state]))
        assert base and selected
        assert base["background"] != selected["background"], (
            f"{sel_state} no longer differs from {base_state} in the stylesheet"
        )
    # The stylesheet distinguishes them; the DOM never asks for the distinction.
    assert all(s in css for s in (
        '[data-testid="stButtonGroup"] button[aria-checked="true"]',
        '[data-testid="stButtonGroup"] button[aria-pressed="true"]',
    ))


# ── Characterisation snapshot ────────────────────────────────────────────────
# tests/support/button_states.json holds every resolved declaration for the 54
# button states below, captured from the built stylesheet. It is the safety net
# for consolidation: a refactor that changes a computed value fails here even if
# the diff looks harmless, and a refactor that only removes shadowed
# declarations passes without needing to be trusted.
#
# #195 modelled 16 states and said so plainly: consolidating the remaining rule
# blocks would be blind, because the harness did not model the surfaces they
# cover. This list is that gap closed. The 16 original states resolve to
# byte-identical values here -- the growth is coverage, not a re-baseline.
#
# What the 38 added states cover, and why each needed its own entry:
#   - label text. Streamlit wraps every label in <p>, so `button p` decides the
#     text colour. Six states; none of it was modelled.
#   - the ::after sheen. Its own box and animation, invisible to every state
#     that resolves the button itself.
#   - download / form-submit / link-button / popover, the sibling widgets that
#     share the foundation rule but diverge on hover.
#   - segmented_control and pills, an entire control with no coverage at all.
#   - eight more light-theme states; only two of the pair were modelled.
#   - seven more reduced-motion states. One per animating surface, or a
#     "cleanup" can delete the query for a single widget and stay green.
#
# Every one of them is mutation-tested: perturbing the declaration each state
# depends on fails that state, and the tree is verified clean before and after.
# Two cautions learned doing it -- run each mutation in a FRESH process (the
# stylesheet builders cache), and clear __pycache__ between runs (a same-length
# edit inside the mtime granularity is served from a stale .pyc, which reads as
# a passing mutation and is not one).
#
# To change it deliberately: make the change, confirm the diff this test prints
# is what you intended, and update the fixture in the same commit.

_LIGHT = 'html[data-ua-theme="light"]'
_GROUP = '[data-testid="stButtonGroup"]'
_SIDEBAR = 'section[data-testid="stSidebar"]'

_STATES = {
    # ── .stButton: the main surface ──────────────────────────────────────────
    "base": (".stButton > button",),
    "hover": (".stButton > button", ".stButton > button:hover"),
    "active": (".stButton > button", ".stButton > button:active"),
    "focus": (".stButton > button", ".stButton > button:focus-visible"),
    "primary": (".stButton > button", '.stButton > button[kind="primary"]'),
    "primary_hover": (".stButton > button", '.stButton > button[kind="primary"]',
                      '.stButton > button[kind="primary"]:hover'),
    "primary_active": (".stButton > button", '.stButton > button[kind="primary"]',
                       '.stButton > button[kind="primary"]:active'),
    "secondary": (".stButton > button", '.stButton > button:not([kind="primary"])'),
    "secondary_hover": (".stButton > button", '.stButton > button:not([kind="primary"])',
                        '.stButton > button:not([kind="primary"]):hover'),
    "secondary_active": (".stButton > button", '.stButton > button:not([kind="primary"])',
                         '.stButton > button:not([kind="primary"]):active'),

    # ── the ::after sheen overlay ────────────────────────────────────────────
    # Its own box, its own animation. A consolidation that drops the overlay
    # changes nothing in any state above, so it needs states of its own.
    "after_base": (".stButton > button::after",),
    "after_active": (".stButton > button::after", ".stButton > button:active::after"),

    # ── label text: the pixels a reader actually looks at ────────────────────
    # Streamlit wraps every button label in <p>, so `button p` -- not `button`
    # -- decides the text colour. None of this was modelled before.
    "label_base": (".stButton > button p",),
    "label_sidebar": (f'{_SIDEBAR} .stButton > button p',),
    "label_sidebar_span": (f'{_SIDEBAR} .stButton > button span',),
    "label_download": (".stDownloadButton > button p",),
    "label_link": (".stLinkButton > a p",),
    "label_basebutton": ('button[data-testid^="stBaseButton"] p',),

    # ── sibling button widgets ───────────────────────────────────────────────
    "download": (".stDownloadButton > button",),
    "download_hover": (".stDownloadButton > button", ".stDownloadButton > button:hover"),
    "form_submit": (".stFormSubmitButton > button",),
    "form_submit_hover": (".stFormSubmitButton > button", ".stFormSubmitButton > button:hover"),
    "link_button": (".stLinkButton > a",),
    "link_button_hover": (".stLinkButton > a", ".stLinkButton > a:hover"),

    # Two readings, and they disagree -- see
    # test_the_ticker_submit_sizing_never_reaches_the_button.
    "popover_as_declared": ('[data-testid="stPopover"] > button',),
    "popover_as_rendered": ('[data-testid="stPopoverButton"]',),
    "ticker_submit_as_declared": (".stFormSubmitButton > button",
                                  ".st-key-global_ticker_submit button",
                                  '[data-testid="stFormSubmitButton"] '
                                  'button[key="global_ticker_submit"]'),
    "ticker_submit_as_rendered": (".stFormSubmitButton > button",
                                  ".st-key-global_ticker_submit button"),

    # ── sidebar ──────────────────────────────────────────────────────────────
    "sidebar": (f'{_SIDEBAR} .stButton > button',),
    "sidebar_hover": (f'{_SIDEBAR} .stButton > button',
                      f'{_SIDEBAR} .stButton > button:hover'),

    # ── segmented control / pills ────────────────────────────────────────────
    "group": (f'{_GROUP} button',),
    "group_checked": (f'{_GROUP} button', f'{_GROUP} button[aria-checked="true"]'),
    "group_pressed": (f'{_GROUP} button', f'{_GROUP} button[aria-pressed="true"]'),
    "group_label": (f'{_GROUP} label',),
    "group_label_checked": (f'{_GROUP} label', f'{_GROUP} label:has(input:checked)'),

    # ── light theme ──────────────────────────────────────────────────────────
    "light_base": (f'{_LIGHT} .stButton > button',),
    "light_primary": (f'{_LIGHT} .stButton > button[kind="primary"]',),
    "light_secondary": (f'{_LIGHT} button[data-testid="stBaseButton-secondary"]',),
    "light_secondary_hover": (f'{_LIGHT} button[data-testid="stBaseButton-secondary"]',
                              f'{_LIGHT} button[data-testid="stBaseButton-secondary"]:hover'),
    "light_group": (f'{_LIGHT} {_GROUP} button',),
    "light_group_hover": (f'{_LIGHT} {_GROUP} button', f'{_LIGHT} {_GROUP} button:hover'),
    "light_group_checked": (f'{_LIGHT} {_GROUP} button',
                            f'{_LIGHT} {_GROUP} button[aria-checked="true"]'),
    "light_group_label_checked": (f'{_LIGHT} {_GROUP} label',
                                  f'{_LIGHT} {_GROUP} label:has(input:checked)'),
    "light_popover": (f'{_LIGHT} [data-testid="stPopover"] button',),
    "light_popover_button": (f'{_LIGHT} [data-testid="stPopoverButton"]',),

    # ── reduced motion ───────────────────────────────────────────────────────
    # Every surface that animates needs its own reduced-motion state, or a
    # "cleanup" can delete the query for that surface alone and stay green.
    "rm_base": (".stButton > button",),
    "rm_primary_active": (".stButton > button", '.stButton > button[kind="primary"]:active'),
    "rm_hover": (".stButton > button", ".stButton > button:hover"),
    "rm_secondary_hover": (".stButton > button", '.stButton > button:not([kind="primary"])',
                           '.stButton > button:not([kind="primary"]):hover'),
    "rm_sidebar": (f'{_SIDEBAR} .stButton > button',),
    "rm_download_hover": (".stDownloadButton > button", ".stDownloadButton > button:hover"),
    "rm_link_hover": (".stLinkButton > a", ".stLinkButton > a:hover"),
    "rm_form_hover": (".stFormSubmitButton > button", ".stFormSubmitButton > button:hover"),
    "rm_after_active": (".stButton > button::after", ".stButton > button:active::after"),
}

_RM_STATES = {
    "rm_base", "rm_primary_active", "rm_hover", "rm_secondary_hover", "rm_sidebar",
    "rm_download_hover", "rm_link_hover", "rm_form_hover", "rm_after_active",
}


def test_every_button_state_matches_the_recorded_snapshot(css):
    import json
    from pathlib import Path

    fixture = Path(__file__).parent / "support" / "button_states.json"
    expected = json.loads(fixture.read_text(encoding="utf-8"))

    changes = []
    for state, selectors in _STATES.items():
        media = (REDUCED_MOTION,) if state in _RM_STATES else ()
        actual = resolved_values(css, _exact(*selectors), media=media)
        want = expected.get(state, {})
        for prop in sorted(set(want) | set(actual)):
            if want.get(prop) != actual.get(prop):
                changes.append(
                    f"{state}.{prop}: {want.get(prop)!r} -> {actual.get(prop)!r}"
                )
    assert not changes, (
        f"{len(changes)} resolved button value(s) changed:\n  "
        + "\n  ".join(changes[:20])
        + "\n\nIf intended, update tests/support/button_states.json in the same "
          "commit. If not, the refactor changed what a user sees."
    )
