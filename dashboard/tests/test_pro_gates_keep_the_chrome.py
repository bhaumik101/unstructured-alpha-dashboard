"""A Pro gate must render inside the app, not replace it.

Found by pointing the axe harness at all 32 routes for the first time. Measured
main-content length for an anonymous visitor:

    /options-flow       334 chars
    /factor-exposure    356 chars
    /decision-queue    1715 chars
    /thesis-journal    1721 chars
    /portfolio-suite   1829 chars

Chrome alone is ~1,200 chars (nav + proxy links + ticker tape). The first two
are BELOW that: they were calling require_pro() before render_header(), so the
upgrade wall replaced the entire page. No nav, no header, no account widget --
a visitor arriving from a Pro CTA lands somewhere whose only exits are the
sign-in form and the back button.

The other four call render_header() first and gate after, which is what the
majority of the product does and what keeps the visitor inside it.

utils/billing.require_pro()'s own docstring used to prescribe the broken order
("call this at the TOP ... before rendering any content"). Chrome is not
content; the docstring was updated with the pages.
"""

from __future__ import annotations

import re
from pathlib import Path

_PAGES = Path(__file__).resolve().parent.parent / "pages"


def _gated_pages() -> list[Path]:
    return [
        p for p in sorted(_PAGES.glob("*.py"))
        if re.search(r"^\s*require_pro\(", p.read_text(encoding="utf-8"), re.M)
    ]


def test_the_gate_never_runs_before_the_header():
    """Otherwise the upgrade wall IS the page."""
    bad = []
    for path in _gated_pages():
        src = path.read_text(encoding="utf-8")
        code = "\n".join(line.split("#")[0] for line in src.splitlines())
        gate = re.search(r"^\s*require_pro\(", code, re.M)
        head = re.search(r"^\s*(?:_\w+\s*=\s*)?render_header\(", code, re.M)
        if not gate or not head:
            continue
        if gate.start() < head.start():
            bad.append(
                f"{path.name}: require_pro at line "
                f"{code[:gate.start()].count(chr(10)) + 1}, "
                f"render_header at line {code[:head.start()].count(chr(10)) + 1}"
            )
    assert not bad, (
        "these gate before rendering the app chrome, so an anonymous visitor "
        "gets an upgrade wall with no navigation:\n  " + "\n  ".join(bad)
    )


def test_every_gated_page_actually_renders_chrome():
    """A gated page that never calls render_header is the same dead end."""
    missing = [
        p.name for p in _gated_pages()
        if not re.search(r"^\s*(?:_\w+\s*=\s*)?render_header\(",
                         p.read_text(encoding="utf-8"), re.M)
    ]
    assert not missing, (
        "these are Pro-gated but never render the header:\n  " + "\n  ".join(missing)
    )


def test_the_helper_documents_the_order_it_needs():
    """The docstring previously prescribed the behaviour that caused this."""
    src = (_PAGES.parent / "utils" / "billing.py").read_text(encoding="utf-8")
    doc = src[src.index("def require_pro"): src.index("def require_pro") + 1400]
    assert "before rendering any content" not in doc, (
        "require_pro's docstring still tells callers to gate before any content, "
        "which is what put the upgrade wall in front of the navigation"
    )
