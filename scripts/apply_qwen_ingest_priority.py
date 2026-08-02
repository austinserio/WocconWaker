#!/usr/bin/env python3
"""Backup Azure live rules and apply qwen_ingest_priority.json (P1/P2 promote, M1/M2 merge)."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ENRICH_MARKER = "[Enriched from Resurrecting Qwen validation, 2026-08-01]"

# Qwen lookup keys → search terms for staging text
QWEN_LOOKUP: Dict[str, List[str]] = {
    "p1_obstruent": ["obstruent", "*b", "*d", "glottal", "*š"],
    "p1_s_sh": ["lacks the phoneme /š/", "/š/"],
    "p1_se": ["*-se", "end", "point"],
    "p1_re_existential": ["existential", "there are", "quantities"],
    "p1_r_bar": ["*r̄", "defective", "word-initially"],
    "p2_tau": ["*-tau", "ikettau", "bread"],
    "p2_possession": ["alienable", "inalienable"],
    "p2_ru": ["*ru-", "by hand", "manufactured"],
    "p2_nasal_assim": ["regressive nasal", "esaw", "saraw"],
    "m1_modes": ["participial", "imperative", "interrogative", "independent modal"],
    "m1_re": ["independent modal suffix *-re", "verbs, nouns, adverbs"],
    "m1_nasal_oral": ["correspondence", "nasal vowel", "long oral"],
    "m1_dapa": ["*dapa-", "wild animal"],
    "m1_ne": ["interrogative", "*-ne"],
    "m1_vowel12": ["twelve vowel", "*wátupi", "short oral"],
    "m2_redup": ["reduplication", "frequentive", "intensive"],
    "m2_i_prefix": ["third person plural", "*i-", "prefix *i-"],
    "m2_compounds": ["parasites", "clothing", "manufactured items"],
    "m2_dy": ["*dy*", "affricated", "widyu", "witso"],
    "m2_syncope": ["weakening", "unstressed syllables", "syncope"],
    "m2_grapheme": ["grapheme", "copyist error", "kú·wate"],
    "m2_denasl": ["denasalization", "m and n became b and d"],
}

# Priority item → qwen lookup key (+ optional override)
ITEM_QWEN_KEY: Dict[str, str] = {
    "Proto-Catawban obstruent inventory": "p1_obstruent",
    "Woccon lacks attested phoneme /š/": "p1_s_sh",
    "Proto-Catawban suffix *-se": "p1_se",
    "Independent modal *-re·* as existential": "p1_re_existential",
    "*r̄ distributed freely in Woccon": "p1_r_bar",
    "Participial/nominalizing suffix *-tau*": "p2_tau",
    "Alienable possession = suffix": "p2_possession",
    "Proto-Catawban *ru- prefix": "p2_ru",
    "Regressive nasal assimilation": "p2_nasal_assim",
    "Four modal modes": "m1_modes",
    "Independent modal *-re·* on verbs": "m1_re",
    "Nasal vowel ↔ long oral vowel": "m1_nasal_oral",
    "*dapa- wild animal classifier": "m1_dapa",
    "Interrogative *-ne*": "m1_ne",
    "12-vowel inventory with illustrated forms": "m1_vowel12",
    "Reduplication: full-root frequentive": "m2_redup",
    "3pl subject prefix *i- on verbs": "m2_i_prefix",
    "Compound templates: parasites": "m2_compounds",
    "Medial *dy* → [dz] affrication": "m2_dy",
    "Vowel weakening/syncope": "m2_syncope",
    "Lawson grapheme conventions": "m2_grapheme",
    "Denasalization m/n → b/d": "m2_denasl",
}


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def _base_url() -> str:
    webhook = (os.environ.get("AZURE_CONTAINER_APP_WEBHOOK_URL") or "").strip()
    if webhook:
        p = urlparse(webhook)
        return f"{p.scheme}://{p.netloc}"
    explicit = (os.environ.get("PANEL_BASE_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/")
    raise SystemExit("Set AZURE_CONTAINER_APP_WEBHOOK_URL in .env")


def _login(session: requests.Session, base: str) -> str:
    email = os.environ.get("PANEL_ADMIN_EMAIL", "").strip()
    password = os.environ.get("PANEL_ADMIN_PASSWORD", "").strip()
    if not email or not password:
        raise SystemExit("PANEL_ADMIN_EMAIL and PANEL_ADMIN_PASSWORD required")
    resp = session.post(
        f"{base}/api/auth/login/json",
        json={"email": email, "password": password},
        timeout=60,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise SystemExit("Login failed: no access_token")
    return token


def _condense_qwen(text: str, max_len: int = 2000) -> str:
    t = re.sub(r"\s+", " ", text.strip())
    if len(t) <= max_len:
        return t
    return t[: max_len - 3] + "..."


def _find_qwen_text(notes: List[str], keywords: List[str], category: Optional[str] = None) -> str:
    best = ""
    best_score = 0
    for t in notes:
        tl = t.lower()
        score = sum(3 if k.lower() in tl else 0 for k in keywords)
        if score > best_score:
            best_score, best = score, t
    if best_score == 0:
        return ""
    return _condense_qwen(best)


def _qwen_key_for_claim(claim: str) -> Optional[str]:
    for prefix, key in ITEM_QWEN_KEY.items():
        if prefix.lower() in claim.lower():
            return key
    return None


def _merge_content(existing: str, qwen_text: str) -> str:
    if not qwen_text:
        return existing
    if ENRICH_MARKER in existing:
        # replace prior enrichment block
        base = existing.split(ENRICH_MARKER)[0].rstrip()
    else:
        base = existing.rstrip()
    return f"{base}\n\n{ENRICH_MARKER}\n{qwen_text}"


def _domain_for_lineage(lineage: Optional[str], category: str, claim: str) -> Optional[str]:
    if category == "pronunciation":
        return "phonology"
    cl = claim.lower()
    if any(x in cl for x in ("phoneme", "vowel", "consonant", "nasal assimilation", "affricat", "grapheme", "syncop")):
        return "phonology"
    if lineage in ("proto_catawban", "proto_siouan_catawban", "siouan_comparative", "woccon_attested"):
        return "morphology"
    return "morphology"


def backup_live(session: requests.Session, base: str, headers: dict) -> Path:
    out: Dict[str, Any] = {
        "base_url": base,
        "backed_up_at": datetime.now(timezone.utc).isoformat(),
    }
    for cat in ("grammar", "pronunciation"):
        resp = session.get(f"{base}/api/rules", params={"category": cat}, headers=headers, timeout=120)
        resp.raise_for_status()
        out[cat] = resp.json()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = ROOT / "data" / "backups" / f"azure_live_rules_pre_qwen_ingest_{ts}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Backup: {path} ({len(out['grammar'])} grammar, {len(out['pronunciation'])} pronunciation)")
    return path


def apply(session: requests.Session, base: str, headers: dict, dry_run: bool = False) -> Dict[str, Any]:
    from scripts.compare_qwen_vs_azure_live import merge_qwen_notes

    priority = json.loads((ROOT / "data/backups/qwen_ingest_priority.json").read_text())
    qwen = merge_qwen_notes(ROOT / "woccon_language/drive_staging_qwen_validate")
    all_grammar = qwen["grammar"]
    all_pron = qwen["pronunciation"]

    live_by_id: Dict[str, dict] = {}
    for cat in ("grammar", "pronunciation"):
        resp = session.get(f"{base}/api/rules", params={"category": cat}, headers=headers, timeout=120)
        resp.raise_for_status()
        for r in resp.json():
            live_by_id[r["id"]] = r

    log: Dict[str, Any] = {"promoted": [], "merged": [], "skipped": [], "errors": []}
    pending_ids: List[str] = []

    for item in priority["items"]:
        action = item["action"]
        claim = item["qwen_claim"]
        if action == "SKIP":
            log["skipped"].append(claim[:80])
            continue

        qkey = _qwen_key_for_claim(claim)
        keywords = QWEN_LOOKUP.get(qkey or "", [])
        cat = item.get("category") or "grammar"
        notes = all_grammar if cat == "grammar" else all_pron
        qwen_text = _find_qwen_text(notes, keywords, cat) if keywords else ""

        if action == "PROMOTE":
            # P2 Ikettau → merge into existing rule when live_rule_id present
            if item.get("live_rule_id") and ("Ikettau" in claim or "*-tau*" in claim):
                action = "MERGE"
            else:
                content = qwen_text or claim
                body = {
                    "category": cat,
                    "content": content,
                    "reviewer_notes": f"Qwen Resurrecting validation {item['priority']}",
                }
                gd = _domain_for_lineage(item.get("lineage"), cat, claim)
                if gd:
                    body["grammar_domain"] = gd
                if dry_run:
                    log["promoted"].append({"claim": claim[:80], "dry_run": True})
                    continue
                resp = session.post(f"{base}/api/pending/rules", json=body, headers=headers, timeout=60)
                if not resp.ok:
                    log["errors"].append({"action": "promote", "claim": claim[:60], "error": resp.text[:200]})
                    continue
                pid = resp.json()["id"]
                pending_ids.append(pid)
                log["promoted"].append({"id": pid, "claim": claim[:80]})
                continue

        if action == "MERGE":
            rid = item.get("live_rule_id")
            if not rid:
                log["skipped"].append(f"merge no target id: {claim[:60]}")
                continue
            if rid not in live_by_id:
                log["errors"].append({"action": "merge", "claim": claim[:60], "error": f"rule not found: {rid}"})
                continue
            row = live_by_id[rid]
            new_content = _merge_content(row["content"], qwen_text)
            if new_content == row["content"]:
                log["skipped"].append(f"merge unchanged: {claim[:60]}")
                continue
            if dry_run:
                log["merged"].append({"id": rid, "claim": claim[:80], "dry_run": True})
                continue
            resp = session.patch(
                f"{base}/api/rules/{rid}",
                json={"content": new_content, "provenance_status": "manual"},
                headers=headers,
                timeout=60,
            )
            if not resp.ok:
                log["errors"].append({"action": "merge", "id": rid, "error": resp.text[:200]})
                continue
            log["merged"].append({"id": rid, "claim": claim[:80]})
            live_by_id[rid]["content"] = new_content

    if pending_ids and not dry_run:
        resp = session.post(
            f"{base}/api/pending/rules/bulk",
            json={"ids": pending_ids, "status": "approved"},
            headers=headers,
            timeout=60,
        )
        if not resp.ok:
            log["errors"].append({"action": "approve", "error": resp.text[:200]})
        else:
            log["approved_pending"] = resp.json()
        resp = session.post(f"{base}/api/admin/commit", headers=headers, timeout=120)
        if not resp.ok:
            log["errors"].append({"action": "commit", "error": resp.text[:200]})
        else:
            log["commit"] = resp.json()

    return log


def main() -> int:
    _load_env()
    dry_run = "--dry-run" in sys.argv
    base = _base_url()
    session = requests.Session()
    token = _login(session, base)
    headers = {"Authorization": f"Bearer {token}"}

    backup_live(session, base, headers)
    log = apply(session, base, headers, dry_run=dry_run)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = ROOT / "data" / "backups" / f"qwen_ingest_apply_log_{ts}.json"
    out.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in log.items()}, indent=2))
    print(f"Log: {out}")
    if log.get("errors"):
        print("ERRORS:", json.dumps(log["errors"], indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
