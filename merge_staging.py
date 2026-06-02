"""
Phase 4: Build unified lexicon and notes from Drive staging, compare to legacy dictionary,
produce report and unified files. Every entry includes source_url for citation (e.g. in Frappe).
"""
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("merge_staging")

STAGING_DIR = os.environ.get("DRIVE_STAGING_DIR", "woccon_language/drive_staging")
DICTIONARY_PATH = "woccon_language/dictionary.json"
RULES_PATH = "woccon_language/rules.json"
OUTPUT_LEXICON_FROM_DRIVE = "woccon_language/lexicon_from_drive.json"
OUTPUT_COMPARISON_REPORT = "woccon_language/merge_comparison_report.json"
OUTPUT_DICTIONARY_UNIFIED = "woccon_language/dictionary_unified.json"
OUTPUT_COMMUNITY_NOTES = "woccon_language/community_notes.json"
OUTPUT_RULES_UNIFIED = "woccon_language/rules_unified.json"
BACKUP_SUFFIX = "_backup_{}.json"


def _normalize_woccon(w: str) -> str:
    return (w or "").strip().lower()


def load_staging_files(staging_dir: str) -> List[Dict[str, Any]]:
    """Load all staging JSONs that have lexicon_entries (skip manifest)."""
    staging_path = Path(staging_dir)
    if not staging_path.exists():
        log.warning("Staging dir %s does not exist", staging_dir)
        return []
    files_data = []
    for p in sorted(staging_path.glob("*.json")):
        if p.name == "manifest.json":
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "lexicon_entries" not in data:
                continue
            files_data.append(data)
        except Exception as e:
            log.warning("Skip %s: %s", p.name, e)
    return files_data


def build_community_lexicon(files_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge lexicon from all staging files. Dedupe by woccon (lowercase); prefer entry with pronunciation. Every entry has source_url."""
    by_key: Dict[str, Dict[str, Any]] = {}
    for data in files_data:
        source_url = data.get("source_url")
        source_path = data.get("source_path", "unknown")
        for e in data.get("lexicon_entries") or []:
            w = (e.get("woccon") or "").strip()
            if not w:
                continue
            key = _normalize_woccon(w)
            entry = {
                "woccon": w,
                "english": (e.get("english") or "").strip(),
                "pos": (e.get("pos") or "").strip() or "unknown",
                "pronunciation": (e.get("pronunciation") or "").strip() or None,
                "source": "community_drive",
                "source_url": source_url,
            }
            for field in (
                "source_page",
                "source_page_end",
                "source_excerpt",
                "provenance_status",
                "citation_short",
                "citation_full",
            ):
                if e.get(field) is not None:
                    entry[field] = e.get(field)
            if not entry["english"]:
                continue
            existing = by_key.get(key)
            if existing is None or (entry.get("pronunciation") and not existing.get("pronunciation")):
                by_key[key] = entry
    return list(by_key.values())


def build_community_notes(files_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, str]]]:
    """Build grammar_notes, pronunciation_notes, cultural_notes each as list of { text, source_url }."""
    grammar: List[Dict[str, str]] = []
    pronunciation: List[Dict[str, str]] = []
    cultural: List[Dict[str, str]] = []
    for data in files_data:
        url = data.get("source_url")
        for g in data.get("grammar_notes") or []:
            t = (g.get("text") if isinstance(g, dict) else str(g)).strip()
            if t:
                note = {"text": t, "source_url": url}
                if isinstance(g, dict):
                    for field in (
                        "source_page",
                        "source_page_end",
                        "source_excerpt",
                        "provenance_status",
                    ):
                        if g.get(field) is not None:
                            note[field] = g.get(field)
                grammar.append(note)
        for p in data.get("pronunciation_notes") or []:
            t = (p.get("text") if isinstance(p, dict) else str(p)).strip()
            if t:
                note = {"text": t, "source_url": url}
                if isinstance(p, dict):
                    for field in (
                        "source_page",
                        "source_page_end",
                        "source_excerpt",
                        "provenance_status",
                    ):
                        if p.get(field) is not None:
                            note[field] = p.get(field)
                pronunciation.append(note)
        for c in data.get("cultural_notes") or []:
            t = (c.get("text") if isinstance(c, dict) else str(c)).strip()
            if t:
                note = {"text": t, "source_url": url}
                if isinstance(c, dict):
                    for field in (
                        "source_page",
                        "source_page_end",
                        "source_excerpt",
                        "provenance_status",
                    ):
                        if c.get(field) is not None:
                            note[field] = c.get(field)
                cultural.append(note)
    return {"grammar_notes": grammar, "pronunciation_notes": pronunciation, "cultural_notes": cultural}


def load_legacy_dictionary(path: str) -> Dict[str, Any]:
    """Load dictionary.json."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_legacy_rules(path: str) -> Dict[str, Any]:
    """Load rules.json (structured phonology/morphology)."""
    if not path or not Path(path).exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_lexicons(
    community: List[Dict[str, Any]],
    legacy_lexicon: List[Dict[str, Any]],
) -> Tuple[List[str], List[str], List[str], Dict[str, Dict], Dict[str, Dict]]:
    """
    Returns (old_only_woccon, new_only_woccon, overlap_woccon, old_entries_by_key, community_entries_by_key).
    """
    old_keys = {_normalize_woccon(e.get("woccon") or ""): e for e in legacy_lexicon if (e.get("woccon") or "").strip()}
    new_keys = {_normalize_woccon(e.get("woccon") or ""): e for e in community if (e.get("woccon") or "").strip()}
    old_only = [k for k in old_keys if k not in new_keys]
    new_only = [k for k in new_keys if k not in old_keys]
    overlap = [k for k in old_keys if k in new_keys]
    return old_only, new_only, overlap, old_keys, new_keys


def build_unified_lexicon(
    community: List[Dict[str, Any]],
    legacy_lexicon: List[Dict[str, Any]],
    old_only: List[str],
    overlap: List[str],
    old_entries_by_key: Dict[str, Dict],
    community_entries_by_key: Dict[str, Dict],
) -> List[Dict[str, Any]]:
    """Unified list: community entries (with source_url) for overlap + new; Lawson-only for old_only with source_url null."""
    unified: List[Dict[str, Any]] = []
    # Add all community-derived entries (overlap + new_only). Community wins for overlap.
    for e in community:
        unified.append(dict(e))  # already has source_url
    # Add Lawson-only entries (no community version)
    for key in old_only:
        e = old_entries_by_key.get(key)
        if not e:
            continue
        unified.append({
            "woccon": (e.get("woccon") or "").strip(),
            "english": (e.get("english") or "").strip(),
            "pos": (e.get("pos") or "").strip() or "unknown",
            "pronunciation": None,
            "source": "lawson",
            "source_url": None,
        })
    return unified


def verify_merge(
    unified_lexicon: List[Dict[str, Any]],
    legacy_lexicon: List[Dict[str, Any]],
    legacy_rules: Dict[str, Any],
    unified_rules: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Check that no legacy lexicon or rules content was dropped. Returns verification dict for the report."""
    out: Dict[str, Any] = {"lexicon": {}, "rules": {}}
    # Lexicon: every legacy woccon (normalized) must appear in unified
    unified_keys = {_normalize_woccon(e.get("woccon") or "") for e in unified_lexicon if (e.get("woccon") or "").strip()}
    legacy_keys = {_normalize_woccon(e.get("woccon") or "") for e in legacy_lexicon if (e.get("woccon") or "").strip()}
    missing = sorted(legacy_keys - unified_keys)
    out["lexicon"] = {
        "legacy_entries": len(legacy_lexicon),
        "legacy_unique_woccon": len(legacy_keys),
        "unified_entries": len(unified_lexicon),
        "unified_unique_woccon": len(unified_keys),
        "legacy_all_in_unified": len(missing) == 0,
        "missing_legacy_woccon": missing,
    }
    # Rules: every legacy key must be in unified (we only add keys, never remove)
    if legacy_rules and unified_rules is not None:
        legacy_key_set = set(legacy_rules.keys())
        unified_key_set = set(unified_rules.keys())
        missing_rules_keys = sorted(legacy_key_set - unified_key_set)
        out["rules"] = {
            "legacy_key_count": len(legacy_rules),
            "unified_key_count": len(unified_rules),
            "legacy_keys_preserved": len(missing_rules_keys) == 0,
            "missing_legacy_keys": missing_rules_keys,
        }
    else:
        out["rules"] = {"legacy_keys_preserved": None, "note": "No legacy rules or unified rules to compare."}
    return out


def run_merge(
    staging_dir: Optional[str] = None,
    dictionary_path: Optional[str] = None,
    write_backup: bool = True,
) -> Dict[str, Any]:
    """
    Load staging, build community lexicon and notes, compare to legacy, write report and unified files.
    Returns summary dict.
    """
    staging_dir = staging_dir or STAGING_DIR
    dictionary_path = dictionary_path or DICTIONARY_PATH
    summary = {"staging_files": 0, "community_lexicon_count": 0, "old_only_count": 0, "new_only_count": 0, "overlap_count": 0}

    files_data = load_staging_files(staging_dir)
    summary["staging_files"] = len(files_data)
    if not files_data:
        log.warning("No staging files found in %s", staging_dir)
        return summary

    community_lexicon = build_community_lexicon(files_data)
    summary["community_lexicon_count"] = len(community_lexicon)
    community_notes = build_community_notes(files_data)

    # Save lexicon-from-drive (community only) for reference
    os.makedirs(os.path.dirname(OUTPUT_LEXICON_FROM_DRIVE) or ".", exist_ok=True)
    with open(OUTPUT_LEXICON_FROM_DRIVE, "w", encoding="utf-8") as f:
        json.dump({"source": "drive_staging", "lexicon": community_lexicon}, f, indent=2, ensure_ascii=False)
    log.info("Wrote %s", OUTPUT_LEXICON_FROM_DRIVE)

    legacy = load_legacy_dictionary(dictionary_path)
    legacy_lexicon = legacy.get("lexicon") or []
    old_only, new_only, overlap, old_by_key, new_by_key = compare_lexicons(community_lexicon, legacy_lexicon)
    summary["old_only_count"] = len(old_only)
    summary["new_only_count"] = len(new_only)
    summary["overlap_count"] = len(overlap)

    # Unified rules: legacy rules.json + community notes (grammar, pronunciation, cultural) with source_url
    rules_path = RULES_PATH
    legacy_rules = load_legacy_rules(rules_path)
    unified_rules = None
    if legacy_rules:
        unified_rules = dict(legacy_rules)
        unified_rules["community_grammar_notes"] = community_notes["grammar_notes"]
        unified_rules["community_pronunciation_notes"] = community_notes["pronunciation_notes"]
        unified_rules["community_cultural_notes"] = community_notes["cultural_notes"]
        unified_rules["source_note"] = "Legacy rules (phonology, morphology, etc.) plus community notes from Drive with source_url for citation."
        if write_backup:
            rules_backup = rules_path.replace(".json", BACKUP_SUFFIX.format(datetime.now(timezone.utc).strftime("%Y%m%d")))
            shutil.copy2(rules_path, rules_backup)
            log.info("Backed up rules to %s", rules_backup)
            summary["rules_backup_path"] = rules_backup
        with open(OUTPUT_RULES_UNIFIED, "w", encoding="utf-8") as f:
            json.dump(unified_rules, f, indent=2, ensure_ascii=False)
        log.info("Wrote %s", OUTPUT_RULES_UNIFIED)
        summary["rules_unified_grammar"] = len(community_notes["grammar_notes"])
        summary["rules_unified_pronunciation"] = len(community_notes["pronunciation_notes"])
        summary["rules_unified_cultural"] = len(community_notes["cultural_notes"])
    else:
        log.warning("No legacy rules at %s; skipping rules_unified.json", rules_path)

    unified_lexicon = build_unified_lexicon(
        community_lexicon,
        legacy_lexicon,
        old_only,
        overlap,
        old_by_key,
        new_by_key,
    )
    unified_dictionary = dict(legacy)
    unified_dictionary["lexicon"] = unified_lexicon
    unified_dictionary["source_note"] = "Merged: community_drive (with source_url) + lawson (source_url null). Community over Lawson for overlaps."

    verification = verify_merge(unified_lexicon, legacy_lexicon, legacy_rules, unified_rules)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "staging_dir": staging_dir,
        "legacy_dictionary": dictionary_path,
        "legacy_rules": rules_path,
        "rules_in_report": bool(legacy_rules),
        "counts": {
            "legacy_lexicon": len(legacy_lexicon),
            "community_lexicon": len(community_lexicon),
            "old_only_lawson": len(old_only),
            "new_only_community": len(new_only),
            "overlap_community_wins": len(overlap),
        },
        "rules": {
            "path": rules_path,
            "unified_path": OUTPUT_RULES_UNIFIED if legacy_rules else None,
            "merged": bool(legacy_rules),
            "note": "Unified = legacy rules (phonology, morphology, etc.) + community_grammar_notes, community_pronunciation_notes, community_cultural_notes from Drive (each item has source_url).",
        },
        "verification": verification,
        "old_only_woccon": sorted(old_only),
        "new_only_woccon": sorted(new_only),
        "overlap_woccon": sorted(overlap),
    }
    with open(OUTPUT_COMPARISON_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    log.info("Wrote %s", OUTPUT_COMPARISON_REPORT)
    if not verification["lexicon"]["legacy_all_in_unified"]:
        log.warning("Lexicon verification: %s legacy woccon missing from unified", verification["lexicon"]["missing_legacy_woccon"])
    if verification.get("rules", {}).get("legacy_keys_preserved") is False:
        log.warning("Rules verification: %s legacy keys missing from unified", verification["rules"]["missing_legacy_keys"])

    if write_backup:
        backup_path = dictionary_path.replace(".json", BACKUP_SUFFIX.format(datetime.now(timezone.utc).strftime("%Y%m%d")))
        shutil.copy2(dictionary_path, backup_path)
        log.info("Backed up dictionary to %s", backup_path)
        summary["backup_path"] = backup_path

    with open(OUTPUT_DICTIONARY_UNIFIED, "w", encoding="utf-8") as f:
        json.dump(unified_dictionary, f, indent=2, ensure_ascii=False)
    log.info("Wrote %s", OUTPUT_DICTIONARY_UNIFIED)
    summary["unified_lexicon_count"] = len(unified_lexicon)

    with open(OUTPUT_COMMUNITY_NOTES, "w", encoding="utf-8") as f:
        json.dump(community_notes, f, indent=2, ensure_ascii=False)
    log.info("Wrote %s", OUTPUT_COMMUNITY_NOTES)
    summary["community_notes_grammar"] = len(community_notes["grammar_notes"])
    summary["community_notes_pronunciation"] = len(community_notes["pronunciation_notes"])
    summary["community_notes_cultural"] = len(community_notes["cultural_notes"])

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    summary = run_merge()
    print(json.dumps(summary, indent=2))
