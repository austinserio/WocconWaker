#!/usr/bin/env python3
"""Import definitive base vocabulary from Google Doc into canonical_lexicon."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panel_api.db import get_session_factory, init_db
from panel_api.services.base_vocab import import_base_vocab


def main() -> int:
    init_db()
    db = get_session_factory()()
    try:
        result = import_base_vocab(db)
        print(result)
        return 0 if result.get("total", 0) or result.get("updated") else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
