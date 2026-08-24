#!/usr/bin/env python3
"""
Coverage Ratchet Checker (T7).

Ensures that current coverage does not regress below the baseline
frozen at T7. The baseline is stored in artifacts/test-refactor/t7/coverage/baseline.json
and contains line_coverage.

Usage:
    python scripts/verification/check_coverage_ratchet.py --baseline artifacts/test-refactor/t7/coverage/baseline.json --current artifacts/ci/coverage-gate/coverage.json
"""

import argparse
import json
import sys
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description="Coverage ratchet checker")
    parser.add_argument("--baseline", required=True, help="Baseline json path")
    parser.add_argument("--current", required=True, help="Current coverage json path")
    parser.add_argument("--tolerance", type=float, default=0.0, help="Allowed drop (default 0)")
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    current_path = Path(args.current)

    if not baseline_path.exists():
        print(f"FAIL: baseline not found: {baseline_path}", file=sys.stderr)
        return 1
    if not current_path.exists():
        print(f"FAIL: current coverage not found: {current_path}", file=sys.stderr)
        return 1

    baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    current = json.loads(current_path.read_text(encoding='utf-8'))

    baseline_cov = baseline.get("line_coverage") or baseline.get("totals", {}).get("percent_covered") or 0
    # current coverage json from pytest-cov has structure {"totals": {"percent_covered": 82, ...}}
    if "totals" in current:
        current_cov = current["totals"].get("percent_covered", 0)
    else:
        current_cov = current.get("line_coverage", 0)

    print(f"Baseline: {baseline_cov:.2f}%")
    print(f"Current:  {current_cov:.2f}%")
    threshold = baseline.get("threshold", baseline_cov)
    # Ratchet: current may stay equal or increase; never decrease.
    # Allow tiny floating epsilon (0.02%) for rounding between baseline snapshot and live run.
    epsilon = 0.02
    if current_cov + args.tolerance + epsilon < baseline_cov:
        print(f"FAIL: coverage regressed below baseline ({current_cov:.2f} < {baseline_cov:.2f})", file=sys.stderr)
        return 1
    if current_cov + epsilon < threshold:
        print(f"FAIL: coverage below threshold ({current_cov:.2f} < {threshold:.2f})", file=sys.stderr)
        return 1
    print(f"PASS: coverage ratchet OK (threshold {threshold:.2f}%)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
