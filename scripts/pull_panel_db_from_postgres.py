#!/usr/bin/env python3
"""Refresh local SQLite from production PostgreSQL."""
from __future__ import annotations

import argparse
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


def main() -> None:
  parser = argparse.ArgumentParser(description="Copy production Postgres → local SQLite")
  parser.add_argument("--target", default="sqlite:///./data/woccon.db", help="Local SQLite URL")
  parser.add_argument("--dry-run", action="store_true")
  args = parser.parse_args()

  source_url = normalize_url(os.environ.get("POSTGRES_DATABASE_URL", ""))
  if not source_url.startswith("postgresql"):
    print("Set POSTGRES_DATABASE_URL in .env", file=sys.stderr)
    sys.exit(1)
  target_url = args.target

  print(f"Source: {source_url.split('@')[-1]}")
  print(f"Target: {target_url}")

  if args.dry_run:
    print("[dry-run] Would backup local SQLite and copy from Postgres.")
    return

  backup_assets(target_url, ROOT / "data" / "backups")

  target_path = target_url.replace("sqlite:///", "", 1)
  if target_path and not target_path.startswith(":"):
    p = Path(target_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
      ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
      shutil.copy2(p, p.parent / "backups" / f"woccon_pre_pull_{ts}.db")

  run_alembic_upgrade(target_url)
  prepare_target_schema(target_url)

  source_engine = make_engine(source_url)
  target_engine = make_engine(target_url)
  counts = copy_all(source_engine, target_engine, replace=True)

  diffs = compare_counts(source_engine, target_engine)
  if diffs:
    print("Row count mismatch:", file=sys.stderr)
    for name, s, t in diffs:
      print(f"  {name}: postgres={s} sqlite={t}", file=sys.stderr)
    sys.exit(1)

  print("Local SQLite refreshed from Postgres:")
  for name, n in sorted(counts.items()):
    print(f"  {name}: {n}")


if __name__ == "__main__":
  main()
