#!/usr/bin/env python3
"""Diff a full ingest run against a pre-run snapshot.

The lossy-scan detector routes image-backed pages with diacritic-stripped text layers to
vision OCR, so a force-full re-ingest can silently rewrite the text layer of documents that
previously came through as ASCII. This reports what actually changed before any of it gets
committed:

  A. Text layer  - which documents gained phonetic notation, and by how much.
  B. Lexicon     - which staged headwords were added, dropped, or respelled with diacritics.

The respelling case matters most: an entry whose diacritic-stripped form is unchanged but
whose surface form gained accents is the same word finally recorded correctly, not a new one.

    python scripts/diff_ingest_run.py                     # uses LAST_PRE_INGEST_SNAPSHOT
    python scripts/diff_ingest_run.py --snapshot DIR --out report.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PHONETIC_CHAR = re.compile(r"[\u00C0-\u024F\u0250-\u02FF\u0300-\u036F]")


def strip_diacritics(s: str) -> str:
    decomposed = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower().strip()


def load_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_text_cache(d: Path) -> dict:
    """Map Drive path -> cache record. Later cache files win on duplicate paths."""
    out = {}
    for f in sorted(d.glob("*.json")):
        rec = load_json(f)
        path = rec.get("path")
        if path:
            out[path] = rec
    return out


def load_staging(d: Path) -> dict:
    out = {}
    for f in sorted(d.glob("*.json")):
        rec = load_json(f)
        key = rec.get("source_path") or f.stem
        out[key] = rec
    return out


def sample_new_phonetic_lines(before: str, after: str, limit: int = 3) -> list:
    """Lines in the new text carrying phonetic characters the old text lacked."""
    old_lines = {strip_diacritics(l): l for l in (before or "").splitlines()}
    hits = []
    for line in (after or "").splitlines():
        line = line.strip()
        if len(line) < 12 or not PHONETIC_CHAR.search(line):
            continue
        prior = old_lines.get(strip_diacritics(line))
        if prior is not None and not PHONETIC_CHAR.search(prior):
            hits.append((prior.strip(), line))
            if len(hits) >= limit:
                break
    return hits


def diff_text_layer(before: dict, after: dict) -> list:
    rows = []
    for path in sorted(set(before) | set(after)):
        b, a = before.get(path), after.get(path)
        bt = (b or {}).get("text") or ""
        at = (a or {}).get("text") or ""
        bp, ap = len(PHONETIC_CHAR.findall(bt)), len(PHONETIC_CHAR.findall(at))
        rows.append(
            {
                "path": path,
                "status": "new" if b is None else "gone" if a is None else "kept",
                "before_chars": len(bt),
                "after_chars": len(at),
                "before_phonetic": bp,
                "after_phonetic": ap,
                "phonetic_delta": ap - bp,
                "before_method": (b or {}).get("text_method"),
                "after_method": (a or {}).get("text_method"),
                "samples": sample_new_phonetic_lines(bt, at) if b and a and ap > bp else [],
            }
        )
    return rows


def entry_index(rec: dict) -> dict:
    """Map diacritic-stripped headword -> set of surface forms."""
    idx = {}
    for e in rec.get("lexicon_entries") or []:
        w = (e.get("woccon") or "").strip()
        if w:
            idx.setdefault(strip_diacritics(w), set()).add(w)
    return idx


def diff_lexicon(before: dict, after: dict) -> dict:
    added, removed, respelled = [], [], []
    per_doc = []
    for path in sorted(set(before) | set(after)):
        bi = entry_index(before.get(path, {}))
        ai = entry_index(after.get(path, {}))
        doc_add = sorted(set(ai) - set(bi))
        doc_rem = sorted(set(bi) - set(ai))
        doc_res = []
        for key in set(bi) & set(ai):
            b_forms, a_forms = bi[key], ai[key]
            if a_forms == b_forms:
                continue
            gained = {f for f in a_forms if PHONETIC_CHAR.search(f)} - b_forms
            if gained:
                doc_res.append((sorted(b_forms), sorted(gained)))
        per_doc.append(
            {
                "path": path,
                "before_n": sum(len(v) for v in bi.values()),
                "after_n": sum(len(v) for v in ai.values()),
                "added": doc_add,
                "removed": doc_rem,
                "respelled": doc_res,
            }
        )
        added += doc_add
        removed += doc_rem
        respelled += doc_res
    return {"per_doc": per_doc, "added": added, "removed": removed, "respelled": respelled}


def render(text_rows: list, lex: dict) -> str:
    L = ["# Ingest run diff", ""]

    gained = [r for r in text_rows if r["phonetic_delta"] > 0]
    lost = [r for r in text_rows if r["phonetic_delta"] < 0]
    new = [r for r in text_rows if r["status"] == "new"]
    gone = [r for r in text_rows if r["status"] == "gone"]

    L += [
        "## A. Text layer",
        "",
        f"- documents compared: {len(text_rows)}",
        f"- gained phonetic notation: {len(gained)}",
        f"- lost phonetic notation: {len(lost)}",
        f"- new documents: {len(new)}",
        f"- documents no longer present: {len(gone)}",
        "",
    ]

    if gained:
        L += ["### Recovered phonetic notation", "", "| document | phonetic before | after | delta | method |", "|---|---|---|---|---|"]
        for r in sorted(gained, key=lambda x: -x["phonetic_delta"]):
            L.append(
                f"| {r['path']} | {r['before_phonetic']} | {r['after_phonetic']} | "
                f"+{r['phonetic_delta']} | {r['before_method']} to {r['after_method']} |"
            )
        L.append("")
        for r in sorted(gained, key=lambda x: -x["phonetic_delta"]):
            if not r["samples"]:
                continue
            L += [f"**{r['path']}**", ""]
            for old, newl in r["samples"]:
                L += [f"- before: `{old}`", f"  after:  `{newl}`"]
            L.append("")

    if lost:
        L += ["### Regressions: phonetic notation lost", "", "These need review before committing.", "",
              "| document | before | after | delta |", "|---|---|---|---|"]
        for r in sorted(lost, key=lambda x: x["phonetic_delta"]):
            L.append(f"| {r['path']} | {r['before_phonetic']} | {r['after_phonetic']} | {r['phonetic_delta']} |")
        L.append("")

    for label, rows in (("New documents", new), ("Documents no longer present", gone)):
        if rows:
            L += [f"### {label}", ""] + [f"- {r['path']}" for r in rows] + [""]

    L += [
        "## B. Lexicon staging",
        "",
        f"- headwords added: {len(lex['added'])}",
        f"- headwords removed: {len(lex['removed'])}",
        f"- headwords respelled with diacritics: {len(lex['respelled'])}",
        "",
    ]

    if lex["respelled"]:
        L += ["### Respelled (same word, notation restored)", "", "| was | now |", "|---|---|"]
        for old, newf in lex["respelled"]:
            L.append(f"| {', '.join(f'`{o}`' for o in old)} | {', '.join(f'`{n}`' for n in newf)} |")
        L.append("")

    L += ["### Per document", "", "| document | entries before | after | added | removed | respelled |", "|---|---|---|---|---|---|"]
    for d in lex["per_doc"]:
        if d["before_n"] == d["after_n"] and not d["added"] and not d["removed"] and not d["respelled"]:
            continue
        L.append(
            f"| {d['path']} | {d['before_n']} | {d['after_n']} | "
            f"{len(d['added'])} | {len(d['removed'])} | {len(d['respelled'])} |"
        )
    L.append("")

    if lex["added"]:
        L += ["### Added headwords", "", ", ".join(f"`{w}`" for w in lex["added"][:200]), ""]
    if lex["removed"]:
        L += ["### Removed headwords", "", "Check these against the source before accepting the run.", "",
              ", ".join(f"`{w}`" for w in lex["removed"][:200]), ""]

    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", help="pre-ingest snapshot dir (default: LAST_PRE_INGEST_SNAPSHOT)")
    ap.add_argument("--new-cache", default="data/ingest_text_cache")
    ap.add_argument("--new-staging", default="woccon_language/drive_staging_qwen_full")
    ap.add_argument("--out", default="data/backups/ingest_diff.md")
    args = ap.parse_args()

    snap = args.snapshot
    if not snap:
        marker = ROOT / "data/backups/LAST_PRE_INGEST_SNAPSHOT"
        if not marker.exists():
            print("no snapshot given and no LAST_PRE_INGEST_SNAPSHOT marker", file=sys.stderr)
            return 1
        snap = marker.read_text(encoding="utf-8").strip()
    snap_dir = (ROOT / snap) if not Path(snap).is_absolute() else Path(snap)
    if not snap_dir.exists():
        print(f"snapshot not found: {snap_dir}", file=sys.stderr)
        return 1

    new_cache = ROOT / args.new_cache
    new_staging = ROOT / args.new_staging
    if not new_staging.exists():
        print(f"warning: {new_staging} does not exist; lexicon diff will show removals only", file=sys.stderr)

    text_rows = diff_text_layer(
        load_text_cache(snap_dir / "ingest_text_cache"),
        load_text_cache(new_cache),
    )
    lex = diff_lexicon(
        load_staging(snap_dir / "drive_staging"),
        load_staging(new_staging) if new_staging.exists() else {},
    )

    report = render(text_rows, lex)
    out = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")

    gained = sum(1 for r in text_rows if r["phonetic_delta"] > 0)
    lost = sum(1 for r in text_rows if r["phonetic_delta"] < 0)
    print(f"snapshot:  {snap_dir}")
    print(f"text layer: {len(text_rows)} docs, {gained} gained notation, {lost} lost")
    print(f"lexicon:    +{len(lex['added'])} / -{len(lex['removed'])} / {len(lex['respelled'])} respelled")
    print(f"report:     {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
