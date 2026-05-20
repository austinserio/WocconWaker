"""Teaching taxonomy for dictionary / lexicon entries."""

from typing import Any, Dict, List, Optional

# Thematic unit — how words are grouped for lessons
TEACHING_UNITS: List[Dict[str, str]] = [
    {"id": "lawson_core", "label": "Lawson core (1709)", "description": "Original attested Lawson word list — start here"},
    {"id": "kinship", "label": "Kinship & people", "description": "Family, social roles, human referents"},
    {"id": "body", "label": "Body & health", "description": "Body parts, illness, physical states"},
    {"id": "animals", "label": "Animals & hunting", "description": "Fauna, fish, game, animal products"},
    {"id": "plants_food", "label": "Plants & food", "description": "Flora, crops, cooking, eating"},
    {"id": "nature", "label": "Nature & environment", "description": "Weather, water, land, sky, seasons"},
    {"id": "home_objects", "label": "Home & objects", "description": "Tools, clothing, dwellings, everyday things"},
    {"id": "numbers", "label": "Numbers & counting", "description": "Numerals, quantity, ordinals"},
    {"id": "colors_qualities", "label": "Colors & qualities", "description": "Color, size, shape, descriptors"},
    {"id": "motion", "label": "Motion & direction", "description": "Go, come, path, location deixis"},
    {"id": "actions", "label": "Actions & verbs", "description": "General verbs and activities"},
    {"id": "speech_grammar", "label": "Function & grammar words", "description": "Pronouns, particles, conjunctions, affixes"},
    {"id": "places", "label": "Places & geography", "description": "Locations, rivers, settlements"},
    {"id": "culture", "label": "Culture & ceremony", "description": "Ritual, belief, community life"},
    {"id": "reconstruction", "label": "Reconstruction & cognates", "description": "Proto-forms, comparative Siouan material"},
    {"id": "other", "label": "Other / review", "description": "Unclassified — needs teaching unit"},
]

# Normalized word class for teaching (maps messy extractor POS)
WORD_CLASSES: List[Dict[str, str]] = [
    {"id": "noun", "label": "Noun"},
    {"id": "verb", "label": "Verb"},
    {"id": "adjective", "label": "Adjective"},
    {"id": "adverb", "label": "Adverb"},
    {"id": "pronoun", "label": "Pronoun"},
    {"id": "determiner", "label": "Determiner"},
    {"id": "postposition", "label": "Postposition"},
    {"id": "particle", "label": "Particle / clitic"},
    {"id": "numeral", "label": "Numeral"},
    {"id": "interjection", "label": "Interjection"},
    {"id": "conjunction", "label": "Conjunction"},
    {"id": "affix", "label": "Affix / morpheme"},
    {"id": "phrase", "label": "Phrase / multiword"},
    {"id": "unknown", "label": "Unknown"},
]

# Lesson progression band
LESSON_BANDS: List[Dict[str, str]] = [
    {"id": "lawson_core", "label": "Lawson core", "description": "Priority attested vocabulary"},
    {"id": "beginner", "label": "Beginner unit", "description": "High-frequency thematic sets"},
    {"id": "intermediate", "label": "Intermediate", "description": "Broader community lexicon"},
    {"id": "advanced", "label": "Advanced", "description": "Comparative, technical, rare"},
    {"id": "reference", "label": "Reference only", "description": "Scholarly / reconstruction — not drill vocabulary"},
]

TEACHING_UNIT_IDS = {u["id"] for u in TEACHING_UNITS}
WORD_CLASS_IDS = {w["id"] for w in WORD_CLASSES}
LESSON_BAND_IDS = {b["id"] for b in LESSON_BANDS}


def lexicon_taxonomy_payload() -> Dict[str, Any]:
    return {
        "teaching_units": TEACHING_UNITS,
        "word_classes": WORD_CLASSES,
        "lesson_bands": LESSON_BANDS,
    }


def unit_label(unit_id: Optional[str]) -> str:
    for u in TEACHING_UNITS:
        if u["id"] == unit_id:
            return u["label"]
    return (unit_id or "").replace("_", " ").title()
