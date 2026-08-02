#!/usr/bin/env python3
"""Run Lawson holdout evaluation with tiered scoring and rule-generality audit."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from woccon_reconstruction.alignment import align_pair  # noqa: E402
from woccon_reconstruction.comparative_utils import (  # noqa: E402
    DEFAULT_REGISTRY,
    load_registry,
    registry_rules,
)
from woccon_reconstruction.morphology import (  # noqa: E402
    project_compound,
    project_reduplicated,
    trim_catawba_extra_morpheme,
)
from woccon_reconstruction.orthography import repair_ocr  # noqa: E402
from woccon_reconstruction.proposer import (  # noqa: E402
    filter_rules_by_recurrence,
    project_c_to_w,
    project_c_to_w_nbest,
)
from woccon_reconstruction.recurrence import _train_segment_score  # noqa: E402
from woccon_reconstruction.scoring import (  # noqa: E402
    SMALL_SAMPLE_THRESHOLD,
    ablation_table,
    aggregate_metrics,
    rule_generality_audit,
    score_row_with_baseline,
)

DEFAULT_SPLIT = ROOT / "data/lawson_holdout_split.json"
DEFAULT_OUT = ROOT / "data/holdout_report.json"


def _eval_ids(split: Dict[str, Any], split_name: str) -> Set[str]:
    if split_name == "train":
        return set(split.get("train_ids") or [])
    if split_name == "dev":
        return set(split.get("dev_ids") or split.get("holdout_ids") or [])
    if split_name == "test":
        return set(split.get("test_ids") or split.get("holdout_ids") or [])
    return set(split.get("holdout_ids") or split.get("test_ids") or [])


def _project_item(
    item: Dict[str, Any],
    rules: List[Dict[str, Any]],
) -> Dict[str, Any]:
    raw_c_form = repair_ocr(item.get("catawba_form") or "")
    target = repair_ocr(item.get("woccon_reconstituted") or item.get("lawson_attested") or "")
    bucket = item.get("projectability") or "simple"
    notes = item.get("notes")
    # Rudes flags trailing Catawba morphemes absent from the Woccon cognate.
    c_form = trim_catawba_extra_morpheme(raw_c_form, notes)

    def _proj(cf: str):
        r = project_c_to_w_nbest(cf, rules, n_best=3)
        return r.candidates[0] if r.candidates else cf, r.rules_used

    if bucket == "compound":
        predicted, rules_used, strategy = project_compound(c_form, target, notes, _proj)
        nbest = [predicted]
    elif bucket == "reduplicated":
        predicted, rules_used, strategy = project_reduplicated(c_form, target, _proj)
        nbest = [predicted]
    elif bucket in ("corrupt", "fragment", "broken"):
        predicted, rules_used, strategy = c_form, [], bucket
        nbest = [c_form]
    else:
        result = project_c_to_w_nbest(c_form, rules, n_best=3)
        predicted = result.candidates[0] if result.candidates else c_form
        rules_used = result.rules_used
        strategy = "simple"
        nbest = result.candidates

    tier = score_row_with_baseline(predicted, target, copy_source=c_form)
    return {
        "cognate_id": item.get("cognate_id"),
        "gloss": item.get("gloss"),
        "catawba_form": c_form,
        "catawba_form_raw": raw_c_form,
        "target": target,
        "predicted": predicted,
        "baseline_prediction": c_form,
        "candidates": nbest,
        "score": tier["label"],
        "tier": tier,
        "rules_used": rules_used,
        "projectability": bucket,
        "strategy": strategy,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--eval-split",
        choices=("dev", "test", "train"),
        default="dev",
        help="Which partition to score (test requires --final)",
    )
    parser.add_argument(
        "--final",
        action="store_true",
        help="Allow scoring locked test set (records checksum)",
    )
    parser.add_argument(
        "--min-recurrence",
        type=int,
        default=1,
        help="Firing-count precondition; the ablation gate does the real filtering",
    )
    parser.add_argument(
        "--no-ablation-gate",
        action="store_true",
        help="Use recurrence-only gate (debug)",
    )
    args = parser.parse_args()

    split = json.loads(args.split.read_text(encoding="utf-8"))
    if args.eval_split == "test" and not args.final:
        print(
            "ERROR: scoring test split requires --final (locked test set)",
            file=sys.stderr,
        )
        return 1

    registry = load_registry(args.registry)
    all_rules = registry_rules(registry)
    items = {r["cognate_id"]: r for r in split.get("items") or []}
    train_ids = set(split.get("train_ids") or [])
    train_items = [items[i] for i in train_ids if i in items]

    admitted, rejected, train_counts = filter_rules_by_recurrence(
        all_rules,
        train_items,
        align_pair,
        min_count=args.min_recurrence,
        use_ablation=not args.no_ablation_gate,
    )

    def _score_train(rows: List[Dict[str, Any]], rules: List[Dict[str, Any]]) -> float:
        return _train_segment_score(rows, rules, project_c_to_w)

    rule_ablation, train_seg_full = ablation_table(
        admitted,
        train_items,
        _score_train,
        train_counts=train_counts,
    )

    eval_ids = _eval_ids(split, args.eval_split)
    results: List[Dict[str, Any]] = []
    rule_hits: Counter[str] = Counter()
    rule_misses: Counter[str] = Counter()

    for cid in sorted(eval_ids):
        item = items.get(cid)
        if not item:
            continue
        row = _project_item(item, admitted)
        results.append(row)
        for rid in row.get("rules_used") or []:
            if row["tier"]["label"] in ("exact", "partial"):
                rule_hits[rid] += 1
            else:
                rule_misses[rid] += 1

    metrics_all = aggregate_metrics(results)
    metrics_simple = aggregate_metrics(results, bucket="simple", headline=True)
    by_bucket = {
        b: aggregate_metrics(results, bucket=b)
        for b in sorted({r.get("projectability") for r in results})
    }

    headline = metrics_simple if metrics_simple.get("headline_eligible") else metrics_all
    gate_threshold = 0.05
    value_added = headline.get("value_added_segment", 0.0)
    gate_pass = value_added >= gate_threshold and headline.get("count", 0) >= SMALL_SAMPLE_THRESHOLD

    generality = rule_generality_audit(results, train_counts, rejected)

    per_rule: List[Dict[str, Any]] = []
    for rid in sorted(set(rule_hits) | set(rule_misses)):
        per_rule.append(
            {
                "rule_id": rid,
                "train_count": train_counts.get(rid, 0),
                "hits": rule_hits[rid],
                "misses": rule_misses[rid],
            }
        )

    report = {
        "version": 3,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "eval_split": args.eval_split,
        "final_run": args.final,
        "test_checksum": split.get("test_checksum"),
        "eval_size": len(results),
        "rules_admitted": len(admitted),
        "rules_rejected": len(rejected),
        "train_segment_score": round(train_seg_full, 4),
        "rule_ablation": rule_ablation,
        "metrics": {
            **metrics_all,
            "headline": headline,
            "gate_threshold_value_added_segment": gate_threshold,
            "gate_pass_value_added": gate_pass,
        },
        "metrics_by_bucket": by_bucket,
        "metrics_simple": metrics_simple,
        "rule_generality": generality,
        "per_rule": per_rule,
        "results": results,
        "documented_failure_example": next(
            (r for r in results if r["tier"]["label"] == "miss" and r.get("projectability") == "simple"),
            next((r for r in results if r["tier"]["label"] == "miss"), None),
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
    print(
        f"Eval={args.eval_split} n={len(results)} "
        f"seg={headline.get('segment_accuracy', 0):.1%} "
        f"baseline={headline.get('baseline_segment_accuracy', 0):.1%} "
        f"value_added={value_added:+.1%} "
        f"whole_exact={headline.get('accuracy_exact', 0):.1%} "
        f"gate={'PASS' if gate_pass else 'FAIL'} "
        f"rules={len(admitted)}/{len(all_rules)}"
    )
    print(f"  rows changed by rules: {headline.get('rows_changed_by_rules', 0)}/{headline.get('count', 0)}")
    if headline.get("no_rule_applicable_warning"):
        print(f"  NOTE: {headline['no_rule_applicable_warning']}")
    d_n = headline.get("discriminative_count", 0)
    if d_n:
        print(
            f"  discriminative subset (copy imperfect): n={d_n} "
            f"seg={headline.get('discriminative_segment_accuracy', 0):.1%} "
            f"baseline={headline.get('discriminative_baseline_segment_accuracy', 0):.1%} "
            f"value_added={headline.get('discriminative_value_added', 0):+.1%}"
        )
    else:
        print("  discriminative subset: 0 rows — copy is already perfect, no rule signal measurable")
    if metrics_simple.get("small_sample_warning"):
        print(f"WARNING: {metrics_simple['small_sample_warning']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
