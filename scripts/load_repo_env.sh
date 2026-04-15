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
  # shellcheck disable=SC1091
  source "$_woccon_repo_root/.env"
  set +a
fi
unset _woccon_repo_root
