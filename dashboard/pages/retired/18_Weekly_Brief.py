"""
pages/18_Weekly_Brief.py
========================
Unstructured Alpha — Weekly Macro Research Note

Machine-generated institutional macro research note published weekly.
Powered by the Anthropic API (claude-haiku-4-5) writing from the live
signal state. Each note is stored permanently in the macro_narratives
DB table, with a full archive going back to the first generated note.

Layout:
  ┌────────────────────────────────────────────────────────┐
  │  📰 WEEKLY MACRO BRIEF                                 │
  │  [Regime chip]  [Date]  [Bull/Bear summary]            │
  │  ─────────────────────────────────────────────         │
  │  [Headline]                                            │
  │                                                        │
  │  [Body paragraphs — editorial layout]                  │
  │                                                        │
  │  [Archive expander — past notes index]                 │
  │                                                        │
  │  [Generate Now button — Pro/admin only]                │
  └────────────────────────────────────────────────────────┘
"""

import streamlit as st

st.set_page_config(
    page_title="Weekly Brief — Unstructured Alpha",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

import html as _html_mod  # must be at module level — used in archive section outside else block

from utils.header import render_header, render_sidebar_base, render_page_header

render_header()

render_page_header(
    "Weekly Brief",
    "AI-generated macro research notes published every Sunday.",
    icon="📰",
)

# ── Imports ───────────────────────────────────────────────────────────────────
from utils.narrative_engine import (
    get_latest_note,
    get_note_archive,
    generate_weekly_note,
)

# ── Page CSS ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Page-level resets ── */
.block-container { padding-top: 0.5rem !important; max-width: 860px !important; }

/* ── Masthead ── */
.ua-masthead {
    border-bottom: 3px double #E8EEFF;
    padding-bottom: 10px;
    margin-bottom: 18px;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
}
.ua-masthead-title {
    font-family: Inter, -apple-system, sans-serif;
    font-size: 1.55rem;
    font-weight: 700;
    color: #E8EEFF;
    letter-spacing: 0.02em;
}
.ua-masthead-sub {
    font-family: Inter, sans-serif;
    font-size: 0.75rem;
    color: #6B5E52;
    font-style: italic;
}
/* ── Regime chip ── */
.ua-regime-chip {
    display: inline-block;
    font-size: 0.70rem;
    font-weight: 700;
    letter-spacing: 0.10em;
    padding: 3px 10px;
    border-radius: 3px;
    margin-right: 6px;
    vertical-align: middle;
}
/* ── Note metadata bar ── */
.ua-meta-bar {
    font-family: Inter, sans-serif;
    font-size: 0.73rem;
    color: #6B5E52;
    margin-bottom: 14px;
    line-height: 1.5;
}
/* ── Headline ── */
.ua-headline {
    font-family: Inter, -apple-system, sans-serif;
    font-size: 1.45rem;
    font-weight: 700;
    color: #E8EEFF;
    line-height: 1.35;
    margin-bottom: 18px;
    border-left: 4px solid #8B6914;
    padding-left: 14px;
}
/* ── Body text ── */
.ua-body {
    font-family: Inter, -apple-system, sans-serif;
    font-size: 0.96rem;
    line-height: 1.82;
    color: #E8EEFF;
    max-width: 780px;
}
.ua-body p {
    margin-bottom: 1.2em;
}
.ua-body strong, .ua-body b {
    font-weight: 700;
    color: #E8EEFF;
}
/* "Bottom Line:" paragraph gets a special treatment */
.ua-bottom-line {
    background: #0B0D12;
    border: 1px solid #E0D5C5;
    border-radius: 6px;
    padding: 14px 18px;
    font-family: Inter, sans-serif;
    font-size: 0.94rem;
    line-height: 1.75;
    color: #E8EEFF;
    margin-top: 4px;
}
/* ── Archive table ── */
.ua-archive-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 7px 0;
    border-bottom: 1px solid #EDE8E0;
    flex-wrap: wrap;
}
.ua-archive-date { font-size: 0.72rem; color: #6B7FBF; min-width: 80px; font-family: monospace; }
.ua-archive-hl   { font-size: 0.83rem; color: #E8EEFF; font-family: Inter, sans-serif; flex: 1; line-height: 1.3; }
.ua-archive-regime { font-size: 0.65rem; font-weight: 700; letter-spacing: 0.08em; padding: 2px 6px; border-radius: 2px; }
/* ── Empty state ── */
.ua-empty {
    text-align: center;
    padding: 40px 20px;
    font-family: Inter, sans-serif;
    color: #6B5E52;
}
</style>
""", unsafe_allow_html=True)

# ── Helper: regime chip ───────────────────────────────────────────────────────
def _regime_chip(regime: str) -> str:
    colors = {
        "RISK-ON":            ("#E8F5E9", "#00D566"),
        "CAUTIOUSLY BULLISH": ("#F1F8E9", "#33691E"),
        "MIXED / TRANSITION": ("rgba(245,158,11,0.12)", "#F59E0B"),
        "CAUTIOUSLY BEARISH": ("#FBE9E7", "#BF360C"),
        "RISK-OFF":           ("#FFEBEE", "#FF4444"),
    }
    bg, fg = colors.get(regime, ("#F5F5F5", "#444444"))
    return (
        f'<span class="ua-regime-chip" '
        f'style="background:{bg};color:{fg};border:1px solid {fg}33;">'
        f'{regime}</span>'
    )


def _render_archive_chip(regime: str) -> str:
    colors = {
        "RISK-ON":            ("#E8F5E9", "#00D566"),
        "CAUTIOUSLY BULLISH": ("#F1F8E9", "#33691E"),
        "MIXED / TRANSITION": ("rgba(245,158,11,0.12)", "#F59E0B"),
        "CAUTIOUSLY BEARISH": ("#FBE9E7", "#BF360C"),
        "RISK-OFF":           ("#FFEBEE", "#FF4444"),
    }
    bg, fg = colors.get(regime, ("#F5F5F5", "#444444"))
    return (
        f'<span class="ua-archive-regime" '
        f'style="background:{bg};color:{fg};border:1px solid {fg}33;">'
        f'{regime}</span>'
    )


# ── Masthead ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="ua-masthead">
    <span class="ua-masthead-title">📰 Unstructured Alpha — Weekly Brief</span>
    <span class="ua-masthead-sub">Machine intelligence · Macro signal synthesis · Published weekly</span>
</div>
""", unsafe_allow_html=True)

# ── Load latest note ──────────────────────────────────────────────────────────
note = get_latest_note()

if note is None:
    st.markdown("""
    <div class="ua-empty">
        <p style="font-size:1.1rem;font-weight:700;color:#E8EEFF;">No notes generated yet.</p>
        <p>The first Weekly Brief will be generated automatically next Sunday,<br>
        or you can generate one now using the button below.</p>
    </div>
    """, unsafe_allow_html=True)
else:
    # ── Regime chip + meta bar ────────────────────────────────────────────────
    regime    = note.get("regime", "MIXED / TRANSITION")
    note_date = note.get("note_date", "")
    bull_n    = note.get("bull_count") or 0
    bear_n    = note.get("bear_count") or 0
    model_str = note.get("model", "")

    # Format date: "2026-06-22" → "June 22, 2026"
    try:
        from datetime import datetime
        _d = datetime.strptime(note_date, "%Y-%m-%d")
        date_display = _d.strftime("%B %d, %Y")
    except Exception:
        date_display = note_date

    st.markdown(
        f'{_regime_chip(regime)}'
        f'<span class="ua-meta-bar">&nbsp;&nbsp;'
        f'Published {date_display} &nbsp;·&nbsp; '
        f'{bull_n} bullish · {bear_n} bearish signals &nbsp;·&nbsp; '
        f'Generated by {model_str}'
        f'</span>',
        unsafe_allow_html=True,
    )

    # ── Parse note body ───────────────────────────────────────────────────────
    # Body format: HEADLINE (line 1), then blank line, then paragraphs.
    # We already stored the headline separately; strip it from body for display.
    raw_body  = note.get("body", "")
    headline  = note.get("headline", "")
    paragraphs = [p.strip() for p in raw_body.split("\n\n") if p.strip()]

    # Drop the first paragraph if it exactly matches the headline
    # (some generation runs include it twice)
    if paragraphs and paragraphs[0].strip("*#").strip() == headline.strip("*#").strip():
        paragraphs = paragraphs[1:]

    # ── Headline ──────────────────────────────────────────────────────────────
    display_headline = _html_mod.escape(headline.lstrip("#*").strip())
    st.markdown(
        f'<div class="ua-headline">{display_headline}</div>',
        unsafe_allow_html=True,
    )

    # ── Body paragraphs ───────────────────────────────────────────────────────
    body_html_parts: list[str] = []
    for para in paragraphs:
        safe = _html_mod.escape(para)
        # Handle both "Bottom Line:" and "**Bottom Line:**" (markdown bold variant)
        _is_bottom_line = (
            safe.startswith("Bottom Line:")
            or safe.startswith("**Bottom Line:**")
            or safe.startswith("**Bottom Line:**")
        )
        if _is_bottom_line:
            # Strip any of the known prefix forms, then render with styled label
            _rest = safe
            for _prefix in ("**Bottom Line:**", "**Bottom Line:**", "Bottom Line:"):
                if _rest.startswith(_prefix):
                    _rest = _rest[len(_prefix):].strip()
                    break
            body_html_parts.append(
                f'<div class="ua-bottom-line"><strong>Bottom Line:</strong> {_rest}</div>'
            )
        else:
            body_html_parts.append(f'<p>{safe}</p>')

    st.markdown(
        f'<div class="ua-body">{"".join(body_html_parts)}</div>',
        unsafe_allow_html=True,
    )

    # ── Divider ───────────────────────────────────────────────────────────────
    st.markdown(
        '<hr style="border:none;border-top:1px solid #DDD5C8;margin:28px 0 18px;">',
        unsafe_allow_html=True,
    )

# ── Archive ───────────────────────────────────────────────────────────────────
archive = get_note_archive(limit=16)

if len(archive) > 1:
    with st.expander(f"📂 Archive — past {len(archive)} notes", expanded=False):
        rows_html: list[str] = []
        for rec in archive:
            # Skip the current note (already shown above)
            if note and rec.get("note_date") == note.get("note_date"):
                continue
            try:
                from datetime import datetime as _dt
                _d2 = _dt.strptime(rec["note_date"], "%Y-%m-%d")
                d_str = _d2.strftime("%b %d, %Y")
            except Exception:
                d_str = rec["note_date"]

            hl  = _html_mod.escape(rec.get("headline", ""))
            rows_html.append(
                f'<div class="ua-archive-row">'
                f'<span class="ua-archive-date">{d_str}</span>'
                f'{_render_archive_chip(rec.get("regime", ""))}'
                f'<span class="ua-archive-hl">{hl}</span>'
                f'</div>'
            )
        st.markdown("".join(rows_html), unsafe_allow_html=True)

        # Full archive note expanders
        for rec in archive:
            if note and rec.get("note_date") == note.get("note_date"):
                continue
            try:
                from datetime import datetime as _dt2
                _d3 = _dt2.strptime(rec["note_date"], "%Y-%m-%d")
                d_label = _d3.strftime("%B %d, %Y")
            except Exception:
                d_label = rec["note_date"]
            _safe_hl_exp = _html_mod.escape(rec.get("headline", d_label)[:70])
            with st.expander(f"Read: {rec.get('headline', d_label)[:70]}…", expanded=False):
                st.caption(f"{d_label} · {rec.get('regime', '')}")
                raw2 = rec.get("body", "")
                paras2 = [p.strip() for p in raw2.split("\n\n") if p.strip()]
                hl2 = rec.get("headline", "").strip("*#").strip()
                if paras2 and paras2[0].strip("*#").strip() == hl2:
                    paras2 = paras2[1:]
                for pa in paras2:
                    safe2 = _html_mod.escape(pa)
                    _is_bl2 = (
                        safe2.startswith("Bottom Line:")
                        or safe2.startswith("**Bottom Line:**")
                    )
                    if _is_bl2:
                        _rest2 = safe2
                        for _pfx2 in ("**Bottom Line:**", "Bottom Line:"):
                            if _rest2.startswith(_pfx2):
                                _rest2 = _rest2[len(_pfx2):].strip()
                                break
                        st.markdown(
                            f'<div class="ua-bottom-line"><strong>Bottom Line:</strong> {_rest2}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(f'<div class="ua-body"><p>{safe2}</p></div>', unsafe_allow_html=True)

# ── Generate Now button ───────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<p style="font-size:0.75rem;color:#6B7FBF;font-family:\'Georgia\',serif;">'
    'Weekly Briefs are generated automatically every Sunday using live signal data and the Anthropic API. '
    'You can generate or regenerate a note at any time using the button below.'
    '</p>',
    unsafe_allow_html=True,
)

col_btn, col_pad = st.columns([0.25, 0.75])
with col_btn:
    if st.button("⚡ Generate Note Now", use_container_width=True):
        with st.spinner("Calling Anthropic API — generating macro research note..."):
            new_note = generate_weekly_note(force=True)
        if new_note:
            st.success("Note generated! Refreshing...")
            st.rerun()
        else:
            st.error(
                "Generation failed. Check that ANTHROPIC_API_KEY is set in Render "
                "environment variables and that the API key is valid."
            )
