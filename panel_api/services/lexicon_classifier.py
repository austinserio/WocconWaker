"""Classify lexicon entries for teaching units, word class, and lesson band."""
import re
from typing import Dict, Optional

from panel_api.lexicon_taxonomy import TEACHING_UNIT_IDS, WORD_CLASS_IDS

# English-gloss rules — order matters (first match wins).
# Classify from the English definition, not the Woccon form.
_ENGLISH_UNIT_RULES = [
    # Reconstruction / comparative material
    (
        r"\b(proto|reconstruct|cognate|siouan|catawba|yuchi|comparative)\b|^\*",
        "reconstruction",
    ),
    # Function words & grammar
    (
        r"\b(pronoun|possessive|prefix|suffix|affix|particle|clitic|enclitic|conjunction|"
        r"interrogative|preposition|postposition|plus|more than|that'?s all|how many|"
        r"on top of|third person|person-genuine)\b",
        "speech_grammar",
    ),
    # Numerals
    (
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
        r"fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|"
        r"fifty|hundred|thousand|numeral|number|counting|count)\b",
        "numbers",
    ),
    # Places & geography
    (
        r"\b(town|village|river|lake|place|north|south|east|west|settlement|"
        r"waccon|loblolly|peak|mountain|hill)\b",
        "places",
    ),
    # Culture & ceremony
    (
        r"\b(dance|song|god|spirit|ceremony|treaty|peace|war|wampum|goodbye|"
        r"mouth harp|jew'?s harp|drunk|harvest festival)\b",
        "culture",
    ),
    # Kinship & people
    (
        r"\b(mother|father|brother|sister|wife|husband|kin|child|children|people|"
        r"man|woman|chief|king|indians?|englishman|lazy|lazy fellow|old woman|person|"
        r"genuine|fellow|wife)\b",
        "kinship",
    ),
    # Colors, qualities, emotions, states
    (
        r"\b(red|black|white|blue|gray|grey|green|yellow|brown|big|small|long|short|"
        r"color|colour|heavy|light|hard|soft|bitter|sweet|afraid|angry|mad|dead|"
        r"cubit|length|tall|wide|narrow|old|new|good|bad|hot|cold|warm|cool)\b",
        "colors_qualities",
    ),
    # Body & health
    (
        r"\b(head|hair|eye|eyes|leg|foot|feet|hand|hands|body|blood|sick|ill|pain|"
        r"heart|tooth|teeth|mouth|nose|ear|arm|finger|bone|fart|turd|fat|"
        r"flesh|skin(?!\s*-)|dressed skin|raw undressed skin)\b",
        "body",
    ),
    # Animal materials & hunting gear (before general animals)
    (r"\b(\w+-skin|raccoon skin|bear skin|fox skin|dressed skin|buckskin|feathers)\b", "home_objects"),
    # Animals & hunting
    (
        r"\b(dog|wolf|bear|fish|deer|snake|bird|turkey|beaver|animal|hunt|fox|duck|"
        r"goose|swan|cow|horse|swine|pig|rats?|otter|mink|alligator|crabs?|cockles?|louse|"
        r"fawn|squirrel|panther|cat|dogs)\b",
        "animals",
    ),
    # Plants, food & agriculture
    (
        r"\b(corn|eat|food|bread|meal|plant|tree|root|berry|acorn|acorns|tobacco|"
        r"potato|potatoes|peas|pease|homine|nuts|hickory|pine|spear-tree|reed|wood|rum|"
        r"drink|peach|plum|acorn|crop|grain|hominy|flour|meal|hunger|starve)\b",
        "plants_food",
    ),
    # Nature & environment (incl. time-of-day / weather)
    (
        r"\b(water|rain|wind|fire|sun|moon|star|river|snow|sky|earth|day|night|"
        r"yesterday|tomorrow|season|winter|summer|spring|fall|autumn|clay|moss|"
        r"smoke|lightwood|roanoak|ronoak|oak|boulder|lightning|thunder|cloud|ice|frost|world|"
        r"sun/moon|sun and moon)\b",
        "nature",
    ),
    # Home, tools, clothing & everyday objects
    (
        r"\b(house|cloth|pot|bow|arrow|tool|path|road|gun|axe|knife|gunpowder|shot|"
        r"gunlock|flint|shirt|shoe|shoes|hat|coat|belt|breeches|stocking|blanket|"
        r"button|basket|bag|box|bowl|bottle|gourd|kettle|rundlet|canoe|hoe|awl|"
        r"needle|scissors|comb|spoon|pestle|mortar|pipe|paint|rope|mat|flap|dress|"
        r"fishgig|wampum|knot|burl|fist|comb|stockings|awl|tongues|flap|bottle|"
        r"flints?|homine|spear|net|trap|lock|powder|rum|breech|blankets)\b",
        "home_objects",
    ),
    # Motion, direction & time deixis
    (
        r"\b(go|come|walk|run|here|there|direction|along with|will you go|will you come|"
        r"little while ago|away|leave|arrive|enter|exit|path)\b",
        "motion",
    ),
    # Actions & verbs
    (
        r"\b(speak|say|hear|see|know|want|make|do|kill|die|live|remember|give|sell|"
        r"let alone|let it alone|buy|trade|work|sleep|wake|sit|stand|think|learn|teach|help|"
        r"call|answer|laugh|cry|fight|build|carry|bring|take|hold|open|close)\b",
        "actions",
    ),
]

_POS_MAP = [
    (r"^noun", "noun"),
    (r"^verb", "verb"),
    (r"^adjective", "adjective"),
    (r"^adverb", "adverb"),
    (r"^pronoun", "pronoun"),
    (r"^determiner", "determiner"),
    (r"^preposition", "postposition"),
    (r"^postposition", "postposition"),
    (r"^particle", "particle"),
    (r"^numeral|^number", "numeral"),
    (r"^interjection", "interjection"),
    (r"^conjunction", "conjunction"),
    (r"^prefix|^suffix|^affix", "affix"),
    (r"^phrase", "phrase"),
    (r"^interrogative", "particle"),
    (r"^quantifier", "determiner"),
    (r"^auxiliary", "verb"),
    (r"^proper noun", "noun"),
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


def _classify_teaching_unit(english: str, pos: str) -> str:
    eng = (english or "").strip()
    pos_l = (pos or "").strip().lower()
    word_class = normalize_word_class(pos)

    if eng.startswith("*") or "proto" in eng.lower():
        return "reconstruction"

    if word_class in ("affix", "particle", "conjunction"):
        return "speech_grammar"
    if word_class == "numeral":
        return "numbers"
    if word_class == "postposition" or pos_l == "preposition":
        return "speech_grammar"

    unit = _first_match(eng, _ENGLISH_UNIT_RULES)
    if unit:
        return unit

    # Phrases: reuse embedded English keywords (already covered by rules above).
    if word_class == "phrase" and eng:
        return "actions"

    if word_class == "interjection":
        return "culture"

    return "other"


def _lesson_band_for(
    teaching_unit: str,
    word_class: str,
    source: Optional[str],
) -> str:
    if source == "lawson" or (source and "lawson" in source.lower()):
        return "lawson_core"
    if word_class in ("affix", "particle") or teaching_unit in ("reconstruction", "speech_grammar"):
        return "reference"
    if teaching_unit in ("kinship", "body", "numbers", "motion", "lawson_core"):
        return "beginner"
    if teaching_unit in ("animals", "plants_food", "nature", "home_objects", "colors_qualities"):
        return "intermediate"
    if teaching_unit in ("culture", "places", "actions"):
        return "intermediate"
    if teaching_unit == "reconstruction":
        return "advanced"
    return "intermediate"


def classify_lexicon_entry(
    woccon: str,
    english: str,
    pos: str,
    source: Optional[str] = None,
) -> Dict[str, str]:
    word_class = normalize_word_class(pos)
    teaching_unit = _classify_teaching_unit(english, pos)

    if source == "lawson" or (source and "lawson" in source.lower()):
        if teaching_unit == "other":
            teaching_unit = "lawson_core"

    lesson_band = _lesson_band_for(teaching_unit, word_class, source)

    if teaching_unit not in TEACHING_UNIT_IDS:
        teaching_unit = "other"
    if word_class not in WORD_CLASS_IDS:
        word_class = "unknown"

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
