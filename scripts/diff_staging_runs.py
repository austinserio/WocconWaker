#!/usr/bin/env python3
"""
Compare two drive_extract staging directories (e.g. Opus vs local model).

Usage:
  python scripts/diff_staging_runs.py
  python scripts/diff_staging_runs.py --old woccon_language/drive_staging \\
      --new woccon_language/drive_staging_local
  python scripts/diff_staging_runs.py --file English-Woccon
  python scripts/diff_staging_runs.py --json-out data/tmp_staging_diff.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from drive_extract import _lexicon_dedup_key  # noqa: E402

DEFAULT_OLD = ROOT / "woccon_language" / "drive_staging"
DEFAULT_NEW = ROOT / "woccon_language" / "drive_staging_local"
SKIP_FILES = {"manifest.json", "sync_state.json"}
NOTE_BUCKETS = ("grammar_notes", "pronunciation_notes", "cultural_notes")
LEXICON_COMPARE_FIELDS = ("woccon", "english", "part_of_speech", "notes", "source")


def _safe_filename(path: str) -> str:
    from drive_extract import _safe_filename as sf

    return sf(path)


def _load_staging_file(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_staging_files(staging_dir: Path, file_filter: Optional[str]) -> Iterable[Tuple[str, Path]]:
    if not staging_dir.is_dir():
        return
    for p in sorted(staging_dir.glob("*.json")):
        if p.name in SKIP_FILES:
            continue
        if file_filter and file_filter.lower() not in p.stem.lower():
            continue
        yield p.stem, p


def _lexicon_map(entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for e in entries or []:
        woccon = (e.get("woccon") or "").strip()
        english = (e.get("english") or "").strip()
        if not woccon or not english:
            continue
        out[_lexicon_dedup_key(woccon, english)] = e
    return out


def _note_key(note: Any) -> str:
    if isinstance(note, str):
        return note.strip().lower()
    if isinstance(note, dict):
        return (note.get("text") or "").strip().lower()
    return ""


def _note_map(notes: List[Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for note in notes or []:
        if isinstance(note, str):
            note = {"text": note}
        if not isinstance(note, dict):
            continue
        key = _note_key(note)
        if key:
            out[key] = note
    return out


def _normalize_lexicon_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (entry.get(k) or "").strip() if isinstance(entry.get(k), str) else entry.get(k) for k in LEXICON_COMPARE_FIELDS}


def _entry_changed(old: Dict[str, Any], new: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    old_n = _normalize_lexicon_entry(old)
    new_n = _normalize_lexicon_entry(new)
    changes = {}
    for k in LEXICON_COMPARE_FIELDS:
        if old_n.get(k) != new_n.get(k):
            changes[k] = {"old": old_n.get(k), "new": new_n.get(k)}
    return changes or None


def _note_changed(old: Dict[str, Any], new: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if json.dumps(old, sort_keys=True) == json.dumps(new, sort_keys=True):
        return None
    return {"old": old, "new": new}


def diff_bucket_maps(
    old_map: Dict[str, Dict[str, Any]],
    new_map: Dict[str, Dict[str, Any]],
    *,
    key_label: str = "key",
) -> Dict[str, Any]:
    old_keys = set(old_map)
    new_keys = set(new_map)
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    changed = []
    for key in sorted(old_keys & new_keys):
        diff = _note_changed(old_map[key], new_map[key]) if key_label == "text" else _entry_changed(old_map[key], new_map[key])
        if diff:
            item = {key_label: key.split("\x00")[0] if key_label == "key" else key, "changes": diff}
            if key_label == "key":
                parts = key.split("\x00", 1)
                item["woccon"] = parts[0]
                item["english"] = parts[1] if len(parts) > 1 else ""
            changed.append(item)
    return {
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "added": [new_map[k] for k in added],
        "removed": [old_map[k] for k in removed],
        "changed": changed,
    }


def diff_staging_payload(old_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "source_path": new_data.get("source_path") or old_data.get("source_path"),
        "source_url": new_data.get("source_url") or old_data.get("source_url"),
    }
    result["lexicon"] = diff_bucket_maps(
        _lexicon_map(old_data.get("lexicon_entries") or []),
        _lexicon_map(new_data.get("lexicon_entries") or []),
        key_label="key",
    )
    for bucket in NOTE_BUCKETS:
        result[bucket] = diff_bucket_maps(
            _note_map(old_data.get(bucket) or []),
            _note_map(new_data.get(bucket) or []),
            key_label="text",
        )
    return result


def build_index(staging_dir: Path, file_filter: Optional[str]) -> Dict[str, Path]:
    index: Dict[str, Path] = {}
    for stem, path in _iter_staging_files(staging_dir, file_filter):
        index[stem] = path
    return index


def summarize_counts(diff: Dict[str, Any]) -> Dict[str, int]:
    out = {
        "lexicon_added": diff["lexicon"]["added_count"],
        "lexicon_removed": diff["lexicon"]["removed_count"],
        "lexicon_changed": diff["lexicon"]["changed_count"],
    }
    for bucket in NOTE_BUCKETS:
        out[f"{bucket}_added"] = diff[bucket]["added_count"]
        out[f"{bucket}_removed"] = diff[bucket]["removed_count"]
        out[f"{bucket}_changed"] = diff[bucket]["changed_count"]
    return out


def print_file_summary(name: str, diff: Dict[str, Any]) -> None:
    counts = summarize_counts(diff)
    print(f"\n=== {name} ===")
    print(f"  source: {diff.get('source_path') or name}")
    print(
        "  lexicon: "
        f"+{counts['lexicon_added']} -{counts['lexicon_removed']} ~{counts['lexicon_changed']}"
    )
    for bucket in NOTE_BUCKETS:
        label = bucket.replace("_notes", "")
        print(
            f"  {label}: "
            f"+{counts[f'{bucket}_added']} -{counts[f'{bucket}_removed']} ~{counts[f'{bucket}_changed']}"
        )


def print_aggregate(totals: Dict[str, int], file_count: int) -> None:
    print("\n=== Aggregate ===")
    print(f"  files compared: {file_count}")
    print(
        "  lexicon: "
        f"+{totals['lexicon_added']} -{totals['lexicon_removed']} ~{totals['lexicon_changed']}"
    )
    for bucket in NOTE_BUCKETS:
        label = bucket.replace("_notes", "")
        print(
            f"  {label}: "
            f"+{totals[f'{bucket}_added']} -{totals[f'{bucket}_removed']} ~{totals[f'{bucket}_changed']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff two drive_extract staging directories")
    parser.add_argument("--old", type=Path, default=DEFAULT_OLD, help="Baseline staging dir (e.g. Opus run)")
    parser.add_argument("--new", type=Path, default=DEFAULT_NEW, help="New staging dir (e.g. local model run)")
    parser.add_argument("--file", dest="file_filter", help="Only compare files whose stem contains this substring")
    parser.add_argument("--json-out", type=Path, help="Write full diff JSON to this path")
    parser.add_argument("--verbose", action="store_true", help="Print added/removed/changed details")
    args = parser.parse_args()

    old_dir = args.old if args.old.is_absolute() else ROOT / args.old
    new_dir = args.new if args.new.is_absolute() else ROOT / args.new

    if not old_dir.is_dir():
        print(f"Old staging dir not found: {old_dir}", file=sys.stderr)
        return 1
    if not new_dir.is_dir():
        print(f"New staging dir not found: {new_dir}", file=sys.stderr)
        return 1

    old_index = build_index(old_dir, args.file_filter)
    new_index = build_index(new_dir, args.file_filter)
    all_names = sorted(set(old_index) | set(new_index))

    report: Dict[str, Any] = {
        "old_dir": str(old_dir),
        "new_dir": str(new_dir),
        "files": {},
        "only_in_old": sorted(set(old_index) - set(new_index)),
        "only_in_new": sorted(set(new_index) - set(old_index)),
    }
    totals = {k: 0 for k in [
        "lexicon_added", "lexicon_removed", "lexicon_changed",
        *[f"{b}_{s}" for b in NOTE_BUCKETS for s in ("added", "removed", "changed")],
    ]}

    for name in all_names:
        if name not in old_index:
            continue
        if name not in new_index:
            continue
        old_data = _load_staging_file(old_index[name])
        new_data = _load_staging_file(new_index[name])
        diff = diff_staging_payload(old_data, new_data)
        report["files"][name] = diff
        print_file_summary(name, diff)
        counts = summarize_counts(diff)
        for k, v in counts.items():
            totals[k] += v
        if args.verbose:
            for section in ("lexicon", *NOTE_BUCKETS):
                for label in ("added", "removed", "changed"):
                    items = diff[section].get(label) or []
                    if items:
                        print(f"    {section} {label}:")
                        for item in items[:20]:
                            print(f"      {json.dumps(item, ensure_ascii=False)[:300]}")
                        if len(items) > 20:
                            print(f"      ... and {len(items) - 20} more")

    print_aggregate(totals, len(report["files"]))
    if report["only_in_old"]:
        print(f"\nOnly in old ({len(report['only_in_old'])}): {', '.join(report['only_in_old'][:10])}")
    if report["only_in_new"]:
        print(f"Only in new ({len(report['only_in_new'])}): {', '.join(report['only_in_new'][:10])}")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote full diff to {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
