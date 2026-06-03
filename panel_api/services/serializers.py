"""Helpers to attach citations to API response models."""
from typing import Any, Optional

from panel_api.schemas import (
    BaseMatchPreview,
    CanonicalLexiconOut,
    CanonicalRuleOut,
    CitationOut,
    DuplicateMatchPreview,
    PendingLexiconOut,
    PendingRuleOut,
)
from panel_api.services.citation import citation_for_entry
from panel_api.services.duplicates import resolve_lexicon_duplicate, resolve_rule_duplicate
from panel_api.services.pronunciation import normalize_pronunciation
from panel_api.services.vocab_match import (
    attestation_citation_count,
    base_entry_preview,
    variant_count,
)


def _attach_citation(db, row, out_cls, extra: dict | None = None, doc=None):
    data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    if extra:
        data.update(extra)
    out = out_cls.model_validate(row)
    citation = citation_for_entry(
        db,
        source_document_id=getattr(row, "source_document_id", None),
        source=getattr(row, "source", None),
        source_url=getattr(row, "source_url", None),
        source_page=getattr(row, "source_page", None),
        source_page_end=getattr(row, "source_page_end", None),
        source_excerpt=getattr(row, "source_excerpt", None),
        provenance_status=getattr(row, "provenance_status", None),
        doc=doc,
    )
    payload = out.model_dump()
    payload["citation"] = citation
    if "pronunciation" in payload:
        payload["pronunciation"] = normalize_pronunciation(payload.get("pronunciation"))
    if extra:
        payload.update(extra)
    return out_cls.model_validate(payload)


def _duplicate_match_preview(db, match_row, match_type: str) -> DuplicateMatchPreview:
    citation = citation_for_entry(
        db,
        source_document_id=getattr(match_row, "source_document_id", None),
        source=getattr(match_row, "source", None),
        source_url=getattr(match_row, "source_url", None),
        source_page=getattr(match_row, "source_page", None),
        source_page_end=getattr(match_row, "source_page_end", None),
        source_excerpt=getattr(match_row, "source_excerpt", None),
        provenance_status=getattr(match_row, "provenance_status", None),
    )
    return DuplicateMatchPreview(
        id=match_row.id,
        match_type=match_type,
        woccon=getattr(match_row, "woccon", None),
        english=getattr(match_row, "english", None),
        pos=getattr(match_row, "pos", None),
        pronunciation=normalize_pronunciation(getattr(match_row, "pronunciation", None)),
        teaching_unit=getattr(match_row, "teaching_unit", None),
        word_class=getattr(match_row, "word_class", None),
        lesson_band=getattr(match_row, "lesson_band", None),
        category=getattr(match_row, "category", None),
        content=getattr(match_row, "content", None),
        status=getattr(match_row, "status", None),
        source_url=getattr(match_row, "source_url", None),
        source_page=getattr(match_row, "source_page", None),
        source_page_end=getattr(match_row, "source_page_end", None),
        source_excerpt=getattr(match_row, "source_excerpt", None),
        provenance_status=getattr(match_row, "provenance_status", None),
        citation=citation,
    )


def pending_lexicon_out(db, row) -> PendingLexiconOut:
    extra: dict = {}
    if row.base_entry_id:
        preview = base_entry_preview(db, row.base_entry_id)
        if preview:
            extra["base_match"] = BaseMatchPreview(
                id=preview["id"],
                woccon=preview["woccon"],
                english=preview["english"],
                score=row.base_match_score,
                method=row.base_match_method,
            )
    if row.duplicate_of_id:
        match_row, match_type = resolve_lexicon_duplicate(db, row.duplicate_of_id)
        if match_row:
            extra["duplicate_match"] = _duplicate_match_preview(db, match_row, match_type)
    return _attach_citation(db, row, PendingLexiconOut, extra)


def pending_rule_out(db, row) -> PendingRuleOut:
    extra: dict = {}
    if row.duplicate_of_id:
        match_row, match_type = resolve_rule_duplicate(db, row.duplicate_of_id)
        if match_row:
            extra["duplicate_match"] = _duplicate_match_preview(db, match_row, match_type)
    return _attach_citation(db, row, PendingRuleOut, extra)


def canonical_lexicon_out(
    db,
    row,
    *,
    include_variant_count: bool = False,
    doc_cache: dict | None = None,
    variant_counts: dict | None = None,
    variants_by_base: dict | None = None,
) -> CanonicalLexiconOut:
    extra: dict = {}
    doc = None
    if doc_cache is not None and getattr(row, "source_document_id", None):
        doc = doc_cache.get(row.source_document_id)
    if include_variant_count and getattr(row, "is_base_entry", False):
        if variant_counts is not None:
            extra["variant_count"] = variant_counts.get(row.id, 0)
        else:
            extra["variant_count"] = variant_count(db, row.id)
        if variants_by_base is not None:
            variants = variants_by_base.get(row.id, [])
            extra["source_count"] = _attestation_count_from_rows(row, variants)
        else:
            extra["source_count"] = attestation_citation_count(db, row)
    return _attach_citation(db, row, CanonicalLexiconOut, extra, doc=doc)


def _attestation_count_from_rows(base_row, variants: list) -> int:
    """Same logic as attestation_citation_count without extra queries."""
    from panel_api.services.vocab_match import _citation_key

    seen: set[str] = set()
    count = 0
    for item in [base_row, *variants]:
        key = _citation_key(item)
        if key in seen:
            continue
        seen.add(key)
        count += 1
    return count


def canonical_rule_out(db, row) -> CanonicalRuleOut:
    return _attach_citation(db, row, CanonicalRuleOut)
