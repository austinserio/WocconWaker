"""Build Kokoro IPA overrides from community pronunciation guides (CAPS = stress)."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Callable

from panel_api.services.pronunciation import normalize_pronunciation

# Kokoro / misaki phoneme vocabulary helpers (mirrored from misaki.en).
PRIMARY_STRESS = "ˈ"
SECONDARY_STRESS = "ˌ"
VOWELS = frozenset("AIOQWYaiuæɑɒɔəɛɜɪʊʌᵻ")

# Prefer first alternative when guides contain " or ".
_OR_SPLIT_RE = re.compile(r"\s+or\s+", re.I)


def _strip_stress_marks(phonemes: str) -> str:
    return phonemes.replace(PRIMARY_STRESS, "").replace(SECONDARY_STRESS, "")


def _primary_stress_before_first_vowel(phonemes: str) -> str:
    ps = _strip_stress_marks(phonemes)
    for i, ch in enumerate(ps):
        if ch in VOWELS:
            return ps[:i] + PRIMARY_STRESS + ps[i:]
    return ps


def _syllable_is_stressed(chunk: str) -> bool:
    letters = [c for c in chunk if c.isalpha()]
    return bool(letters) and any(c.isupper() for c in letters)


def _split_guide_syllables(guide: str) -> list[tuple[str, bool]]:
    """Split on spaces and hyphens; CAPS in a chunk marks community stress."""
    text = _OR_SPLIT_RE.split(guide, maxsplit=1)[0].strip()
    syllables: list[tuple[str, bool]] = []
    for word in text.split():
        for part in word.split("-"):
            chunk = part.strip().strip("()")
            if not chunk or not re.search(r"[a-zA-Z]", chunk):
                continue
            syllables.append((chunk, _syllable_is_stressed(chunk)))
    return syllables


@lru_cache(maxsize=1)
def _get_g2p():
    from misaki import en, espeak

    try:
        fallback = espeak.EspeakFallback(british=False)
    except Exception:
        fallback = None
    return en.G2P(trf=False, british=False, fallback=fallback, unk="")


def _phonemize_syllable(syllable: str) -> str | None:
    try:
        phonemes, _rating = _get_g2p()(syllable.lower())
    except Exception:
        return None
    if not phonemes:
        return None
    return phonemes.strip()


def build_phoneme_string(pronunciation: str | None) -> str | None:
    """Lowercase syllables → misaki G2P; CAPS chunks get primary IPA stress."""
    clean = normalize_pronunciation(pronunciation)
    if not clean:
        return None
    syllables = _split_guide_syllables(clean)
    if not syllables:
        return None

    parts: list[str] = []
    for chunk, stressed in syllables:
        ps = _phonemize_syllable(chunk)
        if not ps:
            continue
        parts.append(_primary_stress_before_first_vowel(ps) if stressed else _strip_stress_marks(ps))

    if not parts:
        return None
    return " ".join(parts)


def prepare_kokoro_text(pronunciation: str | None) -> str | None:
    """Kokoro input: markdown IPA override preserving display guide + stressed phonemes."""
    clean = normalize_pronunciation(pronunciation)
    if not clean:
        return None
    phonemes = build_phoneme_string(clean)
    if not phonemes:
        # Fallback: spaced lowercase (no CAPS spelling trap).
        spaced = clean.replace("-", " ").strip()
        return spaced.lower() if spaced else None
    return f"[{clean}](/{phonemes}/)"


def prepare_kokoro_text_with_builder(
    pronunciation: str | None,
    *,
    phoneme_builder: Callable[[str | None], str | None] | None = None,
) -> str | None:
    """Same as prepare_kokoro_text but allows injecting a test double for G2P."""
    if phoneme_builder is None:
        return prepare_kokoro_text(pronunciation)
    clean = normalize_pronunciation(pronunciation)
    if not clean:
        return None
    phonemes = phoneme_builder(clean)
    if not phonemes:
        spaced = clean.replace("-", " ").strip()
        return spaced.lower() if spaced else None
    return f"[{clean}](/{phonemes}/)"
