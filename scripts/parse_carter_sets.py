#!/usr/bin/env python3
"""Parse Carter (1980) numbered comparative sets and link them to the Rudes seed.

Carter's Woccon-Catawba sets are printed as "(8) W Tauh-he dog; C təsi dog." Until the
scan was re-OCRed the Catawba side was stripped of diacritics, which is why carter_set_ids
was empty on every seed entry. This links each Carter set to its Rudes counterpart, records
Carter's independently transcribed Catawba form for cross-validation, and reports the sets
Carter has that Rudes lacks.

    python scripts/parse_carter_sets.py                  # report only
    python scripts/parse_carter_sets.py --write          # populate carter_set_ids
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
REOCR = ROOT / "data" / "carter_reocr.json"
SEED = ROOT / "woccon_language" / "cognate_sets" / "rudes_carter_seed.json"
REPORT = ROOT / "data" / "carter_inventory.json"

CITATION = "Carter 1980, set {n}"
SOURCE_PATH = "Articles/Carter-WocconLanguageNorth-1980.pdf"

# "(8) W Tauh-he dog; C təsi dog." — the body runs to the next numbered set.
SET_HEAD = re.compile(r"\((\d+)\)\s*W\s+", re.M)

_FOLD = str.maketrans({"ɔ": "o", "ɛ": "e", "ə": "e", "ɩ": "i", "ʔ": "", "·": "", "ñ": "n"})


def norm(s: Optional[str]) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", s.translate(_FOLD))


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip(" .,;")


def parse_sets(text: str) -> List[Dict]:
    heads = list(SET_HEAD.finditer(text))
    out: List[Dict] = []
    seen = set()
    for i, m in enumerate(heads):
        num = int(m.group(1))
        body = text[m.end() : heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        # Woccon side runs to the first "; C " marker; commentary follows the Catawba gloss.
        split = re.search(r";\s*C\s+", body)
        if not split:
            continue
        woccon = clean(body[: split.start()])
        catawba_zone = body[split.end() :]
        # Commentary starts at the first sentence break followed by a capitalised word,
        # a footnote marker, or a citation; page footnotes run on from the last set.
        stop = re.search(
            r"\.\s*(?=[A-Z]|[\u00b9\u00b2\u00b3\u2070-\u2079]|Ibid|op\.\s*cit|pp?\.)",
            catawba_zone,
        )
        catawba = clean(catawba_zone[: stop.start()] if stop else catawba_zone)
        if not woccon or not catawba or num in seen:
            continue
        seen.add(num)
        out.append(
            {
                "carter_set_id": f"carter1980_set_{num:02d}",
                "set_number": num,
                "woccon_raw": woccon,
                "catawba_raw": catawba,
                "woccon_form": woccon.split()[0] if woccon.split() else "",
                "gloss": " ".join(woccon.split()[1:]).strip(" ,"),
            }
        )
    return sorted(out, key=lambda r: r["set_number"])


def gloss_tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z]+", (s or "").lower()) if len(t) > 2 and t not in {"the", "and", "for"}}


def link(sets: List[Dict], seed: List[Dict]) -> Dict[str, List[str]]:
    """Conservative match: identical normalized Lawson form, or a shared gloss plus
    the same initial letter. Fuzzy string similarity alone produced false pairings
    (Carter's 'Tauh-he dog' matching Rudes' 'Yauh-he Indians')."""
    by_form: Dict[str, List[Dict]] = {}
    for entry in seed:
        for field in ("lawson_form", "lawson_form_corrected"):
            key = norm(entry.get(field))
            if key:
                by_form.setdefault(key, []).append(entry)

    links: Dict[str, List[str]] = {}
    for cs in sets:
        key = norm(cs["woccon_form"])
        matches = by_form.get(key, [])
        if not matches:
            ctoks = gloss_tokens(cs["gloss"])
            for entry in seed:
                etoks = gloss_tokens(entry.get("gloss")) | gloss_tokens(entry.get("lawson_gloss"))
                lf = norm(entry.get("lawson_form"))
                if ctoks & etoks and lf[:1] == key[:1] and lf and key:
                    matches = [entry]
                    break
        if matches:
            cs["matched_id"] = matches[0]["id"]
            links.setdefault(matches[0]["id"], []).append(cs["carter_set_id"])
        else:
            cs["matched_id"] = None
    return links


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="populate carter_set_ids in the seed")
    args = ap.parse_args()

    if not REOCR.exists():
        print(f"missing {REOCR}; run scripts/reocr_lossy_pdf.py first", file=sys.stderr)
        return 1

    text = "\n".join(json.loads(REOCR.read_text(encoding="utf-8"))["pages"])
    sets = parse_sets(text)
    seed_doc = json.loads(SEED.read_text(encoding="utf-8"))
    seed = seed_doc["sets"]
    links = link(sets, seed)

    matched = [s for s in sets if s.get("matched_id")]
    unmatched = [s for s in sets if not s.get("matched_id")]

    print(f"Carter sets parsed:        {len(sets)}")
    print(f"  linked to a Rudes entry: {len(matched)}")
    print(f"  Carter-only (new pairs): {len(unmatched)}")
    print(f"Rudes entries now carrying a Carter cross-reference: {len(links)} of {len(seed)}\n")

    if unmatched:
        print("Carter-only sets (candidate additions to the cognate pool):")
        for s in unmatched:
            print(f"  {s['carter_set_id']}  W {s['woccon_form']:<18} {s['gloss'][:22]:<24} C {s['catawba_raw'][:44]}")

    by_id = {e["id"]: e for e in seed}
    repairs = []
    for s in matched:
        entry = by_id[s["matched_id"]]
        cf = (entry.get("catawba_form") or "").strip()
        if len(cf) < 3 or re.search(r"[()0-9]", cf):
            repairs.append((entry, s))
    if repairs:
        print("\nRudes entries whose Catawba side looks corrupt, with Carter's reading:")
        for entry, s in repairs:
            print(
                f"  {entry['id']:<22} {entry.get('lawson_form','')!r:<20} "
                f"rudes={entry.get('catawba_form')!r:<12} carter={s['catawba_raw'][:40]!r}"
            )

    REPORT.write_text(
        json.dumps(
            {
                "source": SOURCE_PATH,
                "sets_parsed": len(sets),
                "linked": len(matched),
                "carter_only": len(unmatched),
                "sets": sets,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {REPORT.relative_to(ROOT)}")

    if args.write:
        set_by_id = {s["carter_set_id"]: s for s in sets}
        for entry in seed:
            ids = links.get(entry["id"], [])
            if not ids:
                continue
            entry["carter_set_ids"] = ids
            entry["carter_catawba_forms"] = [set_by_id[i]["catawba_raw"] for i in ids]
        SEED.write_text(json.dumps(seed_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"updated {SEED.relative_to(ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
