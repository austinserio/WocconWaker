"""Backfill teaching classification on lexicon entries."""
import logging
from sqlalchemy.orm import Session

from panel_api.db import CanonicalLexicon, PendingLexicon
from panel_api.services.lexicon_classifier import apply_lexicon_classification

log = logging.getLogger("lexicon_reclassify")


def _inherit_from_base(db: Session, row: CanonicalLexicon) -> None:
    """When a linked variant gloss does not classify cleanly, use the base entry's unit."""
    if row.teaching_unit != "other" or not row.base_entry_id:
        return
    base = db.get(CanonicalLexicon, row.base_entry_id)
    if not base or base.teaching_unit == "other":
        return
    row.teaching_unit = base.teaching_unit
    if base.lesson_band:
        row.lesson_band = base.lesson_band


def reclassify_all_lexicon(db: Session) -> dict:
    counts = {"canonical": 0, "pending": 0, "inherited": 0}
    for row in db.query(CanonicalLexicon).all():
        before = row.teaching_unit
        apply_lexicon_classification(row, row.woccon, row.english, row.pos, row.source)
        if row.teaching_unit == "other":
            _inherit_from_base(db, row)
            if row.teaching_unit != before and row.teaching_unit != "other":
                counts["inherited"] += 1
        counts["canonical"] += 1
    for row in db.query(PendingLexicon).all():
        apply_lexicon_classification(row, row.woccon, row.english, row.pos, None)
        counts["pending"] += 1
    db.commit()
    log.info("Reclassified lexicon: %s", counts)
    return counts
