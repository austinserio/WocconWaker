#!/usr/bin/env python3
"""Validate correspondence registry v2 and alignment sidecar."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from woccon_reconstruction.comparative_utils import (  # noqa: E402
    DEFAULT_ALIGNMENTS,
    DEFAULT_REGISTRY,
    load_alignments,
    load_registry,
    registry_rules,
)

RULE_KINDS = {"orthographic", "sister_wc", "diachronic_psc", "diachronic_ps"}
STATUSES = {"established", "tentative", "singleton"}
NON_DEFAULT_ENVS = {
    "word-initial",
    "word-medial",
    "vowel_correspondence",
    "attested_inventory",
    "ps_retention",
}
ID_PATTERN = re.compile(r"^[a-z0-9_]+$")


def validate_rule(row: Dict[str, Any], index: int) -> List[str]:
    errors: List[str] = []
    p = f"rules[{index}]"
    for key in ("id", "rule_kind", "correspondence_status", "source"):
        if not row.get(key):
            errors.append(f"{p}: missing {key!r}")
    if row.get("rule_kind") not in RULE_KINDS:
        errors.append(f"{p}: invalid rule_kind")
    if row.get("correspondence_status") not in STATUSES:
        errors.append(f"{p}: invalid correspondence_status")
    rid = row.get("id")
    if rid and not ID_PATTERN.match(str(rid)):
        errors.append(f"{p}: invalid id {rid!r}")
    if row.get("rule_kind") == "sister_wc" and row.get("correspondence_status") == "established":
        n = len(row.get("example_cognate_ids") or [])
        if n < 2 and not row.get("provenance_text"):
            errors.append(f"{p}: established sister_wc needs >=2 examples or provenance_text")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--alignments", type=Path, default=DEFAULT_ALIGNMENTS)
    args = parser.parse_args()

    errors: List[str] = []
    warnings: List[str] = []

    envelope = load_registry(args.registry)
    if envelope.get("version", 1) < 2:
        warnings.append("registry version < 2 (run upgrade_correspondence_registry.py)")

    rules = registry_rules(envelope)
    for i, row in enumerate(rules):
        errors.extend(validate_rule(row, i))

    # Environment-specific rules with aligned examples
    align_data = load_alignments(args.alignments)
    alignment_rows = align_data.get("alignments") or []
    rule_used_in_align: Counter[str] = Counter()
    for row in alignment_rows:
        for aln in row.get("alignments") or []:
            rid = aln.get("rule_id")
            if rid:
                rule_used_in_align[rid] += 1

    env_specific_with_examples = 0
    for r in rules:
        env = r.get("environment") or "default"
        if env == "default":
            continue
        rid = r.get("id")
        ex = len(r.get("example_cognate_ids") or [])
        used = rule_used_in_align.get(rid or "", 0)
        has_provenance = bool(r.get("provenance_text"))
        if ex >= 2 or used >= 2 or (has_provenance and r.get("correspondence_status") == "established"):
            env_specific_with_examples += 1

    if env_specific_with_examples < 5:
        errors.append(
            f"expected >=5 environment-specific rules with >=2 examples/alignments, got {env_specific_with_examples}"
        )

    aligned_pairs = sum(1 for r in alignment_rows if r.get("ruled_count", 0) > 0)
    if aligned_pairs < 10:
        errors.append(f"expected >=10 App.1 pairs with alignments, got {aligned_pairs}")

    by_env = Counter(r.get("environment") or "default" for r in rules)
    print("Registry rules:", len(rules))
    print("By environment:", dict(sorted(by_env.items())))
    print("Aligned pairs with rules:", aligned_pairs)

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"OK: registry v{envelope.get('version', 1)} validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
