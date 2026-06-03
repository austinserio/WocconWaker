from collections import defaultdict
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, or_

from panel_api.db import CanonicalLexicon, PendingLexicon, SourceDocument
from panel_api.deps import CurrentUser, DbSession, RequireAdmin, RequireWorker
from panel_api.lexicon_taxonomy import (
    LESSON_BAND_IDS,
    TEACHING_UNIT_IDS,
    TEACHING_UNITS,
    WORD_CLASS_IDS,
    lexicon_taxonomy_payload,
    unit_label,
)
from panel_api.schemas import (
    CanonicalLexiconOut,
    CanonicalLexiconPatch,
    LexiconGroupOut,
    LexiconListResponse,
)
from panel_api.services.audit import write_audit
from panel_api.services.lexicon_classifier import apply_lexicon_classification, normalize_word_class
from panel_api.services.lexicon_reclassify import reclassify_all_lexicon
from panel_api.services.serializers import canonical_lexicon_out

router = APIRouter(prefix="/lexicon", tags=["lexicon"])


def _lexicon_batch_context(db, rows: list) -> dict:
    """Prefetch documents and variant stats for grouped/list responses."""
    doc_ids = {r.source_document_id for r in rows if r.source_document_id}
    doc_cache = {}
    if doc_ids:
        doc_cache = {
            d.id: d
            for d in db.query(SourceDocument).filter(SourceDocument.id.in_(doc_ids)).all()
        }
    variant_counts = dict(
        db.query(CanonicalLexicon.base_entry_id, func.count())
        .filter(CanonicalLexicon.base_entry_id.isnot(None))
        .group_by(CanonicalLexicon.base_entry_id)
        .all()
    )
    base_ids = [r.id for r in rows if r.is_base_entry]
    variants_by_base: dict = defaultdict(list)
    if base_ids:
        for v in (
            db.query(CanonicalLexicon)
            .filter(
                CanonicalLexicon.base_entry_id.in_(base_ids),
                CanonicalLexicon.is_base_entry.is_(False),
            )
            .all()
        ):
            variants_by_base[v.base_entry_id].append(v)
    return {
        "doc_cache": doc_cache,
        "variant_counts": variant_counts,
        "variants_by_base": dict(variants_by_base),
    }


def _apply_dedupe_filter(query, dedupe: bool):
    """Hide variant rows that are already grouped under a base entry."""
    if dedupe:
        query = query.filter(
            or_(
                CanonicalLexicon.is_base_entry.is_(True),
                CanonicalLexicon.base_entry_id.is_(None),
            )
        )
    return query


def _lexicon_query(
    db,
    *,
    q: Optional[str],
    teaching_unit: Optional[str],
    word_class: Optional[str],
    lesson_band: Optional[str],
    source: Optional[str],
    pos: Optional[str],
    view: Optional[str] = None,
    dedupe: bool = True,
):
    query = db.query(CanonicalLexicon)
    if view == "base":
        query = query.filter(CanonicalLexicon.is_base_entry.is_(True))
    elif view == "unlinked":
        query = query.filter(
            CanonicalLexicon.is_base_entry.is_(False),
            CanonicalLexicon.base_entry_id.is_(None),
        )
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(CanonicalLexicon.woccon.ilike(like), CanonicalLexicon.english.ilike(like))
        )
    if teaching_unit:
        query = query.filter(CanonicalLexicon.teaching_unit == teaching_unit)
    if word_class:
        query = query.filter(CanonicalLexicon.word_class == word_class)
    if lesson_band:
        query = query.filter(CanonicalLexicon.lesson_band == lesson_band)
    if source:
        query = query.filter(CanonicalLexicon.source == source)
    if pos:
        query = query.filter(CanonicalLexicon.pos.ilike(f"%{pos}%"))
    query = _apply_dedupe_filter(query, dedupe)
    if view == "base":
        return query.order_by(
            CanonicalLexicon.sort_order.asc().nulls_last(),
            CanonicalLexicon.woccon,
        )
    return query.order_by(
        CanonicalLexicon.teaching_unit.asc().nulls_last(),
        CanonicalLexicon.lesson_band.asc().nulls_last(),
        CanonicalLexicon.woccon,
    )


@router.get("/taxonomy")
def get_lexicon_taxonomy(user: CurrentUser):
    return lexicon_taxonomy_payload()


@router.get("/stats")
def lexicon_stats(db: DbSession, user: CurrentUser):
    total = db.query(func.count(CanonicalLexicon.id)).scalar() or 0
    base_count = (
        db.query(func.count(CanonicalLexicon.id))
        .filter(CanonicalLexicon.is_base_entry.is_(True))
        .scalar()
        or 0
    )
    variant_count = (
        db.query(func.count(CanonicalLexicon.id))
        .filter(
            CanonicalLexicon.is_base_entry.is_(False),
            CanonicalLexicon.base_entry_id.isnot(None),
        )
        .scalar()
        or 0
    )
    by_unit = dict(
        db.query(
            func.coalesce(CanonicalLexicon.teaching_unit, "other"),
            func.count(),
        )
        .group_by(func.coalesce(CanonicalLexicon.teaching_unit, "other"))
        .all()
    )
    by_class = dict(
        db.query(
            func.coalesce(CanonicalLexicon.word_class, "unknown"),
            func.count(),
        )
        .group_by(func.coalesce(CanonicalLexicon.word_class, "unknown"))
        .all()
    )
    by_band = dict(
        db.query(
            func.coalesce(CanonicalLexicon.lesson_band, "intermediate"),
            func.count(),
        )
        .group_by(func.coalesce(CanonicalLexicon.lesson_band, "intermediate"))
        .all()
    )
    unmatched_pending = (
        db.query(PendingLexicon)
        .filter(
            PendingLexicon.status.in_(["pending", "modified"]),
            PendingLexicon.match_status == "unmatched",
        )
        .count()
    )
    return {
        "total": total,
        "base_count": base_count,
        "variant_count": variant_count,
        "unmatched_pending": unmatched_pending,
        "by_teaching_unit": by_unit,
        "by_word_class": by_class,
        "by_lesson_band": by_band,
    }


@router.get("/grouped", response_model=List[LexiconGroupOut])
def list_lexicon_grouped(
    db: DbSession,
    user: CurrentUser,
    word_class: Optional[str] = Query(None),
    lesson_band: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    dedupe: bool = Query(True),
):
    rows = _lexicon_query(
        db,
        q=q,
        teaching_unit=None,
        word_class=word_class,
        lesson_band=lesson_band,
        source=None,
        pos=None,
        dedupe=dedupe,
    ).all()
    ctx = _lexicon_batch_context(db, rows)
    groups: dict = defaultdict(list)
    for r in rows:
        key = r.teaching_unit or "other"
        groups[key].append(
            canonical_lexicon_out(
                db,
                r,
                include_variant_count=True,
                doc_cache=ctx["doc_cache"],
                variant_counts=ctx["variant_counts"],
                variants_by_base=ctx["variants_by_base"],
            )
        )
    unit_order = [u["id"] for u in TEACHING_UNITS]
    result = []
    for uid in unit_order:
        if uid in groups:
            result.append(
                LexiconGroupOut(
                    teaching_unit=uid,
                    label=unit_label(uid),
                    count=len(groups[uid]),
                    entries=groups[uid],
                )
            )
    for uid, entries in groups.items():
        if uid not in unit_order:
            result.append(
                LexiconGroupOut(
                    teaching_unit=uid,
                    label=unit_label(uid),
                    count=len(entries),
                    entries=entries,
                )
            )
    return result


@router.get("/base", response_model=LexiconListResponse)
def list_base_lexicon(
    db: DbSession,
    user: CurrentUser,
    q: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=500),
    sort: Optional[str] = Query("order"),
):
    query = db.query(CanonicalLexicon).filter(CanonicalLexicon.is_base_entry.is_(True))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(CanonicalLexicon.woccon.ilike(like), CanonicalLexicon.english.ilike(like))
        )
    if sort == "woccon":
        query = query.order_by(CanonicalLexicon.woccon)
    elif sort == "english":
        query = query.order_by(CanonicalLexicon.english)
    else:
        query = query.order_by(
            CanonicalLexicon.sort_order.asc().nulls_last(),
            CanonicalLexicon.woccon,
        )
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return LexiconListResponse(
        items=[canonical_lexicon_out(db, r, include_variant_count=True) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=LexiconListResponse)
def list_lexicon(
    db: DbSession,
    user: CurrentUser,
    q: Optional[str] = Query(None),
    teaching_unit: Optional[str] = Query(None),
    word_class: Optional[str] = Query(None),
    lesson_band: Optional[str] = Query(None),
    pos: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    view: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort: Optional[str] = Query(None),
    dedupe: bool = Query(True),
):
    query = _lexicon_query(
        db,
        q=q,
        teaching_unit=teaching_unit,
        word_class=word_class,
        lesson_band=lesson_band,
        source=source,
        pos=pos,
        view=view,
        dedupe=dedupe,
    )
    if sort in ("english", "woccon"):
        col = CanonicalLexicon.english if sort == "english" else CanonicalLexicon.woccon
        query = query.order_by(None).order_by(col)
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return LexiconListResponse(
        items=[
            canonical_lexicon_out(db, r, include_variant_count=r.is_base_entry)
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/reclassify")
def reclassify_lexicon(db: DbSession, admin: RequireAdmin):
    return reclassify_all_lexicon(db)


@router.get("/{entry_id}/variants", response_model=List[CanonicalLexiconOut])
def list_lexicon_variants(entry_id: str, db: DbSession, user: CurrentUser):
    base = db.get(CanonicalLexicon, entry_id)
    if not base or not base.is_base_entry:
        raise HTTPException(status_code=404, detail="Base entry not found")
    rows = (
        db.query(CanonicalLexicon)
        .filter(CanonicalLexicon.base_entry_id == entry_id, CanonicalLexicon.is_base_entry.is_(False))
        .order_by(CanonicalLexicon.woccon)
        .all()
    )
    return [canonical_lexicon_out(db, r) for r in rows]


@router.get("/{entry_id}", response_model=CanonicalLexiconOut)
def get_lexicon(entry_id: str, db: DbSession, user: CurrentUser):
    row = db.get(CanonicalLexicon, entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return canonical_lexicon_out(db, row)


@router.patch("/{entry_id}", response_model=CanonicalLexiconOut)
def patch_lexicon(entry_id: str, body: CanonicalLexiconPatch, db: DbSession, user: RequireWorker):
    row = db.get(CanonicalLexicon, entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    if row.is_base_entry and any(k in data for k in ("woccon", "english")):
        raise HTTPException(
            status_code=409,
            detail="Base vocabulary entries cannot change woccon/english here; sync from the definitive Google Doc.",
        )
    for k, v in data.items():
        if k == "teaching_unit" and v is not None and v not in TEACHING_UNIT_IDS:
            raise HTTPException(status_code=400, detail=f"Invalid teaching_unit: {v}")
        if k == "word_class" and v is not None and v not in WORD_CLASS_IDS:
            raise HTTPException(status_code=400, detail=f"Invalid word_class: {v}")
        if k == "lesson_band" and v is not None and v not in LESSON_BAND_IDS:
            raise HTTPException(status_code=400, detail=f"Invalid lesson_band: {v}")
        setattr(row, k, v)
    if "woccon" in data:
        row.woccon_normalized = (row.woccon or "").strip().lower()
    if any(k in data for k in ("woccon", "english", "pos")) and not any(
        k in data for k in ("teaching_unit", "word_class", "lesson_band")
    ):
        apply_lexicon_classification(row, row.woccon, row.english, row.pos, row.source)
    elif "pos" in data:
        row.word_class = normalize_word_class(row.pos)
    if any(k in data for k in ("source_page", "source_page_end", "source_excerpt")):
        row.provenance_status = "manual"
    db.commit()
    db.refresh(row)
    return canonical_lexicon_out(db, row)


@router.delete("/{entry_id}", status_code=204)
def delete_lexicon(entry_id: str, db: DbSession, user: RequireWorker):
    row = db.get(CanonicalLexicon, entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if row.is_base_entry:
        raise HTTPException(
            status_code=409,
            detail="Base vocabulary entries cannot be deleted; re-sync from the definitive Google Doc.",
        )
    if row.source and "lawson" in row.source.lower():
        raise HTTPException(
            status_code=409,
            detail="Lawson seed entries cannot be deleted from the panel; they would reappear on commit from the legacy dictionary.",
        )
    write_audit(
        db,
        entity_type="canonical_lexicon",
        entity_id=row.id,
        action="delete",
        user_id=user.id,
        payload={"woccon": row.woccon, "english": row.english, "source": row.source},
    )
    db.delete(row)
    db.commit()
    return Response(status_code=204)
