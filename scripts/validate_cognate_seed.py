#!/usr/bin/env python3
"""Validate rudes_carter_seed.json against schema and Phase 1 count expectations."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = ROOT / "woccon_language/cognate_sets/rudes_carter_seed.json"
DEFAULT_SCHEMA = ROOT / "woccon_language/cognate_sets/schema.json"

EVIDENCE_TIERS = {"certain", "partial", "possible", "ps_only", "loan", "unknown", "blend"}
DIALECTS = {"esaw", "saraw", "unknown", None}
ID_PATTERN = re.compile(r"^rudes2000_app[1-7]_[0-9]{3}$")

# Rudes claimed totals; App.1 OCR may be short — warn only
EXPECTED_COUNTS = {
    1: {"target": 58, "hard_min": 45, "hard_fail_below": None},
    2: {"target": 7, "hard_min": 7, "hard_fail_below": 7},
    3: {"target": 6, "hard_min": 4, "hard_fail_below": None},
    4: {"target": 10, "hard_min": 8, "hard_fail_below": None},
}


def validate_set(row: Dict[str, Any], index: int) -> List[str]:
    errors: List[str] = []
    prefix = f"sets[{index}]"
    required = {
        "id",
        "gloss",
        "evidence_tier",
        "rudes_appendix",
        "rudes_item",
        "citation_short",
        "source_path",
    }
    for key in required:
        if key not in row or row[key] in (None, ""):
            errors.append(f"{prefix}: missing required field {key!r}")

    rid = row.get("id")
    if rid and not ID_PATTERN.match(str(rid)):
        errors.append(f"{prefix}: invalid id {rid!r}")

    tier = row.get("evidence_tier")
    if tier not in EVIDENCE_TIERS:
        errors.append(f"{prefix}: invalid evidence_tier {tier!r}")

    if row.get("catawba_dialect") not in DIALECTS:
        errors.append(f"{prefix}: invalid catawba_dialect {row.get('catawba_dialect')!r}")

    if tier == "certain":
        if not row.get("gloss"):
            errors.append(f"{prefix}: certain row missing gloss")
        if not row.get("lawson_form") and not row.get("woccon_reconstituted"):
            errors.append(f"{prefix}: certain row missing lawson_form and woccon_reconstituted")

    if tier == "ps_only" and not row.get("proto_siouan") and not row.get("woccon_reconstituted"):
        errors.append(f"{prefix}: ps_only row missing proto_siouan and woccon_reconstituted")

    allowed = {
        "id",
        "gloss",
        "lawson_form",
        "lawson_form_corrected",
        "lawson_gloss",
        "woccon_reconstituted",
        "catawba_form",
        "catawba_dialect",
        "proto_siouan",
        "evidence_tier",
        "rudes_appendix",
        "rudes_item",
        "carter_set_ids",
        "notes",
        "citation_short",
        "source_path",
    }
    extra = set(row.keys()) - allowed
    if extra:
        errors.append(f"{prefix}: unexpected keys {sorted(extra)}")

    if not isinstance(row.get("carter_set_ids"), list):
        errors.append(f"{prefix}: carter_set_ids must be a list")

    return errors


def validate_envelope(data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if data.get("version") != 1:
        errors.append("envelope: version must be 1")
    if not data.get("source"):
        errors.append("envelope: missing source")
    sets = data.get("sets")
    if not isinstance(sets, list):
        errors.append("envelope: sets must be an array")
        return errors, warnings

    seen_ids: set[str] = set()
    by_app: Counter[int] = Counter()
    by_tier: Counter[str] = Counter()

    for i, row in enumerate(sets):
        if not isinstance(row, dict):
            errors.append(f"sets[{i}]: not an object")
            continue
        errors.extend(validate_set(row, i))
        rid = row.get("id")
        if rid in seen_ids:
            errors.append(f"sets[{i}]: duplicate id {rid}")
        seen_ids.add(rid)
        by_app[int(row.get("rudes_appendix") or 0)] += 1
        by_tier[str(row.get("evidence_tier") or "")] += 1

    for app, spec in EXPECTED_COUNTS.items():
        count = by_app.get(app, 0)
        target = spec["target"]
        hard_min = spec["hard_min"]
        hard_fail = spec["hard_fail_below"]
        if hard_fail is not None and count < hard_fail:
            errors.append(f"appendix {app}: count {count} < required {hard_fail}")
        elif count < hard_min:
            warnings.append(f"appendix {app}: count {count} < soft minimum {hard_min} (target {target})")
        elif count < target:
            warnings.append(f"appendix {app}: count {count} < Rudes target {target} (OCR shortfall likely)")

    print("Summary by evidence_tier:")
    for tier, n in sorted(by_tier.items()):
        print(f"  {tier}: {n}")
    print("Summary by appendix:")
    for app, n in sorted(by_app.items()):
        if app:
            print(f"  app {app}: {n}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Schema path (informational)")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    if not args.seed.is_file():
        print(f"ERROR: seed file not found: {args.seed}", file=sys.stderr)
        return 1
    if args.schema.is_file():
        print(f"Using schema: {args.schema.relative_to(ROOT)}")

    data = json.loads(args.seed.read_text(encoding="utf-8"))
    errors, warnings = validate_envelope(data)

    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)

    if errors:
        print(f"FAILED: {len(errors)} error(s)", file=sys.stderr)
        return 1
    if warnings and args.strict:
        print(f"FAILED: {len(warnings)} warning(s) in strict mode", file=sys.stderr)
        return 1
    print(f"OK: {len(data.get('sets') or [])} cognate sets validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
