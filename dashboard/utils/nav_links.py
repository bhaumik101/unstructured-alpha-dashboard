"""Map each nav URL to the page file that serves it.

WHY THIS EXISTS. The custom top nav is built from raw <a href> anchors, so every
click is a FULL browser navigation: the whole Streamlit frontend re-bootstraps
(135 JS files re-parsed, new websocket, fresh Python session) on each page
change. st.page_link does not have that problem -- Streamlit renders it as an
anchor with a React onClick handler that intercepts the click and navigates
client-side (verified against a live Streamlit instance).

So the nav keeps its markup and design, and a small script proxies each click to
a hidden st.page_link for the same destination.

The mapping is PARSED from app.py's st.Page(...) registry rather than
hand-written, because a hand-written copy silently rots the moment a page is
added, renamed or re-pathed -- and the failure mode of a stale entry is a nav
item that no longer navigates.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

_APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def _default_url_path(script: str) -> str:
    """Streamlit derives a slug from the filename when url_path is omitted."""
    stem = Path(script).stem
    # Leading numeric ordering prefix ("2_Today_Digest" -> "Today_Digest").
    if "_" in stem and stem.split("_", 1)[0].isdigit():
        stem = stem.split("_", 1)[1]
    return stem.replace("_", "-").lower()


@lru_cache(maxsize=1)
def page_targets() -> tuple[tuple[str, str], ...]:
    """((url_path, script_path), ...) for every registered page.

    The home page is registered with default=True and no url_path; Streamlit
    serves it at "/", so it is emitted with an empty url_path.
    """
    try:
        tree = ast.parse(_APP_PY.read_text(encoding="utf-8"))
    except Exception:
        return ()

    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)
        if name != "Page" or not node.args:
            continue
        first = node.args[0]
        if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
            continue
        script = first.value

        url_path = None
        is_default = False
        for kw in node.keywords:
            if kw.arg == "url_path" and isinstance(kw.value, ast.Constant):
                url_path = kw.value.value
            elif kw.arg == "default" and isinstance(kw.value, ast.Constant):
                is_default = bool(kw.value.value)

        if is_default and url_path is None:
            url_path = ""
        elif url_path is None:
            url_path = _default_url_path(script)

        out.append((str(url_path), script))

    return tuple(out)


def targets_for_hrefs(hrefs: set[str]) -> tuple[tuple[str, str], ...]:
    """Only the pages the visible nav can actually reach.

    Rendering a hidden link for all 33 pages when the nav exposes 22 is wasted
    render work on every page.
    """
    wanted = {h.strip("/") for h in hrefs}
    return tuple((u, s) for u, s in page_targets() if u in wanted)
