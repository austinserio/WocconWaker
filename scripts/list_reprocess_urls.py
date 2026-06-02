#!/usr/bin/env python3
"""List Drive URLs to reprocess via Library (sources with extracted content)."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "woccon_language" / "drive_staging" / "manifest.json"
OUT_DIR = ROOT / "data"


def _item_count(entry: dict) -> int:
    return sum(
        entry.get(k, 0) or 0
        for k in ("lexicon_count", "grammar_count", "pronunciation_count", "cultural_count")
    )


def load_entries(manifest_path: Path, *, all_files: bool = False) -> list[dict]:
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    files = data.get("files") or []
    if all_files:
        return files
    return [e for e in files if _item_count(e) > 0]


def format_entries(entries: list[dict]) -> str:
    lines = []
    for i, e in enumerate(entries, start=1):
        title = e.get("source_path") or e.get("file") or "unknown"
        url = e.get("source_url") or ""
        count = _item_count(e)
        lines.append(f"{i:2d}. {title}  ({count} items)")
        lines.append(f"    {url}")
    return "\n".join(lines)


def write_outputs(entries: list[dict]) -> dict[str, str]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    txt_path = OUT_DIR / "reprocess_urls.txt"
    md_path = OUT_DIR / "reprocess_urls.md"

    txt_path.write_text("\n".join(e.get("source_url", "") for e in entries if e.get("source_url")) + "\n", encoding="utf-8")

    md_lines = [
        "# Reprocess URLs",
        "",
        "Drive sources with extracted content — ingest one at a time via Upload → Library → Pending → Commit.",
        "",
        "| # | Title | Items | URL |",
        "|---|-------|------:|-----|",
    ]
    for i, e in enumerate(entries, start=1):
        title = (e.get("source_path") or e.get("file") or "unknown").replace("|", "\\|")
        url = e.get("source_url") or ""
        count = _item_count(e)
        md_lines.append(f"| {i} | {title} | {count} | {url} |")
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return {"txt": str(txt_path), "md": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="List Drive URLs to reprocess via Library")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="Path to manifest.json")
    parser.add_argument("--all", action="store_true", help="Include empty sources (meeting notes, WIP)")
    parser.add_argument("--no-write", action="store_true", help="Print only; do not write data/reprocess_urls.*")
    args = parser.parse_args()

    if not args.manifest.is_file():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1

    entries = load_entries(args.manifest, all_files=args.all)
    entries.sort(key=lambda e: _item_count(e), reverse=True)

    print(f"Reprocess URLs ({len(entries)} sources):\n")
    print(format_entries(entries))

    if not args.no_write:
        paths = write_outputs(entries)
        print(f"\nWrote {paths['txt']}")
        print(f"Wrote {paths['md']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
