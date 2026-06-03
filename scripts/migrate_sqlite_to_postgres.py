#!/usr/bin/env python3
"""Migrate panel data from local SQLite to Azure PostgreSQL."""
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
from panel_db_transfer import (  # noqa: E402
    compare_counts,
    copy_all,
    make_engine,
    normalize_url,
    prepare_target_schema,
    run_alembic_upgrade,
)
from reset_panel_db import backup_assets  # noqa: E402


def _resolve_urls() -> tuple[str, str]:
  # Always migrate from current local DB unless explicitly overridden.
  source = os.environ.get("SQLITE_SOURCE_URL", "sqlite:///./data/woccon.db")
  target = os.environ.get("POSTGRES_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
  target = normalize_url(target)
  if not target.startswith("postgresql"):
    print(
      "Set POSTGRES_DATABASE_URL in .env (postgresql+psycopg://...).\n"
      "Run ./scripts/setup-azure-postgres.sh first.",
      file=sys.stderr,
    )
    sys.exit(1)
  return source, target


def main() -> None:
  parser = argparse.ArgumentParser(description="Copy panel SQLite → PostgreSQL")
  parser.add_argument("--skip-backup", action="store_true")
  parser.add_argument("--skip-alembic", action="store_true")
  parser.add_argument(
    "--no-replace",
    action="store_true",
    help="Do not truncate Postgres before copy (default: replace)",
  )
  parser.add_argument("--dry-run", action="store_true")
  args = parser.parse_args()

  source_url, target_url = _resolve_urls()
  print(f"Source: {source_url}")
  print(f"Target: {target_url.split('@')[-1] if '@' in target_url else target_url}")

  if args.dry_run:
    print("[dry-run] Would backup, alembic upgrade, and copy tables.")
    return

  if not args.skip_backup:
    summary = backup_assets(source_url, ROOT / "data" / "backups")
    print(f"Backup: {summary.get('manifest', 'ok')}")

  if not args.skip_alembic:
    print("Running alembic upgrade head on Postgres...")
    run_alembic_upgrade(target_url)
    print("Applying schema patches (init_db)...")
    prepare_target_schema(target_url)

  source_engine = make_engine(source_url)
  target_engine = make_engine(target_url)

  print("Copying tables...")
  counts = copy_all(source_engine, target_engine, replace=not args.no_replace)
  for name, n in sorted(counts.items()):
    print(f"  {name}: {n} rows")

  diffs = compare_counts(source_engine, target_engine)
  if diffs:
    print("\nRow count mismatch:", file=sys.stderr)
    for name, s, t in diffs:
      print(f"  {name}: source={s} target={t}", file=sys.stderr)
    sys.exit(1)

  lex = counts.get("canonical_lexicon", 0)
  rules = counts.get("canonical_rules", 0)
  users = counts.get("users", 0)
  print(f"\nOK — canonical_lexicon={lex}, canonical_rules={rules}, users={users}")
  print("Next: ./scripts/sync-azure-container-env.sh")


if __name__ == "__main__":
  main()
