"""Recurrence and ablation gates for correspondence rules."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from woccon_reconstruction.scoring import segment_accuracy


def count_rule_attestations_on_train(
    train_items: List[Dict[str, Any]],
    rules: List[Dict[str, Any]],
    align_fn,
    project_fn=None,
) -> Dict[str, int]:
    """Count distinct train cognates where each rule_id is attested."""
    from collections import Counter

    counts: Counter[str] = Counter()
    train_ids = {item.get("cognate_id") for item in train_items}
    for rule in rules:
        for ex_id in rule.get("example_cognate_ids") or []:
            if ex_id in train_ids:
                counts[rule["id"]] += 1
    for item in train_items:
        w = item.get("woccon_reconstituted") or ""
        c = item.get("catawba_form") or ""
        if not w or not c:
            continue
        seen: set[str] = set()
        for seg in align_fn(w, c, rules):
            rid = seg.get("rule_id")
            if rid and rid not in seen:
                counts[rid] += 1
                seen.add(rid)
        if project_fn:
            _, used = project_fn(c, rules)
            for rid in used:
                if rid not in seen:
                    counts[rid] += 1
                    seen.add(rid)
    return dict(counts)


def apply_recurrence_gate(
    rules: List[Dict[str, Any]],
    train_counts: Dict[str, int],
    min_count: int = 2,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Return (admitted_rules, rejected_rules) by firing-count threshold."""
    admitted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for r in rules:
        rid = r.get("id", "")
        cnt = train_counts.get(rid, 0)
        if cnt >= min_count:
            admitted.append(r)
        else:
            rejected.append(
                {
                    "rule_id": rid,
                    "train_count": cnt,
                    "lhs": r.get("lhs"),
                    "rhs": r.get("rhs"),
                    "environment": r.get("environment"),
                    "reason": f"below recurrence threshold ({cnt} < {min_count})",
                }
            )
    return admitted, rejected


# Buckets the proposer actually runs sound laws on. Scoring the gate on
# `simple` alone hides rules whose only training evidence sits in compounds.
PROJECTABLE_BUCKETS = ("simple", "compound", "affixed", "reduplicated")


def _train_segment_score(
    train_items: List[Dict[str, Any]],
    rules: List[Dict[str, Any]],
    project_fn: Callable[[str, List[Dict[str, Any]]], Tuple[str, List[str]]],
    *,
    bucket: Any = PROJECTABLE_BUCKETS,
) -> float:
    from woccon_reconstruction.morphology import trim_catawba_extra_morpheme
    from woccon_reconstruction.orthography import repair_ocr

    buckets = (bucket,) if isinstance(bucket, str) else tuple(bucket)
    rows = [i for i in train_items if i.get("projectability") in buckets]
    if not rows:
        rows = train_items
    total = 0.0
    n = 0
    for item in rows:
        c = trim_catawba_extra_morpheme(
            repair_ocr(item.get("catawba_form") or ""), item.get("notes")
        )
        target = repair_ocr(item.get("woccon_reconstituted") or "")
        if not c or not target:
            continue
        pred, _ = project_fn(c, rules)
        total += segment_accuracy(pred, target)
        n += 1
    return total / n if n else 0.0


def apply_ablation_gate(
    rules: List[Dict[str, Any]],
    train_items: List[Dict[str, Any]],
    project_fn: Callable[[str, List[Dict[str, Any]]], Tuple[str, List[str]]],
    train_counts: Dict[str, int],
    *,
    min_count: int = 2,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Admit rules that pass recurrence AND are not harmful when ablated.

    Non-identity rules whose removal *increases* train segment score are rejected.
    Identity rules pass on recurrence alone.
    """
    recurrence_admitted, recurrence_rejected = apply_recurrence_gate(
        rules, train_counts, min_count=min_count
    )
    full_score = _train_segment_score(train_items, recurrence_admitted, project_fn)
    admitted: List[Dict[str, Any]] = []
    ablation_rejected: List[Dict[str, Any]] = []

    for rule in recurrence_admitted:
        lhs, rhs = rule.get("lhs"), rule.get("rhs")
        if str(lhs) == str(rhs):
            admitted.append(rule)
            continue
        reduced = [r for r in recurrence_admitted if r.get("id") != rule.get("id")]
        without = _train_segment_score(train_items, reduced, project_fn)
        if without >= full_score - 1e-9:
            ablation_rejected.append(
                {
                    "rule_id": rule.get("id"),
                    "train_count": train_counts.get(rule.get("id"), 0),
                    "lhs": lhs,
                    "rhs": rhs,
                    "environment": rule.get("environment"),
                    "reason": (
                        f"ablation neutral_or_harmful "
                        f"(without={without:.4f} >= full={full_score:.4f})"
                    ),
                    "score_with": round(full_score, 4),
                    "score_without": round(without, 4),
                }
            )
        else:
            admitted.append(rule)

    rejected = recurrence_rejected + ablation_rejected
    return admitted, rejected
