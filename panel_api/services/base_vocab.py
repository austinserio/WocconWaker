"""Import and sync definitive base vocabulary from Google Doc."""
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from panel_api.config import get_settings
from panel_api.db import CanonicalLexicon, SourceDocument
from panel_api.services.duplicates import normalize_text
from panel_api.services.ingest import fetch_drive_text, parse_drive_file_id
from panel_api.services.lexicon_classifier import apply_lexicon_classification
from list_doc_parser import parse_pronunciation_text as _parse_pronunciation_text
from list_doc_parser import parse_vocab_text as _parse_vocab_text
from panel_api.services.pronunciation import normalize_pronunciation
from panel_api.services.vocab_match import (
    base_woccon_match,
    find_duplicate_base,
    normalize_woccon,
)

log = logging.getLogger("base_vocab")

VOCAB_BASE_TITLE = "Documentation of Woccon Words"
STAGING_FALLBACK = Path("woccon_language/drive_staging/Documentation of Woccon Words.json")
PRONUNCIATION_TITLE = "English-Woccon"
PRONUNCIATION_STAGING = Path("woccon_language/drive_staging/English-Woccon.json")
MIN_PARSED_ENTRIES = 180
MIN_PRONUNCIATION_ENTRIES = 150

def _source_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{file_id}/view"


def parse_vocab_text(text: str) -> List[Dict[str, Any]]:
    return _parse_vocab_text(text)


def parse_pronunciation_text(text: str) -> List[Dict[str, Any]]:
    """Parse English-Woccon style lines that include (pronunciation) guides."""
    entries = _parse_pronunciation_text(text)
    return [
        {
            "woccon": e["woccon"],
            "english": e["english"],
            "pronunciation": normalize_pronunciation(e.get("pronunciation")),
        }
        for e in entries
    ]


def load_pronunciation_staging() -> List[Dict[str, Any]]:
    if not PRONUNCIATION_STAGING.is_file():
        return []
    data = json.loads(PRONUNCIATION_STAGING.read_text(encoding="utf-8"))
    out = []
    for e in data.get("lexicon_entries") or []:
        pron = (e.get("pronunciation") or "").strip()
        if not pron:
            continue
        out.append(
            {
                "woccon": (e.get("woccon") or "").strip(),
                "english": (e.get("english") or "").strip(),
                "pronunciation": normalize_pronunciation(pron),
            }
        )
    return out


def fetch_pronunciation_entries(file_id: str) -> List[Dict[str, Any]]:
    """Load pronunciation rows from Drive text or staging JSON."""
    try:
        text, _, _ = fetch_drive_text(file_id)
        parsed = parse_pronunciation_text(text)
        if len(parsed) >= MIN_PRONUNCIATION_ENTRIES:
            log.info("Parsed %d pronunciation entries from Drive text", len(parsed))
            return parsed
        log.warning("Drive pronunciation parse yielded %d entries; trying staging", len(parsed))
    except Exception as e:
        log.warning("Pronunciation Drive fetch failed (%s); using staging", e)

    staging = load_pronunciation_staging()
    if staging:
        log.info("Loaded %d pronunciation entries from staging JSON", len(staging))
        return staging
    return []


def load_staging_fallback() -> List[Dict[str, Any]]:
    path = STAGING_FALLBACK
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("lexicon_entries") or []


def fetch_vocab_entries(file_id: str) -> List[Dict[str, Any]]:
    """Fetch entries from Drive text, falling back to staging JSON."""
    try:
        text, _, _ = fetch_drive_text(file_id)
        parsed = parse_vocab_text(text)
        if len(parsed) >= MIN_PARSED_ENTRIES:
            log.info("Parsed %d base vocab entries from Drive text", len(parsed))
            return parsed
        log.warning("Drive parse yielded %d entries; trying staging fallback", len(parsed))
    except Exception as e:
        log.warning("Drive fetch failed (%s); using staging fallback", e)

    staging = load_staging_fallback()
    if staging:
        log.info("Loaded %d base vocab entries from staging JSON", len(staging))
        return staging
    return []


def find_vocab_base_document(db: Session, file_id: str) -> Optional[SourceDocument]:
    for doc in db.query(SourceDocument).all():
        if doc.is_vocab_base:
            return doc
        if doc.drive_file_id == file_id:
            return doc
        if doc.source_url and parse_drive_file_id(doc.source_url) == file_id:
            return doc
    return None


def ensure_vocab_base_document(db: Session) -> Optional[SourceDocument]:
    settings = get_settings()
    file_id = (settings.base_vocab_drive_id or "").strip()
    if not file_id:
        return None

    doc = find_vocab_base_document(db, file_id)
    if doc:
        doc.is_vocab_base = True
        doc.drive_file_id = file_id
        doc.source_url = doc.source_url or _source_url(file_id)
        if doc.source_type not in ("vocab_base", "seed"):
            doc.source_type = "vocab_base"
        doc.status = doc.status or "ready"
        if not doc.title or doc.title == "drive_document":
            doc.title = VOCAB_BASE_TITLE
        db.commit()
        db.refresh(doc)
        return doc

    doc = SourceDocument(
        title=VOCAB_BASE_TITLE,
        source_type="vocab_base",
        source_url=_source_url(file_id),
        drive_file_id=file_id,
        mime_type="application/vnd.google-apps.document",
        is_vocab_base=True,
        status="ready",
        short_title="Woccon Words",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    log.info("Created vocab base source document %s", doc.id)
    return doc


def ensure_pronunciation_document(db: Session) -> Optional[SourceDocument]:
    settings = get_settings()
    file_id = (settings.base_pronunciation_drive_id or "").strip()
    if not file_id:
        return None

    for doc in db.query(SourceDocument).all():
        if doc.drive_file_id == file_id:
            if not doc.title or doc.title == "drive_document":
                doc.title = PRONUNCIATION_TITLE
            if doc.source_type not in ("pronunciation_guide", "vocab_base", "seed"):
                doc.source_type = "pronunciation_guide"
            doc.source_url = doc.source_url or _source_url(file_id)
            db.commit()
            db.refresh(doc)
            return doc
        if doc.source_url and parse_drive_file_id(doc.source_url) == file_id:
            doc.drive_file_id = file_id
            doc.title = doc.title or PRONUNCIATION_TITLE
            doc.source_type = "pronunciation_guide"
            db.commit()
            db.refresh(doc)
            return doc

    doc = SourceDocument(
        title=PRONUNCIATION_TITLE,
        source_type="pronunciation_guide",
        source_url=_source_url(file_id),
        drive_file_id=file_id,
        mime_type="application/vnd.google-apps.document",
        status="ready",
        short_title="English-Woccon",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    log.info("Created pronunciation guide source document %s", doc.id)
    return doc


def scrub_base_pronunciations(db: Session) -> int:
    """Normalize stored pronunciation strings on all base vocabulary rows."""
    scrubbed = 0
    for row in db.query(CanonicalLexicon).filter(CanonicalLexicon.is_base_entry.is_(True)).all():
        clean = normalize_pronunciation(row.pronunciation)
        if clean != row.pronunciation:
            row.pronunciation = clean
            scrubbed += 1
    if scrubbed:
        db.commit()
    return scrubbed


def merge_pronunciation_into_base(db: Session, *, file_id: Optional[str] = None) -> Dict[str, int]:
    """Copy pronunciation from English-Woccon doc onto matching base vocabulary rows."""
    from panel_api.services.vocab_match import find_base_match

    settings = get_settings()
    fid = (file_id or settings.base_pronunciation_drive_id or "").strip()
    if not fid:
        return {"merged": 0, "skipped": 0, "unmatched": 0, "scrubbed": 0}

    ensure_pronunciation_document(db)
    scrubbed = scrub_base_pronunciations(db)
    entries = fetch_pronunciation_entries(fid)
    if not entries:
        return {"merged": 0, "skipped": 0, "unmatched": 0, "scrubbed": scrubbed}

    merged = 0
    skipped = 0
    unmatched = 0
    base_by_id = {
        r.id: r
        for r in db.query(CanonicalLexicon).filter(CanonicalLexicon.is_base_entry.is_(True)).all()
    }

    for e in entries:
        w = (e.get("woccon") or "").strip()
        eng = (e.get("english") or "").strip()
        pron = normalize_pronunciation((e.get("pronunciation") or "").strip())
        if not w or not pron:
            continue

        base_row = (
            db.query(CanonicalLexicon)
            .filter(
                CanonicalLexicon.is_base_entry.is_(True),
                CanonicalLexicon.woccon_normalized == normalize_woccon(w),
            )
            .first()
        )
        if not base_row:
            base_id, _, _ = find_base_match(db, w, eng)
            base_row = base_by_id.get(base_id) if base_id else None

        if not base_row:
            unmatched += 1
            continue
        if base_row.pronunciation == pron:
            skipped += 1
            continue
        base_row.pronunciation = pron
        merged += 1

    db.commit()
    log.info(
        "Pronunciation merge: merged=%d skipped=%d unmatched=%d scrubbed=%d",
        merged,
        skipped,
        unmatched,
        scrubbed,
    )
    return {"merged": merged, "skipped": skipped, "unmatched": unmatched, "scrubbed": scrubbed}


def _pick_canonical_base(rows: List[CanonicalLexicon]) -> CanonicalLexicon:
    """Definitive list winner: earliest in doc, then pronunciation, then stable id."""
    return min(
        rows,
        key=lambda r: (
            r.sort_order if r.sort_order is not None else 99999,
            0 if r.pronunciation else 1,
            r.woccon or "",
            r.id or "",
        ),
    )


def _merge_base_into_winner(
    db: Session,
    winner: CanonicalLexicon,
    loser: CanonicalLexicon,
    *,
    score: float,
    method: str,
) -> None:
    """Demote a duplicate base row to a variant linked under the canonical base."""
    if loser.id == winner.id:
        return

    for variant in (
        db.query(CanonicalLexicon)
        .filter(CanonicalLexicon.base_entry_id == loser.id)
        .all()
    ):
        variant.base_entry_id = winner.id

    if not winner.pronunciation and loser.pronunciation:
        winner.pronunciation = loser.pronunciation

    loser.is_base_entry = False
    loser.base_entry_id = winner.id
    loser.base_match_score = score
    loser.base_match_method = method


def dedupe_base_vocabulary(db: Session) -> Dict[str, int]:
    """Merge duplicate base rows that share an English gloss and similar Woccon spelling."""
    settings = get_settings()
    threshold = settings.base_vocab_dedupe_threshold
    bases = (
        db.query(CanonicalLexicon)
        .filter(CanonicalLexicon.is_base_entry.is_(True))
        .order_by(CanonicalLexicon.sort_order.nulls_last(), CanonicalLexicon.woccon)
        .all()
    )

    by_english: Dict[str, List[CanonicalLexicon]] = defaultdict(list)
    for row in bases:
        eng = normalize_text(row.english)
        if eng:
            by_english[eng].append(row)

    merged = 0
    clusters_found = 0

    for rows in by_english.values():
        if len(rows) < 2:
            continue

        parent: Dict[str, str] = {r.id: r.id for r in rows}
        row_by_id = {r.id: r for r in rows}

        def find(i: str) -> str:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for i, a in enumerate(rows):
            for b in rows[i + 1 :]:
                score, method = base_woccon_match(a.woccon, b.woccon, threshold=threshold)
                if score > 0:
                    union(a.id, b.id)

        clusters: Dict[str, List[CanonicalLexicon]] = defaultdict(list)
        for row in rows:
            clusters[find(row.id)].append(row)

        for cluster in clusters.values():
            if len(cluster) < 2:
                continue
            clusters_found += 1
            winner = _pick_canonical_base(cluster)
            for loser in cluster:
                if loser.id == winner.id:
                    continue
                score, method = base_woccon_match(winner.woccon, loser.woccon, threshold=threshold)
                _merge_base_into_winner(
                    db,
                    winner,
                    loser,
                    score=score or 1.0,
                    method=method or "woccon_fuzzy",
                )
                merged += 1

    if merged:
        db.commit()
        log.info("Base vocab dedupe: merged=%d clusters=%d", merged, clusters_found)
    return {"merged": merged, "clusters": clusters_found}


def import_base_vocab(db: Session, *, file_id: Optional[str] = None) -> Dict[str, Any]:
    settings = get_settings()
    fid = (file_id or settings.base_vocab_drive_id or "").strip()
    if not fid:
        raise ValueError("WOCCON_BASE_VOCAB_DRIVE_ID is not set")

    doc = ensure_vocab_base_document(db)
    if not doc:
        raise ValueError("Could not create vocab base document")

    doc.status = "processing"
    doc.progress_pct = 0
    doc.progress_message = "Syncing base vocabulary…"
    db.commit()

    entries = fetch_vocab_entries(fid)
    if not entries:
        doc.status = "failed"
        doc.error_message = "No vocabulary entries found"
        doc.progress_message = None
        db.commit()
        return {"imported": 0, "updated": 0, "document_id": doc.id, "error": doc.error_message}

    imported = 0
    updated = 0
    source_url = _source_url(fid)

    for i, e in enumerate(entries):
        w = (e.get("woccon") or "").strip()
        eng = (e.get("english") or "").strip()
        if not w or not eng:
            continue
        key = normalize_woccon(w)
        row = find_duplicate_base(db, w, eng)
        if row:
            row.woccon = w
            row.english = eng
            row.woccon_normalized = key
            row.pos = (e.get("pos") or row.pos or "unknown").strip()
            row.pronunciation = normalize_pronunciation(e.get("pronunciation")) or row.pronunciation
            row.source = "vocab_base"
            row.source_url = source_url
            row.source_document_id = doc.id
            row.sort_order = i
            row.is_base_entry = True
            row.base_entry_id = None
            updated += 1
        else:
            row = CanonicalLexicon(
                woccon=w,
                english=eng,
                pos=(e.get("pos") or "unknown").strip(),
                pronunciation=normalize_pronunciation(e.get("pronunciation")),
                source="vocab_base",
                source_url=source_url,
                source_document_id=doc.id,
                woccon_normalized=key,
                sort_order=i,
                is_base_entry=True,
            )
            apply_lexicon_classification(row, w, eng, row.pos, "vocab_base")
            db.add(row)
            imported += 1

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pron_stats = merge_pronunciation_into_base(db)
    dedupe_stats = dedupe_base_vocabulary(db)
    doc.status = "ready"
    doc.error_message = None
    doc.progress_pct = 100
    pron_note = ""
    if pron_stats.get("merged"):
        pron_note = f" · {pron_stats['merged']} pronunciations merged"
    if dedupe_stats.get("merged"):
        pron_note += f" · {dedupe_stats['merged']} duplicate bases merged"
    doc.progress_message = f"Synced {imported + updated} base entries{pron_note} · {now}"
    db.commit()

    return {
        "imported": imported,
        "updated": updated,
        "total": imported + updated,
        "document_id": doc.id,
        "pronunciation": pron_stats,
        "dedupe": dedupe_stats,
    }


def link_all_canonical_to_base(db: Session) -> Dict[str, int]:
    from panel_api.services.vocab_match import apply_base_link_to_canonical

    linked = 0
    skipped = 0
    for row in db.query(CanonicalLexicon).filter(CanonicalLexicon.is_base_entry.is_(False)).all():
        if row.base_entry_id:
            skipped += 1
            continue
        before = row.base_entry_id
        apply_base_link_to_canonical(row, db)
        if row.base_entry_id and row.base_entry_id != before:
            linked += 1
    db.commit()
    return {"linked": linked, "skipped": skipped}
