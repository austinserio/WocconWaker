"""Backfill provenance by re-parsing sources referenced in canonical citations."""
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from panel_api.db import CanonicalLexicon, CanonicalRule, SourceDocument
from panel_api.services.ingest import (
    apply_bibliography_defaults,
    fetch_drive_text,
    merge_locators_from_text,
    parse_drive_file_id,
    process_document,
)

log = logging.getLogger("citation_backfill")

DEFAULT_STAGING_DIR = os.environ.get("DRIVE_STAGING_DIR", "woccon_language/drive_staging")


@dataclass
class CitationSource:
    source_url: str
    file_id: str
    lexicon_count: int
    rules_count: int
    title: Optional[str] = None


def load_staging_metadata(staging_dir: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    """Map Drive file_id -> {source_path, source_url} from manifest and sync_state."""
    base = Path(staging_dir or DEFAULT_STAGING_DIR)
    out: Dict[str, Dict[str, str]] = {}
    manifest_path = base / "manifest.json"
    if manifest_path.is_file():
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("files") or []:
            url = entry.get("source_url") or ""
            fid = parse_drive_file_id(url)
            if fid:
                out[fid] = {
                    "source_path": entry.get("source_path") or entry.get("file") or fid,
                    "source_url": url,
                }
    sync_path = base / "sync_state.json"
    if sync_path.is_file():
        with open(sync_path, encoding="utf-8") as f:
            sync = json.load(f)
        for fid, meta in sync.items():
            if fid not in out and isinstance(meta, dict):
                staging_file = meta.get("staging_file", "")
                out[fid] = {
                    "source_path": staging_file.replace(".json", "").replace("_", " "),
                    "source_url": f"https://drive.google.com/file/d/{fid}/view",
                }
    return out


def collect_citation_sources(db: Session) -> List[CitationSource]:
    """Distinct Drive sources cited on canonical lexicon and rules."""
    by_file: Dict[str, CitationSource] = {}
    staging = load_staging_metadata()

    for row in db.query(CanonicalLexicon).filter(CanonicalLexicon.source_url.isnot(None)).all():
        fid = parse_drive_file_id(row.source_url or "")
        if not fid:
            continue
        if fid not in by_file:
            meta = staging.get(fid, {})
            by_file[fid] = CitationSource(
                source_url=row.source_url or "",
                file_id=fid,
                lexicon_count=0,
                rules_count=0,
                title=meta.get("source_path"),
            )
        by_file[fid].lexicon_count += 1

    for row in db.query(CanonicalRule).filter(CanonicalRule.source_url.isnot(None)).all():
        fid = parse_drive_file_id(row.source_url or "")
        if not fid:
            continue
        if fid not in by_file:
            meta = staging.get(fid, {})
            by_file[fid] = CitationSource(
                source_url=row.source_url or "",
                file_id=fid,
                lexicon_count=0,
                rules_count=0,
                title=meta.get("source_path"),
            )
        by_file[fid].rules_count += 1

    return sorted(by_file.values(), key=lambda s: s.title or s.file_id)


def ensure_source_document(
    db: Session,
    file_id: str,
    source_url: str,
    title: Optional[str] = None,
) -> SourceDocument:
    """Get or create a drive_link SourceDocument for a cited Drive file."""
    from drive_extract import _source_url

    doc = db.query(SourceDocument).filter(SourceDocument.drive_file_id == file_id).first()
    canonical_url = _source_url(file_id)
    if doc:
        if not doc.source_url:
            doc.source_url = canonical_url
        if title and (not doc.title or doc.title == "drive_document"):
            doc.title = title
        return doc
    doc = SourceDocument(
        title=title or file_id,
        source_type="drive_link",
        source_url=canonical_url or source_url,
        drive_file_id=file_id,
        status="ready",
    )
    apply_bibliography_defaults(doc)
    db.add(doc)
    db.flush()
    return doc


def backfill_from_citations(
    db: Session,
    *,
    dry_run: bool = False,
    file_id_filter: Optional[str] = None,
    text_only: bool = False,
) -> Dict[str, Any]:
    """Re-fetch each cited Drive source and merge locators into canonical rows."""
    sources = collect_citation_sources(db)
    if file_id_filter:
        sources = [s for s in sources if s.file_id == file_id_filter]
    summary: Dict[str, Any] = {
        "sources_found": len(sources),
        "dry_run": dry_run,
        "results": [],
    }
    if dry_run:
        for s in sources:
            summary["results"].append(
                {
                    "file_id": s.file_id,
                    "title": s.title,
                    "source_url": s.source_url,
                    "lexicon_count": s.lexicon_count,
                    "rules_count": s.rules_count,
                }
            )
        return summary

    for s in sources:
        entry: Dict[str, Any] = {
            "file_id": s.file_id,
            "title": s.title,
            "source_url": s.source_url,
        }
        try:
            doc = ensure_source_document(db, s.file_id, s.source_url, s.title)
            db.commit()
            text, drive_name, _ = fetch_drive_text(s.file_id)
            if s.title and doc.title == s.file_id:
                doc.title = drive_name or s.title
            if not (text or "").strip():
                entry["error"] = "No text extracted from Drive"
                summary["results"].append(entry)
                continue
            doc.status = "processing"
            db.commit()
            if text_only:
                locators_from_text = merge_locators_from_text(db, doc, text)
                doc.status = "ready"
                db.commit()
                result = {
                    "document_id": doc.id,
                    "status": "ready",
                    "text_only": True,
                    "locators_from_text": locators_from_text,
                }
            else:
                result = process_document(
                    db,
                    doc,
                    text,
                    merge_locators=True,
                    merge_only=True,
                )
            entry.update(result)
            log.info(
                "Citation backfill %s: llm=%s text=%s",
                s.title or s.file_id,
                result.get("locators_merged"),
                result.get("locators_from_text"),
            )
        except Exception as e:
            log.exception("Citation backfill failed for %s", s.file_id)
            entry["error"] = str(e)
        summary["results"].append(entry)
    return summary
