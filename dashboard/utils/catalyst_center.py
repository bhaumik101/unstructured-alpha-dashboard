"""Live macro calendar, portfolio catalyst ranking, and private event plans."""

from __future__ import annotations

from datetime import date, datetime, timezone
import re
from typing import Iterable

import streamlit as st
from sqlalchemy import select

from utils.db import catalyst_plans, engine, upsert_stmt
from utils.resilience import resilient_get


FRED_RELEASE_DATES_URL = "https://api.stlouisfed.org/fred/releases/dates"
VALID_PLAN_STATUSES = {"planned", "reviewed"}

# Ordered from more specific to broader phrases. The FRED response supplies the
# authoritative release name and date; this mapping only selects high-impact
# releases and attaches the product's already-documented signal families.
RELEASE_RULES = (
    {
        "match": ("consumer price index",),
        "label": "Consumer Price Index",
        "category": "Inflation",
        "signals": ("tips_breakeven", "ten_year_yield", "hy_spread"),
    },
    {
        "match": ("employment situation",),
        "label": "Employment Situation",
        "category": "Labor",
        "signals": ("jobless_claims", "retail_sales", "consumer_sentiment"),
    },
    {
        "match": ("gross domestic product",),
        "label": "Gross Domestic Product",
        "category": "Growth",
        "signals": ("ism_pmi", "retail_sales", "durable_goods"),
    },
    {
        "match": ("personal income and outlays",),
        "label": "Personal Income and Outlays",
        "category": "Inflation",
        "signals": ("tips_breakeven", "ten_year_yield", "consumer_sentiment"),
    },
    {
        "match": ("advance monthly sales for retail",),
        "label": "Retail Sales",
        "category": "Consumer",
        "signals": ("retail_sales", "consumer_sentiment", "jobless_claims"),
    },
    {
        "match": ("new residential construction",),
        "label": "Housing Starts",
        "category": "Housing",
        "signals": ("housing_starts", "lumber_futures", "ten_year_yield"),
    },
    {
        "match": ("durable goods manufacturers", "manufacturers' shipments, inventories"),
        "label": "Durable Goods",
        "category": "Growth",
        "signals": ("durable_goods", "ism_pmi", "rail_traffic"),
    },
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:limit]


def _clean_body(value: object, limit: int) -> str:
    """Preserve intentional paragraphs while removing control whitespace."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in str(value or "").splitlines()]
    return "\n".join(lines).strip()[:limit]


def _rule_for(name: str) -> dict | None:
    normalized = str(name or "").lower()
    for rule in RELEASE_RULES:
        if any(fragment in normalized for fragment in rule["match"]):
            return rule
    return None


def parse_fred_release_calendar(
    payload: dict, *, start: date, end: date
) -> list[dict]:
    """Normalize and deduplicate the high-impact portion of a FRED response."""
    events: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in (payload or {}).get("release_dates") or []:
        try:
            event_day = date.fromisoformat(str(raw.get("date")))
        except (TypeError, ValueError):
            continue
        if event_day < start or event_day > end:
            continue
        rule = _rule_for(str(raw.get("release_name") or ""))
        if not rule:
            continue
        dedupe_key = (rule["label"], event_day.isoformat())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        release_id = int(raw.get("release_id") or 0)
        events.append({
            "event_key": f"macro:{release_id}:{event_day.isoformat()}",
            "event_type": "macro",
            "date": event_day,
            "date_str": event_day.isoformat(),
            "title": rule["label"],
            "official_name": str(raw.get("release_name") or rule["label"]),
            "category": rule["category"],
            "signals": list(rule["signals"]),
            "release_id": release_id,
            "source": "FRED release calendar",
            "source_url": f"https://fred.stlouisfed.org/release?rid={release_id}" if release_id else "https://fred.stlouisfed.org/releases/calendar",
        })
    events.sort(key=lambda row: (row["date"], row["title"]))
    return events


@st.cache_data(ttl=21_600, show_spinner=False, max_entries=8)
def fetch_fred_release_calendar(
    start: str, end: str, api_key: str = ""
) -> dict:
    """Fetch official future release dates; failures stay explicitly unavailable."""
    try:
        start_day = date.fromisoformat(str(start)[:10])
        end_day = date.fromisoformat(str(end)[:10])
    except ValueError:
        return {"available": False, "events": [], "error": "InvalidDateRange"}
    if not api_key:
        return {"available": False, "events": [], "error": "MissingAPIKey"}
    try:
        response = resilient_get(
            FRED_RELEASE_DATES_URL,
            provider="fred",
            params={
                "api_key": api_key,
                "file_type": "json",
                "realtime_start": start_day.isoformat(),
                "realtime_end": end_day.isoformat(),
                "order_by": "release_date",
                "sort_order": "asc",
                "include_release_dates_with_no_data": "true",
                "limit": 1000,
            },
            timeout=12,
        )
        response.raise_for_status()
        events = parse_fred_release_calendar(
            response.json(), start=start_day, end=end_day
        )
        return {
            "available": True,
            "events": events,
            "error": None,
            "fetched_at": _now(),
            "source": "Federal Reserve Bank of St. Louis FRED API",
        }
    except Exception as exc:
        return {
            "available": False,
            "events": [],
            "error": type(exc).__name__,
            "fetched_at": _now(),
        }


def build_portfolio_catalysts(
    holdings: Iterable[dict],
    macro_events: Iterable[dict],
    earnings_by_ticker: dict[str, dict | None],
    ticker_signal_map: dict[str, Iterable[str]],
    *,
    today: date | None = None,
) -> list[dict]:
    """Rank dated events by proximity and saved portfolio weight affected."""
    day = today or datetime.now(timezone.utc).date()
    positions = [
        {
            "ticker": str(row.get("ticker", "")).upper().strip(),
            "weight": max(0.0, float(row.get("weight_pct", row.get("weight", 0)) or 0)),
        }
        for row in (holdings or [])
        if str(row.get("ticker", "")).strip()
    ]
    catalysts: list[dict] = []

    for event in macro_events or []:
        event_day = event.get("date")
        if not isinstance(event_day, date):
            try:
                event_day = date.fromisoformat(str(event.get("date_str")))
            except ValueError:
                continue
        days_until = (event_day - day).days
        if days_until < 0:
            continue
        relevant = set(event.get("signals") or [])
        affected = [
            row for row in positions
            if relevant.intersection(set(ticker_signal_map.get(row["ticker"], []) or []))
        ]
        exposure = round(sum(row["weight"] for row in affected), 1)
        if not affected:
            continue
        catalyst = dict(event)
        catalyst.update({
            "days_until": days_until,
            "affected_weight": exposure,
            "affected_tickers": [row["ticker"] for row in affected],
            "is_estimate": False,
            "priority": round(100 - min(days_until, 30) * 1.5 + min(exposure, 100) * 0.25, 1),
        })
        catalysts.append(catalyst)

    for row in positions:
        info = earnings_by_ticker.get(row["ticker"])
        if not info:
            continue
        event_day = info.get("date")
        if not isinstance(event_day, date):
            try:
                event_day = date.fromisoformat(str(event_day))
            except ValueError:
                continue
        days_until = (event_day - day).days
        if days_until < 0:
            continue
        catalysts.append({
            "event_key": f"earnings:{row['ticker']}:{event_day.isoformat()}",
            "event_type": "earnings",
            "date": event_day,
            "date_str": event_day.isoformat(),
            "title": f"{row['ticker']} Earnings",
            "official_name": f"{row['ticker']} expected earnings date",
            "category": "Company event",
            "signals": [],
            "source": "Market-data provider earnings calendar",
            "source_url": "",
            "days_until": days_until,
            "affected_weight": round(row["weight"], 1),
            "affected_tickers": [row["ticker"]],
            "is_estimate": bool(info.get("is_estimate", True)),
            "priority": round(108 - min(days_until, 30) * 2 + min(row["weight"], 50) * 0.35, 1),
        })

    catalysts.sort(key=lambda row: (-row["priority"], row["date"], row["title"]))
    return catalysts


def save_catalyst_plan(
    *,
    user_id: int,
    event_key: str,
    event_date: date | str,
    title: str,
    base_case: str = "",
    upside_case: str = "",
    downside_case: str = "",
    watch_for: str = "",
    status: str = "planned",
    outcome_notes: str = "",
) -> None:
    normalized_status = str(status).lower().strip()
    if normalized_status not in VALID_PLAN_STATUSES:
        raise ValueError("Invalid catalyst plan status.")
    key = _clean_text(event_key, 128)
    clean_title = _clean_text(title, 160)
    if not key or not clean_title:
        raise ValueError("An event key and title are required.")
    try:
        event_day = event_date if isinstance(event_date, date) else date.fromisoformat(str(event_date)[:10])
    except ValueError as exc:
        raise ValueError("A valid event date is required.") from exc
    now = _now()
    values = {
        "user_id": int(user_id),
        "event_key": key,
        "event_date": event_day.isoformat(),
        "title": clean_title,
        "base_case": _clean_body(base_case, 4000) or None,
        "upside_case": _clean_body(upside_case, 4000) or None,
        "downside_case": _clean_body(downside_case, 4000) or None,
        "watch_for": _clean_body(watch_for, 4000) or None,
        "status": normalized_status,
        "outcome_notes": _clean_body(outcome_notes, 4000) or None,
        "created_at": now,
        "updated_at": now,
    }
    stmt = upsert_stmt(catalyst_plans, ["user_id", "event_key"]).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "event_key"],
        set_={key: value for key, value in values.items() if key not in {"user_id", "event_key", "created_at"}},
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def get_catalyst_plan(user_id: int, event_key: str) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(catalyst_plans).where(
                catalyst_plans.c.user_id == int(user_id),
                catalyst_plans.c.event_key == str(event_key),
            )
        ).mappings().first()
    return dict(row) if row else None


def list_catalyst_plans(user_id: int) -> list[dict]:
    with engine.begin() as conn:
        rows = conn.execute(
            select(catalyst_plans)
            .where(catalyst_plans.c.user_id == int(user_id))
            .order_by(catalyst_plans.c.event_date.asc(), catalyst_plans.c.updated_at.desc())
        ).mappings().all()
    return [dict(row) for row in rows]
