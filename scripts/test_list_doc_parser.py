#!/usr/bin/env python3
"""Unit tests for list_doc_parser hybrid extract."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from list_doc_parser import (  # noqa: E402
    lexicon_merge_key,
    merge_parser_and_llm_lexicon,
    parse_list_document,
    parse_list_line,
)
from drive_extract import _repair_lexicon_fields, _validate_extraction  # noqa: E402


def test_parse_known_lines() -> None:
    cases = [
        ("Rum= yup se", "yup se", "Rum", None),
        ("Got anything to eat?= noccoo eraute (no-CHOO-ay-rahw-tay)", "noccoo eraute", "Got anything to eat?", "no-CHOO-ay-rahw-tay"),
        ("Ten= soone noponne (SUE-nay no-po-nay)", "soone noponne", "Ten", "SUE-nay no-po-nay"),
        ("Arrow= wą'se (WAWN-she)", "wą'se", "Arrow", "WAWN-she"),
        ("Will you go along with me?= Quake (qwah-kay)", "Quake", "Will you go along with me?", "qwah-kay"),
        ("Angry= roocheha (RUE-chay-ha) ( capital here means that it is longer/emphasis)", "roocheha", "Angry", "RUE-chay-ha"),
        ("Bear= nomme [Rudes(2000) 240]", "nomme", "Bear", None),
        ("One: tonne", "tonne", "One", None),
    ]
    for line, exp_w, exp_e, exp_p in cases:
        parsed = parse_list_line(line)
        assert parsed is not None, f"failed to parse: {line!r}"
        assert parsed.woccon == exp_w, f"{line}: woccon {parsed.woccon!r} != {exp_w!r}"
        assert parsed.english == exp_e, f"{line}: english {parsed.english!r} != {exp_e!r}"
        if exp_p:
            assert parsed.pronunciation == exp_p, f"{line}: pron {parsed.pronunciation!r}"


def test_duplicate_woccon_different_english() -> None:
    text = "Chert= wonsh-shee\nNeedle= wonsh-shee (wohnsh-shee)"
    entries = parse_list_document(text, section="full")
    keys = {lexicon_merge_key(e["woccon"], e["english"]) for e in entries}
    assert len(entries) == 2
    assert len(keys) == 2


def test_merge_parser_and_llm() -> None:
    parser = [
        {"woccon": "noccoo eraute", "english": "Got anything to eat?", "pos": "phrase", "pronunciation": None},
    ]
    llm = [
        {
            "woccon": "noccoo eraute",
            "english": "Got anything to eat?",
            "pos": "verb phrase",
            "pronunciation": "no-CHOO-ay-rahw-tay",
            "source_excerpt": "Got anything to eat?= noccoo eraute",
        },
        {"woccon": "Quake", "english": "Will you go along with me?", "pos": "verb", "pronunciation": "qwah-kay"},
    ]
    merged, audit = merge_parser_and_llm_lexicon(parser, llm)
    assert audit["parser_count"] == 1
    assert audit["llm_count"] == 2
    assert audit["merged_count"] == 2
    by_key = {lexicon_merge_key(e["woccon"], e["english"]): e for e in merged}
    row = by_key[lexicon_merge_key("noccoo eraute", "Got anything to eat?")]
    assert row["extraction_method"] == "merged"
    assert row["pronunciation"] == "no-CHOO-ay-rahw-tay"
    assert by_key[lexicon_merge_key("Quake", "Will you go along with me?")]["extraction_method"] == "llm"


def test_validate_repair_malformed_woccon() -> None:
    raw = {
        "lexicon_entries": [
            {"woccon": "Ten=soone noponne", "english": "Theirs", "pos": "numeral"},
        ],
        "grammar_notes": [],
        "pronunciation_notes": [],
        "cultural_notes": [],
    }
    ok, normalized, audit = _validate_extraction(raw)
    assert ok
    assert len(normalized["lexicon_entries"]) == 1
    assert normalized["lexicon_entries"][0]["woccon"] == "soone noponne"
    assert normalized["lexicon_entries"][0]["english"] == "Ten"
    assert len(audit["repaired_malformed_woccon"]) == 1


def test_validate_repair_fields_helper() -> None:
    w, e, reason = _repair_lexicon_fields("Ten=soone noponne", "Theirs")
    assert reason == "repaired_malformed_woccon"
    assert w == "soone noponne"
    assert e == "Ten"


def test_source_list_completeness() -> None:
    from scripts.compare_english_woccon_source import SOURCE_ENTRIES, parse_source

    text = SOURCE_ENTRIES
    parsed = parse_list_document(text, section="full")
    parsed_keys = {lexicon_merge_key(e["woccon"], e["english"]) for e in parsed}
    missing = []
    for eng, woc in parse_source(SOURCE_ENTRIES):
        if lexicon_merge_key(woc, eng) not in parsed_keys:
            missing.append(f"{eng} = {woc}")
    assert len(missing) <= 5, f"too many missing from canonical source: {missing[:10]}"


def test_possible_words_section() -> None:
    text = """
English-Woccon
Acorns= roosome
-re= he is
Possible Words:
Coffee= ejause (bitter water?)
Ball=wap (as in Wap-ka-hare=ball knock)
Could "Roa"= leader?  More=good or excel at, Roamore=king
In all but Crow (aho) Tutelo () and Catawba (Hawuh)- thank you= hahó
Known names:
"""
    entries = parse_list_document(text, section="english_woccon")
    keys = {lexicon_merge_key(e["woccon"], e["english"]) for e in entries}
    for w, eng in [
        ("ejause", "Coffee"),
        ("wap", "Ball"),
        ("Roa", "leader?"),
        ("hahó", "thank you"),
    ]:
        assert lexicon_merge_key(w, eng) in keys, f"missing {eng} = {w}"
    pw = [e for e in entries if e.get("source_section") == "possible_words"]
    assert pw, "expected possible_words rows"
    assert any(e.get("confidence") == "possible" for e in pw)


def test_carry_forward_and_completeness() -> None:
    from list_doc_parser import (
        audit_dropped_vs_previous,
        check_lexicon_completeness,
        collect_parser_candidate_keys,
        merge_carry_forward,
    )

    text = """
English-Woccon
Coffee= ejause
Possible Words:
Ball=wap
Known names:
"""
    parser_keys = collect_parser_candidate_keys(text, section="english_woccon")
    merged = [{"woccon": "ejause", "english": "Coffee", "extraction_method": "parser"}]
    previous = [
        {"woccon": "wap", "english": "Ball", "extraction_method": "llm"},
        {"woccon": "rum", "english": "yup se", "extraction_method": "llm"},
    ]
    out, carry = merge_carry_forward(merged, previous, parser_keys)
    assert carry["carried_forward_count"] == 1
    assert any(e["woccon"] == "wap" for e in out)
    completeness = check_lexicon_completeness(text, out)
    assert completeness["missing_count"] == 0
    dropped = audit_dropped_vs_previous(out, previous)
    assert len(dropped) == 1
    assert dropped[0]["woccon"] == "rum"


def main() -> int:
    tests = [
        test_parse_known_lines,
        test_duplicate_woccon_different_english,
        test_merge_parser_and_llm,
        test_possible_words_section,
        test_carry_forward_and_completeness,
        test_validate_repair_malformed_woccon,
        test_validate_repair_fields_helper,
        test_source_list_completeness,
    ]
    for fn in tests:
        fn()
        print(f"OK {fn.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
