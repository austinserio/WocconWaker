import json
from collections import defaultdict
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import or_

from panel_api.config import get_settings
from panel_api.db import CanonicalRule
from panel_api.deps import DbSession, RequireAdmin, RequireWorker
from panel_api.schemas import CanonicalRuleOut, CanonicalRulePatch, RuleGroupOut, RuleReorderRequest
from panel_api.services.audit import write_audit
from panel_api.services.duplicates import normalize_text
from panel_api.services.reclassify import reclassify_all_grammar
from panel_api.services.serializers import canonical_rule_out
from panel_api.services.rule_classifier import apply_classification_to_rule
from panel_api.taxonomy import (
    CONSTRUCTION_IDS,
    DOMAIN_IDS,
    POS_IDS,
    GRAMMAR_DOMAINS,
    label_for,
    taxonomy_payload,
)

router = APIRouter(prefix="/rules", tags=["rules"])


def _rule_query(
    db,
    *,
    category: Optional[str],
    grammar_domain: Optional[str],
    pos_tag: Optional[str],
    construction_type: Optional[str],
    q: Optional[str],
):
    query = db.query(CanonicalRule)
    if category:
        query = query.filter(CanonicalRule.category == category)
    if grammar_domain:
        query = query.filter(CanonicalRule.grammar_domain == grammar_domain)
    if pos_tag:
        query = query.filter(CanonicalRule.pos_tag == pos_tag)
    if construction_type:
        query = query.filter(CanonicalRule.construction_type == construction_type)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                CanonicalRule.content.ilike(like),
                CanonicalRule.content_normalized.ilike(like),
            )
        )
    return query.order_by(
        CanonicalRule.grammar_domain.asc().nulls_last(),
        CanonicalRule.sort_order,
    )


@router.get("/taxonomy")
def get_taxonomy():
    return taxonomy_payload()


@router.get("/stats")
def rule_stats(db: DbSession, category: str = Query("grammar")):
    rows = db.query(CanonicalRule).filter(CanonicalRule.category == category).all()
    by_domain: dict = defaultdict(int)
    by_pos: dict = defaultdict(int)
    by_construction: dict = defaultdict(int)
    for r in rows:
        by_domain[r.grammar_domain or "other"] += 1
        by_pos[r.pos_tag or "na"] += 1
        by_construction[r.construction_type or "na"] += 1
    return {
        "total": len(rows),
        "by_domain": dict(by_domain),
        "by_pos": dict(by_pos),
        "by_construction": dict(by_construction),
    }


@router.get("/grouped", response_model=List[RuleGroupOut])
def list_rules_grouped(
    db: DbSession,
    category: str = Query("grammar"),
    pos_tag: Optional[str] = Query(None),
    construction_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
):
    rows = _rule_query(
        db,
        category=category,
        grammar_domain=None,
        pos_tag=pos_tag,
        construction_type=construction_type,
        q=q,
    ).all()
    groups: dict = defaultdict(list)
    for r in rows:
        key = r.grammar_domain or "other"
        groups[key].append(canonical_rule_out(db, r))
    domain_order = [d["id"] for d in GRAMMAR_DOMAINS]
    result = []
    for domain_id in domain_order:
        if domain_id in groups:
            result.append(
                RuleGroupOut(
                    grammar_domain=domain_id,
                    label=label_for(GRAMMAR_DOMAINS, domain_id),
                    count=len(groups[domain_id]),
                    rules=groups[domain_id],
                )
            )
    for domain_id, rules in groups.items():
        if domain_id not in domain_order:
            result.append(
                RuleGroupOut(
                    grammar_domain=domain_id,
                    label=label_for(GRAMMAR_DOMAINS, domain_id),
                    count=len(rules),
                    rules=rules,
                )
            )
    return result


@router.get("", response_model=List[CanonicalRuleOut])
def list_rules(
    db: DbSession,
    category: Optional[str] = Query(None),
    grammar_domain: Optional[str] = Query(None),
    pos_tag: Optional[str] = Query(None),
    construction_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
):
    rows = _rule_query(
        db,
        category=category,
        grammar_domain=grammar_domain,
        pos_tag=pos_tag,
        construction_type=construction_type,
        q=q,
    ).all()
    return [canonical_rule_out(db, r) for r in rows]


@router.get("/legacy")
def legacy_rules():
    settings = get_settings()
    path = Path(settings.rules_legacy_path)
    if not path.is_file():
        path = Path(settings.rules_unified_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Rules file not found")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {
        "phonology": data.get("phonology"),
        "morphology": data.get("morphology"),
        "syntax": data.get("syntax"),
    }


@router.post("/reclassify")
def reclassify_rules(db: DbSession, admin: RequireAdmin):
    return reclassify_all_grammar(db)


@router.patch("/reorder")
def reorder_rules(body: RuleReorderRequest, db: DbSession, user: RequireWorker):
    if body.category not in ("grammar", "pronunciation", "cultural"):
        raise HTTPException(status_code=400, detail="Invalid category")

    if body.grammar_domain and body.category == "grammar":
        all_in_cat = (
            db.query(CanonicalRule)
            .filter(CanonicalRule.category == body.category)
            .order_by(CanonicalRule.sort_order)
            .all()
        )
        domain_rules = [r for r in all_in_cat if (r.grammar_domain or "other") == body.grammar_domain]
        other_rules = [r for r in all_in_cat if (r.grammar_domain or "other") != body.grammar_domain]
        id_to_rule = {r.id: r for r in domain_rules}
        reordered = [id_to_rule[rid] for rid in body.ordered_ids if rid in id_to_rule]
        merged = []
        di = 0
        for r in all_in_cat:
            if (r.grammar_domain or "other") != body.grammar_domain:
                merged.append(r)
            else:
                if di < len(reordered):
                    merged.append(reordered[di])
                    di += 1
        for i, row in enumerate(merged):
            row.sort_order = i
    else:
        for i, rid in enumerate(body.ordered_ids):
            row = db.get(CanonicalRule, rid)
            if row and row.category == body.category:
                row.sort_order = i
    db.commit()
    return {"category": body.category, "grammar_domain": body.grammar_domain, "count": len(body.ordered_ids)}


@router.patch("/{rule_id}", response_model=CanonicalRuleOut)
def patch_rule(rule_id: str, body: CanonicalRulePatch, db: DbSession, user: RequireWorker):
    row = db.get(CanonicalRule, rule_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k in ("grammar_domain", "pos_tag", "construction_type") and v is not None:
            if k == "grammar_domain" and v not in DOMAIN_IDS:
                raise HTTPException(status_code=400, detail=f"Invalid grammar_domain: {v}")
            if k == "pos_tag" and v not in POS_IDS:
                raise HTTPException(status_code=400, detail=f"Invalid pos_tag: {v}")
            if k == "construction_type" and v not in CONSTRUCTION_IDS:
                raise HTTPException(status_code=400, detail=f"Invalid construction_type: {v}")
        setattr(row, k, v)
    if "content" in data:
        row.content_normalized = normalize_text(row.content)
        if row.category == "grammar" and not any(
            k in data for k in ("grammar_domain", "pos_tag", "construction_type")
        ):
            apply_classification_to_rule(row, row.category, row.content)
    if any(k in data for k in ("source_page", "source_page_end", "source_excerpt")):
        row.provenance_status = "manual"
    db.commit()
    db.refresh(row)
    return canonical_rule_out(db, row)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: str, db: DbSession, user: RequireWorker):
    row = db.get(CanonicalRule, rule_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    write_audit(
        db,
        entity_type="canonical_rule",
        entity_id=row.id,
        action="delete",
        user_id=user.id,
        payload={"category": row.category, "content": row.content[:200]},
    )
    db.delete(row)
    db.commit()
    return Response(status_code=204)
