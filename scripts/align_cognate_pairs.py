#!/usr/bin/env python3
"""Rule-based segment alignment for App. 1 certain cognate pairs."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from woccon_reconstruction.comparative_utils import (  # noqa: E402
    DEFAULT_ALIGNMENTS,
    DEFAULT_COGNATES,
    DEFAULT_REGISTRY,
    app1_certain,
    load_cognate_sets,
    load_registry,
    norm_form,
    registry_rules,
)

Token = Tuple[str, int, int]  # char, start, end in original


def tokenize(form: str) -> List[Token]:
    tokens: List[Token] = []
    for i, ch in enumerate(form):
        if ch.isalnum() or ch in "·?-*|":
            tokens.append((ch.lower(), i, i + 1))
    return tokens


def rule_applies(
    rule: Dict[str, Any],
    w_char: str,
    c_char: str,
    w_pos: int,
    w_len: int,
) -> bool:
    lhs = norm_form(rule.get("lhs"))
    rhs = norm_form(rule.get("rhs"))
    if not lhs or not rhs:
        return False
    env = rule.get("environment") or "default"
    if env == "word-initial" and w_pos > 0:
        return False
    if env == "word-medial" and w_pos == 0:
        return False
    # Match single-char rules primarily
    if len(lhs) == 1 and len(rhs) == 1:
        return w_char == lhs and c_char == rhs
    if lhs == rhs:
        return w_char == lhs and c_char == rhs
    return False


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
            alignments.append(
                {
                    "w_span": w_form[ws:we],
                    "c_span": c_form[cs:ce],
                    "w_start": ws,
                    "w_end": we,
                    "c_start": cs,
                    "c_end": ce,
                    "rule_id": matched_rule["id"],
                }
            )
            wi += 1
            ci += 1
        elif w_ch == c_ch:
            alignments.append(
                {
                    "w_span": w_form[ws:we],
                    "c_span": c_form[cs:ce],
                    "w_start": ws,
                    "w_end": we,
                    "c_start": cs,
                    "c_end": ce,
                    "rule_id": None,
                }
            )
            wi += 1
            ci += 1
        else:
            wi += 1
            ci += 1
    return alignments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cognates", type=Path, default=DEFAULT_COGNATES)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path, default=DEFAULT_ALIGNMENTS)
    args = parser.parse_args()

    cognates = load_cognate_sets(args.cognates)
    registry = load_registry(args.registry)
    sister_rules = [
        r
        for r in registry_rules(registry)
        if r.get("rule_kind") == "sister_wc"
        and r.get("correspondence_status") in ("established", "tentative")
    ]

    rows: List[Dict[str, Any]] = []
    for cog in app1_certain(cognates):
        w = cog.get("woccon_reconstituted") or ""
        c = cog.get("catawba_form") or ""
        alns = align_pair(w, c, sister_rules)
        ruled = [a for a in alns if a.get("rule_id")]
        rows.append(
            {
                "cognate_id": cog["id"],
                "gloss": cog.get("gloss"),
                "woccon_reconstituted": w,
                "catawba_form": c,
                "alignments": alns,
                "ruled_count": len(ruled),
            }
        )

    envelope = {
        "version": 1,
        "source": "App. 1 certain cognate alignments (Phase 3)",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "generator": "align_cognate_pairs",
        "alignments": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with_rules = sum(1 for r in rows if r.get("ruled_count", 0) > 0)
    print(f"Wrote {args.out}: {len(rows)} pairs, {with_rules} with rule-backed alignments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
