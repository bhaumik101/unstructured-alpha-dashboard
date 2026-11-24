"""The first-visit walkthrough (utils/tour.py).

  * Every step points at something the page really renders: its selector's
    class or widget key appears in the code that draws it.
  * The two "click it" steps target real buttons, so the visitor's click
    does the real thing (measure the sample, open the editor).
  * The copy describes; it never forecasts or recommends.
  * The last card links only to routes the app registers.
  * It ships in the served page's runtime, and the script parses.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from utils import tour

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "pages" / "60_Exposure_Report.py").read_text(encoding="utf-8")
SOURCES = PAGE + "".join((ROOT / "utils" / f).read_text(encoding="utf-8")
                         for f in ("report_ui.py", "dashboard_ui.py"))


def test_every_step_targets_something_the_page_draws():
    for sid, sel, *_ in tour.STEPS:
        if not sel:
            assert sid == "welcome"
            continue
        key = re.search(r"\.st-key-([a-z_]+)", sel)
        cls = re.search(r"^\.([a-z][a-z0-9-]+)", sel)
        if key:
            assert f'key="{key.group(1)}"' in PAGE or f'key=f"uar_sample_{{key}}"' in PAGE and key.group(1).startswith("uar_sample_"), sid
        else:
            name = cls.group(1)
            assert re.search(r'class=\\?"[^"]*\b' + re.escape(name) + r'\b', SOURCES), (sid, name)


def test_the_click_steps_are_the_real_buttons():
    clicks = {s[0]: s[1] for s in tour.STEPS if s[4] == "click"}
    assert clicks == {"sample": ".st-key-uar_sample_balanced button", "edit": ".st-key-uar_edit button"}
    from utils import report_ui as ui
    assert "balanced" in ui.SAMPLE_KEYS
    assert 'if st.button("Change holdings", key="uar_edit"' in PAGE
    # a wait step follows the sample click, watching for the report
    ids = [s[0] for s in tour.STEPS]
    assert tour.STEPS[ids.index("sample") + 1][4] == "wait"


def test_the_copy_describes_and_never_advises():
    text = " ".join(s[2] + " " + s[3] for s in tour.STEPS).lower()
    for word in ("forecast", "predict", "recommend", "should buy", "beat the market", "profit", "guarantee"):
        assert word not in text, word


def test_the_last_card_links_only_to_real_routes():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    for _label, href in tour.EXPLORE:
        assert f'url_path="{href.strip("/")}"' in app, href


def test_it_ships_in_the_runtime_and_parses():
    sys.path.insert(0, str(ROOT / "scripts"))
    import inject_boot_splash as inj
    rt = inj._build_runtime()
    assert "window.uaTour" in rt and tour.KEY in rt
    js = tour.tour_js()
    for ph in ("__KEY__", "__STEPS__", "__EXPLORE__", "__CSS__"):
        assert ph not in js, ph
    assert json.dumps(tour.TOUR_CSS) in js
    node = shutil.which("node")
    if node:
        r = subprocess.run([node, "-e", "new Function(require('fs').readFileSync(0,'utf8'))"],
                           input=js, capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr


def test_it_starts_only_for_a_newcomer_and_can_always_be_left():
    js = tour.TOUR_JS
    assert "localStorage.getItem('ua-last-portfolio')" in js        # someone who measured before is not new
    assert "!/[?&](h|sample)=/.test(location.search)" in js          # a shared link is not hijacked
    assert "ev.key === 'Escape'" in js and 'data-uat="skip"' in js
    assert "prefers-reduced-motion" in js and "prefers-reduced-motion" in tour.TOUR_CSS
    assert "data-ua-tour-start" in PAGE and "data-ua-tour-start" in js
