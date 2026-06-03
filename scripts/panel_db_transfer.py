"""Copy panel schema rows between SQLite and PostgreSQL engines."""
from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine

from panel_api.db import Base


def normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args)


def table_names(engine: Engine) -> list[str]:
    return sorted(inspect(engine).get_table_names())


def count_rows(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()


def truncate_all(engine: Engine) -> None:
    tables = [t.name for t in Base.metadata.sorted_tables]
    if not tables:
        return
    quoted = ", ".join(f'"{n}"' for n in reversed(tables))
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
        else:
            for name in reversed(tables):
                conn.execute(text(f'DELETE FROM "{name}"'))


def copy_table(source: Engine, target: Engine, table_name: str, batch_size: int = 500) -> int:
    table = Base.metadata.tables[table_name]
    total = 0
    with source.connect() as src_conn, target.begin() as tgt_conn:
        result = src_conn.execute(select(table))
        keys = list(result.keys())
        while True:
            rows = result.fetchmany(batch_size)
            if not rows:
                break
            payload = [dict(zip(keys, row)) for row in rows]
            tgt_conn.execute(table.insert(), payload)
            total += len(payload)
    return total


def copy_all(source: Engine, target: Engine, *, replace: bool = False) -> dict[str, int]:
    if replace:
        truncate_all(target)
    counts: dict[str, int] = {}
    for table in Base.metadata.sorted_tables:
        name = table.name
        if name not in table_names(source):
            continue
        counts[name] = copy_table(source, target, name)
    return counts


def compare_counts(source: Engine, target: Engine) -> list[tuple[str, int, int]]:
  diffs: list[tuple[str, int, int]] = []
  for table in Base.metadata.sorted_tables:
    name = table.name
    if name not in table_names(source) or name not in table_names(target):
      continue
    s = count_rows(source, name)
    t = count_rows(target, name)
    if s != t:
      diffs.append((name, s, t))
  return diffs


def prepare_target_schema(database_url: str) -> None:
    """Apply init_db patches (columns beyond alembic) on the target database."""
    import panel_api.db as db_module
    from panel_api.config import get_settings
    from panel_api.db import init_db

    url = normalize_url(database_url)
    prev_db = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    db_module._engine = None
    db_module._SessionLocal = None
    init_db()
    if prev_db is not None:
        os.environ["DATABASE_URL"] = prev_db
    else:
        os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
    db_module._engine = None
    db_module._SessionLocal = None


def run_alembic_upgrade(database_url: str) -> None:
  import subprocess
  import sys

  env = os.environ.copy()
  env["DATABASE_URL"] = normalize_url(database_url)
  subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    env=env,
    check=True,
  )
