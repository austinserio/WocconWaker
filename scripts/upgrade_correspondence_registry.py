#!/usr/bin/env python3
"""Upgrade correspondence registry v1 → v2 with environment assignments."""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panel_api.services.rule_classifier import classify_correspondence_status  # noqa: E402
from scripts.tag_rule_kinds import link_cognate_examples  # noqa: E402
from woccon_reconstruction.comparative_utils import load_cognate_sets  # noqa: E402

DEFAULT_IN = ROOT / "woccon_language/correspondences/registry.json"
DEFAULT_OUT = ROOT / "woccon_language/correspondences/registry.json"

ENV_BY_ID = {
    "rudes_wc_r_n_medial": "word-medial",
    "rudes_wc_defective_r": "word-initial",
    "rudes_wc_nasal_oral": "vowel_correspondence",
    "rudes_ortho_no_bd": "attested_inventory",
}

ENV_BY_PAIR = {
    ("r", "n"): "word-medial",
    ("r", "r"): "word-medial",
    ("n", "r"): "word-medial",
    ("n", "n"): "default",
    ("m", "mn"): "word-medial",
    ("h", "s"): "default",
    ("h", "h"): "default",
    ("ś", "s"): "default",
}


def assign_environment(rule: Dict[str, Any]) -> str:
    rid = rule.get("id") or ""
    if rid in ENV_BY_ID:
        return ENV_BY_ID[rid]
    if rule.get("rule_kind") == "orthographic":
        return rule.get("environment") or "attested_inventory"
    if rule.get("rule_kind") != "sister_wc":
        return rule.get("environment") or "ps_retention"
    lhs, rhs = rule.get("lhs"), rule.get("rhs")
    if lhs and rhs:
        key = (lhs, rhs)
        if key in ENV_BY_PAIR:
            return ENV_BY_PAIR[key]
        if lhs == rhs:
            return "default"
    prov = (rule.get("provenance_text") or "").lower()
    if "word-initial" in prov or "defective" in prov:
        return "word-initial"
    if "nasal" in prov and "oral" in prov:
        return "vowel_correspondence"
    if "medial" in prov:
        return "word-medial"
    return rule.get("environment") or "default"


def upgrade_rules(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rule in rules:
        row = deepcopy(rule)
        row["environment"] = assign_environment(row)
        out.append(row)
    return out


def refresh_examples(rules: List[Dict[str, Any]], cognates_path: Path) -> None:
    cognates = load_cognate_sets(cognates_path)
    for rule in rules:
        if rule.get("rule_kind") != "sister_wc":
            continue
        lhs, rhs = rule.get("lhs"), rule.get("rhs")
        if not lhs or not rhs or len(str(lhs)) > 4 or len(str(rhs)) > 4:
            continue
        if rule.get("provenance_text") and rule.get("correspondence_status") == "established":
            continue
        linked = link_cognate_examples(lhs, rhs, cognates)
        if linked:
            rule["example_cognate_ids"] = linked
            rule["correspondence_status"] = classify_correspondence_status(
                "sister_wc", lhs, rhs, linked
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="inp", type=Path, default=DEFAULT_IN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--cognates",
        type=Path,
        default=ROOT / "woccon_language/cognate_sets/rudes_carter_seed.json",
    )
    parser.add_argument("--from-json", type=Path, help="Merge hand-edited rule overrides")
    args = parser.parse_args()

    envelope = json.loads(args.inp.read_text(encoding="utf-8"))
    rules = upgrade_rules(envelope.get("rules") or [])
    refresh_examples(rules, args.cognates)

    if args.from_json:
        extra = json.loads(args.from_json.read_text(encoding="utf-8"))
        rows = extra if isinstance(extra, list) else extra.get("rules") or []
        by_id = {r["id"]: r for r in rules if r.get("id")}
        for row in rows:
            if isinstance(row, dict) and row.get("id"):
                by_id[row["id"]] = row
        rules = sorted(by_id.values(), key=lambda r: r.get("id", ""))

    out_env = {
        "version": 2,
        "schema_version": 2,
        "source": envelope.get("source") or "Woccon reconstruction correspondence registry (Phase 3)",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "generator": "upgrade_correspondence_registry",
        "rules": rules,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_env, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    env_counts: Dict[str, int] = {}
    for r in rules:
        env = r.get("environment") or "?"
        env_counts[env] = env_counts.get(env, 0) + 1
    print(f"Wrote {args.out} ({len(rules)} rules, version 2)")
    print("Environments:", dict(sorted(env_counts.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
