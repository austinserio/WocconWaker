#!/usr/bin/env python3
"""Validate holdout split and report files."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SPLIT = ROOT / "data/lawson_holdout_split.json"
DEFAULT_REPORT = ROOT / "data/holdout_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    errors: list[str] = []
    if not args.split.is_file():
        errors.append(f"missing split file {args.split}")
    else:
        split = json.loads(args.split.read_text(encoding="utf-8"))
        train = set(split.get("train_ids") or [])
        dev = set(split.get("dev_ids") or [])
        test = set(split.get("test_ids") or split.get("holdout_ids") or [])
        if train & dev:
            errors.append("train and dev overlap")
        if train & test:
            errors.append("train and test overlap")
        if dev & test:
            errors.append("dev and test overlap")
        if len(test) < 10:
            errors.append(f"test too small: {len(test)}")
        if split.get("version", 1) >= 2 and not split.get("test_checksum"):
            errors.append("split missing test_checksum")

    if not args.report.is_file():
        errors.append(f"missing report file {args.report}")
    else:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if "metrics" not in report:
            errors.append("report missing metrics")
        if "rule_generality" not in report:
            errors.append("report missing rule_generality audit")
        if report.get("version", 1) >= 3:
            if "rule_ablation" not in report:
                errors.append("report missing rule_ablation table")
            headline = (report.get("metrics") or {}).get("headline") or {}
            if "baseline_segment_accuracy" not in headline and "baseline_segment_accuracy" not in (report.get("metrics") or {}):
                errors.append("report missing baseline_segment_accuracy")
        if not report.get("documented_failure_example"):
            errors.append("report missing documented failure example")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print("OK: holdout split and report validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
