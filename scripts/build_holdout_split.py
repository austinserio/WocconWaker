#!/usr/bin/env python3
"""Build stable Lawson + cognate train/dev/test split."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from woccon_reconstruction.comparative_utils import (  # noqa: E402
    DEFAULT_COGNATES,
    DEFAULT_DICTIONARY,
    effective_lawson,
    load_cognate_sets,
    load_dictionary,
    norm_lawson,
)
from woccon_reconstruction.orthography import repair_ocr  # noqa: E402
from woccon_reconstruction.projectability import annotate_pool  # noqa: E402

DEFAULT_OUT = ROOT / "data/lawson_holdout_split.json"
RAW_DIR = ROOT / "woccon_language/cognate_sets/_raw"
DEV_RATIO = 0.20
TEST_RATIO = 0.25
MAX_DEV = 20
MAX_TEST = 30


def load_raw_chunks() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for app in (1, 2, 3, 4):
        path = RAW_DIR / f"app{app}.txt"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        import re

        for m in re.finditer(r"(?:^|\s)(\d+)[.,]\s+", text):
            pass
        # map by appendix item from seed ids later via item number
        for num_m in re.finditer(r"(?:^|\s)(\d+)[.,]\s+([\s\S]*?)(?=(?:^|\s)\d+[.,]\s+|\Z)", text):
            item = int(num_m.group(1))
            out[f"rudes2000_app{app}_{item:03d}"] = num_m.group(2).strip()
    return out


def dict_by_woccon(lexicon: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in lexicon:
        key = norm_lawson(row.get("woccon"))
        if key:
            out[key] = row
    return out


def build_pool(
    cognates: List[Dict[str, Any]],
    lexicon: List[Dict[str, Any]],
    *,
    tiers: Set[str],
    appendices: Set[int],
) -> List[Dict[str, Any]]:
    dix = dict_by_woccon(lexicon)
    pool: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for cog in cognates:
        if cog.get("evidence_tier") not in tiers:
            continue
        if cog.get("rudes_appendix") not in appendices:
            continue
        if not cog.get("catawba_form") or not cog.get("woccon_reconstituted"):
            continue
        cid = cog["id"]
        if cid in seen:
            continue
        seen.add(cid)
        lawson = effective_lawson(cog)
        dict_row = dix.get(norm_lawson(lawson or "")) if lawson else None
        pool.append(
            {
                "cognate_id": cid,
                "gloss": cog.get("gloss") or (dict_row or {}).get("english") or cog.get("gloss"),
                "lawson_form": lawson,
                "lawson_attested": (dict_row or {}).get("woccon") if dict_row else None,
                "woccon_reconstituted": repair_ocr(cog.get("woccon_reconstituted") or ""),
                "catawba_form": repair_ocr(cog.get("catawba_form") or ""),
                "catawba_dialect": cog.get("catawba_dialect"),
                "evidence_tier": cog.get("evidence_tier"),
                "rudes_appendix": cog.get("rudes_appendix"),
                "notes": cog.get("notes"),
                "bucket": (lawson[0].lower() if lawson else "z"),
            }
        )
    return sorted(pool, key=lambda r: r["cognate_id"])


def _hash_pick(ids: List[str], n: int) -> List[str]:
    ranked = sorted(ids, key=lambda i: hashlib.sha256(i.encode()).hexdigest())
    return ranked[:n]


# Environments where a non-identity sound law can fire. Only ~6 cognates in the
# whole corpus show these, so an unstratified split puts them all in train and
# leaves dev/test unable to measure any rule at all.
_ENV_PROBES = {
    "initial_d": lambda c: c.startswith("d"),
    "initial_n": lambda c: c.startswith("n"),
    "rd_cluster": lambda c: "rd" in c,
    "has_b": lambda c: "b" in c,
    "medial_d": lambda c: len(c) > 2 and "d" in c[1:-1],
    "final_e": lambda c: c.endswith("e"),
}


def environment_signature(row: Dict[str, Any]) -> str:
    """Which non-identity rule environments this Catawba form exhibits."""
    c = (row.get("catawba_form") or "").lower()
    hits = [name for name, fn in _ENV_PROBES.items() if c and fn(c)]
    return "+".join(hits) if hits else "identity_only"


def stratify_rule_environments(
    pool: List[Dict[str, Any]],
    dev_ids: List[str],
    test_ids: List[str],
) -> tuple[List[str], List[str]]:
    """
    Ensure each rule-relevant environment appears in dev and test when supply allows.

    Swaps in an unassigned carrier of a missing environment, evicting an
    identity-only row so split sizes stay fixed.
    """
    by_id = {r["cognate_id"]: r for r in pool}
    projectable = {"simple", "compound", "affixed", "reduplicated"}

    carriers: Dict[str, List[str]] = {}
    for row in pool:
        if row.get("projectability") not in projectable:
            continue
        c = (row.get("catawba_form") or "").lower()
        for name, fn in _ENV_PROBES.items():
            if c and fn(c):
                carriers.setdefault(name, []).append(row["cognate_id"])

    dev, test = list(dev_ids), list(test_ids)
    for env, ids in sorted(carriers.items()):
        if len(ids) < 3:
            continue  # too few carriers to hold any out without starving train
        for target in (dev, test):
            if any(i in target for i in ids):
                continue
            assigned = set(dev) | set(test)
            # A rule can only be learned if at least one carrier stays in train.
            in_train = [i for i in ids if i not in assigned]
            if len(in_train) < 2:
                continue
            evictable = [
                i
                for i in target
                if environment_signature(by_id.get(i, {})) == "identity_only"
            ]
            if not evictable:
                continue
            target.remove(evictable[0])
            target.append(in_train[0])
    return dev, test


def three_way_split(
    pool: List[Dict[str, Any]],
    *,
    dev_size: int | None = None,
    test_size: int | None = None,
) -> tuple[List[str], List[str], List[str]]:
    """Stratified train / dev / test by initial letter bucket."""
    n = len(pool)
    if n == 0:
        return [], [], []
    test_size = test_size if test_size is not None else min(MAX_TEST, max(8, round(n * TEST_RATIO)))
    dev_size = dev_size if dev_size is not None else min(MAX_DEV, max(8, round(n * DEV_RATIO)))
    if test_size + dev_size >= n:
        test_size = max(1, n // 5)
        dev_size = max(1, n // 5)
    by_bucket: Dict[str, List[str]] = {}
    for row in pool:
        by_bucket.setdefault(row["bucket"], []).append(row["cognate_id"])

    dev_ids: List[str] = []
    test_ids: List[str] = []
    for bucket in sorted(by_bucket):
        ids = by_bucket[bucket]
        dev_quota = max(1, round(dev_size * len(ids) / len(pool))) if pool else 0
        test_quota = max(1, round(test_size * len(ids) / len(pool))) if pool else 0
        picked_dev = _hash_pick(ids, dev_quota)
        dev_ids.extend(picked_dev)
        remaining = [i for i in ids if i not in picked_dev]
        picked_test = _hash_pick(remaining, test_quota)
        test_ids.extend(picked_test)

    dev_ids = dev_ids[:dev_size]
    test_ids = [i for i in test_ids if i not in dev_ids][:test_size]
    all_eval = set(dev_ids) | set(test_ids)
    if len(test_ids) < test_size:
        remaining = [r["cognate_id"] for r in pool if r["cognate_id"] not in all_eval]
        test_ids.extend(_hash_pick(remaining, test_size - len(test_ids)))
        all_eval = set(dev_ids) | set(test_ids)
    train_ids = [r["cognate_id"] for r in pool if r["cognate_id"] not in all_eval]
    return train_ids, dev_ids, test_ids


def split_checksum(test_ids: List[str]) -> str:
    payload = ",".join(sorted(test_ids))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cognates", type=Path, default=DEFAULT_COGNATES)
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dev-size", type=int, default=None)
    parser.add_argument("--test-size", type=int, default=None)
    parser.add_argument(
        "--no-stratify-environments",
        action="store_true",
        help="Skip rule-environment stratification (debug)",
    )
    args = parser.parse_args()

    cognates = load_cognate_sets(args.cognates)
    lexicon = load_dictionary(args.dictionary)
    pool = build_pool(
        cognates,
        lexicon,
        tiers={"certain", "partial", "possible"},
        appendices={1, 2, 3, 4},
    )
    raw = load_raw_chunks()
    pool = annotate_pool(pool, raw)
    train_ids, dev_ids, test_ids = three_way_split(pool, dev_size=args.dev_size, test_size=args.test_size)
    if not args.no_stratify_environments:
        dev_ids, test_ids = stratify_rule_environments(pool, dev_ids, test_ids)
        eval_ids = set(dev_ids) | set(test_ids)
        train_ids = [r["cognate_id"] for r in pool if r["cognate_id"] not in eval_ids]
    checksum = split_checksum(test_ids)

    env_by_split = {
        name: sorted(
            {
                environment_signature(r)
                for r in pool
                if r["cognate_id"] in set(ids) and r.get("projectability") == "simple"
            }
        )
        for name, ids in (("train", train_ids), ("dev", dev_ids), ("test", test_ids))
    }

    envelope = {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "pool_size": len(pool),
        "train_size": len(train_ids),
        "dev_size": len(dev_ids),
        "test_size": len(test_ids),
        "holdout_size": len(test_ids),
        "train_ids": train_ids,
        "dev_ids": dev_ids,
        "test_ids": test_ids,
        "holdout_ids": test_ids,
        "test_checksum": checksum,
        "environment_stratified": not args.no_stratify_environments,
        "rule_environments_by_split": env_by_split,
        "items": pool,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.out}: pool={len(pool)} train={len(train_ids)} "
        f"dev={len(dev_ids)} test={len(test_ids)} checksum={checksum}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
