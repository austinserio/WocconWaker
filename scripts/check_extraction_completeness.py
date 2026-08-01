#!/usr/bin/env python3
"""
Heuristic completeness check: compare regex-detected vocabulary lines in source text
against staged lexicon_entries from drive_extract output.

Usage:
  python scripts/check_extraction_completeness.py \\
    --source-text /path/to/doc.txt \\
    --staging woccon_language/drive_staging/English-Woccon.json

  python scripts/check_extraction_completeness.py --bulk \\
    --staging-dir woccon_language/drive_staging
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

DEFAULT_STAGING_DIR = ROOT / "woccon_language" / "drive_staging"
SKIP_STAGING_FILES = {"manifest.json", "sync_state.json"}
PAGE_MARKER_RE = re.compile(r"^\s*--\s*\d+\s+of\s+\d+\s*--\s*$", re.IGNORECASE)
URL_RE = re.compile(r"https?://", re.IGNORECASE)
LEXICON_LINE_RE = re.compile(r"^\s*(.+?)\s*([=:])\s*(.+?)\s*$")
LEXICON_LINE_DASH_RE = re.compile(r"^\s*(.+?)\s*-\s*(.+?)\s*$")
SKIP_ENGLISH = {
    "i",
    "e",
    "a",
    "u",
    "i:",
    "e:",
    "a:",
    "u:",
}
SKIP_WOCCON_FRAGMENTS = (
    "same as above",
    "living dictionary entry",
)


def normalize_woccon(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (w or "").strip().lower())


def normalize_english(e: str) -> str:
    return re.sub(r"\s+", " ", (e or "").strip().lower())


def lexicon_key(woccon: str, english: str) -> str:
    return f"{normalize_woccon(woccon)}\x00{normalize_english(english)}"


def strip_woccon_right(right: str) -> str:
    woccon = (right or "").strip()
    for sep in [" (", " [", " -or-", "\t"]:
        if sep in woccon:
            woccon = woccon.split(sep)[0].strip()
    return " ".join(woccon.split())


def should_skip_candidate(english: str, woccon: str) -> bool:
    eng = normalize_english(english)
    w = woccon.strip().lower()
    if not eng or not w:
        return True
    if eng in SKIP_ENGLISH:
        return True
    if any(skip in w for skip in SKIP_WOCCON_FRAGMENTS):
        return True
    if URL_RE.search(w) or URL_RE.search(english):
        return True
    if len(eng) > 120 or len(w) > 120:
        return True
    if eng.startswith("possible ") and "?" in english:
        return False
    return False


def iter_lexicon_candidates(text: str) -> Iterable[Tuple[str, str, str]]:
    """Yield (english, woccon, source_line) heuristic candidates from raw text."""
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or PAGE_MARKER_RE.match(line):
            continue
        if line.startswith("[[PAGE ") or line.startswith("#"):
            continue

        match = LEXICON_LINE_RE.match(line)
        if match:
            english, _delim, right = match.group(1), match.group(2), match.group(3)
            woccon = strip_woccon_right(right)
        else:
            match = LEXICON_LINE_DASH_RE.match(line)
            if not match:
                continue
            english, right = match.group(1), match.group(2)
            woccon = strip_woccon_right(right)

        english = english.strip().strip('"')
        if should_skip_candidate(english, woccon):
            continue
        yield english, woccon, line


def load_staging_lexicon(staging_path: Path) -> List[Dict[str, Any]]:
    with staging_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("lexicon_entries") or [])


def staging_keys(entries: Iterable[Dict[str, Any]]) -> Set[str]:
    keys: Set[str] = set()
    for entry in entries:
        w = (entry.get("woccon") or "").strip()
        e = (entry.get("english") or "").strip()
        if w and e:
            keys.add(lexicon_key(w, e))
    return keys


def compare_source_to_staging(source_text: str, staging_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    candidates = list(iter_lexicon_candidates(source_text))
    extracted_keys = staging_keys(staging_entries)
    missing: List[Dict[str, str]] = []
    matched = 0
    for english, woccon, line in candidates:
        key = lexicon_key(woccon, english)
        if key in extracted_keys:
            matched += 1
        else:
            missing.append({"english": english, "woccon": woccon, "source_line": line})

    candidate_count = len(candidates)
    pct = round(100.0 * matched / candidate_count, 1) if candidate_count else 100.0
    return {
        "candidate_count": candidate_count,
        "staging_count": len(staging_entries),
        "matched_count": matched,
        "missing_count": len(missing),
        "completeness_pct": pct,
        "missing": missing,
    }


def parse_drive_file_id(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if qs.get("id"):
        return qs["id"][0]
    return None


def fetch_drive_text(file_id: str) -> str:
    import drive_ingest

    creds = drive_ingest._get_credentials()
    service = drive_ingest._build_drive_service(creds)
    meta = service.files().get(fileId=file_id, fields="mimeType,name").execute()
    mime = meta.get("mimeType", "")
    if mime == drive_ingest.GOOGLE_DOCS_MIME:
        return drive_ingest.fetch_doc_text(service, file_id)
    if mime == drive_ingest.PDF_MIME:
        return drive_ingest.fetch_pdf_text(service, file_id)
    raise ValueError(f"Unsupported Drive mime type for completeness check: {mime}")


def load_source_text_for_staging(staging_path: Path, source_text: Optional[Path]) -> str:
    if source_text:
        return source_text.read_text(encoding="utf-8", errors="replace")
    with staging_path.open("r", encoding="utf-8") as f:
        staging = json.load(f)
    source_url = staging.get("source_url") or ""
    file_id = parse_drive_file_id(source_url)
    if not file_id:
        raise ValueError(
            f"No --source-text provided and could not parse Drive file id from {staging_path}"
        )
    return fetch_drive_text(file_id)


def print_report(label: str, report: Dict[str, Any], *, show_missing: int = 20) -> None:
    print("=" * 72)
    print(label)
    print("=" * 72)
    print(f"  Heuristic candidates: {report['candidate_count']}")
    print(f"  Staging lexicon rows: {report['staging_count']}")
    print(f"  Matched:              {report['matched_count']}")
    print(f"  Likely missing:       {report['missing_count']}")
    print(f"  Completeness:         {report['completeness_pct']}%")
    if report["missing"]:
        print()
        print("Likely missing entries:")
        for item in report["missing"][:show_missing]:
            print(f"  {item['english']} = {item['woccon']}")
        if len(report["missing"]) > show_missing:
            print(f"  ... and {len(report['missing']) - show_missing} more")


def run_single(staging_path: Path, source_text: Optional[Path], show_missing: int) -> int:
    staging_entries = load_staging_lexicon(staging_path)
    text = load_source_text_for_staging(staging_path, source_text)
    report = compare_source_to_staging(text, staging_entries)
    print_report(staging_path.name, report, show_missing=show_missing)
    return 0 if report["missing_count"] == 0 else 1


def run_bulk(staging_dir: Path, show_missing: int) -> int:
    manifest_path = staging_dir / "manifest.json"
    if not manifest_path.is_file():
        print(f"Missing manifest: {manifest_path}", file=sys.stderr)
        return 2

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    files = manifest.get("files") or []
    worst_pct = 100.0
    exit_code = 0
    summary_rows = []

    for entry in files:
        staging_file = entry.get("file")
        if not staging_file:
            continue
        staging_path = staging_dir / staging_file
        if not staging_path.is_file():
            continue
        try:
            staging_entries = load_staging_lexicon(staging_path)
            text = load_source_text_for_staging(staging_path, None)
            report = compare_source_to_staging(text, staging_entries)
        except Exception as exc:
            print(f"SKIP {staging_file}: {exc}")
            continue
        summary_rows.append((report["completeness_pct"], staging_file, report))
        worst_pct = min(worst_pct, report["completeness_pct"])
        if report["missing_count"]:
            exit_code = 1

    print("Bulk extraction completeness summary")
    print("-" * 72)
    for pct, staging_file, report in sorted(summary_rows, key=lambda row: row[0]):
        print(
            f"{pct:5.1f}%  missing={report['missing_count']:3d}  "
            f"candidates={report['candidate_count']:4d}  staging={report['staging_count']:4d}  {staging_file}"
        )
    print("-" * 72)
    print(f"Lowest completeness: {worst_pct}%")
    if exit_code:
        print("\nDocuments with likely missing entries:")
        for pct, staging_file, report in sorted(summary_rows, key=lambda row: row[0]):
            if not report["missing_count"]:
                continue
            print(f"\n{staging_file} ({pct}% complete, {report['missing_count']} missing)")
            for item in report["missing"][:show_missing]:
                print(f"  {item['english']} = {item['woccon']}")
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="Heuristic extraction completeness checker")
    parser.add_argument("--staging", type=Path, help="Path to one staging JSON file")
    parser.add_argument("--source-text", type=Path, help="Optional raw source text file")
    parser.add_argument("--bulk", action="store_true", help="Check all files listed in manifest.json")
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=DEFAULT_STAGING_DIR,
        help=f"Staging directory for --bulk (default: {DEFAULT_STAGING_DIR})",
    )
    parser.add_argument("--show-missing", type=int, default=20, help="Max missing rows to print per doc")
    args = parser.parse_args()

    if args.bulk:
        return run_bulk(args.staging_dir, args.show_missing)
    if not args.staging:
        parser.error("Provide --staging FILE or use --bulk")
    return run_single(args.staging, args.source_text, args.show_missing)


if __name__ == "__main__":
    raise SystemExit(main())
