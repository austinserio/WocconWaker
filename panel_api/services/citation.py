"""Chicago author-date citation formatting for source documents."""
import json
import re
from typing import Any, List, Optional

from panel_api.db import SourceDocument
from panel_api.schemas import CitationOut

LAWSON_SEED_ID = "00000000-0000-4000-8000-000000000001"


def parse_authors(doc: SourceDocument) -> List[str]:
    raw = doc.authors or "[]"
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(a).strip() for a in data if str(a).strip()]
    except json.JSONDecodeError:
        pass
    if raw.strip():
        return [raw.strip()]
    return []


def _author_surname(author: str) -> str:
    author = author.strip()
    if "," in author:
        return author.split(",", 1)[0].strip()
    parts = author.split()
    return parts[-1] if parts else author


def _short_author_label(authors: List[str], doc: SourceDocument) -> str:
    if not authors:
        if doc.short_title:
            return doc.short_title.strip()
        return (doc.title or "Unknown").strip()[:60]
    if len(authors) == 1:
        return _author_surname(authors[0])
    if len(authors) == 2:
        return f"{_author_surname(authors[0])} and {_author_surname(authors[1])}"
    return f"{_author_surname(authors[0])} et al."


def _page_suffix(page: Optional[int], page_end: Optional[int] = None) -> str:
    if page is None:
        return ""
    if page_end is not None and page_end != page:
        return f", pp. {page}–{page_end}"
    return f", p. {page}"


def format_chicago_short(
    doc: Optional[SourceDocument],
    page: Optional[int] = None,
    page_end: Optional[int] = None,
    *,
    fallback_source: Optional[str] = None,
) -> str:
    if doc is None:
        if fallback_source:
            base = fallback_source.replace("_", " ").title()
            return f"{base}{_page_suffix(page, page_end)}".strip(", ")
        return ""
    authors = parse_authors(doc)
    label = _short_author_label(authors, doc)
    year = (doc.year or "n.d.").strip()
    return f"{label} {year}{_page_suffix(page, page_end)}"


def format_chicago_full(doc: SourceDocument) -> str:
    if doc.citation_text and doc.citation_text.strip():
        return doc.citation_text.strip()
    authors = parse_authors(doc)
    year = (doc.year or "n.d.").strip()
    pub_title = (doc.pub_title or doc.short_title or doc.title or "").strip()
    parts: List[str] = []
    if authors:
        if len(authors) == 1:
            parts.append(authors[0] + ".")
        elif len(authors) == 2:
            parts.append(f"{authors[0]} and {authors[1]}.")
        else:
            parts.append(f"{authors[0]}, {authors[1]}, and {authors[-1]}.")
    parts.append(f"{year}.")
    if pub_title:
        parts.append(f"*{pub_title}*.")
    if doc.container_title:
        parts.append(f"In *{doc.container_title.strip()}*.")
    pub_bits = []
    if doc.place:
        pub_bits.append(doc.place.strip())
    if doc.publisher:
        pub_bits.append(doc.publisher.strip())
    if pub_bits:
        parts.append(": ".join(pub_bits) + ".")
    return " ".join(parts)


def guess_bibliography_from_title(title: str) -> dict[str, Any]:
    """Best-effort defaults when a document is uploaded."""
    short = title
    year = None
    m = re.search(r"\((19|20)\d{2}\)", title)
    if m:
        year = m.group(0).strip("()")
    m2 = re.search(r"(19|20)\d{2}", title)
    if not year and m2:
        year = m2.group(0)
    if len(title) > 80:
        short = title[:77] + "..."
    return {"short_title": short, "year": year, "pub_title": title}


def build_citation_out(
    doc: Optional[SourceDocument],
    *,
    page: Optional[int] = None,
    page_end: Optional[int] = None,
    excerpt: Optional[str] = None,
    provenance_status: Optional[str] = None,
    source_url: Optional[str] = None,
    fallback_source: Optional[str] = None,
) -> Optional[CitationOut]:
    url = source_url or (doc.source_url if doc else None)
    if doc is None and not fallback_source and not url:
        return None
    short = format_chicago_short(doc, page, page_end, fallback_source=fallback_source)
    full = format_chicago_full(doc) if doc else (fallback_source or "")
    if not short and not full and not url:
        return None
    file_url = f"/api/documents/{doc.id}/file" if doc else None
    return CitationOut(
        short=short or full,
        full=full,
        page=page,
        page_end=page_end,
        excerpt=excerpt,
        provenance_status=provenance_status,
        document_id=doc.id if doc else None,
        document_title=doc.title if doc else None,
        source_url=url,
        file_url=file_url,
    )


def citation_for_entry(
    db,
    *,
    source_document_id: Optional[str],
    source: Optional[str],
    source_url: Optional[str],
    source_page: Optional[int] = None,
    source_page_end: Optional[int] = None,
    source_excerpt: Optional[str] = None,
    provenance_status: Optional[str] = None,
    doc: Optional[SourceDocument] = None,
) -> Optional[CitationOut]:
    if doc is None and source_document_id:
        doc = db.get(SourceDocument, source_document_id)
    if doc is None and source and source.lower() in ("lawson", "lawson1709"):
        doc = db.get(SourceDocument, LAWSON_SEED_ID)
    fallback = None
    if doc is None and source:
        fallback = source.replace("_", " ").title()
        if "lawson" in (source or "").lower():
            fallback = "Lawson 1709"
    return build_citation_out(
        doc,
        page=source_page,
        page_end=source_page_end,
        excerpt=source_excerpt,
        provenance_status=provenance_status,
        source_url=source_url,
        fallback_source=fallback,
    )
