#!/usr/bin/env python3
"""Cross-validate parsed Lawson spellings against dictionary.json."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = ROOT / "woccon_language/cognate_sets/rudes_carter_seed.json"
DEFAULT_DICT = ROOT / "woccon_language/dictionary.json"


def _norm_lawson(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def load_dictionary_keys(path: Path) -> Set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    lex = data.get("lexicon") or data
    keys: Set[str] = set()
    for entry in lex:
        w = entry.get("woccon") or entry.get("word") or ""
        if w:
            keys.add(_norm_lawson(w))
    return keys


def verify_seed(
    seed_path: Path,
    dict_path: Path,
    *,
    appendix: int = 1,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    envelope = json.loads(seed_path.read_text(encoding="utf-8"))
    sets = envelope.get("sets") or envelope
    dict_keys = load_dictionary_keys(dict_path)

    verified: List[Dict[str, Any]] = []
    residue: List[Dict[str, Any]] = []

    for row in sets:
        if row.get("rudes_appendix") != appendix:
            continue
        lawson = row.get("lawson_form") or row.get("lawson_form_corrected") or ""
        norm = _norm_lawson(lawson)
        matched = norm in dict_keys if norm else False
        item = {
            "cognate_id": row.get("id"),
            "gloss": row.get("gloss"),
            "lawson_form": lawson,
            "lawson_norm": norm,
            "woccon_reconstituted": row.get("woccon_reconstituted"),
            "catawba_form": row.get("catawba_form"),
            "rudes_item": row.get("rudes_item"),
            "dictionary_match": matched,
        }
        if matched:
            verified.append(item)
        else:
            residue.append(item)

    return verified, residue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--dict", type=Path, default=DEFAULT_DICT, dest="dict_path")
    parser.add_argument("--appendix", type=int, default=1)
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    verified, residue = verify_seed(args.seed, args.dict_path, appendix=args.appendix)
    total = len(verified) + len(residue)
    report = {
        "appendix": args.appendix,
        "total": total,
        "verified_count": len(verified),
        "residue_count": len(residue),
        "verified": verified,
        "residue": residue,
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Appendix {args.appendix}: {len(verified)}/{total} Lawson forms match dictionary.json")
        if residue:
            print("\nResidue (needs hand review):")
            for r in residue:
                print(
                    f"  #{r['rudes_item']:02d} {r['cognate_id']}: "
                    f"Lawson={r['lawson_form']!r} W={r['woccon_reconstituted']!r}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
