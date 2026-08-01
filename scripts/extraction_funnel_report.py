#!/usr/bin/env python3
"""
Report extraction funnel counts from staging JSON through pending to canonical DB,
and flag orphaned staging files or stalled pending rows.

Usage:
  python scripts/extraction_funnel_report.py
  python scripts/extraction_funnel_report.py --staging-dir woccon_language/drive_staging
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def _ensure_project_python() -> None:
    try:
        import sqlalchemy  # noqa: F401
        return
    except ImportError:
        pass
    venv_python = ROOT / ".venv" / "bin" / "python3"
    running_via_venv = Path(sys.executable).resolve().parent == (ROOT / ".venv" / "bin").resolve()
    if not running_via_venv and venv_python.is_file():
        os.execv(str(venv_python), [str(venv_python), *sys.argv])
    print(
        "Missing project dependencies. Use:\n\n"
        "  .venv/bin/python scripts/extraction_funnel_report.py\n",
        file=sys.stderr,
    )
    sys.exit(1)


_ensure_project_python()

from panel_api.config import get_settings
from panel_api.db import CanonicalLexicon, CanonicalRule, PendingLexicon, PendingRule, SourceDocument, get_session_factory

DEFAULT_STAGING_DIR = ROOT / "woccon_language" / "drive_staging"
SKIP_STAGING_FILES = {"manifest.json", "sync_state.json"}
DRIVE_D_ID_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)")
DRIVE_OPEN_RE = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")


def parse_drive_file_id(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    m = DRIVE_D_ID_RE.search(url.strip())
    if m:
        return m.group(1)
    m = DRIVE_OPEN_RE.search(url)
    if m:
        return m.group(1)
    return None


def urls_match(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    a, b = a.strip(), b.strip()
    if a == b:
        return True
    fa, fb = parse_drive_file_id(a), parse_drive_file_id(b)
    if fa and fb:
        return fa == fb
    return a.rstrip("/") == b.rstrip("/")


def load_manifest_files(staging_dir: Path) -> Dict[str, Dict[str, Any]]:
    manifest_path = staging_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    with manifest_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    out: Dict[str, Dict[str, Any]] = {}
    for entry in data.get("files") or []:
        fname = entry.get("file")
        if fname:
            out[fname] = entry
    return out


def load_staging_counts(staging_dir: Path, filename: str) -> Dict[str, int]:
    path = staging_dir / filename
    if not path.is_file():
        return {"lexicon": 0, "grammar": 0, "pronunciation": 0, "cultural": 0}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        "lexicon": len(data.get("lexicon_entries") or []),
        "grammar": len(data.get("grammar_notes") or []),
        "pronunciation": len(data.get("pronunciation_notes") or []),
        "cultural": len(data.get("cultural_notes") or []),
    }


def find_source_document(
    docs: List[SourceDocument],
    *,
    source_url: Optional[str],
    source_path: Optional[str],
) -> Optional[SourceDocument]:
    file_id = parse_drive_file_id(source_url)
    for doc in docs:
        if file_id and doc.drive_file_id == file_id:
            return doc
        if source_url and urls_match(doc.source_url, source_url):
            return doc
        if source_path and (doc.title or "").strip() == (source_path or "").strip():
            return doc
    return None


def count_pending_for_doc(session, doc_id: str) -> Dict[str, int]:
    pending_lex = session.query(PendingLexicon).filter(PendingLexicon.source_document_id == doc_id).all()
    pending_rules = session.query(PendingRule).filter(PendingRule.source_document_id == doc_id).all()
    return {
        "pending_lexicon_total": len(pending_lex),
        "pending_lexicon_pending": sum(1 for r in pending_lex if r.status == "pending"),
        "pending_lexicon_approved": sum(1 for r in pending_lex if r.status == "approved"),
        "pending_rules_total": len(pending_rules),
        "pending_rules_pending": sum(1 for r in pending_rules if r.status == "pending"),
        "pending_rules_approved": sum(1 for r in pending_rules if r.status == "approved"),
    }


def count_canonical_for_doc(session, doc_id: str) -> Dict[str, int]:
    return {
        "canonical_lexicon": session.query(CanonicalLexicon).filter(
            CanonicalLexicon.source_document_id == doc_id
        ).count(),
        "canonical_rules": session.query(CanonicalRule).filter(
            CanonicalRule.source_document_id == doc_id
        ).count(),
    }


def find_stalled_pending(session, *, days: int) -> List[Dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        session.query(PendingLexicon)
        .filter(PendingLexicon.status == "pending", PendingLexicon.created_at <= cutoff)
        .all()
    )
    out = []
    for row in rows:
        out.append(
            {
                "type": "lexicon",
                "id": row.id,
                "woccon": row.woccon,
                "english": row.english,
                "source_document_id": row.source_document_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    rule_rows = (
        session.query(PendingRule)
        .filter(PendingRule.status == "pending", PendingRule.created_at <= cutoff)
        .all()
    )
    for row in rule_rows:
        out.append(
            {
                "type": "rule",
                "id": row.id,
                "category": row.category,
                "content_preview": (row.content or "")[:120],
                "source_document_id": row.source_document_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Extraction funnel and orphan report")
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=DEFAULT_STAGING_DIR,
        help=f"Drive staging directory (default: {DEFAULT_STAGING_DIR})",
    )
    parser.add_argument(
        "--stalled-days",
        type=int,
        default=get_settings().pending_duplicate_days,
        help="Flag pending rows older than this many days",
    )
    args = parser.parse_args()

    staging_dir = args.staging_dir
    manifest = load_manifest_files(staging_dir)
    manifest_files: Set[str] = set(manifest.keys())
    all_staging_files = {
        p.name
        for p in staging_dir.glob("*.json")
        if p.name not in SKIP_STAGING_FILES
    }
    orphaned = sorted(all_staging_files - manifest_files)

    session = get_session_factory()()
    try:
        docs = session.query(SourceDocument).filter(SourceDocument.is_seed.is_(False)).all()
        rows: List[Dict[str, Any]] = []
        flags: List[str] = []

        for filename in sorted(manifest_files):
            meta = manifest[filename]
            counts = load_staging_counts(staging_dir, filename)
            doc = find_source_document(
                docs,
                source_url=meta.get("source_url"),
                source_path=meta.get("source_path"),
            )
            pending = count_pending_for_doc(session, doc.id) if doc else {}
            canonical = count_canonical_for_doc(session, doc.id) if doc else {}
            row = {
                "staging_file": filename,
                "source_path": meta.get("source_path"),
                "source_url": meta.get("source_url"),
                "staging_lexicon": counts["lexicon"],
                "staging_rules": counts["grammar"] + counts["pronunciation"] + counts["cultural"],
                "library_document_id": doc.id if doc else None,
                "library_title": doc.title if doc else None,
                **pending,
                **canonical,
            }
            rows.append(row)
            if counts["lexicon"] and doc and pending.get("pending_lexicon_total", 0) == 0 and canonical.get("canonical_lexicon", 0) == 0:
                flags.append(
                    f"STAGED_BUT_NOT_IN_DB: {filename} has {counts['lexicon']} staged lexicon rows but no pending/canonical rows"
                )
            if not doc and (counts["lexicon"] or counts["grammar"] or counts["pronunciation"] or counts["cultural"]):
                flags.append(f"NO_LIBRARY_DOC: {filename} has staged content but no matching SourceDocument")

        stalled = find_stalled_pending(session, days=args.stalled_days)
    finally:
        session.close()

    print("Extraction funnel report")
    print("=" * 100)
    print(f"Staging dir: {staging_dir}")
    print(f"Manifest files: {len(manifest_files)}  |  Orphan staging JSON: {len(orphaned)}")
    print()
    print(f"{'Staging file':<55} {'StgLex':>6} {'PndLex':>6} {'CanLex':>6} {'StgRule':>7} {'PndRule':>7} {'CanRule':>7}")
    print("-" * 100)
    for row in rows:
        print(
            f"{row['staging_file'][:53]:<55} "
            f"{row['staging_lexicon']:>6} "
            f"{row.get('pending_lexicon_total', 0):>6} "
            f"{row.get('canonical_lexicon', 0):>6} "
            f"{row['staging_rules']:>7} "
            f"{row.get('pending_rules_total', 0):>7} "
            f"{row.get('canonical_rules', 0):>7}"
        )

    if orphaned:
        print()
        print("Orphan staging files (on disk but not in manifest.json):")
        for name in orphaned:
            counts = load_staging_counts(staging_dir, name)
            print(
                f"  {name}  lexicon={counts['lexicon']}  "
                f"grammar={counts['grammar']}  pronunciation={counts['pronunciation']}  cultural={counts['cultural']}"
            )

    if flags:
        print()
        print("Flags:")
        for flag in flags:
            print(f"  - {flag}")

    if stalled:
        print()
        print(f"Stalled pending rows (>{args.stalled_days} days):")
        for item in stalled[:30]:
            if item["type"] == "lexicon":
                print(
                    f"  lexicon {item['id']}: {item['woccon']} = {item['english']} "
                    f"(doc={item['source_document_id']}, created={item['created_at']})"
                )
            else:
                print(
                    f"  rule {item['id']}: [{item['category']}] {item['content_preview']} "
                    f"(doc={item['source_document_id']}, created={item['created_at']})"
                )
        if len(stalled) > 30:
            print(f"  ... and {len(stalled) - 30} more")

    return 1 if orphaned or flags else 0


if __name__ == "__main__":
    raise SystemExit(main())
