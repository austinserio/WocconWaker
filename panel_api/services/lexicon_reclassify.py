"""Backfill teaching classification on lexicon entries."""
import logging
from sqlalchemy.orm import Session

from panel_api.db import CanonicalLexicon, PendingLexicon
from panel_api.services.lexicon_classifier import apply_lexicon_classification

log = logging.getLogger("lexicon_reclassify")


def reclassify_all_lexicon(db: Session) -> dict:
    counts = {"canonical": 0, "pending": 0}
    for row in db.query(CanonicalLexicon).all():
        apply_lexicon_classification(row, row.woccon, row.english, row.pos, row.source)
        counts["canonical"] += 1
    for row in db.query(PendingLexicon).all():
        apply_lexicon_classification(row, row.woccon, row.english, row.pos, None)
        counts["pending"] += 1
    db.commit()
    log.info("Reclassified lexicon: %s", counts)
    return counts
