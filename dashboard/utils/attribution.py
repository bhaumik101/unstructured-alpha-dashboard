# utils/attribution.py
# Unstructured Alpha — return attribution: what drove a portfolio's past weeks
#
# "Your portfolio returned −3.2% over the last 26 weeks. The stock market
# accounts for −4.1 points of that, interest rates +0.6, oil −0.3 ... and 0.4
# is not explained by any of them." That is the question an adviser answers
# in every review, and the report's weekly data (report["series"]) answers it.
#
# HOW
# ---
# The report's core model gives each force a weekly sensitivity (and the
# market its beta). Over the chosen window, each force's contribution is
# sensitivity x what that force actually did, week by week, summed. Whatever
# the forces don't account for -- stock-specific news, the model's intercept,
# noise -- is reported as its own line, never hidden.
#
# Returns are SUMMED weekly returns, so the parts add up exactly to the
# total; the compounded return over the window is shown beside it for
# reference. The sensitivities were estimated on data that includes these
# weeks, so this is a description of the past, not a test of anything.

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from utils import exposure as ex

WINDOWS = (4, 13, 26, 52)


def _minus(text: str) -> str:
    """A true minus sign, matching every other figure on the page."""
    return text.replace("-", "−")


def available(report: dict) -> bool:
    s = (report or {}).get("series") or {}
    p = (report or {}).get("portfolio") or {}
    return bool(s.get("weeks")) and p.get("market_beta") is not None and bool(p.get("readings"))


def attribute(report: dict, weeks: int) -> Optional[dict]:
    """Contributions over the last `weeks` weeks, or None if not measurable."""
    if not available(report):
        return None
    s, p = report["series"], report["portfolio"]
    idx = pd.to_datetime(s["weeks"])
    weights = s["weights"]
    port = sum(pd.Series(s["holdings"][t], idx, dtype=float) * w for t, w in weights.items())
    frame = pd.DataFrame({"__p__": port, "__mkt__": pd.Series(s["market"], idx, dtype=float),
                          **{k: pd.Series(v, idx, dtype=float) for k, v in s["core"].items()}}).dropna()
    tail = frame.iloc[-weeks:]
    if len(tail) < min(weeks, 4):
        return None

    by_key = {f.key: f for f in ex.FACTORS}
    lines: List[dict] = [{
        "key": "market", "label": "Stock market", "kind": "market",
        "contribution": float(p["market_beta"] * tail["__mkt__"].sum()), "se": None,
        "what_happened": _minus(f"the S&P 500 returned {tail['__mkt__'].sum():+.1f}% (summed weekly)"),
        "evidence": None,
    }]
    for key, r in p["readings"].items():
        if key not in tail:
            continue
        f = by_key[key]
        per_unit = r["impact"] / f.shock
        move = float(tail[key].sum())
        happened = (f"{move:+.1f}% (summed weekly)" if f.transform == "pct"
                    else f"{move:+.2f} percentage points")
        lines.append({
            "key": key, "label": r["label"], "kind": "force",
            "contribution": float(per_unit * move),
            "se": float(r["se_impact"] / abs(f.shock) * abs(move)),
            "what_happened": _minus(f"{ex.lower_label(r['label'])} moved {happened}"),
            "evidence": r["evidence"],
        })
    total = float(tail["__p__"].sum())
    explained = sum(l["contribution"] for l in lines)
    lines.append({"key": "other", "label": "Not explained by these forces", "kind": "other",
                  "contribution": total - explained, "se": None,
                  "what_happened": "company-specific news, everything else, and noise",
                  "evidence": None})
    compounded = float((np.prod(1 + tail["__p__"].to_numpy() / 100.0) - 1) * 100.0)
    return {
        "weeks": int(len(tail)), "start": str(tail.index[0].date()), "end": str(tail.index[-1].date()),
        "total": total, "compounded": compounded, "lines": lines,
        "explained_share": (explained / total) if abs(total) > 1e-9 else None,
    }
