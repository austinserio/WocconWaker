#!/usr/bin/env python3
"""
Compare Sonnet vs Haiku extraction outputs.
Reads drive_staging/ (Sonnet) and drive_staging_haiku/ (Haiku), compares counts and lexicon overlap per file and overall.
"""
import json
import os
from pathlib import Path

SONNET_DIR = "woccon_language/drive_staging"
HAIKU_DIR = "woccon_language/drive_staging_haiku"
SKIP = {"manifest.json", "sync_state.json"}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _lexicon_key(e: dict) -> str:
    return _norm(e.get("woccon") or "")


def load_staging(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    base = Path(__file__).resolve().parent.parent
    sonnet_path = base / SONNET_DIR
    haiku_path = base / HAIKU_DIR
    if not sonnet_path.exists():
        print(f"Missing {SONNET_DIR}")
        return
    if not haiku_path.exists():
        print(f"Missing {HAIKU_DIR}")
        return

    sonnet_files = {p.name for p in sonnet_path.glob("*.json") if p.name not in SKIP}
    haiku_files = {p.name for p in haiku_path.glob("*.json") if p.name not in SKIP}
    common = sorted(sonnet_files & haiku_files)
    only_sonnet = sorted(sonnet_files - haiku_files)
    only_haiku = sorted(haiku_files - sonnet_files)

    totals_s = {"lexicon": 0, "grammar": 0, "pronunciation": 0, "cultural": 0, "files": 0}
    totals_h = {"lexicon": 0, "grammar": 0, "pronunciation": 0, "cultural": 0, "files": 0}
    total_lexicon_overlap = 0
    total_lexicon_only_s = 0
    total_lexicon_only_h = 0

    print("=" * 60)
    print("Sonnet vs Haiku extraction comparison")
    print("=" * 60)
    print(f"Sonnet dir: {sonnet_path}")
    print(f"Haiku dir:  {haiku_path}")
    print(f"Common files: {len(common)}  |  Only in Sonnet: {len(only_sonnet)}  |  Only in Haiku: {len(only_haiku)}")
    if only_sonnet:
        print(f"  Only Sonnet: {only_sonnet[:10]}{'...' if len(only_sonnet) > 10 else ''}")
    if only_haiku:
        print(f"  Only Haiku:  {only_haiku[:10]}{'...' if len(only_haiku) > 10 else ''}")
    print()

    rows = []
    for name in common:
        s = load_staging(sonnet_path / name)
        h = load_staging(haiku_path / name)
        if not s or not h:
            continue
        ls = s.get("lexicon_entries") or []
        lh = h.get("lexicon_entries") or []
        gs = len(s.get("grammar_notes") or [])
        gh = len(h.get("grammar_notes") or [])
        ps = len(s.get("pronunciation_notes") or [])
        ph = len(h.get("pronunciation_notes") or [])
        cs = len(s.get("cultural_notes") or [])
        ch = len(h.get("cultural_notes") or [])

        totals_s["lexicon"] += len(ls)
        totals_s["grammar"] += gs
        totals_s["pronunciation"] += ps
        totals_s["cultural"] += cs
        totals_s["files"] += 1
        totals_h["lexicon"] += len(lh)
        totals_h["grammar"] += gh
        totals_h["pronunciation"] += ph
        totals_h["cultural"] += ch
        totals_h["files"] += 1

        keys_s = {_lexicon_key(e) for e in ls if _lexicon_key(e)}
        keys_h = {_lexicon_key(e) for e in lh if _lexicon_key(e)}
        overlap = len(keys_s & keys_h)
        only_s = len(keys_s - keys_h)
        only_h = len(keys_h - keys_s)
        total_lexicon_overlap += overlap
        total_lexicon_only_s += only_s
        total_lexicon_only_h += only_h

        rows.append({
            "file": name,
            "lex_s": len(ls), "lex_h": len(lh),
            "gram_s": gs, "gram_h": gh,
            "pron_s": ps, "pron_h": ph,
            "cult_s": cs, "cult_h": ch,
            "overlap": overlap, "only_s": only_s, "only_h": only_h,
        })

    # Totals
    print("--- Totals (common files only) ---")
    print(f"  Lexicon:      Sonnet {totals_s['lexicon']}  |  Haiku {totals_h['lexicon']}  |  diff {totals_h['lexicon'] - totals_s['lexicon']:+d}")
    print(f"  Grammar:      Sonnet {totals_s['grammar']}  |  Haiku {totals_h['grammar']}  |  diff {totals_h['grammar'] - totals_s['grammar']:+d}")
    print(f"  Pronunciation: Sonnet {totals_s['pronunciation']}  |  Haiku {totals_h['pronunciation']}  |  diff {totals_h['pronunciation'] - totals_s['pronunciation']:+d}")
    print(f"  Cultural:     Sonnet {totals_s['cultural']}  |  Haiku {totals_h['cultural']}  |  diff {totals_h['cultural'] - totals_s['cultural']:+d}")
    print()
    print("--- Lexicon overlap (by woccon key) ---")
    print(f"  In both: {total_lexicon_overlap}  |  Only Sonnet: {total_lexicon_only_s}  |  Only Haiku: {total_lexicon_only_h}")
    print()

    # Per-file table (sample: first 15 and any with big diff)
    print("--- Per-file counts (lexicon | grammar | pron | cultural) ---")
    print(f"{'File':<50} {'Sonnet':>20} {'Haiku':>20} {'Overlap':>8}")
    print("-" * 100)
    for r in rows[:15]:
        ss = f"{r['lex_s']} | {r['gram_s']} | {r['pron_s']} | {r['cult_s']}"
        hh = f"{r['lex_h']} | {r['gram_h']} | {r['pron_h']} | {r['cult_h']}"
        short = r["file"][:48] + ".." if len(r["file"]) > 50 else r["file"]
        print(f"{short:<50} {ss:>20} {hh:>20} {r['overlap']:>8}")
    if len(rows) > 15:
        print("...")
        for r in rows[-5:]:
            ss = f"{r['lex_s']} | {r['gram_s']} | {r['pron_s']} | {r['cult_s']}"
            hh = f"{r['lex_h']} | {r['gram_h']} | {r['pron_h']} | {r['cult_h']}"
            short = r["file"][:48] + ".." if len(r["file"]) > 50 else r["file"]
            print(f"{short:<50} {ss:>20} {hh:>20} {r['overlap']:>8}")
    print()
    # Files with largest lexicon diff
    rows_by_diff = sorted(rows, key=lambda x: abs(x["lex_s"] - x["lex_h"]), reverse=True)
    print("--- Files with largest lexicon count difference (Sonnet - Haiku) ---")
    for r in rows_by_diff[:8]:
        d = r["lex_s"] - r["lex_h"]
        if d == 0:
            continue
        print(f"  {r['lex_s'] - r['lex_h']:+4d}  {r['file']}")
    print("Done.")


if __name__ == "__main__":
    main()
