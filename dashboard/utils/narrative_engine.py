"""
utils/narrative_engine.py
=========================
Anthropic-powered macro research note generator.

Every Sunday (or on-demand), this module:
  1. Pulls the current state of all signals via get_all_signal_scores()
  2. Builds a structured intelligence brief (signal counts, top drivers,
     category breakdown, regime summary) and feeds it into the Anthropic API
  3. Receives a 500-700 word professional macro research note from Claude
  4. Extracts the headline + regime label, stores the full note in DB
  5. Returns the latest note for display on the Weekly Brief page and home page

API key is read from the ANTHROPIC_API_KEY environment variable — it is
NEVER user-configurable in the UI. Set it once in Render's environment
variables alongside FRED_API_KEY and EIA_API_KEY.

Model used: claude-haiku-4-5 (fast, cheap, sufficient for structured generation).
Estimated token cost per note: ~1,800 in / ~700 out ≈ $0.0008 per note.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

import utils.db as db
from utils.db import macro_narratives, upsert_stmt

# ── Constants ─────────────────────────────────────────────────────────────────

_MODEL        = "claude-haiku-4-5-20251001"
_MAX_TOKENS   = 900
_BULL_THRESH  = 65.0
_BEAR_THRESH  = 35.0

# Map internal category keys → readable section headers for the prompt
_CAT_LABELS = {
    "macro":            "Macro / Credit / Rates",
    "energy":           "Energy Markets",
    "ai_infrastructure":"AI & Technology Infrastructure",
    "nuclear":          "Nuclear & Power Generation",
    "financials":       "Financial Conditions",
    "healthcare":       "Healthcare / Biotech",
    "consumer":         "Consumer",
    "industrials":      "Industrials",
}


# ── Prompt construction ───────────────────────────────────────────────────────

def _build_prompt(scores: dict) -> tuple[str, int, int, str]:
    """
    Build the user-turn prompt from current signal states.

    Returns (prompt_text, bull_count, bear_count, regime_label).
    regime_label is determined here (before the API call) for storage.
    """
    valid   = {k: v for k, v in scores.items() if not v.get("error")}
    bull    = {k: v for k, v in valid.items() if v["status"] == "bullish"}
    bear    = {k: v for k, v in valid.items() if v["status"] == "bearish"}
    neutral = {k: v for k, v in valid.items() if v["status"] not in ("bullish", "bearish")}

    bull_n, bear_n, total = len(bull), len(bear), max(1, len(valid))

    # Regime
    bull_pct = bull_n / total
    bear_pct = bear_n / total
    if bull_pct >= 0.55:
        regime = "RISK-ON"
    elif bear_pct >= 0.55:
        regime = "RISK-OFF"
    elif bull_pct >= 0.40:
        regime = "CAUTIOUSLY BULLISH"
    elif bear_pct >= 0.40:
        regime = "CAUTIOUSLY BEARISH"
    else:
        regime = "MIXED / TRANSITION"

    # Composite score
    composite = round(
        sum(v["score"] for v in valid.values()) / max(1, len(valid)), 1
    )

    # Top 6 bullish + top 6 bearish sorted by score conviction
    top_bull = sorted(bull.values(), key=lambda v: -v["score"])[:6]
    top_bear = sorted(bear.values(), key=lambda v: v["score"])[:6]

    def _sig_line(sv: dict) -> str:
        trend = ""
        t4 = sv.get("trend_4w_pct", 0.0)
        if abs(t4) >= 0.5:
            trend = f" (4w trend: {'+' if t4 > 0 else ''}{t4:.1f}%)"
        return f"  • {sv['name']} — score {sv['score']:.0f}/100{trend}"

    # Category breakdown
    cat_lines: list[str] = []
    for cat_key, cat_label in _CAT_LABELS.items():
        cat_sigs = {k: v for k, v in valid.items() if v.get("category") == cat_key}
        if not cat_sigs:
            continue
        c_bull = sum(1 for v in cat_sigs.values() if v["status"] == "bullish")
        c_bear = sum(1 for v in cat_sigs.values() if v["status"] == "bearish")
        c_avg  = round(sum(v["score"] for v in cat_sigs.values()) / len(cat_sigs), 0)
        cat_lines.append(f"  {cat_label}: {c_bull} bull / {c_bear} bear (avg score {c_avg:.0f})")

    prompt = f"""You are a senior macro strategist at a quantitative hedge fund writing the firm's weekly internal research note.

Today's date: {datetime.now(timezone.utc).strftime("%B %d, %Y")}
Signal universe: {total} active macro indicators
Composite macro score: {composite}/100
Regime classification: {regime}
Bullish signals: {bull_n}/{total} ({bull_pct*100:.0f}%)
Bearish signals: {bear_n}/{total} ({bear_pct*100:.0f}%)
Neutral/Transitioning: {len(neutral)}/{total}

TOP BULLISH CONVICTION SIGNALS:
{chr(10).join(_sig_line(sv) for sv in top_bull) if top_bull else "  None above threshold"}

TOP BEARISH CONVICTION SIGNALS:
{chr(10).join(_sig_line(sv) for sv in top_bear) if top_bear else "  None above threshold"}

CATEGORY BREAKDOWN:
{chr(10).join(cat_lines)}

Write a 550-700 word professional macro research note based on this signal data. The note must:

1. Open with a bold headline (1 line, no quotes, actionable, specific — e.g. "Labor Market Resilience Offsets Credit Spread Widening as Regime Holds Risk-On Bias")
2. State the current regime and composite score in the first sentence
3. Explain the most important 3-4 signal developments driving the current read, with specific data points from the signal values above
4. Discuss any notable tension or divergence between signal categories (e.g. macro positive but credit tightening)
5. Close with a "Bottom Line" paragraph: what this means for risk positioning, what would flip the regime, key things to watch this week
6. Use active voice, institutional vocabulary (no hype, no "rocket" language, no exclamation points)
7. Format: HEADLINE on first line, then blank line, then body paragraphs separated by blank lines, then final paragraph starting with "Bottom Line:"

Do not add any metadata, dates, author names, or section headers other than "Bottom Line:" at the end. Output only the note text."""

    return prompt, bull_n, bear_n, regime


# ── API call ─────────────────────────────────────────────────────────────────

def generate_weekly_note(force: bool = False) -> Optional[dict]:
    """
    Generate and store a new macro research note for today's date.

    Returns the stored note dict (from DB) or None on any failure.

    Set force=True to regenerate even if today's note already exists
    (used by the "Generate Now" button in Weekly Brief page).

    This function is NOT cached — it's called explicitly, not on every
    page load. DB reads are what power the live display.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        st.warning("ANTHROPIC_API_KEY is not set. Add it to Render environment variables.")
        return None

    # Check if today's note already exists (skip unless force=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not force:
        existing = get_note_by_date(today)
        if existing:
            return existing

    # Pull signal state
    try:
        from utils.signals_cache import get_all_signal_scores
        scores = get_all_signal_scores()
    except Exception as exc:
        st.error(f"Could not load signal scores: {exc}")
        return None

    # Build prompt
    prompt, bull_n, bear_n, regime = _build_prompt(scores)

    # Call Anthropic API
    try:
        import anthropic
        client   = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=(
                "You are a senior macro strategist writing precise, institutional-grade "
                "quantitative research notes. Your writing is dense with information, "
                "analytically rigorous, and written for sophisticated investors. "
                "Never use hype language. Always ground analysis in the specific data provided."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        st.error(f"Anthropic API error: {exc}")
        return None

    raw_text     = response.content[0].text.strip()
    input_tok    = response.usage.input_tokens
    output_tok   = response.usage.output_tokens

    # Extract headline (first non-empty line)
    lines    = [ln.strip() for ln in raw_text.split("\n") if ln.strip()]
    headline = lines[0][:255] if lines else "Unstructured Alpha Weekly Macro Note"

    # Store in DB (upsert on note_date — idempotent re-generation)
    engine = get_engine()
    now_ts = datetime.now(timezone.utc).isoformat()
    try:
        stmt = upsert_stmt(macro_narratives, ["note_date"]).values(
            note_date=today,
            regime=regime,
            headline=headline,
            body=raw_text,
            bull_count=bull_n,
            bear_count=bear_n,
            model=_MODEL,
            input_tokens=input_tok,
            output_tokens=output_tok,
            created_at=now_ts,
        ).on_conflict_do_update(
            index_elements=["note_date"],
            set_={
                "regime":        regime,
                "headline":      headline,
                "body":          raw_text,
                "bull_count":    bull_n,
                "bear_count":    bear_n,
                "model":         _MODEL,
                "input_tokens":  input_tok,
                "output_tokens": output_tok,
                "created_at":    now_ts,
            },
        )
        with db.engine.begin() as conn:
            conn.execute(stmt)
    except Exception as exc:
        st.error(f"DB write error: {exc}")
        return None

    return get_note_by_date(today)


# ── DB reads ─────────────────────────────────────────────────────────────────

def get_latest_note() -> Optional[dict]:
    """
    Return the most recent macro narrative note from DB, or None if none exist.
    """
    try:
        from sqlalchemy import select, text
        with db.engine.connect() as conn:
            row = conn.execute(
                select(macro_narratives)
                .order_by(text("note_date DESC"))
                .limit(1)
            ).mappings().first()
        return dict(row) if row else None
    except Exception:
        return None


def get_note_by_date(note_date: str) -> Optional[dict]:
    """
    Return the note for a specific YYYY-MM-DD date, or None.
    """
    try:
        from sqlalchemy import select
        with db.engine.connect() as conn:
            row = conn.execute(
                select(macro_narratives).where(macro_narratives.c.note_date == note_date)
            ).mappings().first()
        return dict(row) if row else None
    except Exception:
        return None


def get_note_archive(limit: int = 12) -> list[dict]:
    """
    Return up to `limit` past notes ordered newest-first (for archive display).
    """
    try:
        from sqlalchemy import select, text
        with db.engine.connect() as conn:
            rows = conn.execute(
                select(
                    macro_narratives.c.id,
                    macro_narratives.c.note_date,
                    macro_narratives.c.regime,
                    macro_narratives.c.headline,
                    macro_narratives.c.bull_count,
                    macro_narratives.c.bear_count,
                    macro_narratives.c.body,
                    macro_narratives.c.created_at,
                )
                .order_by(text("note_date DESC"))
                .limit(limit)
            ).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []


def should_auto_generate() -> bool:
    """
    Returns True if today is Sunday AND no note exists for today yet.
    Called from app.py (best-effort, wrapped in try/except there).
    """
    today = datetime.now(timezone.utc)
    if today.weekday() != 6:  # 6 = Sunday
        return False
    return get_note_by_date(today.strftime("%Y-%m-%d")) is None
