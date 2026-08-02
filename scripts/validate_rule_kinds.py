#!/usr/bin/env python3
"""Validate correspondence registry.json against schema and Phase 2 expectations."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "woccon_language/correspondences/registry.json"
DEFAULT_SCHEMA = ROOT / "woccon_language/correspondences/schema.json"
DEFAULT_RULES = ROOT / "woccon_language/rules_unified.json"

RULE_KINDS = {"orthographic", "sister_wc", "diachronic_psc", "diachronic_ps"}
STATUSES = {"established", "tentative", "singleton"}
DIRECTIONS = {
    "w_to_c",
    "c_to_w",
    "psc_to_w",
    "ps_to_w",
    "lawson_to_w",
    "bidirectional",
    None,
}
ID_PATTERN = __import__("re").compile(r"^[a-z0-9_]+$")

CORRESPONDENCE_KEYWORDS = [
    "correspondence",
    "nasal vowel",
    "long oral",
    "defective",
    "*r",
    "proto-siouan",
    "proto siouan",
]


def validate_rule(row: Dict[str, Any], index: int) -> List[str]:
    errors: List[str] = []
    prefix = f"rules[{index}]"
    for key in ("id", "rule_kind", "correspondence_status", "source"):
        if not row.get(key):
            errors.append(f"{prefix}: missing required field {key!r}")

    rid = row.get("id")
    if rid and not ID_PATTERN.match(str(rid)):
        errors.append(f"{prefix}: invalid id {rid!r}")

    rk = row.get("rule_kind")
    if rk not in RULE_KINDS:
        errors.append(f"{prefix}: invalid rule_kind {rk!r}")

    st = row.get("correspondence_status")
    if st not in STATUSES:
        errors.append(f"{prefix}: invalid correspondence_status {st!r}")

    if row.get("direction") not in DIRECTIONS:
        errors.append(f"{prefix}: invalid direction {row.get('direction')!r}")

    examples = row.get("example_cognate_ids")
    if examples is not None and not isinstance(examples, list):
        errors.append(f"{prefix}: example_cognate_ids must be a list")

    if rk == "sister_wc" and st == "established":
        n = len(examples or [])
        if n < 2 and not row.get("provenance_text"):
            errors.append(
                f"{prefix}: sister_wc established requires >=2 examples or provenance_text"
            )

    allowed = {
        "id",
        "rule_kind",
        "lhs",
        "rhs",
        "environment",
        "direction",
        "correspondence_status",
        "example_cognate_ids",
        "grammar_lineage",
        "source",
        "notes",
        "provenance_text",
    }
    extra = set(row.keys()) - allowed
    if extra:
        errors.append(f"{prefix}: unexpected keys {sorted(extra)}")

    return errors


def legacy_pairs_covered(registry: List[Dict[str, Any]], rules_path: Path) -> List[str]:
    errors: List[str] = []
    if not rules_path.is_file():
        return errors
    rules_doc = json.loads(rules_path.read_text(encoding="utf-8"))
    pairs = (
        rules_doc.get("phonology", {})
        .get("sound_correspondences", {})
        .get("Woccon_to_Catawba", [])
    )
    reg_keys = {
        (r.get("lhs"), r.get("rhs"))
        for r in registry
        if r.get("rule_kind") == "sister_wc" and r.get("lhs") and r.get("rhs")
    }
    for pair in pairs:
        lhs = pair.get("Woccon") or pair.get("woccon")
        rhs = pair.get("Catawba") or pair.get("catawba")
        if (lhs, rhs) not in reg_keys:
            errors.append(f"missing registry row for legacy pair Woccon {lhs!r} -> Catawba {rhs!r}")
    return errors


def untagged_correspondence_notes(rules_path: Path, registry: List[Dict[str, Any]]) -> List[str]:
    warnings: List[str] = []
    if not rules_path.is_file():
        return warnings
    rules_doc = json.loads(rules_path.read_text(encoding="utf-8"))
    notes = rules_doc.get("community_grammar_notes") or []
    covered_text = {r.get("provenance_text", "") for r in registry if r.get("provenance_text")}
    for note in notes:
        text = (note.get("text") or "").strip()
        if not text:
            continue
        lower = text.lower()
        if not any(k in lower for k in CORRESPONDENCE_KEYWORDS):
            continue
        if text not in covered_text and not any(text in c for c in covered_text if c):
            warnings.append(f"correspondence-ish grammar note not in registry: {text[:80]}...")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()

    if not args.registry.is_file():
        print(f"ERROR: missing {args.registry}", file=sys.stderr)
        return 1

    data = json.loads(args.registry.read_text(encoding="utf-8"))
    rules = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(rules, list):
        print("ERROR: registry must contain rules[]", file=sys.stderr)
        return 1

    errors: List[str] = []
    warnings: List[str] = []

    if data.get("version") != 1:
        errors.append("envelope: version must be 1")
    if not data.get("source"):
        errors.append("envelope: missing source")

    for i, row in enumerate(rules):
        errors.extend(validate_rule(row, i))

    errors.extend(legacy_pairs_covered(rules, args.rules))
    warnings.extend(untagged_correspondence_notes(args.rules, rules))

    sister_with_examples = sum(
        1
        for r in rules
        if r.get("rule_kind") == "sister_wc" and r.get("example_cognate_ids")
    )
    if sister_with_examples < 8:
        errors.append(
            f"expected >=8 sister_wc rules with cognate examples, got {sister_with_examples}"
        )

    by_kind = Counter(r.get("rule_kind") for r in rules)
    by_status = Counter(r.get("correspondence_status") for r in rules)
    print(f"Using schema: {args.schema.relative_to(ROOT) if args.schema.is_relative_to(ROOT) else args.schema}")
    print("Summary by rule_kind:")
    for k, v in sorted(by_kind.items()):
        print(f"  {k}: {v}")
    print("Summary by correspondence_status:")
    for k, v in sorted(by_status.items()):
        print(f"  {k}: {v}")
    print(f"Sister rules with cognate examples: {sister_with_examples}")

    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"OK: {len(rules)} correspondence rules validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
