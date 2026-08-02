#!/usr/bin/env python3
"""Verify Catawba sources cannot contribute vocabulary to the Woccon lexicon.

Catawba is comparative evidence for reconstructing Woccon, not Woccon. The pipeline had no
concept of content language, so a Catawba word list in the Drive corpus would have been sent
to the Woccon extraction prompt and merged into dictionary_unified.json. These checks cover
each layer that now guards against that, including the case where the model ignores the
Catawba prompt and returns Woccon entries anyway.

    python scripts/test_content_language_guard.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import content_language as cl  # noqa: E402
import drive_extract  # noqa: E402
from merge_staging import load_staging_files  # noqa: E402
from panel_api.extraction_config import build_extraction_prompt  # noqa: E402

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{'  ' + detail if detail and not cond else ''}")
    if not cond:
        failures.append(label)


def test_classification() -> None:
    print("\nfolder classification")
    check("Catawba folder is catawba",
          cl.classify_path("Catawba Language/Speck-CatawbaTexts-1934.pdf") == cl.CATAWBA)
    check("context folder is context",
          cl.classify_path("Catawba Nation - Context/Mongiello-2025.pdf") == cl.CONTEXT)
    check("plain article is woccon",
          cl.classify_path("Articles/Carter-WocconLanguageNorth-1980.pdf") == cl.WOCCON)
    # The decisive case: a Woccon source whose title contains "Catawban".
    check("'Resurrecting Coastal Catawban' stays woccon",
          cl.classify_path(
              "Articles/Resurrecting Coastal Catawban - The Reconstitudes Phonology "
              "and Morpology of the Woccon Language"
          ) == cl.WOCCON)
    check("nested Catawba folder still catawba",
          cl.classify_path("Articles/Sub/Catawba Language/x.pdf") == cl.CATAWBA)
    check("missing path defaults to woccon", cl.classify_path(None) == cl.WOCCON)


def test_prompt() -> None:
    print("\nextraction prompt routing")
    cat = build_extraction_prompt(context_header="H", text="T", focus="catawba_lexicon")
    check("catawba prompt requests catawba_entries", "catawba_entries" in cat)
    check("catawba prompt never requests Woccon vocabulary", "Woccon vocabulary" not in cat)
    check("catawba prompt demands diacritic fidelity", "diacritic" in cat.lower())
    gen = build_extraction_prompt(context_header="H", text="T", focus="general")
    check("general prompt still requests Woccon vocabulary", "Woccon vocabulary" in gen)


def test_extraction_drops_woccon_from_catawba_source() -> None:
    """The model may ignore the prompt. The merge step must drop Woccon rows anyway."""
    print("\nextraction guard (model returns Woccon rows for a Catawba source)")
    rogue = {
        "lexicon_entries": [{"woccon": "kus", "english": "corn"}],
        "catawba_entries": [{"catawba": "kus", "english": "maize"}],
        "grammar_notes": [{"text": "Catawba marks plurals with a suffix."}],
        "pronunciation_notes": [],
        "cultural_notes": [],
    }
    original = drive_extract.extract_from_chunk
    drive_extract.extract_from_chunk = lambda *a, **k: dict(rogue)
    try:
        out = drive_extract.extract_one_file(
            "some catawba source text", "Catawba Language/Speck-CatawbaTexts-1934.pdf"
        )
    finally:
        drive_extract.extract_from_chunk = original

    check("content_language recorded as catawba", out.get("content_language") == cl.CATAWBA)
    check("no Woccon lexicon entries survive", out.get("lexicon_entries") == [],
          f"got {out.get('lexicon_entries')}")
    check("catawba entries kept", len(out.get("catawba_entries") or []) == 1)
    check("dropped rows are audited",
          int((out.get("audit") or {}).get("dropped_non_woccon_source") or 0) == 1)
    check("grammar notes still collected", len(out.get("grammar_notes") or []) == 1)


def test_staging_separation() -> None:
    print("\nstaging separation")
    with tempfile.TemporaryDirectory() as tmp:
        woccon_dir = os.path.join(tmp, "drive_staging")
        os.makedirs(woccon_dir, exist_ok=True)
        cat_dir = cl.staging_dir_for(cl.CATAWBA, woccon_dir)
        check("catawba stages to its own directory", os.path.abspath(cat_dir) != os.path.abspath(woccon_dir),
              f"{cat_dir} == {woccon_dir}")
        check("woccon stages in place", cl.staging_dir_for(cl.WOCCON, woccon_dir) == woccon_dir)


def test_merge_refuses_non_woccon() -> None:
    print("\nmerge guard")
    with tempfile.TemporaryDirectory() as tmp:
        def write(name, payload):
            Path(tmp, name).write_text(json.dumps(payload), encoding="utf-8")

        write("a.json", {"source_path": "Articles/Rudes.pdf",
                         "lexicon_entries": [{"woccon": "yau", "english": "fire"}]})
        write("b.json", {"source_path": "Catawba Language/Speck.pdf",
                         "content_language": "catawba",
                         "lexicon_entries": [{"woccon": "kus", "english": "corn"}]})
        # No content_language field: the path fallback must still catch it.
        write("c.json", {"source_path": "Catawba Language/Lieber.pdf",
                         "lexicon_entries": [{"woccon": "yap", "english": "wood"}]})
        write("d.json", {"source_path": "Catawba Nation - Context/Casino.pdf",
                         "content_language": "context",
                         "lexicon_entries": [{"woccon": "x", "english": "y"}]})
        loaded = load_staging_files(tmp)
        paths = [d["source_path"] for d in loaded]
        check("only the Woccon staging file is merged", paths == ["Articles/Rudes.pdf"], f"got {paths}")


def main() -> int:
    print("Catawba/Woccon separation guard")
    test_classification()
    test_prompt()
    test_extraction_drops_woccon_from_catawba_source()
    test_staging_separation()
    test_merge_refuses_non_woccon()
    print(f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILURE(S): ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
