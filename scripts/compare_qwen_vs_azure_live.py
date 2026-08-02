#!/usr/bin/env python3
"""Compare fresh Qwen Resurrecting extracts against Azure live canonical rules."""
from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_FILTER = "Resurrecting"


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").lower().strip())


def get_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("text") or item.get("content") or ""
    return str(item)


def best_ratio(a: str, corpus: List[str]) -> float:
    if not corpus:
        return 0.0
    return max(SequenceMatcher(None, norm(a)[:500], norm(c)[:500]).ratio() for c in corpus)


def _matches_source_filter(text: str, source_filter: str) -> bool:
    if not source_filter:
        return True
    return source_filter.lower() in (text or "").lower()


def load_staging_paths(base: Path, source_filter: str) -> List[Path]:
    paths: List[Path] = []
    if not base.is_dir():
        return paths
    for sub in sorted(base.iterdir()):
        if not sub.is_dir():
            continue
        for p in sub.glob("*.json"):
            if _matches_source_filter(p.name, source_filter):
                paths.append(p)
    if not paths:
        for p in base.rglob("*.json"):
            if p.name in {"manifest.json", "sync_state.json"}:
                continue
            if _matches_source_filter(p.name, source_filter):
                paths.append(p)
            else:
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    sp = data.get("source_path") or ""
                    if _matches_source_filter(sp, source_filter):
                        paths.append(p)
                except (json.JSONDecodeError, OSError):
                    pass
    return paths


def _live_rule_matches_source(rule: dict, source_filter: str) -> bool:
    if not source_filter:
        return True
    citation = rule.get("citation") or {}
    for field in (
        rule.get("source_url") or "",
        citation.get("document_title") or "",
        citation.get("source_url") or "",
        rule.get("content") or "",
    ):
        if _matches_source_filter(field, source_filter):
            return True
    return False


def merge_qwen_notes(staging_base: Path, source_filter: str) -> Dict[str, List[str]]:
    merged: Dict[str, List[str]] = {"grammar": [], "pronunciation": []}
    seen: Dict[str, set] = {"grammar": set(), "pronunciation": set()}
    for path in load_staging_paths(staging_base, source_filter):
        data = json.loads(path.read_text(encoding="utf-8"))
        for bucket, key in (("grammar_notes", "grammar"), ("pronunciation_notes", "pronunciation")):
            for note in data.get(bucket) or []:
                t = get_text(note).strip()
                nk = norm(t)
                if not nk or nk in seen[key]:
                    continue
                seen[key].add(nk)
                merged[key].append(t)
    return merged


def live_texts(live: dict, category: str, source_filter: str = "") -> List[str]:
    rows = live.get(category) or []
    out = []
    for row in rows:
        if isinstance(row, dict):
            if source_filter and not _live_rule_matches_source(row, source_filter):
                continue
            out.append((row.get("content") or row.get("text") or "").strip())
        else:
            out.append(str(row).strip())
    return [t for t in out if t]


def gap_report(live_texts_list: List[str], qwen_texts: List[str], thresh: float = 0.60) -> Dict[str, Any]:
    missing_in_qwen = []
    for lt in live_texts_list:
        r = best_ratio(lt, qwen_texts)
        if r < thresh:
            missing_in_qwen.append({"text": lt, "best_ratio": round(r, 3)})
    new_in_qwen = []
    for qt in qwen_texts:
        r = best_ratio(qt, live_texts_list)
        if r < thresh:
            new_in_qwen.append({"text": qt, "best_ratio": round(r, 3)})
    matched = len(live_texts_list) - len(missing_in_qwen)
    return {
        "live_count": len(live_texts_list),
        "qwen_count": len(qwen_texts),
        "matched_live_at_threshold": matched,
        "missing_in_qwen_count": len(missing_in_qwen),
        "new_in_qwen_count": len(new_in_qwen),
        "missing_in_qwen": missing_in_qwen,
        "new_in_qwen": new_in_qwen,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", default=str(ROOT / "data/backups/azure_live_rules.json"))
    ap.add_argument("--staging", default=str(ROOT / "woccon_language/drive_staging_qwen_validate"))
    ap.add_argument("--out", default=str(ROOT / "data/backups/qwen_vs_azure_live_gaps.json"))
    ap.add_argument("--threshold", type=float, default=0.60)
    ap.add_argument(
        "--source-filter",
        default=DEFAULT_SOURCE_FILTER,
        help="Scope live rules and staging files to documents matching this substring (e.g. Carter, Rudes)",
    )
    args = ap.parse_args()

    live = json.loads(Path(args.live).read_text(encoding="utf-8"))
    qwen = merge_qwen_notes(Path(args.staging), args.source_filter)

    report = {
        "live_source": live.get("base_url"),
        "live_fetched_at": live.get("fetched_at"),
        "staging_base": args.staging,
        "source_filter": args.source_filter,
        "threshold": args.threshold,
        "grammar": gap_report(
            live_texts(live, "grammar", args.source_filter),
            qwen["grammar"],
            args.threshold,
        ),
        "pronunciation": gap_report(
            live_texts(live, "pronunciation", args.source_filter),
            qwen["pronunciation"],
            args.threshold,
        ),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Grammar: live={report['grammar']['live_count']} qwen={report['grammar']['qwen_count']} "
          f"matched={report['grammar']['matched_live_at_threshold']} "
          f"missing_in_qwen={report['grammar']['missing_in_qwen_count']} "
          f"new_in_qwen={report['grammar']['new_in_qwen_count']}")
    print(f"Pronunciation: live={report['pronunciation']['live_count']} qwen={report['pronunciation']['qwen_count']} "
          f"matched={report['pronunciation']['matched_live_at_threshold']} "
          f"missing_in_qwen={report['pronunciation']['missing_in_qwen_count']} "
          f"new_in_qwen={report['pronunciation']['new_in_qwen_count']}")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
