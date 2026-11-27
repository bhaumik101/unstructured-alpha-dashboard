"""Walk-forward test of the EXTRA forces (styles, currencies, commodities, ...).

    python scripts/study_extras_oos.py            # writes /tmp/extras_oos.json

Same design as docs/RESEARCH_2026-11.md §7-8, for each extra force: before each
of three held-out years (52 weeks ending 2024-11, 2025-11, 2026-11), fit the
engine's extra model (market + five core forces + that one extra, labelled
with EXTRA_CLEAR_T exactly as the report does) on the prior 156 weeks; then in
the held-out year's big weeks for the extra (|move| > 1 sd of the fit window)
count how often the name's move beyond the market and the core forces pointed
the way the fitted slope said. Research only: nothing here runs in the app.
"""

from __future__ import annotations

import json
import logging
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from utils import exposure as ex  # noqa: E402
from utils.fetchers import _get_fred_key, fetch_fred, fetch_prices_batch  # noqa: E402

STOCKS = ("AAPL MSFT NVDA AMZN GOOGL META JPM BAC WFC C GS XOM CVX COP OXY SLB EOG HAL DVN EQT NEE DUK SO D AEP "
          "PG KO PEP WMT COST HD LOW DHI LEN NVR PHM CAT DE BA GE HON UNH JNJ PFE MRK ABBV LLY T VZ AMT PLD O "
          "SPG NEM FCX DOW LIN F GM TSLA INTC AMD KMI WMB MPC PSX VLO SCHW MET PRU").split()
FUNDS = ("QQQ IWM VXUS EEM EFA TLT IEF HYG LQD TIP GLD XLE XLF XLU XLK XLV XLP XLY XLI XLB XLRE ITB KBE GDX "
         "VNQ IWN EWJ FXI").split()
END = pd.Timestamp("2026-11-20")
OUT = Path("/tmp/extras_oos.json")


def fred(sid, s, e):
    key = _get_fred_key()
    x = fetch_fred(sid, s, e, api_key=key) if key else None
    return x if x is not None and len(x) else ex.fetch_fred_public(sid, s, e)


def main() -> int:
    s, e = "2018-06-01", str(END.date())
    names = STOCKS + FUNDS
    px = dict(fetch_prices_batch(tuple(sorted(set(names) | {ex.MARKET_TICKER} | set(ex.EXTRA_PRICE_TICKERS))), s, e) or {})
    mkt = ex.to_weekly_returns(ex._clean(px.get(ex.MARKET_TICKER)))
    core = {f.key: ex.to_changes(fred(f.series_id, s, e), f.transform) for f in ex.FACTORS}
    extra = {}
    for f in ex.EXTRA_FACTORS:
        try:
            if f.source == "spread":
                a, b = ex._spread_legs(f)
                ch = (ex.to_weekly_returns(px.get(a)) - ex.to_weekly_returns(px.get(b))).dropna()
            else:
                lv = px.get(f.series_id) if f.source == "price" else fred(f.series_id, s, e)
                ch = ex.to_changes(lv, f.transform)
            if len(ch) > 300 and not ex.spike_dominated(ch):
                extra[f.key] = ch
        except Exception:
            continue
    print("extras measured:", sorted(extra), file=sys.stderr)
    by_key = {f.key: f for f in ex.EXTRA_FACTORS}
    rows = []
    for t in names:
        y = ex.to_weekly_returns(ex._clean(px.get(t)))
        if y.empty:
            continue
        for xk, xch in extra.items():
            frame = pd.concat({"__y__": y, "__mkt__": mkt, **core, xk: xch}, axis=1).dropna()
            for fold_end in (END, END - pd.Timedelta(weeks=52), END - pd.Timedelta(weeks=104)):
                f_all = frame[frame.index <= fold_end]
                if len(f_all) < 52 + 150:
                    continue
                test, fit_f = f_all.iloc[-52:], f_all.iloc[-52 - 156:-52]
                fit = ex._fit_on_frame(fit_f, "__y__", ex.FACTORS + (by_key[xk],), ex.MIN_WEEKS, ex.EXTRA_CLEAR_T)
                r = (fit.get("readings") or {}).get(xk)
                if not r:
                    continue
                ks = [f.key for f in ex.FACTORS] + [xk]
                X = np.column_stack([np.ones(len(fit_f)), fit_f[["__mkt__"] + ks].to_numpy()])
                b = np.linalg.lstsq(X, fit_f["__y__"].to_numpy(), rcond=None)[0]
                Xt = test[["__mkt__"] + ks].to_numpy()
                beyond = test["__y__"].to_numpy() - b[0] - b[1] * Xt[:, 0] - Xt[:, 1:-1] @ b[2:-1]
                fx = Xt[:, -1]
                big = np.abs(fx) > fit_f[xk].std()
                hits = int(np.sum(np.sign(beyond[big]) == np.sign(b[-1] * fx[big])))
                rows.append({"t": t, "kind": "stock" if t in STOCKS else "fund", "k": xk, "fold": str(fold_end.date()),
                             "ev": r["evidence"], "tstat": r["t"], "big": int(big.sum()), "hits": hits})
    OUT.write_text(json.dumps(rows))
    print("rows", len(rows), "->", OUT, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
