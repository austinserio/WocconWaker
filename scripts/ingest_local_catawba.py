#!/usr/bin/env python3
"""Vision-OCR local Catawba PDFs and extract them into the Catawba staging area.

Every Catawba source acquired so far (Speck 1934, Lieber 1858, Gatschet 1900) ships a
diacritic-stripped text layer, so the phonetic notation the comparison depends on has to be
recovered by vision OCR before the text is worth anything. This runs that pass and then the
Catawba extraction prompt, writing to `woccon_language/catawba_staging/`.

Paths are prefixed with the Drive folder name so `content_language.classify_path` tags every
document as Catawba, which is what keeps these forms out of the Woccon lexicon.

Both stages are resumable: OCR output is cached per document and skipped when present.

    python scripts/ingest_local_catawba.py --dir ~/Downloads/CatawbaUpload --dry-run
    python scripts/ingest_local_catawba.py --dir ~/Downloads/CatawbaUpload
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import drive_extract  # noqa: E402
from content_language import CATAWBA, classify_path  # noqa: E402
from panel_api.services.pdf_text import (  # noqa: E402
    extract_pages_with_pdfplumber,
    pages_with_lossy_text_layer,
)
from scripts.reocr_lossy_pdf import PHONETIC_CHAR, ocr_pages  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("catawba_ingest")

OCR_CACHE = ROOT / "data" / "catawba_ocr"
DRIVE_FOLDER = "Catawba Language"


def ocr_document(pdf: Path, dpi: int) -> dict:
    """Return {"pages": [...]} for one PDF, reusing a cached OCR run when present."""
    OCR_CACHE.mkdir(parents=True, exist_ok=True)
    cache = OCR_CACHE / f"{pdf.stem}.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        log.info("%s: reusing cached OCR (%d pages)", pdf.name, len(payload.get("pages") or []))
        return payload

    data = pdf.read_bytes()
    page_texts = extract_pages_with_pdfplumber(data)
    lossy = pages_with_lossy_text_layer(data, page_texts)
    targets = [i for i, flag in enumerate(lossy, start=1) if flag]
    # A page with no text layer at all is sparse rather than lossy; OCR those too.
    for i, t in enumerate(page_texts, start=1):
        if i not in targets and len((t or "").strip()) < 50:
            targets.append(i)
    targets.sort()

    log.info("%s: %d pages, %d need OCR at %d DPI", pdf.name, len(page_texts), len(targets), dpi)
    if targets:
        recovered = ocr_pages(data, targets, dpi)
        for n, text in recovered.items():
            page_texts[n - 1] = text

    payload = {
        "source_pdf": pdf.name,
        "dpi": dpi,
        "pages": page_texts,
        "phonetic_chars": sum(len(PHONETIC_CHAR.findall(t or "")) for t in page_texts),
    }
    cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("%s: wrote %s (%d phonetic chars)", pdf.name, cache.name, payload["phonetic_chars"])
    return payload


def extract_document(pdf: Path, pages: list) -> dict:
    text = "\n\n".join(t.strip() for t in pages if t and t.strip())
    drive_path = f"{DRIVE_FOLDER}/{pdf.name}"
    language = classify_path(drive_path)
    if language != CATAWBA:
        raise RuntimeError(f"{drive_path} did not classify as Catawba (got {language})")

    log.info("%s: extracting %d chars with the Catawba prompt", pdf.name, len(text))
    started = time.monotonic()
    result = drive_extract.extract_one_file(text, drive_path, content_language=CATAWBA)
    result["content_language"] = CATAWBA

    lex = result.get("lexicon_entries") or []
    if lex:
        raise RuntimeError(f"guard failure: {len(lex)} Woccon lexicon rows survived from {drive_path}")

    staging = drive_extract._staging_dir_for_model(None)
    drive_extract._write_one_file_staging(result, staging)
    log.info(
        "%s: %d catawba entries, %d grammar, %d pronunciation in %.0fs",
        pdf.name,
        len(result.get("catawba_entries") or []),
        len(result.get("grammar_notes") or []),
        len(result.get("pronunciation_notes") or []),
        time.monotonic() - started,
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="directory of Catawba PDFs")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--ocr-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = Path(args.dir).expanduser()
    pdfs = sorted(p for p in root.rglob("*.pdf"))
    if not pdfs:
        log.error("no PDFs under %s", root)
        return 1

    # Only documents inside the Catawba Language folder are Catawba-language material.
    pdfs = [p for p in pdfs if DRIVE_FOLDER.lower() in {q.name.lower() for q in p.parents}]
    if not pdfs:
        log.error("no PDFs under a %r folder in %s", DRIVE_FOLDER, root)
        return 1

    print(f"Catawba documents to process ({len(pdfs)}):")
    for p in pdfs:
        print(f"  {p.name}")
    if args.dry_run:
        return 0

    failures = []
    for pdf in pdfs:
        try:
            payload = ocr_document(pdf, args.dpi)
            if not args.ocr_only:
                extract_document(pdf, payload.get("pages") or [])
        except Exception as exc:
            log.exception("FAILED %s: %s", pdf.name, exc)
            failures.append(pdf.name)

    if failures:
        log.error("completed with %d failure(s): %s", len(failures), ", ".join(failures))
        return 1
    log.info("all %d Catawba documents processed", len(pdfs))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
