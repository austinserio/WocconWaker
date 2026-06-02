#!/usr/bin/env python3
"""Manually link orphan canonical lexicon rows to base entries."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panel_api.db import CanonicalLexicon, get_session_factory, init_db
from panel_api.services.vocab_match import manual_link_canonical_to_base

# (variant woccon, base woccon) — English gloss verified against base entry.
MANUAL_LINKS = [
    ("Intorn", "intom"),
    ("wátupi", "wattape"),
    ("Hooha", "Hooheh"),
    ("lute teraugh", "itte teraugh"),
    ("ku-wate", "Quaute"),
    ("yuppa mei", "yuppa me"),
]


def main() -> int:
    init_db()
    db = get_session_factory()()
    linked = 0
    skipped = 0
    try:
        for variant_w, base_w in MANUAL_LINKS:
            row = (
                db.query(CanonicalLexicon)
                .filter(
                    CanonicalLexicon.woccon == variant_w,
                    CanonicalLexicon.is_base_entry.is_(False),
                    CanonicalLexicon.base_entry_id.is_(None),
                )
                .first()
            )
            base = (
                db.query(CanonicalLexicon)
                .filter(CanonicalLexicon.woccon == base_w, CanonicalLexicon.is_base_entry.is_(True))
                .first()
            )
            if not row:
                print(f"skip (no orphan): {variant_w!r}")
                skipped += 1
                continue
            if not base:
                print(f"skip (no base): {base_w!r} for {variant_w!r}")
                skipped += 1
                continue
            manual_link_canonical_to_base(db, row, base)
            print(f"linked {variant_w!r} | {row.english!r} -> {base.woccon!r} | {base.english!r}")
            linked += 1
        db.commit()
        remaining = (
            db.query(CanonicalLexicon)
            .filter(
                CanonicalLexicon.is_base_entry.is_(False),
                CanonicalLexicon.base_entry_id.is_(None),
            )
            .count()
        )
        print({"linked": linked, "skipped": skipped, "remaining_orphans": remaining})
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
