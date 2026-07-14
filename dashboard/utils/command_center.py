# utils/command_center.py
# Unstructured Alpha — Personal Macro Command Center (Phase 2, second audit)
#
# The signed-in home should answer, in strict priority order, and with ONE
# dominant insight rather than ten equal cards:
#   1. What requires my attention?      (meaningful change around a holding)
#   2. What is my portfolio exposed to?  (largest shared macro factor)
#   3. What changed in the environment?  (only material moves)
#   4. What should I explore?            (contextual, intent-named links)
#
# This module does NOT recompute anything. It ASSEMBLES already-built engine
# outputs — utils.portfolio_xray.build_portfolio_xray (exposure) and
# utils.what_changed.build_what_changed (attention items) — into a single,
# hierarchy-ranked command-center payload. That keeps it a pure function with no
# Streamlit/DB/network, unit-testable against ground truth; the page computes the
# heavy inputs and passes them in.

from __future__ import annotations

from typing import Optional


def build_command_center(
    xray: Optional[dict] = None,
    what_changed: Optional[dict] = None,
) -> dict:
    """
    Assemble the command-center payload from a Portfolio X-Ray payload and a
    What Changed payload.

    Returns:
        {
          "state": "empty" | "no_holdings" | "ready",
          "dominant": {kind, ...} | None,   # the ONE most important thing
          "secondary": [ {kind, ...}, ... ],# 2-3 supporting insights
          "explore": [ {label, action, ...} ],  # contextual, intent-named
          "n_holdings": int,
        }
    Priority for the DOMINANT insight: a holding whose macro backdrop MATERIALLY
    changed (attention) outranks a standing exposure concentration.
    """
    xray = xray or {}
    wc = what_changed or {}
    n = int(xray.get("n_holdings") or 0)

    if not xray or xray.get("empty") or n == 0:
        return {"state": "no_holdings", "dominant": None, "secondary": [],
                "explore": [], "n_holdings": 0}

    # ── Attention items: meaningful changes that actually hit the user's book ──
    attention = []
    for c in (wc.get("changes") or []):
        hits = c.get("watchlist_hits") or []
        if not hits:
            continue
        attention.append({
            "kind": "attention",
            "ticker": hits[0],
            "all_tickers": hits,
            "headline": c.get("headline", ""),
            "factor": c.get("category_name") or c.get("name"),
            "from_score": c.get("from_score"),
            "to_score": c.get("to_score"),
            "delta": c.get("delta"),
            "direction": c.get("direction"),
            "why": c.get("why", ""),
        })
    # biggest move first
    attention.sort(key=lambda a: abs(a.get("delta") or 0), reverse=True)

    # ── Exposure: the largest shared macro factor across the book ─────────────
    risks = xray.get("risks") or []
    top_exposure = None
    if risks:
        r = risks[0]
        top_exposure = {
            "kind": "exposure",
            "factor": r.get("name"),
            "pct_holdings": r.get("pct_holdings"),
            "n_exposed": r.get("n_exposed"),
            "tickers": r.get("exposed_tickers") or [],
            "avg_direction": r.get("avg_direction"),
        }

    most_vuln = xray.get("most_vulnerable") or {}

    # ── Rank: dominant = biggest attention item, else the top exposure ────────
    dominant = attention[0] if attention else top_exposure
    secondary = []
    used_ids = {id(dominant)} if dominant else set()
    for item in (attention[1:3] + ([top_exposure] if (top_exposure and dominant is not top_exposure) else [])):
        if item and id(item) not in used_ids:
            secondary.append(item)
            used_ids.add(id(item))
    # a "most vulnerable holding" card if not already the story
    if most_vuln.get("ticker") and (not dominant or dominant.get("ticker") != most_vuln["ticker"]):
        secondary.append({
            "kind": "vulnerable",
            "ticker": most_vuln["ticker"],
            "score": most_vuln.get("score"),
            "driver": most_vuln.get("driver"),
        })
    secondary = secondary[:3]

    # ── Explore: contextual, intent-named actions (not "View Dashboard") ──────
    explore = []
    if dominant and dominant.get("kind") == "attention":
        explore.append({"label": f"Why did {dominant['ticker']} change?",
                        "action": "ticker", "ticker": dominant["ticker"]})
    if top_exposure:
        explore.append({"label": f"See my shared {top_exposure['factor']} exposure",
                        "action": "portfolio"})
    explore.append({"label": "Review portfolio concentration", "action": "portfolio"})
    # de-dupe by label, cap 3
    seen, deduped = set(), []
    for e in explore:
        if e["label"] not in seen:
            seen.add(e["label"]); deduped.append(e)
    explore = deduped[:3]

    return {
        "state": "ready",
        "dominant": dominant,
        "secondary": secondary,
        "explore": explore,
        "n_holdings": n,
        "n_attention": len(attention),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Presentation — strong hierarchy: one big insight, small supporting ones.
# ─────────────────────────────────────────────────────────────────────────────

def _delta_str(d) -> str:
    if d is None:
        return ""
    di = int(round(d))
    return f"+{di}" if di >= 0 else f"{di}"


def _dominant_html(item: dict) -> str:
    if not item:
        return ""
    if item["kind"] == "attention":
        accent = "#00C853" if item.get("direction") == "up" else "#FF4444"
        move = ""
        if item.get("from_score") is not None and item.get("to_score") is not None:
            move = (f'<span style="color:#C3CBE0;font-variant-numeric:tabular-nums;">'
                    f'{item["from_score"]:g} &rarr; {item["to_score"]:g}</span> '
                    f'<span style="color:{accent};font-weight:700;">({_delta_str(item.get("delta"))})</span>')
        return (
            f'<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.08em;'
            f'color:#8892AA;font-weight:700;">Needs your attention</div>'
            f'<div style="font-size:1.6rem;font-weight:800;color:#E8EEFF;margin:4px 0 2px;">'
            f'{item["ticker"]} — {item["headline"]}</div>'
            f'<div style="font-size:0.95rem;margin-bottom:6px;">{move}</div>'
            + (f'<div style="font-size:0.82rem;color:#8892AA;">{item["factor"]} is the main driver.</div>'
               if item.get("factor") else "")
        )
    # exposure dominant
    return (
        f'<div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.08em;'
        f'color:#8892AA;font-weight:700;">Your biggest shared exposure</div>'
        f'<div style="font-size:1.6rem;font-weight:800;color:#E8EEFF;margin:4px 0 2px;">'
        f'{item["factor"]}</div>'
        f'<div style="font-size:0.9rem;color:#8892AA;">'
        f'{item.get("pct_holdings", 0):g}% of your holdings move with this factor '
        f'({", ".join((item.get("tickers") or [])[:6])}).</div>'
    )


def render_command_center_html(payload: dict) -> str:
    """Render the command center with strong hierarchy for st.html()."""
    if payload.get("state") == "no_holdings":
        # honest, actionable empty state (Phase 14)
        return (
            '<div style="background:#0F1320;border:1px solid #232942;border-radius:14px;'
            'padding:22px 24px;font-family:Inter,-apple-system,sans-serif;">'
            '<div style="font-size:1.15rem;font-weight:800;color:#E8EEFF;">'
            'Your macro exposure is invisible until you add holdings.</div>'
            '<div style="font-size:0.86rem;color:#8892AA;margin-top:6px;max-width:560px;line-height:1.6;">'
            'Add three stocks you follow and this becomes your command center — the biggest '
            'shared risk across them, the most-supported and most-challenged name, and what '
            'changed recently. Enter tickers in the box below to begin.</div></div>'
        )

    dom = payload.get("dominant")
    secondary = payload.get("secondary") or []
    explore = payload.get("explore") or []

    sec_html = ""
    for s in secondary:
        if s["kind"] == "attention":
            accent = "#00C853" if s.get("direction") == "up" else "#FF4444"
            body = (f'{s["ticker"]} — {s["headline"]} '
                    f'<span style="color:{accent};">({_delta_str(s.get("delta"))})</span>')
        elif s["kind"] == "exposure":
            body = f'Shared {s["factor"]} exposure · {s.get("pct_holdings",0):g}% of holdings'
        else:  # vulnerable
            body = f'Most challenged: <b>{s["ticker"]}</b> · {s.get("score",0):g} ({s.get("driver","")})'
        sec_html += (f'<div style="font-size:0.82rem;color:#C3CBE0;padding:7px 0;'
                     f'border-top:1px solid #1E2436;">{body}</div>')

    explore_html = ""
    if explore:
        chips = "".join(
            f'<span style="display:inline-block;font-size:0.76rem;color:#7C9CFF;font-weight:600;'
            f'background:#141A2E;border:1px solid #2A3350;border-radius:7px;padding:6px 12px;'
            f'margin:4px 6px 0 0;">{e["label"]} &rarr;</span>'
            for e in explore
        )
        explore_html = (
            '<div style="margin-top:16px;">'
            '<div style="font-size:0.66rem;text-transform:uppercase;letter-spacing:0.07em;'
            'color:#8892AA;font-weight:700;margin-bottom:4px;">Explore</div>'
            f'{chips}</div>'
        )

    return (
        '<div style="background:#0F1320;border:1px solid #232942;border-left:3px solid #7C3AED;'
        'border-radius:14px;padding:20px 24px;font-family:Inter,-apple-system,sans-serif;">'
        f'{_dominant_html(dom)}'
        + (f'<div style="margin-top:14px;">{sec_html}</div>' if sec_html else "")
        + explore_html
        + '</div>'
    )
