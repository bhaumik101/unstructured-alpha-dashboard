"""Calibration harness for compute_backtested_pcs (PR for handoff item #1).

Re-derives the before/after table quoted in that function's docstring.
Runs ~6 min; needs no API keys and no database -- it is pure simulation.

Both formulas are evaluated on IDENTICAL simulated data: the old one is
reconstructed from significance_rate/avg_abs_r, which the function still
returns, so no code has to be duplicated or re-run.
"""
import numpy as np, pandas as pd, sys
sys.path.insert(0, '.')
from utils.analysis import compute_backtested_pcs

N_OBS, N_TICKERS, TRIALS = 101, 5, 3000     # n=101 matches #211's ig_credit/NVDA sample
IDX = pd.date_range("2024-01-01", periods=N_OBS + 1, freq="W")
TK = [f"T{i}" for i in range(N_TICKERS)]
SD = 0.02                                    # both components share a scale, so mixing weight == corr

def old_pcs(res):
    return int(round(max(1.0, min(10.0, 1 + res["significance_rate"] * 5 + res["avg_abs_r"] * 4))))

def run(rho, seed):
    rng = np.random.default_rng(seed)
    old, new, obs_r = [], [], []
    for _ in range(TRIALS):
        se = rng.normal(0, SD, N_OBS + 1)
        sig = pd.Series(np.exp(np.cumsum(se)), index=IDX)
        prices = [
            pd.Series(np.exp(np.cumsum(
                rho * se + np.sqrt(max(0.0, 1 - rho ** 2)) * rng.normal(0, SD, N_OBS + 1)
            )), index=IDX)
            for _ in range(N_TICKERS)
        ]
        r = compute_backtested_pcs(sig, prices, tickers=TK)
        if r["backtested"]:
            old.append(old_pcs(r)); new.append(r["pcs"]); obs_r.append(r["avg_abs_r"])
    return np.array(old), np.array(new), np.array(obs_r)

print(f"{TRIALS} trials/row · n={N_OBS} weekly obs · {N_TICKERS} tickers per signal")
print(f"{'true rho':>8} {'obs |r|':>8} │ {'OLD mean':>8} {'p95':>4} {'P(>=3)':>7} │ "
      f"{'NEW mean':>8} {'p95':>4} {'P(>=3)':>7}")
print("─" * 74)
for rho in [0.0, 0.10, 0.19, 0.25, 0.30, 0.50]:
    o, n, ar = run(rho, 20260826)
    tag = "  <- #211's strongest observed" if rho == 0.19 else ""
    print(f"{rho:>8.2f} {ar.mean():>8.3f} │ {o.mean():>8.2f} {np.percentile(o,95):>4.0f} "
          f"{100*(o>=3).mean():>6.1f}% │ {n.mean():>8.2f} {np.percentile(n,95):>4.0f} "
          f"{100*(n>=3).mean():>6.1f}%{tag}")
