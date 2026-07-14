# utils/taxonomy.py
# Unstructured Alpha — Canonical Macro-Factor Taxonomy (single source of truth)
#
# WHY THIS EXISTS: the app had two problems the second audit called out.
#   1. The only grouping available was config.SIGNALS[*]["category"] — a
#      SECTOR-themed label (macro / energy / financials / ai_infrastructure …),
#      which is NOT a macro-factor family. "What is this portfolio's shared
#      exposure to real rates?" cannot be answered from sector categories.
#   2. Public pages rendered the raw enum via `category.title()`, producing
#      embarrassments like "Ai_Infrastructure" in the UI.
#
# This module fixes both by defining ONE canonical macro-factor taxonomy: every
# one of the 47 signals maps to exactly one FACTOR FAMILY (Rates, Liquidity,
# Credit, Growth, Labor, Consumer, Housing, Inflation, Energy, Volatility &
# Positioning, Capex & Technology). A single test guarantees no signal is
# orphaned and no mapping points at an unknown family, so this stays correct as
# signals are added. Every surface (score attribution, portfolio X-ray, ticker
# pages, signal pages, methodology) should read factor families from here.
#
# Pure data + pure helpers; no Streamlit / DB. Unit-tested against the real
# SIGNALS registry (every id mapped, every family known).

from __future__ import annotations

# Ordered so views can render families in a stable, sensible order.
FACTOR_FAMILIES: dict[str, dict] = {
    "rates":       {"name": "Rates",                    "short": "Rates"},
    "liquidity":   {"name": "Liquidity",                "short": "Liquidity"},
    "credit":      {"name": "Credit",                   "short": "Credit"},
    "growth":      {"name": "Growth",                   "short": "Growth"},
    "labor":       {"name": "Labor",                    "short": "Labor"},
    "consumer":    {"name": "Consumer",                 "short": "Consumer"},
    "housing":     {"name": "Housing",                  "short": "Housing"},
    "inflation":   {"name": "Inflation",                "short": "Inflation"},
    "energy":      {"name": "Energy",                   "short": "Energy"},
    "volatility":  {"name": "Volatility & Positioning", "short": "Volatility"},
    "capex_tech":  {"name": "Capex & Technology",       "short": "Capex/Tech"},
}

# Canonical signal_id -> factor family. Built from each signal's actual
# economic meaning (not its sector tag). Keep this the ONLY place the mapping
# lives; tests enforce that it covers exactly the live SIGNALS registry.
SIGNAL_FACTOR: dict[str, str] = {
    # ── Rates (real & nominal, curve, Fed) ──
    "yield_curve": "rates", "ten_year_yield": "rates", "tips_breakeven": "rates",
    "fedspeaks_hawkishness": "rates",
    # ── Liquidity (money, dollar, lending availability) ──
    "m2_money_supply": "liquidity", "dollar_index": "liquidity",
    "bank_lending_standards": "liquidity",
    # ── Credit (spreads, delinquency) ──
    "hy_spread": "credit", "ig_credit": "credit", "credit_card_delinquency": "credit",
    # ── Growth (activity, orders, freight) ──
    "ism_pmi": "growth", "durable_goods": "growth", "manufacturers_new_orders": "growth",
    "ata_trucking": "growth", "rail_traffic": "growth", "shipping_index": "growth",
    "ny_fed_gscpi": "growth", "inventory_sales_ratio": "growth",
    "construction_spending": "growth",
    # ── Labor ──
    "jobless_claims": "labor", "layoffs_rate": "labor", "jolts_openings": "labor",
    "retail_job_openings": "labor",
    # ── Consumer ──
    "retail_sales": "consumer", "consumer_sentiment": "consumer",
    "ecommerce_share": "consumer", "retail_gasoline": "consumer",
    # ── Housing ──
    "housing_starts": "housing", "lumber_futures": "housing",
    # ── Inflation (goods/commodity price pressure) ──
    "food_cpi": "inflation", "copper": "inflation", "copper_gold_ratio": "inflation",
    # ── Energy ──
    "crude_oil": "energy", "crude_inventories": "energy", "natural_gas": "energy",
    "gas_storage": "energy", "uranium_proxy": "energy", "nuclear_generation": "energy",
    "power_demand_growth": "energy",
    # ── Volatility & Positioning ──
    "vix": "volatility", "vix_term_structure": "volatility",
    "put_call_ratio": "volatility", "retail_fear_gauge": "volatility",
    # ── Capex & Technology ──
    "hyperscaler_capex": "capex_tech", "semiconductor_etf": "capex_tech",
    "quantum_arxiv_velocity": "capex_tech", "fda_approval_velocity": "capex_tech",
}


def factor_family_of(signal_id: str) -> str:
    """Canonical factor-family id for a signal (defaults to 'growth' if unknown —
    tests ensure no live signal actually hits the default)."""
    return SIGNAL_FACTOR.get(signal_id, "growth")


def factor_family_name(family_id: str) -> str:
    """Display name for a factor family; never emits a raw enum."""
    fam = FACTOR_FAMILIES.get(family_id)
    if fam:
        return fam["name"]
    return (family_id or "").replace("_", " ").title() or "Macro"


def factor_family_name_of(signal_id: str) -> str:
    return factor_family_name(factor_family_of(signal_id))


# ─────────────────────────────────────────────────────────────────────────────
# Safe category display — the fix for "Ai_Infrastructure"-style raw-enum leaks.
# Prefer this over any `category.title()` at a call site.
# ─────────────────────────────────────────────────────────────────────────────

# Hand-maintained display names for the legacy sector `category` field, so the
# raw enum never reaches the UI even where sector categories are still shown.
_CATEGORY_DISPLAY: dict[str, str] = {
    "macro": "Macro & Liquidity",
    "energy": "Energy & Oil",
    "nuclear": "Power & Nuclear",
    "ai_infrastructure": "AI Infrastructure",
    "financials": "Financials & Credit",
    "healthcare": "Healthcare & Biotech",
    "consumer": "Consumer",
    "industrials": "Industrials",
}


def category_display(category_id: str, categories: dict | None = None) -> str:
    """
    Human display name for a legacy sector `category` id. Checks the passed
    CATEGORIES dict first (authoritative), then this module's fallback map, and
    only as a last resort tidies the raw id — but NEVER returns something like
    'Ai_Infrastructure' (the underscore-preserving `.title()` bug).
    """
    cid = (category_id or "").strip()
    if categories and cid in categories and (categories[cid] or {}).get("name"):
        return categories[cid]["name"]
    if cid in _CATEGORY_DISPLAY:
        return _CATEGORY_DISPLAY[cid]
    # Last resort: replace underscores AND fix acronym casing sensibly.
    tidy = cid.replace("_", " ").strip().title()
    return tidy.replace("Ai ", "AI ") if tidy else "Macro"
