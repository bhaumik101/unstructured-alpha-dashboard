#!/usr/bin/env python3
"""Run the deterministic production-readiness audit.

Usage:
    python scripts/production_audit.py
    python scripts/production_audit.py --json
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.production_audit import run_production_audit  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit deploy-critical production contracts.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    report = run_production_audit(ROOT)
    if args.json:
        print(report.to_json())
    else:
        headline = "PASS" if report.ok else "FAIL"
        print(f"Production audit: {headline}")
        for name, summary in report.checks.items():
            details = ", ".join(f"{key}={value}" for key, value in summary.items() if key != "status")
            print(f"  {name:16s} {summary['status'].upper():4s}  {details}")
        for finding in report.findings:
            location = finding.file
            if finding.line is not None:
                location = f"{location}:{finding.line}"
            print(f"  ERROR [{finding.check}] {finding.message} ({location})")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
