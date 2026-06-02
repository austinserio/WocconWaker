#!/usr/bin/env python3
"""Re-run page-aware extraction on staging JSON, panel DB, or canonical citations."""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("backfill_provenance")

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
    """Re-exec with .venv Python when project deps are missing."""
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
        "Missing project dependencies (sqlalchemy). Use the project virtualenv:\n\n"
        "  source .venv/bin/activate\n"
        "  pip install -r requirements.txt\n"
        "  python scripts/backfill_provenance.py --from-citations\n\n"
        "Or run directly:\n\n"
        "  .venv/bin/python scripts/backfill_provenance.py --from-citations\n",
        file=sys.stderr,
    )
    sys.exit(1)


_ensure_project_python()


def backfill_staging(staging_dir: str, dry_run: bool = False) -> dict:
    staging_path = Path(staging_dir)
    stats = {"files": 0, "verified": 0, "inferred": 0, "missing": 0}
    for p in sorted(staging_path.glob("*.json")):
        if p.name in ("manifest.json", "sync_state.json"):
            continue
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if "lexicon_entries" not in data:
            continue
        stats["files"] += 1
        for e in data.get("lexicon_entries") or []:
            st = e.get("provenance_status") or "missing"
            stats[st] = stats.get(st, 0) + 1
        log.info(
            "%s: %d lexicon, locators present=%d",
            p.name,
            len(data.get("lexicon_entries") or []),
            sum(1 for e in data.get("lexicon_entries") or [] if e.get("source_page")),
        )
    return stats


def backfill_db(document_id: str | None = None, dry_run: bool = False) -> dict:
    from panel_api.db import SourceDocument, get_session_factory, init_db
    from panel_api.services.ingest import process_document, reload_document_text

    init_db()
    db = get_session_factory()()
    try:
        q = db.query(SourceDocument).filter(SourceDocument.is_seed.is_(False))
        if document_id:
            q = q.filter(SourceDocument.id == document_id)
        docs = q.all()
        summary = {"documents": len(docs), "results": []}
        for doc in docs:
            if dry_run:
                summary["results"].append({"document_id": doc.id, "title": doc.title, "dry_run": True})
                continue
            try:
                text, _ = reload_document_text(doc)
            except ValueError as e:
                log.warning("Skip %s: %s", doc.title, e)
                summary["results"].append({"document_id": doc.id, "error": str(e)})
                continue
            doc.status = "processing"
            db.commit()
            result = process_document(
                db,
                doc,
                text,
                merge_locators=True,
                replace_pending=True,
            )
            summary["results"].append(result)
            log.info("Re-extracted %s: %s", doc.title, result)
        return summary
    finally:
        db.close()


def backfill_citations(
    file_id: str | None = None,
    dry_run: bool = False,
    export: bool = False,
    text_only: bool = False,
) -> dict:
    from panel_api.db import get_session_factory, init_db
    from panel_api.services.citation_backfill import backfill_from_citations
    from panel_api.services.commit import export_unified_json

    init_db()
    db = get_session_factory()()
    try:
        summary = backfill_from_citations(
            db, dry_run=dry_run, file_id_filter=file_id, text_only=text_only
        )
        if export and not dry_run:
            summary["export_paths"] = export_unified_json(db)
        return summary
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill bibliographic provenance")
    parser.add_argument("--staging-dir", default=os.environ.get("DRIVE_STAGING_DIR", "woccon_language/drive_staging"))
    parser.add_argument("--document-id", help="Re-extract one panel SourceDocument by ID (--db mode)")
    parser.add_argument("--file-id", help="Re-extract one cited Drive file by ID (--from-citations mode)")
    parser.add_argument("--db", action="store_true", help="Re-extract Library uploads in source_documents")
    parser.add_argument(
        "--from-citations",
        action="store_true",
        help="Discover Drive sources from canonical source_url and re-extract (recommended)",
    )
    parser.add_argument(
        "--text-only",
        action="store_true",
        help="Skip LLM re-extract; search source PDF text for page locators (fast re-run)",
    )
    parser.add_argument("--export", action="store_true", help="Write dictionary_unified.json / rules_unified.json after backfill")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.from_citations or args.file_id:
        summary = backfill_citations(args.file_id, dry_run=args.dry_run, export=args.export, text_only=args.text_only)
    elif args.db or args.document_id:
        summary = backfill_db(args.document_id, dry_run=args.dry_run)
    else:
        summary = backfill_staging(args.staging_dir, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
