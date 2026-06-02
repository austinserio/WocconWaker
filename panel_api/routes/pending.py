from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from panel_api.db import CanonicalLexicon, PendingLexicon, PendingRule, SourceDocument
from panel_api.deps import DbSession, RequireWorker
from panel_api.schemas import (
    BulkStatusRequest,
    LinkBaseRequest,
    PendingLexiconCreate,
    PendingLexiconOut,
    PendingLexiconPatch,
    PendingRuleCreate,
    PendingRuleOut,
    PendingRulePatch,
)
from panel_api.services.audit import write_audit
from panel_api.services.duplicates import find_lexicon_duplicate, find_rule_duplicate
from panel_api.services.vocab_match import apply_base_link_to_pending
from panel_api.lexicon_taxonomy import LESSON_BAND_IDS, TEACHING_UNIT_IDS, WORD_CLASS_IDS
from panel_api.services.lexicon_classifier import apply_lexicon_classification
from panel_api.services.rule_classifier import apply_classification_to_rule
from panel_api.services.serializers import pending_lexicon_out, pending_rule_out
from panel_api.taxonomy import CONSTRUCTION_IDS, DOMAIN_IDS, POS_IDS

router = APIRouter(prefix="/pending", tags=["pending"])

_LEXICON_CONTENT_FIELDS = frozenset(
    {"woccon", "english", "pos", "pronunciation", "source_page", "source_page_end", "source_excerpt"}
)
_RULE_CONTENT_FIELDS = frozenset(
    {"content", "category", "source_page", "source_page_end", "source_excerpt"}
)


def _validate_lexicon_taxonomy(data: dict) -> None:
    for k, ids in (
        ("teaching_unit", TEACHING_UNIT_IDS),
        ("word_class", WORD_CLASS_IDS),
        ("lesson_band", LESSON_BAND_IDS),
    ):
        v = data.get(k)
        if v is not None and v not in ids:
            raise HTTPException(status_code=400, detail=f"Invalid {k}: {v}")


def _validate_rule_taxonomy(data: dict) -> None:
    for k, ids in (
        ("grammar_domain", DOMAIN_IDS),
        ("pos_tag", POS_IDS),
        ("construction_type", CONSTRUCTION_IDS),
    ):
        v = data.get(k)
        if v is not None and v not in ids:
            raise HTTPException(status_code=400, detail=f"Invalid {k}: {v}")


def _maybe_mark_modified(row, data: dict, content_fields: frozenset) -> None:
    if row.status in ("approved", "rejected", "committed"):
        return
    if content_fields.intersection(data.keys()) and "status" not in data:
        row.status = "modified"


@router.get("/lexicon", response_model=List[PendingLexiconOut])
def list_pending_lexicon(
    db: DbSession,
    user: RequireWorker,
    status: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
    duplicate_only: bool = Query(False),
    unmatched_only: bool = Query(False),
):
    q = db.query(PendingLexicon)
    if status:
        if status == "pending":
            q = q.filter(PendingLexicon.status.in_(["pending", "modified"]))
        else:
            q = q.filter(PendingLexicon.status == status)
    if document_id:
        q = q.filter(PendingLexicon.source_document_id == document_id)
    if duplicate_only:
        q = q.filter(PendingLexicon.duplicate_of_id.isnot(None))
    if unmatched_only:
        q = q.filter(PendingLexicon.match_status == "unmatched")
    return [pending_lexicon_out(db, r) for r in q.order_by(PendingLexicon.created_at.desc()).all()]


@router.post("/lexicon", response_model=PendingLexiconOut, status_code=201)
def create_pending_lexicon(body: PendingLexiconCreate, db: DbSession, user: RequireWorker):
    data = body.model_dump()
    _validate_lexicon_taxonomy(data)
    if data.get("source_document_id") and not db.get(SourceDocument, data["source_document_id"]):
        raise HTTPException(status_code=400, detail="Invalid source_document_id")

    row = PendingLexicon(
        woccon=data["woccon"],
        english=data["english"],
        pos=data.get("pos") or "unknown",
        pronunciation=data.get("pronunciation"),
        source_document_id=data.get("source_document_id"),
        source_page=data.get("source_page"),
        source_page_end=data.get("source_page_end"),
        source_excerpt=data.get("source_excerpt"),
        reviewer_notes=data.get("reviewer_notes"),
        status="pending",
        provenance_status="manual",
    )
    if data.get("teaching_unit"):
        row.teaching_unit = data["teaching_unit"]
    if data.get("word_class"):
        row.word_class = data["word_class"]
    if data.get("lesson_band"):
        row.lesson_band = data["lesson_band"]
    if not all(data.get(k) for k in ("teaching_unit", "word_class", "lesson_band")):
        apply_lexicon_classification(row, row.woccon, row.english, row.pos, None)

    dup_id, dup_score, _ = find_lexicon_duplicate(db, row.woccon, row.english)
    row.duplicate_of_id = dup_id
    row.duplicate_score = dup_score
    apply_base_link_to_pending(row, db)

    db.add(row)
    db.flush()
    write_audit(
        db,
        entity_type="pending_lexicon",
        entity_id=row.id,
        action="create",
        user_id=user.id,
        payload={"woccon": row.woccon, "english": row.english},
    )
    db.commit()
    db.refresh(row)
    return pending_lexicon_out(db, row)


@router.patch("/lexicon/{row_id}", response_model=PendingLexiconOut)
def patch_pending_lexicon(row_id: str, body: PendingLexiconPatch, db: DbSession, user: RequireWorker):
    row = db.get(PendingLexicon, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    _validate_lexicon_taxonomy(data)
    for k, v in data.items():
        setattr(row, k, v)
    _maybe_mark_modified(row, data, _LEXICON_CONTENT_FIELDS)
    if "woccon" in data or "english" in data:
        dup_id, dup_score, _ = find_lexicon_duplicate(db, row.woccon, row.english)
        row.duplicate_of_id = dup_id
        row.duplicate_score = dup_score
        if row.match_status != "manual":
            apply_base_link_to_pending(row, db)
    if any(k in data for k in ("woccon", "english", "pos")) and not any(
        k in data for k in ("teaching_unit", "word_class", "lesson_band")
    ):
        apply_lexicon_classification(row, row.woccon, row.english, row.pos, None)
    if any(k in data for k in ("source_page", "source_page_end", "source_excerpt")):
        row.provenance_status = "manual"
    db.commit()
    db.refresh(row)
    return pending_lexicon_out(db, row)


@router.post("/lexicon/{row_id}/link-base", response_model=PendingLexiconOut)
def link_pending_to_base(row_id: str, body: LinkBaseRequest, db: DbSession, user: RequireWorker):
    row = db.get(PendingLexicon, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    base = db.get(CanonicalLexicon, body.base_entry_id)
    if not base or not base.is_base_entry:
        raise HTTPException(status_code=400, detail="Invalid base entry")
    row.base_entry_id = base.id
    row.base_match_score = 1.0
    row.base_match_method = "manual"
    row.match_status = "manual"
    db.commit()
    db.refresh(row)
    return pending_lexicon_out(db, row)


@router.post("/lexicon/{row_id}/promote-base", response_model=PendingLexiconOut)
def promote_pending_to_base(row_id: str, db: DbSession, user: RequireWorker):
    row = db.get(PendingLexicon, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    key = (row.woccon or "").strip().lower()
    existing = (
        db.query(CanonicalLexicon)
        .filter(CanonicalLexicon.is_base_entry.is_(True), CanonicalLexicon.woccon_normalized == key)
        .first()
    )
    if existing:
        row.base_entry_id = existing.id
        row.match_status = "matched"
    else:
        from panel_api.services.base_vocab import ensure_vocab_base_document

        doc = ensure_vocab_base_document(db)
        base_row = CanonicalLexicon(
            woccon=row.woccon,
            english=row.english,
            pos=row.pos,
            pronunciation=row.pronunciation,
            source="vocab_base",
            source_url=row.source_url,
            source_document_id=doc.id if doc else row.source_document_id,
            woccon_normalized=key,
            is_base_entry=True,
            sort_order=(
                db.query(CanonicalLexicon).filter(CanonicalLexicon.is_base_entry.is_(True)).count()
            ),
        )
        apply_lexicon_classification(base_row, row.woccon, row.english, row.pos, "vocab_base")
        db.add(base_row)
        db.flush()
        row.base_entry_id = base_row.id
        row.match_status = "manual"
    row.base_match_method = "manual"
    row.base_match_score = 1.0
    row.status = "approved"
    db.commit()
    db.refresh(row)
    return pending_lexicon_out(db, row)


@router.post("/lexicon/bulk")
def bulk_lexicon(body: BulkStatusRequest, db: DbSession, user: RequireWorker):
    updated = 0
    for row in db.query(PendingLexicon).filter(PendingLexicon.id.in_(body.ids)).all():
        row.status = body.status
        updated += 1
    db.commit()
    return {"updated": updated}


@router.get("/rules", response_model=List[PendingRuleOut])
def list_pending_rules(
    db: DbSession,
    user: RequireWorker,
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
    duplicate_only: bool = Query(False),
):
    q = db.query(PendingRule)
    if status:
        if status == "pending":
            q = q.filter(PendingRule.status.in_(["pending", "modified"]))
        else:
            q = q.filter(PendingRule.status == status)
    if category:
        q = q.filter(PendingRule.category == category)
    if document_id:
        q = q.filter(PendingRule.source_document_id == document_id)
    if duplicate_only:
        q = q.filter(PendingRule.duplicate_of_id.isnot(None))
    return [pending_rule_out(db, r) for r in q.order_by(PendingRule.created_at.desc()).all()]


@router.post("/rules", response_model=PendingRuleOut, status_code=201)
def create_pending_rule(body: PendingRuleCreate, db: DbSession, user: RequireWorker):
    data = body.model_dump()
    _validate_rule_taxonomy(data)
    if data.get("source_document_id") and not db.get(SourceDocument, data["source_document_id"]):
        raise HTTPException(status_code=400, detail="Invalid source_document_id")

    row = PendingRule(
        category=data["category"],
        content=data["content"],
        source_document_id=data.get("source_document_id"),
        grammar_domain=data.get("grammar_domain"),
        pos_tag=data.get("pos_tag"),
        construction_type=data.get("construction_type"),
        source_page=data.get("source_page"),
        source_page_end=data.get("source_page_end"),
        source_excerpt=data.get("source_excerpt"),
        reviewer_notes=data.get("reviewer_notes"),
        status="pending",
        provenance_status="manual",
    )
    if row.category == "grammar" and not any(
        data.get(k) for k in ("grammar_domain", "pos_tag", "construction_type")
    ):
        apply_classification_to_rule(row, row.category, row.content)

    dup_id, dup_score, _ = find_rule_duplicate(db, row.category, row.content)
    row.duplicate_of_id = dup_id
    row.duplicate_score = dup_score

    db.add(row)
    db.flush()
    write_audit(
        db,
        entity_type="pending_rule",
        entity_id=row.id,
        action="create",
        user_id=user.id,
        payload={"category": row.category, "content": row.content[:200]},
    )
    db.commit()
    db.refresh(row)
    return pending_rule_out(db, row)


@router.patch("/rules/{row_id}", response_model=PendingRuleOut)
def patch_pending_rule(row_id: str, body: PendingRulePatch, db: DbSession, user: RequireWorker):
    row = db.get(PendingRule, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    _validate_rule_taxonomy(data)
    for k, v in data.items():
        setattr(row, k, v)
    _maybe_mark_modified(row, data, _RULE_CONTENT_FIELDS)
    if "content" in data or "category" in data:
        dup_id, dup_score, _ = find_rule_duplicate(db, row.category, row.content)
        row.duplicate_of_id = dup_id
        row.duplicate_score = dup_score
    if row.category == "grammar":
        if any(k in data for k in ("grammar_domain", "pos_tag", "construction_type", "content", "category")):
            if not any(k in data for k in ("grammar_domain", "pos_tag", "construction_type")):
                apply_classification_to_rule(row, row.category, row.content)
    if any(k in data for k in ("source_page", "source_page_end", "source_excerpt")):
        row.provenance_status = "manual"
    db.commit()
    db.refresh(row)
    return pending_rule_out(db, row)


@router.post("/rules/bulk")
def bulk_rules(body: BulkStatusRequest, db: DbSession, user: RequireWorker):
    updated = 0
    for row in db.query(PendingRule).filter(PendingRule.id.in_(body.ids)).all():
        row.status = body.status
        updated += 1
    db.commit()
    return {"updated": updated}
