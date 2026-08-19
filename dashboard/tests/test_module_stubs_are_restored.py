"""A test that stubs a shared module must put the real one back.

pytest-xdist reuses one interpreter per worker, so a module-scope write to
sys.modules is not scoped to the file that made it -- it replaces that module
for every test collected afterwards in the same worker. Two files did this and
never restored:

    test_foundation_unit.py        utils.config  (47 signals, 193 tickers)
    test_score_explainer_unit.py   utils.config  (6 signals)
                                   utils.taxonomy
    test_portfolio_xray_unit.py    utils.taxonomy

Measured before the fix, with a probe run immediately after each file:

    after the 47-signal stub   utils.config.__file__ is None  -- the STUB,
                               reporting fabricated SIGNALS and TICKERS, and
                               passing only because it happened to hold 47
    after the 6-signal stub    ImportError from utils.product_metrics

The damage is silent. Nothing raises; later tests simply measure a fiction. It
surfaced as seo/main.py failing to collect with "cannot import name
'category_display' from 'utils.taxonomy' (unknown location)" -- a message that
reads like a path problem and is not one -- and as test_foundation_unit.py
passing inside the full suite while failing on its own.

`from utils import x` binds the module onto the utils PACKAGE too, so restoring
sys.modules alone is not enough; the package attribute has to go back as well.
"""

from __future__ import annotations

import re
from pathlib import Path

_TESTS = Path(__file__).resolve().parent

# Writes performed through the monkeypatch fixture are restored by pytest, so
# only bare module-scope writes are of interest here.
_STUB_WRITE = re.compile(r'^\s*sys\.modules(?:\.setdefault\(|\[)', re.M)
_RESTORE = re.compile(
    r'sys\.modules\.pop\(|sys\.modules\[[^\]]+\]\s*=\s*_real', re.M
)


def _module_scope_stub_files() -> list[Path]:
    out = []
    for path in sorted(_TESTS.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        src = path.read_text(encoding="utf-8")
        code = "\n".join(line.split("#")[0] for line in src.splitlines())
        for m in _STUB_WRITE.finditer(code):
            line = code[m.start(): code.find("\n", m.start())]
            if "monkeypatch" in line:
                continue
            out.append(path)
            break
    return out


def test_every_module_scope_stub_is_restored():
    missing = []
    for path in _module_scope_stub_files():
        code = "\n".join(
            line.split("#")[0]
            for line in path.read_text(encoding="utf-8").splitlines()
        )
        if not _RESTORE.search(code):
            missing.append(path.name)
    assert not missing, (
        "these files replace a module in sys.modules at import time and never "
        "put the real one back, so every test collected after them in the same "
        "xdist worker gets the stub:\n  " + "\n  ".join(missing)
        + "\n\nsave the original, stub, import your target, then restore both "
          "sys.modules and the attribute on the parent package."
    )


def test_the_restore_also_puts_back_the_package_attribute():
    """`from utils import config` binds onto the utils package object too."""
    incomplete = []
    for path in _module_scope_stub_files():
        code = "\n".join(
            line.split("#")[0]
            for line in path.read_text(encoding="utf-8").splitlines()
        )
        if not _RESTORE.search(code):
            continue  # already reported above
        if "_utils_pkg" not in code:
            incomplete.append(path.name)
    assert not incomplete, (
        "these restore sys.modules but not the attribute on the utils package, "
        "so `from utils import <name>` still resolves to the stub:\n  "
        + "\n  ".join(incomplete)
    )
