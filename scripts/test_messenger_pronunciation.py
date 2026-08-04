#!/usr/bin/env python3
"""Unit tests for Messenger pronunciation intent detection and lookup."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from messenger_pronunciation import (  # noqa: E402
    find_lexicon_entry,
    format_pronunciation_text,
    parse_pronunciation_query,
    resolve_pronunciation_response,
)


SAMPLE_LEXICON = [
    {
        "woccon": "roosome",
        "english": "Acorns",
        "pronunciation": "rue-sa-may",
        "is_base_entry": True,
    },
    {
        "woccon": "week",
        "english": "Shot",
        "pronunciation": "way ayk",
        "is_base_entry": True,
    },
    {
        "woccon": "hay",
        "english": "Something",
        "pronunciation": None,
        "is_base_entry": True,
    },
]


def test_parse_pronunciation_query():
    assert parse_pronunciation_query("How do I pronounce roosome?") == "roosome"
    assert parse_pronunciation_query("how is roosome pronounced") == "roosome"
    assert parse_pronunciation_query("pronunciation of Acorns") == "Acorns"
    assert parse_pronunciation_query("How to pronounce week") == "week"
    assert parse_pronunciation_query("What is the pronunciation of week?") == "week"
    assert parse_pronunciation_query("pronounce roosome") == "roosome"
    assert parse_pronunciation_query("What does roosome mean?") is None
    assert parse_pronunciation_query("Hello") is None


def test_find_lexicon_entry():
    assert find_lexicon_entry(SAMPLE_LEXICON, "roosome")["english"] == "Acorns"
    assert find_lexicon_entry(SAMPLE_LEXICON, "Acorns")["woccon"] == "roosome"
    assert find_lexicon_entry(SAMPLE_LEXICON, "acorns")["woccon"] == "roosome"
    assert find_lexicon_entry(SAMPLE_LEXICON, "missing") is None


def test_resolve_without_audio():
    result = resolve_pronunciation_response(SAMPLE_LEXICON, "roosome")
    assert result is not None
    assert result["woccon"] == "roosome"
    assert result["pronunciation"] == "rue-sa-may"
    assert result["has_audio"] is False
    assert result["audio_url"] is None


def test_format_text_fallback():
    text = format_pronunciation_text(
        {
            "woccon": "roosome",
            "english": "Acorns",
            "pronunciation": "rue-sa-may",
            "has_audio": False,
        }
    )
    assert "roosome" in text
    assert "rue-sa-may" in text
    assert "pre-recorded clip" in text

    no_guide = format_pronunciation_text(
        {
            "woccon": "hay",
            "english": "Something",
            "pronunciation": None,
            "has_audio": False,
        }
    )
    assert "pronunciation guide" in no_guide.lower()


def main() -> int:
    test_parse_pronunciation_query()
    test_find_lexicon_entry()
    test_resolve_without_audio()
    test_format_text_fallback()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
