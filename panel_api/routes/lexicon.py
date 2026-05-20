from collections import defaultdict
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_

from panel_api.db import CanonicalLexicon
from panel_api.deps import CurrentUser, DbSession, RequireAdmin, RequireReviewer
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
from panel_api.services.lexicon_classifier import apply_lexicon_classification, normalize_word_class
from panel_api.services.lexicon_reclassify import reclassify_all_lexicon

router = APIRouter(prefix="/lexicon", tags=["lexicon"])


def _lexicon_query(
    db,
    *,
    q: Optional[str],
    teaching_unit: Optional[str],
    word_class: Optional[str],
    lesson_band: Optional[str],
    source: Optional[str],
    pos: Optional[str],
):
    query = db.query(CanonicalLexicon)
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
    rows = db.query(CanonicalLexicon).all()
    by_unit: dict = defaultdict(int)
    by_class: dict = defaultdict(int)
    by_band: dict = defaultdict(int)
    for r in rows:
        by_unit[r.teaching_unit or "other"] += 1
        by_class[r.word_class or "unknown"] += 1
        by_band[r.lesson_band or "intermediate"] += 1
    return {
        "total": len(rows),
        "by_teaching_unit": dict(by_unit),
        "by_word_class": dict(by_class),
        "by_lesson_band": dict(by_band),
    }


@router.get("/grouped", response_model=List[LexiconGroupOut])
def list_lexicon_grouped(
    db: DbSession,
    user: CurrentUser,
    word_class: Optional[str] = Query(None),
    lesson_band: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
):
    rows = _lexicon_query(
        db,
        q=q,
        teaching_unit=None,
        word_class=word_class,
        lesson_band=lesson_band,
        source=None,
        pos=None,
    ).all()
    groups: dict = defaultdict(list)
    for r in rows:
        key = r.teaching_unit or "other"
        groups[key].append(CanonicalLexiconOut.model_validate(r))
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
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    query = _lexicon_query(
        db,
        q=q,
        teaching_unit=teaching_unit,
        word_class=word_class,
        lesson_band=lesson_band,
        source=source,
        pos=pos,
    )
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return LexiconListResponse(
        items=[CanonicalLexiconOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/reclassify")
def reclassify_lexicon(db: DbSession, admin: RequireAdmin):
    return reclassify_all_lexicon(db)


@router.get("/{entry_id}", response_model=CanonicalLexiconOut)
def get_lexicon(entry_id: str, db: DbSession, user: CurrentUser):
    row = db.get(CanonicalLexicon, entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return CanonicalLexiconOut.model_validate(row)


@router.patch("/{entry_id}", response_model=CanonicalLexiconOut)
def patch_lexicon(entry_id: str, body: CanonicalLexiconPatch, db: DbSession, user: RequireReviewer):
    row = db.get(CanonicalLexicon, entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
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
    db.commit()
    db.refresh(row)
    return CanonicalLexiconOut.model_validate(row)
