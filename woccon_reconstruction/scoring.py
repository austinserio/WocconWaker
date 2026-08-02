"""Tiered holdout scoring and rule-generality audit."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from woccon_reconstruction.orthography import (
    edit_distance,
    normalize_for_scoring,
    normalize_strict,
    normalized_similarity,
)

SMALL_SAMPLE_THRESHOLD = 15


def score_exact_normalized(predicted: str, target: str) -> bool:
    return normalize_for_scoring(predicted) == normalize_for_scoring(target)


def score_exact_strict(predicted: str, target: str) -> bool:
    return normalize_strict(predicted) == normalize_strict(target)


def score_partial_prefix(predicted: str, target: str, threshold: float = 0.6) -> bool:
    p, t = normalize_for_scoring(predicted), normalize_for_scoring(target)
    if not p or not t:
        return False
    shared = 0
    for a, b in zip(p, t):
        if a == b:
            shared += 1
        else:
            break
    return shared >= max(1, int(threshold * min(len(p), len(t))))


def tiered_score(predicted: str, target: str) -> Dict[str, Any]:
    exact_norm = score_exact_normalized(predicted, target)
    exact_strict = score_exact_strict(predicted, target)
    partial = score_partial_prefix(predicted, target)
    sim = normalized_similarity(predicted, target)
    if exact_norm:
        label = "exact"
    elif partial:
        label = "partial"
    else:
        label = "miss"
    return {
        "label": label,
        "exact_normalized": exact_norm,
        "exact_strict": exact_strict,
        "partial_prefix": partial,
        "similarity": round(sim, 4),
        "edit_distance": edit_distance(predicted, target),
    }


def score_nbest(candidates: List[str], target: str) -> Dict[str, Any]:
    """Score top-k candidate list; report best label and rank of first exact."""
    best = {"label": "miss", "exact_normalized": False, "similarity": 0.0, "rank": None}
    for i, pred in enumerate(candidates):
        tier = tiered_score(pred, target)
        if tier["exact_normalized"]:
            return {**tier, "rank": i + 1, "top3_hit": i < 3}
        if tier["similarity"] > best["similarity"]:
            best = {**tier, "rank": i + 1}
    best["top3_hit"] = any(
        score_exact_normalized(c, target) for c in candidates[:3]
    )
    return best


def segment_counts(predicted: str, target: str) -> Tuple[int, int, int]:
    """
    Return (correct_chars, target_len, predicted_len) on normalized strings.

    Uses target-length edit distance so partial consonant progress is visible.
    """
    p = normalize_for_scoring(predicted)
    t = normalize_for_scoring(target)
    if not t:
        return 0, 0, len(p)
    dist = edit_distance(p, t)
    correct = max(0, len(t) - dist)
    return correct, len(t), len(p)


def segment_accuracy(predicted: str, target: str) -> float:
    correct, t_len, _ = segment_counts(predicted, target)
    if t_len == 0:
        return 0.0
    return correct / t_len


def segment_precision_recall(predicted: str, target: str) -> Tuple[float, float]:
    """Character-level P/R treating alignment as edit-distance overlap."""
    correct, t_len, p_len = segment_counts(predicted, target)
    recall = correct / t_len if t_len else 0.0
    precision = correct / p_len if p_len else 0.0
    return round(precision, 4), round(recall, 4)


def score_row_with_baseline(
    predicted: str,
    target: str,
    *,
    copy_source: Optional[str] = None,
) -> Dict[str, Any]:
    """Tiered score plus copy baseline and value-added segment delta."""
    tier = tiered_score(predicted, target)
    baseline_source = copy_source if copy_source is not None else predicted
    seg_sys = segment_accuracy(predicted, target)
    seg_base = segment_accuracy(baseline_source, target) if copy_source is not None else seg_sys
    prec, rec = segment_precision_recall(predicted, target)
    whole_base = score_exact_normalized(baseline_source, target) if copy_source is not None else tier["exact_normalized"]
    return {
        **tier,
        "segment_accuracy": round(seg_sys, 4),
        "segment_precision": prec,
        "segment_recall": rec,
        "baseline_segment_accuracy": round(seg_base, 4),
        "value_added_segment": round(seg_sys - seg_base, 4),
        "baseline_whole_exact": whole_base,
        "value_added_whole_exact": int(tier["exact_normalized"]) - int(whole_base),
    }


def aggregate_metrics(
    results: List[Dict[str, Any]],
    bucket: Optional[str] = None,
    *,
    headline: bool = False,
) -> Dict[str, Any]:
    rows = results if bucket is None else [r for r in results if r.get("projectability") == bucket]
    if not rows:
        return {"count": 0}

    exact = sum(1 for r in rows if (r.get("tier") or {}).get("exact_normalized"))
    strict = sum(1 for r in rows if (r.get("tier") or {}).get("exact_strict"))
    partial = sum(1 for r in rows if (r.get("tier") or {}).get("label") == "partial")
    miss = sum(1 for r in rows if (r.get("tier") or {}).get("label") == "miss")
    top3 = sum(1 for r in rows if (r.get("tier") or {}).get("top3_hit"))
    sims = [(r.get("tier") or {}).get("similarity", 0) for r in rows]

    seg_correct = seg_target = 0
    base_seg_correct = base_seg_target = 0
    seg_precisions: List[float] = []
    seg_recalls: List[float] = []
    value_added_seg: List[float] = []

    for r in rows:
        tier = r.get("tier") or {}
        c, t_len, _ = segment_counts(r.get("predicted", ""), r.get("target", ""))
        seg_correct += c
        seg_target += t_len
        bc, bt_len, _ = segment_counts(r.get("baseline_prediction", r.get("catawba_form", "")), r.get("target", ""))
        base_seg_correct += bc
        base_seg_target += bt_len
        if tier.get("segment_precision") is not None:
            seg_precisions.append(tier["segment_precision"])
            seg_recalls.append(tier["segment_recall"])
        if tier.get("value_added_segment") is not None:
            value_added_seg.append(tier["value_added_segment"])

    n = len(rows)
    seg_acc = seg_correct / seg_target if seg_target else 0.0
    base_seg_acc = base_seg_correct / base_seg_target if base_seg_target else 0.0

    out: Dict[str, Any] = {
        "count": n,
        "exact_normalized": exact,
        "exact_strict": strict,
        "partial": partial,
        "miss": miss,
        "accuracy_exact": round(exact / n, 4),
        "accuracy_exact_partial": round((exact + partial) / n, 4),
        "top3_accuracy": round(top3 / n, 4)
        if any((r.get("tier") or {}).get("top3_hit") is not None for r in rows)
        else None,
        "mean_similarity": round(sum(sims) / n, 4),
        "segment_accuracy": round(seg_acc, 4),
        "segment_precision_mean": round(sum(seg_precisions) / len(seg_precisions), 4)
        if seg_precisions
        else round(seg_acc, 4),
        "segment_recall_mean": round(sum(seg_recalls) / len(seg_recalls), 4)
        if seg_recalls
        else round(seg_acc, 4),
        "baseline_segment_accuracy": round(base_seg_acc, 4),
        "value_added_segment": round(seg_acc - base_seg_acc, 4),
        "baseline_whole_exact": round(
            sum(1 for r in rows if (r.get("tier") or {}).get("baseline_whole_exact")) / n, 4
        ),
        "value_added_whole_exact": round(exact / n - sum(
            1 for r in rows if (r.get("tier") or {}).get("baseline_whole_exact")
        ) / n, 4),
    }

    # Rows where no rule fired at all: the metric cannot see rules here.
    changed = sum(
        1
        for r in rows
        if normalize_for_scoring(r.get("predicted", ""))
        != normalize_for_scoring(r.get("baseline_prediction", r.get("catawba_form", "")))
    )
    out["rows_changed_by_rules"] = changed
    if changed == 0:
        out["no_rule_applicable_warning"] = (
            "No rule altered any row in this split — a 0.0% value-added here means "
            "the split contains no applicable environments, not that rules failed"
        )

    # Rows where copying already scores perfectly cannot show rule value.
    # Report the discriminative subset so a flat delta is not read as failure.
    disc = [r for r in rows if (r.get("tier") or {}).get("baseline_segment_accuracy", 1.0) < 1.0]
    if disc:
        d_correct = d_target = d_base_correct = d_base_target = 0
        for r in disc:
            c, t_len, _ = segment_counts(r.get("predicted", ""), r.get("target", ""))
            d_correct += c
            d_target += t_len
            bc, bt_len, _ = segment_counts(
                r.get("baseline_prediction", r.get("catawba_form", "")), r.get("target", "")
            )
            d_base_correct += bc
            d_base_target += bt_len
        d_seg = d_correct / d_target if d_target else 0.0
        d_base = d_base_correct / d_base_target if d_base_target else 0.0
        out["discriminative_count"] = len(disc)
        out["discriminative_segment_accuracy"] = round(d_seg, 4)
        out["discriminative_baseline_segment_accuracy"] = round(d_base, 4)
        out["discriminative_value_added"] = round(d_seg - d_base, 4)
    else:
        out["discriminative_count"] = 0
        out["discriminative_note"] = "all rows already perfect under copy baseline"

    if n < SMALL_SAMPLE_THRESHOLD:
        out["small_sample_warning"] = (
            f"Only {n} items — do not use as headline metric (threshold {SMALL_SAMPLE_THRESHOLD})"
        )
        out["headline_eligible"] = False
    else:
        out["headline_eligible"] = True

    if headline and not out.get("headline_eligible"):
        out["headline_blocked"] = True

    return out


def rule_generality_audit(
    results: List[Dict[str, Any]],
    train_rule_counts: Dict[str, int],
    rejected_rules: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Audit whether correct predictions come from general rules."""
    rule_hits: Counter[str] = Counter()
    rule_correct: Counter[str] = Counter()
    for r in results:
        if r.get("score") in ("exact", "partial") or r.get("tier", {}).get("label") in ("exact", "partial"):
            for rid in r.get("rules_used") or []:
                rule_hits[rid] += 1
                if r.get("tier", {}).get("exact_normalized") or r.get("score") == "exact":
                    rule_correct[rid] += 1

    coverage = [train_rule_counts.get(rid, 0) for rid in rule_hits]
    hist: Dict[str, int] = defaultdict(int)
    for c in coverage:
        hist[str(c)] += 1

    multi = sum(1 for rid in rule_correct if train_rule_counts.get(rid, 0) >= 3)
    total_correct = sum(1 for r in results if (r.get("tier") or {}).get("exact_normalized"))
    share_multi = multi / total_correct if total_correct else 0.0

    return {
        "train_items_per_rule_mean": round(sum(coverage) / len(coverage), 2) if coverage else 0.0,
        "train_items_per_rule_histogram": dict(hist),
        "rejected_rule_count": len(rejected_rules),
        "rejected_rules": rejected_rules,
        "correct_from_rules_with_3plus_train": multi,
        "share_correct_from_3plus_rules": round(share_multi, 4),
    }


def ablation_table(
    rules: List[Dict[str, Any]],
    train_rows: List[Dict[str, Any]],
    score_fn,
    *,
    min_recurrence: int = 2,
    train_counts: Optional[Dict[str, int]] = None,
) -> Tuple[List[Dict[str, Any]], float]:
    """
    For each non-identity rule, measure train simple segment score with/without it.
    Returns (rows, baseline_full_score).
    """
    full_score = score_fn(train_rows, rules)
    rows: List[Dict[str, Any]] = []
    for rule in rules:
        lhs, rhs = rule.get("lhs"), rule.get("rhs")
        if str(lhs) == str(rhs):
            continue
        reduced = [r for r in rules if r.get("id") != rule.get("id")]
        without = score_fn(train_rows, reduced)
        delta = without - full_score
        if delta < 0:
            verdict = "earns_it"
        elif delta > 0:
            verdict = "harmful"
        else:
            verdict = "neutral"
        rows.append(
            {
                "rule_id": rule.get("id"),
                "train_count": (train_counts or {}).get(rule.get("id"), 0),
                "score_with": round(full_score, 4),
                "score_without": round(without, 4),
                "delta_segment": round(delta, 4),
                "verdict": verdict,
                "lhs": lhs,
                "rhs": rhs,
                "environment": rule.get("environment"),
            }
        )
    rows.sort(key=lambda r: r["delta_segment"])
    return rows, full_score
