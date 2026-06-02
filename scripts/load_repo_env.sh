#!/usr/bin/env bash
# Load gitignored .env from the repository root. Source this from project scripts.
#
# From a script in repo root:
#   ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   # shellcheck source=scripts/load_repo_env.sh
#   source "$ROOT/scripts/load_repo_env.sh" "$ROOT"
#
# From scripts/something.sh:
#   ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
#   source "$ROOT/scripts/load_repo_env.sh" "$ROOT"

_woccon_repo_root="${1:-}"
if [ -z "$_woccon_repo_root" ] || [ ! -d "$_woccon_repo_root" ]; then
  echo "load_repo_env.sh: pass repository root directory as first argument" >&2
  return 1 2>/dev/null || exit 1
fi
if [ -f "$_woccon_repo_root/.env" ]; then
  set -a
  # Parse .env safely (unquoted spaces in values break plain `source`, e.g. Gmail app passwords).
  if command -v python3 >/dev/null 2>&1; then
    # shellcheck disable=SC2046
    eval "$(
      WOCCON_ENV_FILE="$_woccon_repo_root/.env" python3 - <<'PY'
import os, shlex
from pathlib import Path

path = Path(os.environ["WOCCON_ENV_FILE"])
for raw in path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        continue
    key, _, value = line.partition("=")
    key = key.strip()
    if not key or not key.replace("_", "").isalnum():
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    print(f"export {key}={shlex.quote(value)}")
PY
    )"
  else
    # shellcheck disable=SC1091
    source "$_woccon_repo_root/.env"
  fi
  set +a
fi
unset _woccon_repo_root
