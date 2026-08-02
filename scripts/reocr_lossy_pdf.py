#!/usr/bin/env python3
"""Re-OCR PDF pages whose embedded text layer lost its phonetic characters.

Scanned journal PDFs ship an OCR text layer that reads as clean English while having
dropped every diacritic. Those pages pass the character-count check in pdf_text.py, so
this script re-runs vision OCR over them and rewrites the ingest text cache entry.

    python scripts/reocr_lossy_pdf.py --pdf data/ingest_sources/<file>.pdf --page 4 --dry-run
    python scripts/reocr_lossy_pdf.py --pdf data/ingest_sources/<file>.pdf --write
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from llm_client import llm_vision_chat  # noqa: E402
from panel_api.services.pdf_text import (  # noqa: E402
    extract_pages_with_pdfplumber,
    pages_with_lossy_text_layer,
    render_pdf_pages,
)

PHONETIC_OCR_PROMPT = """Transcribe all visible text from this page of a linguistics journal exactly as printed.

This page uses Americanist phonetic transcription. Reproduce every diacritic and special
character exactly as shown: acute and grave accents, macrons, breves, hooks and ogoneks,
raised dots for length, glottal stops, barred and hooked letters, and any superscripts or
subscripts. Never substitute a plain ASCII letter for an accented one, and never normalize
or modernize a spelling.

If the page is printed in two columns, transcribe the left column in full and then the right
column; otherwise read straight down the page. Keep numbered comparative sets such as
"(21) W form gloss; C form gloss" and tabular correspondence lists on their own lines, one
entry per line. Transcribe footnotes after the body text.

Output only the transcribed text, with no commentary."""

NON_ASCII = re.compile(r"[^\x00-\x7f]")
PHONETIC_CHAR = re.compile(r"[\u00C0-\u024F\u0250-\u02FF\u0300-\u036F]")


def ocr_pages(pdf_bytes: bytes, page_nums: List[int], dpi: int) -> Dict[int, str]:
    images = render_pdf_pages(pdf_bytes, page_nums, dpi=dpi)
    out: Dict[int, str] = {}
    for n in page_nums:
        png = images.get(n)
        if not png:
            print(f"  page {n}: render failed", file=sys.stderr)
            continue
        started = time.monotonic()
        result = llm_vision_chat(
            "",
            f"{PHONETIC_OCR_PROMPT}\n\nThis is page {n} of the document.",
            [png],
            options={"temperature": 0.0, "num_predict": 4096},
        )
        text = ((result.get("message") or {}).get("content") or "").strip()
        if text.startswith("Error:"):
            print(f"  page {n}: {text}", file=sys.stderr)
            continue
        out[n] = text
        print(
            f"  page {n}: {time.monotonic() - started:5.0f}s  {len(text):5d} chars  "
            f"{len(PHONETIC_CHAR.findall(text)):4d} phonetic chars"
        )
    return out


def find_cache_entry(pdf_path: Path) -> Path | None:
    file_id = pdf_path.name.split("_")[0]
    for candidate in (ROOT / "data" / "ingest_text_cache").glob("*.json"):
        if candidate.name.startswith(file_id + "_"):
            return candidate
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--page", type=int, action="append", help="limit to page(s); repeatable")
    ap.add_argument("--dpi", type=int, default=int(os.getenv("PDF_OCR_DPI", "300")))
    ap.add_argument("--write", action="store_true", help="update the ingest text cache entry")
    ap.add_argument("--out", help="also write recovered page text to this JSON file")
    ap.add_argument("--from-json", help="reuse a previous --out file instead of calling the model")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.is_absolute():
        pdf_path = ROOT / pdf_path
    data = pdf_path.read_bytes()

    page_texts = extract_pages_with_pdfplumber(data)
    lossy = pages_with_lossy_text_layer(data, page_texts)
    targets = args.page or [i for i, flag in enumerate(lossy, start=1) if flag]
    if not targets:
        print("No pages flagged as having a lossy text layer; nothing to do.")
        return 0

    print(f"{pdf_path.name}: {len(page_texts)} pages, re-OCRing {len(targets)} at {args.dpi} DPI")
    if args.dry_run:
        print("dry run; pages that would be re-OCRed:", targets)
        return 0

    if args.from_json:
        cached_path = Path(args.from_json)
        if not cached_path.is_absolute():
            cached_path = ROOT / cached_path
        cached_pages = json.loads(cached_path.read_text(encoding="utf-8"))["pages"]
        recovered = {n: cached_pages[n - 1] for n in targets if n <= len(cached_pages)}
        print(f"reusing {len(recovered)} page(s) from {cached_path.name}")
    else:
        recovered = ocr_pages(data, targets, args.dpi)
    if not recovered:
        print("No pages recovered.", file=sys.stderr)
        return 1

    before = sum(len(PHONETIC_CHAR.findall(page_texts[n - 1] or "")) for n in recovered)
    after = sum(len(PHONETIC_CHAR.findall(t)) for t in recovered.values())
    print(f"\nphonetic characters on re-OCRed pages: {before} -> {after}")

    for n, text in recovered.items():
        page_texts[n - 1] = text

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {"source_pdf": pdf_path.name, "dpi": args.dpi, "pages": page_texts},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"wrote {out_path}")

    if args.write:
        cache = find_cache_entry(pdf_path)
        if not cache:
            print("No matching ingest cache entry found; skipped cache update.", file=sys.stderr)
            return 1
        payload = json.loads(cache.read_text(encoding="utf-8"))
        backup = cache.with_suffix(".json.pre_reocr")
        if not backup.exists():
            backup.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["text"] = "\n\n".join(t.strip() for t in page_texts if t and t.strip())
        payload["text_method"] = "vision_reocr"
        cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"updated {cache.name} (backup at {backup.name})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
