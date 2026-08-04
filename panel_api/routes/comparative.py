"""Comparative data API: cognate sets and correspondence rules."""
from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from panel_api.db import CognateRuleExample, CognateSet, CorrespondenceRule
from panel_api.deps import DbSession
from panel_api.schemas import (
    CognateRuleExampleOut,
    CognateSetListResponse,
    CognateSetOut,
    CorrespondenceRuleListResponse,
    CorrespondenceRuleOut,
)

router = APIRouter(tags=["comparative"])


def _cognate_out(row: CognateSet, examples: Optional[List[CognateRuleExample]] = None) -> CognateSetOut:
    ex_out: List[CognateRuleExampleOut] = []
    for ex in examples or []:
        alignment = None
        if ex.alignment_json:
            try:
                alignment = json.loads(ex.alignment_json)
            except json.JSONDecodeError:
                alignment = None
        ex_out.append(
            CognateRuleExampleOut(
                id=ex.id,
                correspondence_rule_id=ex.correspondence_rule_id,
                alignment=alignment,
            )
        )
    return CognateSetOut(
        id=row.id,
        gloss=row.gloss,
        lawson_form=row.lawson_form,
        lawson_form_corrected=row.lawson_form_corrected,
        lawson_gloss=row.lawson_gloss,
        woccon_reconstituted=row.woccon_reconstituted,
        catawba_form=row.catawba_form,
        catawba_dialect=row.catawba_dialect,
        proto_siouan=row.proto_siouan,
        evidence_tier=row.evidence_tier,
        rudes_appendix=row.rudes_appendix,
        rudes_item=row.rudes_item,
        citation_short=row.citation_short,
        source_path=row.source_path,
        source_url=row.source_url,
        notes=row.notes,
        canonical_lexicon_id=row.canonical_lexicon_id,
        rule_examples=ex_out,
    )


def _rule_out(row: CorrespondenceRule, example_ids: Optional[List[str]] = None) -> CorrespondenceRuleOut:
    return CorrespondenceRuleOut(
        id=row.id,
        rule_kind=row.rule_kind,
        lhs=row.lhs,
        rhs=row.rhs,
        environment=row.environment,
        direction=row.direction,
        correspondence_status=row.correspondence_status,
        grammar_lineage=row.grammar_lineage,
        source=row.source,
        notes=row.notes,
        provenance_text=row.provenance_text,
        example_cognate_ids=example_ids or [],
    )


@router.get("/cognate-sets", response_model=CognateSetListResponse)
def list_cognate_sets(
    db: DbSession,
    gloss: Optional[str] = Query(None),
    evidence_tier: Optional[str] = Query(None),
    rudes_appendix: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    query = db.query(CognateSet)
    if gloss:
        query = query.filter(CognateSet.gloss.ilike(f"%{gloss}%"))
    if evidence_tier:
        query = query.filter(CognateSet.evidence_tier == evidence_tier)
    if rudes_appendix is not None:
        query = query.filter(CognateSet.rudes_appendix == rudes_appendix)
    total = query.count()
    rows = (
        query.order_by(CognateSet.rudes_appendix, CognateSet.rudes_item)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return CognateSetListResponse(
        items=[_cognate_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/cognate-sets/{cognate_id}", response_model=CognateSetOut)
def get_cognate_set(cognate_id: str, db: DbSession):
    row = db.get(CognateSet, cognate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Cognate set not found")
    examples = (
        db.query(CognateRuleExample)
        .filter(CognateRuleExample.cognate_set_id == cognate_id)
        .all()
    )
    return _cognate_out(row, examples)


@router.get("/correspondence-rules", response_model=CorrespondenceRuleListResponse)
def list_correspondence_rules(
    db: DbSession,
    rule_kind: Optional[str] = Query(None),
    correspondence_status: Optional[str] = Query(None),
    environment: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    query = db.query(CorrespondenceRule)
    if rule_kind:
        query = query.filter(CorrespondenceRule.rule_kind == rule_kind)
    if correspondence_status:
        query = query.filter(CorrespondenceRule.correspondence_status == correspondence_status)
    if environment:
        query = query.filter(CorrespondenceRule.environment == environment)
    total = query.count()
    rows = query.order_by(CorrespondenceRule.rule_kind, CorrespondenceRule.id).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return CorrespondenceRuleListResponse(
        items=[_rule_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/correspondence-rules/{rule_id}", response_model=CorrespondenceRuleOut)
def get_correspondence_rule(rule_id: str, db: DbSession):
    row = db.get(CorrespondenceRule, rule_id)
    if not row:
        raise HTTPException(status_code=404, detail="Correspondence rule not found")
    example_ids = [
        ex.cognate_set_id
        for ex in db.query(CognateRuleExample)
        .filter(CognateRuleExample.correspondence_rule_id == rule_id)
        .all()
    ]
    return _rule_out(row, example_ids)
