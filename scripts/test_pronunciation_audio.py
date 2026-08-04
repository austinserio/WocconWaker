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
    audio_path_for_content_hash,
    is_publicly_fetchable_base,
    is_speakable_pronunciation,
    prepare_tts_text,
    pronunciation_audio_hash_url,
    pronunciation_content_hash,
    pronunciation_audio_url,
    public_base_url,
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
    assert is_speakable_pronunciation("way ayk")
    assert is_speakable_pronunciation("hay")
    assert not is_speakable_pronunciation("")


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


def test_hash_url_for_ejau():
    rel = pronunciation_audio_hash_url("ay-jah-oo")
    assert rel == "/api/pronunciation-audio/h/68e905ba6ac1fa508b6814f81e4e4a16140d82f4.mp3"
    path = audio_path_for_content_hash("68e905ba6ac1fa508b6814f81e4e4a16140d82f4")
    assert path is not None
    assert path.name == "ejau - Water (ay-jah-oo).mp3"


def test_public_base_url_rejects_localhost(monkeypatch=None):
    import os

    saved = {
        k: os.environ.get(k)
        for k in (
            "PUBLIC_WEBHOOK_BASE_URL",
            "AZURE_CONTAINER_APP_WEBHOOK_URL",
            "PANEL_PUBLIC_BASE_URL",
        )
    }
    try:
        os.environ.pop("PUBLIC_WEBHOOK_BASE_URL", None)
        os.environ.pop("AZURE_CONTAINER_APP_WEBHOOK_URL", None)
        os.environ["PANEL_PUBLIC_BASE_URL"] = "http://localhost:5173"
        assert public_base_url() is None

        os.environ.pop("PANEL_PUBLIC_BASE_URL", None)
        os.environ["PUBLIC_WEBHOOK_BASE_URL"] = "https://woccon-dev.example.com"
        assert public_base_url() == "https://woccon-dev.example.com"
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_is_publicly_fetchable_base():
    assert is_publicly_fetchable_base("https://woccon-dev.example.com")
    assert not is_publicly_fetchable_base("http://woccon-dev.example.com")
    assert not is_publicly_fetchable_base("https://localhost:8000")
    assert not is_publicly_fetchable_base("https://127.0.0.1")


def main() -> int:
    test_prepare_tts_text()
    test_is_speakable()
    test_hash_stable()
    test_audio_filename()
    test_audio_url_missing_file()
    test_hash_url_for_ejau()
    test_public_base_url_rejects_localhost()
    test_is_publicly_fetchable_base()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
