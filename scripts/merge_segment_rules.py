#!/usr/bin/env python3
"""Merge rudes_segment_rules.json into correspondence registry."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_REGISTRY = ROOT / "woccon_language/correspondences/registry.json"
DEFAULT_SEGMENT = ROOT / "woccon_language/correspondences/rudes_segment_rules.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--segment", type=Path, default=DEFAULT_SEGMENT)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    segment = json.loads(args.segment.read_text(encoding="utf-8"))
    seg_rules = segment.get("rules") or []

    by_id = {r["id"]: r for r in registry.get("rules") or []}
    added = 0
    updated = 0
    for rule in seg_rules:
        rid = rule["id"]
        if rid in by_id:
            by_id[rid] = {**by_id[rid], **rule}
            updated += 1
        else:
            by_id[rid] = rule
            added += 1

    registry["rules"] = sorted(by_id.values(), key=lambda r: r.get("id", ""))
    registry["generated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    registry["generator"] = "merge_segment_rules"

    out = args.out or args.registry
    out.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {out}: added={added} updated={updated} total={len(registry['rules'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
