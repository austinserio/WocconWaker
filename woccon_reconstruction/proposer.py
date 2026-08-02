"""Deterministic Catawba → Woccon projection using sister_wc registry rules."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from woccon_reconstruction.comparative_utils import norm_form
from woccon_reconstruction.orthography import repair_ocr
from woccon_reconstruction.recurrence import (
    apply_ablation_gate,
    apply_recurrence_gate,
    count_rule_attestations_on_train,
)


@dataclass
class ProjectionResult:
    predicted: str
    rules_used: List[str] = field(default_factory=list)
    strategy: str = "simple"
    candidates: List[str] = field(default_factory=list)


def _usable_rules(rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rules:
        if r.get("rule_kind") != "sister_wc":
            continue
        if r.get("correspondence_status") not in ("established", "tentative"):
            continue
        lhs, rhs = r.get("lhs"), r.get("rhs")
        if lhs is None and rhs is None:
            continue
        out.append(r)
    out.sort(
        key=lambda x: (
            -len(norm_form(x.get("rhs") or "")),
            -len(norm_form(x.get("lhs") or "")),
        )
    )
    return out


def _environment_ok(env: str, pos: int, length: int, is_vowel: bool, word: str = "") -> bool:
    if env in ("default", "", None):
        return True
    if env == "word-initial":
        return pos == 0
    if env == "word-initial-long":
        return pos == 0 and len(norm_form(word)) >= 5
    if env == "word-medial":
        return 0 < pos < length - 1
    if env == "word-final":
        return pos >= max(0, length - 1)
    if env == "vowel_correspondence":
        return is_vowel
    return True


def _is_vowel_char(ch: str) -> bool:
    return ch.lower() in "aeiouąęįųáéíóú"


def _inverse_segments(rules: List[Dict[str, Any]]) -> List[Tuple[str, str, str, str]]:
    """(catawba_seg, woccon_seg, rule_id, environment) longest-first."""
    inv: List[Tuple[str, str, str, str]] = []
    seen: Set[Tuple[str, str, str]] = set()
    for r in _usable_rules(rules):
        lhs = str(r.get("lhs") or "")
        rhs = str(r.get("rhs") or "")
        env = r.get("environment") or "default"
        key = (norm_form(rhs), norm_form(lhs), env)
        if key in seen:
            continue
        seen.add(key)
        inv.append((rhs, lhs, r["id"], env))
    inv.sort(key=lambda t: len(norm_form(t[0])), reverse=True)
    return inv


def _tokenize(form: str) -> List[Tuple[str, int, int]]:
    """Character tokens with span positions."""
    tokens: List[Tuple[str, int, int]] = []
    for i, ch in enumerate(form):
        if ch.isalnum() or ch in "·?-*|ąęįųáéíóú":
            tokens.append((ch, i, i + 1))
    return tokens


def _apply_rules_once(
    catawba_form: str,
    inv: List[Tuple[str, str, str, str]],
) -> Tuple[str, List[str]]:
    """Single-pass longest-match substitution on catawba string."""
    if not catawba_form:
        return "", []
    form = repair_ocr(catawba_form)
    used: List[str] = []
    chars = list(form)
    i = 0
    while i < len(chars):
        matched = False
        pos_norm = i
        for rhs, lhs, rid, env in inv:
            rhs_norm = norm_form(rhs)
            if not rhs_norm and env == "word-initial" and i == 0:
                # insert W r at start only when Catawba begins with a vowel
                if lhs and _is_vowel_char(chars[0]):
                    chars.insert(0, lhs)
                    used.append(rid)
                    i += 1
                    matched = True
                    break
                continue
            if not rhs_norm:
                continue
            segment = norm_form("".join(chars[i : i + len(rhs)]))
            if segment != rhs_norm:
                continue
            if env == "vowel_correspondence" and not (
                _is_vowel_char(chars[i]) and lhs and _is_vowel_char(lhs[0])
            ):
                continue
            if not _environment_ok(env, pos_norm, len(chars), _is_vowel_char(chars[i]), word=form):
                continue
            replacement = list(lhs) if lhs else []
            chars[i : i + len(rhs)] = replacement
            used.append(rid)
            if replacement:
                i += len(replacement)
            matched = True
            break
        if not matched:
            i += 1
    return "".join(chars), used


def project_c_to_w(
    catawba_form: str,
    rules: List[Dict[str, Any]],
    *,
    n_best: int = 3,
) -> Tuple[str, List[str]]:
    """Apply inverse sister rules; return top prediction + rule ids used."""
    result = project_c_to_w_nbest(catawba_form, rules, n_best=n_best)
    if not result.candidates:
        return catawba_form, []
    return result.candidates[0], result.rules_used


def project_c_to_w_nbest(
    catawba_form: str,
    rules: List[Dict[str, Any]],
    *,
    n_best: int = 3,
) -> ProjectionResult:
    """Return n-best candidate projections with provenance."""
    if not catawba_form:
        return ProjectionResult("", [], "empty")
    form = repair_ocr(catawba_form)
    if " " in form.strip():
        parts = form.split()
        preds: List[str] = []
        all_rules: List[str] = []
        for part in parts:
            sub = project_c_to_w_nbest(part, rules, n_best=1)
            preds.append(sub.candidates[0] if sub.candidates else part)
            all_rules.extend(sub.rules_used)
        combined = " ".join(preds)
        return ProjectionResult(
            predicted=combined,
            rules_used=list(dict.fromkeys(all_rules)),
            strategy="simple",
            candidates=[combined],
        )
    inv = _inverse_segments(rules)
    candidates: List[str] = []
    all_rules: List[str] = []

    # Primary pass
    pred1, rules1 = _apply_rules_once(catawba_form, inv)
    candidates.append(pred1)
    all_rules.extend(rules1)

    # Second pass on original (catch rules blocked by first pass ordering)
    pred2, rules2 = _apply_rules_once(catawba_form, list(reversed(inv)))
    if pred2 not in candidates:
        candidates.append(pred2)
    all_rules.extend(rules2)

    # Vowel-focused pass
    vowel_inv = [t for t in inv if t[3] == "vowel_correspondence"]
    if vowel_inv:
        pred3, rules3 = _apply_rules_once(catawba_form, vowel_inv + inv)
        if pred3 not in candidates:
            candidates.append(pred3)
        all_rules.extend(rules3)

    # Identity baseline
    base = repair_ocr(catawba_form)
    if base not in candidates:
        candidates.append(base)

    # Dedupe preserving order
    seen: Set[str] = set()
    uniq: List[str] = []
    for c in candidates:
        key = norm_form(c)
        if key not in seen:
            seen.add(key)
            uniq.append(c)

    return ProjectionResult(
        predicted=uniq[0] if uniq else base,
        rules_used=list(dict.fromkeys(all_rules)),
        strategy="simple",
        candidates=uniq[:n_best],
    )


def filter_rules_by_recurrence(
    rules: List[Dict[str, Any]],
    train_items: List[Dict[str, Any]],
    align_fn,
    min_count: int = 2,
    *,
    use_ablation: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    counts = count_rule_attestations_on_train(train_items, rules, align_fn, project_fn=project_c_to_w)
    if use_ablation:
        admitted, rejected = apply_ablation_gate(
            rules, train_items, project_c_to_w, counts, min_count=min_count
        )
    else:
        admitted, rejected = apply_recurrence_gate(rules, counts, min_count=min_count)
    return admitted, rejected, counts


def score_prediction(predicted: str, target: str) -> str:
    """Legacy label for backward compatibility."""
    from woccon_reconstruction.scoring import tiered_score

    return tiered_score(predicted, target)["label"]
