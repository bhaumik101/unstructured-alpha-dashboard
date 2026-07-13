# utils/what_changed.py
# Unstructured Alpha — "What Changed" compression engine (Point 4)
#
# WHY THIS MODULE EXISTS: the old daily view listed every signal flip and
# mover as a flat wall of updates. That is information density, not decision
# compression — the user still has to do the work of figuring out which of
# today's moves actually matter and to which of their holdings. This engine
# does that work: it takes the raw day-over-day diff (utils.score_history.
# get_signal_diff) and returns a short, ranked list of the MEANINGFUL changes,
# each mapped to the sectors and — crucially — the user's own watchlist names
# it touches, then states plainly that everything else was noise.
#
# The product it sells is compression:
#     "3 meaningful changes since yesterday. Here's what moved, which of YOUR
#      holdings it hits, and why. The other 44 signals were noise."
#
# DESIGN PRINCIPLES:
#   • Compression over density — cap the list, bucket the rest as noise.
#   • Grounded, not narrated — "why it matters" is each signal's real config
#     description, not invented copy. Score moves are shown as measured
#     "X → Y (+Δ)", never dramatised.
#   • The user's holdings come first — a change that hits a watchlist name
#     outranks a bigger change that doesn't.
#   • Honest empty state — "no meaningful changes, the backdrop held steady"
#     is a valid and useful answer, not a failure to fill space.
#
# Pure functions (no Streamlit, no DB) so the ranking/mapping logic is
# unit-testable against ground truth; render_what_changed_html() is the only
# presentation concern.

from __future__ import annotations

from typing import Optional

from utils.config import SIGNALS, TICKERS, CATEGORIES

# A "mover" must move at least this many score points to count as meaningful.
# Status flips are always meaningful regardless of magnitude (a flip is, by
# definition, a change of state). 8 points is roughly a meaningful shift on the
# 0-100 signal scale without being so sensitive that ordinary daily wiggle
# floods the list — the whole point is to filter noise.
MEANINGFUL_DELTA = 8.0


# ─────────────────────────────────────────────────────────────────────────────
# Config lookups
# ─────────────────────────────────────────────────────────────────────────────

def _signal_name(sig_id: str) -> str:
    return (SIGNALS.get(sig_id) or {}).get("name") or sig_id.replace("_", " ").title()


def _signal_category(sig_id: str) -> str:
    return (SIGNALS.get(sig_id) or {}).get("category", "macro")


def _category_name(cat_id: Optional[str]) -> str:
    if not cat_id:
        return "Macro"
    return (CATEGORIES.get(cat_id) or {}).get("name", cat_id.replace("_", " ").title())


def _signal_why(sig_id: str, limit: int = 160) -> str:
    """Grounded 'why it matters' — the signal's real config description."""
    desc = (SIGNALS.get(sig_id) or {}).get("description", "") or ""
    desc = " ".join(desc.split())
    if len(desc) > limit:
        desc = desc[: limit - 1].rstrip() + "…"
    return desc


# ─────────────────────────────────────────────────────────────────────────────
# Impact mapping — which tickers/sectors a signal touches
# ─────────────────────────────────────────────────────────────────────────────

def affects_ticker(sig_id: str, ticker: str) -> bool:
    """
    A signal affects a ticker if either side of the config declares the link:
    the ticker lists the signal among its drivers, OR the signal lists the
    ticker among its relevant names.
    """
    ticker = (ticker or "").upper().strip()
    tkr = TICKERS.get(ticker) or {}
    if sig_id in (tkr.get("signals") or []):
        return True
    if ticker in (SIGNALS.get(sig_id, {}).get("relevant_tickers") or []):
        return True
    return False


def _affected_universe(sig_id: str) -> set[str]:
    """All tracked tickers a signal touches (union of both config directions)."""
    out = set(SIGNALS.get(sig_id, {}).get("relevant_tickers") or [])
    for tkr, meta in TICKERS.items():
        if sig_id in (meta.get("signals") or []):
            out.add(tkr)
    return out


def affected_sectors(sig_id: str, limit: int = 3) -> list[str]:
    """Sectors most represented among the tickers this signal touches."""
    from collections import Counter
    counts: Counter = Counter()
    for tkr in _affected_universe(sig_id):
        sector = (TICKERS.get(tkr) or {}).get("sector")
        if sector:
            counts[sector] += 1
    return [s for s, _ in counts.most_common(limit)]


def affected_watchlist(sig_id: str, watchlist: Optional[list]) -> list[str]:
    """The subset of the user's watchlist this signal actually touches."""
    if not watchlist:
        return []
    return [t.upper().strip() for t in watchlist if affects_ticker(sig_id, t.upper().strip())]


# ─────────────────────────────────────────────────────────────────────────────
# Framing a single change into plain English
# ─────────────────────────────────────────────────────────────────────────────

def _frame_entry(sig_id: str, name: str, from_score, to_score, delta,
                 kind: str, to_status: Optional[str] = None) -> dict:
    """
    Build a display-ready change record. Direction is read from the SCORE move
    (the signal score already accounts for inverse signals, so 'up' always
    means 'more supportive'). Headlines stay factual: improved / weakened /
    turned supportive / turned challenging.
    """
    up = (delta or 0) > 0
    if kind == "flip":
        if (to_status or "").lower() == "bullish":
            headline = f"{name} turned supportive"
            direction = "up"
        elif (to_status or "").lower() == "bearish":
            headline = f"{name} turned challenging"
            direction = "down"
        else:
            headline = f"{name} shifted to neutral"
            direction = "flat"
    else:
        headline = f"{name} {'improved' if up else 'weakened'}"
        direction = "up" if up else ("down" if (delta or 0) < 0 else "flat")

    return {
        "sig_id": sig_id,
        "name": name,
        "kind": kind,                      # "flip" | "mover"
        "headline": headline,
        "direction": direction,
        "from_score": round(float(from_score), 0) if from_score is not None else None,
        "to_score": round(float(to_score), 0) if to_score is not None else None,
        "delta": round(float(delta), 1) if delta is not None else None,
        "category": _signal_category(sig_id),
        "category_name": _category_name(_signal_category(sig_id)),
        "why": _signal_why(sig_id),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def build_what_changed(
    diff: dict,
    watchlist: Optional[list] = None,
    meaningful_delta: float = MEANINGFUL_DELTA,
    total_signals: Optional[int] = None,
    max_items: int = 6,
) -> dict:
    """
    Compress a get_signal_diff() result into the "What Changed" payload.

    diff: the dict returned by utils.score_history.get_signal_diff(days_back=N),
          with flipped_bullish / flipped_bearish (each {signal_id,name,from_score,
          to_score,to_status}) and biggest_movers (each {signal_id,name,delta,
          direction,from_score?,to_score?}).
    watchlist: the user's tickers (list[str]); None/empty is fine (no personal
          layer, just the macro view).
    total_signals: universe size for the noise count (defaults to len(SIGNALS)).

    Returns:
        {
          "period_days": int,
          "regime_shift": str|None,
          "meaningful_total": int,     # distinct meaningful signals detected
          "changes": [ {…framed…, "watchlist_hits":[...], "sectors":[...]} ],
          "noise_count": int,          # signals that did NOT meaningfully change
          "most_exposed": str|None,    # watchlist name hit by the most changes
          "has_watchlist": bool,
        }
    """
    diff = diff or {}
    total_signals = total_signals if total_signals is not None else len(SIGNALS)

    # 1) Collect flips (always meaningful) keyed by signal_id.
    entries: dict[str, dict] = {}
    for f in (diff.get("flipped_bullish") or []) + (diff.get("flipped_bearish") or []):
        sid = f.get("signal_id")
        if not sid:
            continue
        d = float(f.get("to_score", 50)) - float(f.get("from_score", 50))
        entries[sid] = _frame_entry(
            sid, f.get("name") or _signal_name(sid),
            f.get("from_score"), f.get("to_score"), d,
            kind="flip", to_status=f.get("to_status"),
        )

    # 2) Add movers that clear the meaningfulness bar and aren't already a flip.
    for m in (diff.get("biggest_movers") or []):
        sid = m.get("signal_id")
        if not sid or sid in entries:
            continue
        if abs(float(m.get("delta", 0) or 0)) < meaningful_delta:
            continue
        entries[sid] = _frame_entry(
            sid, m.get("name") or _signal_name(sid),
            m.get("from_score"), m.get("to_score"), m.get("delta"),
            kind="mover",
        )

    meaningful_total = len(entries)

    # 3) Attach impact (sectors + the user's own holdings).
    for sid, e in entries.items():
        e["watchlist_hits"] = affected_watchlist(sid, watchlist)
        e["sectors"] = affected_sectors(sid)

    # 4) Rank: holdings-affecting first, then by absolute score move.
    ranked = sorted(
        entries.values(),
        key=lambda e: (len(e["watchlist_hits"]) > 0, abs(e["delta"] or 0)),
        reverse=True,
    )[:max_items]

    # 5) Noise = everything in the universe that did NOT meaningfully change.
    noise_count = max(0, total_signals - meaningful_total)

    # 6) Most-exposed watchlist name across the meaningful changes.
    most_exposed = None
    if watchlist:
        from collections import Counter
        c: Counter = Counter()
        for e in entries.values():
            for t in e["watchlist_hits"]:
                c[t] += 1
        if c:
            most_exposed = c.most_common(1)[0][0]

    return {
        "period_days": int(diff.get("days_back", 1) or 1),
        "regime_shift": diff.get("regime_shift"),
        "meaningful_total": meaningful_total,
        "changes": ranked,
        "noise_count": noise_count,
        "most_exposed": most_exposed,
        "has_watchlist": bool(watchlist),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Presentation
# ─────────────────────────────────────────────────────────────────────────────

def _period_label(days: int) -> str:
    if days <= 1:
        return "yesterday"
    if days == 7:
        return "last week"
    return f"the last {days} days"


def _delta_str(delta) -> str:
    if delta is None:
        return ""
    d = round(float(delta), 0)
    di = int(d)
    return f"+{di}" if di >= 0 else f"{di}"


def render_what_changed_html(payload: dict) -> str:
    """Render the payload as one self-contained HTML block for st.markdown()."""
    period = _period_label(payload.get("period_days", 1))
    changes = payload.get("changes") or []
    n = payload.get("meaningful_total", 0)

    # Header + optional regime chip
    regime = payload.get("regime_shift")
    regime_html = (
        f'<span style="margin-left:10px;font-size:0.7rem;font-weight:700;color:#C9A227;'
        f'background:#231F14;border:1px solid #4A3F1E;border-radius:6px;padding:3px 8px;">'
        f'Regime: {regime}</span>'
        if regime else ""
    )

    if n == 0:
        return (
            f'<div style="background:#0F1320;border:1px solid #232942;border-radius:12px;'
            f'padding:18px 20px;font-family:Inter,-apple-system,sans-serif;">'
            f'<div style="font-size:1.05rem;font-weight:700;color:#E8EEFF;">'
            f'No meaningful changes since {period}</div>'
            f'<div style="font-size:0.84rem;color:#8892AA;margin-top:4px;">'
            f'The macro backdrop held steady — no signal flipped or moved enough to matter. '
            f'That itself is information: nothing around your holdings shifted.{regime_html}</div>'
            f'</div>'
        )

    header = (
        f'<div style="display:flex;align-items:baseline;flex-wrap:wrap;">'
        f'<span style="font-size:1.15rem;font-weight:800;color:#E8EEFF;">'
        f'{n} meaningful change{"s" if n != 1 else ""} since {period}</span>{regime_html}'
        f'</div>'
    )

    rows = []
    for e in changes:
        accent = {"up": "#00C853", "down": "#FF4444"}.get(e["direction"], "#8892AA")
        # score move
        if e["from_score"] is not None and e["to_score"] is not None:
            move = (
                f'<span style="color:#8892AA;">score </span>'
                f'<span style="color:#C3CBE0;font-variant-numeric:tabular-nums;">'
                f'{e["from_score"]:g} → {e["to_score"]:g}</span> '
                f'<span style="color:{accent};font-weight:600;">({_delta_str(e["delta"])})</span>'
            )
        else:
            move = f'<span style="color:{accent};font-weight:600;">{_delta_str(e["delta"])} pts</span>'

        # impact line: user's holdings first (highlighted), then sectors
        impact_bits = []
        if e["watchlist_hits"]:
            names = ", ".join(e["watchlist_hits"])
            impact_bits.append(
                f'<span style="color:#7C9CFF;font-weight:600;">Your holdings: {names}</span>'
            )
        sectors = e.get("sectors") or []
        cat = e.get("category_name")
        label = cat if cat else "Macro"
        if sectors:
            label = f'{cat} · ' + ", ".join(sectors[:3]) if cat else ", ".join(sectors[:3])
        impact_bits.append(f'<span style="color:#8892AA;">Affects: {label}</span>')
        impact = ' &nbsp;·&nbsp; '.join(impact_bits)

        rows.append(
            f'<div style="border-left:3px solid {accent};background:#12162400;'
            f'padding:10px 0 10px 14px;margin-top:12px;">'
            f'<div style="font-size:0.95rem;font-weight:700;color:#E8EEFF;">{e["headline"]}</div>'
            f'<div style="font-size:0.82rem;margin-top:3px;">{move}</div>'
            f'<div style="font-size:0.78rem;margin-top:5px;">{impact}</div>'
            + (f'<div style="font-size:0.75rem;color:#6B7280;margin-top:5px;line-height:1.5;">{e["why"]}</div>'
               if e.get("why") else "")
            + '</div>'
        )

    # Footer: noise + most-exposed callout
    foot_bits = []
    noise = payload.get("noise_count", 0)
    if noise > 0:
        foot_bits.append(
            f'The other {noise} signals moved less — treated as noise.'
        )
    most = payload.get("most_exposed")
    if most:
        foot_bits.append(
            f'<span style="color:#7C9CFF;">Most exposed holding today: '
            f'<b>{most}</b></span>'
        )
    footer = (
        f'<div style="font-size:0.78rem;color:#6B7280;margin-top:16px;border-top:1px solid #1E2436;'
        f'padding-top:10px;">{" &nbsp;·&nbsp; ".join(foot_bits)}</div>'
        if foot_bits else ""
    )

    return (
        f'<div style="background:#0F1320;border:1px solid #232942;border-radius:12px;'
        f'padding:18px 20px;font-family:Inter,-apple-system,sans-serif;">'
        f'{header}{"".join(rows)}{footer}</div>'
    )
