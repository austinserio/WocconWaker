#!/usr/bin/env python3
"""
Rules Capture Certainty audit — single dashboard artifact combining:
  - Azure live rules grouped by source document
  - Per-document Tier A/B/C topic checklist coverage
  - Opus vs Qwen full staging diff summary (if available)
  - Explicit unknowns (Tier-A gaps with no live rule and no Qwen hit)

Usage:
  python scripts/rules_capture_audit.py
  python scripts/rules_capture_audit.py --json-out data/backups/rules_capture_audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_rule_topic_coverage import (  # noqa: E402
    build_report,
    load_registry,
    resolve_document_profile,
    topic_ids_for_profile,
)
from scripts.diff_staging_runs import build_index, diff_staging_payload, summarize_counts, _load_staging_file  # noqa: E402

DEFAULT_LIVE = ROOT / "data" / "backups" / "azure_live_rules.json"
DEFAULT_REGISTRY = ROOT / "data" / "rule_topic_registry.json"
DEFAULT_DIFF = ROOT / "data" / "backups" / "full_qwen_vs_opus_diff.json"
DEFAULT_STAGING_QWEN = ROOT / "woccon_language" / "drive_staging_qwen_full"
DEFAULT_STAGING_OPUS = ROOT / "woccon_language" / "drive_staging"
NOTE_BUCKETS = ("grammar_notes", "pronunciation_notes")


def _rule_source_label(rule: Dict[str, Any]) -> str:
    citation = rule.get("citation") or {}
    return (
        citation.get("document_title")
        or rule.get("source_url")
        or "unknown"
    )


def group_live_by_source(live: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"grammar": 0, "pronunciation": 0})
    for category in ("grammar", "pronunciation"):
        for rule in live.get(category) or []:
            if not isinstance(rule, dict):
                continue
            label = _rule_source_label(rule)
            counts[label][category] += 1
    return dict(counts)


def diff_aggregate_summary(diff_path: Path) -> Optional[Dict[str, Any]]:
    if not diff_path.is_file():
        return None
    data = json.loads(diff_path.read_text(encoding="utf-8"))
    totals: Dict[str, int] = defaultdict(int)
    files = data.get("files") or {}
    for diff in files.values():
        c = summarize_counts(diff)
        for k, v in c.items():
            totals[k] += v
    return {
        "diff_path": str(diff_path),
        "old_dir": data.get("old_dir"),
        "new_dir": data.get("new_dir"),
        "files_compared": len(files),
        "only_in_old": data.get("only_in_old") or [],
        "only_in_new": data.get("only_in_new") or [],
        "totals": dict(totals),
    }


def build_staging_diff_if_missing(
    old_dir: Path,
    new_dir: Path,
    json_out: Path,
) -> Optional[Dict[str, Any]]:
    if not old_dir.is_dir() or not new_dir.is_dir():
        return None
    if json_out.is_file():
        return diff_aggregate_summary(json_out)
    old_index = build_index(old_dir, None)
    new_index = build_index(new_dir, None)
    report: Dict[str, Any] = {
        "old_dir": str(old_dir),
        "new_dir": str(new_dir),
        "files": {},
        "only_in_old": sorted(set(old_index) - set(new_index)),
        "only_in_new": sorted(set(new_index) - set(old_index)),
    }
    for name in sorted(set(old_index) & set(new_index)):
        old_data = _load_staging_file(old_index[name])
        new_data = _load_staging_file(new_index[name])
        report["files"][name] = diff_staging_payload(old_data, new_data)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return diff_aggregate_summary(json_out)


def collect_unknowns(
    registry: Dict[str, Any],
    doc_filter: str,
    live_report: Dict[str, Any],
    staging_report: Optional[Dict[str, Any]],
) -> List[str]:
    _, profile = resolve_document_profile(registry, doc_filter)
    live_tier_a_gaps = set((live_report.get("tier_a") or {}).get("gaps") or [])
    if not staging_report:
        return sorted(live_tier_a_gaps)
    qwen_covered = set((staging_report.get("tier_a") or {}).get("covered_ids") or [])
    return sorted(live_tier_a_gaps - qwen_covered)


def markdown_summary(audit: Dict[str, Any]) -> str:
    lines = [
        "# Rules Capture Audit",
        "",
        f"Generated: {audit.get('generated_at')}",
        f"Live rules: {audit.get('live_totals')}",
        "",
        "## Per-document Tier A coverage (live)",
    ]
    for doc, block in (audit.get("documents") or {}).items():
        live = block.get("live") or {}
        ta = live.get("tier_a") or {}
        lines.append(f"- **{doc}**: {ta.get('covered', 0)}/{ta.get('total', 0)} Tier A")
        gaps = ta.get("gaps") or []
        if gaps:
            lines.append(f"  - gaps: {', '.join(gaps)}")
        unknowns = block.get("unknowns") or []
        if unknowns:
            lines.append(f"  - unknowns: {', '.join(unknowns)}")
    diff = audit.get("staging_diff")
    if diff:
        lines.extend(["", "## Staging diff (Opus vs Qwen full)", f"Files compared: {diff.get('files_compared')}"])
        totals = diff.get("totals") or {}
        lines.append(
            f"Grammar: +{totals.get('grammar_notes_added', 0)} "
            f"-{totals.get('grammar_notes_removed', 0)} "
            f"~{totals.get('grammar_notes_changed', 0)}"
        )
        lines.append(
            f"Pronunciation: +{totals.get('pronunciation_notes_added', 0)} "
            f"-{totals.get('pronunciation_notes_removed', 0)} "
            f"~{totals.get('pronunciation_notes_changed', 0)}"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Rules capture certainty audit report")
    ap.add_argument("--live", type=Path, default=DEFAULT_LIVE)
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    ap.add_argument("--staging-qwen", type=Path, default=DEFAULT_STAGING_QWEN)
    ap.add_argument("--staging-opus", type=Path, default=DEFAULT_STAGING_OPUS)
    ap.add_argument("--diff", type=Path, default=DEFAULT_DIFF)
    ap.add_argument("--json-out", type=Path, default=ROOT / "data" / "backups" / "rules_capture_audit.json")
    ap.add_argument("--md-out", type=Path, default=ROOT / "data" / "backups" / "rules_capture_audit.md")
    args = ap.parse_args()

    live_path = args.live if args.live.is_absolute() else ROOT / args.live
    if not live_path.is_file():
        print(f"Live rules not found: {live_path}", file=sys.stderr)
        return 1

    live = json.loads(live_path.read_text(encoding="utf-8"))
    registry = load_registry(args.registry if args.registry.is_absolute() else ROOT / args.registry)

    staging_qwen = args.staging_qwen if args.staging_qwen.is_absolute() else ROOT / args.staging_qwen
    staging_opus = args.staging_opus if args.staging_opus.is_absolute() else ROOT / args.staging_opus
    diff_path = args.diff if args.diff.is_absolute() else ROOT / args.diff

    staging_diff = build_staging_diff_if_missing(staging_opus, staging_qwen, diff_path)

    documents: Dict[str, Any] = {}
    for doc_key in (registry.get("document_profiles") or {}):
        try:
            live_report = build_report(registry=registry, document_filter=doc_key, live=live)
        except SystemExit:
            continue
        staging_report = None
        if staging_qwen.is_dir():
            try:
                combined = build_report(
                    registry=registry,
                    document_filter=doc_key,
                    staging=staging_qwen,
                    compare_live=live,
                )
                staging_report = combined.get("staging")
                live_vs_qwen = combined.get("live_vs_qwen")
            except SystemExit:
                live_vs_qwen = None
        else:
            live_vs_qwen = None

        unknowns = collect_unknowns(
            registry,
            doc_key,
            live_report.get("live") or {},
            staging_report,
        )
        documents[doc_key] = {
            "live": live_report.get("live"),
            "staging": staging_report,
            "live_vs_qwen": live_vs_qwen,
            "unknowns": unknowns,
        }

    audit: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "live_source": live.get("base_url"),
        "live_fetched_at": live.get("fetched_at"),
        "live_totals": {
            "grammar": len(live.get("grammar") or []),
            "pronunciation": len(live.get("pronunciation") or []),
        },
        "live_by_source": group_live_by_source(live),
        "documents": documents,
        "staging_diff": staging_diff,
        "exit_criteria": {
            "tier_a_resurrecting_carter": _tier_a_status(documents, ["Resurrecting", "Carter-WocconLanguageNorth"]),
            "english_woccon_vocab": "see list_doc_parser.check_lexicon_completeness",
            "full_qwen_diff_archived": staging_diff is not None,
        },
    }

    json_out = args.json_out if args.json_out.is_absolute() else ROOT / args.json_out
    md_out = args.md_out if args.md_out.is_absolute() else ROOT / args.md_out
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    md_out.write_text(markdown_summary(audit), encoding="utf-8")

    print(markdown_summary(audit))
    print(f"Wrote {json_out}")
    print(f"Wrote {md_out}")
    return 0


def _tier_a_status(documents: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
    out = {}
    for key in keys:
        block = documents.get(key) or {}
        live = block.get("live") or {}
        ta = live.get("tier_a") or {}
        out[key] = {
            "covered": ta.get("covered"),
            "total": ta.get("total"),
            "gaps": ta.get("gaps") or [],
            "unknowns": block.get("unknowns") or [],
        }
    return out


if __name__ == "__main__":
    raise SystemExit(main())
