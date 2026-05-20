"""Backfill classification on existing grammar rules."""
import logging
from sqlalchemy.orm import Session

from panel_api.db import CanonicalRule, PendingRule
from panel_api.services.rule_classifier import apply_classification_to_rule

log = logging.getLogger("reclassify")


def reclassify_all_grammar(db: Session) -> dict:
    counts = {"canonical": 0, "pending": 0}
    for row in db.query(CanonicalRule).filter(CanonicalRule.category == "grammar").all():
        apply_classification_to_rule(row, "grammar", row.content)
        counts["canonical"] += 1
    for row in db.query(PendingRule).filter(PendingRule.category == "grammar").all():
        apply_classification_to_rule(row, "grammar", row.content)
        counts["pending"] += 1
    db.commit()
    log.info("Reclassified grammar rules: %s", counts)
    return counts
