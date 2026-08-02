"""Heuristic classification of grammar rules by domain, POS, construction, and rule kind."""
import re
from typing import Dict, List, Optional, Tuple

# (pattern, domain, pos, construction) — first match wins per dimension
_DOMAIN_RULES = [
    (r"\b(phoneme|phonolog|vowel|consonant|nasal|tone|accent|stress|syllable|ablaut|lenition|assimilation|fricative|stop|affricate)\b", "phonology"),
    (r"\b(affix|morpheme|root|suffix|prefix|inflection|derivation|reduplicat|incorporat|compound)\b", "morphology"),
    (r"\b(word order|sov|osv|svo|clause|sentence|relative|subordinat|coordination|switch.?reference)\b", "syntax"),
    (r"\b(agreement|concord|valence|transitive|intransitive|argument|patient|agent|subject|object)\b", "morphosyntax"),
    (r"\b(classifier|noun class|lexicon|vocabulary|cognate|pos\b|part of speech)\b", "lexicon"),
    (r"\b(tense|aspect|modal|future|past|meaning|semantic|gloss)\b", "semantics"),
    (r"\b(topic|focus|discourse|pragmatic|information structure)\b", "discourse"),
    (r"\b(proto|reconstruct|comparative|cognate|lawson|historical|siouan|catawba|yuchi)\b", "historical"),
]

_POS_RULES = [
    (r"\b(noun|nominal|noun phrase)\b", "noun"),
    (r"\b(verb|verbal|verb phrase|intransitive|transitive)\b", "verb"),
    (r"\b(adjective|describing word|stative)\b", "adjective"),
    (r"\b(pronoun|pronominal|first person|second person|third person|1sg|2sg|3sg)\b", "pronoun"),
    (r"\b(determiner|article|demonstrative)\b", "determiner"),
    (r"\b(postposition|preposition|adposition)\b", "adposition"),
    (r"\b(adverb)\b", "adverb"),
    (r"\b(particle|clitic|enclitic)\b", "particle"),
    (r"\b(affix|suffix|prefix|morpheme)\b", "affix"),
    (r"\b(numeral|number word|counting)\b", "numeral"),
    (r"\b(classifier)\b", "classifier"),
    (r"\b(clause|sentence|word order)\b", "clause"),
]

_CONSTRUCTION_RULES = [
    (r"\b(word order|sov|osv|svo)\b", "word_order"),
    (r"\b(relative clause|relativiz)\b", "relative_clause"),
    (r"\b(incorporat)\b", "incorporation"),
    (r"\b(possess|inalienable|alienable)\b", "possession"),
    (r"\b(negat|negative)\b", "negation"),
    (r"\b(question|interrogative|wh-)\b", "question"),
    (r"\b(coordinat|conjunction|and\b|or\b)\b", "coordination"),
    (r"\b(subordinat|dependent clause|complement)\b", "subordination"),
    (r"\b(switch.?reference)\b", "switch_reference"),
    (r"\b(valence|transitive|intransitive|diathesis)\b", "valence"),
    (r"\b(agreement|concord)\b", "agreement"),
    (r"\b(reduplicat)\b", "reduplication"),
    (r"\b(compound|compounding)\b", "compounding"),
    (r"\b(classifier)\b", "classifier_construction"),
    (r"\b(copula|predicat)\b", "copula"),
    (r"\b(imperative|command)\b", "imperative"),
    (r"\b(tense|aspect|future|past)\b", "tense_aspect"),
]

# Comparative / attestation level — order matters (specific proto nodes before generic)
_LINEAGE_RULES = [
    (r"\b(proto.?siouan.?catawban|proto-siouan-catawban|\*psc\b|siouan.?catawban)\b", "proto_siouan_catawban"),
    (r"\b(proto.?catawban|proto-catawban|\*pc\b|coastal catawban|catawba-woccon)\b", "proto_catawban"),
    (r"\b(proto.?siouan|proto-siouan|\*ps\b|pan-siouan)\b", "proto_siouan"),
    (r"\b(yuchi|biloxi|tunica)\b", "other_comparative"),
    (r"\b(catawba|catawban|siouan|cognate|comparative)\b", "siouan_comparative"),
    (r"\b(woccon|w\s*\(|attested)\b", "woccon_attested"),
]


def _first_match(text: str, rules: list) -> Optional[str]:
    lower = text.lower()
    for pattern, value in rules:
        if re.search(pattern, lower, re.I):
            return value
    return None


def classify_grammar_lineage(content: str) -> Optional[str]:
    """Heuristic grammar lineage when the extractor did not tag a note."""
    return _first_match(content, _LINEAGE_RULES)


# Rule kind — order matters (specific diachronic before generic sister)
_RULE_KIND_RULES = [
    (
        r"\b(lawson|copyist|grapheme|handwriting|elongated|orthograph|printer error|explorer orthography|misinterpretation of lawson)\b",
        "orthographic",
    ),
    (
        r"\b(proto.?siouan.?catawban|proto-siouan-catawban|\*psc\b|siouan.?catawban)\b",
        "diachronic_psc",
    ),
    (
        r"\b(proto.?siouan|proto-siouan|\*ps\b|pan-siouan|proto-macro-siouan|proto-siouan initial)\b",
        "diachronic_ps",
    ),
    (
        r"\b(correspondence|catawba.*woccon|woccon.*catawba|nasal vowel|long oral|defective|\*r\b|\*r̄|woccon r|catawba n|sound correspond|denasal|woccon_to_catawba|eliminated r|word-initial)\b",
        "sister_wc",
    ),
]

_CORRESPONDENCE_NOTE_KEYWORDS = [
    "correspondence",
    "catawba",
    "woccon",
    "nasal vowel",
    "long oral",
    "defective",
    "*r",
    "lawson",
    "proto-siouan",
    "proto siouan",
    "sound correspond",
]


def is_correspondence_like(content: str) -> bool:
    """True when prose likely describes a correspondence rule (not general grammar)."""
    lower = (content or "").lower()
    return any(k in lower for k in _CORRESPONDENCE_NOTE_KEYWORDS)


def classify_rule_kind(content: str) -> Optional[str]:
    """Classify rule_kind for correspondence registry rows; None if not a correspondence rule."""
    if not (content or "").strip():
        return None
    return _first_match(content, _RULE_KIND_RULES)


def classify_correspondence_status(
    rule_kind: str,
    lhs: Optional[str],
    rhs: Optional[str],
    example_cognate_ids: Optional[List[str]] = None,
) -> str:
    """Demote singletons; promote identity pairs with broad cognate support."""
    examples = example_cognate_ids or []
    n = len(examples)
    if rule_kind != "sister_wc":
        return "established" if n >= 2 else "tentative"
    if lhs and rhs and lhs == rhs:
        if n >= 5:
            return "established"
        if n >= 2:
            return "tentative"
        return "singleton"
    if n >= 3:
        return "established"
    if n >= 2:
        return "tentative"
    return "singleton"


def infer_direction(rule_kind: str) -> Optional[str]:
    if rule_kind == "orthographic":
        return "lawson_to_w"
    if rule_kind == "sister_wc":
        return "w_to_c"
    if rule_kind == "diachronic_psc":
        return "psc_to_w"
    if rule_kind == "diachronic_ps":
        return "ps_to_w"
    return None


def classify_grammar_rule(content: str) -> Dict[str, str]:
    """Return grammar_domain, pos_tag, construction_type for a rule string."""
    domain = _first_match(content, _DOMAIN_RULES) or "other"
    pos = _first_match(content, _POS_RULES) or "multi"
    construction = _first_match(content, _CONSTRUCTION_RULES) or "na"
    # Refine: syntax domain often implies clause-level POS
    if domain == "syntax" and pos == "multi":
        pos = "clause"
    if domain == "morphology" and construction == "na" and re.search(r"reduplicat", content, re.I):
        construction = "reduplication"
    return {
        "grammar_domain": domain,
        "pos_tag": pos,
        "construction_type": construction,
    }


def apply_classification_to_rule(
    row,
    category: str,
    content: str,
    *,
    grammar_lineage: Optional[str] = None,
) -> None:
    """Set classification fields on a PendingRule or CanonicalRule row."""
    if category != "grammar":
        row.grammar_domain = None
        row.pos_tag = None
        row.construction_type = None
        row.grammar_lineage = None
        if hasattr(row, "rule_kind"):
            row.rule_kind = None
        if hasattr(row, "correspondence_status"):
            row.correspondence_status = None
        return
    tags = classify_grammar_rule(content)
    row.grammar_domain = tags["grammar_domain"]
    row.pos_tag = tags["pos_tag"]
    row.construction_type = tags["construction_type"]
    gl = (grammar_lineage or "").strip() or classify_grammar_lineage(content)
    row.grammar_lineage = gl
    rk = classify_rule_kind(content)
    if hasattr(row, "rule_kind"):
        row.rule_kind = rk
    if hasattr(row, "correspondence_status"):
        row.correspondence_status = (
            classify_correspondence_status(rk, None, None) if rk else None
        )
