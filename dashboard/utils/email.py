# utils/email.py
# Unstructured Alpha — Verification Email Sending (Resend)
#
# Endpoint/payload shape verified live against Resend's published API
# reference before writing this, 2026-06-21:
#   POST https://api.resend.com/emails
#   Authorization: Bearer {api_key}
#   {"from": "...", "to": [...], "subject": "...", "html": "..."}
#   -> {"id": "..."}
# Plain requests.post, not Resend's Python SDK -- consistent with every
# other third-party integration in this codebase (FRED, EIA, SEC, FINRA all
# use requests directly), and avoids adding a dependency just to wrap one
# REST call this small.
#
# Configuration -- environment variable checked FIRST, st.secrets as a
# fallback (same priority order as FRED_API_KEY/EIA_API_KEY in
# utils/fetchers.py and DATABASE_URL in utils/db.py). This matters beyond
# consistency: st.secrets only exists at all under Streamlit Cloud's
# secrets.toml mechanism, so a host without that (Render, Railway, a plain
# VPS) needs the env var path to work, not just a fallback that happens to
# never get reached:
#   RESEND_API_KEY   -- required to actually send mail.
#   RESEND_FROM_EMAIL -- optional; defaults to Resend's own test sender
#     ("onboarding@resend.dev"), which only works for sending TO the email
#     address on the Resend account itself, not arbitrary recipients --
#     real signups need a verified sending domain configured in Resend and
#     that address set here.

import hashlib
import html as _html
import os

import requests
import streamlit as st

_RESEND_API_URL = "https://api.resend.com/emails"
_DEFAULT_FROM = "Unstructured Alpha <onboarding@resend.dev>"
_APP_URL = os.environ.get("APP_BASE_URL", "https://app.unstructuredalpha.com").rstrip("/")


class EmailSendError(Exception):
    """Raised when the verification email genuinely fails to send (bad/missing
    API key, Resend API error) -- distinct from AuthError, since this is an
    infrastructure failure, not a user input mistake."""


def _get_resend_config() -> tuple[str, str]:
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        try:
            api_key = st.secrets.get("RESEND_API_KEY", "")
        except Exception:
            api_key = ""

    from_email = os.environ.get("RESEND_FROM_EMAIL", "")
    if not from_email:
        try:
            from_email = st.secrets.get("RESEND_FROM_EMAIL", _DEFAULT_FROM)
        except Exception:
            from_email = _DEFAULT_FROM
    return api_key, from_email


def _safe(value: object) -> str:
    """Escape dynamic content before inserting it into an HTML email."""
    return _html.escape(str(value), quote=True)


def _recipient_token(to_email: str) -> str:
    return hashlib.sha256(to_email.strip().lower().encode("utf-8")).hexdigest()[:16]


def _post_resend_email(
    *,
    api_key: str,
    from_email: str,
    to_email: str,
    subject: str,
    html: str,
    email_type: str,
    idempotency_key: str,
    timeout: int = 20,
) -> requests.Response:
    """Send a tagged, retry-safe Resend email."""
    return requests.post(
        _RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key[:256],
        },
        json={
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html,
            "tags": [{"name": "email_type", "value": email_type}],
        },
        timeout=timeout,
    )


def send_verification_email(to_email: str, code: str) -> None:
    """Send a 6-digit verification code to to_email. Raises EmailSendError
    if RESEND_API_KEY isn't configured or Resend's API rejects the request.

    TEMPORARY DIAGNOSTIC LOGGING (added 2026-06-22, remove once the "emails
    aren't arriving for arbitrary recipients" issue is confirmed fixed):
    the FIRST version of this logging never showed up in Render's logs at
    all, even though a fresh, fully-observed incognito test confirmed
    signup() really was completing successfully (the "We emailed a code"
    UI message only renders when no exception was raised) -- and the
    GitHub source for the exact deployed commit was checked directly and
    does contain these print() calls. That combination only makes sense
    as a well-known Python/Docker gotcha: stdout is FULLY buffered (not
    line-buffered) when it's not an interactive terminal, which is always
    true for a containerized process whose stdout is piped into a log
    collector -- so print() output can sit in an internal buffer
    indefinitely in a long-running server process that never naturally
    exits, instead of ever reaching the log stream. flush=True on every
    print() below forces each line out immediately rather than waiting
    on Python's buffer to fill.
    """
    api_key, from_email = _get_resend_config()
    print(f"[email] send_verification_email called: to={to_email!r} from={from_email!r} "
          f"api_key_present={bool(api_key)} api_key_prefix={api_key[:6] if api_key else None!r}",
          flush=True)
    if not api_key:
        print("[email] aborting: no RESEND_API_KEY configured", flush=True)
        raise EmailSendError(
            "No RESEND_API_KEY configured -- add one in Streamlit secrets to send real verification emails."
        )

    html = f"""
    <div style="font-family: Georgia, serif; max-width: 480px;">
        <h2 style="color:#1C2B4A;">Verify your Unstructured Alpha account</h2>
        <p>Enter this code to finish creating your account:</p>
        <div style="font-size:2rem; font-weight:700; letter-spacing:0.2em; color:#B8860B; margin: 16px 0;">
            {code}
        </div>
        <p style="color:#8B7355; font-size:0.85rem;">This code expires in 15 minutes. If you didn't request this, you can ignore this email.</p>
    </div>
    """

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "Your Unstructured Alpha verification code",
                "html": html,
            },
            timeout=15,
        )
        print(f"[email] Resend API responded: status={resp.status_code} body={resp.text[:500]!r}", flush=True)
        resp.raise_for_status()
        print(f"[email] send succeeded for to={to_email!r}", flush=True)
    except requests.RequestException as e:
        print(f"[email] send FAILED for to={to_email!r}: {type(e).__name__}: {e}", flush=True)
        raise EmailSendError(f"Failed to send verification email: {e}") from e


def _build_article_html(
    signal_scores: dict,
    signal_flips: list[dict],
    bias: str,
    bull_n: int,
    bear_n: int,
    neut_n: int,
    date_str: str,
) -> tuple[str, str]:
    """
    Build the Seeking Alpha-style macro article HTML.
    Returns (article_html, subject_line).

    signal_scores: {sig_id: {"name": str, "score": float, "status": str}}
    """
    total = bull_n + bear_n + neut_n or 1

    # ── Top signals by conviction ──────────────────────────────────────────
    bull_sigs = sorted(
        [(sid, sv) for sid, sv in signal_scores.items() if sv.get("status") == "bullish"],
        key=lambda x: -x[1].get("score", 0),
    )[:4]
    bear_sigs = sorted(
        [(sid, sv) for sid, sv in signal_scores.items() if sv.get("status") == "bearish"],
        key=lambda x: x[1].get("score", 100),
    )[:3]

    top_bull_name = bull_sigs[0][1].get("name", "several macro series") if bull_sigs else "broad macro data"
    top_bear_name = bear_sigs[0][1].get("name", "some indicators") if bear_sigs else None

    # ── Dynamic subject line ───────────────────────────────────────────────
    flip_n = len(signal_flips)
    if flip_n >= 3:
        subject = f"{flip_n} Signals Just Flipped — What the Data Is Saying This Morning"
    elif bias == "Bullish" and bull_n >= bear_n * 2:
        subject = f"Bull Signals Dominate {bull_n}–{bear_n}: {top_bull_name} Leads the Way"
    elif bias == "Bearish" and bear_n >= bull_n * 2:
        subject = f"Macro Warning: {bear_n} Bearish Signals This Morning — UA Brief"
    elif bias == "Bullish":
        subject = f"UA Morning Brief — Signal Stack Reads Bullish ({bull_n}▲ {bear_n}▼)"
    elif bias == "Bearish":
        subject = f"UA Morning Brief — Signal Stack Reads Bearish ({bear_n}▼ {bull_n}▲)"
    else:
        subject = f"UA Morning Brief — Mixed Signals ({bull_n}▲ {bear_n}▼) · {date_str}"

    # ── Headline ───────────────────────────────────────────────────────────
    if flip_n >= 3:
        headline = (
            f"{flip_n} Signals Flipped Overnight — "
            f"Here's What the Data Is Saying on {date_str}"
        )
    elif bias == "Bullish" and bull_n >= bear_n * 2:
        headline = (
            f"Bull Signals Outnumber Bears {bull_n}–{bear_n}: "
            f"{top_bull_name} Is Leading the Way"
        )
    elif bias == "Bearish" and bear_n >= bull_n:
        headline = (
            f"Macro Headwinds: {bear_n} Bearish Signals Across Independent Series — "
            f"Morning Brief"
        )
    else:
        headline = (
            f"Mixed Picture: {bull_n} Bull vs {bear_n} Bear — "
            f"Where the Data Agrees and Disagrees"
        )

    # ── Lede paragraph ─────────────────────────────────────────────────────
    if bias == "Bullish" and bull_n / total >= 0.50:
        lede = (
            f"<strong>This morning's macro read leans bullish.</strong> "
            f"The Unstructured Alpha signal stack — {total} independent macro, positioning, "
            f"and momentum series — is registering {bull_n} bullish against {bear_n} bearish. "
            f"The lead signal is <strong>{top_bull_name}</strong>, reading at "
            f"{bull_sigs[0][1].get('score', 0):.0f}/100."
        ) if bull_sigs else (
            f"<strong>This morning's macro read leans bullish.</strong> "
            f"The signal stack shows {bull_n} bullish against {bear_n} bearish across "
            f"{total} independent series."
        )
    elif bias == "Bearish" and bear_n / total >= 0.45:
        lede = (
            f"<strong>Caution is warranted this morning.</strong> "
            f"The signal stack is reading {bear_n} bearish against {bull_n} bullish "
            f"across {total} independent series. "
            + (f"<strong>{top_bear_name}</strong> is the sharpest bearish read at "
               f"{bear_sigs[0][1].get('score', 0):.0f}/100." if top_bear_name and bear_sigs else "")
        )
    else:
        lede = (
            f"<strong>The signal stack is sending mixed messages this morning.</strong> "
            f"{bull_n} series read bullish and {bear_n} read bearish across {total} "
            f"independent data sources — a split that calls for selectivity rather than "
            f"a broad directional bet."
        )

    # ── Key Data Points rows ───────────────────────────────────────────────
    data_rows = ""
    shown = set()
    for sid, sv in bull_sigs[:3]:
        shown.add(sid)
        score = sv.get("score", 0)
        name  = sv.get("name", sid)
        data_rows += (
            f'<tr>'
            f'<td style="padding:5px 8px 5px 0;font-size:0.83rem;color:#1a202c;'
            f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
            f'<span style="color:#00875A;font-weight:700;">▲</span>&nbsp;{name}</td>'
            f'<td style="padding:5px 0 5px 8px;font-weight:700;font-size:0.83rem;'
            f'color:#00875A;text-align:right;white-space:nowrap;">{score:.0f}/100</td>'
            f'</tr>'
        )
    for sid, sv in bear_sigs[:2]:
        if sid in shown:
            continue
        score = sv.get("score", 0)
        name  = sv.get("name", sid)
        data_rows += (
            f'<tr>'
            f'<td style="padding:5px 8px 5px 0;font-size:0.83rem;color:#1a202c;'
            f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
            f'<span style="color:#C53030;font-weight:700;">▼</span>&nbsp;{name}</td>'
            f'<td style="padding:5px 0 5px 8px;font-weight:700;font-size:0.83rem;'
            f'color:#C53030;text-align:right;white-space:nowrap;">{score:.0f}/100</td>'
            f'</tr>'
        )

    if flip_n:
        # Highlight the biggest flip
        top_flip = signal_flips[0]
        flip_dir = "→ Bullish" if top_flip.get("to_status") == "bullish" else "→ Bearish"
        flip_color = "#00875A" if top_flip.get("to_status") == "bullish" else "#C53030"
        data_rows += (
            f'<tr style="border-top:1px solid #E2E8F0;">'
            f'<td style="padding:7px 8px 5px 0;font-size:0.83rem;color:#4A5568;'
            f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
            f'Flip: {top_flip.get("signal_name", top_flip.get("signal_id",""))}</td>'
            f'<td style="padding:7px 0 5px 8px;font-weight:700;font-size:0.83rem;'
            f'color:{flip_color};text-align:right;">{flip_dir}</td>'
            f'</tr>'
        )

    # ── Analysis paragraph ─────────────────────────────────────────────────
    if bias == "Bullish":
        analysis = (
            "When multiple independent macro series align in the same direction, "
            "the signal is historically more meaningful than any single indicator. "
            "The current bullish cluster spans economic sectors with low mutual "
            "correlation — meaning the read isn't coming from one shared driver, "
            "but from genuinely broad-based improvement across the data stack."
        )
        if bear_sigs:
            analysis += (
                f" The main counterpoint: {top_bear_name} is still reading bearish "
                f"at {bear_sigs[0][1].get('score', 0):.0f}/100 — worth monitoring as a "
                f"potential early-warning indicator for any reversal."
            ) if top_bear_name else ""
    elif bias == "Bearish":
        analysis = (
            "The bearish cluster deserves attention precisely because it's showing up "
            "across independent data series — not all of which move on the same economic cycle. "
            "When trucking volumes, credit conditions, and forward-looking indicators all "
            "lean negative simultaneously, it typically reflects broad underlying softness "
            "rather than one-sector noise."
        )
        if bull_sigs:
            analysis += (
                f" The counter-argument: {top_bull_name} remains bullish at "
                f"{bull_sigs[0][1].get('score', 0):.0f}/100, providing a reason for "
                f"selectivity rather than blanket defensiveness."
            )
    else:
        analysis = (
            "Mixed signal environments are the norm, not the exception — "
            "but the current split is notable because it's clean: the bullish "
            "readings are concentrated in leading indicators (they point forward), "
            "while the bearish readings cluster in coincident and lagging data. "
            "This setup has historically resolved in the direction of the leading indicators "
            "within 2–4 weeks, making the next round of data prints especially important."
        )

    # ── Risk / Watch section ───────────────────────────────────────────────
    if bear_sigs:
        risk_sig = bear_sigs[0]
        risk_text = (
            f"<strong>{risk_sig[1].get('name', 'Key signal')}</strong> is the sharpest "
            f"bearish read in the stack at {risk_sig[1].get('score', 0):.0f}/100. "
            f"A continuation lower in this series would shift the overall picture and "
            f"is the primary data point to watch in the next 1–2 weeks."
        )
    elif bias == "Bullish":
        risk_text = (
            "The bull read is broad but not unanimous. "
            "Watch for any reversal in labor or freight data — "
            "both have historically given 2–4 weeks of lead time on macro inflections."
        )
    else:
        risk_text = (
            "Monitor the signal flip table below for any cluster of moves in one direction. "
            "Three or more coordinated flips in a single session have historically been "
            "a reliable confirmation signal."
        )

    # ── Bottom line ────────────────────────────────────────────────────────
    if bias == "Bullish":
        bottom_line = (
            f"Bull signals outnumber bears {bull_n}:{bear_n} today. "
            f"The machine leans bullish on macro grounds. "
            f"As always — verify with your own research before acting."
        )
    elif bias == "Bearish":
        bottom_line = (
            f"Bear signals outnumber bulls {bear_n}:{bull_n} today. "
            f"The data skews cautious. This is a read on macro alignment, "
            f"not a market call — do your own diligence."
        )
    else:
        bottom_line = (
            f"The signal stack is split {bull_n} bull / {bear_n} bear today. "
            f"No clear macro consensus. Selectivity over broad directional bets."
        )

    # ── Bias accent color ──────────────────────────────────────────────────
    accent = "#6A5ACD" if bias == "Bullish" else ("#C53030" if bias == "Bearish" else "#5A6472")

    article_html = f"""
    <div style="background:#ffffff;padding:28px 24px 20px;">
        <!-- Article header -->
        <div style="border-left:4px solid {accent};padding-left:16px;margin-bottom:20px;">
            <div style="font-size:0.60rem;color:#8892AA;text-transform:uppercase;
                        letter-spacing:0.12em;margin-bottom:7px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                MACRO INTELLIGENCE · {date_str.upper()}
            </div>
            <h2 style="font-size:1.25rem;font-weight:800;color:#0f1119;margin:0 0 8px;
                       line-height:1.35;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                {headline}
            </h2>
        </div>

        <!-- Lede -->
        <p style="font-size:0.92rem;color:#1a202c;line-height:1.75;margin:0 0 18px;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            {lede}
        </p>

        <!-- Key Data Points -->
        <div style="background:#F7F8FA;border-radius:6px;padding:14px 16px;margin-bottom:20px;
                    border:1px solid #E2E8F0;">
            <div style="font-size:0.60rem;font-weight:700;color:{accent};
                        text-transform:uppercase;letter-spacing:0.12em;margin-bottom:10px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                KEY DATA POINTS
            </div>
            <table style="border-collapse:collapse;width:100%;">
                {data_rows}
            </table>
        </div>

        <!-- What This Means -->
        <div style="font-size:0.60rem;font-weight:700;color:#4A5568;text-transform:uppercase;
                    letter-spacing:0.10em;margin-bottom:8px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            WHAT THIS MEANS
        </div>
        <p style="font-size:0.88rem;color:#2D3748;line-height:1.78;margin:0 0 18px;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            {analysis}
        </p>

        <!-- Watch For -->
        <div style="border-left:3px solid #C53030;padding:10px 14px;
                    background:#FFF5F5;border-radius:0 4px 4px 0;margin-bottom:20px;">
            <div style="font-size:0.60rem;font-weight:700;color:#C53030;
                        text-transform:uppercase;letter-spacing:0.10em;margin-bottom:5px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                WATCH FOR
            </div>
            <p style="font-size:0.83rem;color:#4A5568;margin:0;line-height:1.65;
                      font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                {risk_text}
            </p>
        </div>

        <!-- Bottom Line -->
        <div style="border-top:2px solid #E2E8F0;padding-top:14px;">
            <span style="font-size:0.60rem;font-weight:700;color:{accent};
                         text-transform:uppercase;letter-spacing:0.10em;
                         font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                BOTTOM LINE
            </span>
            <p style="font-size:0.88rem;color:#1a202c;margin:5px 0 0;font-weight:600;
                      line-height:1.55;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
                {bottom_line}
            </p>
        </div>
    </div>
    """

    return article_html, subject


def _build_watchlist_html(
    items: list[dict],
    narrative: str | None = None,
    *,
    portfolio_mode: bool = False,
) -> str:
    """
    Build personalised portfolio intelligence with a watchlist fallback.
    items:     [{ticker, name, score, case, delta, aligned, total_relevant, weight_pct}]
               max 5 items expected.
    narrative: optional AI-generated 2-3 sentence plain-English summary.
    """
    CASE_COLOR = {"BULL": "#00875A", "BEAR": "#C53030", "NEUTRAL": "#5A6472"}
    CASE_BG    = {"BULL": "#F0FDF4", "BEAR": "#FFF5F5", "NEUTRAL": "#F7F8FA"}
    CASE_SYM   = {"BULL": "▲", "BEAR": "▼", "NEUTRAL": "●"}

    # ── AI narrative block ────────────────────────────────────────────────────
    narrative_html = ""
    if narrative:
        narrative_html = f"""
      <div style="border-left:3px solid #7C3AED;padding:10px 14px;margin-bottom:14px;
                  background:#F3F0FF;border-radius:0 6px 6px 0;">
        <p style="margin:0;font-size:0.86rem;color:#1F1235;line-height:1.65;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
          {_safe(narrative)}
        </p>
      </div>"""

    # ── Score cards ───────────────────────────────────────────────────────────
    cards = ""
    col_width = f"{100 // len(items)}%" if items else "33%"
    for item in items:
        case   = item.get("case", "NEUTRAL")
        color  = CASE_COLOR.get(case, "#5A6472")
        bg     = CASE_BG.get(case, "#F7F8FA")
        sym    = CASE_SYM.get(case, "●")
        score  = item["score"]
        delta  = item.get("delta")
        delta_str = (
            f'<span style="font-size:0.72rem;color:{"#00875A" if delta >= 0 else "#C53030"};'
            f'font-weight:700;">{("+" if delta >= 0 else "")}{delta:.1f} 7d</span>'
            if delta is not None else ""
        )
        ticker = _safe(item["ticker"])
        item_name = str(item.get("name", item["ticker"]))
        name_short = item_name[:22] + "…" if len(item_name) > 24 else item_name
        name_short = _safe(name_short)
        weight = max(0.0, float(item.get("weight_pct") or 0))
        weight_str = (
            f'<div style="font-size:0.62rem;color:#4B5563;margin-top:4px;">'
            f'{weight:.1f}% of portfolio</div>'
            if portfolio_mode and weight > 0 else ""
        )

        # Conviction: signal alignment badge
        aligned   = item.get("aligned", 0)
        total_rel = item.get("total_relevant", 0)
        if total_rel > 0:
            align_pct   = aligned / total_rel
            align_color = (
                "#00875A" if align_pct >= 0.70 else
                "#D97706" if align_pct >= 0.50 else
                "#C53030"
            )
            conviction_str = (
                f'<div style="font-size:0.62rem;color:{align_color};margin-top:4px;'
                f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
                f'{aligned}/{total_rel} signals aligned</div>'
            )
        else:
            conviction_str = ""

        cards += f"""
        <td style="width:{col_width};padding:0 6px;vertical-align:top;">
          <div style="background:{bg};border:1px solid {color}33;border-radius:6px;
                      padding:12px 10px;text-align:center;">
            <div style="font-size:1.1rem;font-weight:800;color:#0f1119;margin-bottom:2px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
              {ticker}
            </div>
            <div style="font-size:0.65rem;color:#6B7280;margin-bottom:8px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
              {name_short}
            </div>
            <div style="font-size:1.6rem;font-weight:900;color:{color};line-height:1;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
              {score:.0f}
            </div>
            <div style="font-size:0.65rem;color:#6B7280;margin-top:1px;margin-bottom:6px;
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
              / 100
            </div>
            <div style="font-size:0.72rem;font-weight:700;color:{color};
                        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
              {sym} {case}
            </div>
            <div style="margin-top:4px;">{delta_str}</div>
            {weight_str}
            {conviction_str}
            <div style="margin-top:9px;">
              <a href="{_APP_URL}/ticker-deep-dive?ticker={ticker}"
                 style="font-size:0.68rem;color:#5B21B6;text-decoration:none;font-weight:700;">
                Open research →
              </a>
            </div>
          </div>
        </td>"""

    # Explain the Move — one deterministic "why" for the biggest watchlist mover,
    # reusing the shared attribution engine. Full-width so it isn't cramped inside
    # the narrow score cards; safe/silent if there's no snapshot history yet.
    why_block = ""
    try:
        from utils.score_history import explain_move
        _mover = max((it for it in items if it.get("delta") is not None),
                     key=lambda it: abs(it["delta"]), default=None)
        if _mover and abs(_mover.get("delta", 0)) >= 3.0:
            _a = explain_move(_mover["ticker"], days_back=7)
            if _a.get("state") in ("ok", "insufficient_coverage") and _a.get("summary"):
                why_block = (
                    '<div style="margin-top:12px;padding:10px 14px;background:#FFFFFF;'
                    'border:1px solid #E5E7EB;border-radius:6px;font-size:0.78rem;'
                    "color:#374151;line-height:1.6;font-family:-apple-system,BlinkMacSystemFont,"
                    "'Segoe UI',sans-serif;\">"
                    f'<span style="font-weight:700;color:#7C3AED;">Why {_safe(_mover["ticker"])} moved:</span> '
                    f'{_safe(_a["summary"])}</div>'
                )
    except Exception:
        why_block = ""

    section_title = "Your Portfolio Intelligence" if portfolio_mode else "Your Watchlist Intelligence"
    action_url = f"{_APP_URL}/portfolio-suite" if portfolio_mode else f"{_APP_URL}/my-watchlist"
    action_label = "Open Portfolio Intelligence →" if portfolio_mode else "Open Watchlist →"

    return f"""
    <div style="background:#F7F8FA;border-top:3px solid #7C3AED;padding:16px 24px 12px;">
      <div style="font-size:0.60rem;font-weight:700;color:#7C3AED;text-transform:uppercase;
                  letter-spacing:0.12em;margin-bottom:12px;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
        {section_title}
      </div>
      {narrative_html}
      <table style="border-collapse:collapse;width:100%;">
        <tr>{cards}</tr>
      </table>
      {why_block}
      <div style="margin-top:10px;text-align:right;">
        <a href="{action_url}"
           style="font-size:0.72rem;color:#7C3AED;text-decoration:none;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
          {action_label}
        </a>
      </div>
    </div>
    """


def _build_catalyst_digest_html(items: list[dict] | None) -> str:
    """Render a compact, escaped catalyst agenda for the morning brief."""
    if not items:
        return ""
    rows = ""
    for item in items[:4]:
        review_due = item.get("delivery_type") == "review_due"
        days = int(item.get("days_until", 0))
        if review_due:
            timing = f'Review due · {int(item.get("days_overdue", abs(days)))}d after event'
            accent = "#D97706"
            detail = "Compare the saved scenario with the outcome while the evidence is fresh."
        else:
            timing = "Today" if days == 0 else "Tomorrow" if days == 1 else f"In {days} days"
            accent = "#7C3AED"
            weight = max(0.0, float(item.get("affected_weight") or 0))
            tickers = ", ".join(str(value) for value in (item.get("affected_tickers") or [])[:5])
            detail_parts = []
            if weight:
                detail_parts.append(f"{weight:.1f}% portfolio weight")
            if tickers:
                detail_parts.append(tickers)
            if item.get("is_estimate"):
                detail_parts.append("provisional date")
            detail = " · ".join(detail_parts) or "Portfolio event"

        plan_badge = (
            '<span style="color:#00875A;font-weight:700;">Plan saved</span>'
            if item.get("plan_saved") else
            '<span style="color:#6B7280;">No plan yet</span>'
        )
        watch_for = str(item.get("watch_for") or "").strip()
        watch_html = (
            f'<div style="font-size:0.70rem;color:#4B5563;margin-top:4px;">'
            f'Watch: {_safe(watch_for[:160])}</div>'
            if watch_for else ""
        )
        rows += f"""
        <div style="border-left:3px solid {accent};padding:9px 12px;margin-bottom:8px;
                    background:#FFFFFF;border-radius:0 6px 6px 0;">
          <table style="width:100%;border-collapse:collapse;"><tr>
            <td style="vertical-align:top;">
              <div style="font-size:0.82rem;font-weight:750;color:#111827;">{_safe(item.get('title', 'Catalyst'))}</div>
              <div style="font-size:0.70rem;color:#6B7280;margin-top:2px;">{_safe(detail)}</div>
              {watch_html}
            </td>
            <td style="text-align:right;vertical-align:top;white-space:nowrap;padding-left:12px;">
              <div style="font-size:0.72rem;font-weight:700;color:{accent};">{_safe(timing)}</div>
              <div style="font-size:0.66rem;margin-top:4px;">{plan_badge}</div>
            </td>
          </tr></table>
        </div>"""

    return f"""
    <div style="background:#F8F7FF;border-top:1px solid #E9E5FF;padding:16px 24px 12px;">
      <div style="font-size:0.60rem;font-weight:700;color:#7C3AED;text-transform:uppercase;
                  letter-spacing:0.12em;margin-bottom:10px;">Your Catalyst Agenda</div>
      {rows}
      <div style="margin-top:9px;text-align:right;">
        <a href="{_APP_URL}/events-forecasts" style="font-size:0.72rem;color:#7C3AED;
           text-decoration:none;font-weight:700;">Open Catalyst Command Center →</a>
      </div>
    </div>"""


def send_digest_email(
    to_email: str,
    signal_flips: list[dict],
    score_movers: list[dict],
    overall_bias: str,
    bull_n: int,
    bear_n: int,
    neut_n: int,
    unavailable_n: int = 0,
    signal_scores: dict | None = None,
    watchlist_items: list[dict] | None = None,
    watchlist_narrative: str | None = None,
    portfolio_mode: bool = False,
    catalyst_items: list[dict] | None = None,
) -> None:
    """
    Send the morning intelligence digest to a single opted-in user.
    Called by cron/send_digest.py for each opted-in user.

    signal_flips:       list of {signal_id, from_status, to_status, to_score} dicts
    score_movers:       list of {ticker, from_score, to_score, delta, case} dicts
    overall_bias:       "Bullish", "Bearish", or "Mixed"
    bull_n / bear_n / neut_n: current live signal counts
    unavailable_n: sources excluded because the live fetch was unavailable
    signal_scores:      {sig_id: {name, score, status}} — used for the article section.
                        Optional for backward compat; article is skipped if None.
    watchlist_items:    [{ticker, name, score, case, delta}] — personalised section.
                        None = no watchlist section (user has empty watchlist).
    watchlist_narrative: AI-generated 2-3 sentence plain-English summary of the user's
                        watchlist relative to today's macro environment. None = omitted.
    portfolio_mode:      render holdings, weights, and the Portfolio Intelligence CTA.
                         False preserves the watchlist fallback and older callers.
    catalyst_items:      near-term weighted events and overdue saved-plan reviews.
    """
    api_key, from_email = _get_resend_config()
    print(f"[digest] send_digest_email: to={to_email!r} bias={overall_bias}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    from datetime import date
    today_str = date.today().strftime("%B %-d, %Y")
    live_n = bull_n + bear_n + neut_n
    configured_n = live_n + unavailable_n
    coverage_text = f"{live_n}/{configured_n} live sources loaded" if configured_n else "No live sources loaded"
    if unavailable_n:
        coverage_text += f" · {unavailable_n} unavailable excluded"

    # ── Personalised portfolio section (watchlist fallback) ──────────────
    watchlist_html = (
        _build_watchlist_html(
            watchlist_items,
            narrative=watchlist_narrative,
            portfolio_mode=portfolio_mode,
        )
        if watchlist_items else ""
    )
    catalyst_html = _build_catalyst_digest_html(catalyst_items)

    # ── Seeking Alpha-style macro article ──────────────────────────────────
    if signal_scores:
        article_html, subject_line = _build_article_html(
            signal_scores=signal_scores,
            signal_flips=signal_flips,
            bias=overall_bias,
            bull_n=bull_n,
            bear_n=bear_n,
            neut_n=neut_n,
            date_str=today_str,
        )
    else:
        article_html = ""
        subject_line = f"UA Morning Brief — {today_str}"

    # ── Signal flips table ─────────────────────────────────────────────────
    FLIP_COLOR = {"bullish": "#00875A", "bearish": "#C53030",
                  "neutral": "#5A6472", "insufficient_data": "#9E9E9E"}
    FLIP_SYM   = {"bullish": "▲", "bearish": "▼",
                  "neutral": "●", "insufficient_data": "○"}

    if signal_flips:
        flip_rows = ""
        for f in signal_flips[:6]:
            from_c = FLIP_COLOR.get(f["from_status"], "#9E9E9E")
            to_c   = FLIP_COLOR.get(f["to_status"],   "#9E9E9E")
            from_s = FLIP_SYM.get(f["from_status"], "●")
            to_s   = FLIP_SYM.get(f["to_status"],   "●")
            flip_rows += (
                f'<tr style="border-bottom:1px solid #F0F0F0;">'
                f'<td style="padding:7px 8px;font-size:0.83rem;color:#1a202c;'
                f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
                f'{f.get("signal_name", f.get("signal_id",""))}</td>'
                f'<td style="padding:7px 8px;color:{from_c};font-size:0.83rem;white-space:nowrap;">'
                f'{from_s} {f["from_status"].title()}</td>'
                f'<td style="padding:7px 4px;color:#9E9E9E;font-size:1rem;">→</td>'
                f'<td style="padding:7px 8px;font-weight:700;color:{to_c};'
                f'font-size:0.83rem;white-space:nowrap;">'
                f'{to_s} {f["to_status"].title()}</td>'
                f'</tr>'
            )
        flips_html = f"""
        <div style="font-size:0.60rem;font-weight:700;color:#4A5568;text-transform:uppercase;
                    letter-spacing:0.10em;margin-bottom:10px;padding:0 24px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            {len(signal_flips)} Signal Flip{"s" if len(signal_flips) != 1 else ""} Since Yesterday
        </div>
        <table style="border-collapse:collapse;width:100%;margin-bottom:4px;">
            {flip_rows}
        </table>
        """
    else:
        flips_html = """
        <div style="font-size:0.60rem;font-weight:700;color:#4A5568;text-transform:uppercase;
                    letter-spacing:0.10em;margin-bottom:8px;padding:0 24px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            Signal Flips
        </div>
        <p style="font-size:0.83rem;color:#6B7280;padding:0 24px;margin:0 0 4px;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            No status changes since yesterday — signals are holding steady.
        </p>
        """

    # ── Score movers table ─────────────────────────────────────────────────
    if score_movers:
        mover_rows = ""
        for m in score_movers[:5]:
            delta = m["delta"]
            dc = "#00875A" if delta > 0 else "#C53030"
            ds = f"+{delta:.1f}" if delta > 0 else f"{delta:.1f}"
            case = m.get("case", "")
            case_color = "#00875A" if case == "BULL" else ("#C53030" if case == "BEAR" else "#5A6472")
            mover_rows += (
                f'<tr style="border-bottom:1px solid #F0F0F0;">'
                f'<td style="padding:7px 8px;font-weight:700;font-size:0.88rem;color:#0f1119;'
                f'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;">'
                f'{m["ticker"]}</td>'
                f'<td style="padding:7px 8px;color:#6B7280;font-size:0.83rem;">'
                f'{m["from_score"]:.0f} → {m["to_score"]:.0f}</td>'
                f'<td style="padding:7px 8px;font-weight:700;color:{dc};font-size:0.83rem;">{ds}</td>'
                f'<td style="padding:7px 8px;color:{case_color};font-size:0.78rem;font-weight:600;">'
                f'{case}</td>'
                f'</tr>'
            )
        movers_html = f"""
        <div style="font-size:0.60rem;font-weight:700;color:#4A5568;text-transform:uppercase;
                    letter-spacing:0.10em;margin-bottom:10px;padding:0 24px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            Biggest Score Movers (7 days)
        </div>
        <table style="border-collapse:collapse;width:100%;margin-bottom:4px;">
            <tr style="background:#F7F8FA;">
                <th style="padding:5px 8px;text-align:left;font-size:0.65rem;color:#6B7280;
                           font-weight:600;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">TICKER</th>
                <th style="padding:5px 8px;text-align:left;font-size:0.65rem;color:#6B7280;font-weight:600;">SCORE</th>
                <th style="padding:5px 8px;text-align:left;font-size:0.65rem;color:#6B7280;font-weight:600;">7D Δ</th>
                <th style="padding:5px 8px;text-align:left;font-size:0.65rem;color:#6B7280;font-weight:600;">CASE</th>
            </tr>
            {mover_rows}
        </table>
        """
    else:
        movers_html = """
        <div style="font-size:0.60rem;font-weight:700;color:#4A5568;text-transform:uppercase;
                    letter-spacing:0.10em;margin-bottom:8px;padding:0 24px;
                    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            Score Movers
        </div>
        <p style="font-size:0.83rem;color:#6B7280;padding:0 24px;margin:0 0 4px;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
            Score history builds as tickers get viewed — check back as the platform gets more traffic.
        </p>
        """

    # ── Bias banner ────────────────────────────────────────────────────────
    bias_color  = "#00875A" if overall_bias == "Bullish" else ("#C53030" if overall_bias == "Bearish" else "#5A6472")
    bias_bg     = "#F0FDF4" if overall_bias == "Bullish" else ("#FFF5F5" if overall_bias == "Bearish" else "#F7F8FA")

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#F0F2F5;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
  {_safe(overall_bias)} signal pulse · {_safe(coverage_text)} · {"weighted portfolio" if portfolio_mode else "personalised watchlist"} intelligence
</div>
<div style="max-width:600px;margin:0 auto;background:#ffffff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">

    <!-- Header -->
    <div style="background:#0f1119;padding:20px 24px;">
        <table style="width:100%;border-collapse:collapse;">
            <tr>
                <td>
                    <div style="font-size:0.60rem;color:#7C3AED;text-transform:uppercase;
                                letter-spacing:0.14em;margin-bottom:4px;">
                        UNSTRUCTURED ALPHA
                    </div>
                    <div style="font-size:1.1rem;font-weight:700;color:#E8EEFF;">
                        Morning Intelligence Brief
                    </div>
                </td>
                <td style="text-align:right;vertical-align:middle;">
                    <div style="font-size:0.75rem;color:#8892AA;">{today_str}</div>
                </td>
            </tr>
        </table>
    </div>

    <div style="padding:8px 24px;background:#FFFFFF;border-bottom:1px solid #E5E7EB;
                font-size:0.70rem;color:#6B7280;">
        {_safe(coverage_text)}. Unavailable sources are not scored or treated as neutral.
    </div>

    <!-- Signal Pulse Banner -->
    <div style="background:{bias_bg};padding:12px 24px;border-left:5px solid {bias_color};">
        <table style="border-collapse:collapse;width:100%;">
            <tr>
                <td>
                    <div style="font-size:0.60rem;color:{bias_color};text-transform:uppercase;
                                letter-spacing:0.10em;margin-bottom:3px;">Signal Pulse</div>
                    <div style="font-size:1.2rem;font-weight:800;color:{bias_color};">
                        {overall_bias}
                    </div>
                </td>
                <td style="text-align:right;vertical-align:middle;">
                    <span style="font-size:0.80rem;color:#4A5568;">
                        <span style="color:#00875A;font-weight:700;">▲ {bull_n}</span> &nbsp;
                        <span style="color:#C53030;font-weight:700;">▼ {bear_n}</span> &nbsp;
                        <span style="color:#6B7280;">● {neut_n}</span>
                    </span>
                </td>
            </tr>
        </table>
    </div>

    <!-- Personalised portfolio intelligence with watchlist fallback -->
    {watchlist_html}

    <!-- Verified portfolio catalysts and saved-plan review prompts -->
    {catalyst_html}

    <!-- Article -->
    {article_html}

    <!-- Divider -->
    <div style="height:1px;background:#E2E8F0;margin:0 24px;"></div>

    <!-- Data Tables -->
    <div style="padding:20px 24px;">
        {flips_html}
        <div style="height:20px;"></div>
        {movers_html}
    </div>

    <!-- CTA -->
    <div style="padding:4px 24px 28px;text-align:center;">
        <a href="{_APP_URL}/today-s-brief"
           style="display:inline-block;background:#7C3AED;color:#ffffff;
                  padding:12px 28px;border-radius:6px;text-decoration:none;
                  font-size:0.9rem;font-weight:700;">
            Open Full Brief →
        </a>
    </div>

    <!-- Footer -->
    <div style="background:#0f1119;padding:14px 24px;border-radius:0 0 4px 4px;">
        <p style="font-size:0.68rem;color:#6B7280;text-align:center;margin:0;">
            Unstructured Alpha · app.unstructuredalpha.com · Not financial advice · Live public-source data<br>
            <a href="{_APP_URL}/my-watchlist"
               style="color:#7C3AED;text-decoration:none;">Manage preferences</a>
        </p>
    </div>

</div>
</body>
</html>"""

    try:
        resp = _post_resend_email(
            api_key=api_key,
            from_email=from_email,
            to_email=to_email,
            subject=subject_line,
            html=html,
            email_type="morning_digest",
            idempotency_key=f"morning-digest/{date.today().isoformat()}/{_recipient_token(to_email)}",
            timeout=20,
        )
        print(f"[digest] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[digest] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send digest to {to_email}: {e}") from e


def send_trial_reminder_email(to_email: str, trial_end_display: str) -> None:
    """
    Send a "your trial ends tomorrow" nudge email to a user on day 6 of their
    7-day free trial. Called by cron/send_trial_reminder.py.

    trial_end_display: human-readable date string, e.g. "July 1, 2026"
    """
    api_key, from_email = _get_resend_config()
    print(f"[trial-reminder] sending to={to_email!r} trial_end={trial_end_display!r}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    html = f"""
    <div style="font-family:Georgia,serif;max-width:540px;color:#1A1612;">
        <div style="background:#1C2B4A;padding:18px 24px;border-radius:8px 8px 0 0;">
            <div style="font-size:0.70rem;color:#C9A84C;letter-spacing:0.12em;text-transform:uppercase;">
                Unstructured Alpha
            </div>
            <div style="font-size:1.2rem;font-weight:700;color:#FAF7F0;margin-top:4px;">
                Your free trial ends tomorrow
            </div>
        </div>

        <div style="background:#FFFFFF;padding:24px 24px;">
            <p style="font-size:1rem;color:#1A1612;margin:0 0 16px;">
                Your 7-day Pro trial wraps up on <strong>{trial_end_display}</strong>.
            </p>
            <p style="font-size:0.9rem;color:#4A4A4A;margin:0 0 16px;">
                After that, you'll move to the Free plan — you'll keep your account and
                watchlist, but lose access to:
            </p>
            <ul style="color:#4A4A4A;font-size:0.9rem;padding-left:20px;margin:0 0 20px;">
                <li>Factor Exposure — Fama-French regression for any ticker</li>
                <li>PDF Research Reports</li>
                <li>Signal Backtester</li>
                <li>Portfolio Analyzer</li>
                <li>Options Flow</li>
                <li>Morning digest email</li>
            </ul>
            <p style="font-size:0.9rem;color:#4A4A4A;margin:0 0 24px;">
                Keep access by adding a payment method before your trial ends.
                No charge until <strong>{trial_end_display}</strong>.
            </p>
            <div style="text-align:center;">
                <a href="https://unstructuredalpha.com/Upgrade"
                   style="background:linear-gradient(90deg,#7C3AED,#00C8E0);color:#fff;
                          padding:12px 28px;border-radius:6px;text-decoration:none;
                          font-size:0.95rem;font-weight:700;display:inline-block;">
                    Continue with Pro →
                </a>
            </div>
        </div>

        <div style="background:#F0EBE1;padding:10px 24px;border-radius:0 0 8px 8px;
                    font-size:0.72rem;color:#9E9E8E;text-align:center;">
            Unstructured Alpha · unstructuredalpha.com<br>
            Questions? Just reply to this email.
        </div>
    </div>
    """

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "Your Unstructured Alpha trial ends tomorrow",
                "html": html,
            },
            timeout=15,
        )
        print(f"[trial-reminder] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[trial-reminder] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send trial reminder to {to_email}: {e}") from e


def send_welcome_email(to_email: str) -> None:
    """
    Send a day-0 welcome email immediately after a user verifies their email
    address. Goal: warm, useful, one clear CTA (open the dashboard).
    Called by auth.verify_email() in a try/except so it never blocks
    the verification flow.
    """
    api_key, from_email = _get_resend_config()
    print(f"[welcome] sending to={to_email!r}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    html = """
    <div style="font-family:Georgia,serif;max-width:540px;color:#1A1612;">
        <div style="background:#1C2B4A;padding:20px 28px;border-radius:8px 8px 0 0;">
            <div style="font-size:0.70rem;color:#C9A84C;letter-spacing:0.12em;text-transform:uppercase;">
                Unstructured Alpha
            </div>
            <div style="font-size:1.3rem;font-weight:700;color:#FAF7F0;margin-top:6px;">
                Your account is ready.
            </div>
        </div>

        <div style="background:#FFFFFF;padding:28px 28px 24px;">
            <p style="font-size:1rem;color:#1A1612;margin:0 0 18px;line-height:1.6;">
                Welcome. Unstructured Alpha scores 28 macro and alternative data signals
                daily — credit spreads, energy inventories, Fed liquidity, insider activity,
                options flow — and tells you what they're saying about the market right now.
            </p>

            <p style="font-size:0.9rem;color:#4A4A4A;margin:0 0 6px;font-weight:700;">
                Start here:
            </p>
            <ul style="color:#4A4A4A;font-size:0.9rem;padding-left:20px;margin:0 0 24px;line-height:1.8;">
                <li>
                    <a href="https://unstructuredalpha.com/Today%27s_Brief"
                       style="color:#1C2B4A;font-weight:700;">Today's Brief</a>
                    — daily signal pulse with what flipped overnight
                </li>
                <li>
                    <a href="https://unstructuredalpha.com/Ticker_Deep_Dive"
                       style="color:#1C2B4A;font-weight:700;">Ticker Deep Dive</a>
                    — type any stock ticker to see which signals are driving it
                </li>
                <li>
                    <a href="https://unstructuredalpha.com/Watchlist"
                       style="color:#1C2B4A;font-weight:700;">Watchlist</a>
                    — track your stocks and set alerts
                </li>
            </ul>

            <div style="text-align:center;">
                <a href="https://unstructuredalpha.com"
                   style="background:#1C2B4A;color:#FAF7F0;padding:13px 30px;
                          border-radius:5px;text-decoration:none;
                          font-size:0.95rem;font-weight:700;display:inline-block;">
                    Open the Dashboard →
                </a>
            </div>

            <p style="font-size:0.82rem;color:#8B8B8B;margin:24px 0 0;line-height:1.5;">
                You're on the <strong>Free plan</strong>. Upgrade to Pro anytime for
                factor exposure, PDF reports, the signal backtester, and the morning
                digest email.
                <a href="https://unstructuredalpha.com/Upgrade"
                   style="color:#1C2B4A;">See what's included →</a>
            </p>
        </div>

        <div style="background:#F0EBE1;padding:10px 28px;border-radius:0 0 8px 8px;
                    font-size:0.72rem;color:#9E9E8E;text-align:center;">
            Unstructured Alpha · Not financial advice · All data from public sources
        </div>
    </div>
    """

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "Welcome to Unstructured Alpha",
                "html": html,
            },
            timeout=15,
        )
        print(f"[welcome] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[welcome] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send welcome email to {to_email}: {e}") from e


def send_watchlist_alert_email(to_email: str, new_alerts: list[dict]) -> None:
    """
    Send a watchlist threshold-crossing alert email to a single user.
    Called by cron/send_watchlist_alerts.py for every user who has new alerts
    since the last evaluation.

    new_alerts: list of alert dicts from evaluate_watchlist(), each with at
    minimum: ticker (str), alert_type (str), direction (str), message (str).
    """
    api_key, from_email = _get_resend_config()
    print(f"[watchlist-alert] sending to={to_email!r} n_alerts={len(new_alerts)}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")
    if not new_alerts:
        return

    from datetime import date
    today_str = date.today().strftime("%B %-d, %Y")

    DIRECTION_COLOR = {"bullish": "#047857", "bearish": "#B91C1C"}
    DIRECTION_ICON = {"bullish": "▲", "bearish": "▼"}
    ALERT_LABELS = {
        "score_bull": "Confluence threshold",
        "score_bear": "Confluence threshold",
        "price_move": "Material price move",
        "52w_high": "New 52-week high",
        "52w_low": "New 52-week low",
        "signal_change": "Differentiator change",
        "screen_entry": "Saved screen entrant",
    }

    alert_rows = ""
    for a in new_alerts[:10]:                       # cap at 10 in the email
        ticker    = _safe(a.get("ticker", "???").upper())
        direction = (a.get("direction") or "neutral").lower()
        message   = _safe(a.get("message", "Threshold crossed."))
        alert_label = _safe(ALERT_LABELS.get(a.get("alert_type"), "Watchlist trigger"))
        color     = DIRECTION_COLOR.get(direction, "#8892AA")
        icon      = DIRECTION_ICON.get(direction, "●")
        alert_rows += f"""
        <tr>
          <td style="padding:14px 16px;border-bottom:1px solid #E5E7EB;">
            <div style="font-size:0.66rem;font-weight:700;color:#6B7280;text-transform:uppercase;
                        letter-spacing:0.08em;margin-bottom:4px;">{alert_label}</div>
            <div style="font-size:0.96rem;font-weight:800;color:#111827;
                        font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
              <span style="color:{color};margin-right:6px;">{icon}</span>{ticker}
            </div>
            <div style="font-size:0.80rem;color:#4B5563;margin-top:4px;line-height:1.55;
                        font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
              {message}
            </div>
            <a href="{_APP_URL}/ticker-deep-dive?ticker={ticker}"
               style="display:inline-block;margin-top:8px;font-size:0.72rem;color:#5B21B6;
                      font-weight:700;text-decoration:none;">Review the full research →</a>
          </td>
          <td style="padding:14px 16px;border-bottom:1px solid #E5E7EB;
                     text-align:right;vertical-align:top;white-space:nowrap;">
            <span style="color:{color};font-size:0.78rem;font-weight:700;
                         font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
                         text-transform:uppercase;letter-spacing:0.04em;">
              {direction.title()}
            </span>
          </td>
        </tr>"""

    n      = len(new_alerts)
    plural = "s" if n != 1 else ""
    tickers_short = ", ".join(sorted({_safe(a.get("ticker", "???").upper()) for a in new_alerts[:4]}))
    if n > 4:
        tickers_short += f" +{n - 4} more"

    _all_screen_entries = all(a.get("alert_type") == "screen_entry" for a in new_alerts)
    _has_screen_entries = any(a.get("alert_type") == "screen_entry" for a in new_alerts)
    _alert_name = "Saved Screen Alert" if _all_screen_entries else (
        "Research Alert" if _has_screen_entries else "Watchlist Alert"
    )
    _header_label = "SAVED SCREENS" if _all_screen_entries else (
        "RESEARCH ALERTS" if _has_screen_entries else "WATCHLIST"
    )
    _cta_url = f"{_APP_URL}/stock-recommender" if _all_screen_entries else f"{_APP_URL}/my-watchlist"
    _cta_label = "Open Stock Recommender" if _all_screen_entries else "Open Watchlist"
    subject = f"{n} {_alert_name}{plural}: {tickers_short}"
    alert_fingerprint = hashlib.sha256(
        "|".join(
            sorted(
                f"{a.get('ticker')}:{a.get('alert_type')}:{a.get('direction')}:{a.get('message')}"
                for a in new_alerts
            )
        ).encode("utf-8")
    ).hexdigest()[:20]

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#F3F4F6;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
  {_safe(tickers_short)} triggered a saved research condition. Review the evidence and next action.
</div>
<div style="max-width:560px;margin:0 auto;background:#FFFFFF;
            font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">

  <!-- Header -->
  <div style="background:#111827;padding:24px 28px;border-radius:8px 8px 0 0;
              border-top:4px solid #7C3AED;">
    <div style="font-size:0.60rem;color:#C4B5FD;letter-spacing:0.14em;
                text-transform:uppercase;margin-bottom:5px;">
      UNSTRUCTURED ALPHA · {_header_label}
    </div>
    <div style="font-size:1.4rem;font-weight:800;color:#FFFFFF;line-height:1.2;">
      {n} {_alert_name}{plural}
    </div>
    <div style="font-size:0.82rem;color:#B8C0D4;margin-top:6px;">
      {today_str} · {tickers_short}
    </div>
  </div>

  <!-- Alert table -->
  <div style="background:#FFFFFF;padding:8px 12px;">
    <table style="border-collapse:collapse;width:100%;">
      {alert_rows}
    </table>
  </div>

  <!-- CTA -->
  <div style="background:#F9FAFB;padding:22px 28px;text-align:center;">
    <a href="{_cta_url}"
       style="display:inline-block;background:#6D28D9;color:#FFFFFF;padding:12px 30px;border-radius:6px;
              text-decoration:none;font-size:0.9rem;font-weight:700;letter-spacing:0.02em;">
      {_cta_label} →
    </a>
  </div>

  <!-- Footer -->
  <div style="background:#111827;padding:14px 28px;border-radius:0 0 8px 8px;
              font-size:0.68rem;color:#9CA3AF;text-align:center;line-height:1.6;">
    Unstructured Alpha · app.unstructuredalpha.com · Not financial advice<br>
    <a href="{_cta_url}"
       style="color:#7C3AED;text-decoration:none;">Manage alert settings</a>
  </div>

</div>
</body>
</html>"""

    try:
        resp = _post_resend_email(
            api_key=api_key,
            from_email=from_email,
            to_email=to_email,
            subject=subject,
            html=html,
            email_type="watchlist_alert",
            idempotency_key=f"watchlist-alert/{_recipient_token(to_email)}/{alert_fingerprint}",
            timeout=15,
        )
        print(f"[watchlist-alert] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[watchlist-alert] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send watchlist alert to {to_email}: {e}") from e


def send_pro_welcome_email(to_email: str) -> None:
    """
    Send a rich onboarding email immediately after a user upgrades to Pro.
    Guides them to the highest-value Pro features so they get value on day 1.
    Called in a try/except so it never blocks the upgrade flow.
    """
    api_key, from_email = _get_resend_config()
    print(f"[pro-welcome] sending to={to_email!r}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    html = """
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;
                max-width:580px;margin:0 auto;background:#0B0D12;color:#E8EEFF;">

      <!-- Header -->
      <div style="background:linear-gradient(135deg,#7C3AED 0%,#0B0D12 100%);
                  padding:32px 32px 28px;border-radius:12px 12px 0 0;">
        <div style="font-size:0.65rem;color:#A78BFA;letter-spacing:0.14em;
                    text-transform:uppercase;margin-bottom:8px;">
          Unstructured Alpha · Pro
        </div>
        <div style="font-size:1.7rem;font-weight:800;color:#FFFFFF;line-height:1.2;">
          You're in. Here's where to start.
        </div>
        <div style="font-size:0.9rem;color:#C4B5FD;margin-top:10px;">
          Your Pro access is live — every signal, every tool, no paywalls.
        </div>
      </div>

      <!-- Intro -->
      <div style="background:#12151E;padding:28px 32px 8px;">
        <p style="font-size:0.95rem;color:#B8C0D4;line-height:1.7;margin:0 0 8px;">
          Most people open the dashboard and immediately go to the ticker they're
          watching. That's fine — but here's how to get the most out of the machine
          in the first week.
        </p>
      </div>

      <!-- Feature guide -->
      <div style="background:#12151E;padding:8px 32px 28px;">

        <!-- Item 1 -->
        <div style="border-left:3px solid #7C3AED;padding:14px 0 14px 18px;margin-bottom:20px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            Today's Brief — read this every morning
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            The daily signal pulse: what's bullish, what's bearish, what flipped
            overnight. Takes 60 seconds. Sets your macro frame for the day.
          </div>
          <a href="https://unstructuredalpha.com/Today%27s_Brief"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#A78BFA;text-decoration:none;font-weight:600;">
            Open Today's Brief →
          </a>
        </div>

        <!-- Item 2 -->
        <div style="border-left:3px solid #00D566;padding:14px 0 14px 18px;margin-bottom:20px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            🔍 Ticker Deep Dive — your most powerful tool
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            Type any ticker. You'll see the Confluence Score, which macro signals
            are driving it, an auto-explainer, insider cluster detection, a radar
            chart across 5 signal axes, and the full PDF export. This is the core.
          </div>
          <a href="https://unstructuredalpha.com/Ticker_Deep_Dive"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#00D566;text-decoration:none;font-weight:600;">
            Open Ticker Deep Dive →
          </a>
        </div>

        <!-- Item 3 -->
        <div style="border-left:3px solid #00C8E0;padding:14px 0 14px 18px;margin-bottom:20px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            PDF Export — institutional-quality reports
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            From any Ticker Deep Dive, hit "Export Full PDF Report." You get the
            full correlation-weighted score, all signal breakdowns, insider
            transactions, 13F institutional holders, and methodology notes —
            formatted and ready to share or archive.
          </div>
          <a href="https://unstructuredalpha.com/Export"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#00C8E0;text-decoration:none;font-weight:600;">
            Try PDF Export →
          </a>
        </div>

        <!-- Item 4 -->
        <div style="border-left:3px solid #F59E0B;padding:14px 0 14px 18px;margin-bottom:20px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            Short Squeeze Radar
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            Screens for tickers with high short interest + macro tailwinds +
            insider cluster buying. The combination that historically precedes
            sharp moves. Updated daily.
          </div>
          <a href="https://unstructuredalpha.com/Short_Squeeze_Radar"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#F59E0B;text-decoration:none;font-weight:600;">
            Open Radar →
          </a>
        </div>

        <!-- Item 5 -->
        <div style="border-left:3px solid #FF4444;padding:14px 0 14px 18px;margin-bottom:20px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            📈 Signal Backtester — build and test your own thesis
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            Pick any combination of signals and see how they would have
            performed historically on any ticker. Pro-only. Great for validating
            whether a setup you see today has actually worked before.
          </div>
          <a href="https://unstructuredalpha.com/Signal_Backtester"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#FF4444;text-decoration:none;font-weight:600;">
            Open Backtester →
          </a>
        </div>

        <!-- Item 6 -->
        <div style="border-left:3px solid #8892AA;padding:14px 0 14px 18px;margin-bottom:4px;">
          <div style="font-size:1rem;font-weight:700;color:#E8EEFF;margin-bottom:4px;">
            Watchlist & Alerts — let it come to you
          </div>
          <div style="font-size:0.88rem;color:#8892AA;line-height:1.6;">
            Add your tickers to the Watchlist and set score-threshold alerts.
            You'll get notified when a ticker crosses into bullish or bearish
            territory — without having to check manually.
          </div>
          <a href="https://unstructuredalpha.com/Watchlist"
             style="display:inline-block;margin-top:10px;font-size:0.82rem;
                    color:#8892AA;text-decoration:none;font-weight:600;">
            Set up Watchlist →
          </a>
        </div>

      </div>

      <!-- Morning digest opt-in nudge -->
      <div style="background:#0f1119;border:1px solid rgba(124,58,237,0.3);
                  border-radius:8px;margin:0 32px 24px;padding:18px 20px;">
        <div style="font-size:0.85rem;font-weight:700;color:#A78BFA;margin-bottom:6px;">
          📬 Morning Digest (Pro)
        </div>
        <div style="font-size:0.82rem;color:#8892AA;line-height:1.6;">
          Get a Seeking Alpha-style macro briefing in your inbox every morning at
          7 AM ET — signal pulse, what flipped, top movers, and an editorial
          take on the day's setup. Enable it in your
          <a href="https://unstructuredalpha.com/Watchlist"
             style="color:#A78BFA;">Watchlist settings</a>.
        </div>
      </div>

      <!-- CTA -->
      <div style="background:#12151E;padding:12px 32px 28px;text-align:center;">
        <a href="https://unstructuredalpha.com"
           style="display:inline-block;background:linear-gradient(135deg,#7C3AED,#00C8E0);
                  color:#FFFFFF;padding:14px 36px;border-radius:8px;
                  text-decoration:none;font-size:0.95rem;font-weight:700;
                  letter-spacing:0.02em;">
          Open Unstructured Alpha →
        </a>
      </div>

      <!-- Footer -->
      <div style="background:#0B0D12;padding:16px 32px;border-radius:0 0 12px 12px;
                  border-top:1px solid rgba(255,255,255,0.06);
                  font-size:0.70rem;color:#4A5280;text-align:center;line-height:1.6;">
        Unstructured Alpha · Pro Member<br>
        Not financial advice. All signals are statistical correlations, not predictions.<br>
        Questions? Reply to this email.
      </div>

    </div>
    """

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "You're Pro — here's where to start on Unstructured Alpha",
                "html": html,
            },
            timeout=15,
        )
        print(f"[pro-welcome] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[pro-welcome] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send Pro welcome email to {to_email}: {e}") from e


def send_referral_welcome_email(to_email: str) -> None:
    """
    Send a welcome email to a user who signed up via a referral link.
    Tells them they have a 14-day free trial (double the normal 7 days)
    and links to the Upgrade page to start it.

    Called best-effort from utils/referral.record_referral_signup() after
    the referral row is committed. Never raises externally — callers wrap
    in try/except; if Resend is not configured this is silently a no-op.
    """
    api_key, from_email = _get_resend_config()
    print(f"[referral-welcome] sending to={to_email!r}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    html = """<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0B0D12;">
<div style="max-width:560px;margin:0 auto;background:#12151E;
            font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#00C8E0 0%,#0B0D12 100%);
              padding:32px 32px 28px;border-radius:12px 12px 0 0;">
    <div style="font-size:0.62rem;color:#67E8F9;letter-spacing:0.14em;
                text-transform:uppercase;margin-bottom:8px;">
      Unstructured Alpha
    </div>
    <div style="font-size:1.6rem;font-weight:800;color:#FFFFFF;line-height:1.2;">
      A friend invited you.
    </div>
    <div style="font-size:0.92rem;color:#A5F3FC;margin-top:10px;">
      You have a 14-day free trial waiting — double the normal 7 days.
    </div>
  </div>

  <!-- Body -->
  <div style="background:#12151E;padding:28px 32px 8px;">
    <p style="font-size:0.95rem;color:#B8C0D4;line-height:1.75;margin:0 0 20px;">
      Someone who uses Unstructured Alpha thought you'd find it useful, so they sent
      you a link. Because of that, your free trial is <strong style="color:#E8EEFF;">14 days</strong> —
      twice what a direct signup gets.
    </p>

    <!-- Trial callout -->
    <div style="background:rgba(0,200,224,0.08);border:1px solid rgba(0,200,224,0.25);
                border-radius:8px;padding:16px 20px;margin-bottom:24px;">
      <div style="font-size:0.62rem;font-weight:700;color:#00C8E0;letter-spacing:0.12em;
                  text-transform:uppercase;margin-bottom:8px;">Your trial</div>
      <div style="display:flex;align-items:baseline;gap:8px;">
        <div style="font-size:2rem;font-weight:900;color:#00C8E0;line-height:1;">14</div>
        <div style="font-size:0.88rem;color:#8892AA;">days free · full Pro access</div>
      </div>
      <div style="font-size:0.78rem;color:#6B7A95;margin-top:6px;">
        Normal trial is 7 days. No extra charge — this is your referral benefit.
      </div>
    </div>

    <!-- What you can do -->
    <div style="font-size:0.62rem;font-weight:700;color:#8892AA;letter-spacing:0.10em;
                text-transform:uppercase;margin-bottom:14px;">What's included</div>

    <table style="border-collapse:collapse;width:100%;margin-bottom:24px;">
      <tr>
        <td style="padding:8px 12px 8px 0;vertical-align:top;width:28px;">
          <span style="color:#00D566;font-size:1rem;">▲</span>
        </td>
        <td style="padding:8px 0;">
          <div style="font-size:0.88rem;font-weight:700;color:#E8EEFF;">
            Ticker Deep Dive
          </div>
          <div style="font-size:0.80rem;color:#8892AA;margin-top:2px;line-height:1.5;">
            Confluence Score for any stock — 28 macro + alt-data signals scored and explained
          </div>
        </td>
      </tr>
      <tr>
        <td style="padding:8px 12px 8px 0;vertical-align:top;">
          <span style="color:#7C3AED;font-size:1rem;">◈</span>
        </td>
        <td style="padding:8px 0;">
          <div style="font-size:0.88rem;font-weight:700;color:#E8EEFF;">
            Morning Digest
          </div>
          <div style="font-size:0.80rem;color:#8892AA;margin-top:2px;line-height:1.5;">
            Daily macro briefing in your inbox — what flipped overnight and what it means
          </div>
        </td>
      </tr>
      <tr>
        <td style="padding:8px 12px 8px 0;vertical-align:top;">
          <span style="color:#F59E0B;font-size:1rem;">ALERT</span>
        </td>
        <td style="padding:8px 0;">
          <div style="font-size:0.88rem;font-weight:700;color:#E8EEFF;">
            Short Squeeze Radar + PDF Reports
          </div>
          <div style="font-size:0.80rem;color:#8892AA;margin-top:2px;line-height:1.5;">
            Screen for macro-backed squeeze setups · export institutional-grade PDF research
          </div>
        </td>
      </tr>
    </table>
  </div>

  <!-- CTA -->
  <div style="background:#0f1119;padding:24px 32px;text-align:center;">
    <a href="https://unstructuredalpha.com/Upgrade"
       style="display:inline-block;background:linear-gradient(135deg,#00C8E0,#7C3AED);
              color:#FFFFFF;padding:14px 36px;border-radius:8px;
              text-decoration:none;font-size:0.95rem;font-weight:700;
              letter-spacing:0.02em;">
      Start Your 14-Day Free Trial →
    </a>
    <div style="font-size:0.75rem;color:#6B7A95;margin-top:10px;">
      Full Pro access · No charge for 14 days
    </div>
  </div>

  <!-- Footer -->
  <div style="background:#0B0D12;padding:16px 32px;border-radius:0 0 12px 12px;
              border-top:1px solid rgba(255,255,255,0.06);
              font-size:0.70rem;color:#4A5280;text-align:center;line-height:1.6;">
    Unstructured Alpha · unstructuredalpha.com<br>
    Not financial advice. All signals are statistical correlations from public data sources.
  </div>

</div>
</body>
</html>"""

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "You've been invited — your 14-day free trial is waiting",
                "html": html,
            },
            timeout=15,
        )
        print(f"[referral-welcome] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[referral-welcome] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send referral welcome email to {to_email}: {e}") from e


def send_password_reset_email(to_email: str, code: str) -> None:
    """
    Send a 6-digit password reset code to to_email. Raises EmailSendError
    if RESEND_API_KEY isn't configured or Resend's API rejects the request.
    """
    api_key, from_email = _get_resend_config()
    print(f"[password-reset] sending to={to_email!r}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0B0D12;">
<div style="max-width:520px;margin:0 auto;background:#12151E;
            font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">

  <!-- Header -->
  <div style="background:#0f1119;padding:24px 28px;border-radius:12px 12px 0 0;
              border-bottom:1px solid rgba(255,255,255,0.06);">
    <div style="font-size:0.60rem;color:#8892AA;letter-spacing:0.14em;
                text-transform:uppercase;margin-bottom:4px;">
      Unstructured Alpha
    </div>
    <div style="font-size:1.25rem;font-weight:700;color:#E8EEFF;">
      Reset your password
    </div>
  </div>

  <!-- Body -->
  <div style="padding:28px 32px;">
    <p style="font-size:0.92rem;color:#B8C0D4;line-height:1.7;margin:0 0 24px;">
      Use the code below to reset your Unstructured Alpha password.
      It expires in <strong style="color:#E8EEFF;">15 minutes</strong>.
    </p>

    <!-- Code block -->
    <div style="background:#0f1119;border:1px solid rgba(255,255,255,0.08);
                border-radius:8px;padding:20px;text-align:center;margin-bottom:24px;">
      <div style="font-size:0.62rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;
                  text-transform:uppercase;margin-bottom:12px;">
        Your reset code
      </div>
      <div style="font-size:2.4rem;font-weight:800;color:#E8EEFF;letter-spacing:0.25em;
                  font-variant-numeric:tabular-nums;">
        {code}
      </div>
    </div>

    <p style="font-size:0.82rem;color:#6B7A95;line-height:1.6;margin:0;">
      If you didn't request a password reset, you can safely ignore this email —
      your account has not been changed.
    </p>
  </div>

  <!-- Footer -->
  <div style="background:#0B0D12;padding:14px 28px;border-radius:0 0 12px 12px;
              border-top:1px solid rgba(255,255,255,0.06);
              font-size:0.68rem;color:#4A5280;text-align:center;line-height:1.6;">
    Unstructured Alpha · unstructuredalpha.com · Not financial advice
  </div>

</div>
</body>
</html>"""

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": "Your Unstructured Alpha password reset code",
                "html": html,
            },
            timeout=15,
        )
        print(f"[password-reset] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[password-reset] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send password reset email to {to_email}: {e}") from e


def send_score_moved_email(to_email: str, moved: list[dict]) -> None:
    """
    Notify a user that one or more of their watched tickers has seen a
    meaningful confluence-score shift.

    ``moved`` is a list of dicts, each with:
        ticker        str   — e.g. "NVDA"
        old_score     float — last emailed baseline score
        new_score     float — current score
        delta         float — new_score - old_score (signed)

    Raises EmailSendError if RESEND_API_KEY is missing or the send fails.
    """
    if not moved:
        return

    api_key, from_email = _get_resend_config()
    print(
        f"[score-moved] sending to={to_email!r} tickers={[m['ticker'] for m in moved]}",
        flush=True,
    )
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    def _score_color(score: float) -> str:
        if score >= 65:
            return "#00D566"
        if score <= 35:
            return "#FF4D6A"
        return "#F59E0B"

    def _delta_arrow(delta: float) -> str:
        return "▲" if delta > 0 else "▼"

    def _delta_color(delta: float) -> str:
        return "#00D566" if delta > 0 else "#FF4D6A"

    # Build one row per ticker
    rows_html = ""
    for m in moved:
        ticker    = m["ticker"]
        old_s     = m["old_score"]
        new_s     = m["new_score"]
        delta     = m["delta"]
        arrow     = _delta_arrow(delta)
        acol      = _delta_color(delta)
        ncol      = _score_color(new_s)
        direction = "bullish" if delta > 0 else "bearish"
        # Explain the Move — the deterministic "why" behind the shift, reusing the
        # shared attribution engine. Turns an empty "69 → 54" alert into a reason.
        # Safe/silent if this ticker has no component-snapshot history yet.
        _why = ""
        try:
            from utils.score_history import explain_move
            _attr = explain_move(ticker, days_back=7)
            if _attr.get("state") in ("ok", "insufficient_coverage") and _attr.get("summary"):
                _why = _attr["summary"]
        except Exception:
            _why = ""
        why_html = (
            f'<div style="font-size:0.72rem;color:#8892AA;margin-top:6px;'
            f'line-height:1.5;max-width:210px;">{_why}</div>'
        ) if _why else ""
        rows_html += f"""
    <tr>
      <td style="padding:14px 0;border-bottom:1px solid rgba(255,255,255,0.06);vertical-align:middle;">
        <div style="font-size:1rem;font-weight:700;color:#E8EEFF;">{ticker}</div>
        <div style="font-size:0.72rem;color:#8892AA;margin-top:2px;text-transform:capitalize;">{direction}</div>
        {why_html}
      </td>
      <td style="padding:14px 8px;border-bottom:1px solid rgba(255,255,255,0.06);
                 text-align:right;vertical-align:middle;">
        <span style="font-size:0.88rem;color:#6B7A95;">{old_s:.0f}</span>
      </td>
      <td style="padding:14px 8px;border-bottom:1px solid rgba(255,255,255,0.06);
                 text-align:center;vertical-align:middle;">
        <span style="font-size:1rem;color:{acol};font-weight:700;">{arrow} {abs(delta):.0f}</span>
      </td>
      <td style="padding:14px 0;border-bottom:1px solid rgba(255,255,255,0.06);
                 text-align:right;vertical-align:middle;">
        <span style="font-size:1.1rem;font-weight:800;color:{ncol};">{new_s:.0f}</span>
      </td>
    </tr>"""

    count = len(moved)
    subject_ticker = moved[0]["ticker"] if count == 1 else f"{count} watched tickers"
    subject = f"Score alert: {subject_ticker} moved significantly"

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0B0D12;">
<div style="max-width:520px;margin:0 auto;background:#12151E;
            font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">

  <!-- Header -->
  <div style="background:#0f1119;padding:22px 28px 18px;border-radius:12px 12px 0 0;
              border-bottom:1px solid rgba(255,255,255,0.06);">
    <div style="font-size:0.60rem;color:#8892AA;letter-spacing:0.14em;
                text-transform:uppercase;margin-bottom:4px;">
      Unstructured Alpha · Watchlist
    </div>
    <div style="font-size:1.2rem;font-weight:700;color:#E8EEFF;">
      Confluence Score Movement
    </div>
    <div style="font-size:0.82rem;color:#8892AA;margin-top:4px;">
      {count} ticker{'s' if count != 1 else ''} moved ±10+ points since your last alert
    </div>
  </div>

  <!-- Table -->
  <div style="padding:20px 28px 8px;">
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr>
          <th style="font-size:0.62rem;font-weight:700;color:#6B7A95;letter-spacing:0.10em;
                     text-transform:uppercase;padding-bottom:10px;text-align:left;">Ticker</th>
          <th style="font-size:0.62rem;font-weight:700;color:#6B7A95;letter-spacing:0.10em;
                     text-transform:uppercase;padding-bottom:10px;text-align:right;">Previous</th>
          <th style="font-size:0.62rem;font-weight:700;color:#6B7A95;letter-spacing:0.10em;
                     text-transform:uppercase;padding-bottom:10px;text-align:center;">Change</th>
          <th style="font-size:0.62rem;font-weight:700;color:#6B7A95;letter-spacing:0.10em;
                     text-transform:uppercase;padding-bottom:10px;text-align:right;">Now</th>
        </tr>
      </thead>
      <tbody>{rows_html}
      </tbody>
    </table>
  </div>

  <!-- Score legend -->
  <div style="padding:16px 28px 20px;">
    <div style="background:#0f1119;border:1px solid rgba(255,255,255,0.06);
                border-radius:8px;padding:12px 16px;
                font-size:0.75rem;color:#6B7A95;line-height:1.7;">
      <span style="color:#00D566;font-weight:700;">≥ 65</span> Bullish &nbsp;·&nbsp;
      <span style="color:#F59E0B;font-weight:700;">35–65</span> Neutral &nbsp;·&nbsp;
      <span style="color:#FF4D6A;font-weight:700;">≤ 35</span> Bearish &nbsp;·&nbsp;
      Score = 0–100
    </div>
  </div>

  <!-- CTA -->
  <div style="padding:4px 28px 24px;text-align:center;">
    <a href="https://unstructuredalpha.com/Watchlist"
       style="display:inline-block;background:linear-gradient(135deg,#00C8E0,#7C3AED);
              color:#FFFFFF;padding:12px 32px;border-radius:8px;
              text-decoration:none;font-size:0.90rem;font-weight:700;">
      View Watchlist →
    </a>
  </div>

  <!-- Footer -->
  <div style="background:#0B0D12;padding:14px 28px;border-radius:0 0 12px 12px;
              border-top:1px solid rgba(255,255,255,0.06);
              font-size:0.68rem;color:#4A5280;text-align:center;line-height:1.6;">
    Unstructured Alpha · unstructuredalpha.com<br>
    Not financial advice. Confluence Score is a statistical composite from public data.
  </div>

</div>
</body>
</html>"""

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
        print(f"[score-moved] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[score-moved] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send score-moved email to {to_email}: {e}") from e


def send_velocity_alert_email(to_email: str, alerts: list[dict]) -> None:
    """
    Send an email notifying the user that one or more of their watched tickers
    is exhibiting an unusually high rate of confluence-score change.

    Each alert dict:
        ticker:        str   — e.g. "NVDA"
        name:          str   — full company name
        velocity:      float — pts/day (positive = rising, negative = falling)
        percentile:    float — 0–100 where this velocity ranks vs history
        current_score: float — latest recorded score
        case:          str   — "BULL" | "BEAR" | "NEUTRAL"
        direction:     str   — "up" | "down"
    """
    api_key    = _get_resend_key()
    from_email = _get_from_email()

    n = len(alerts)
    if n == 1:
        subj_ticker = alerts[0]["ticker"]
        subject = f"Score Velocity Alert: {subj_ticker} is moving fast"
    else:
        subject = f"Score Velocity Alert: {n} of your tickers are moving fast"

    def _score_pill(score: float, case: str) -> str:
        color = "#00D566" if case == "BULL" else ("#FF4D6A" if case == "BEAR" else "#F59E0B")
        return (
            f'<span style="color:{color};font-weight:800;">{score:.0f}</span>'
            f'<span style="color:#4A5280;font-size:0.82em;">/100</span>'
        )

    def _vel_arrow(direction: str) -> str:
        return "▲" if direction == "up" else "▼"

    def _vel_color(direction: str) -> str:
        return "#00D566" if direction == "up" else "#FF4D6A"

    rows_html = ""
    for a in alerts:
        vel   = a["velocity"]
        pct   = a["percentile"]
        vsign = "+" if vel >= 0 else ""
        vc    = _vel_color(a["direction"])
        va    = _vel_arrow(a["direction"])
        top_n = round(100 - pct, 0)
        rows_html += f"""
      <tr style="border-bottom:1px solid #1E2535;">
        <td style="padding:12px 8px 12px 0;vertical-align:middle;">
          <div style="font-size:0.95rem;font-weight:800;color:#E8EEFF;">{a["ticker"]}</div>
          <div style="font-size:0.72rem;color:#6B7A95;margin-top:2px;">{a.get("name","")[:32]}</div>
        </td>
        <td style="padding:12px 8px;vertical-align:middle;text-align:center;">
          {_score_pill(a["current_score"], a["case"])}
        </td>
        <td style="padding:12px 8px;vertical-align:middle;text-align:center;">
          <span style="color:{vc};font-weight:700;font-size:0.90rem;">
            {va} {vsign}{vel:.1f} pts/day
          </span>
        </td>
        <td style="padding:12px 0 12px 8px;vertical-align:middle;text-align:right;">
          <span style="font-size:0.78rem;color:#F59E0B;font-weight:600;">
            Top {top_n:.0f}%
          </span>
        </td>
      </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0B0D12;font-family:Inter,system-ui,sans-serif;">
<div style="max-width:580px;margin:32px auto;background:#12151E;border-radius:12px;
            border:1px solid #1E2535;overflow:hidden;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1A1E30,#0F1118);
              padding:24px 28px 20px;border-bottom:1px solid #1E2535;">
    <div style="font-size:0.60rem;font-weight:700;color:#F59E0B;letter-spacing:0.14em;
                text-transform:uppercase;margin-bottom:6px;">Velocity Alert</div>
    <div style="font-size:1.30rem;font-weight:800;color:#E8EEFF;line-height:1.3;">
      Score moving at an unusual pace
    </div>
    <div style="font-size:0.80rem;color:#6B7A95;margin-top:6px;line-height:1.5;">
      The machine detected rapid score movement on your watched ticker{"s" if n > 1 else ""}.
      Rare velocity often precedes continued momentum — or a reversal.
    </div>
  </div>

  <!-- Table -->
  <div style="padding:20px 28px 8px;">
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr>
          <th style="font-size:0.62rem;font-weight:700;color:#6B7A95;letter-spacing:0.10em;
                     text-transform:uppercase;padding-bottom:10px;text-align:left;">Ticker</th>
          <th style="font-size:0.62rem;font-weight:700;color:#6B7A95;letter-spacing:0.10em;
                     text-transform:uppercase;padding-bottom:10px;text-align:center;">Score</th>
          <th style="font-size:0.62rem;font-weight:700;color:#6B7A95;letter-spacing:0.10em;
                     text-transform:uppercase;padding-bottom:10px;text-align:center;">Velocity</th>
          <th style="font-size:0.62rem;font-weight:700;color:#6B7A95;letter-spacing:0.10em;
                     text-transform:uppercase;padding-bottom:10px;text-align:right;">Rank</th>
        </tr>
      </thead>
      <tbody>{rows_html}
      </tbody>
    </table>
  </div>

  <!-- Context note -->
  <div style="padding:12px 28px 20px;">
    <div style="background:#0f1119;border:1px solid rgba(245,158,11,0.20);border-left:3px solid #F59E0B;
                border-radius:6px;padding:12px 16px;
                font-size:0.75rem;color:#8892AA;line-height:1.7;">
      <strong style="color:#F59E0B;">What this means:</strong>
      Velocity = pts/day change in the Confluence Score over the last 5 sessions.
      "Top N%" = how rarely this ticker moves this fast in either direction.
      Not financial advice.
    </div>
  </div>

  <!-- CTA -->
  <div style="padding:4px 28px 24px;text-align:center;">
    <a href="https://unstructuredalpha.com/Ticker_Deep_Dive"
       style="display:inline-block;background:linear-gradient(135deg,#F59E0B,#D97706);
              color:#0B0D12;padding:12px 32px;border-radius:8px;
              text-decoration:none;font-size:0.90rem;font-weight:800;">
      Analyze on Ticker Deep Dive →
    </a>
  </div>

  <!-- Footer -->
  <div style="background:#0B0D12;padding:14px 28px;border-radius:0 0 12px 12px;
              border-top:1px solid rgba(255,255,255,0.06);
              font-size:0.68rem;color:#4A5280;text-align:center;line-height:1.6;">
    Unstructured Alpha · unstructuredalpha.com<br>
    Velocity alerts fire when score moves faster than 90% of all historical windows.
  </div>

</div>
</body>
</html>"""

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to":   [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
        print(f"[velocity-alert] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[velocity-alert] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send velocity alert email to {to_email}: {e}") from e


# ── Internal helpers for weekly brief ────────────────────────────────────────

def _get_resend_key() -> str:
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        try:
            api_key = st.secrets.get("RESEND_API_KEY", "")
        except Exception:
            api_key = ""
    return api_key


def _get_from_email() -> str:
    from_email = os.environ.get("RESEND_FROM_EMAIL", "")
    if not from_email:
        try:
            from_email = st.secrets.get("RESEND_FROM_EMAIL", _DEFAULT_FROM)
        except Exception:
            from_email = _DEFAULT_FROM
    return from_email


def send_weekly_brief_email(
    to_email: str,
    *,
    # Watchlist composite (week-over-week)
    composite_score: float | None = None,
    composite_delta: float | None = None,    # +/- pts week-over-week
    composite_label: str = "Mixed",          # "Bullish" | "Bearish" | "Mixed"
    n_tickers: int = 0,
    # Per-ticker movers on this user's watchlist
    watchlist_movers: list[dict] | None = None,   # [{ticker, name, score, delta, case}]
    # Market signal flips this week
    signal_flips_7d: list[dict] | None = None,    # [{signal_id, name, from_status, to_status}]
    # Market-wide Best Ideas (public, acquisition hook)
    best_ideas: list[dict] | None = None,         # [{ticker, name, score, velocity, rank_score}]
    # AI "what to watch next week" paragraph — Pro only
    ai_watchout: str | None = None,
    # Referral CTA
    referral_link: str | None = None,
    # Week string, e.g. "Jun 30 – Jul 6"
    week_str: str | None = None,
) -> None:
    """
    Send the weekly AI Portfolio Brief to a single Pro user.
    Called by cron/send_weekly_brief.py each Sunday at 15:00 UTC.

    Designed as a *retention anchor* (high-quality weekly read) and
    *acquisition engine* (referral CTA + shareable Best Ideas content).
    Never raises on missing optional sections — they're simply omitted.
    Raises EmailSendError only if RESEND_API_KEY is missing or the API call fails.
    """
    api_key    = _get_resend_key()
    from_email = _get_from_email()
    print(f"[weekly-brief] sending to={to_email!r}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    from datetime import date
    today_str = date.today().strftime("%B %-d, %Y")
    if not week_str:
        week_str = today_str

    subject = f"Your Weekly Portfolio Brief — {week_str}"

    # ── Composite score section ─────────────────────────────────────────────
    if composite_score is not None and n_tickers > 0:
        c_color   = "#00D566" if composite_label == "Bullish" else ("#FF4D6A" if composite_label == "Bearish" else "#F59E0B")
        c_bg      = "#0D2B1A" if composite_label == "Bullish" else ("#2B0D15" if composite_label == "Bearish" else "#1A1E2B")
        delta_str = ""
        if composite_delta is not None:
            dsign = "+" if composite_delta >= 0 else ""
            darrow = "▲" if composite_delta >= 0 else "▼"
            dc = "#00D566" if composite_delta >= 0 else "#FF4D6A"
            delta_str = (
                f'<span style="font-size:0.82rem;color:{dc};font-weight:700;margin-left:10px;">'
                f'{darrow} {dsign}{composite_delta:.1f} pts this week</span>'
            )
        composite_html = f"""
  <!-- Watchlist Composite Score -->
  <div style="background:{c_bg};border:1px solid {c_color}33;border-radius:10px;
              padding:20px 24px;margin:20px 24px 0;">
    <div style="font-size:0.58rem;font-weight:700;color:{c_color};letter-spacing:0.14em;
                text-transform:uppercase;margin-bottom:8px;">
      YOUR WATCHLIST · {n_tickers} TICKER{'S' if n_tickers != 1 else ''}
    </div>
    <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">
      <div style="font-size:3rem;font-weight:900;color:{c_color};line-height:1;">
        {composite_score:.0f}
      </div>
      <div>
        <div style="font-size:0.78rem;color:#8892AA;">/100 composite score</div>
        <div style="font-size:0.88rem;font-weight:700;color:{c_color};margin-top:2px;">
          {composite_label}
        </div>
      </div>
      {delta_str}
    </div>
  </div>"""
    else:
        composite_html = ""

    # ── Watchlist movers table ──────────────────────────────────────────────
    if watchlist_movers:
        mover_rows = ""
        for m in watchlist_movers[:3]:
            sc   = float(m.get("score", 50))
            d    = float(m.get("delta", 0))
            case = m.get("case", "NEUT")
            sc_c = "#00D566" if case == "BULL" else ("#FF4D6A" if case == "BEAR" else "#F59E0B")
            da   = "▲" if d >= 0 else "▼"
            dc   = "#00D566" if d >= 0 else "#FF4D6A"
            dsign = "+" if d >= 0 else ""
            mover_rows += f"""
        <tr style="border-bottom:1px solid #1E2535;">
          <td style="padding:10px 0;vertical-align:middle;">
            <div style="font-size:0.92rem;font-weight:700;color:#E8EEFF;">{m['ticker']}</div>
            <div style="font-size:0.72rem;color:#6B7A95;margin-top:2px;">{str(m.get('name',''))[:28]}</div>
          </td>
          <td style="padding:10px 8px;text-align:center;vertical-align:middle;">
            <span style="color:{sc_c};font-weight:800;font-size:0.95rem;">{sc:.0f}</span>
            <span style="color:#4A5280;font-size:0.75rem;">/100</span>
          </td>
          <td style="padding:10px 0;text-align:right;vertical-align:middle;">
            <span style="color:{dc};font-weight:700;font-size:0.88rem;">{da} {dsign}{d:.1f}</span>
            <span style="font-size:0.68rem;color:#6B7A95;"> 7d</span>
          </td>
        </tr>"""
        movers_html = f"""
  <!-- Watchlist Movers -->
  <div style="margin:16px 24px 0;">
    <div style="font-size:0.58rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;
                text-transform:uppercase;margin-bottom:10px;">
      YOUR TOP MOVERS THIS WEEK
    </div>
    <table style="width:100%;border-collapse:collapse;">
      {mover_rows}
    </table>
    <div style="text-align:right;margin-top:6px;">
      <a href="https://unstructuredalpha.com/Watchlist"
         style="font-size:0.72rem;color:#7C3AED;text-decoration:none;">
        Open Watchlist →
      </a>
    </div>
  </div>"""
    else:
        movers_html = ""

    # ── Signal flips table ──────────────────────────────────────────────────
    if signal_flips_7d:
        flip_rows = ""
        STATUS_COLOR = {
            "bullish": "#00D566", "bearish": "#FF4D6A",
            "neutral": "#F59E0B", "insufficient_data": "#6B7A95",
        }
        STATUS_SYM = {
            "bullish": "▲", "bearish": "▼",
            "neutral": "●", "insufficient_data": "○",
        }
        for f in signal_flips_7d[:5]:
            fc = STATUS_COLOR.get(f.get("from_status", "neutral"), "#6B7A95")
            tc = STATUS_COLOR.get(f.get("to_status",   "neutral"), "#6B7A95")
            fa = STATUS_SYM.get(f.get("from_status",   "neutral"), "●")
            ta = STATUS_SYM.get(f.get("to_status",     "neutral"), "●")
            flip_rows += f"""
          <tr style="border-bottom:1px solid #1E2535;">
            <td style="padding:9px 0;font-size:0.82rem;color:#B8C0D4;">{f.get('name', f.get('signal_id',''))}</td>
            <td style="padding:9px 8px;color:{fc};font-size:0.82rem;white-space:nowrap;">{fa} {str(f.get('from_status','')).title()}</td>
            <td style="padding:9px 4px;color:#4A5280;font-size:0.9rem;">→</td>
            <td style="padding:9px 0;color:{tc};font-weight:700;font-size:0.82rem;white-space:nowrap;">{ta} {str(f.get('to_status','')).title()}</td>
          </tr>"""
        flips_html = f"""
  <!-- Signal Flips -->
  <div style="margin:20px 24px 0;">
    <div style="font-size:0.58rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;
                text-transform:uppercase;margin-bottom:10px;">
      MACRO SIGNAL FLIPS THIS WEEK
    </div>
    <table style="width:100%;border-collapse:collapse;">
      {flip_rows}
    </table>
    <div style="text-align:right;margin-top:6px;">
      <a href="https://unstructuredalpha.com/Today%27s_Brief"
         style="font-size:0.72rem;color:#7C3AED;text-decoration:none;">
        View full signal state →
      </a>
    </div>
  </div>"""
    else:
        flips_html = """
  <div style="margin:20px 24px 0;padding:14px;background:#0f1119;border-radius:8px;
              border:1px solid #1E2535;font-size:0.82rem;color:#6B7A95;text-align:center;">
    No macro signal flips this week — the regime has been stable.
  </div>"""

    # ── AI watchout section ─────────────────────────────────────────────────
    if ai_watchout:
        ai_html = f"""
  <!-- AI What to Watch -->
  <div style="margin:20px 24px 0;padding:16px 18px;
              background:rgba(124,58,237,0.06);
              border:1px solid rgba(124,58,237,0.18);
              border-left:3px solid #7C3AED;border-radius:8px;">
    <div style="font-size:0.58rem;font-weight:700;color:#A78BFA;letter-spacing:0.12em;
                text-transform:uppercase;margin-bottom:8px;">
      ✦ AI OUTLOOK · WHAT TO WATCH NEXT WEEK
    </div>
    <div style="font-size:0.88rem;color:#B8C0D4;line-height:1.75;">
      {ai_watchout}
    </div>
  </div>"""
    else:
        ai_html = ""

    # ── Best Ideas section (market-wide, public content — acquisition hook) ─
    if best_ideas:
        idea_rows = ""
        for i, row in enumerate(best_ideas[:3], 1):
            vel  = row.get("velocity", 0)
            vsign = "+" if vel >= 0 else ""
            idea_rows += f"""
          <tr>
            <td style="padding:10px 0;vertical-align:middle;width:24px;">
              <span style="font-size:0.82rem;color:#F59E0B;font-weight:700;">{i}</span>
            </td>
            <td style="padding:10px 8px;vertical-align:middle;">
              <div style="font-size:0.92rem;font-weight:700;color:#E8EEFF;">{row['ticker']}</div>
              <div style="font-size:0.70rem;color:#6B7A95;">{str(row.get('name',''))[:24]}</div>
            </td>
            <td style="padding:10px 8px;text-align:center;vertical-align:middle;">
              <span style="color:#00D566;font-weight:800;">{float(row.get('score',0)):.0f}</span>
              <span style="color:#4A5280;font-size:0.75rem;">/100</span>
            </td>
            <td style="padding:10px 0;text-align:right;vertical-align:middle;white-space:nowrap;">
              <span style="color:#00D566;font-size:0.80rem;font-weight:700;">▲ {vsign}{vel:.1f} pts/d</span>
            </td>
          </tr>"""
        best_ideas_html = f"""
  <!-- Divider -->
  <div style="height:1px;background:#1E2535;margin:20px 24px;"></div>

  <!-- Best Ideas -->
  <div style="margin:0 24px;">
    <div style="font-size:0.58rem;font-weight:700;color:#F59E0B;letter-spacing:0.12em;
                text-transform:uppercase;margin-bottom:4px;">
      MACHINE'S BEST IDEAS RIGHT NOW
    </div>
    <div style="font-size:0.72rem;color:#6B7A95;margin-bottom:12px;">
      Highest conviction + rising score momentum across all tracked tickers
    </div>
    <table style="width:100%;border-collapse:collapse;">
      {idea_rows}
    </table>
    <div style="margin-top:10px;">
      <a href="https://unstructuredalpha.com/Best_Ideas"
         style="display:inline-block;background:rgba(245,158,11,0.10);
                border:1px solid rgba(245,158,11,0.30);color:#F59E0B;
                padding:8px 18px;border-radius:6px;text-decoration:none;
                font-size:0.82rem;font-weight:700;">
        See full Best Ideas list →
      </a>
    </div>
  </div>"""
    else:
        best_ideas_html = ""

    # ── Referral CTA ────────────────────────────────────────────────────────
    if referral_link:
        referral_html = f"""
  <!-- Divider -->
  <div style="height:1px;background:#1E2535;margin:20px 24px;"></div>

  <!-- Referral CTA -->
  <div style="margin:0 24px 0;padding:16px 18px;
              background:rgba(0,213,102,0.04);
              border:1px solid rgba(0,213,102,0.15);border-radius:8px;">
    <div style="font-size:0.82rem;font-weight:700;color:#E8EEFF;margin-bottom:6px;">
      Know someone who'd find this useful?
    </div>
    <div style="font-size:0.78rem;color:#8892AA;line-height:1.65;margin-bottom:12px;">
      Forward this email or share your personal link — they'll get a
      <strong style="color:#00D566;">14-day free Pro trial</strong>
      (double the normal 7 days), and you'll earn a free month when they subscribe.
    </div>
    <a href="{referral_link}"
       style="display:inline-block;background:rgba(0,213,102,0.12);
              border:1px solid rgba(0,213,102,0.30);color:#00D566;
              padding:8px 18px;border-radius:6px;text-decoration:none;
              font-size:0.82rem;font-weight:700;word-break:break-all;">
      {referral_link}
    </a>
  </div>"""
    else:
        referral_html = ""

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0B0D12;font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
<div style="max-width:580px;margin:24px auto;background:#12151E;border-radius:12px;
            border:1px solid #1E2535;overflow:hidden;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1A1E30 0%,#0B0D12 100%);
              padding:24px 28px 20px;border-bottom:1px solid #1E2535;">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">
      <div>
        <div style="font-size:0.58rem;font-weight:700;color:#7C3AED;letter-spacing:0.14em;
                    text-transform:uppercase;margin-bottom:6px;">
          UNSTRUCTURED ALPHA · WEEKLY BRIEF
        </div>
        <div style="font-size:1.35rem;font-weight:800;color:#E8EEFF;line-height:1.25;">
          Portfolio Intelligence Brief
        </div>
        <div style="font-size:0.80rem;color:#6B7A95;margin-top:5px;">{week_str}</div>
      </div>
      <div style="text-align:right;">
        <div style="font-size:0.68rem;color:#4A5280;">28-signal macro engine</div>
        <div style="font-size:0.68rem;color:#4A5280;">unstructuredalpha.com</div>
      </div>
    </div>
  </div>

  {composite_html}
  {movers_html}

  <!-- Divider -->
  <div style="height:1px;background:#1E2535;margin:20px 24px;"></div>

  {flips_html}
  {ai_html}
  {best_ideas_html}
  {referral_html}

  <!-- Main CTA -->
  <div style="padding:24px 24px;text-align:center;">
    <a href="https://unstructuredalpha.com/Watchlist"
       style="display:inline-block;background:linear-gradient(135deg,#7C3AED,#5B21B6);
              color:#FFFFFF;padding:12px 30px;border-radius:8px;
              text-decoration:none;font-size:0.92rem;font-weight:700;
              letter-spacing:0.02em;">
      Open Dashboard →
    </a>
  </div>

  <!-- Footer -->
  <div style="background:#0B0D12;padding:14px 28px;border-top:1px solid #1E2535;
              font-size:0.68rem;color:#4A5280;text-align:center;line-height:1.7;">
    Unstructured Alpha · unstructuredalpha.com · Not financial advice · Data from public sources<br>
    <a href="https://unstructuredalpha.com/Watchlist"
       style="color:#6B7A95;text-decoration:none;">Manage email preferences</a>
    &nbsp;·&nbsp;
    <a href="https://unstructuredalpha.com/Best_Ideas"
       style="color:#6B7A95;text-decoration:none;">Best Ideas</a>
  </div>

</div>
</body>
</html>"""

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to":   [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=20,
        )
        print(f"[weekly-brief] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[weekly-brief] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send weekly brief to {to_email}: {e}") from e


def send_reengagement_email(
    to_email: str,
    *,
    days_away: int,
    # Top movers on the user's watchlist since they last logged in
    movers: list[dict] | None = None,   # [{ticker, name, score, delta, case}]
    # Signal flips since they last logged in
    signal_flips: list[dict] | None = None,  # [{name, from_status, to_status}]
    # Overall macro regime
    regime_label: str = "Mixed",
) -> None:
    """
    Re-engagement email for users who haven't logged in for >= INACTIVE_DAYS.
    Called by cron/send_reengagement.py.

    Tone: friendly, not pushy. "Here's what changed while you were away."
    CTA: come back and check your watchlist.

    Raises EmailSendError if RESEND_API_KEY is missing or the API call fails.
    """
    api_key    = _get_resend_key()
    from_email = _get_from_email()
    print(f"[reengagement] sending to={to_email!r} days_away={days_away}", flush=True)
    if not api_key:
        raise EmailSendError("No RESEND_API_KEY configured.")

    from datetime import date
    today_str = date.today().strftime("%B %-d, %Y")

    subject = f"👋 {days_away} days of macro moves — your watchlist has updates"

    # ── Movers section ──────────────────────────────────────────────────────
    if movers:
        mover_rows = ""
        for m in movers[:4]:
            sc   = float(m.get("score", 50))
            d    = float(m.get("delta", 0))
            case = m.get("case", "NEUT")
            sc_c = "#00D566" if case == "BULL" else ("#FF4D6A" if case == "BEAR" else "#F59E0B")
            da   = "▲" if d >= 0 else "▼"
            dc   = "#00D566" if d >= 0 else "#FF4D6A"
            dsign = "+" if d >= 0 else ""
            mover_rows += f"""
        <tr style="border-bottom:1px solid #1E2535;">
          <td style="padding:10px 0;vertical-align:middle;">
            <div style="font-size:0.92rem;font-weight:700;color:#E8EEFF;">{m['ticker']}</div>
            <div style="font-size:0.72rem;color:#6B7A95;">{str(m.get('name',''))[:28]}</div>
          </td>
          <td style="padding:10px 8px;text-align:center;vertical-align:middle;white-space:nowrap;">
            <span style="color:{sc_c};font-weight:800;">{sc:.0f}</span>
            <span style="color:#4A5280;font-size:0.72rem;">/100</span>
          </td>
          <td style="padding:10px 0;text-align:right;vertical-align:middle;white-space:nowrap;">
            <span style="color:{dc};font-weight:700;">{da} {dsign}{d:.1f}</span>
            <span style="font-size:0.68rem;color:#6B7A95;"> since you left</span>
          </td>
        </tr>"""
        movers_html = f"""
  <div style="margin:16px 0 0;">
    <div style="font-size:0.58rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;
                text-transform:uppercase;margin-bottom:10px;">YOUR WATCHLIST MOVERS</div>
    <table style="width:100%;border-collapse:collapse;">{mover_rows}
    </table>
  </div>"""
    else:
        movers_html = """
  <div style="margin:16px 0 0;padding:12px;background:#0f1119;border-radius:6px;
              font-size:0.82rem;color:#6B7A95;">
    Add tickers to your watchlist to see score changes here.
  </div>"""

    # ── Signal flips section ────────────────────────────────────────────────
    if signal_flips:
        STATUS_COLOR = {
            "bullish": "#00D566", "bearish": "#FF4D6A",
            "neutral": "#F59E0B", "insufficient_data": "#6B7A95",
        }
        STATUS_SYM = {
            "bullish": "▲", "bearish": "▼", "neutral": "●", "insufficient_data": "○",
        }
        flip_rows = ""
        for f in signal_flips[:4]:
            fc = STATUS_COLOR.get(f.get("from_status", "neutral"), "#6B7A95")
            tc = STATUS_COLOR.get(f.get("to_status",   "neutral"), "#6B7A95")
            fa = STATUS_SYM.get(f.get("from_status",   "neutral"), "●")
            ta = STATUS_SYM.get(f.get("to_status",     "neutral"), "●")
            flip_rows += f"""
          <tr style="border-bottom:1px solid #1E2535;">
            <td style="padding:8px 0;font-size:0.82rem;color:#B8C0D4;">{f.get('name','')}</td>
            <td style="padding:8px 6px;color:{fc};font-size:0.80rem;white-space:nowrap;">{fa} {str(f.get('from_status','')).title()}</td>
            <td style="padding:8px 4px;color:#4A5280;">→</td>
            <td style="padding:8px 0;color:{tc};font-weight:700;font-size:0.80rem;white-space:nowrap;">{ta} {str(f.get('to_status','')).title()}</td>
          </tr>"""
        flips_html = f"""
  <div style="margin:20px 0 0;">
    <div style="font-size:0.58rem;font-weight:700;color:#8892AA;letter-spacing:0.12em;
                text-transform:uppercase;margin-bottom:10px;">MACRO SIGNAL FLIPS WHILE YOU WERE AWAY</div>
    <table style="width:100%;border-collapse:collapse;">{flip_rows}
    </table>
  </div>"""
    else:
        flips_html = ""

    # ── Regime badge ────────────────────────────────────────────────────────
    r_color = "#00D566" if regime_label == "Bullish" else ("#FF4D6A" if regime_label == "Bearish" else "#F59E0B")

    html = f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0B0D12;font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;">
<div style="max-width:560px;margin:24px auto;background:#12151E;border-radius:12px;
            border:1px solid #1E2535;overflow:hidden;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1A1E30 0%,#0B0D12 100%);
              padding:24px 28px 20px;border-bottom:1px solid #1E2535;">
    <div style="font-size:0.58rem;font-weight:700;color:#7C3AED;letter-spacing:0.14em;
                text-transform:uppercase;margin-bottom:6px;">UNSTRUCTURED ALPHA</div>
    <div style="font-size:1.25rem;font-weight:800;color:#E8EEFF;line-height:1.25;">
      A few things moved while you were away
    </div>
    <div style="font-size:0.80rem;color:#6B7A95;margin-top:5px;">
      {days_away} days · {today_str} ·
      <span style="color:{r_color};font-weight:700;">Macro: {regime_label}</span>
    </div>
  </div>

  <!-- Body -->
  <div style="padding:20px 28px 8px;">
    {movers_html}
    {flips_html}
  </div>

  <!-- CTA -->
  <div style="padding:20px 28px 24px;text-align:center;">
    <a href="https://unstructuredalpha.com/Watchlist"
       style="display:inline-block;background:linear-gradient(135deg,#7C3AED,#5B21B6);
              color:#FFFFFF;padding:12px 32px;border-radius:8px;
              text-decoration:none;font-size:0.92rem;font-weight:700;">
      Check Your Watchlist →
    </a>
    <div style="margin-top:10px;font-size:0.72rem;color:#4A5280;">
      Or go to
      <a href="https://unstructuredalpha.com/Today%27s_Brief"
         style="color:#7C3AED;text-decoration:none;">Today's Brief</a>
      for the full macro picture.
    </div>
  </div>

  <!-- Footer -->
  <div style="background:#0B0D12;padding:14px 28px;border-top:1px solid #1E2535;
              font-size:0.68rem;color:#4A5280;text-align:center;line-height:1.7;">
    Unstructured Alpha · unstructuredalpha.com · Not financial advice<br>
    <a href="https://unstructuredalpha.com/Watchlist"
       style="color:#6B7A95;text-decoration:none;">Manage email preferences</a>
  </div>

</div>
</body>
</html>"""

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to":   [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
        print(f"[reengagement] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[reengagement] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send reengagement email to {to_email}: {e}") from e


# ─────────────────────────────────────────────────────────────────────────────
# Day-3 Onboarding Email
# Sent by cron/send_onboarding_day3.py three days after a user verifies their
# email. Shows the 3 most-used Pro features they may not have discovered yet,
# with a soft upgrade CTA for free users.
# ─────────────────────────────────────────────────────────────────────────────

def send_day3_onboarding_email(
    to_email: str,
    *,
    is_pro: bool = False,
    top_bull_ticker: str | None = None,   # highest-score bullish ticker right now
    top_bull_score: float | None = None,
    regime_label: str = "Mixed",
) -> None:
    """
    Day-3 onboarding email — highlights 3 features users commonly miss.
    Sent 3 days after email verification.
    """
    api_key    = _get_resend_key()
    from_email = _get_from_email()

    subject = "3 features you probably haven't tried yet 🔍"

    # Personalisation snippets
    _ticker_callout = ""
    if top_bull_ticker and top_bull_score is not None:
        _ticker_callout = f"""
<div style="background:rgba(0,213,102,0.08);border:1px solid rgba(0,213,102,0.20);
            border-radius:10px;padding:12px 18px;margin:16px 0;">
  <div style="font-size:0.70rem;font-weight:700;color:#8892AA;text-transform:uppercase;
              letter-spacing:0.10em;margin-bottom:4px;">Machine's Top Pick Right Now</div>
  <span style="font-size:1.1rem;font-weight:800;color:#00D566;">{top_bull_ticker}</span>
  <span style="font-size:0.85rem;color:#00D566;margin-left:8px;">Score: {top_bull_score:.0f}/100</span>
  <div style="font-size:0.75rem;color:#8892AA;margin-top:4px;">
    {regime_label} macro regime · Updated hourly
  </div>
</div>"""

    _upgrade_cta = "" if is_pro else """
<div style="background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.22);
            border-radius:10px;padding:14px 20px;margin:20px 0;text-align:center;">
  <div style="font-size:0.88rem;font-weight:700;color:#C5CCDE;margin-bottom:6px;">
    All three features above are included with Pro
  </div>
  <div style="font-size:0.78rem;color:#8892AA;margin-bottom:12px;">
    $20/month · Cancel anytime · 7-day free trial
  </div>
  <a href="https://unstructuredalpha.com/Upgrade"
     style="display:inline-block;background:linear-gradient(135deg,#7C3AED,#5B21B6);
            color:#fff;padding:10px 28px;border-radius:8px;
            text-decoration:none;font-size:0.88rem;font-weight:700;">
    Start Free Trial →
  </a>
</div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0B0D12;font-family:Inter,Arial,sans-serif;">
<div style="max-width:600px;margin:0 auto;background:#0F1117;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#12151E,#1A1E2E);padding:24px 28px 20px;
              border-bottom:1px solid #1E2535;">
    <div style="font-size:0.60rem;font-weight:700;color:#8892AA;letter-spacing:0.14em;
                text-transform:uppercase;">Unstructured Alpha</div>
    <div style="font-size:1.4rem;font-weight:900;color:#E8EEFF;margin-top:4px;">
      You're in — here's what to try next
    </div>
    <div style="font-size:0.85rem;color:#8892AA;margin-top:6px;">
      3 features that most users discover on day 3 or later
    </div>
  </div>

  <!-- Body -->
  <div style="padding:24px 28px;">
    {_ticker_callout}

    <p style="font-size:0.88rem;color:#C5CCDE;line-height:1.65;margin-bottom:20px;">
      Most people start on the Signal Dashboard and stop there. That misses the best parts.
      Here are the three features worth trying today:
    </p>

    <!-- Feature 1 -->
    <div style="border:1px solid #1E2535;border-radius:12px;padding:18px 20px;margin-bottom:14px;">
      <div style="font-size:0.62rem;font-weight:700;color:#00C8E0;text-transform:uppercase;
                  letter-spacing:0.10em;margin-bottom:6px;">Best Ideas Page</div>
      <div style="font-size:0.92rem;font-weight:700;color:#E8EEFF;margin-bottom:6px;">
        The machine's highest-conviction bullish calls right now
      </div>
      <div style="font-size:0.82rem;color:#8892AA;line-height:1.6;">
        Score ≥ 62 + positive velocity = rising conviction. Updated hourly.
        Tickers are ranked by score + momentum — not sorted by name like a screener.
      </div>
      <a href="https://unstructuredalpha.com/Best_Ideas"
         style="display:inline-block;margin-top:10px;font-size:0.80rem;font-weight:700;
                color:#00C8E0;text-decoration:none;">Open Best Ideas →</a>
    </div>

    <!-- Feature 2 -->
    <div style="border:1px solid #1E2535;border-radius:12px;padding:18px 20px;margin-bottom:14px;">
      <div style="font-size:0.62rem;font-weight:700;color:#F59E0B;text-transform:uppercase;
                  letter-spacing:0.10em;margin-bottom:6px;">Ticker Deep Dive</div>
      <div style="font-size:0.92rem;font-weight:700;color:#E8EEFF;margin-bottom:6px;">
        28 signals, each scored for your specific ticker
      </div>
      <div style="font-size:0.82rem;color:#8892AA;line-height:1.6;">
        The AI explanation shows exactly which signals are driving the score — and which
        would need to flip to change the thesis. Each signal links to its source data.
      </div>
      <a href="https://unstructuredalpha.com/Ticker_Deep_Dive"
         style="display:inline-block;margin-top:10px;font-size:0.80rem;font-weight:700;
                color:#F59E0B;text-decoration:none;">Open Ticker Deep Dive →</a>
    </div>

    <!-- Feature 3 -->
    <div style="border:1px solid #1E2535;border-radius:12px;padding:18px 20px;margin-bottom:14px;">
      <div style="font-size:0.62rem;font-weight:700;color:#00D566;text-transform:uppercase;
                  letter-spacing:0.10em;margin-bottom:6px;">⭐ My Watchlist</div>
      <div style="font-size:0.92rem;font-weight:700;color:#E8EEFF;margin-bottom:6px;">
        Score alerts + weekly report card for your tickers
      </div>
      <div style="font-size:0.82rem;color:#8892AA;line-height:1.6;">
        Add any ticker to your watchlist and get email alerts when its Confluence Score
        crosses your thresholds. The new Weekly Score Report Card grades each ticker A–F
        on 7-day score trajectory.
      </div>
      <a href="https://unstructuredalpha.com/My_Watchlist"
         style="display:inline-block;margin-top:10px;font-size:0.80rem;font-weight:700;
                color:#00D566;text-decoration:none;">Open My Watchlist →</a>
    </div>

    {_upgrade_cta}
  </div>

  <!-- Footer -->
  <div style="background:#0B0D12;padding:14px 28px;border-top:1px solid #1E2535;
              font-size:0.68rem;color:#4A5280;text-align:center;line-height:1.7;">
    Unstructured Alpha · unstructuredalpha.com · Not financial advice<br>
    <a href="https://unstructuredalpha.com/My_Watchlist"
       style="color:#6B7A95;text-decoration:none;">Manage email preferences</a>
  </div>

</div>
</body>
</html>"""

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to":   [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
        print(f"[day3-onboarding] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[day3-onboarding] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send day-3 email to {to_email}: {e}") from e


# ─────────────────────────────────────────────────────────────────────────────
# Day-7 Retention Email
# ─────────────────────────────────────────────────────────────────────────────

def send_day7_onboarding_email(
    to_email: str,
    *,
    is_pro: bool = False,
    regime_label: str = "Mixed",
    top_tickers: list[dict] | None = None,
    signal_flip: dict | None = None,
) -> None:
    """Send the day-7 "one week in" retention email.

    Parameters
    ----------
    to_email:
        Recipient address.
    is_pro:
        True if the user is on a Pro plan — skips the upgrade CTA.
    regime_label:
        Current macro regime string: "Bullish", "Bearish", or "Mixed".
    top_tickers:
        List of dicts with keys ``ticker``, ``score``, ``status`` —
        the machine's top picks right now.  Up to 3 are shown.
    signal_flip:
        Optional dict with keys ``name``, ``from_status``, ``to_status`` —
        the most notable signal flip in the past 7 days.
    """
    api_key, from_email = _get_email_config()

    _REGIME_COLOR = {"Bullish": "#00D566", "Bearish": "#FF4444", "Mixed": "#F59E0B"}
    regime_color = _REGIME_COLOR.get(regime_label, "#F59E0B")

    tickers = (top_tickers or [])[:3]

    # ── Ticker rows ──────────────────────────────────────────────────────────
    def _ticker_row(t: dict) -> str:
        sc    = t.get("score", 50)
        tick  = t.get("ticker", "?")
        stat  = (t.get("status") or "neutral").capitalize()
        scolor = "#00D566" if stat == "Bullish" else "#FF4444" if stat == "Bearish" else "#F59E0B"
        sc_int = int(round(sc))
        return (
            f'<tr>'
            f'<td style="padding:8px 14px;font-size:0.88rem;font-weight:700;color:#E8EEFF;">{tick}</td>'
            f'<td style="padding:8px 14px;">'
            f'  <span style="background:{scolor}18;border:1px solid {scolor}33;'
            f'  border-radius:4px;padding:2px 8px;font-size:0.72rem;font-weight:700;color:{scolor};">'
            f'  {stat}</span>'
            f'</td>'
            f'<td style="padding:8px 14px;font-size:0.88rem;font-weight:700;color:{scolor};">'
            f'  {sc_int}/100'
            f'</td>'
            f'</tr>'
        )

    ticker_rows_html = "".join(_ticker_row(t) for t in tickers) if tickers else (
        '<tr><td colspan="3" style="padding:10px 14px;color:#8892AA;font-size:0.82rem;">'
        'Scores refreshing — check the live dashboard for the latest.</td></tr>'
    )

    # ── Signal flip block ─────────────────────────────────────────────────────
    if signal_flip:
        flip_from = (signal_flip.get("from_status") or "neutral").upper()
        flip_to   = (signal_flip.get("to_status")   or "neutral").upper()
        flip_name = signal_flip.get("name", "A macro signal")
        flip_to_color = "#00D566" if "BULL" in flip_to else "#FF4444" if "BEAR" in flip_to else "#F59E0B"
        flip_html = f"""
        <div style="background:#0F1118;border-left:3px solid {flip_to_color};
                    border-radius:8px;padding:12px 16px;margin-bottom:20px;">
          <div style="font-size:0.68rem;font-weight:700;color:{flip_to_color};
                      letter-spacing:0.10em;text-transform:uppercase;margin-bottom:4px;">
            Signal Flip This Week
          </div>
          <div style="font-size:0.88rem;color:#B8C0D4;line-height:1.6;">
            <b style="color:#E8EEFF;">{flip_name}</b>
            flipped from
            <span style="font-weight:700;color:#8892AA;">{flip_from}</span>
            →
            <span style="font-weight:700;color:{flip_to_color};">{flip_to}</span>
          </div>
        </div>"""
    else:
        flip_html = ""

    # ── Pro CTA (free only) ───────────────────────────────────────────────────
    pro_cta = "" if is_pro else """
        <div style="background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.20);
                    border-radius:10px;padding:16px 20px;margin:20px 0;">
          <div style="font-size:0.72rem;font-weight:700;color:#A78BFA;
                      letter-spacing:0.10em;text-transform:uppercase;margin-bottom:6px;">
            Upgrade to Pro
          </div>
          <div style="font-size:0.85rem;color:#B8C0D4;line-height:1.6;margin-bottom:12px;">
            You've seen the free tier — Pro unlocks personalized daily email alerts,
            macro stress testing, webhook notifications, and AI watchlist narratives.
          </div>
          <a href="https://unstructuredalpha.com/Upgrade_to_Pro"
             style="display:inline-block;background:#7C3AED;color:#FFFFFF;
                    border-radius:6px;padding:9px 20px;font-size:0.82rem;
                    font-weight:700;text-decoration:none;letter-spacing:0.04em;">
            Start Free Trial →
          </a>
        </div>"""

    subject = "One week in — what the machine is seeing right now"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{subject}</title></head>
<body style="margin:0;padding:0;background:#0B0D12;font-family:'Helvetica Neue',Arial,sans-serif;">

<div style="max-width:580px;margin:0 auto;padding:32px 20px;">

  <!-- Header -->
  <div style="text-align:center;margin-bottom:28px;">
    <div style="font-size:1.05rem;font-weight:800;color:#E8EEFF;letter-spacing:0.04em;">
      Unstructured Alpha
    </div>
    <div style="font-size:0.68rem;color:#6B7FBF;letter-spacing:0.10em;
                text-transform:uppercase;margin-top:2px;">
      Signal Intelligence Dashboard
    </div>
  </div>

  <!-- Headline -->
  <div style="font-size:1.25rem;font-weight:700;color:#E8EEFF;line-height:1.4;margin-bottom:8px;">
    You've been here one week.
  </div>
  <div style="font-size:0.90rem;color:#8892AA;line-height:1.6;margin-bottom:24px;">
    Here's a snapshot of what 38 alternative signals are saying right now.
  </div>

  <!-- Regime pill -->
  <div style="display:inline-block;background:{regime_color}18;
              border:1px solid {regime_color}33;border-radius:20px;
              padding:4px 16px;margin-bottom:20px;">
    <span style="font-size:0.75rem;font-weight:700;color:{regime_color};letter-spacing:0.08em;
                 text-transform:uppercase;">
      Current Macro Regime: {regime_label}
    </span>
  </div>

  <!-- Top tickers table -->
  <div style="background:#12151E;border:1px solid rgba(255,255,255,0.07);
              border-radius:10px;overflow:hidden;margin-bottom:20px;">
    <div style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.05);">
      <span style="font-size:0.65rem;font-weight:700;color:#8892AA;letter-spacing:0.10em;
                   text-transform:uppercase;">Machine's Top Picks Right Now</span>
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
          <th style="padding:7px 14px;text-align:left;font-size:0.65rem;color:#6B7FBF;
                     font-weight:600;letter-spacing:0.08em;text-transform:uppercase;">Ticker</th>
          <th style="padding:7px 14px;text-align:left;font-size:0.65rem;color:#6B7FBF;
                     font-weight:600;letter-spacing:0.08em;text-transform:uppercase;">Signal</th>
          <th style="padding:7px 14px;text-align:left;font-size:0.65rem;color:#6B7FBF;
                     font-weight:600;letter-spacing:0.08em;text-transform:uppercase;">Score</th>
        </tr>
      </thead>
      <tbody>{ticker_rows_html}</tbody>
    </table>
  </div>

  {flip_html}

  <!-- Feature reminder -->
  <div style="background:#12151E;border:1px solid rgba(255,255,255,0.07);
              border-radius:10px;padding:16px 20px;margin-bottom:20px;">
    <div style="font-size:0.65rem;font-weight:700;color:#00C8E0;letter-spacing:0.10em;
                text-transform:uppercase;margin-bottom:8px;">Tip: Signal Backtester</div>
    <div style="font-size:0.85rem;color:#B8C0D4;line-height:1.6;margin-bottom:10px;">
      Pick any combination of signals and see how well they predicted 4–12 week forward
      returns — before you trust them. Most retail platforms hide this test entirely.
    </div>
    <a href="https://unstructuredalpha.com/Signal_Backtester"
       style="font-size:0.82rem;color:#00C8E0;text-decoration:none;font-weight:600;">
      Open Signal Backtester →
    </a>
  </div>

  {pro_cta}

  <!-- CTA -->
  <div style="text-align:center;margin:24px 0 8px;">
    <a href="https://unstructuredalpha.com/"
       style="display:inline-block;background:#00D566;color:#0B0D12;
              border-radius:6px;padding:11px 28px;font-size:0.88rem;
              font-weight:800;text-decoration:none;letter-spacing:0.04em;">
      Open Dashboard →
    </a>
  </div>

  <!-- Footer -->
  <div style="margin-top:32px;padding-top:20px;border-top:1px solid rgba(255,255,255,0.06);
              font-size:0.68rem;color:#4A5280;text-align:center;line-height:1.7;">
    Unstructured Alpha · unstructuredalpha.com · Not financial advice<br>
    <a href="https://unstructuredalpha.com/My_Watchlist"
       style="color:#6B7A95;text-decoration:none;">Manage email preferences</a>
  </div>

</div>
</body>
</html>"""

    try:
        resp = requests.post(
            _RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to":   [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
        print(f"[day7-onboarding] Resend responded: status={resp.status_code}", flush=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[day7-onboarding] send FAILED to={to_email!r}: {e}", flush=True)
        raise EmailSendError(f"Failed to send day-7 email to {to_email}: {e}") from e
