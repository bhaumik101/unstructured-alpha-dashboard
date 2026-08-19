"""The subscriber brief email must deliver the whole note and link only to real hosts.

This cron ran every Sunday at 16:00 UTC sending an email that was broken in two
compounding ways, neither of which anything checked:

  1. It sent `paras[:3]` and put the remainder "behind a link" pointing at
     https://stocks.unstructuredalpha.com/brief. That host has never had a DNS
     record. Not a 404 -- it does not resolve.

  2. Even at a host that does resolve, /brief does not exist. The route lives in
     seo/app.py, which is NOT deployed; render.yaml starts seo.main:app, and
     dashboard/seo/main.py has no /brief route. The dashboard's own brief page
     was retired (pages/retired/18_Weekly_Brief.py).

So the withheld remainder was unreachable by any route. The generator asks for a
550-700 word note whose LAST paragraph starts with "Bottom Line:" -- the
actionable conclusion -- which means a [:3] cut dropped the conclusion from every
brief ever sent.

The fix was to make the email self-contained. These tests hold that: the whole
note ships, and no link may point somewhere the product does not actually serve.
"""

from __future__ import annotations

import re

import cron.send_brief_subscribers as brief

# A six-paragraph note shaped like the generator's contract: headline, body,
# closing "Bottom Line:". Six matters -- it must exceed the old cut of three.
_PARAS = [
    "Paragraph one establishes the regime and composite score.",
    "Paragraph two covers the bullish signals driving the read.",
    "Paragraph three covers the bearish offsets.",
    "Paragraph four discusses credit spreads and liquidity.",
    "Paragraph five discusses labour and consumer data.",
    "Bottom Line: risk-on bias holds; a credit spread breakout would flip it.",
]
_BRIEF = {
    "id": 1,
    "headline": "Labor Market Resilience Offsets Credit Spread Widening",
    "body": "\n\n".join(_PARAS),
    "note_date": "2026-08-16",
    "regime": "RISK-ON",
    "bull_count": 31,
    "bear_count": 16,
}

# Hosts this product actually serves. stocks.* is deliberately absent.
_ALLOWED_HOSTS = {
    "unstructuredalpha.com",
    "www.unstructuredalpha.com",
    "seo.unstructuredalpha.com",
}


def _html() -> str:
    html, _ = brief._build_brief_html(_BRIEF, first_name="Sam")
    return html


def test_every_paragraph_of_the_note_is_in_the_email():
    """No truncation. The reader gets what the generator wrote."""
    html = _html()
    missing = [p for p in _PARAS if p not in html]
    assert not missing, (
        "these paragraphs were written but never sent:\n  "
        + "\n  ".join(missing)
    )


def test_the_bottom_line_paragraph_survives():
    """The conclusion is the payload, and it is always last.

    Called out separately from the paragraph sweep above because any
    'send the first N' change reintroduces exactly this bug, and this is the
    paragraph whose loss actually costs the reader something.
    """
    html = _html()
    assert _PARAS[-1] in html, (
        "the closing 'Bottom Line:' paragraph is missing -- the reader gets the "
        "analysis without the conclusion, which is the half that tells them what "
        "to do"
    )


def test_no_link_points_at_a_host_the_product_does_not_serve():
    """Catches the original bug directly, and any future variant of it."""
    hosts = {
        m.group(1).lower()
        for m in re.finditer(r'href="https?://([^/"]+)', _html())
    }
    unknown = sorted(hosts - _ALLOWED_HOSTS)
    assert not unknown, (
        "the brief email links to host(s) this product does not serve: "
        + ", ".join(unknown)
        + "\nstocks.unstructuredalpha.com in particular has no DNS record at all."
    )


def test_any_brief_link_points_at_the_host_that_serves_it():
    """/brief exists again -- but only on the SEO service.

    This test used to assert that NO link mentioned /brief, because the route
    lived solely in seo/app.py, an undeployed copy of the service. That premise
    stopped being true when the route was added to seo/main.py, so the assertion
    changed rather than being deleted: the concern was never "never say /brief",
    it was "never link somewhere nothing serves".

    The host has to be the one the SEO pages canonicalise to. Pointing the email
    at a second host that also serves the page splits the ranking signal for the
    same content, which is what the www consolidation existed to stop.
    """
    html = _html()
    hosts = {
        m.group(1).lower()
        for m in re.finditer(r'href="https?://([^/"]+)/brief', html)
    }
    assert hosts, "the brief email no longer offers a browser copy at all"
    unexpected = sorted(hosts - {"www.unstructuredalpha.com"})
    assert not unexpected, (
        "brief links must use the canonical SEO host; found: " + ", ".join(unexpected)
    )


def test_the_dashboard_cta_still_works():
    """The one link that was always fine must stay.

    Removing dead links should not strip the email of its actual conversion path.
    """
    assert f'href="{brief._APP_BASE_URL}"' in _html(), (
        "the Open Dashboard CTA is gone; the email now has no way into the product"
    )
