"""Public copy must not claim what the evidence does not support.

Every predictive configuration tested on this data failed
(docs/NOWCAST_RESULTS.md). The landing page nevertheless advertised a "4–16w
typical signal lead time", regime shifts spotted "before they hit price", a
"MOST POPULAR" plan with no customers, and a Philadelphia Fed series labelled as
ISM. These phrases are banned from the marketing site so they cannot drift back.

Negations are allowed where they are the point ("not a forecast"), so the list
names specific claims rather than every forward-looking word.
"""

from __future__ import annotations

import re
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent
WEB = DASHBOARD / "unstructured-alpha-web" / "app"
APP_SURFACES = [
    DASHBOARD / "pages" / name
    for name in ("60_Exposure_Report.py", "61_What_Changed.py", "62_Alerts.py",
                 "63_Methodology.py", "64_Research.py", "65_Pricing.py")
] + [DASHBOARD / "utils" / "report_ui.py"]
SURFACES = [WEB / "page.tsx", WEB / "layout.tsx", *APP_SURFACES]

BANNED = [
    r"lead[\s-]?time",
    r"before (?:they|it) hits? price",
    r"before the move",
    r"historically precedes",
    r"most popular",
    r"institutional desks",
    r"\bISM\b",
    r"bullish",
    r"bearish",
    r"regime shifts?",
    r"beat the market",
    r"outperform",
    r"guaranteed? (?:returns|alpha|profits)",
    r"\bFINRA\b",
    r"\bCBOE\b",
    r"47 macro signals",
    r"Discord|Slack",
]


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"\{/\*.*?\*/\}", "", text, flags=re.DOTALL)
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("//"))


def test_marketing_surfaces_make_no_predictive_or_unsupported_claims():
    offenders = []
    for path in SURFACES:
        body = _strip_comments(path.read_text(encoding="utf-8"))
        for pattern in BANNED:
            for m in re.finditer(pattern, body, flags=re.IGNORECASE):
                offenders.append(f"{path.name}: {m.group(0)!r}")
    assert not offenders, "unsupported claims on the marketing site:\n" + "\n".join(offenders)


def test_the_landing_page_says_plainly_that_it_is_not_a_forecast():
    page = (WEB / "page.tsx").read_text(encoding="utf-8")
    assert "not a forecast" in page.lower()
    assert "not investment advice" in page.lower()


def test_unbuilt_paid_features_are_labelled_as_in_development():
    """Pricing must not sell what does not exist yet."""
    page = (WEB / "page.tsx").read_text(encoding="utf-8")
    pricing = page[page.index('id="pricing"'):page.index('id="faq"')]
    marker = pricing.index("In development")
    for unbuilt in ("what changed", "alerts", "PDF export"):
        assert unbuilt in pricing[marker:], (
            f"{unbuilt!r} is offered on the pricing page but not marked in development"
        )
