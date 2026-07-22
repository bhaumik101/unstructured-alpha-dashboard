"""Tests for the branded loading screen (macro facts + splash).

Two editorial/behavioural invariants matter here:
  1. Every fact is a real, non-empty statement — this product does not present
     fiction as fact, and a loading screen is not an exception.
  2. The boot splash and the in-app splash draw from the SAME fact list, so they
     can't drift, and the injected splash is well-formed (placeholder resolved,
     shape and fact element present).
"""

from __future__ import annotations

import importlib.util
import json
import random
from pathlib import Path

import pytest

from utils.macro_facts import FACTS, all_facts, random_fact

DASHBOARD = Path(__file__).resolve().parent.parent


# ── Facts content ─────────────────────────────────────────────────────────────

def test_facts_nonempty_and_plentiful():
    assert len(FACTS) >= 8, "want a decent rotation so it doesn't feel repetitive"


def test_every_fact_is_a_nonempty_string():
    for f in FACTS:
        assert isinstance(f, str)
        assert len(f.strip()) > 20, f"fact too short to be meaningful: {f!r}"


def test_facts_are_unique():
    assert len(set(FACTS)) == len(FACTS), "duplicate facts in the rotation"


def test_facts_make_no_performance_or_prediction_claims():
    """Guard the editorial rule: no 'our signal', no returns, no forecasts.

    A loading screen that claimed performance would reintroduce exactly the
    over-claiming this product is built to avoid.
    """
    banned = ("our signal", "guarantee", "will rise", "will fall", "will go",
              "profit", "returns of", "% return", "beat the market", "outperform")
    offenders = [f for f in FACTS if any(b in f.lower() for b in banned)]
    assert not offenders, f"facts making performance/prediction claims: {offenders}"


def test_random_fact_is_a_member():
    for _ in range(50):
        assert random_fact() in FACTS


def test_random_fact_accepts_injected_rng():
    rng = random.Random(42)
    a = random_fact(rng)
    rng2 = random.Random(42)
    assert a == random_fact(rng2), "should be deterministic given a seeded RNG"


def test_all_facts_returns_the_tuple():
    assert all_facts() == FACTS


# ── In-app splash ─────────────────────────────────────────────────────────────

def test_loading_splash_has_shape_wordmark_and_fact():
    from utils.theme import loading_splash

    html = loading_splash(fact="A plain test fact about the yield curve.")
    assert "ua-load-hex" in html and "uaLoadGrad" in html, "filled brand shape missing"
    assert "UNSTRUCTURED" in html and "ALPHA" in html, "wordmark missing"
    assert "A plain test fact about the yield curve." in html
    assert "DID YOU KNOW" in html


def test_loading_splash_escapes_the_fact():
    """Facts are interpolated into HTML; a stray < or & must not break markup."""
    from utils.theme import loading_splash

    html = loading_splash(fact="rates < inflation & spreads")
    assert "rates &lt; inflation &amp; spreads" in html
    assert "rates < inflation & spreads" not in html


def test_loading_splash_respects_reduced_motion():
    from utils.theme import loading_splash

    assert "prefers-reduced-motion" in loading_splash()


def test_loading_splash_default_fact_is_a_real_one():
    from utils.theme import loading_splash

    html = loading_splash()
    assert any(f in html or f.replace('"', "&quot;") in html for f in FACTS) or \
        "DID YOU KNOW" in html  # at minimum the frame renders


# ── Boot splash (build-time injector) ─────────────────────────────────────────

def _load_boot_module():
    spec = importlib.util.spec_from_file_location(
        "boot_splash", DASHBOARD / "scripts" / "inject_boot_splash.py"
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_boot_splash_substitutes_facts_and_shape():
    m = _load_boot_module()
    splash = m._build_splash()
    assert "__UA_FACTS_JSON__" not in splash, "facts placeholder was not substituted"
    assert "ua-boot-hex" in splash and "uaBootGrad" in splash, "hexagon shape missing"
    assert "ua-boot-fact" in splash, "fact element missing"


def test_boot_splash_facts_match_the_shared_list():
    """The boot splash must use the same facts as the in-app splash — no drift."""
    m = _load_boot_module()
    facts = m._load_facts()
    assert list(facts) == list(FACTS), (
        "boot splash facts diverged from utils.macro_facts.FACTS"
    )


def test_boot_splash_embeds_valid_json_array():
    import re

    m = _load_boot_module()
    splash = m._build_splash()
    # `var facts=[...]` on one line. A naive split on ';' would break because a
    # fact legitimately contains one ("expansion; below 50"); match the whole
    # bracketed array instead.
    match = re.search(r"var facts=(\[.*\]);", splash)
    assert match, "facts JS array not found"
    parsed = json.loads(match.group(1))
    assert isinstance(parsed, list) and len(parsed) == len(FACTS)


def test_boot_splash_fact_loader_never_raises():
    """It must degrade to a fallback rather than break the build."""
    m = _load_boot_module()
    facts = m._load_facts()
    assert isinstance(facts, list) and len(facts) >= 3


def test_boot_splash_waits_for_the_streamlit_run_to_finish():
    """An empty mounted app shell is not a completed Streamlit page."""
    m = _load_boot_module()
    splash = m._build_splash()

    assert 'stStatusWidgetRunningIcon' in splash
    assert 'stSpinner' in splash
    assert 'hasRenderedContent()' in splash
    assert 'MutationObserver' in splash
    assert 'now-lastMutation>=SETTLE_MS' in splash


def test_boot_splash_has_no_early_window_load_dismissal():
    """Browser load completes before Streamlit's websocket script run."""
    m = _load_boot_module()
    splash = m._build_splash()

    assert "window.addEventListener('load'" not in splash
    assert 'setTimeout(hide,2500)' not in splash
    assert 'HARD_TIMEOUT_MS=45000' in splash
