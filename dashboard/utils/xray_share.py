# utils/xray_share.py
# Unstructured Alpha — a shared Portfolio X-ray that previews as itself
#
# The X-ray kept a mix in the link's #fragment, which link-preview crawlers
# (X, LinkedIn, Slack, iMessage) never see, so every shared mix previewed as
# the same generic card. A share link now carries the mix as ?p=AAPL:50,XOM:50;
# the server reads it, titles the page with the mix's biggest driver, and
# points og:image at a card drawn for that mix (/xray/og.png?p=...).
#
# RULES
#   * The blend is the page's own: each holding's typical weekly move times its
#     weight, S&P 500 trackers counted as zero, a force left out ("not
#     measured for every holding") when any holding lacks it. A test runs the
#     page's script against this in Node.
#   * Only tickers on record are read; anything else in ?p= is dropped, never
#     echoed. At most MAX_HOLDINGS.
#   * The canonical stays /xray: a shared mix is a view, not a new page.
#   * Past, not a forecast -- the card says so.

from __future__ import annotations

import io
import math
from typing import List, Optional, Tuple

from utils.xray_page import MAX_HOLDINGS

Mix = List[Tuple[str, float]]


def parse_mix(p: str, data: dict) -> Mix:
    """?p= -> [(ticker, weight)], weights summing to 1. Unknown tickers and
    bad weights are dropped; no weights at all means equal weight; a holding
    with no weight among weighted ones gets 10 (as the page does)."""
    known = set(data.get("s") or {}) | set(data.get("mkt") or [])
    picked: List[Tuple[str, Optional[float]]] = []
    for part in str(p or "")[:600].split(","):
        t, _, w = part.partition(":")
        t = t.strip().upper()
        if not t or t not in known or any(t == x for x, _ in picked):
            continue
        try:
            wf = float(w) if w.strip() else None
        except ValueError:
            continue
        if wf is not None and (not math.isfinite(wf) or wf <= 0):
            continue
        picked.append((t, wf))
        if len(picked) >= MAX_HOLDINGS:
            break
    if not picked:
        return []
    if all(w is None for _, w in picked):
        return [(t, 1 / len(picked)) for t, _ in picked]
    raw = [(t, 10.0 if w is None else w) for t, w in picked]
    total = sum(w for _, w in raw)
    return [(t, w / total) for t, w in raw]


def blend(data: dict, mix: Mix) -> List[dict]:
    """Per core force: {key, label, phrase, ok, value}."""
    mkt = set(data.get("mkt") or [])
    rows = []
    for i, (key, label, phrase) in enumerate(data["f"]):
        v, ok = 0.0, True
        for t, w in mix:
            if t in mkt:
                continue                          # the market itself: zero beyond the market
            r = data["s"][t][2][i]
            if r is None:
                ok = False
                break
            v += w * r[0]
        rows.append({"key": key, "label": label, "phrase": phrase, "ok": ok, "value": v if ok else 0.0})
    return rows


def biggest(rows: List[dict]) -> Optional[dict]:
    good = [r for r in rows if r["ok"]]
    return max(good, key=lambda r: abs(r["value"])) if good else None


def mix_query(mix: Mix) -> str:
    return ",".join(f"{t}:{round(100 * w, 1):g}" for t, w in mix)


def _names(mix: Mix, n: int = 4) -> str:
    ts = [t for t, _ in mix]
    return ", ".join(ts[:n]) + (f" +{len(ts) - n} more" if len(ts) > n else "")


def share_title(mix: Mix, rows: List[dict]) -> str:
    from utils.exposure_pages import fmt_pct
    top = biggest(rows)
    head = f"Portfolio X-ray: {_names(mix)}"
    if not top:
        return head
    label = top["label"] if top["label"].startswith("U.S.") else top["label"][0].lower() + top["label"][1:]
    return f"{head} — biggest driver: {label}, {fmt_pct(top['value'])} beyond the market"


def share_description(rows: List[dict]) -> str:
    top = biggest(rows)
    if not top:
        return "How this mix has moved with interest rates, inflation, the dollar, oil and credit."
    return (f"In weeks when {top['phrase']}, this mix has typically moved beyond the stock market as shown. "
            "Measured over three years of weekly returns. The past, not a forecast.")


def xray_og_png(mix: Mix, rows: List[dict], as_of: str) -> bytes:
    from PIL import Image, ImageDraw

    from utils.exposure_pages import _date, fmt_pct
    from utils.og_image import BG, BRAND, DIM, DOWN, INK, LINE, UP, W, H, _font, _minus

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((64, 48), "UNSTRUCTURED ALPHA · PORTFOLIO X-RAY", fill=BRAND, font=_font(26))
    names = _names(mix, 6)
    d.text((64, 96), names if len(names) <= 44 else names[:43] + "…", fill=INK, font=_font(54))
    d.text((64, 176), "This mix's typical weekly move with each force, beyond the market",
           fill=DIM, font=_font(28))
    good = [abs(r["value"]) for r in rows if r["ok"]]
    scale = max(good + [0.25])
    top, row = 248, 62
    bar_l, bar_r = 560, 960
    mid = (bar_l + bar_r) // 2
    for i, r in enumerate(rows):
        y = top + i * row
        d.line([(64, y - 8), (W - 64, y - 8)], fill=LINE, width=1)
        d.text((64, y + 6), r["label"], fill=INK, font=_font(34))
        d.rounded_rectangle([bar_l, y + 18, bar_r, y + 34], radius=8, fill="#132c49")
        d.line([(mid, y + 12), (mid, y + 40)], fill=DIM, width=2)
        if not r["ok"]:
            d.text((W - 64, y + 10), "not measured", fill=DIM, font=_font(28), anchor="ra")
            continue
        half = (bar_r - bar_l) / 2
        w = half * min(1.0, abs(r["value"]) / scale)
        up = r["value"] >= 0
        x0, x1 = (mid, mid + w) if up else (mid - w, mid)
        if w >= 1:
            d.rounded_rectangle([x0, y + 18, x1, y + 34], radius=8, fill=UP if up else DOWN)
        d.text((W - 64, y + 6), _minus(fmt_pct(r["value"])), fill=INK, font=_font(34), anchor="ra")
    d.text((64, H - 62), _minus(f"Weighted average of each holding's reading. Data through {_date(as_of)}. "
                                "The past, not a forecast."), fill=DIM, font=_font(24))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
