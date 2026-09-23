# utils/statement_import.py
# Unstructured Alpha — read holdings out of a brokerage statement
#
# WHY THIS EXISTS
# ---------------
# The CSV importer assumes the visitor can produce a positions export. Plenty
# cannot: a workplace plan often offers nothing but a PDF statement, an adviser
# gets a client's statement by email, and "export positions" is three menus
# deep at most brokers. Those people were being asked to retype a portfolio,
# and they leave instead.
#
# So this reads the positions table out of the file they already have.
#
# THE RULE THIS FILE IS BUILT AROUND: NEVER SILENTLY INVENT A HOLDING.
# Statement layouts vary wildly and no parser gets every one of them right.
# The failure that matters is not "we missed a row" — the visitor can see that
# and add it. It is "we confidently produced a portfolio that is not theirs",
# because every number downstream then describes something they never held, and
# the report gives no sign of it. So:
#
#   - a row is accepted only when a plausible ticker AND an amount appear on
#     the same line. A bare name with no symbol is reported, not guessed at;
#   - every accepted row carries the line it came from, and the page shows the
#     parsed list for the visitor to correct BEFORE anything is measured;
#   - totals, cash lines and account summaries are dropped rather than parsed;
#   - a PDF with no extractable text says so (it is a scan) instead of
#     returning an empty portfolio that looks like a parse with no holdings.

from __future__ import annotations

import re
from typing import List, Tuple

# Tokens that look like tickers in a statement and never are. Without this the
# header row of a Schwab export parses as holdings in CASH, NAV and YTD.
STOPWORDS = frozenset({
    "A", "I", "AM", "PM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF", "IN",
    "IS", "IT", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE",
    "ACCT", "ADR", "ALL", "AND", "APR", "AUG", "AVG", "BAL", "BUY", "CAD",
    "CASH", "CHF", "CLASS", "CLOSE", "COST", "CUSIP", "DATE", "DEC", "DIV",
    "END", "EPS", "EST", "ETF", "EUR", "FEB", "FEE", "FOR", "FUND", "GAIN",
    "GBP", "HIGH", "INC", "IRA", "JAN", "JPY", "JUL", "JUN", "LLC", "LOSS",
    "LOW", "LP", "LTD", "MAR", "MAY", "MTD", "NAV", "NET", "NEW", "NOV", "OCT",
    "OPEN", "PAGE", "PCT", "PLC", "PRICE", "QTY", "REIT", "ROTH", "SELL",
    "SEP", "SHRS", "SUB", "SUM", "SYM", "TERM", "TOTAL", "TRUST", "TYPE",
    "UNIT", "USD", "VALUE", "YTD", "YTM",
})

# Summary rows, not holdings.
#
# The first version matched /total/ anywhere on the line, which silently ate
# every holding a fund is named after: "VANGUARD TOTAL STOCK MKT ETF" and
# "VANGUARD TOTAL BOND MARKET ETF" both vanished from a Schwab statement and
# the parse came back with one holding out of three. Summary language belongs
# at the START of a row; only the cash sweep is matched anywhere, because
# brokers label it a dozen different ways mid-line.
_SKIP_HEAD = re.compile(
    r"^(total|subtotal|grand\s+total|account|net\s|beginning|ending|"
    r"cash\b|sweep|page\b|statement|portfolio\s+total|market\s+value)", re.I)
_SKIP_ANY = re.compile(
    r"\b(money\s*market|cash\s*(&|and)\s*cash|cash\s*sweep|"
    r"statement\s+period|page\s+\d+\s+of)\b", re.I)

# An amount: 1,234.56 / $1,234.56 / (1,234.56) / 1234.56. Two decimals or a
# thousands group -- a bare "100" is usually a share count.
_AMOUNT = re.compile(r"\(?\$?\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2})\)?")
_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s?%")
# A ticker as brokers print it: 1-5 capitals, optionally a class suffix.
_TICKER = re.compile(r"^[A-Z]{1,5}(?:[.\-][A-Z]{1,2})?$")
_PAREN_TICKER = re.compile(r"\(([A-Z]{1,5}(?:[.\-][A-Z]{1,2})?)\)")
_NUMERIC = re.compile(r"^[\$\(\)\-\d,.%\s]+$")
_CASH_LINE = re.compile(r"\b(cash|money\s*market|sweep)\b", re.I)


def extract_pdf_text(data: bytes) -> Tuple[str, str]:
    """(text, problem). `problem` is a sentence for the visitor, or "".

    A statement that is a scan has no text layer at all. Saying so is the whole
    point: an empty parse would otherwise read as "your statement has no
    holdings in it", which is both wrong and impossible to act on.
    """
    try:
        from pypdf import PdfReader
    except Exception:
        return "", ("PDF reading isn't available on this server right now. "
                    "Paste the holdings instead, or upload a CSV.")
    try:
        import io

        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages[:40]:          # statements are rarely longer
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                continue
        text = "\n".join(pages)
    except Exception:
        return "", ("That PDF couldn't be opened. If it is password-protected, "
                    "save an unlocked copy and try again.")
    if len(text.strip()) < 40:
        return "", ("That PDF has no text in it, which usually means it is a scan "
                    "or a photo. Paste the holdings instead, or upload a CSV.")
    return text, ""


def _amounts(line: str) -> List[float]:
    out = []
    for raw in _AMOUNT.findall(line):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def _fields(raw_line: str) -> List[str]:
    """Columns, not words. Two or more spaces (or a tab) separate them.

    Column position is the strongest signal a statement gives: the symbol is
    its own field, the description is the next one. Collapsing the line to
    single spaces first threw that away, and the ticker heuristic then picked
    the last word of the fund's NAME -- "APPLE" instead of "AAPL".
    """
    return [f.strip() for f in re.split(r"\s{2,}|\t", raw_line) if f.strip()]


def _ticker_and_name(raw_line: str, fields: List[str]) -> Tuple[str, str]:
    """(ticker, description) for one line, or ("", "") when nothing is certain."""
    # 1. A symbol in parentheses is unambiguous: "TOTAL BOND MKT ETF (BND)".
    parens = [t for t in _PAREN_TICKER.findall(raw_line) if t not in STOPWORDS]
    if parens:
        name = _PAREN_TICKER.sub("", raw_line).split("  ")[0].strip(" .-")
        return parens[0], name[:60]

    # 2. A field that is exactly a ticker -- the symbol column.
    for index, field in enumerate(fields):
        token = field.upper()
        if _TICKER.match(token) and token not in STOPWORDS:
            name = next((f for f in fields[index + 1:]
                         if not _NUMERIC.match(f) and len(f) > 3), "")
            return token, name[:60]

    # 3. Otherwise the line's first word, if it stands alone as a symbol.
    first = (raw_line.split() or [""])[0].upper()
    if _TICKER.match(first) and first not in STOPWORDS:
        return first, ""
    return "", ""


def parse_statement_text(text: str, *, max_rows: int = 60) -> Tuple[List[dict], List[str]]:
    """Positions out of statement text. Returns (rows, notes).

    Each row carries the line it came from so the page can show its work.
    """
    rows: List[dict] = []
    saw_named_rows = 0
    dropped_cash = False
    for raw_line in str(text or "").splitlines():
        raw_line = raw_line.rstrip()
        flat = " ".join(raw_line.split())
        if len(flat) < 6 or _SKIP_ANY.search(flat) or _SKIP_HEAD.match(flat):
            if _CASH_LINE.search(flat) and _AMOUNT.search(flat):
                dropped_cash = True
            continue
        amounts = _amounts(flat)
        if not amounts:
            continue
        fields = _fields(raw_line)
        ticker, name = _ticker_and_name(raw_line, fields)
        if not ticker:
            # A holding line with money on it but no symbol we trust. Counted
            # so the page can say what it could not read, never guessed at.
            if len(flat) > 20:
                saw_named_rows += 1
            continue

        percents = [p for p in (float(x) for x in _PERCENT.findall(flat)) if 0 < p <= 100]
        rows.append({
            "ticker": ticker,
            "name": name,
            "value": max(amounts),
            "weight_pct": percents[-1] if percents else None,
            "source_line": flat[:160],
        })
        if len(rows) >= max_rows:
            break

    merged: dict = {}
    for row in rows:
        if row["ticker"] in merged:
            # The same holding across two accounts on one statement.
            prior = merged[row["ticker"]]
            prior["value"] += row["value"]
            if prior["weight_pct"] is not None and row["weight_pct"] is not None:
                prior["weight_pct"] += row["weight_pct"]
        else:
            merged[row["ticker"]] = dict(row)

    out = list(merged.values())
    notes: List[str] = []
    if dropped_cash and out:
        # Cash has no exposure to measure, so it is left out and the rest are
        # rescaled. On a statement that is 13% cash that quietly changes what
        # every weight means, so it is said rather than assumed.
        notes.append("A cash or money-market line was left out, since cash has no "
                     "exposure to measure. The weights below describe the invested part.")
    if saw_named_rows and out:
        notes.append(f"{saw_named_rows} line(s) looked like holdings but carried no ticker "
                     f"symbol, so they were left out. Add them by name if they matter.")
    elif saw_named_rows and not out:
        notes.append("No ticker symbols were found. Some statements print fund names only; "
                     "add those by name using the search box.")
    return out, notes


def to_draft(rows: List[dict]) -> List[dict]:
    """Parsed rows -> the same draft list the search box builds.

    Weights come from the statement's own percentages when it prints them, and
    from market values otherwise. Either way they are rescaled to 100%, and the
    visitor sees and can change every one before anything is measured.
    """
    if not rows:
        return []
    have_percents = all(r.get("weight_pct") for r in rows)
    basis = [float(r["weight_pct"]) if have_percents else float(r.get("value") or 0.0)
             for r in rows]
    total = sum(basis)
    if total <= 0:
        basis = [1.0] * len(rows)
        total = float(len(rows))
    return [{"ticker": r["ticker"], "name": r.get("name") or "",
             "weight_pct": round(100.0 * b / total, 1)}
            for r, b in zip(rows, basis)]


SUPPORTED = ("pdf", "csv", "tsv", "txt")


def read_statement(filename: str, data: bytes) -> Tuple[List[dict], List[str]]:
    """Any supported upload -> (draft rows, notes). Never raises.

    CSV keeps going through utils/report_ui.parse_holdings_csv, which already
    understands brokerage exports column by column; this covers the files that
    have no columns at all.
    """
    name = str(filename or "").lower()
    if name.endswith(".pdf"):
        text, problem = extract_pdf_text(data)
        if problem:
            return [], [problem]
    else:
        try:
            text = data.decode("utf-8", "replace")
        except Exception:
            return [], ["That file couldn't be read as text."]

    rows, notes = parse_statement_text(text)
    if not rows and not notes:
        notes.append("No holdings were found in that file. It may not be a positions "
                     "statement — paste the holdings instead.")
    return to_draft(rows), notes
