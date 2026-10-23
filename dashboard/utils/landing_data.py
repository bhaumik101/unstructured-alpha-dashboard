# utils/landing_data.py
# Unstructured Alpha — the small live feed behind the landing page's demo
#
# The landing page (Next.js, on Vercel) lets a visitor pick a core force and
# a size of move and see real stocks that rose and fell most in weeks like
# it. It needs only a few rows per force, not the library, so this builds a
# compact JSON document the page fetches through www (/landing.json).
#
# RULES
#   * Only readings that held up (Clear or Tentative) are listed, largest
#     first on each side; how many stocks showed no link is carried too, so
#     the page can say so.
#   * The data date travels with the rows; an empty library gives an empty
#     list of forces and the page hides the demo rather than invent one.

from __future__ import annotations

from typing import Iterable

from utils import exposure as ex
from utils.explore_page import _unit
from utils.force_pages import ALL_FORCES, force_stats

PER_SIDE = 6


def landing_data(stocks: Iterable[dict]) -> dict:
    stocks = list(stocks)
    forces, newest = [], ""
    for f in ex.FACTORS:
        st = force_stats(f.key, stocks)
        if not st["measured"]:
            continue
        newest = max(newest, st["as_of"])

        def rows(side):
            return [[r["ticker"], r.get("name") or "", round(float(r["impact"]), 4), r["evidence"]]
                    for r in side[:PER_SIDE]]
        forces.append({"key": f.key, "label": f.label, "lower": ex.lower_label(f.label), "phrase": f.shock_phrase,
                       "step": abs(f.shock), "unit": _unit(f), "measured": st["measured"],
                       "none": st["none"], "held_up": len(st["up"]), "held_down": len(st["down"]),
                       "up": rows(st["up"]), "down": rows(st["down"])})
    # How many forces (of every group) have at least one reading: the landing's
    # stats strip states it from here, never as a number written into copy.
    measured = sum(1 for f in ALL_FORCES if any(f.key in (s.get("exposures") or {}) for s in stocks))
    return {"as_of": newest, "stocks": len(stocks), "forces_measured": measured, "forces": forces}
