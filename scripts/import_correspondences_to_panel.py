#!/usr/bin/env python3
"""Import correspondence registry into panel DB."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panel_api.db import get_session_factory, init_db  # noqa: E402
from panel_api.services.comparative_import import import_correspondences  # noqa: E402
from woccon_reconstruction.comparative_utils import DEFAULT_REGISTRY  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()

    init_db()
    db = get_session_factory()()
    try:
        result = import_correspondences(db, registry_path=args.registry)
        db.commit()
        print(result)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
