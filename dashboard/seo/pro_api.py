"""Read-only, rate-limited Pro API backed only by persisted score snapshots."""

from __future__ import annotations

import re
import threading

from fastapi import APIRouter, Header, HTTPException, Query, Response
from sqlalchemy import select


router = APIRouter(prefix="/api/v1", tags=["pro-api"])

_API_RATE_LIMIT = 120
_API_RATE_WINDOW = 3600
_STORE_READY = False
_STORE_LOCK = threading.Lock()


def _score_store():
    """Initialize the shared schema at most once, then return the score store."""
    global _STORE_READY
    from utils import db

    if not _STORE_READY:
        with _STORE_LOCK:
            if not _STORE_READY:
                db.init_db()
                _STORE_READY = True
    return db.engine, db.score_snapshots


def _authorize(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="A valid Pro API bearer key is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from utils.api_access import authenticate_api_key

    principal = authenticate_api_key(authorization.split(" ", 1)[1].strip())
    if not principal:
        raise HTTPException(
            status_code=401,
            detail="The API key is invalid, revoked, or no longer has Pro access.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from utils.ratelimit import check

    allowed, retry_after = check(
        f"pro_api:{principal['key_id']}", _API_RATE_LIMIT, _API_RATE_WINDOW
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="API rate limit exceeded.",
            headers={"Retry-After": str(retry_after)},
        )
    return principal


def _normalize_symbol(value: str) -> str:
    symbol = str(value or "").upper().strip().lstrip("$")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,14}", symbol):
        raise HTTPException(status_code=400, detail="Invalid ticker symbol.")
    return symbol


def _case_label(score: float) -> str:
    if score >= 65:
        return "BULLISH"
    if score <= 35:
        return "BEARISH"
    return "NEUTRAL"


def _latest_scores(symbols: list[str]) -> tuple[list[dict], list[str]]:
    engine, score_snapshots = _score_store()
    with engine.begin() as conn:
        rows = conn.execute(
            select(score_snapshots)
            .where(score_snapshots.c.ticker.in_(symbols))
            .order_by(
                score_snapshots.c.snapshot_date.desc(),
                score_snapshots.c.id.desc(),
            )
        ).mappings().all()

    latest: dict[str, dict] = {}
    for row in rows:
        latest.setdefault(str(row["ticker"]).upper(), dict(row))

    scores = [
        {
            "ticker": symbol,
            "score": round(float(latest[symbol]["score"]), 1),
            "case": latest[symbol].get("case")
            or _case_label(float(latest[symbol]["score"])),
            "conviction": latest[symbol].get("conviction"),
            "score_kind": latest[symbol].get("score_kind") or "full",
            "as_of": latest[symbol]["snapshot_date"],
            "source": "persisted_score_snapshot",
        }
        for symbol in symbols
        if symbol in latest
    ]
    missing = [symbol for symbol in symbols if symbol not in latest]
    return scores, missing


def _response_headers(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-RateLimit-Limit"] = str(_API_RATE_LIMIT)
    response.headers["X-RateLimit-Window"] = str(_API_RATE_WINDOW)


@router.get("")
def index(
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict:
    _authorize(authorization)
    _response_headers(response)
    return {
        "version": "v1",
        "endpoints": [
            "/api/v1/scores/{ticker}",
            "/api/v1/scores?tickers=AAPL,MSFT",
        ],
        "data_policy": (
            "Persisted real score snapshots only; unavailable scores are never estimated."
        ),
    }


@router.get("/scores")
def scores(
    response: Response,
    tickers: str = Query(..., min_length=1, max_length=400),
    authorization: str | None = Header(default=None),
) -> dict:
    _authorize(authorization)
    raw_symbols = [part for part in tickers.split(",") if part.strip()]
    symbols = list(dict.fromkeys(_normalize_symbol(part) for part in raw_symbols))
    if not symbols:
        raise HTTPException(status_code=400, detail="Provide at least one ticker.")
    if len(symbols) > 25:
        raise HTTPException(status_code=400, detail="A batch may contain at most 25 tickers.")
    data, missing = _latest_scores(symbols)
    _response_headers(response)
    return {
        "data": data,
        "missing": missing,
        "count": len(data),
        "data_policy": (
            "Persisted real score snapshots only; missing tickers are not estimated."
        ),
    }


@router.get("/scores/{symbol}")
def score(
    symbol: str,
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict:
    _authorize(authorization)
    ticker = _normalize_symbol(symbol)
    data, _ = _latest_scores([ticker])
    if not data:
        raise HTTPException(
            status_code=404,
            detail=f"No trustworthy persisted score snapshot is available for {ticker}.",
        )
    _response_headers(response)
    return {
        "data": data[0],
        "data_policy": (
            "Persisted real score snapshot; no on-request scoring or estimation."
        ),
    }
