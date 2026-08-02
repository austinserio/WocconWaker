"""Import cognate sets and correspondence rules from JSON seeds into panel DB."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from panel_api.db import CanonicalLexicon, CognateRuleExample, CognateSet, CorrespondenceRule
from woccon_reconstruction.comparative_utils import (
    DEFAULT_ALIGNMENTS,
    DEFAULT_COGNATES,
    DEFAULT_REGISTRY,
    effective_lawson,
    load_alignments,
    load_cognate_sets,
    load_registry,
    norm_form,
    registry_rules,
)

ROOT = Path(__file__).resolve().parents[2]


def _link_lexicon_id(db: Session, row: Dict[str, Any]) -> Optional[str]:
    """Best-effort link to canonical_lexicon by Lawson or reconstituted form."""
    candidates: List[str] = []
    lawson = effective_lawson(row)
    if lawson:
        candidates.append(norm_form(lawson))
    wrec = row.get("woccon_reconstituted")
    if wrec:
        candidates.append(norm_form(wrec))
    if not candidates:
        return None
    for key in candidates:
        if not key:
            continue
        hit = (
            db.query(CanonicalLexicon)
            .filter(CanonicalLexicon.woccon_normalized == key)
            .first()
        )
        if hit:
            return hit.id
    gloss = (row.get("gloss") or "").strip().lower()
    if gloss:
        hit = (
            db.query(CanonicalLexicon)
            .filter(CanonicalLexicon.english.ilike(f"%{gloss}%"))
            .first()
        )
        if hit:
            return hit.id
    return None


def import_cognates(
    db: Session,
    *,
    cognates_path: Path = DEFAULT_COGNATES,
    alignments_path: Path = DEFAULT_ALIGNMENTS,
    link_lexicon: bool = True,
) -> Dict[str, Any]:
    sets = load_cognate_sets(cognates_path)
    align_data = load_alignments(alignments_path)
    align_by_id = {a["cognate_id"]: a for a in align_data.get("alignments") or []}

    db.query(CognateRuleExample).delete()
    db.query(CognateSet).delete()
    db.flush()

    linked = 0
    examples_written = 0
    for row in sets:
        lex_id = _link_lexicon_id(db, row) if link_lexicon else None
        if lex_id:
            linked += 1
        db.add(
            CognateSet(
                id=row["id"],
                gloss=row.get("gloss") or "",
                lawson_form=row.get("lawson_form"),
                lawson_form_corrected=row.get("lawson_form_corrected"),
                lawson_gloss=row.get("lawson_gloss"),
                woccon_reconstituted=row.get("woccon_reconstituted"),
                catawba_form=row.get("catawba_form"),
                catawba_dialect=row.get("catawba_dialect"),
                proto_siouan=row.get("proto_siouan"),
                evidence_tier=row.get("evidence_tier") or "unknown",
                rudes_appendix=int(row.get("rudes_appendix") or 0),
                rudes_item=int(row.get("rudes_item") or 0),
                citation_short=row.get("citation_short"),
                source_path=row.get("source_path"),
                source_url=row.get("source_url"),
                notes=row.get("notes"),
                canonical_lexicon_id=lex_id,
            )
        )

    db.flush()

    rule_spans: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for cid, align_row in align_by_id.items():
        for seg in align_row.get("alignments") or []:
            rid = seg.get("rule_id")
            if not rid:
                continue
            rule_spans[(cid, rid)].append(seg)

    for (cid, rid), spans in rule_spans.items():
        if not db.get(CognateSet, cid) or not db.get(CorrespondenceRule, rid):
            continue
        db.add(
            CognateRuleExample(
                cognate_set_id=cid,
                correspondence_rule_id=rid,
                alignment_json=json.dumps(spans, ensure_ascii=False),
            )
        )
        examples_written += 1

    db.flush()
    return {
        "cognates_imported": len(sets),
        "lexicon_linked": linked,
        "rule_examples": examples_written,
        "alignments_source": str(alignments_path),
    }


def import_correspondences(
    db: Session,
    *,
    registry_path: Path = DEFAULT_REGISTRY,
) -> Dict[str, Any]:
    envelope = load_registry(registry_path)
    rules = registry_rules(envelope)

    db.query(CognateRuleExample).delete()
    db.query(CorrespondenceRule).delete()
    db.flush()

    for rule in rules:
        db.add(
            CorrespondenceRule(
                id=rule["id"],
                rule_kind=rule.get("rule_kind") or "orthographic",
                lhs=rule.get("lhs"),
                rhs=rule.get("rhs"),
                environment=rule.get("environment"),
                direction=rule.get("direction"),
                correspondence_status=rule.get("correspondence_status") or "singleton",
                grammar_lineage=rule.get("grammar_lineage"),
                source=rule.get("source") or "",
                notes=rule.get("notes"),
                provenance_text=rule.get("provenance_text"),
            )
        )

    db.flush()
    return {
        "rules_imported": len(rules),
        "registry_version": envelope.get("version"),
        "registry_source": str(registry_path),
    }


def import_comparative_all(
    db: Session,
    *,
    cognates_path: Path = DEFAULT_COGNATES,
    alignments_path: Path = DEFAULT_ALIGNMENTS,
    registry_path: Path = DEFAULT_REGISTRY,
    link_lexicon: bool = True,
) -> Dict[str, Any]:
    """Import registry first, then cognates + alignment examples."""
    reg = import_correspondences(db, registry_path=registry_path)
    cog = import_cognates(
        db,
        cognates_path=cognates_path,
        alignments_path=alignments_path,
        link_lexicon=link_lexicon,
    )
    return {"correspondences": reg, "cognates": cog}
