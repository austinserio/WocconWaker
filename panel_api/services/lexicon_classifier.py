"""Classify lexicon entries for teaching units, word class, and lesson band."""
import re
from typing import Dict, Optional

from panel_api.lexicon_taxonomy import LESSON_BAND_IDS, TEACHING_UNIT_IDS, WORD_CLASS_IDS

_UNIT_RULES = [
    (r"\b(dog|wolf|bear|fish|deer|snake|bird|turkey|beaver|animal|hunt)\b", "animals"),
    (r"\b(mother|father|brother|sister|wife|husband|kin|child|people|man|woman|chief)\b", "kinship"),
    (r"\b(head|hand|foot|body|blood|sick|pain|heart|tooth)\b", "body"),
    (r"\b(corn|eat|food|bread|meal|plant|tree|root|berry|acorn)\b", "plants_food"),
    (r"\b(water|rain|wind|fire|sun|moon|star|river|snow|sky|earth)\b", "nature"),
    (r"\b(house|skin|cloth|pot|bow|arrow|tool|path|road)\b", "home_objects"),
    (r"\b(one|two|three|four|five|six|seven|eight|nine|ten|number|count)\b", "numbers"),
    (r"\b(red|black|white|big|small|long|short|color|heavy|light)\b", "colors_qualities"),
    (r"\b(go|come|walk|run|path|there|here|direction)\b", "motion"),
    (r"\b(speak|say|hear|see|know|want|make|do|kill|die|live)\b", "actions"),
    (r"\b(pronoun|particle|prefix|suffix|conjunction|clitic|enclitic)\b", "speech_grammar"),
    (r"\b(town|village|river|lake|place|north|south)\b", "places"),
    (r"\b(dance|song|god|spirit|ceremony|treaty|peace|war)\b", "culture"),
    (r"\b(proto|reconstruct|cognate|siouan|catawba|yuchi|lawson)\b", "reconstruction"),
]

_POS_MAP = [
    (r"^noun", "noun"),
    (r"^verb", "verb"),
    (r"^adjective", "adjective"),
    (r"^adverb", "adverb"),
    (r"pronoun", "pronoun"),
    (r"determiner", "determiner"),
    (r"preposition|postposition", "postposition"),
    (r"particle|clitic|enclitic", "particle"),
    (r"numeral|number", "numeral"),
    (r"interjection", "interjection"),
    (r"conjunction|coordinator", "conjunction"),
    (r"prefix|suffix|morpheme|affix", "affix"),
    (r"phrase", "phrase"),
    (r"interrogative", "particle"),
    (r"quantifier", "determiner"),
    (r"auxiliary", "verb"),
]


def _first_match(text: str, rules: list) -> Optional[str]:
    lower = text.lower()
    for pattern, value in rules:
        if re.search(pattern, lower, re.I):
            return value
    return None


def normalize_word_class(raw_pos: str) -> str:
    raw = (raw_pos or "unknown").strip().lower()
    for pattern, wc in _POS_MAP:
        if re.search(pattern, raw, re.I):
            return wc
    return "unknown"


def classify_lexicon_entry(
    woccon: str,
    english: str,
    pos: str,
    source: Optional[str] = None,
) -> Dict[str, str]:
    combined = f"{woccon} {english} {pos}"
    word_class = normalize_word_class(pos)
    teaching_unit = _first_match(combined, _UNIT_RULES) or "other"

    if source == "lawson" or (source and "lawson" in source.lower()):
        lesson_band = "lawson_core"
        if teaching_unit == "other":
            teaching_unit = "lawson_core"
    elif word_class in ("affix", "particle") or teaching_unit == "reconstruction":
        lesson_band = "reference"
    elif teaching_unit in ("lawson_core", "kinship", "body", "numbers", "motion"):
        lesson_band = "beginner"
    elif teaching_unit in ("animals", "plants_food", "nature", "home_objects", "colors_qualities"):
        lesson_band = "intermediate"
    elif teaching_unit == "reconstruction":
        lesson_band = "advanced"
    else:
        lesson_band = "intermediate"

    if "proto" in english.lower() or english.strip().startswith("*"):
        teaching_unit = "reconstruction"
        lesson_band = "reference"

    return {
        "teaching_unit": teaching_unit,
        "word_class": word_class,
        "lesson_band": lesson_band,
    }


def apply_lexicon_classification(row, woccon: str, english: str, pos: str, source: Optional[str] = None) -> None:
    tags = classify_lexicon_entry(woccon, english, pos, source or getattr(row, "source", None))
    row.teaching_unit = tags["teaching_unit"]
    row.word_class = tags["word_class"]
    row.lesson_band = tags["lesson_band"]
    if not row.pos or row.pos == "unknown":
        row.pos = tags["word_class"]
