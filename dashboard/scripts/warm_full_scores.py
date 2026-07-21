#!/usr/bin/env python3
"""Run the safe full-score warm-up outside web-process startup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.score_warmup import DEFAULT_WARM_TICKERS, warm_full_scores


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="*", default=list(DEFAULT_WARM_TICKERS))
    parser.add_argument("--pause-seconds", type=float, default=0.75)
    args = parser.parse_args()
    report = warm_full_scores(args.tickers, pause_seconds=max(0.0, args.pause_seconds))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(item["success"] for item in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
