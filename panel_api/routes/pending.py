from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from panel_api.db import PendingLexicon, PendingRule
from panel_api.deps import DbSession, RequireReviewer
from panel_api.schemas import (
    BulkStatusRequest,
    PendingLexiconOut,
    PendingLexiconPatch,
    PendingRuleOut,
    PendingRulePatch,
)
from panel_api.services.duplicates import find_lexicon_duplicate, find_rule_duplicate
from panel_api.lexicon_taxonomy import LESSON_BAND_IDS, TEACHING_UNIT_IDS, WORD_CLASS_IDS
from panel_api.services.lexicon_classifier import apply_lexicon_classification
from panel_api.services.rule_classifier import apply_classification_to_rule
from panel_api.taxonomy import CONSTRUCTION_IDS, DOMAIN_IDS, POS_IDS

router = APIRouter(prefix="/pending", tags=["pending"])


@router.get("/lexicon", response_model=List[PendingLexiconOut])
def list_pending_lexicon(
    db: DbSession,
    user: RequireReviewer,
    status: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
    duplicate_only: bool = Query(False),
):
    q = db.query(PendingLexicon)
    if status:
        q = q.filter(PendingLexicon.status == status)
    if document_id:
        q = q.filter(PendingLexicon.source_document_id == document_id)
    if duplicate_only:
        q = q.filter(PendingLexicon.duplicate_of_id.isnot(None))
    return [PendingLexiconOut.model_validate(r) for r in q.order_by(PendingLexicon.created_at.desc()).all()]


@router.patch("/lexicon/{row_id}", response_model=PendingLexiconOut)
def patch_pending_lexicon(row_id: str, body: PendingLexiconPatch, db: DbSession, user: RequireReviewer):
    row = db.get(PendingLexicon, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k in ("teaching_unit", "word_class", "lesson_band") and v is not None:
            if k == "teaching_unit" and v not in TEACHING_UNIT_IDS:
                raise HTTPException(status_code=400, detail=f"Invalid {k}")
            if k == "word_class" and v not in WORD_CLASS_IDS:
                raise HTTPException(status_code=400, detail=f"Invalid {k}")
            if k == "lesson_band" and v not in LESSON_BAND_IDS:
                raise HTTPException(status_code=400, detail=f"Invalid {k}")
        setattr(row, k, v)
    if "woccon" in data or "english" in data:
        dup_id, dup_score, _ = find_lexicon_duplicate(db, row.woccon, row.english)
        row.duplicate_of_id = dup_id
        row.duplicate_score = dup_score
    if any(k in data for k in ("woccon", "english", "pos")) and not any(
        k in data for k in ("teaching_unit", "word_class", "lesson_band")
    ):
        apply_lexicon_classification(row, row.woccon, row.english, row.pos, None)
    db.commit()
    db.refresh(row)
    return PendingLexiconOut.model_validate(row)


@router.post("/lexicon/bulk")
def bulk_lexicon(body: BulkStatusRequest, db: DbSession, user: RequireReviewer):
    updated = 0
    for row in db.query(PendingLexicon).filter(PendingLexicon.id.in_(body.ids)).all():
        row.status = body.status
        updated += 1
    db.commit()
    return {"updated": updated}


@router.get("/rules", response_model=List[PendingRuleOut])
def list_pending_rules(
    db: DbSession,
    user: RequireReviewer,
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
    duplicate_only: bool = Query(False),
):
    q = db.query(PendingRule)
    if status:
        q = q.filter(PendingRule.status == status)
    if category:
        q = q.filter(PendingRule.category == category)
    if document_id:
        q = q.filter(PendingRule.source_document_id == document_id)
    if duplicate_only:
        q = q.filter(PendingRule.duplicate_of_id.isnot(None))
    return [PendingRuleOut.model_validate(r) for r in q.order_by(PendingRule.created_at.desc()).all()]


@router.patch("/rules/{row_id}", response_model=PendingRuleOut)
def patch_pending_rule(row_id: str, body: PendingRulePatch, db: DbSession, user: RequireReviewer):
    row = db.get(PendingRule, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    if "content" in data or "category" in data:
        dup_id, dup_score, _ = find_rule_duplicate(db, row.category, row.content)
        row.duplicate_of_id = dup_id
        row.duplicate_score = dup_score
    if row.category == "grammar":
        if any(k in data for k in ("grammar_domain", "pos_tag", "construction_type", "content", "category")):
            for k in ("grammar_domain", "pos_tag", "construction_type"):
                if k in data and data[k] is not None:
                    if k == "grammar_domain" and data[k] not in DOMAIN_IDS:
                        raise HTTPException(status_code=400, detail=f"Invalid {k}")
                    if k == "pos_tag" and data[k] not in POS_IDS:
                        raise HTTPException(status_code=400, detail=f"Invalid {k}")
                    if k == "construction_type" and data[k] not in CONSTRUCTION_IDS:
                        raise HTTPException(status_code=400, detail=f"Invalid {k}")
            if not any(k in data for k in ("grammar_domain", "pos_tag", "construction_type")):
                apply_classification_to_rule(row, row.category, row.content)
    db.commit()
    db.refresh(row)
    return PendingRuleOut.model_validate(row)


@router.post("/rules/bulk")
def bulk_rules(body: BulkStatusRequest, db: DbSession, user: RequireReviewer):
    updated = 0
    for row in db.query(PendingRule).filter(PendingRule.id.in_(body.ids)).all():
        row.status = body.status
        updated += 1
    db.commit()
    return {"updated": updated}
