"""OCR repair and scoring normalization for Woccon/Catawba forms."""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

# Common OCR glottal / length / nasal substitutions
_GLOTTAL_CHARS = {"7", "ʔ", "ʼ", "ʻ", "‹", "›"}
_LENGTH_CHARS = {"·", "⋅", "•", "‹", "›", "ˑ"}
_STRESS = str.maketrans("", "", "áéíóúàèìòùâêîôûäëïöüÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÄËÏÖÜ")

_ENGLISH_NOISE = re.compile(
    r"\b(Park|with|error|dialect|Esaw|Saraw|from|plus|step|tree|river|bear|White|grass|skin|hand)\b",
    re.I,
)
_DIGIT_NOISE = re.compile(r"\b\d+\b")


def repair_ocr(s: Optional[str]) -> str:
    """Repair common Rudes OCR artifacts in phonetic strings."""
    if not s:
        return ""
    out = s
    out = out.replace("ı", "i").replace("İ", "i")
    for ch in _GLOTTAL_CHARS:
        out = out.replace(ch, "?")
    for ch in _LENGTH_CHARS:
        if ch not in "?":
            out = out.replace(ch, "·")
    # hq / hą confusion after vowels
    out = re.sub(r"([aeiouáéíóúą])hq", r"\1hą", out, flags=re.I)
    out = re.sub(r"([aeiouáéíóú])q(?=\b|[?·])", r"\1ą", out, flags=re.I)
    # word-initial f often OCR for í in Woccon reconstitutions
    out = re.sub(r"\bfti\b", "íti", out, flags=re.I)
    out = re.sub(r"^\*?fti\b", lambda m: m.group(0).replace("fti", "íti"), out, flags=re.I)
    # normalize combining marks to precomposed where possible
    out = unicodedata.normalize("NFC", out)
    return out.strip()


def normalize_for_scoring(s: Optional[str]) -> str:
    """Fold diacritics and punctuation for lenient comparison."""
    if not s:
        return ""
    s = repair_ocr(s)
    # Fold accented vowels to ASCII before stripping combining marks
    folds = str.maketrans(
        "áéíóúàèìòùâêîôûäëïöü",
        "aeiouaeiouaeiouaeiou",
    )
    s = s.translate(folds)
    s = s.replace("ą", "a").replace("ę", "e").replace("į", "i").replace("ų", "u")
    s = re.sub(r"[·?\-|()\[\]{}]", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()


def normalize_strict(s: Optional[str]) -> str:
    """Keep diacritics but unify OCR noise."""
    if not s:
        return ""
    s = repair_ocr(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_corrupt(s: Optional[str]) -> bool:
    """Flag answer-key strings that are OCR garbage, not phonetic forms."""
    if not s:
        return True
    text = s.strip()
    if not text:
        return True
    if _DIGIT_NOISE.search(text):
        return True
    if _ENGLISH_NOISE.search(text):
        return True
    if " " in text and re.search(r"\b(the|and|for|with|from|id\.|idem)\b", text, re.I):
        return True
    return False


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance on normalized strings."""
    a, b = normalize_for_scoring(a), normalize_for_scoring(b)
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def normalized_similarity(a: str, b: str) -> float:
    """1 - normalized edit distance ratio."""
    a_n, b_n = normalize_for_scoring(a), normalize_for_scoring(b)
    if not a_n and not b_n:
        return 1.0
    if not a_n or not b_n:
        return 0.0
    dist = edit_distance(a_n, b_n)
    return 1.0 - dist / max(len(a_n), len(b_n))
