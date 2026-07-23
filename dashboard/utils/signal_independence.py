"""Effective independent signals — how much a Confluence Score's agreement is
real evidence vs. the same macro factor counted several times.

The Confluence Score's headline claim is "N independent signals agree". But the
signals are NOT independent: VIX, put/call and the VIX term structure all proxy
market risk appetite; HY spreads, IG credit and loan-officer standards all proxy
credit conditions. Counting nine agreeing signals as nine pieces of evidence
overstates conviction when they are really two or three underlying bets — a flaw
a sophisticated user spots instantly, and the exact "N signals agree overstates
confidence" problem the combination literature (Rapach-Strauss-Zhou) warns about.

This module groups each signal by the latent macro FACTOR it proxies, then
computes an EFFECTIVE number of independent signals via the standard
diversification formula from portfolio theory:

    N_eff = (sum w)^2 / (w' C w)

with a block-correlation matrix C: same-factor signals share correlation
RHO_WITHIN, cross-factor signals share RHO_CROSS. For equal weights this reduces
to a closed form that needs only the per-factor counts — no estimated
correlation matrix, so it can't overfit thin history. RHO_WITHIN / RHO_CROSS are
economic PRIORS (documented below); they can be replaced by correlations
estimated from the long signal series once that is worth doing.

The output is additive: it never changes the Confluence Score value, only
qualifies its conviction with an honest "of N agreeing signals, ~k are
independent" read.
"""

from __future__ import annotations

# ── Latent-factor map ─────────────────────────────────────────────────────────
# Each signal assigned to the ONE macro factor it primarily proxies. Signals
# sharing a factor are treated as correlated evidence. This is a deliberate
# simplification (some signals load on several factors); it is transparent and
# reproducible, which matters more than false precision for a v1.
SIGNAL_FACTOR: dict[str, str] = {
    # market risk appetite / positioning
    "vix": "risk_appetite",
    "put_call_ratio": "risk_appetite",
    "vix_term_structure": "risk_appetite",
    "retail_fear_gauge": "risk_appetite",
    # credit conditions
    "hy_spread": "credit",
    "ig_credit": "credit",
    "bank_lending_standards": "credit",
    "credit_card_delinquency": "credit",
    # rates / duration / FX
    "yield_curve": "rates",
    "ten_year_yield": "rates",
    "dollar_index": "rates",
    # monetary policy / liquidity
    "m2_money_supply": "liquidity",
    "fedspeaks_hawkishness": "liquidity",
    # inflation
    "food_cpi": "inflation",
    "tips_breakeven": "inflation",
    # energy complex
    "crude_oil": "energy",
    "crude_inventories": "energy",
    "gas_storage": "energy",
    "natural_gas": "energy",
    "retail_gasoline": "energy",
    # industrial metals
    "copper": "metals",
    "copper_gold_ratio": "metals",
    # AI / power / nuclear thematic complex
    "uranium_proxy": "ai_power",
    "nuclear_generation": "ai_power",
    "power_demand_growth": "ai_power",
    "hyperscaler_capex": "ai_power",
    "semiconductor_etf": "ai_power",
    # real-economy activity / freight
    "ata_trucking": "activity",
    "rail_traffic": "activity",
    "ism_pmi": "activity",
    "durable_goods": "activity",
    "shipping_index": "activity",
    "construction_spending": "activity",
    "manufacturers_new_orders": "activity",
    # labor market
    "jobless_claims": "labor",
    "layoffs_rate": "labor",
    "jolts_openings": "labor",
    "retail_job_openings": "labor",
    # housing
    "housing_starts": "housing",
    "lumber_futures": "housing",
    # consumer
    "retail_sales": "consumer",
    "consumer_sentiment": "consumer",
    "ecommerce_share": "consumer",
    # supply chain
    "ny_fed_gscpi": "supply_chain",
    "inventory_sales_ratio": "supply_chain",
    # single-signal thematic factors (already independent)
    "quantum_arxiv_velocity": "thematic_quantum",
    "fda_approval_velocity": "thematic_health",
}

# Economic priors for the block-correlation matrix.
#   RHO_WITHIN: two signals proxying the SAME factor are moderately correlated.
#   RHO_CROSS:  different macro factors still share a small common (market) driver.
# Deliberately conservative: the whole point is to DISCOUNT over-counting, so a
# modest within-factor correlation already collapses a same-factor cluster hard.
RHO_WITHIN = 0.55
RHO_CROSS = 0.05


def factor_of(sig_id: str) -> str:
    """The latent factor a signal proxies. Unknown signals are treated as their
    own independent factor (conservative — never inflates correlation)."""
    return SIGNAL_FACTOR.get(sig_id, f"_own::{sig_id}")


def effective_signal_count(
    sig_ids,
    rho_within: float = RHO_WITHIN,
    rho_cross: float = RHO_CROSS,
) -> float:
    """Effective number of INDEPENDENT signals among `sig_ids`.

    N_eff = N^2 / (1' C 1) for equal weights, with a block-correlation C.

        1' C 1 = N + rho_within * sum_f n_f(n_f-1) + rho_cross * (N(N-1) - sum_f n_f(n_f-1))

    where n_f is the number of signals in factor f. Ranges from ~1 (all one
    factor) to ~N (all distinct factors, minus the small cross-correlation
    haircut). Returns 0.0 for an empty set.
    """
    ids = list(sig_ids or [])
    n = len(ids)
    if n == 0:
        return 0.0
    if n == 1:
        return 1.0

    counts: dict[str, int] = {}
    for sid in ids:
        f = factor_of(sid)
        counts[f] = counts.get(f, 0) + 1

    within_pairs = sum(c * (c - 1) for c in counts.values())   # ordered pairs, same factor
    total_pairs = n * (n - 1)                                  # ordered pairs, all
    cross_pairs = total_pairs - within_pairs

    quad = n + rho_within * within_pairs + rho_cross * cross_pairs
    if quad <= 0:
        return float(n)
    return (n * n) / quad


def independence(sig_ids) -> dict:
    """Full independence read for a set of agreeing signals.

    Returns raw count, effective independent count, the ratio (0-1), the number
    of distinct factors, and the per-factor breakdown — everything a UI needs to
    say "9 signals aligned across ~3 independent macro factors".
    """
    ids = list(sig_ids or [])
    raw = len(ids)
    eff = effective_signal_count(ids)
    counts: dict[str, int] = {}
    for sid in ids:
        f = factor_of(sid)
        # hide the synthetic per-signal factor label from display breakdowns
        key = f if not f.startswith("_own::") else "other"
        counts[key] = counts.get(key, 0) + 1
    return {
        "raw": raw,
        "effective": round(eff, 2),
        "ratio": round(eff / raw, 3) if raw else 0.0,
        "n_factors": len(counts),
        "factors": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
    }
