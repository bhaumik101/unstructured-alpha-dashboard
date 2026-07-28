"""Edge cases for the decision cockpit that the happy-path unit test misses.

test_decision_cockpit_unit.py covers a healthy two-holding portfolio. These
cover the shapes a real account actually passes through -- a brand-new user
with one holding, and holdings with no score yet -- where max()/min() over the
same list quietly produce a contradiction.
"""

from __future__ import annotations

from datetime import date

from utils.decision_cockpit import build_decision_cockpit

TODAY = date(2026, 7, 28)


def _build(priorities, *, n_total=None, evidence=None):
    brief = {"priorities": priorities, "n_evidence": len(priorities)}
    if n_total is not None:
        brief["n_total"] = n_total
    return build_decision_cockpit(
        evidence if evidence is not None else [],
        priority_brief=brief,
        today=TODAY,
    )


def test_single_holding_is_not_both_strongest_and_challenged():
    """A new user with one holding must not see it billed as simultaneously
    the strongest and the most challenged name -- a contrast needs two sides."""
    out = _build([{"ticker": "AAPL", "personal_score": 72}])
    portfolio = out["portfolio"]

    assert portfolio["strongest"]["ticker"] == "AAPL"
    assert portfolio["challenged"] is None


def test_two_scored_holdings_still_contrast():
    """The normal case must keep working: distinct strongest vs challenged."""
    out = _build([
        {"ticker": "AAPL", "personal_score": 80},
        {"ticker": "MSFT", "personal_score": 40},
    ])
    portfolio = out["portfolio"]

    assert portfolio["strongest"]["ticker"] == "AAPL"
    assert portfolio["challenged"]["ticker"] == "MSFT"


def test_unscored_holdings_are_never_ranked():
    """A holding with no personal_score has no evidence behind it, so it must
    not surface as either extreme. Defaulting to 0/100 ranked it as both."""
    out = _build([
        {"ticker": "NOSCORE"},                       # no personal_score
        {"ticker": "MSFT", "personal_score": 50},
    ])
    portfolio = out["portfolio"]

    # Only one row is scored, so there is no contrast to draw.
    assert portfolio["strongest"]["ticker"] == "MSFT"
    assert portfolio["challenged"] is None


def test_explicit_zero_n_total_is_not_replaced_by_evidence_count():
    """`n_total or len(evidence)` treats a genuine 0 as missing and reports
    holdings the brief explicitly says are not there."""
    out = _build(
        [],
        n_total=0,
        evidence=[{"ticker": "X", "weight_pct": 1},
                  {"ticker": "Y", "weight_pct": 1},
                  {"ticker": "Z", "weight_pct": 1}],
    )

    assert out["portfolio"]["n_total"] == 0


def test_missing_n_total_still_falls_back_to_evidence_count():
    """Absent (rather than zero) stays a fallback, so existing callers that
    never set n_total keep their behaviour."""
    out = _build([], evidence=[{"ticker": "X", "weight_pct": 1},
                               {"ticker": "Y", "weight_pct": 1}])

    assert out["portfolio"]["n_total"] == 2
