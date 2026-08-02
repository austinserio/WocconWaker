"""Segment alignment for recurrence counting."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def rule_applies(
    rule: Dict[str, Any],
    w_char: str,
    c_char: str,
    w_pos: int,
    w_len: int,
) -> bool:
    from woccon_reconstruction.comparative_utils import norm_form

    lhs = norm_form(rule.get("lhs"))
    rhs = norm_form(rule.get("rhs"))
    if lhs is None and rhs is None:
        return False
    env = rule.get("environment") or "default"
    if env == "word-initial" and w_pos > 0:
        return False
    if env == "word-medial" and w_pos == 0:
        return False
    if not lhs or not rhs:
        return lhs == rhs == ""
    if len(lhs) == 1 and len(rhs) == 1:
        return w_char == lhs and c_char == rhs
    return w_char == lhs and c_char == rhs


def tokenize(form: str) -> List[tuple[str, int, int]]:
    tokens: List[tuple[str, int, int]] = []
    for i, ch in enumerate(form):
        if ch.isalnum() or ch in "·?-*|":
            tokens.append((ch.lower(), i, i + 1))
    return tokens


def align_pair(
    w_form: str,
    c_form: str,
    rules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    w_tokens = tokenize(w_form)
    c_tokens = tokenize(c_form)
    alignments: List[Dict[str, Any]] = []
    wi, ci = 0, 0
    while wi < len(w_tokens) and ci < len(c_tokens):
        w_ch, ws, we = w_tokens[wi]
        c_ch, cs, ce = c_tokens[ci]
        matched_rule: Optional[Dict[str, Any]] = None
        for rule in rules:
            if rule.get("correspondence_status") == "singleton":
                continue
            if rule_applies(rule, w_ch, c_ch, wi, len(w_tokens)):
                matched_rule = rule
                break
        if matched_rule:
            alignments.append({"rule_id": matched_rule["id"]})
            wi += 1
            ci += 1
        elif w_ch == c_ch:
            alignments.append({"rule_id": None})
            wi += 1
            ci += 1
        else:
            wi += 1
            ci += 1
    return alignments
