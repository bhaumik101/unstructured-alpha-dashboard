"""The funnel a founder needs to see must actually emit events.

utils/analytics.py defines 36 events. 25 of them were never fired anywhere --
including every step between a visitor arriving and paying:

    signup_started      signup_completed      login
    pricing_viewed      checkout_started      checkout_completed

The product converts 0% of ~190 landing visitors. That number is knowable; WHERE
those visitors stop was not, because no step in between emitted anything. The
events existed, named and documented, which is what made it look instrumented.

(Event.DASHBOARD_VIEWED appears once in the codebase outside its definition --
in analytics.py's own docstring example. A grep that does not exclude the module
itself reports it as wired.)

WHERE EACH ONE FIRES, AND WHY THERE
-----------------------------------
signup_completed fires at email verification, not at the signup form: an
unverified account cannot log in, so counting the submit would report
conversions that never became users.

checkout_completed fires after set_user_tier() flips the tier, not when Stripe
returns: a session that verifies but fails to upgrade is not a completed
checkout.

pricing_viewed fires once per session, not per rerun. Streamlit re-executes the
whole script on every widget interaction, and counting those would inflate the
denominator against a checkout count that can only happen once.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_FUNNEL = {
    "SIGNUP_STARTED":     "utils/auth_ui.py",
    "SIGNUP_COMPLETED":   "utils/auth_ui.py",
    "LOGIN":              "utils/auth_ui.py",
    "PRICING_VIEWED":     "pages/29_Upgrade.py",
    "CHECKOUT_STARTED":   "utils/billing.py",
    "CHECKOUT_COMPLETED": "utils/billing.py",
}


def _sources() -> dict[str, str]:
    out = {}
    for path in list(_ROOT.glob("pages/*.py")) + list(_ROOT.glob("utils/*.py")):
        if "retired" in path.parts or path.name == "analytics.py":
            continue
        out[str(path.relative_to(_ROOT))] = path.read_text(encoding="utf-8")
    return out


def test_every_funnel_step_is_fired_somewhere():
    src = _sources()
    blob = "\n".join(src.values())
    missing = [e for e in _FUNNEL if not re.search(rf"\b{e}\b", blob)]
    assert not missing, (
        "these funnel events are defined but never fired, so the step they "
        "measure is invisible: " + ", ".join(sorted(missing))
    )


def test_each_step_fires_in_the_file_that_owns_it():
    """Guards against an event being fired somewhere that does not mean it."""
    src = _sources()
    wrong = []
    for event, expected in _FUNNEL.items():
        if expected not in src or not re.search(rf"\b{event}\b", src[expected]):
            wrong.append(f"{event} not fired in {expected}")
    assert not wrong, "\n  ".join([""] + wrong)


def test_signup_completed_is_not_fired_at_the_signup_form():
    """An unverified account is not a signup."""
    s = (_ROOT / "utils" / "auth_ui.py").read_text(encoding="utf-8")
    i_signup = s.index("SIGNUP_COMPLETED")
    window = s[max(0, i_signup - 400): i_signup]
    assert "verify_email(" in window, (
        "SIGNUP_COMPLETED no longer fires next to verify_email(); if it moved to "
        "the signup form it now counts accounts that were never verified"
    )


def test_checkout_completed_fires_after_the_tier_actually_changes():
    """Compared on the AST, not on text.

    A comment above the CHECKOUT_STARTED call mentions CHECKOUT_COMPLETED by
    name, so a string search finds the prose first and reports the wrong order.
    Fourth time this session that a guard matched its own rationale instead of
    the code it guards.
    """
    tree = ast.parse((_ROOT / "utils" / "billing.py").read_text(encoding="utf-8"))
    tier_lines, event_lines = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fname = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if fname == "set_user_tier" and any(
            isinstance(a, ast.Constant) and a.value == "pro" for a in node.args
        ):
            tier_lines.append(node.lineno)
        if fname == "_track_billing" and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Attribute) and arg.attr == "CHECKOUT_COMPLETED":
                event_lines.append(node.lineno)
    assert tier_lines, "set_user_tier(..., 'pro') call not found"
    assert event_lines, "CHECKOUT_COMPLETED is not fired via _track_billing"
    assert min(tier_lines) < min(event_lines), (
        f"CHECKOUT_COMPLETED fires at line {min(event_lines)}, before "
        f"set_user_tier at {min(tier_lines)}; a session that verifies but fails "
        "to upgrade would be counted as a paid conversion"
    )


def test_pricing_viewed_is_fired_once_per_session():
    s = (_ROOT / "pages" / "29_Upgrade.py").read_text(encoding="utf-8")
    i = s.index("PRICING_VIEWED")
    window = s[max(0, i - 600): i]
    assert "session_state" in window, (
        "PRICING_VIEWED is no longer guarded by session_state, so every "
        "Streamlit rerun re-counts the view and inflates the funnel"
    )


def test_analytics_can_never_break_auth_or_payment():
    """These call sites sit inside login, signup and checkout."""
    for rel in ("utils/auth_ui.py", "utils/billing.py"):
        tree = ast.parse((_ROOT / rel).read_text(encoding="utf-8"))
        helpers = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name in ("_track_funnel", "_track_billing")
        ]
        assert helpers, f"{rel} lost its guarded analytics helper"
        for fn in helpers:
            assert any(isinstance(n, ast.Try) for n in ast.walk(fn)), (
                f"{rel}:{fn.name} no longer swallows analytics failures, so a "
                "broken tracker can fail a login or a payment"
            )


def test_signup_events_carry_what_attribution_needs():
    """The admin panel names these fields; recording user_id alone is not enough.

    Section 5 of the admin dashboard, verbatim:

        "Signup rows do not store visitor_id, session_id, or last_page, and
         signup_completed is declared but never recorded ... Smallest future
         addition: Record one signup_completed event with user_id, visitor_id,
         session_id, and last_page when account creation commits."

    visitor_id is filled by track() itself. session_id and last_page have to be
    passed, and both are already in hand: the Streamlit session id, and the page
    label utils.header._track_page_view() leaves in session_state["_pv_tracked"].
    """
    src = (_ROOT / "utils" / "auth_ui.py").read_text(encoding="utf-8")
    fn = next(
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.FunctionDef) and n.name == "_track_funnel"
    )
    # Everything below is checked on the AST with the docstring dropped. The
    # docstring quotes the admin panel, which names "_pv_tracked" and
    # "session_id" -- so a text search finds the explanation and passes even
    # when the code is deleted. Confirmed: removing the last_page line survived
    # the first version of this assertion.
    stmts = [n for n in fn.body if not (isinstance(n, ast.Expr)
                                        and isinstance(n.value, ast.Constant)
                                        and isinstance(n.value.value, str))]

    track_calls = [
        c for c in ast.walk(fn)
        if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "track"
    ]
    assert track_calls, "_track_funnel no longer calls track()"
    kwargs = {k.arg for c in track_calls for k in c.keywords}
    assert "session_id" in kwargs, (
        "funnel events no longer carry session_id, so a signup cannot be tied "
        "to the session that produced it"
    )
    literals = {
        n.value for st_ in stmts for n in ast.walk(st_)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }
    assert "_pv_tracked" in literals, (
        "last_page is no longer read from session_state['_pv_tracked'], so "
        "'Last page viewed before signup' has nothing to attribute with"
    )
    assert "last_page" in literals, "the last_page property is no longer set"
