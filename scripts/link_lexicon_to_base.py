#!/usr/bin/env python3
"""Backfill base_entry_id on existing canonical lexicon rows."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panel_api.db import get_session_factory, init_db
from panel_api.services.base_vocab import link_all_canonical_to_base


def main() -> int:
    init_db()
    db = get_session_factory()()
    try:
        result = link_all_canonical_to_base(db)
        print(result)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
