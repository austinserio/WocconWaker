"""Pronunciation guide → Kokoro TTS text, content hashes, and audio URLs."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from panel_api.services.pronunciation import (
    normalize_pronunciation,
    pronunciation_guide_candidates,
)

# Skip guides that look like grammar notes rather than speakable syllables.
_NON_GUIDE_RE = re.compile(
    r"(=|\bmarker\b|\bmode\b|\bquestioning\b|\bgrammar\b|\baffix\b|\bmorpheme\b)",
    re.I,
)
# Bibliographic citations misparsed as pronunciation (LLM ingest noise).
_CITATION_RE = re.compile(
    r"\[(?:Carter|Rudes|Waccamaw|\*\*)|^\[[^\]]*\d{3,4}",
    re.I,
)
# Common English words that together form semantic glosses (not phonetic respellings).
_COMMON_GLOSS_WORDS = frozenset(
    {
        "little",
        "man",
        "woman",
        "wind",
        "blowing",
        "angry",
        "tree",
        "lined",
        "river",
        "place",
        "acorn",
    }
)


def prepare_tts_text(pronunciation: str | None) -> str | None:
    """Normalize a guide and format for Kokoro (hyphens → spaces)."""
    clean = normalize_pronunciation(pronunciation)
    if not clean:
        return None
    return clean.replace("-", " ").strip() or None


def _looks_like_english_gloss(clean: str) -> bool:
    """True for multi-word semantic explanations, not space-separated syllable respellings."""
    if " " not in clean or "-" in clean:
        return False
    words = [w for w in clean.split() if w.isalpha()]
    if len(words) < 2 or not all(w.islower() for w in words):
        return False
    # Respellings often use non-words (ayk, wahw); glosses use ordinary English.
    return all(w in _COMMON_GLOSS_WORDS for w in words)


def is_speakable_pronunciation(pronunciation: str | None) -> bool:
    """True when the string looks like a syllable guide, not a grammar note or gloss."""
    clean = normalize_pronunciation(pronunciation)
    if not clean:
        return False
    if _NON_GUIDE_RE.search(clean):
        return False
    if _CITATION_RE.search(clean):
        return False
    if _looks_like_english_gloss(clean):
        return False
    return True


def synthesis_speed_for_guide(phoneme_string: str | None, default_speed: float = 0.8) -> float:
    """Slow down very short clips (e.g. hay → /hA/) so they remain audible."""
    if not phoneme_string:
        return default_speed
    compact = phoneme_string.replace(" ", "")
    if len(compact) <= 4:
        return min(default_speed, 0.55)
    if len(compact) <= 8:
        return min(default_speed, 0.65)
    return default_speed


def pronunciation_content_hash(pronunciation: str | None) -> str | None:
    """Stable SHA1 for normalized TTS input (shared across entries with same guide)."""
    text = prepare_tts_text(pronunciation)
    if not text:
        return None
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def get_pronunciation_audio_dir() -> Path:
    return Path(os.environ.get("PRONUNCIATION_AUDIO_DIR", "data/pronunciation_audio"))


def slugify_label(text: str, max_len: int = 60) -> str:
    """Filesystem-safe slug for human-readable audio filenames."""
    s = (text or "").strip()
    s = re.sub(r"[^\w\s\-]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip().replace(" ", "-")
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s or "unknown"


def audio_filename(woccon: str, english: str, pronunciation: str | None) -> str:
    """e.g. roosome - Acorns (rue-sa-may).mp3"""
    w = slugify_label(woccon, 40)
    e = slugify_label(english or "unknown", 50)
    guide = slugify_label(normalize_pronunciation(pronunciation) or "no-guide", 40)
    return f"{w} - {e} ({guide}).mp3"


def pick_primary_lexicon_row(rows: list[dict]) -> dict:
    """Choose a stable label source when several entries share one pronunciation."""
    if not rows:
        return {"woccon": "unknown", "english": "unknown", "id": ""}
    return sorted(
        rows,
        key=lambda r: (
            (r.get("woccon") or "").lower(),
            (r.get("english") or "").lower(),
        ),
    )[0]


def unique_audio_filename(
    woccon: str,
    english: str,
    pronunciation: str | None,
    *,
    audio_dir: Path | None = None,
    reserved: set[str] | None = None,
) -> str:
    """Return a unique human-readable filename under audio_dir."""
    root = audio_dir or get_pronunciation_audio_dir()
    taken = set(reserved or ())
    base = audio_filename(woccon, english, pronunciation)
    if base not in taken and not (root / base).exists():
        return base
    stem = base[:-4]
    n = 2
    while True:
        candidate = f"{stem}__{n}.mp3"
        if candidate not in taken and not (root / candidate).exists():
            return candidate
        n += 1


def audio_file_path(filename: str, audio_dir: Path | None = None) -> Path:
    root = audio_dir or get_pronunciation_audio_dir()
    return root / filename


def manifest_entry_for_pronunciation(
    pronunciation: str | None,
    audio_dir: Path | None = None,
) -> dict[str, Any] | None:
    content_hash = pronunciation_content_hash(pronunciation)
    if not content_hash:
        return None
    manifest = load_manifest(audio_dir)
    entry = manifest.get("entries", {}).get(content_hash)
    return entry if isinstance(entry, dict) else None


def pronunciation_audio_url(pronunciation: str | None) -> str | None:
    """Relative API path when a pre-generated clip exists for this guide."""
    resolved = resolve_pronunciation_with_audio(pronunciation)
    if not resolved:
        return None
    _guide, rel = resolved
    return rel


def resolve_pronunciation_with_audio(
    pronunciation: str | None,
) -> tuple[str, str] | None:
    """Return (matched guide, relative API path) for the first clip-backed variant."""
    for candidate in pronunciation_guide_candidates(pronunciation):
        if not is_speakable_pronunciation(candidate):
            continue
        entry = manifest_entry_for_pronunciation(candidate)
        if not entry:
            continue
        filename = entry.get("filename")
        if not filename:
            continue
        path = audio_file_path(filename)
        if not path.is_file():
            continue
        return candidate, f"/api/pronunciation-audio/{quote(filename)}"
    return None


def pronunciation_audio_hash_url(pronunciation: str | None) -> str | None:
    """Stable hash-only API path for external fetchers (Messenger, etc.)."""
    for candidate in pronunciation_guide_candidates(pronunciation):
        if not is_speakable_pronunciation(candidate):
            continue
        content_hash = pronunciation_content_hash(candidate)
        if not content_hash:
            continue
        entry = manifest_entry_for_pronunciation(candidate)
        if not entry:
            continue
        filename = entry.get("filename")
        if not filename:
            continue
        path = audio_file_path(filename)
        if not path.is_file():
            continue
        return f"/api/pronunciation-audio/clip/{content_hash}"
    return None


def audio_path_for_content_hash(content_hash: str, audio_dir: Path | None = None) -> Path | None:
    """Resolve a manifest clip path from its pronunciation content hash."""
    if not re.fullmatch(r"[0-9a-f]{40}", content_hash or ""):
        return None
    manifest = load_manifest(audio_dir)
    entry = manifest.get("entries", {}).get(content_hash)
    if not isinstance(entry, dict):
        return None
    filename = entry.get("filename")
    if not filename:
        return None
    path = audio_file_path(filename, audio_dir)
    return path if path.is_file() else None


def is_publicly_fetchable_base(url: str) -> bool:
    """True when Facebook can fetch an attachment URL (HTTPS, non-localhost)."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith(".local"):
        return False
    return True


def public_base_url() -> str | None:
    """HTTPS base for externally reachable assets (Messenger audio attachments, etc.)."""
    for key in (
        "PUBLIC_WEBHOOK_BASE_URL",
        "AZURE_CONTAINER_APP_WEBHOOK_URL",
    ):
        value = (os.environ.get(key) or "").strip().rstrip("/")
        if value and is_publicly_fetchable_base(value):
            return value
    return None


def public_pronunciation_audio_url(
    pronunciation: str | None,
    *,
    messenger: bool = False,
) -> str | None:
    """Absolute HTTPS URL when a clip exists and a public base URL is configured."""
    rel = (
        pronunciation_audio_hash_url(pronunciation)
        if messenger
        else pronunciation_audio_url(pronunciation)
    )
    if not rel:
        return None
    base = public_base_url()
    if not base:
        return None
    return f"{base}{rel}"


def load_manifest(audio_dir: Path | None = None) -> dict[str, Any]:
    root = audio_dir or get_pronunciation_audio_dir()
    path = root / "manifest.json"
    if not path.is_file():
        return {"version": 2, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 2, "entries": {}}
    if not isinstance(data, dict):
        return {"version": 2, "entries": {}}
    data.setdefault("version", 2)
    data.setdefault("entries", {})
    return data


def save_manifest(manifest: dict[str, Any], audio_dir: Path | None = None) -> None:
    root = audio_dir or get_pronunciation_audio_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cleanup_stale_audio(audio_dir: Path, keep_filenames: set[str]) -> int:
    """Remove old hash-named clips, symlinks, and labeled/ folder leftovers."""
    removed = 0
    labeled_dir = audio_dir / "labeled"
    if labeled_dir.is_dir():
        for child in labeled_dir.iterdir():
            child.unlink(missing_ok=True)
            removed += 1
        labeled_dir.rmdir()
    for mp3 in audio_dir.glob("*.mp3"):
        if mp3.name not in keep_filenames:
            mp3.unlink(missing_ok=True)
            removed += 1
    return removed
