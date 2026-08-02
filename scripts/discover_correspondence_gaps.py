#!/usr/bin/env python3
"""Flag cognate pairs and registry rows needing review after alignment pass."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from woccon_reconstruction.comparative_utils import (  # noqa: E402
    DEFAULT_ALIGNMENTS,
    DEFAULT_COGNATES,
    DEFAULT_REGISTRY,
    load_alignments,
    load_cognate_sets,
    load_registry,
    registry_rules,
)

DEFAULT_OUT = ROOT / "woccon_language/correspondences/gaps_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cognates", type=Path, default=DEFAULT_COGNATES)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--alignments", type=Path, default=DEFAULT_ALIGNMENTS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    registry = load_registry(args.registry)
    rules = registry_rules(registry)
    align_data = load_alignments(args.alignments)
    alignment_rows = align_data.get("alignments") or []

    low_coverage: List[Dict[str, Any]] = []
    for row in alignment_rows:
        if row.get("ruled_count", 0) == 0 and row.get("woccon_reconstituted") != row.get("catawba_form"):
            low_coverage.append(
                {
                    "cognate_id": row.get("cognate_id"),
                    "gloss": row.get("gloss"),
                    "note": "no registry rule matched alignment segments",
                }
            )

    singleton_rules = [
        {
            "id": r["id"],
            "lhs": r.get("lhs"),
            "rhs": r.get("rhs"),
            "environment": r.get("environment"),
            "example_count": len(r.get("example_cognate_ids") or []),
        }
        for r in rules
        if r.get("correspondence_status") == "singleton" and r.get("rule_kind") == "sister_wc"
    ]

    rule_usage: Counter[str] = Counter()
    for row in alignment_rows:
        for aln in row.get("alignments") or []:
            rid = aln.get("rule_id")
            if rid:
                rule_usage[rid] += 1

    unused_established = [
        r["id"]
        for r in rules
        if r.get("correspondence_status") == "established"
        and r.get("rule_kind") == "sister_wc"
        and r["id"] not in rule_usage
        and not r.get("provenance_text")
    ]

    report = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "low_coverage_pairs": low_coverage,
        "singleton_sister_rules": singleton_rules,
        "unused_established_rules": unused_established,
        "rule_usage_counts": dict(rule_usage.most_common()),
        "summary": {
            "low_coverage_count": len(low_coverage),
            "singleton_count": len(singleton_rules),
            "unused_established_count": len(unused_established),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    print("Summary:", report["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
