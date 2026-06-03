#!/usr/bin/env python3
"""Sync source_documents (Library) from your **current** local SQLite into Postgres.

Always uses ./data/woccon.db unless you override SQLITE_LIBRARY_SOURCE.
Creates a fresh backup under data/backups/ before writing to Postgres.

Usage:
  ./scripts/migrate_library_from_sqlite.py
  ./scripts/migrate_library_from_sqlite.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
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
        import psycopg  # noqa: F401
        import sqlalchemy  # noqa: F401
        return
    except ImportError:
        pass
    venv_python = ROOT / ".venv" / "bin" / "python3"
    if venv_python.is_file() and Path(sys.executable).resolve() != venv_python.resolve():
        os.execv(str(venv_python), [str(venv_python), *sys.argv])
    print("Missing deps. Run: pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)


_ensure_project_python()

sys.path.insert(0, str(ROOT / "scripts"))
from panel_db_transfer import make_engine, normalize_url  # noqa: E402
from reset_panel_db import backup_assets  # noqa: E402

from sqlalchemy import select  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from panel_api.db import SourceDocument  # noqa: E402

DEFAULT_SOURCE = "sqlite:///./data/woccon.db"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Library (source_documents) from current local SQLite → Postgres"
    )
    parser.add_argument(
        "--source",
        default=os.environ.get("SQLITE_LIBRARY_SOURCE", DEFAULT_SOURCE),
        help=f"SQLite URL (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-backup", action="store_true")
    args = parser.parse_args()

    if args.source != DEFAULT_SOURCE and "backup" in args.source:
        print(
            "WARNING: source looks like an old backup file. "
            f"Default is current DB: {DEFAULT_SOURCE}",
            file=sys.stderr,
        )

    target_url = normalize_url(os.environ.get("POSTGRES_DATABASE_URL", ""))
    if not target_url.startswith("postgresql"):
        print("Set POSTGRES_DATABASE_URL in .env", file=sys.stderr)
        sys.exit(1)

    if not args.skip_backup and not args.dry_run:
        summary = backup_assets(args.source, ROOT / "data" / "backups")
        print(f"Local backup: {summary.get('manifest')}")

    source_engine = make_engine(args.source)
    target_engine = make_engine(target_url)
    table = SourceDocument.__table__

    with source_engine.connect() as src_conn:
        rows = [dict(r) for r in src_conn.execute(select(table)).mappings().all()]

    print(f"Current local library rows: {len(rows)}")
    if args.dry_run:
        for d in rows:
            print(f"  sync {d['id'][:8]}… {d.get('title')}")
        return

    if not rows:
        print("No source_documents in local DB.")
        return

    upserted = 0
    with target_engine.begin() as tgt_conn:
        for data in rows:
            stmt = pg_insert(table).values(**data)
            update_cols = {
                c.name: stmt.excluded[c.name]
                for c in table.columns
                if c.name != "id"
            }
            stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
            tgt_conn.execute(stmt)
            upserted += 1

    with target_engine.connect() as tgt_conn:
        total = tgt_conn.execute(select(SourceDocument.id)).fetchall()
    print(f"Upserted {upserted} documents into Postgres (total now: {len(total)})")


if __name__ == "__main__":
    main()
