#!/usr/bin/env bash
# Refresh local SQLite from production PostgreSQL.
# Usage: ./scripts/pull_panel_db_from_postgres.sh [--dry-run]
#
# Requires POSTGRES_DATABASE_URL in .env. Stop local app before running.
# If connection fails, refresh firewall: ./scripts/setup-azure-postgres.sh --add-my-ip

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

if [[ -z "${POSTGRES_DATABASE_URL:-}" ]]; then
  echo "Set POSTGRES_DATABASE_URL in .env (from setup-azure-postgres.sh)" >&2
  exit 1
fi

PY="${ROOT}/.venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

ARGS=()
$DRY_RUN && ARGS+=(--dry-run)

# Optional: archive pg_dump when client tools are installed
if command -v pg_dump >/dev/null 2>&1 && ! $DRY_RUN; then
  BACKUP_DIR="${ROOT}/data/backups"
  mkdir -p "$BACKUP_DIR"
  TS="$(date -u +%Y%m%d_%H%M%S)"
  DUMP="${BACKUP_DIR}/prod_woccon_${TS}.dump"
  echo "Archiving Postgres with pg_dump → ${DUMP}"
  # Parse URL for pg_dump (postgresql+psycopg://user:pass@host:5432/db?sslmode=require)
  PARSED="$("$PY" - <<'PY'
import os, re, sys
from urllib.parse import unquote, urlparse
url = os.environ.get("POSTGRES_DATABASE_URL", "")
url = re.sub(r"^postgresql\+psycopg://", "postgresql://", url)
p = urlparse(url)
print(p.hostname or "")
print(p.port or 5432)
print((p.path or "/woccon").lstrip("/"))
print(unquote(p.username or ""))
print(unquote(p.password or ""))
PY
)"
  read -r PG_HOST PG_PORT PG_DB PG_USER PG_PASS <<< "$PARSED"
  PGPASSWORD="$PG_PASS" pg_dump \
    -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
    --format=custom --file="$DUMP" \
    --no-owner --no-acl
  echo "pg_dump saved."
fi

exec "$PY" "${ROOT}/scripts/pull_panel_db_from_postgres.py" "${ARGS[@]}"
