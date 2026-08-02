#!/usr/bin/env python3
"""Build tagged correspondence registry from rules_unified + cognate seed."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panel_api.services.rule_classifier import (  # noqa: E402
    classify_correspondence_status,
    classify_grammar_lineage,
    classify_rule_kind,
    infer_direction,
    is_correspondence_like,
)

DEFAULT_RULES = ROOT / "woccon_language/rules_unified.json"
DEFAULT_COGNATES = ROOT / "woccon_language/cognate_sets/rudes_carter_seed.json"
DEFAULT_OUT = ROOT / "woccon_language/correspondences/registry.json"


def _slug(s: str) -> str:
    parts: List[str] = []
    for ch in s or "":
        if ch.isascii() and ch.isalnum():
            parts.append(ch.lower())
        else:
            parts.append(f"u{ord(ch):04x}")
    return "".join(parts)[:48] or "x"


def _norm_form(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"[^\w]", "", s.lower())


def _pair_id(lhs: str, rhs: str, suffix: str = "") -> str:
    base = f"legacy_wc_{_slug(lhs)}_{_slug(rhs)}"
    return f"{base}_{suffix}" if suffix else base


def _note_id(text: str) -> str:
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"grammar_{h}"


def load_cognate_sets(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("sets") or []


def cognate_supports_pair(
    w_form: Optional[str],
    c_form: Optional[str],
    lhs: str,
    rhs: str,
) -> bool:
    """Simple segment presence check for App. 1 certain pairs."""
    w = _norm_form(w_form)
    c = _norm_form(c_form)
    lhs_n = _norm_form(lhs)
    rhs_n = _norm_form(rhs)
    if not lhs_n or not rhs_n or not w or not c:
        return False
    if lhs_n == rhs_n:
        # Identity correspondence: shared onset or substring
        if w == c:
            return True
        if w.startswith(lhs_n) and c.startswith(rhs_n):
            return True
        return lhs_n in w and rhs_n in c
    return lhs_n in w and rhs_n in c


def link_cognate_examples(
    lhs: str,
    rhs: str,
    cognates: List[Dict[str, Any]],
    *,
    appendix: int = 1,
    tier: str = "certain",
) -> List[str]:
    out: List[str] = []
    for row in cognates:
        if row.get("rudes_appendix") != appendix:
            continue
        if row.get("evidence_tier") != tier:
            continue
        if cognate_supports_pair(
            row.get("woccon_reconstituted"),
            row.get("catawba_form"),
            lhs,
            rhs,
        ):
            rid = row.get("id")
            if rid:
                out.append(rid)
    return sorted(set(out))


def rows_from_sound_correspondences(
    rules: Dict[str, Any],
    cognates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    pairs = (
        rules.get("phonology", {})
        .get("sound_correspondences", {})
        .get("Woccon_to_Catawba", [])
    )
    seen: Set[Tuple[str, str]] = set()
    for i, pair in enumerate(pairs):
        lhs = (pair.get("Woccon") or pair.get("woccon") or "").strip()
        rhs = (pair.get("Catawba") or pair.get("catawba") or "").strip()
        if not lhs or not rhs:
            continue
        key = (lhs, rhs)
        if key in seen:
            suffix = str(i)
            rid = _pair_id(lhs, rhs, suffix)
        else:
            seen.add(key)
            rid = _pair_id(lhs, rhs)
        examples = link_cognate_examples(lhs, rhs, cognates)
        status = classify_correspondence_status("sister_wc", lhs, rhs, examples)
        note = pair.get("note")
        rows.append(
            {
                "id": rid,
                "rule_kind": "sister_wc",
                "lhs": lhs,
                "rhs": rhs,
                "environment": "default",
                "direction": "w_to_c",
                "correspondence_status": status,
                "example_cognate_ids": examples,
                "grammar_lineage": "siouan_comparative",
                "source": "rules_unified.json phonology.sound_correspondences",
                "notes": note,
                "provenance_text": None,
            }
        )
    return rows


def rows_from_grammar_notes(
    notes: List[Dict[str, Any]],
    cognates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for note in notes:
        text = (note.get("text") or "").strip()
        if not text or not is_correspondence_like(text):
            continue
        rk = classify_rule_kind(text)
        if not rk:
            continue
        rid = _note_id(text)
        gl = note.get("grammar_lineage") or classify_grammar_lineage(text)
        rows.append(
            {
                "id": rid,
                "rule_kind": rk,
                "lhs": None,
                "rhs": None,
                "environment": None,
                "direction": infer_direction(rk),
                "correspondence_status": classify_correspondence_status(rk, None, None),
                "example_cognate_ids": [],
                "grammar_lineage": gl,
                "source": "rules_unified.json community_grammar_notes",
                "notes": None,
                "provenance_text": text,
            }
        )
    return rows


def rows_from_ps_cognates(cognates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for row in cognates:
        if row.get("evidence_tier") != "ps_only":
            continue
        ps = (row.get("proto_siouan") or "").strip()
        if not ps:
            continue
        rid = f"ps_{row['id']}"
        rows.append(
            {
                "id": rid,
                "rule_kind": "diachronic_ps",
                "lhs": ps.split()[0] if ps else None,
                "rhs": row.get("woccon_reconstituted"),
                "environment": "ps_retention",
                "direction": "ps_to_w",
                "correspondence_status": "tentative",
                "example_cognate_ids": [row["id"]],
                "grammar_lineage": "proto_siouan",
                "source": f"Rudes 2000 {row.get('citation_short', '')}",
                "notes": row.get("notes"),
                "provenance_text": None,
            }
        )
    return rows


# Hand-curated high-confidence rules (Rudes); merged last so overrides win via --from-json
CURATED_RULES: List[Dict[str, Any]] = [
    {
        "id": "rudes_wc_r_n_medial",
        "rule_kind": "sister_wc",
        "lhs": "r",
        "rhs": "n",
        "environment": "word-medial",
        "direction": "w_to_c",
        "correspondence_status": "established",
        "example_cognate_ids": ["rudes2000_app1_041", "rudes2000_app1_028"],
        "grammar_lineage": "siouan_comparative",
        "source": "Rudes 2000; ronoak/bead cognate set",
        "notes": "Esaw/Saraw regressive nasal assimilation in related forms",
        "provenance_text": "Woccon r corresponds to Catawba n in ronoak (Rummaen) ~ nú?mą? bead",
    },
    {
        "id": "rudes_wc_nasal_oral",
        "rule_kind": "sister_wc",
        "lhs": "oral_v",
        "rhs": "nasal_v",
        "environment": "vowel_correspondence",
        "direction": "w_to_c",
        "correspondence_status": "established",
        "example_cognate_ids": [],
        "grammar_lineage": "siouan_comparative",
        "source": "Rudes 2000 phonology",
        "notes": "Woccon long oral vowel often corresponds to Catawba nasal vowel",
        "provenance_text": "In most correspondence sets between Catawba and Woccon, Woccon shows a long oral vowel where Catawba shows a nasal vowel.",
    },
    {
        "id": "rudes_ortho_no_bd",
        "rule_kind": "orthographic",
        "lhs": "Lawson_inventory",
        "rhs": "Woccon_phonemes",
        "environment": "attested_inventory",
        "direction": "lawson_to_w",
        "correspondence_status": "established",
        "example_cognate_ids": [],
        "grammar_lineage": "woccon_attested",
        "source": "Rudes 2000; Lawson philology",
        "notes": "Do not project Catawba b/d/ſ innovations into Woccon from Lawson gaps alone",
        "provenance_text": "There is no evidence in Lawson's vocabulary for assuming the phonemes b, d, ſ for Woccon",
    },
    {
        "id": "rudes_wc_defective_r",
        "rule_kind": "sister_wc",
        "lhs": "r",
        "rhs": "n|y|d",
        "environment": "word-initial",
        "direction": "w_to_c",
        "correspondence_status": "established",
        "example_cognate_ids": [],
        "grammar_lineage": "siouan_comparative",
        "source": "Rudes 2000 phonology",
        "notes": "Catawba r defective word-initially; Woccon retains r",
        "provenance_text": "Woccon r is retained where Catawba shows n, y, or d (defective *r in Catawba)",
    },
]


def merge_rules(
    base: List[Dict[str, Any]],
    overrides: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_id = {r["id"]: r for r in base if r.get("id")}
    for row in overrides:
        if isinstance(row, dict) and row.get("id"):
            by_id[row["id"]] = row
    return sorted(by_id.values(), key=lambda r: r.get("id", ""))


def build_registry(
    rules_path: Path,
    cognates_path: Path,
    extra: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    rules_doc = json.loads(rules_path.read_text(encoding="utf-8"))
    cognates = load_cognate_sets(cognates_path)
    notes = rules_doc.get("community_grammar_notes") or []

    all_rows: List[Dict[str, Any]] = []
    all_rows.extend(rows_from_sound_correspondences(rules_doc, cognates))
    all_rows.extend(rows_from_grammar_notes(notes, cognates))
    all_rows.extend(rows_from_ps_cognates(cognates))
    all_rows.extend(CURATED_RULES)
    if extra:
        all_rows = merge_rules(all_rows, extra)

    # Recompute status/examples for legacy letter-pair rows only
    for row in all_rows:
        rid = row.get("id") or ""
        if not rid.startswith("legacy_wc_"):
            if row.get("direction") is None and row.get("rule_kind"):
                row["direction"] = infer_direction(row["rule_kind"])
            continue
        lhs, rhs = row.get("lhs"), row.get("rhs")
        if row.get("rule_kind") == "sister_wc" and lhs and rhs:
            if not row.get("example_cognate_ids") and len(str(lhs)) <= 3:
                row["example_cognate_ids"] = link_cognate_examples(lhs, rhs, cognates)
            row["correspondence_status"] = classify_correspondence_status(
                "sister_wc", lhs, rhs, row.get("example_cognate_ids")
            )
        if row.get("direction") is None and row.get("rule_kind"):
            row["direction"] = infer_direction(row["rule_kind"])
    return merge_rules(all_rows, [])


def build_envelope(rules: List[Dict[str, Any]], generator: str) -> Dict[str, Any]:
    return {
        "version": 1,
        "source": "Woccon reconstruction correspondence registry (Phase 2)",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "generator": generator,
        "rules": rules,
    }


def backfill_panel_db(rules: List[Dict[str, Any]], dry_run: bool = False) -> int:
    """Set rule_kind / correspondence_status on canonical grammar rules by content match."""
    from panel_api.db import CanonicalRule, get_session_factory, init_db
    from panel_api.services.rule_classifier import apply_classification_to_rule

    init_db()
    db = get_session_factory()()
    updated = 0
    try:
        rows = (
            db.query(CanonicalRule)
            .filter(CanonicalRule.category == "grammar")
            .all()
        )
        by_provenance = {
            (reg.get("provenance_text") or "").strip(): reg
            for reg in rules
            if reg.get("provenance_text")
        }
        for crow in rows:
            content = (crow.content or "").strip()
            apply_classification_to_rule(
                crow, "grammar", content, grammar_lineage=getattr(crow, "grammar_lineage", None)
            )
            for prov, reg in by_provenance.items():
                if prov and (prov == content or prov in content):
                    crow.rule_kind = reg.get("rule_kind")
                    crow.correspondence_status = reg.get("correspondence_status")
                    break
            updated += 1
        if not dry_run:
            db.commit()
    finally:
        db.close()
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--cognates", type=Path, default=DEFAULT_COGNATES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--from-json", type=Path, help="Merge hand-edited rules array or envelope")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backfill-panel", action="store_true", help="Update panel DB rule_kind columns")
    args = parser.parse_args()

    extra: Optional[List[Dict[str, Any]]] = None
    if args.from_json:
        data = json.loads(args.from_json.read_text(encoding="utf-8"))
        extra = data if isinstance(data, list) else data.get("rules") or []

    registry = build_registry(args.rules, args.cognates, extra=extra)
    generator = "tag_rule_kinds"
    if extra:
        generator += "+merge"

    by_kind: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    linked = sum(1 for r in registry if r.get("example_cognate_ids"))
    for r in registry:
        by_kind[r.get("rule_kind", "?")] = by_kind.get(r.get("rule_kind", "?"), 0) + 1
        by_status[r.get("correspondence_status", "?")] = (
            by_status.get(r.get("correspondence_status", "?"), 0) + 1
        )

    print(f"Registry: {len(registry)} rules")
    print("By rule_kind:", dict(sorted(by_kind.items())))
    print("By correspondence_status:", dict(sorted(by_status.items())))
    print(f"Rules with cognate examples: {linked}")

    if args.dry_run:
        return 0

    envelope = build_envelope(registry, generator)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")

    if args.backfill_panel:
        n = backfill_panel_db(registry, dry_run=False)
        print(f"Backfilled {n} canonical grammar rules in panel DB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
