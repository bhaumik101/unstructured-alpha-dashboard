"""The browser remembers the last portfolio, and the rules that keeps honest.

An anonymous-first product has a retention hole: a visitor measures a
portfolio, closes the tab, comes back a week later to an empty form, and types
everything again. Most do not. The report is already fully described by its ?h=
parameter, so the whole mechanic is to remember that parameter and reopen it.

It runs in scripts/inject_boot_splash.py rather than in Python, because it has
to happen before Streamlit boots and because Streamlit cannot reach
localStorage at all. That makes it unreachable from a unit test, so what is
pinned here is the set of rules the script must contain — each of which was a
way for the feature to become annoying or wrong:

  - an explicit link beats a memory;
  - once per tab, or "Start fresh" bounces straight back;
  - ?fresh=1 actually forgets;
  - the page tells the visitor their holdings are stored in their browser.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.inject_boot_splash import _build_runtime  # noqa: E402
from utils import report_ui as ui  # noqa: E402

RUNTIME = _build_runtime()
BLOCK = RUNTIME[RUNTIME.index("Reopen the portfolio you last measured"):
                RUNTIME.index("Client-side navigation proxy")]


def test_the_memory_runs_in_the_injected_script_not_in_python():
    """st.markdown does not execute scripts and a component runs in a sandboxed
    iframe, so this is the only place it can work. It also has to run before
    Streamlit boots, or the visitor watches an empty form appear first."""
    assert "ua-last-portfolio" in RUNTIME
    assert "<script" in RUNTIME
    page = (_ROOT / "pages" / "60_Exposure_Report.py").read_text(encoding="utf-8")
    assert "localStorage" not in page, "Streamlit cannot reach localStorage"


def test_an_explicit_link_always_beats_the_remembered_one():
    """?sample=, ?theme=, a shared ?h= — any query at all is the visitor being
    explicit, and must not be overridden by what they looked at last week."""
    assert "!uaQ.toString()" in BLOCK, "the restore must require an empty query string"
    assert re.search(r"location\.pathname.*?\)\s*===\s*''", BLOCK), (
        "the restore must be limited to the front door"
    )


def test_it_restores_at_most_once_per_tab():
    """Otherwise Start fresh clears the memory, lands on '/', and is
    immediately sent back to the portfolio it just cleared."""
    assert "sessionStorage.setItem('ua-reopened','1')" in BLOCK
    assert "uaDone" in BLOCK and "!uaDone" in BLOCK


def test_start_fresh_really_forgets():
    assert "uaQ.get('fresh')" in BLOCK
    assert "localStorage.removeItem(UAP)" in BLOCK
    # and it must also mark the tab, or the very next load restores again
    fresh = BLOCK[BLOCK.index("uaQ.get('fresh')"):BLOCK.index("var uaH")]
    assert "sessionStorage.setItem('ua-reopened','1')" in fresh


def test_a_restored_visit_is_marked_so_the_page_can_say_so():
    assert "reopened=1" in BLOCK
    assert "reopened" in (_ROOT / "pages" / "60_Exposure_Report.py").read_text(encoding="utf-8")


def test_nothing_is_sent_anywhere_and_the_page_says_so():
    """It is the visitor's own holdings. Storing them silently would be the
    kind of thing this product exists not to do."""
    assert "fetch(" not in BLOCK and "XMLHttpRequest" not in BLOCK
    notice = ui.reopened_html()
    assert "this browser only" in notice
    assert "nothing was sent anywhere" in notice.lower()
    assert "no account was created" in notice
    assert 'href="/?fresh=1"' in notice


def test_every_storage_access_is_guarded():
    """Private mode and blocked site data make localStorage throw on access,
    not return null. An unguarded read would take the whole runtime down with
    it — theme, client-side navigation and the proxy links' accessibility."""
    for call in re.findall(r"(?:local|session)Storage\.\w+\([^)]*\)", BLOCK):
        start = BLOCK.index(call)
        preceding = BLOCK[:start]
        assert preceding.count("try{") > preceding.count("}catch"), (
            f"{call} is outside a try/catch"
        )


def test_the_memory_follows_a_url_that_streamlit_rewrote():
    """The report puts its own ?h= in the address bar through Streamlit, which
    uses history.replaceState — no page load, no event. A one-shot read at boot
    therefore saw the URL the visitor ARRIVED on and never the portfolio they
    went on to build. Measured in a browser: building a portfolio from the
    search box remembered nothing at all."""
    assert "setInterval(uaRemember" in BLOCK, (
        "the remembered portfolio must keep up with in-page URL rewrites"
    )
    assert "uaRemember()" in BLOCK, "it must also run on arrival"
