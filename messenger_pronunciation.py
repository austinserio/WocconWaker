"""Detect pronunciation-intent Messenger queries and resolve lexicon + audio clips."""
from __future__ import annotations

import re
from typing import Any

from panel_api.services.pronunciation import (
    normalize_pronunciation,
    primary_pronunciation_guide,
    pronunciation_guide_candidates,
)
from panel_api.services.pronunciation_audio import (
    is_speakable_pronunciation,
    public_pronunciation_audio_url,
    resolve_pronunciation_with_audio,
)

# Capture the word/phrase after common pronunciation questions.
_PRONUNCIATION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"how\s+(?:do\s+(?:i|you|we)\s+)?pronounce\s+(.+?)[\?\.!]*$",
        r"how\s+is\s+(.+?)\s+pronounced[\?\.!]*$",
        r"how\s+to\s+pronounce\s+(.+?)[\?\.!]*$",
        r"pronunciation\s+of\s+(.+?)[\?\.!]*$",
        r"(?:what(?:'s|\s+is)\s+)?(?:the\s+)?pronunciation\s+(?:for|of)\s+(.+?)[\?\.!]*$",
        r"^pronounce\s+(.+?)[\?\.!]*$",
    )
)


def _clean_target(raw: str) -> str:
    s = (raw or "").strip().strip("\"'“”‘’")
    s = re.sub(r"\s+", " ", s)
    # Drop trailing "in woccon" / "in Woccon"
    s = re.sub(r"\s+in\s+woccon\s*$", "", s, flags=re.I).strip()
    return s


def parse_pronunciation_query(text: str) -> str | None:
    """Return the target word/phrase when text asks how to pronounce something."""
    t = (text or "").strip()
    if not t:
        return None
    for pattern in _PRONUNCIATION_PATTERNS:
        match = pattern.search(t)
        if match:
            target = _clean_target(match.group(1))
            if target and len(target) <= 80:
                return target
    return None


def _prefer_lexicon_entry(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer canonical base rows over noisy LLM duplicates for the same gloss."""

    def sort_key(entry: dict[str, Any]) -> tuple[int, int, int, str]:
        woccon = (entry.get("woccon") or "").strip()
        simple_woccon = 0 if re.fullmatch(r"[\w-]+", woccon) else 1
        return (
            0 if entry.get("is_base_entry") else 1,
            simple_woccon,
            len(woccon),
            woccon.lower(),
        )

    return sorted(entries, key=sort_key)[0]


def find_lexicon_entry(lexicon: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    """Match a lexicon row by Woccon form or English gloss."""
    target = _clean_target(target)
    if not target:
        return None
    tl = target.lower()

    for entry in lexicon:
        if (entry.get("woccon") or "").lower() == tl:
            return entry

    eng_matches: list[dict[str, Any]] = []
    for entry in lexicon:
        eng = (entry.get("english") or "").lower()
        if not eng:
            continue
        if eng == tl:
            eng_matches.append(entry)
            continue
        for part in re.split(r"[,;/]", eng):
            if part.strip() == tl:
                eng_matches.append(entry)
                break
    if eng_matches:
        return _prefer_lexicon_entry(eng_matches)

    eng_matches = [
        e for e in lexicon if tl in (e.get("english") or "").lower()
    ]
    if len(eng_matches) == 1:
        return eng_matches[0]

    woc_matches = [
        e for e in lexicon if tl in (e.get("woccon") or "").lower()
    ]
    if len(woc_matches) == 1:
        return woc_matches[0]

    return None


def _pronunciation_for_entry(
    lexicon: list[dict[str, Any]], entry: dict[str, Any]
) -> str | None:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(raw: str | None) -> None:
        for guide in pronunciation_guide_candidates(raw):
            key = guide.casefold()
            if key in seen:
                continue
            seen.add(key)
            candidates.append(guide)

    add(entry.get("pronunciation"))
    eng = (entry.get("english") or "").lower()
    if eng:
        for row in lexicon:
            if not row.get("is_base_entry"):
                continue
            if (row.get("english") or "").lower() != eng:
                continue
            add(row.get("pronunciation"))

    for guide in candidates:
        if resolve_pronunciation_with_audio(guide):
            return guide
    return candidates[0] if candidates else None


def resolve_pronunciation_response(
    lexicon: list[dict[str, Any]], target: str
) -> dict[str, Any] | None:
    """
    Resolve pronunciation intent for a target word/phrase.

    Returns None when the target is not in the lexicon (caller may fall back to LLM).
    Otherwise returns keys: woccon, english, pronunciation, audio_url, has_audio.
    """
    entry = find_lexicon_entry(lexicon, target)
    if not entry:
        return None

    pronunciation = _pronunciation_for_entry(lexicon, entry)
    if pronunciation:
        pronunciation = primary_pronunciation_guide(pronunciation) or pronunciation
    woccon = (entry.get("woccon") or "").strip()
    english = (entry.get("english") or "").strip()

    audio_url = None
    if pronunciation and is_speakable_pronunciation(pronunciation):
        audio_url = public_pronunciation_audio_url(pronunciation)

    return {
        "woccon": woccon,
        "english": english,
        "pronunciation": pronunciation,
        "audio_url": audio_url,
        "has_audio": bool(audio_url),
    }


def format_pronunciation_text(result: dict[str, Any]) -> str:
    """Build a Messenger text reply for a resolved pronunciation lookup."""
    woccon = result.get("woccon") or "that word"
    english = result.get("english") or ""
    pronunciation = result.get("pronunciation")

    if pronunciation:
        guide = pronunciation
        lines = [
            f"🔊 **{woccon}**",
        ]
        if english:
            lines.append(f"English: {english}")
        lines.append(f"Pronunciation: {guide}")
        if result.get("has_audio"):
            lines.append("\nHere's a recording you can play.")
        else:
            lines.append(
                "\nI don't have a pre-recorded clip for this guide yet, but you can read the syllables above."
            )
        return "\n".join(lines)

    if english:
        return (
            f"I know **{woccon}** ({english}) in the Woccon vocabulary, "
            "but there isn't a community pronunciation guide recorded for it yet."
        )
    return (
        f"I know **{woccon}** in the Woccon vocabulary, "
        "but there isn't a pronunciation guide recorded for it yet."
    )
