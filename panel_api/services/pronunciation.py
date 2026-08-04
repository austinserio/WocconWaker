"""Normalize community pronunciation guides for storage and display."""
import re


def normalize_pronunciation(value: str | None) -> str | None:
    """Strip wrapping parentheses, slashes, and whitespace from a pronunciation guide."""
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    # Remove outer parens only when the whole string is one group: (rue-sa-may) -> rue-sa-may
    if s.startswith("(") and s.endswith(")") and s.count("(") == 1:
        s = s[1:-1].strip()
    # Remove IPA-style slashes: /foo/ -> foo
    if s.startswith("/") and s.endswith("/") and len(s) > 2:
        s = s[1:-1].strip()
    # Collapse internal whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


def pronunciation_guide_candidates(value: str | None) -> list[str]:
    """
    Expand a guide into preferred lookup/display variants.

    Handles LLM noise like "(AY-JAH-OH) or (YAH)" by preferring the first
    parenthetical alternative before the combined string.
    """
    if not value:
        return []
    raw = value.strip()
    if not raw:
        return []

    seen: set[str] = set()
    out: list[str] = []

    def add(candidate: str | None) -> None:
        clean = normalize_pronunciation(candidate)
        if not clean:
            return
        key = clean.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(clean)

    for group in re.findall(r"\(([^)]+)\)", raw):
        add(group)
    if re.search(r"\s+or\s+", raw, re.I):
        for part in re.split(r"\s+or\s+", raw, flags=re.I):
            add(part)
    add(raw)
    return out


def primary_pronunciation_guide(value: str | None) -> str | None:
    """Return the best single guide string for display/TTS lookup."""
    candidates = pronunciation_guide_candidates(value)
    return candidates[0] if candidates else None
