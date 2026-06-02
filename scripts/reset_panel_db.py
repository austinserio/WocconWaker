#!/usr/bin/env python3
"""Backup panel SQLite DB and optionally wipe for a clean Library rebuild."""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

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
    if venv_python.is_file() and Path(sys.executable).resolve() != venv_python.resolve():
        os.execv(str(venv_python), [str(venv_python), *sys.argv])
    print("Missing sqlalchemy. Run: .venv/bin/pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)


_ensure_project_python()


def _db_path_from_url(url: str) -> Path | None:
    if not url.startswith("sqlite:///"):
        return None
    path = url.replace("sqlite:///", "", 1)
    if path.startswith(":"):
        return None
    return Path(path)


def backup_assets(db_url: str, backup_dir: Path) -> dict:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    summary: dict = {"timestamp": ts, "backups": []}

    db_path = _db_path_from_url(db_url)
    if db_path and db_path.is_file():
        dest = backup_dir / f"woccon_{ts}.db"
        shutil.copy2(db_path, dest)
        summary["backups"].append(str(dest))

    for name in ("dictionary_unified.json", "rules_unified.json"):
        src = ROOT / "woccon_language" / name
        if src.is_file():
            dest = backup_dir / f"{src.stem}_{ts}.json"
            shutil.copy2(src, dest)
            summary["backups"].append(str(dest))

    for name in ("reprocess_urls.txt", "reprocess_urls.md"):
        src = ROOT / "data" / name
        if src.is_file():
            dest = backup_dir / f"{src.stem}_{ts}{src.suffix}"
            shutil.copy2(src, dest)
            summary["backups"].append(str(dest))

    manifest = backup_dir / f"backup_manifest_{ts}.json"
    manifest.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["manifest"] = str(manifest)
    return summary


def wipe_panel_data(db_url: str) -> dict:
    from panel_api.db import (
        AuditLog,
        CanonicalLexicon,
        CanonicalRule,
        PendingLexicon,
        PendingRule,
        SourceDocument,
        get_session_factory,
        init_db,
    )

    init_db()
    db = get_session_factory()()
    counts = {}
    try:
        for model, label in [
            (PendingLexicon, "pending_lexicon"),
            (PendingRule, "pending_rules"),
            (CanonicalLexicon, "canonical_lexicon"),
            (CanonicalRule, "canonical_rules"),
            (AuditLog, "audit_log"),
            (SourceDocument, "source_documents"),
        ]:
            n = db.query(model).delete(synchronize_session=False)
            counts[label] = n
        db.commit()
    finally:
        db.close()
    return counts


def clear_pending_data(db_url: str, *, remove_ingested_documents: bool = True) -> dict:
    """Remove pending review queue; preserve canonical Lawson core and users."""
    from panel_api.db import (
        CanonicalLexicon,
        PendingLexicon,
        PendingRule,
        SourceDocument,
        get_session_factory,
        init_db,
    )

    init_db()
    db = get_session_factory()()
    counts: dict = {}
    try:
        counts["pending_lexicon"] = db.query(PendingLexicon).delete(synchronize_session=False)
        counts["pending_rules"] = db.query(PendingRule).delete(synchronize_session=False)
        if remove_ingested_documents:
            counts["source_documents_removed"] = (
                db.query(SourceDocument).filter(SourceDocument.is_seed.is_(False)).delete(synchronize_session=False)
            )
        db.commit()
        counts["canonical_lexicon_remaining"] = db.query(CanonicalLexicon).count()
    finally:
        db.close()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup and optionally wipe panel DB for clean rebuild")
    parser.add_argument("--backup", action="store_true", help="Copy DB and unified JSON to data/backups/")
    parser.add_argument("--wipe", action="store_true", help="Delete all panel data except users (requires --backup)")
    parser.add_argument(
        "--clear-pending",
        action="store_true",
        help="Delete pending lexicon/rules only; keep canonical Lawson core and users",
    )
    parser.add_argument(
        "--keep-documents",
        action="store_true",
        help="With --clear-pending, keep non-seed Library documents (default: remove them)",
    )
    parser.add_argument("--no-backup", action="store_true", help="Skip backup (not allowed with --wipe)")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=ROOT / "data" / "backups",
        help="Backup destination directory",
    )
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL", "sqlite:///./data/woccon.db")

    if args.wipe and args.no_backup:
        print("Refusing --wipe without backup. Omit --no-backup or run --backup first.", file=sys.stderr)
        return 1

    if args.clear_pending and args.wipe:
        print("Use either --clear-pending or --wipe, not both.", file=sys.stderr)
        return 1

    if not args.backup and not args.wipe and not args.clear_pending:
        parser.print_help()
        return 1

    if args.backup or args.wipe or args.clear_pending:
        print(f"Backing up to {args.backup_dir} …")
        summary = backup_assets(db_url, args.backup_dir)
        print(json.dumps(summary, indent=2))

    if args.clear_pending:
        print("\nClearing pending queue (canonical lexicon/rules preserved) …")
        counts = clear_pending_data(db_url, remove_ingested_documents=not args.keep_documents)
        print(json.dumps(counts, indent=2))
        print(
            "\nAttested core retained in Dictionary. Next steps:\n"
            "  1. Ingest Woccon-specific sources only (Lawson PDF, Carter, English-Woccon, etc.)\n"
            "  2. Review Pending before Commit\n"
            "  3. Defer broad Siouan surveys until extraction relevance filtering is in place"
        )

    if args.wipe:
        print("\nWiping panel data (users table preserved) …")
        counts = wipe_panel_data(db_url)
        print(json.dumps(counts, indent=2))
        print(
            "\nNext steps:\n"
            "  1. Set PANEL_IMPORT_COMMUNITY=false in .env (default in .env.example)\n"
            "  2. Restart the app: python app.py\n"
            "  3. Bootstrap will import Lawson-only lexicon (~141 words) from dictionary.json\n"
            "  4. Reprocess Drive URLs: python scripts/list_reprocess_urls.py\n"
            "  5. Upload one URL at a time via Library; review Pending before Commit"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
