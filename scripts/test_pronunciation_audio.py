#!/usr/bin/env python3
"""Unit tests for pronunciation audio helpers."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from panel_api.services.pronunciation_audio import (  # noqa: E402
    audio_filename,
    is_speakable_pronunciation,
    prepare_tts_text,
    pronunciation_content_hash,
    pronunciation_audio_url,
)


def test_prepare_tts_text():
    assert prepare_tts_text("(rue-sa-may)") == "rue sa may"
    assert prepare_tts_text("RUE-chay-ha") == "RUE chay ha"
    assert prepare_tts_text(None) is None


def test_is_speakable():
    assert is_speakable_pronunciation("rue-sa-may")
    assert is_speakable_pronunciation("hay")
    assert not is_speakable_pronunciation("mo= good and ne= questioning mode marker")
    assert not is_speakable_pronunciation("little man")
    assert not is_speakable_pronunciation("[Carter, 173]")
    assert not is_speakable_pronunciation("[Rudes(2000), 240]")
    assert not is_speakable_pronunciation("wind blowing angry")
    assert not is_speakable_pronunciation("")


def test_synthesis_speed_short():
    from panel_api.services.pronunciation_audio import synthesis_speed_for_guide

    assert synthesis_speed_for_guide("hA", 0.8) == 0.55
    assert synthesis_speed_for_guide("ɹˈu ʧA hɑ", 0.8) == 0.65
    assert synthesis_speed_for_guide("jAn dɑ ɹA wɑwə", 0.8) == 0.8


def test_hash_stable():
    h1 = pronunciation_content_hash("rue-sa-may")
    h2 = pronunciation_content_hash("(rue-sa-may)")
    assert h1 == h2
    assert h1 and len(h1) == 40


def test_audio_filename():
    name = audio_filename("roosome", "Acorns", "rue-sa-may")
    assert name == "roosome - Acorns (rue-sa-may).mp3"


def test_audio_url_missing_file():
    assert pronunciation_audio_url("nonexistent-guide-xyz-abc") is None


def main() -> int:
    test_prepare_tts_text()
    test_is_speakable()
    test_synthesis_speed_short()
    test_hash_stable()
    test_audio_filename()
    test_audio_url_missing_file()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
