"""Extraction focus modes and LLM prompt templates for document analysis."""
from typing import Optional

EXTRACTION_FOCUSES = [
    {
        "id": "general",
        "label": "General (all)",
        "description": "Vocabulary, grammar, pronunciation, and culture in one pass",
    },
    {
        "id": "vocabulary",
        "label": "Vocabulary only",
        "description": "Woccon lexicon entries only — inline pronunciation on words OK; no grammar or culture notes",
    },
    {
        "id": "grammar",
        "label": "Grammar only",
        "description": "Grammar rule packets only — choose a lineage filter below (skips pronunciation & culture)",
    },
    {
        "id": "pronunciation",
        "label": "Pronunciation only",
        "description": "Phonology and pronunciation guides — not grammar rules or vocabulary lists",
    },
    {
        "id": "culture",
        "label": "Culture only",
        "description": "Cultural usage and community context only",
    },
]

GRAMMAR_LINEAGES = [
    {
        "id": "woccon_attested",
        "label": "Attested Woccon",
        "description": "Patterns with attested Woccon forms (W …) — prove the rule applies to Woccon, not merely comparative speculation",
    },
    {
        "id": "siouan_comparative",
        "label": "Siouan comparative",
        "description": "Cross-Siouan patterns citing multiple daughter languages without a single proto node",
    },
    {
        "id": "proto_siouan",
        "label": "Proto-Siouan",
        "description": "Reconstructions labeled Proto-Siouan or pan-Siouan (*PS …)",
    },
    {
        "id": "proto_siouan_catawban",
        "label": "Proto-Siouan-Catawban",
        "description": "Reconstructions for the Siouan-Catawban node (*PSC …, Proto-Siouan-Catawban)",
    },
    {
        "id": "proto_catawban",
        "label": "Proto-Catawban",
        "description": "Coastal Catawban / Catawba-Woccon node reconstructions (*PC …, Proto-Catawban)",
    },
    {
        "id": "other_comparative",
        "label": "Other comparative",
        "description": "Yuchi, Biloxi, or other non-Siouan comparanda; methodological notes",
    },
]

EXTRACTION_FOCUS_IDS = {f["id"] for f in EXTRACTION_FOCUSES}
GRAMMAR_LINEAGE_IDS = {g["id"] for g in GRAMMAR_LINEAGES}


def validate_extraction_config(
    focus: Optional[str], lineage: Optional[str]
) -> tuple[str, Optional[str]]:
    f = (focus or "general").strip().lower()
    if f not in EXTRACTION_FOCUS_IDS:
        raise ValueError(f"Invalid extraction_focus: {focus}")
    gl = (lineage or "").strip() or None
    if gl and gl not in GRAMMAR_LINEAGE_IDS:
        raise ValueError(f"Invalid grammar_lineage: {lineage}")
    if f != "grammar":
        gl = None
    elif not gl:
        gl = "woccon_attested"
    return f, gl


_LINEAGE_PROMPTS = {
    "woccon_attested": """GRAMMAR LINEAGE FILTER — attested Woccon only:
- Extract ONLY grammar/morphology/syntax notes grounded in attested Woccon forms (marked W (…) or clearly labeled Woccon).
- Each note MUST cite at least one attested Woccon example from the text and explain why the pattern is Woccon-specific.
- SKIP notes that are ONLY proto-Siouan, proto-Catawban, or comparative Siouan reconstructions without attested Woccon evidence.
- You may mention Catawba/proto forms as supporting comparanda, but the rule must be about Woccon.
- Set grammar_lineage to "woccon_attested".""",
    "siouan_comparative": """GRAMMAR LINEAGE FILTER — Siouan comparative:
- Extract comparative patterns across Siouan languages (Woccon, Catawba, Biloxi, etc.) without assigning a specific proto node.
- Do NOT extract standalone Woccon-only rules unless they explicitly compare across Siouan languages.
- Do NOT extract proto-Siouan or proto-Catawban reconstructions as the main claim.
- Set grammar_lineage to "siouan_comparative".""",
    "proto_siouan": """GRAMMAR LINEAGE FILTER — Proto-Siouan:
- Extract ONLY reconstructions and rules explicitly labeled Proto-Siouan, *PS, or pan-Siouan.
- SKIP attested Woccon-only patterns and proto-Catawban-only material unless the text frames it as Proto-Siouan.
- Set grammar_lineage to "proto_siouan".""",
    "proto_siouan_catawban": """GRAMMAR LINEAGE FILTER — Proto-Siouan-Catawban:
- Extract ONLY reconstructions for the Siouan-Catawban node (*PSC, Proto-Siouan-Catawban, Siouan-Catawban).
- SKIP generic Proto-Siouan-only or attested Woccon-only notes unless the text assigns them to this node.
- Set grammar_lineage to "proto_siouan_catawban".""",
    "proto_catawban": """GRAMMAR LINEAGE FILTER — Proto-Catawban:
- Extract ONLY Coastal Catawban / Catawba-Woccon node reconstructions (*PC, Proto-Catawban, Coastal Catawban).
- Attested Woccon forms may appear as evidence, but the claim must be a proto-Catawban reconstruction.
- Set grammar_lineage to "proto_catawban".""",
    "other_comparative": """GRAMMAR LINEAGE FILTER — other comparative:
- Extract Yuchi, Biloxi-only, methodological, or non-Siouan comparative material not covered by the proto nodes above.
- Set grammar_lineage to "other_comparative".""",
}


def build_extraction_prompt(
    *,
    context_header: str,
    text: str,
    focus: str = "general",
    grammar_lineage: Optional[str] = None,
) -> str:
    focus = focus if focus in EXTRACTION_FOCUS_IDS else "general"
    header = context_header or "Extract from the following source text."

    if focus == "vocabulary":
        task_block = """From the following text, extract ONLY:
1. lexicon_entries: Woccon vocabulary. Each item: woccon, english, pos (e.g. noun, verb), optionally pronunciation, and when possible source_page and source_excerpt (exact substring from the text, max 200 chars).

Do NOT extract grammar_notes, pronunciation_notes, or cultural_notes — return those as empty arrays.

Output ONLY a single JSON object with keys: "lexicon_entries", "grammar_notes", "pronunciation_notes", "cultural_notes". No markdown."""

    elif focus == "culture":
        task_block = """From the following text, extract ONLY:
1. cultural_notes: self-contained notes on cultural usage, ceremony, community practice, or ethnographic context tied to Woccon language material. Each object has "text" and when possible source_page, source_page_end, source_excerpt (max 800 chars).

Do NOT extract lexicon_entries, grammar_notes, or pronunciation_notes — return those as empty arrays.

Output ONLY a single JSON object with keys: "lexicon_entries", "grammar_notes", "pronunciation_notes", "cultural_notes". No markdown."""

    elif focus == "grammar":
        lineage = grammar_lineage if grammar_lineage in GRAMMAR_LINEAGE_IDS else "woccon_attested"
        lineage_block = _LINEAGE_PROMPTS[lineage]
        task_block = f"""From the following text, extract ONLY grammar rule PACKETS.

{lineage_block}

Each grammar_notes object MUST include:
- "text": self-contained rule packet (claim, evidence, structure, use, caveats — see revitalization goal below)
- "grammar_lineage": one of {sorted(GRAMMAR_LINEAGE_IDS)} (use "{lineage}" for every note in this run)
- when possible: source_page, source_page_end, source_excerpt (max 800 chars)

Do NOT extract lexicon_entries, pronunciation_notes, or cultural_notes — return those as empty arrays.

Output ONLY a single JSON object with keys: "lexicon_entries", "grammar_notes", "pronunciation_notes", "cultural_notes". No markdown."""

    elif focus == "pronunciation":
        task_block = """From the following text, extract ONLY:
1. pronunciation_notes: self-contained phonology/pronunciation rule PACKETS. Include when the source provides them:
   - Sound inventories, alternations, stress, syllable structure, orthography conventions
   - Pronunciation guides for Woccon forms (e.g. English-Woccon style (en-TOME) guides)
   - Phonological arguments with attested examples
   Each object has "text" and when possible source_page, source_page_end, source_excerpt (max 800 chars).

Do NOT extract lexicon_entries, grammar_notes, or cultural_notes — return those as empty arrays.
(If a word list includes inline pronunciation only, skip it unless the text discusses phonology.)

Output ONLY a single JSON object with keys: "lexicon_entries", "grammar_notes", "pronunciation_notes", "cultural_notes". No markdown."""

    else:
        task_block = (
            """From the following text, extract:
1. lexicon_entries: Woccon vocabulary. Each item: woccon, english, pos, optionally pronunciation, source_page, source_excerpt (max 200 chars).
2. grammar_notes: self-contained rule PACKETS. Each object: "text", "grammar_lineage" (one of: """
            + ", ".join(sorted(GRAMMAR_LINEAGE_IDS))
            + """), and when possible source_page, source_page_end, source_excerpt (max 800 chars).
3. pronunciation_notes: phonology/pronunciation (same object shape; grammar_lineage not required).
4. cultural_notes: cultural usage (same object shape; grammar_lineage not required).

For EVERY grammar_notes item, set grammar_lineage based on the primary claim:
- woccon_attested: attested Woccon forms are the evidence; rule applies to Woccon
- siouan_comparative: cross-Siouan comparison without a specific proto label
- proto_siouan / proto_siouan_catawban / proto_catawban: matching reconstruction level
- other_comparative: Yuchi, Biloxi-only, or other comparative framing

Output ONLY a single JSON object with keys: "lexicon_entries", "grammar_notes", "pronunciation_notes", "cultural_notes". No markdown."""
        )

    revitalization = """
GOAL — LANGUAGE REVITALIZATION:
This data will be used to revitalize Woccon. Grammar notes must be revisited STANDALONE (without the source document) so workers can apply attested patterns to analyze and coin new forms. Lexicon entries supply attested stems; grammar notes supply reusable combinatorics (affixes, templates, constraints).

Before outputting each grammar note, ask: could someone apply this rule to build or analyze a new Woccon form without reading the source? If not, add the missing forms, morpheme breakdowns, glosses, or examples from the text.

Grammar notes must be self-contained rule PACKETS (not one-line summaries). Include when the source provides them: claim, attested Woccon forms (and Catawba/proto when given), morpheme breakdown, use, and author caveats. If the source discusses two constructions, output separate grammar_notes."""

    return f"""You are extracting structured Woccon language data from community-authored text (Waccamaw people + Siouan linguist). This data is authoritative.

{revitalization}

{header}

{task_block}

Text:
---
{text}
---
JSON:"""
