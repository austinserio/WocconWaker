#!/usr/bin/env python3
"""Slice Rudes (2000) appendix text from cached OCR into raw text files."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / "data/ingest_text_cache"
DEFAULT_OUT = ROOT / "woccon_language/cognate_sets/_raw"
RUDES_PATH_FRAGMENT = "Resurrecting Coastal Catawban"
SOURCE_PATH = (
    "Articles/Resurrecting Coastal Catawban - "
    "The Reconstitudes Phonology and Morpology of the Woccon Language"
)


def find_rudes_cache(cache_dir: Path) -> Path:
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"Cache directory not found: {cache_dir}")
    matches: list[tuple[int, Path]] = []
    for p in cache_dir.glob("*.json"):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        path = obj.get("path") or ""
        if RUDES_PATH_FRAGMENT in path and path.endswith(".pdf") is False:
            text = obj.get("text") or ""
            matches.append((len(text), p))
    if not matches:
        for p in cache_dir.glob("*.json"):
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if RUDES_PATH_FRAGMENT in (obj.get("path") or ""):
                matches.append((len(obj.get("text") or ""), p))
    if not matches:
        raise FileNotFoundError(
            f"No Rudes OCR cache under {cache_dir} (looked for {RUDES_PATH_FRAGMENT!r})"
        )
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[0][1]


def slice_appendices(text: str, max_appendix: int = 4) -> dict[int, str]:
    """Return appendix number -> body text (between APPENDIX N and APPENDIX N+1)."""
    markers: list[tuple[int, int, str]] = []
    for m in re.finditer(r"APPENDIX\s+(\d+)\.", text, re.IGNORECASE):
        markers.append((m.start(), int(m.group(1)), m.group(0)))
    if not markers:
        raise ValueError("No APPENDIX markers found in OCR text")
    markers.sort(key=lambda x: x[0])
    out: dict[int, str] = {}
    for i, (start, num, _label) in enumerate(markers):
        if num > max_appendix:
            continue
        end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        body = text[start:end].strip()
        out[num] = body
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE,
        help="Directory containing ingest_text_cache JSON files",
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=None,
        help="Explicit OCR cache JSON (overrides --cache-dir search)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT,
        help="Output directory for appN.txt slices",
    )
    parser.add_argument(
        "--max-appendix",
        type=int,
        default=4,
        help="Highest appendix number to extract (default 4)",
    )
    args = parser.parse_args()

    cache_file = args.cache_file or find_rudes_cache(args.cache_dir)
    obj = json.loads(cache_file.read_text(encoding="utf-8"))
    text = obj.get("text") or ""
    if not text.strip():
        print(f"ERROR: empty text in {cache_file}", file=sys.stderr)
        return 1

    slices = slice_appendices(text, max_appendix=args.max_appendix)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "cache_file": str(cache_file.relative_to(ROOT)) if cache_file.is_relative_to(ROOT) else str(cache_file),
        "source_path": SOURCE_PATH,
        "appendices": {},
    }
    for num in range(1, args.max_appendix + 1):
        body = slices.get(num)
        if not body:
            print(f"WARNING: APPENDIX {num} not found", file=sys.stderr)
            continue
        out_path = args.out_dir / f"app{num}.txt"
        out_path.write_text(body + "\n", encoding="utf-8")
        meta["appendices"][str(num)] = {"path": str(out_path.relative_to(ROOT)), "chars": len(body)}
        print(f"Wrote {out_path} ({len(body)} chars)")

    meta_path = args.out_dir / "manifest.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
