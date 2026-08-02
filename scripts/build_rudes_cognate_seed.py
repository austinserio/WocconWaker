#!/usr/bin/env python3
"""Build Rudes cognate seed JSON from sliced appendix text (regex + optional LLM)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RAW_DIR = ROOT / "woccon_language/cognate_sets/_raw"
OUT_PATH = ROOT / "woccon_language/cognate_sets/rudes_carter_seed.json"
SOURCE_PATH = (
    "Articles/Resurrecting Coastal Catawban - "
    "The Reconstitudes Phonology and Morpology of the Woccon Language"
)

APPENDIX_TIER = {
    1: "certain",
    2: "partial",
    3: "possible",
    4: "ps_only",
    5: "loan",
    6: "blend",
    7: "unknown",
}


def _parse_json_array_from_response(content: str) -> Optional[List[Any]]:
    content = (content or "").strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if m:
        content = m.group(1).strip()
    start = content.find("[")
    end = content.rfind("]") + 1
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(content[start:end])
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


def split_numbered_entries(text: str) -> List[Tuple[int, str]]:
    """Split appendix body into (item_number, chunk) pairs."""
    text = re.sub(r"^APPENDIX\s+\d+\.[^\n]*\n", "", text, flags=re.I)
    text = re.sub(r"^BLAIR RUDES\s*$", "", text, flags=re.M)
    text = re.sub(r"^RESURRECTING COASTAL CATAWBAN\s*$", "", text, flags=re.M)
    # Rudes OCR sometimes uses "55," instead of "55."
    matches = list(re.finditer(r"(?:^|\s)(\d+)[.,]\s+", text))
    if not matches:
        return []
    out: List[Tuple[int, str]] = []
    seen: dict[int, int] = {}
    for i, m in enumerate(matches):
        num = int(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if not chunk:
            continue
        # OCR typo: item 52 labeled "32. Three" after item 51 (real 32 is napiné)
        if num == 32 and re.match(r"Three\s+\*", chunk, re.I) and 32 in seen:
            num = 52
        seen[num] = seen.get(num, 0) + 1
        if seen[num] > 1:
            continue
        out.append((num, chunk))
    return out


def _normalize_reconstituted(form: Optional[str]) -> Optional[str]:
    if not form:
        return None
    form = form.strip()
    if form.startswith("*"):
        form = form[1:].strip()
    # OCR lines sometimes run the Lawson W (...) segment into the star form.
    form = re.split(r"\s+W\s+\(", form, maxsplit=1)[0].strip()
    form = re.split(r"\s+'", form, maxsplit=1)[0].strip()
    form = form.strip("]").strip("[")
    return form or None


def _parse_catawba_tail(tail: str, marker_text: str = "") -> Optional[str]:
    """Parse Catawba form text after C/Cy marker."""
    stop_pat = re.compile(
        r"[\u2018\u2019\u201c\u201d'\"]|"
        r"\s+(?:plus|arrow|tree|from|step|on|lit\.|See|come|he|they|burnt|dress|"
        r"blanket|eleven|eight|dog|corn|house|goose|bottle|gunpowder|chief|excel|"
        r"person|man|pestle|powder|meat|skin|firewood|boulder|stone|big|small|there|"
        r"indeed|good|cat|brains|gun|top|water|little|nine|one|bead|hot|soot|snow|"
        r"fine|hunts|goes|prefix|animal|clay|root|rat|something|some|knot|shell|"
        r"snake|three|ten|twelve|thirteen|seven|hat|comb|button|coat|log)\b|"
        r"\(\s*See\b|!",
        re.I,
    )
    stop = stop_pat.search(tail)
    val = tail[: stop.start()] if stop else tail
    val = val.strip().strip("'\"“”‘’")
    val = re.sub(r"\s+\d+\.\s+.*$", "", val)
    val = val.replace("│", "|")
    if marker_text and re.search(r"Cy$", marker_text) and val.startswith("ɩ"):
        val = "y" + val
    if val.startswith("-") and val.endswith("-") and not val.startswith("|"):
        val = f"|{val}|"
    if val and len(val) < 80:
        return val
    return None


def _extract_catawba(chunk: str) -> Optional[str]:
    """Extract full Catawba form after the Lawson W (...) segment.

    Rudes entries follow ``C <form> '<gloss>'`` (multi-token forms are common).
    OCR sometimes glues the label: ``Cyɩ``, ``Citi``.
    """
    w_m = re.search(r"W\s+\([^)]+\)", chunk)
    search_from = w_m.end() if w_m else 0
    rest = chunk[search_from:]

    morph_m = re.search(
        r"(?:;\s*|,\s*|:\s*)(?:Cy|C)\s*(\|[-\w]+\|)",
        rest,
    )
    if morph_m:
        return morph_m.group(1).replace("│", "|")

    marker_m = re.search(
        r"(?:;\s*|,\s*|:\s*|\.\s+|\n)(?:Cy|C)(?:\s+|(?=[^\s]))",
        rest,
    )
    if marker_m:
        marker_text = rest[marker_m.start() : marker_m.end()]
        val = _parse_catawba_tail(rest[marker_m.end() :], marker_text)
        if val:
            return val

    # Appendix 2 partial cognates: "plus C ww 'knot" after a second W (...) line.
    for search_text in (rest, chunk):
        plus_m = re.search(r"plus\s+(?:Cy|C)(?:\s+|(?=[^\s]))", search_text, re.I)
        if plus_m:
            val = _parse_catawba_tail(search_text[plus_m.end() :])
            if val:
                return val

    return None


def _clean_gloss(head: str) -> str:
    head = (head or "").strip().strip(":").strip()
    head = re.sub(r"^\(([^)]+)\)\s*", r"\1 ", head)
    head = re.sub(r"\[([^\]]+)\]", r"\1", head)
    head = re.sub(r"\s+", " ", head)
    if not head:
        return "unknown"
    return head[0].lower() + head[1:] if len(head) > 1 else head.lower()


def parse_entry_chunk(
    appendix: int,
    item: int,
    chunk: str,
    evidence_tier: str,
) -> Dict[str, Any]:
    """Heuristic parse of one Rudes appendix line/chunk."""
    chunk = chunk.strip()
    notes_parts: List[str] = []

    proto_siouan: Optional[str] = None
    ps_m = re.search(r"PS\s+(\*[^\s,\.;]+(?:\s*[^\s,\.;]+)?)", chunk)
    if ps_m:
        proto_siouan = ps_m.group(1).strip()

    woccon_reconstituted: Optional[str] = None
    gloss_head = ""
    morph_m = re.match(r"^(\w+(?:\s+\[[^\]]+\])?)\s+\*(\|[-\w]+\|?\]?)", chunk)
    if morph_m:
        gloss_head = morph_m.group(1).strip()
        raw_morph = morph_m.group(2).strip().strip("]").strip(":").strip("|")
        if raw_morph:
            if not raw_morph.startswith("-"):
                raw_morph = f"-{raw_morph}"
            if not raw_morph.endswith("-"):
                raw_morph = f"{raw_morph}-"
            woccon_reconstituted = f"|{raw_morph}|"
    else:
        head_m = re.match(r"^(.*?)\s*(\*[^:]+):\s*", chunk, re.DOTALL)
        if head_m:
            gloss_head = head_m.group(1).strip()
            woccon_reconstituted = head_m.group(2).strip()
        else:
            alt_m = re.match(
                r"^(.*?)\s*(\*[^\s]+(?:\s+[^\sW][^\s]*)*?)\s+W\s+\(",
                chunk,
                re.DOTALL,
            )
            if alt_m:
                gloss_head = alt_m.group(1).strip()
                woccon_reconstituted = alt_m.group(2).strip()
            elif re.match(r"^\*", chunk):
                star_m = re.match(r"^(\*[^:]+):\s*", chunk)
                if star_m:
                    woccon_reconstituted = star_m.group(1).strip()
            elif re.match(r"^\*[^\s]", chunk):
                star_w = re.match(r"^(\*[^\s]+(?:\s+[^\sW][^\s]*)*?)\s+W\s+\(", chunk)
                if star_w:
                    woccon_reconstituted = star_w.group(1).strip()
            # Appendix 3 "possible" rows have no * reconstruction; do not grab gloss words.

    lawson_form: Optional[str] = None
    lawson_form_corrected: Optional[str] = None
    lawson_gloss: Optional[str] = None
    w_m = re.search(r"W\s+\(([^)]+)\)", chunk)
    if w_m:
        lawson_form = w_m.group(1).strip()
    err_m = re.search(r"\(error for \(([^)]+)\)\)", chunk, re.I)
    if err_m:
        lawson_form_corrected = err_m.group(1).strip()
        lawson_form = lawson_form_corrected
    lg_m = re.search(
        r"W\s+\([^)]+\)(?:\s*\(error for \([^)]+\)\))?[^']*'([^']*)'",
        chunk,
        re.I,
    )
    if lg_m:
        lawson_gloss = lg_m.group(1).strip()

    catawba_form = _extract_catawba(chunk)

    catawba_dialect: Optional[str] = None
    if re.search(r"Esaw dialect", chunk, re.I):
        catawba_dialect = "esaw"
    elif re.search(r"Saraw dialect", chunk, re.I):
        catawba_dialect = "saraw"

    for paren in re.findall(r"\(([^)]+)\)", chunk):
        low = paren.lower()
        if "error for" in low:
            continue
        if "dialect" in low and ("esaw" in low or "saraw" in low):
            continue
        if len(paren) > 15:
            notes_parts.append(paren.strip())

    notes = "; ".join(notes_parts) if notes_parts else None
    gloss = _clean_gloss(gloss_head) if gloss_head else f"item {item}"

    return {
        "id": f"rudes2000_app{appendix}_{item:03d}",
        "gloss": gloss,
        "lawson_form": lawson_form,
        "lawson_form_corrected": lawson_form_corrected,
        "lawson_gloss": lawson_gloss,
        "woccon_reconstituted": _normalize_reconstituted(woccon_reconstituted),
        "catawba_form": catawba_form,
        "catawba_dialect": catawba_dialect,
        "proto_siouan": _normalize_reconstituted(proto_siouan),
        "evidence_tier": evidence_tier,
        "rudes_appendix": appendix,
        "rudes_item": item,
        "carter_set_ids": [],
        "notes": notes,
        "citation_short": f"Rudes 2000, App. {appendix} #{item}",
        "source_path": SOURCE_PATH,
    }


def parse_appendix_file(path: Path, appendix: int) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    tier = APPENDIX_TIER.get(appendix, "unknown")
    entries: List[Dict[str, Any]] = []
    seen_nums: set[int] = set()
    for num, chunk in split_numbered_entries(text):
        if num in seen_nums:
            continue
        seen_nums.add(num)
        entries.append(parse_entry_chunk(appendix, num, chunk, tier))
    entries.sort(key=lambda e: e["rudes_item"])
    return entries


def llm_parse_appendix(path: Path, appendix: int, model: Optional[str] = None) -> List[Dict[str, Any]]:
    from llm_client import llm_chat

    text = path.read_text(encoding="utf-8")
    tier = APPENDIX_TIER.get(appendix, "unknown")
    prompt = f"""Extract every numbered item from Rudes (2000) APPENDIX {appendix} into a JSON array.
Each object must have these keys (use null when absent):
- rudes_item (integer, the item number in the appendix)
- gloss (short English meaning, lowercase)
- lawson_form (Lawson spelling inside W (...), or null)
- lawson_form_corrected (if text says "error for (...)", else null)
- lawson_gloss (English gloss in Lawson quotes after W form, or null)
- woccon_reconstituted (form after *, without leading *, or null)
- catawba_form (Catawba form after C, or null)
- catawba_dialect ("esaw", "saraw", or null)
- proto_siouan (PS * form if present, or null)
- notes (copyist/morphology notes as one string, or null)

Set evidence_tier to "{tier}" for every row. Do not invent forms not in the text.

APPENDIX TEXT:
{text[:12000]}
"""
    resp = llm_chat(
        model or "",
        [{"role": "user", "content": prompt}],
        options={"temperature": 0.1, "num_predict": 8192},
    )
    content = (resp.get("message") or {}).get("content") or ""
    rows = _parse_json_array_from_response(content)
    if not rows:
        raise RuntimeError(f"LLM returned no JSON array for appendix {appendix}")
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = int(row.get("rudes_item") or 0)
        if item <= 0:
            continue
        out.append(
            {
                "id": f"rudes2000_app{appendix}_{item:03d}",
                "gloss": str(row.get("gloss") or f"item {item}"),
                "lawson_form": row.get("lawson_form"),
                "lawson_form_corrected": row.get("lawson_form_corrected"),
                "lawson_gloss": row.get("lawson_gloss"),
                "woccon_reconstituted": row.get("woccon_reconstituted"),
                "catawba_form": row.get("catawba_form"),
                "catawba_dialect": row.get("catawba_dialect"),
                "proto_siouan": row.get("proto_siouan"),
                "evidence_tier": tier,
                "rudes_appendix": appendix,
                "rudes_item": item,
                "carter_set_ids": [],
                "notes": row.get("notes"),
                "citation_short": f"Rudes 2000, App. {appendix} #{item}",
                "source_path": SOURCE_PATH,
            }
        )
    out.sort(key=lambda e: e["rudes_item"])
    return out


def build_envelope(
    sets: List[Dict[str, Any]],
    ocr_cache_file: str,
    generator: str,
) -> Dict[str, Any]:
    return {
        "version": 1,
        "source": "Rudes 2000 Resurrecting Coastal Catawban",
        "ocr_cache_file": ocr_cache_file,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "generator": generator,
        "sets": sets,
    }


def load_merge_from_json(path: Path, existing: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "corrections" in data:
        rows = data.get("corrections") or []
        by_id = {e["id"]: e for e in existing}
        for corr in rows:
            if not isinstance(corr, dict) or not corr.get("cognate_id"):
                continue
            cid = corr["cognate_id"]
            field = corr.get("field")
            val = corr.get("corrected_value")
            if cid in by_id and field and val is not None:
                by_id[cid][field] = val
        return sorted(by_id.values(), key=lambda e: (e.get("rudes_appendix", 0), e.get("rudes_item", 0)))
    rows = data if isinstance(data, list) else data.get("sets") or []
    by_id = {e["id"]: e for e in existing}
    for row in rows:
        if isinstance(row, dict) and row.get("id"):
            by_id[row["id"]] = row
    return sorted(by_id.values(), key=lambda e: (e.get("rudes_appendix", 0), e.get("rudes_item", 0)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--appendix", type=int, action="append", dest="appendices", help="Appendix number (repeatable)")
    parser.add_argument("--use-llm", action="store_true", help="Use LLM instead of regex parser")
    parser.add_argument("--from-json", type=Path, help="Merge hand-edited JSON array, envelope, or corrections.json")
    parser.add_argument(
        "--corrections",
        type=Path,
        default=ROOT / "woccon_language/cognate_sets/corrections.json",
        help="Apply OCR corrections sidecar after build",
    )
    parser.add_argument("--model", type=str, default="", help="LLM model override")
    args = parser.parse_args()

    appendices = args.appendices or [1, 2, 3, 4]
    manifest_path = args.raw_dir / "manifest.json"
    ocr_cache = ""
    if manifest_path.is_file():
        try:
            ocr_cache = json.loads(manifest_path.read_text(encoding="utf-8")).get("cache_file") or ""
        except json.JSONDecodeError:
            pass

    all_sets: List[Dict[str, Any]] = []
    generator = "regex"
    for app in appendices:
        raw_path = args.raw_dir / f"app{app}.txt"
        if not raw_path.is_file():
            print(f"ERROR: missing {raw_path} (run extract_rudes_appendices.py first)", file=sys.stderr)
            return 1
        if args.use_llm:
            try:
                rows = llm_parse_appendix(raw_path, app, model=args.model or None)
                generator = "llm"
            except Exception as exc:
                print(f"WARNING: LLM failed for app {app} ({exc}); falling back to regex", file=sys.stderr)
                rows = parse_appendix_file(raw_path, app)
        else:
            rows = parse_appendix_file(raw_path, app)
        print(f"Appendix {app}: {len(rows)} entries ({APPENDIX_TIER.get(app)})")
        all_sets.extend(rows)

    if args.from_json:
        all_sets = load_merge_from_json(args.from_json, all_sets)
        generator = f"{generator}+merge"
    elif args.corrections.is_file():
        all_sets = load_merge_from_json(args.corrections, all_sets)
        generator = f"{generator}+corrections"

    envelope = build_envelope(all_sets, ocr_cache, generator)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.out} ({len(all_sets)} cognate sets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
