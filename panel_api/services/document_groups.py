"""Known alternate scans of the same scholarly work — unified in the library."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from panel_api.db import SourceDocument


@dataclass(frozen=True)
class WorkGroup:
    key: str
    label: str
    primary_drive_file_ids: tuple[str, ...] = ()
    member_drive_file_ids: tuple[str, ...] = ()
    title_patterns: tuple[str, ...] = ()
    sort_priority: int = 0


WORK_GROUPS: tuple[WorkGroup, ...] = (
    WorkGroup(
        key="carter-1980",
        label="Carter (1980) — Woccon Language of North Carolina",
        primary_drive_file_ids=(
            "1QieCrXYLhuui2BpCyOzURsSllS28d3zV",
            "10Sg53_D1mTjwBt-ZLkL9wb3mgbIShcVUmtfqdlvsjTA",
        ),
        member_drive_file_ids=(
            "1QieCrXYLhuui2BpCyOzURsSllS28d3zV",
            "10Sg53_D1mTjwBt-ZLkL9wb3mgbIShcVUmtfqdlvsjTA",
            "1709qKAVgUD1opM8tIhdAO9LiR6F5CNnC",
            "1SHgTiE2opMYW0amfBBI5Fst1Zdmb7WeMPdWJ49n6YuY",
        ),
        title_patterns=(
            r"carter.*woccon.*1980",
            r"wocconlanguagenorth.*1980",
            r"^woccon by carter",
        ),
        sort_priority=1,
    ),
)

_COMPILED: dict[str, tuple[re.Pattern[str], ...]] = {
    g.key: tuple(re.compile(p, re.I) for p in g.title_patterns) for g in WORK_GROUPS
}


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def work_group_for_document(doc: SourceDocument) -> Optional[WorkGroup]:
    if doc.is_vocab_base or doc.is_seed:
        return None
    drive_id = (doc.drive_file_id or "").strip()
    title = _norm_title(doc.title or "")
    for group in WORK_GROUPS:
        if drive_id and drive_id in group.member_drive_file_ids:
            return group
        for pat in _COMPILED[group.key]:
            if pat.search(title):
                return group
    return None


def _primary_score(doc: SourceDocument, group: WorkGroup) -> tuple:
    drive_id = (doc.drive_file_id or "").strip()
    is_primary_drive = drive_id in group.primary_drive_file_ids
    has_1980 = "1980" in (doc.title or "") or doc.year == "1980"
    status_rank = {"ready": 3, "processing": 2, "failed": 1}.get(doc.status or "", 0)
    created = doc.created_at.timestamp() if doc.created_at else 0
    return (is_primary_drive, has_1980, status_rank, created)


def pick_primary_document(docs: list[SourceDocument], group: WorkGroup) -> SourceDocument:
    return max(docs, key=lambda d: _primary_score(d, group))


def merge_extraction_counts(counts_list: list[Optional[dict]]) -> Optional[dict]:
    merged_extracted: dict[str, int] = {}
    variants_linked = 0
    has_variants = False
    for counts in counts_list:
        if not counts:
            continue
        extracted = counts.get("extracted") or {}
        for key, val in extracted.items():
            merged_extracted[key] = merged_extracted.get(key, 0) + int(val or 0)
        if counts.get("variants_linked"):
            has_variants = True
            variants_linked += int(counts["variants_linked"])
    if not merged_extracted and not has_variants:
        return None
    out: dict = {"extracted": merged_extracted or {}}
    if has_variants:
        out["variants_linked"] = variants_linked
    return out
