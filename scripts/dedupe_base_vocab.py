#!/usr/bin/env python3
"""Merge duplicate base vocabulary rows (same English + similar Woccon spelling)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panel_api.db import get_session_factory, init_db
from panel_api.services.base_vocab import dedupe_base_vocabulary


def main() -> int:
    init_db()
    db = get_session_factory()()
    try:
        result = dedupe_base_vocabulary(db)
        print(result)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
