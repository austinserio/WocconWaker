#!/usr/bin/env python3
"""
Check Tier A/B/C topic coverage for grammar/pronunciation rules per document.

Inputs: staging JSON dir, single staging file, or Azure live export (fetch_azure_live_rules).
Uses keyword/affix matching from data/rule_topic_registry.json — not fuzzy string equality.

Usage:
  python scripts/check_rule_topic_coverage.py --live data/backups/azure_live_rules.json \\
      --document Resurrecting
  python scripts/check_rule_topic_coverage.py --staging woccon_language/drive_staging_qwen_validate \\
      --document Resurrecting --compare-live data/backups/azure_live_rules.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_REGISTRY = ROOT / "data" / "rule_topic_registry.json"
SKIP_FILES = {"manifest.json", "sync_state.json"}


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower().strip())


def get_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("text") or item.get("content") or ""
    return str(item)


def load_registry(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_document_profile(registry: Dict[str, Any], document_filter: str) -> Tuple[str, Dict[str, Any]]:
    profiles = registry.get("document_profiles") or {}
    needle = document_filter.lower()
    for name, profile in profiles.items():
        if needle in name.lower():
            return name, profile
        for pat in profile.get("match_patterns") or []:
            if needle in pat.lower() or pat.lower() in needle:
                return name, profile
    raise SystemExit(f"No document profile matches filter: {document_filter!r}")


def topic_ids_for_profile(profile: Dict[str, Any], tier: Optional[str] = None) -> List[str]:
    ids: List[str] = []
    for tier_key in ("tier_a", "tier_b", "tier_c"):
        tier_label = tier_key.replace("tier_", "").upper()
        if tier and tier_label != tier.upper():
            continue
        ids.extend(profile.get(tier_key) or [])
    return ids


def topic_matches(text: str, topic: Dict[str, Any]) -> bool:
    t = norm(text)
    if not t:
        return False
    for kw in topic.get("keywords") or []:
        if kw.lower() in t:
            return True
    return False


def collect_texts_from_file(path: Path) -> Tuple[List[str], List[str], Optional[str], Optional[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    grammar = [get_text(n).strip() for n in (data.get("grammar_notes") or []) if get_text(n).strip()]
    pronunciation = [get_text(n).strip() for n in (data.get("pronunciation_notes") or []) if get_text(n).strip()]
    return grammar, pronunciation, data.get("source_path"), data.get("source_url")


def rule_matches_document(rule: Dict[str, Any], document_filter: str, profile: Dict[str, Any]) -> bool:
    patterns = [document_filter] + list(profile.get("match_patterns") or [])
    citation = rule.get("citation") or {}
    haystacks = [
        rule.get("source_url") or "",
        citation.get("document_title") or "",
        citation.get("source_url") or "",
    ]
    for h in haystacks:
        hl = h.lower()
        for pat in patterns:
            if pat.lower() in hl:
                return True
    return False


def collect_live_texts(
    live: Dict[str, Any],
    document_filter: str,
    profile: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    grammar: List[str] = []
    pronunciation: List[str] = []
    for category in ("grammar", "pronunciation"):
        for rule in live.get(category) or []:
            if not isinstance(rule, dict):
                continue
            if not rule_matches_document(rule, document_filter, profile):
                continue
            text = (rule.get("content") or rule.get("text") or "").strip()
            if not text:
                continue
            if category == "grammar":
                grammar.append(text)
            else:
                pronunciation.append(text)
    return grammar, pronunciation


def texts_for_topic(
    topic: Dict[str, Any],
    grammar_texts: List[str],
    pronunciation_texts: List[str],
) -> List[str]:
    categories = topic.get("categories") or ["grammar", "pronunciation"]
    pool: List[str] = []
    if "grammar" in categories:
        pool.extend(grammar_texts)
    if "pronunciation" in categories:
        pool.extend(pronunciation_texts)
    return pool


def evaluate_coverage(
    registry: Dict[str, Any],
    profile: Dict[str, Any],
    grammar_texts: List[str],
    pronunciation_texts: List[str],
) -> Dict[str, Any]:
    topics_meta = registry.get("topics") or {}
    covered: List[str] = []
    gaps: List[str] = []
    hits: Dict[str, List[str]] = {}

    for topic_id in topic_ids_for_profile(profile):
        topic = topics_meta.get(topic_id) or {}
        pool = texts_for_topic(topic, grammar_texts, pronunciation_texts)
        matched = [t for t in pool if topic_matches(t, topic)]
        if matched:
            covered.append(topic_id)
            hits[topic_id] = matched[:3]
        else:
            gaps.append(topic_id)

    def tier_summary(tier_key: str) -> Dict[str, Any]:
        ids = profile.get(tier_key) or []
        tier_covered = [i for i in ids if i in covered]
        tier_gaps = [i for i in ids if i in gaps]
        return {
            "covered": len(tier_covered),
            "total": len(ids),
            "gaps": tier_gaps,
            "covered_ids": tier_covered,
        }

    return {
        "tier_a": tier_summary("tier_a"),
        "tier_b": tier_summary("tier_b"),
        "tier_c": tier_summary("tier_c"),
        "hits": hits,
        "grammar_note_count": len(grammar_texts),
        "pronunciation_note_count": len(pronunciation_texts),
    }


def compare_topic_presence(
    registry: Dict[str, Any],
    profile: Dict[str, Any],
    live_grammar: List[str],
    live_pron: List[str],
    qwen_grammar: List[str],
    qwen_pron: List[str],
) -> Dict[str, Any]:
    topics_meta = registry.get("topics") or {}
    live_only: List[str] = []
    qwen_only: List[str] = []
    both: List[str] = []

    for topic_id in topic_ids_for_profile(profile):
        topic = topics_meta.get(topic_id) or {}
        live_pool = texts_for_topic(topic, live_grammar, live_pron)
        qwen_pool = texts_for_topic(topic, qwen_grammar, qwen_pron)
        in_live = any(topic_matches(t, topic) for t in live_pool)
        in_qwen = any(topic_matches(t, topic) for t in qwen_pool)
        if in_live and in_qwen:
            both.append(topic_id)
        elif in_live:
            live_only.append(topic_id)
        elif in_qwen:
            qwen_only.append(topic_id)

    return {"live_only": live_only, "qwen_only": qwen_only, "both": both}


def find_staging_files(staging: Path, document_filter: str, profile: Dict[str, Any]) -> List[Path]:
    if staging.is_file():
        return [staging]
    needle = document_filter.lower()
    paths: List[Path] = []
    patterns = [document_filter] + list(profile.get("match_patterns") or [])
    for p in sorted(staging.rglob("*.json")):
        if p.name in SKIP_FILES:
            continue
        if any(pat.lower() in p.stem.lower() for pat in patterns):
            paths.append(p)
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        sp = (data.get("source_path") or "").lower()
        if any(pat.lower() in sp for pat in patterns):
            paths.append(p)
    return paths


def build_report(
    *,
    registry: Dict[str, Any],
    document_filter: str,
    staging: Optional[Path] = None,
    live: Optional[Dict[str, Any]] = None,
    compare_live: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    doc_name, profile = resolve_document_profile(registry, document_filter)
    report: Dict[str, Any] = {"document": doc_name, "document_filter": document_filter}

    live_grammar: List[str] = []
    live_pron: List[str] = []
    if live:
        live_grammar, live_pron = collect_live_texts(live, document_filter, profile)
        report["live"] = evaluate_coverage(registry, profile, live_grammar, live_pron)
        report["live"]["source"] = live.get("base_url")

    qwen_grammar: List[str] = []
    qwen_pron: List[str] = []
    if staging:
        if staging.is_dir():
            files = find_staging_files(staging, document_filter, profile)
            for fp in files:
                g, pr, _, _ = collect_texts_from_file(fp)
                qwen_grammar.extend(g)
                qwen_pron.extend(pr)
        else:
            g, pr, _, _ = collect_texts_from_file(staging)
            qwen_grammar.extend(g)
            qwen_pron.extend(pr)
        report["staging"] = evaluate_coverage(registry, profile, qwen_grammar, qwen_pron)
        report["staging"]["path"] = str(staging)

    if compare_live or live:
        live_src = compare_live or live
        assert live_src is not None
        lg, lp = collect_live_texts(live_src, document_filter, profile)
        report["live_vs_qwen"] = compare_topic_presence(registry, profile, lg, lp, qwen_grammar, qwen_pron)

    return report


def print_summary(report: Dict[str, Any]) -> None:
    print(f"\n=== {report.get('document')} ===")
    for key in ("live", "staging"):
        block = report.get(key)
        if not block:
            continue
        print(f"  [{key}] grammar={block.get('grammar_note_count')} pronunciation={block.get('pronunciation_note_count')}")
        for tier in ("tier_a", "tier_b", "tier_c"):
            t = block.get(tier) or {}
            print(f"    {tier}: {t.get('covered', 0)}/{t.get('total', 0)} covered")
            gaps = t.get("gaps") or []
            if gaps:
                print(f"      gaps: {', '.join(gaps)}")
    lvq = report.get("live_vs_qwen")
    if lvq:
        print(
            f"  live_vs_qwen: both={len(lvq.get('both', []))} "
            f"live_only={len(lvq.get('live_only', []))} qwen_only={len(lvq.get('qwen_only', []))}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Rule topic checklist coverage per document")
    ap.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    ap.add_argument("--document", required=True, help="Document filter (e.g. Resurrecting, Carter)")
    ap.add_argument("--staging", type=Path, help="Staging dir or JSON file (Qwen/Opus extract)")
    ap.add_argument("--live", type=Path, help="Azure live export JSON")
    ap.add_argument("--compare-live", type=Path, help="Live export for live_vs_qwen (defaults to --live)")
    ap.add_argument("--json-out", type=Path, help="Write report JSON")
    args = ap.parse_args()

    registry = load_registry(args.registry if args.registry.is_absolute() else ROOT / args.registry)
    live_data = None
    if args.live:
        live_path = args.live if args.live.is_absolute() else ROOT / args.live
        live_data = json.loads(live_path.read_text(encoding="utf-8"))

    compare_live = None
    if args.compare_live:
        cp = args.compare_live if args.compare_live.is_absolute() else ROOT / args.compare_live
        compare_live = json.loads(cp.read_text(encoding="utf-8"))

    staging = None
    if args.staging:
        staging = args.staging if args.staging.is_absolute() else ROOT / args.staging

    if not staging and not live_data:
        ap.error("Provide --staging and/or --live")

    report = build_report(
        registry=registry,
        document_filter=args.document,
        staging=staging,
        live=live_data,
        compare_live=compare_live,
    )

    print_summary(report)
    if args.json_out:
        out = args.json_out if args.json_out.is_absolute() else ROOT / args.json_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
