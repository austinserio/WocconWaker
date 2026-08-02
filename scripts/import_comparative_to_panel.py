#!/usr/bin/env python3
"""Import cognate seed, alignments, and correspondence registry into panel DB."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panel_api.db import get_session_factory, init_db  # noqa: E402
from panel_api.services.comparative_import import import_comparative_all  # noqa: E402
from woccon_reconstruction.comparative_utils import (  # noqa: E402
    DEFAULT_ALIGNMENTS,
    DEFAULT_COGNATES,
    DEFAULT_REGISTRY,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cognates", type=Path, default=DEFAULT_COGNATES)
    parser.add_argument("--alignments", type=Path, default=DEFAULT_ALIGNMENTS)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--no-link-lexicon", action="store_true")
    args = parser.parse_args()

    init_db()
    db = get_session_factory()()
    try:
        result = import_comparative_all(
            db,
            cognates_path=args.cognates,
            alignments_path=args.alignments,
            registry_path=args.registry,
            link_lexicon=not args.no_link_lexicon,
        )
        db.commit()
        print(result)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
