"""Every link in a transactional email must point at a page that exists.

utils/email.py accumulated 32 dead links across 10 distinct URLs -- roughly
three quarters of the outbound links in the product's transactional mail. They
were all the same mistake: an old-style Streamlit page name pointed at the
MARKETING domain.

    https://unstructuredalpha.com/Watchlist          x9
    https://unstructuredalpha.com/Upgrade            x4
    https://unstructuredalpha.com/Today%27s_Brief    x4
    ...

Two things had to be true at once for this to survive:

  - unstructuredalpha.com is Vercel (the marketing site). The Streamlit app is
    app.unstructuredalpha.com. Every one of these 404'd, verified live.
  - The app sets url_path explicitly on every st.Page, so the real routes are
    lowercase-hyphenated (/my-watchlist) and never looked like /Watchlist.

Nothing checked, so a welcome email, an upgrade email, a password-reset email
and a paid-customer Pro welcome all shipped with links to nowhere.

WHY THE PLAIN-STRING TEST BELOW EXISTS
--------------------------------------
Fixing this by substituting {_APP_URL} silently created a WORSE bug: five of
the templates are plain triple-quoted strings, not f-strings, so {_APP_URL}
would have rendered literally in the reader's inbox. Caught by AST, not by eye.
That check is kept because the next person to add a link is one keystroke from
the same trap.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_EMAIL = _ROOT / "utils" / "email.py"
_SRC = _EMAIL.read_text(encoding="utf-8")

_APP_HOST = "app.unstructuredalpha.com"


def _registered_routes() -> set[str]:
    """The app's real route table, read from st.Page(url_path=...) in app.py."""
    app = (_ROOT / "app.py").read_text(encoding="utf-8")
    routes = set(re.findall(r'url_path="([^"]+)"', app))
    routes.add("")  # the default page is served at /
    return routes


# Links to features that were RETIRED (they live only in pages/retired/, which
# is not shipped). These are not URL bugs -- the destination genuinely no longer
# exists, so the surrounding marketing copy has to be rewritten or removed, which
# is a product decision rather than a find-and-replace. Tracked here so they
# cannot be forgotten and so no NEW ones can be added quietly.
_RETIRED_FEATURE_LINKS = {
    "/Best_Ideas",           # retired 34_Best_Ideas.py  (nearest live page: /stock-recommender)
    "/Signal_Backtester",    # retired 19_Signal_Backtester.py (nearest live: /signal-strategy)
    "/Short_Squeeze_Radar",  # retired 16_Short_Squeeze_Radar.py (no live equivalent)
}


def test_app_links_point_at_registered_routes():
    routes = _registered_routes()
    bad = []
    for path in re.findall(rf'href="(?:\{{_APP_URL\}}|https://{re.escape(_APP_HOST)})(/[^"?]*)', _SRC):
        slug = path.strip("/").split("?")[0]
        if slug not in routes:
            bad.append(path)
    assert not bad, (
        "these email links point at paths the app does not route:\n  "
        + "\n  ".join(sorted(set(bad)))
        + "\n\nreal routes come from st.Page(url_path=...) in app.py"
    )


def test_no_email_link_sends_a_reader_to_the_marketing_site_for_an_app_page():
    """The marketing site has no app pages. Anything but / is a 404."""
    found = {
        p for p in re.findall(
            r'href="https://(?:www\.)?unstructuredalpha\.com(/[^"]*)"', _SRC
        )
        if p not in ("", "/")
    }
    unexpected = sorted(found - _RETIRED_FEATURE_LINKS)
    assert not unexpected, (
        "these link to app pages on the MARKETING domain, which 404s:\n  "
        + "\n  ".join(unexpected)
        + f"\n\nuse {{_APP_URL}}/<url_path> instead"
    )


def test_the_retired_feature_list_is_honest():
    """Nothing may sit in the retired list once it stops appearing in the file."""
    present = set(
        re.findall(r'href="https://(?:www\.)?unstructuredalpha\.com(/[^"]*)"', _SRC)
    )
    stale = sorted(_RETIRED_FEATURE_LINKS - present)
    assert not stale, (
        "remove these from _RETIRED_FEATURE_LINKS -- they are no longer linked:\n  "
        + "\n  ".join(stale)
    )


def test_app_url_is_never_interpolated_into_a_plain_string():
    """{_APP_URL} inside a non-f-string ships the braces to the reader.

    Five templates in this file are plain triple-quoted strings. Adding a link
    to one of them without the f prefix produces an email containing the literal
    text "{_APP_URL}/my-watchlist".
    """
    tree = ast.parse(_SRC)
    bad = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "{_APP_URL}" in node.value
    ]
    assert not bad, (
        "these lines contain {_APP_URL} inside a plain (non-f) string, so the "
        "braces would render literally in the email: " + ", ".join(map(str, bad))
        + "\nadd the f prefix to the template literal"
    )
