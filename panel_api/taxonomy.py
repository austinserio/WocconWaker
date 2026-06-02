"""Linguistic taxonomy for organizing grammar rules."""

from typing import Any, Dict, List, Optional

# Top-level note category (unchanged)
NOTE_CATEGORIES = ("grammar", "pronunciation", "cultural")

# Extraction focus modes (document AI analysis)
EXTRACTION_FOCUSES: List[Dict[str, str]] = [
    {"id": "general", "label": "General (all)", "description": "Vocabulary, grammar, pronunciation, and culture"},
    {"id": "vocabulary", "label": "Vocabulary only", "description": "Lexicon entries only"},
    {"id": "grammar", "label": "Grammar only", "description": "Grammar rule packets — lineage filter (skips pronunciation & culture)"},
    {"id": "pronunciation", "label": "Pronunciation only", "description": "Phonology and pronunciation guides"},
    {"id": "culture", "label": "Culture only", "description": "Cultural usage and context only"},
]

# Comparative / attestation level for grammar rules
GRAMMAR_LINEAGES: List[Dict[str, str]] = [
    {"id": "woccon_attested", "label": "Attested Woccon", "description": "Rules grounded in attested Woccon forms"},
    {"id": "siouan_comparative", "label": "Siouan comparative", "description": "Cross-Siouan patterns without a proto node"},
    {"id": "proto_siouan", "label": "Proto-Siouan", "description": "Proto-Siouan (*PS) reconstructions"},
    {"id": "proto_siouan_catawban", "label": "Proto-Siouan-Catawban", "description": "Siouan-Catawban node (*PSC)"},
    {"id": "proto_catawban", "label": "Proto-Catawban", "description": "Coastal Catawban / Catawba-Woccon node (*PC)"},
    {"id": "other_comparative", "label": "Other comparative", "description": "Yuchi, Biloxi-only, or other comparative material"},
]

EXTRACTION_FOCUS_IDS = {f["id"] for f in EXTRACTION_FOCUSES}
GRAMMAR_LINEAGE_IDS = {g["id"] for g in GRAMMAR_LINEAGES}

# Grammar subdomain — what area of grammar the rule describes
GRAMMAR_DOMAINS: List[Dict[str, str]] = [
    {"id": "phonology", "label": "Phonology", "description": "Sounds, alternations, phonological processes"},
    {"id": "morphology", "label": "Morphology", "description": "Affixes, roots, word formation, inflection"},
    {"id": "syntax", "label": "Syntax", "description": "Word order, clauses, sentence structure"},
    {"id": "morphosyntax", "label": "Morphosyntax", "description": "Agreement, valence, argument structure"},
    {"id": "lexicon", "label": "Lexicon & word classes", "description": "Parts of speech, classifiers, lexical patterns"},
    {"id": "semantics", "label": "Semantics", "description": "Meaning, tense, aspect, modality"},
    {"id": "discourse", "label": "Discourse", "description": "Information structure, topic, focus"},
    {"id": "historical", "label": "Historical / comparative", "description": "Proto-forms, cognates, language family"},
    {"id": "other", "label": "Other / unclassified", "description": "Needs review or cross-cutting"},
]

# Part of speech or morpheme class the rule primarily concerns
POS_TAGS: List[Dict[str, str]] = [
    {"id": "noun", "label": "Noun"},
    {"id": "verb", "label": "Verb"},
    {"id": "adjective", "label": "Adjective / describing word"},
    {"id": "pronoun", "label": "Pronoun"},
    {"id": "determiner", "label": "Determiner / article"},
    {"id": "adposition", "label": "Postposition / adposition"},
    {"id": "adverb", "label": "Adverb"},
    {"id": "particle", "label": "Particle / clitic"},
    {"id": "affix", "label": "Affix / morpheme"},
    {"id": "numeral", "label": "Numeral"},
    {"id": "classifier", "label": "Classifier"},
    {"id": "clause", "label": "Clause / sentence"},
    {"id": "multi", "label": "Multiple / general"},
    {"id": "na", "label": "Not applicable"},
]

# Sentence construction or syntactic phenomenon
CONSTRUCTION_TYPES: List[Dict[str, str]] = [
    {"id": "word_order", "label": "Word order"},
    {"id": "relative_clause", "label": "Relative clause"},
    {"id": "incorporation", "label": "Incorporation"},
    {"id": "possession", "label": "Possession"},
    {"id": "negation", "label": "Negation"},
    {"id": "question", "label": "Question / interrogative"},
    {"id": "coordination", "label": "Coordination"},
    {"id": "subordination", "label": "Subordination"},
    {"id": "switch_reference", "label": "Switch reference"},
    {"id": "valence", "label": "Valence / transitivity"},
    {"id": "agreement", "label": "Agreement / concord"},
    {"id": "reduplication", "label": "Reduplication"},
    {"id": "compounding", "label": "Compounding"},
    {"id": "classifier_construction", "label": "Classifier construction"},
    {"id": "copula", "label": "Copula / predication"},
    {"id": "imperative", "label": "Imperative / command"},
    {"id": "tense_aspect", "label": "Tense / aspect"},
    {"id": "na", "label": "Not applicable"},
]

DOMAIN_IDS = {d["id"] for d in GRAMMAR_DOMAINS}
POS_IDS = {p["id"] for p in POS_TAGS}
CONSTRUCTION_IDS = {c["id"] for c in CONSTRUCTION_TYPES}


def taxonomy_payload() -> Dict[str, Any]:
    return {
        "grammar_domains": GRAMMAR_DOMAINS,
        "pos_tags": POS_TAGS,
        "construction_types": CONSTRUCTION_TYPES,
        "note_categories": list(NOTE_CATEGORIES),
        "extraction_focuses": EXTRACTION_FOCUSES,
        "grammar_lineages": GRAMMAR_LINEAGES,
    }


def label_for(items: List[Dict[str, str]], id_: Optional[str]) -> str:
    if not id_:
        return ""
    for item in items:
        if item["id"] == id_:
            return item["label"]
    return id_.replace("_", " ").title()
